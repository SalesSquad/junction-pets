"""Affected-path checks for real admission defects; no sponsor/network calls."""
from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from admission_experiment import AdmissionDesk
from reliability_experiment import (
    FEATURE_NAMES, ReliabilityDesk, eligible_driver_ids, features_for,
    load_model, main, outstanding_backlog, unbooked_age_minutes,
)
from test_dispatch import FakeWorld, request, won_order


def flexible_request(identifier="R1", *, next_price=11000, slow_price=10800):
    req = request()
    req["id"] = identifier
    req["referenceFeeCents"] = 3500
    req["options"] = [
        {"kind": "next_day", "deadline": 2200, "listPriceCents": next_price},
        {"kind": "within_3_days", "deadline": 4200, "listPriceCents": slow_price},
    ]
    return req


def model_artifact(probability=0.01):
    return {
        "schemaVersion": 1, "featureNames": list(FEATURE_NAMES),
        "center": [0] * len(FEATURE_NAMES), "scale": [1] * len(FEATURE_NAMES),
        "coefficients": [math.log(probability / (1 - probability))]
                        + [0] * len(FEATURE_NAMES),
        "training": {"source_sha": "a" * 40,
                     "world_ids": ["SYNTHETIC-CONTRACT-FIXTURE-NOT-A-SPONSOR-WORLD"]},
        "threshold": 0.05,
    }


class ReliabilityContracts(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "SPREAD_GUARD_POLICY": "risk_budget",
            "SPREAD_RELIABILITY_MODEL": "",
            "SPREAD_RELIABILITY_LATE_THRESHOLD": "",
            "SPREAD_ADMISSION_PRICE_PCT": "139",
            "SPREAD_ADMISSION_EXTRA_SLACK": "240",
            "SPREAD_ADMISSION_SURGE_PER_BACKLOG": "0",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def write_model(self, artifact=None):
        path = Path(self.temp.name) / "fixture-model.json"
        path.write_text(json.dumps(artifact or model_artifact()), encoding="utf-8")
        return path

    def desk(self, mode="baseline", *, model_path=None, slack=1100):
        desk = ReliabilityDesk(FakeWorld(), 8, 480, mode=mode, model_path=model_path)
        desk._slack = lambda _request, _option: slack
        return desk

    def test_frozen_baseline_matches_existing_quotes_and_fees(self):
        req = request()
        control = AdmissionDesk(FakeWorld(), 8, 480)
        control.quote(copy.deepcopy(req))
        # Old experimental env knobs must not contaminate the frozen control.
        with patch.dict(os.environ, {"SPREAD_ADMISSION_PRICE_PCT": "100",
                                     "SPREAD_ADMISSION_EXTRA_SLACK": "720",
                                     "SPREAD_ADMISSION_SURGE_PER_BACKLOG": "5"}):
            candidate = ReliabilityDesk(FakeWorld(), 8, 480, mode="baseline")
            candidate.quote(copy.deepcopy(req))
        self.assertEqual(candidate.outbox, control.outbox)
        order = won_order(req)
        self.assertEqual(candidate.fees_for(order, 1), control.fees_for(order, 1))
        self.assertEqual((candidate.quote_pct, candidate.extra_slack), (139, 240))

    def test_deadline_prefers_safer_option_with_small_margin_tradeoff(self):
        req = flexible_request()
        baseline, safer = self.desk(), self.desk("deadline")
        for desk in (baseline, safer):
            desk._slack = lambda _r, option: 780 if option["kind"] == "next_day" else 1400
            desk.quote(copy.deepcopy(req))
        self.assertEqual(baseline.outbox[-1]["prices"], {"next_day": 15290})
        self.assertEqual(safer.outbox[-1]["prices"], {"within_3_days": 15012})

    def test_deadline_does_not_sacrifice_unbounded_margin_or_economic_floor(self):
        safer = self.desk("deadline")
        safer._slack = lambda _r, option: 780 if option["kind"] == "next_day" else 1400
        safer.quote(flexible_request(slow_price=6000))
        self.assertEqual(safer.outbox[-1]["prices"], {"next_day": 15290})
        req = flexible_request("R2")
        req["referenceFeeCents"] = 100000
        safer.quote(req)
        self.assertEqual(safer.outbox[-1]["prices"], {"next_day": 220000})

    def test_capacity_rejects_nominal_supply_without_eligible_drivers(self):
        req = flexible_request()
        req["legs"][0]["car"]["premium"] = True
        desk = self.desk("capacity")
        desk.roster[1]["rating"] = 4.7
        desk.roster[2]["completedGigs"] = 10
        desk.roster[3]["licence"] = "automatic_only"
        self.assertEqual(desk._driver_count("A"), 4)  # previous proxy overcounts
        self.assertEqual(eligible_driver_ids(req, desk), ["D0"])
        desk.quote(req)
        self.assertEqual(desk.outbox[-1]["prices"], {"next_day": 220000})

    def test_completed_orders_with_stale_status_are_not_backlog(self):
        baseline, capacity = self.desk(slack=800), self.desk("capacity", slack=800)
        req = flexible_request()
        req["options"] = req["options"][:1]
        for desk in (baseline, capacity):
            for i in range(5):
                done = won_order(flexible_request(f"done-{i}"))
                done["deliveredAt"] = [400]
                done["status"] = "waiting"  # genuine starter.delivered behavior
                desk.orders[done["id"]] = done
            self.assertEqual(outstanding_backlog(req, desk), 0)
            desk.quote(copy.deepcopy(req))
        self.assertEqual(baseline.outbox[-1]["prices"], {"next_day": 220000})
        self.assertEqual(capacity.outbox[-1]["prices"], {"next_day": 15290})

    def test_outstanding_quotes_reserve_capacity_and_refusal_releases_it(self):
        desk = self.desk("capacity")
        desk.roster = desk.roster[:2]
        desk.quote(flexible_request("first"))
        first_action = desk.outbox[-1]
        desk.quote(flexible_request("second"))
        self.assertEqual(first_action["prices"], {"next_day": 15290})
        self.assertEqual(desk.outbox[-1]["prices"], {"next_day": 220000})
        desk.read_results([first_action], [{"ok": False, "reason": "expired"}])
        desk.quote(flexible_request("third"))
        self.assertEqual(desk.outbox[-1]["prices"], {"next_day": 15290})

    def test_result_and_expiry_release_quote_reservations(self):
        desk = self.desk("capacity")
        req = flexible_request("first")
        desk.quote(req)
        self.assertIn("first", desk.pending_quotes)
        desk.handle({"kind": "order_lost", "seq": 1, "at": 490, "requestId": "first"})
        self.assertNotIn("first", desk.pending_quotes)
        desk.quote(flexible_request("second"))
        desk.now = 495
        later = flexible_request("later")
        later["respondBy"] = 510
        self.assertEqual(features_for(later, later["options"][0], desk)["pending_quotes"], 0)

    def add_open_gig(self, desk, *, posted_at=100, order_id="old", gig_id="g-old"):
        req = flexible_request(order_id)
        order = won_order(req)
        desk.requests[order_id] = req
        desk.orders[order_id] = order
        desk._posted_at[gig_id] = posted_at
        desk.carry({"type": "post", "stops": [
            {"orderId": order_id, "leg": 0, "kind": "pickup"},
            {"orderId": order_id, "leg": 0, "kind": "delivery"}],
            "audience": {"experienced": False, "manualLicence": True},
            "schedule": [{"at": posted_at, "feeCents": 3500}]}, gig_id)

    def test_unresolved_booking_age_changes_admission_without_completed_samples(self):
        desk = self.desk("capacity", slack=1100)
        self.add_open_gig(desk, posted_at=0)
        self.assertEqual(len(desk.booking_delays), 0)
        self.assertEqual(unbooked_age_minutes(flexible_request(), desk), 480)
        req = flexible_request()
        req["options"] = req["options"][:1]
        desk.quote(req)
        self.assertEqual(desk.outbox[-1]["prices"], {"next_day": 220000})

    def test_historical_or_booked_posts_do_not_pollute_unbooked_age(self):
        desk = self.desk("capacity")
        self.add_open_gig(desk, posted_at=100)
        self.add_open_gig(desk, posted_at=-5000, order_id="finished", gig_id="g-finished")
        desk.orders["finished"]["deliveredAt"] = [400]
        desk.posts["g-historical"] = {"schedule": [{"at": -10000, "feeCents": 1}]}
        req = flexible_request()
        self.assertEqual(unbooked_age_minutes(req, desk), 380)
        desk.booked.add("g-old")
        self.assertEqual(unbooked_age_minutes(req, desk), 0)

    def test_drop_starts_new_wait_instead_of_counting_booked_time(self):
        desk = self.desk("capacity")
        self.add_open_gig(desk, posted_at=100)
        desk.handle({"kind": "gig_booked", "seq": 1, "at": 200,
                     "gigId": "g-old", "driverId": "D0", "feeCents": 3500})
        desk.handle({"kind": "gig_dropped", "seq": 2, "at": 450,
                     "gigId": "g-old", "driverId": "D0"})
        self.assertEqual(unbooked_age_minutes(flexible_request(), desk), 30)

    def test_feature_contract_is_ordered_pure_and_ignores_future_label_fields(self):
        desk = self.desk("capacity")
        req = flexible_request()
        before = copy.deepcopy((desk.requests, desk.orders, desk.pending_quotes, desk.outbox))
        features = features_for(req, req["options"][0], desk)
        self.assertEqual(tuple(features), FEATURE_NAMES)
        self.assertTrue(all(type(value) is float and math.isfinite(value) for value in features.values()))
        self.assertEqual(before, (desk.requests, desk.orders, desk.pending_quotes, desk.outbox))
        req["deliveredAt"], req["labelLate"], req["finalMarginCents"] = [9999], 1, -100000
        self.assertEqual(features, features_for(req, req["options"][0], desk))
        self.assertEqual(desk.feature_vector(req, req["options"][0]), list(features.values()))

    def test_model_standardization_and_late_veto(self):
        artifact = model_artifact()
        artifact["center"][0], artifact["scale"][0] = 10, 2
        artifact["coefficients"] = [0, -1] + [0] * (len(FEATURE_NAMES) - 1)
        model = load_model(self.write_model(artifact))
        features = {name: 0.0 for name in FEATURE_NAMES}
        features["slack_hours"] = 14
        self.assertAlmostEqual(model.predict(features), 1 / (1 + math.exp(2)))
        for probability, expected in ((0.20, 220000), (0.01, 15290)):
            desk = self.desk("learned", model_path=self.write_model(model_artifact(probability)))
            desk.quote(flexible_request())
            self.assertEqual(desk.outbox[-1]["prices"], {"next_day": expected})

    def test_invalid_model_contracts_fail_closed(self):
        alterations = [
            ("schemaVersion", True), ("featureNames", list(reversed(FEATURE_NAMES))),
            ("scale", [0] * len(FEATURE_NAMES)),
            ("coefficients", [math.nan] + [0] * len(FEATURE_NAMES)),
            ("coefficients", [True] + [0] * len(FEATURE_NAMES)),
            ("training", {"source_sha": "a" * 40, "world_ids": []}),
            ("training", {"source_sha": "main", "world_ids": ["test"]}),
            ("threshold", 1),
        ]
        for field, value in alterations:
            with self.subTest(field=field, value=value):
                artifact = model_artifact()
                artifact[field] = value
                with self.assertRaises(ValueError):
                    load_model(self.write_model(artifact))

    def test_invalid_explicit_model_prevents_world_initialization_and_cli_run(self):
        missing = str(Path(self.temp.name) / "missing.json")
        world = FakeWorld()
        with patch.object(world.client, "map") as fetch_map:
            with self.assertRaises(OSError):
                ReliabilityDesk(world, 8, 480, mode="baseline", model_path=missing)
            fetch_map.assert_not_called()
        with patch("reliability_experiment.starter.main") as run, patch("sys.stderr"):
            with self.assertRaises(SystemExit) as stopped:
                main(["--mode", "learned", "--model", missing, "--level", "8"])
            self.assertNotEqual(stopped.exception.code, 0)
            run.assert_not_called()
        with self.assertRaises(ValueError):
            ReliabilityDesk(world, 8, 480, mode="learned")

    def test_trust_is_an_isolated_bounded_price_ablation(self):
        baseline, trust = self.desk(), self.desk("trust")
        req = flexible_request()
        baseline.quote(copy.deepcopy(req))
        trust.quote(copy.deepcopy(req))
        self.assertEqual(trust.outbox[-1], baseline.outbox[-1])
        trust.trust[req["dealerId"]] = 25
        trust.quote(flexible_request("second"))
        self.assertEqual(trust.outbox[-1]["prices"], {"next_day": 16390})
        self.assertEqual(trust.fees_for(won_order(req), 1), baseline.fees_for(won_order(req), 1))

    def test_rejoin_preserves_original_post_age_after_repricing(self):
        desk = self.desk("capacity")
        req = flexible_request("old")
        order = won_order(req)
        desk.now = 1000
        desk.pending_quotes["stale"] = {"expires_at": 2000, "origin": "A", "driver_id": "D0"}
        gig = {"id": "g1", "status": "open", "driverId": None,
               "postedAt": 500, "feeCents": 4000,
               "stops": [{"orderId": "old", "leg": 0, "kind": "pickup"},
                         {"orderId": "old", "leg": 0, "kind": "delivery"}],
               "audience": {"experienced": False, "manualLicence": True},
               "schedule": [{"at": 900, "feeCents": 4000}]}
        desk.rejoin({"now": 1000, "openRequests": [], "orders": [order], "gigs": [gig]},
                    [{"kind": "price_request", "seq": 1, "at": 480, "request": req}])
        self.assertFalse(desk.pending_quotes)
        self.assertEqual(unbooked_age_minutes(flexible_request(), desk), 500)


if __name__ == "__main__":
    unittest.main()
