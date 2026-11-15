"""Mock-only checks of official fork gating, provenance and safe resumption."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fork_study import (
    check_model_separation, read_json, require_practice, run, state_fingerprint,
)
from reliability_experiment import ReliabilityDesk
from test_dispatch import FakeWorld as SdkFixtureWorld


def summary(world_id, *, parent=None, **changes):
    value = {"worldId": world_id, "kind": "practice", "level": 8,
             "parent": parent, "season": None, "boardRun": None, "ended": False}
    return {**value, **changes}


class MockWorld:
    def __init__(self, client, world_id, snapshot=None, history=None):
        self.client, self.id = client, world_id
        score = {"marginCents": 0, "revenueCents": 0, "marginShare": 0,
                 "wonOrders": 0, "onTimeShare": 0, "undeliveredShare": 0,
                 "ranked": False}
        self.state = copy.deepcopy(snapshot or {
            "now": 480, "endsAt": 600, "openRequests": [], "orders": [],
            "gigs": [], "driverPositions": [], "score": score})
        self.state["worldId"] = world_id
        self.history = copy.deepcopy(history if history is not None else [
            {"kind": "ledger", "seq": 1, "at": 400,
             "line": {"kind": "failed_visit", "orderId": "historical", "cents": -100}}
        ])
        self.advance_calls = 0

    def snapshot(self):
        return copy.deepcopy(self.state)

    def events(self):
        return copy.deepcopy(self.history)

    def roster(self):
        return SdkFixtureWorld().roster()

    def score(self):
        return copy.deepcopy(self.state["score"])

    def fork(self):
        self.client.fork_calls += 1
        world_id = f"child-{self.client.fork_calls}"
        child = MockWorld(self.client, world_id, self.state, self.history)
        self.client.objects[world_id] = child
        self.client.summaries[world_id] = summary(world_id, parent=self.id)
        if self.client.change_parent_after_fork:
            self.state["now"] += 1
        if self.client.lose_next_response:
            self.client.lose_next_response = False
            raise ConnectionError("synthetic lost fork response")
        return child

    def advance(self, *, until, max, actions):
        if self.id == "parent":
            raise AssertionError("Parent must never advance")
        receipt = read_json(self.client.output / "fork_run.json")
        ids = [item.get("world_id") for item in receipt["children"].values()]
        if len(set(ids)) != 2 or None in ids:
            raise AssertionError("Both child IDs must be durable before any action")
        self.advance_calls += 1
        self.state["now"] = self.state["endsAt"]
        self.client.summaries[self.id]["ended"] = True
        event = {"kind": "ledger", "seq": 2, "at": self.state["now"],
                 "line": {"kind": "failed_visit", "orderId": "historical", "cents": -25}}
        # The official API repeats a fork's whole prehistory on first advance.
        events = [*copy.deepcopy(self.history), event]
        self.history.append(event)
        return {"now": self.state["now"], "events": events,
                "results": [{"ok": True} for _ in actions]}

    def act(self, actions):
        raise AssertionError("This fixture has no action that needs direct sending")

    def reveal(self):
        children = [item for item in self.client.summaries.values() if item.get("parent") == "parent"]
        if len(children) != 2 or not all(item["ended"] for item in children):
            raise AssertionError("No future reveal may be read before BOTH children finish")
        self.client.reveal_calls += 1
        return {"fixture": "synthetic, not sponsor evidence"}


class MockClient:
    def __init__(self, output):
        self.output = Path(output)
        self.fork_calls = self.reveal_calls = 0
        self.lose_next_response = self.change_parent_after_fork = False
        self.summaries = {"parent": summary("parent")}
        self.objects = {"parent": MockWorld(self, "parent")}

    def worlds(self):
        return copy.deepcopy(list(self.summaries.values()))

    def world(self, world_id):
        return self.objects[world_id]

    def map(self):
        return SdkFixtureWorld().client.map()


class ForkStudyContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {
            "SPREAD_GUARD_POLICY": "risk_budget", "SPREAD_RELIABILITY_MODEL": "",
            "SPREAD_RELIABILITY_LATE_THRESHOLD": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.args = argparse.Namespace(parent="parent", output=self.temp.name,
            candidate="deadline", seed_group=None, model=None, late_threshold=None,
            max_steps=100, max_wall_seconds=60, max_minutes=1440,
            recover_baseline=None, recover_candidate=None)
        self.client = MockClient(self.temp.name)

    def test_official_parent_gate_rejects_final_board_ended_and_unknown(self):
        for change in ({"kind": "final"}, {"boardRun": 1}, {"ended": True},
                       {"season": 3}, {"ended": None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                require_practice(summary("parent", **change))
        del self.client.summaries["parent"]
        with self.assertRaises(ValueError):
            run(self.args, self.client)
        self.assertEqual(self.client.fork_calls, 0)

    def test_same_future_pair_pins_public_prefix_and_does_not_invent_seed(self):
        result = run(self.args, self.client)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(self.client.fork_calls, 2)
        self.assertEqual(self.client.objects["parent"].advance_calls, 0)
        self.assertEqual(self.client.objects["parent"].state["now"], 480)
        self.assertIsNone(result["seed"])
        self.assertEqual(result["seed_provenance"], "unknown")
        self.assertFalse(result["same_future_evidence"]["hidden_rng_observed"])
        self.assertEqual(result["parent"]["fingerprint"]["history_count"], 1)
        self.assertEqual(result["comparison"]["margin_delta_cents"], 0)
        self.assertEqual(self.client.reveal_calls, 2)
        self.assertIn("reliability_experiment.py", result["config"]["source"]["files_sha256"])
        self.assertIn("client.py", result["config"]["source"]["sdk_files_sha256"])

    def test_history_rejoin_deduplicates_first_child_advance(self):
        created = []

        class ObservedDesk(ReliabilityDesk):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                created.append(self)

        with patch("fork_study.ReliabilityDesk", ObservedDesk):
            run(self.args, self.client)
        self.assertEqual(len(created), 2)
        for desk in created:
            # The old -100 ledger line must not be charged twice by history replay.
            self.assertEqual(desk.expenses_by_order["historical"], 125)
            self.assertEqual(desk.seen, {1, 2})

    def test_completed_resume_creates_no_duplicate_children_or_actions(self):
        result = run(self.args, self.client)
        again = run(self.args, self.client)
        self.assertEqual(again, result)
        self.assertEqual(self.client.fork_calls, 2)
        self.assertEqual(sum(w.advance_calls for w in self.client.objects.values()), 2)

    def test_uncertain_fork_is_not_retried_and_explicit_recovery_is_verified(self):
        self.client.lose_next_response = True
        with self.assertRaises(ConnectionError):
            run(self.args, self.client)
        receipt = read_json(Path(self.temp.name) / "fork_run.json")
        self.assertEqual(receipt["children"]["baseline"]["state"], "fork_delivery_unknown")
        with self.assertRaisesRegex(ValueError, "not retried"):
            run(self.args, self.client)
        self.assertEqual(self.client.fork_calls, 1)
        self.args.recover_baseline = "child-1"
        recovered = run(self.args, self.client)
        self.assertEqual(recovered["state"], "completed")
        self.assertEqual(self.client.fork_calls, 2)
        self.assertEqual(recovered["children"]["baseline"]["world_id"], "child-1")

    def test_changed_parent_aborts_before_second_fork_or_play(self):
        self.client.change_parent_after_fork = True
        with self.assertRaisesRegex(ValueError, "Parent no longer"):
            run(self.args, self.client)
        self.assertEqual(self.client.fork_calls, 1)
        self.assertEqual(sum(w.advance_calls for w in self.client.objects.values()), 0)
        receipt = read_json(Path(self.temp.name) / "fork_run.json")
        self.assertEqual(receipt["children"]["baseline"]["world_id"], "child-1")

    def test_seed_label_is_explicit_and_same_future_is_not_independent_data(self):
        self.args.seed_group = "owner-declared-seed-17"
        result = run(self.args, self.client)
        self.assertEqual(result["seed"], self.args.seed_group)
        self.assertEqual(result["seed_provenance"], "caller_label")
        self.assertTrue(result["future_group"].startswith("fork:parent:"))
        self.assertIn("not independent", result["comparison"]["scope"])

    def test_model_family_and_declared_group_leakage_are_rejected(self):
        worlds = [summary("ancestor"), summary("parent", parent="ancestor"),
                  summary("trained-sibling", parent="ancestor")]
        model = SimpleNamespace(training={"world_ids": ["trained-sibling"]})
        with self.assertRaisesRegex(ValueError, "family"):
            check_model_separation(model, "parent", worlds, None)
        model = SimpleNamespace(training={"world_ids": ["unrelated"], "seed_groups": ["same-seed"]})
        with self.assertRaisesRegex(ValueError, "seed group"):
            check_model_separation(model, "parent", worlds, "same-seed")

    def test_missing_model_and_excessive_bounds_fail_before_fork(self):
        self.args.candidate = "learned"
        with self.assertRaises(ValueError):
            run(self.args, self.client)
        self.args.candidate, self.args.max_steps = "deadline", 50001
        with self.assertRaises(ValueError):
            run(self.args, self.client)
        self.assertEqual(self.client.fork_calls, 0)

    def test_team_slot_limit_is_checked_before_creating_children(self):
        for i in range(6):
            self.client.summaries[f"other-{i}"] = summary(f"other-{i}")
        with self.assertRaisesRegex(ValueError, "slots"):
            run(self.args, self.client)
        self.assertEqual(self.client.fork_calls, 0)

    def test_resume_rejects_changed_policy(self):
        run(self.args, self.client)
        self.args.candidate = "trust"
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            run(self.args, self.client)
        self.assertEqual(self.client.fork_calls, 2)

    def test_fingerprint_excludes_only_world_identity_and_rejects_future_events(self):
        parent = self.client.objects["parent"]
        child = copy.deepcopy(parent.state)
        child["worldId"] = "other-id"
        self.assertEqual(state_fingerprint(parent.state, parent.history),
                         state_fingerprint(child, parent.history))
        future = copy.deepcopy(parent.history)
        future[0]["at"] = 481
        with self.assertRaises(ValueError):
            state_fingerprint(child, future)
        child["score"]["marginCents"] = 1
        self.assertNotEqual(state_fingerprint(parent.state, parent.history),
                            state_fingerprint(child, parent.history))


if __name__ == "__main__":
    unittest.main()
