"""Outcome/provenance checks using isolated synthetic official-world fixtures.

These fixtures are not sponsor runs or evidence of policy performance. The
expected labels are specified by the scenario, independently of the exporter:
one refunded late order, one timely order, one undelivered order, one cancellation.
"""
from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import evidence_dataset as dataset
from reliability_experiment import FEATURE_NAMES


def example_bundle() -> dict:
    orders = [
        {"id": "late", "status": "delivered", "option": "next_day",
         "legs": [{}, {}], "deliveredAt": [1800, 1850]},
        {"id": "timely", "status": "delivered", "option": "same_day",
         "legs": [{}], "deliveredAt": [1000]},
        {"id": "unfinished", "status": "waiting", "option": "next_day",
         "legs": [{}], "deliveredAt": [None]},
        {"id": "cancelled", "status": "cancelled", "option": "same_day",
         "legs": [{}], "deliveredAt": [None]},
    ]
    prices = {"late": 15000, "timely": 11000, "unfinished": 13000, "cancelled": 9000}
    requests = [
        {"request": {"id": order["id"], "respondBy": 540},
         "quote": {order["option"]: prices[order["id"]]},
         "outcome": "won", "option": order["option"]}
        for order in orders
    ]
    # A second offered option is deliberately not the selected one. Its features
    # must not replace the chosen next-day option's decision-time feature row.
    requests[0]["quote"]["same_day"] = 19000
    return {
        "schemaVersion": 1, "world_id": "synthetic-world-a", "seed_group": "synthetic-seed-a",
        "policy": "baseline", "source": {"source_sha": "a" * 40},
        "snapshot": {
            "worldId": "synthetic-world-a", "now": 16680, "endsAt": 16680,
            "orders": orders,
            "gigs": [
                {"id": "shared", "stops": [{"orderId": "late"}, {"orderId": "timely"}]},
                {"id": "waiting", "stops": [{"orderId": "unfinished"}]},
            ],
        },
        "score": {"wonOrders": 3, "onTimeShare": 1 / 3, "marginCents": 12000,
                  "ranked": False, "undeliveredShare": 1 / 3},
        "events": [
            {"seq": 1, "kind": "gig_dropped", "gigId": "shared", "at": 600},
            {"seq": 2, "kind": "visit_failed", "gigId": "shared", "orderId": "late",
             "leg": 0, "reason": "closed", "at": 700},
            {"seq": 3, "kind": "ledger", "at": 1850,
             "line": {"kind": "late_refund", "orderId": "late", "gigId": None, "cents": -1500}},
            {"seq": 4, "kind": "ledger", "at": 16680,
             "line": {"kind": "undelivered_penalty", "orderId": "unfinished", "gigId": None, "cents": -26000}},
            {"seq": 5, "kind": "order_cancelled", "orderId": "cancelled", "at": 800, "gigs": []},
        ],
        "reveal": {"requests": requests, "orders": [], "views": []},
        "roster": [], "map": {"places": [], "roads": []},
    }


def feature_record(order_id: str, option: str, price: int, marker: float) -> dict:
    features = {name: float(index) / 10 for index, name in enumerate(FEATURE_NAMES)}
    features["slack_hours"] = marker
    return {"world_id": "synthetic-world-a", "seed_group": "synthetic-seed-a",
            "policy": "baseline", "partition": "development", "order_id": order_id,
            "option": option, "quoted_price": price, "at": 520, "features": features}


def example_features() -> list[dict]:
    return [
        feature_record("late", "next_day", 14000, 9),  # Replaced quote, not final.
        feature_record("late", "next_day", 15000, 11),
        feature_record("timely", "same_day", 11000, 22),
        feature_record("unfinished", "next_day", 13000, 33),
        feature_record("cancelled", "same_day", 9000, 88),
        feature_record("late", "same_day", 19000, 99),  # Offered but not chosen.
    ]


class OfficialOutcomeReconciliationTests(unittest.TestCase):
    def test_refunded_and_undelivered_orders_are_late(self) -> None:
        labels, causes = dataset.labels_and_causes(example_bundle())
        self.assertEqual({key: row["late"] for key, row in labels.items()},
                         {"late": 1, "timely": 0, "unfinished": 1})
        self.assertEqual(causes["late"]["orders"], 2)
        self.assertEqual(causes["on_time"]["orders"], 1)

    def test_cancelled_order_never_enters_target_or_denominator(self) -> None:
        bundle = example_bundle()
        bundle["events"].append({"seq": 6, "kind": "ledger", "at": 700,
                                 "line": {"kind": "late_refund", "orderId": "cancelled", "gigId": None, "cents": -100}})
        labels, _ = dataset.labels_and_causes(bundle)
        self.assertNotIn("cancelled", labels)
        self.assertEqual(len(labels), 3)
        self.assertEqual(sum(row["late"] == 0 for row in labels.values()), 1)

    def test_disagreement_with_official_score_is_rejected(self) -> None:
        for change in ({"wonOrders": 4}, {"onTimeShare": 2 / 3}, {"onTimeShare": 0.4}):
            with self.subTest(score_change=change):
                bundle = example_bundle()
                bundle["score"].update(change)
                with self.assertRaises(ValueError):
                    dataset.labels_and_causes(bundle)

    def test_order_visit_failure_is_local_but_booking_drop_is_gig_wide(self) -> None:
        labels, _ = dataset.labels_and_causes(example_bundle())
        self.assertTrue(labels["late"]["flags"]["failed_visit"])
        self.assertEqual(labels["late"]["failure_reasons"], ["closed"])
        self.assertFalse(labels["timely"]["flags"]["failed_visit"])
        self.assertEqual(labels["timely"]["failure_reasons"], [])
        self.assertTrue(labels["late"]["flags"]["driver_drop"])
        self.assertTrue(labels["timely"]["flags"]["driver_drop"])
        self.assertFalse(labels["unfinished"]["flags"]["driver_drop"])


class EvidenceDatasetJoinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="bahn-evidence-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "input"
        self.run_directory = self.root / "run"
        self.run_directory.mkdir(parents=True)
        self.destination = Path(self.temporary.name) / "output"
        self.bundle = example_bundle()
        self.records = example_features()
        self.bundle_path = self.run_directory / "synthetic-world-a.json.gz"
        self.receipt_path = self.run_directory / "run.json"
        self.feature_path = self.run_directory / "decision_features.jsonl"
        self.write_bundle_and_receipt()
        self.write_features()

    def write_bundle_and_receipt(self) -> None:
        raw = json.dumps(self.bundle, sort_keys=True, allow_nan=False).encode()
        self.bundle_path.write_bytes(gzip.compress(raw, mtime=0))
        self.receipt = {
            "schemaVersion": 1, "state": "completed", "world_id": self.bundle["world_id"],
            "config": {"seed_group": self.bundle["seed_group"], "policy": self.bundle["policy"],
                       "partition": "development"},
            "evidence": {"world_id": self.bundle["world_id"], "bundle": self.bundle_path.name,
                         "sha256": hashlib.sha256(self.bundle_path.read_bytes()).hexdigest()},
        }
        self.receipt_path.write_text(json.dumps(self.receipt))

    def write_features(self) -> None:
        self.feature_path.write_text("".join(json.dumps(row) + "\n" for row in self.records))

    def read_orders(self) -> list[dict]:
        with open(self.destination / "orders.csv", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_features_join_to_last_quote_and_chosen_option_only(self) -> None:
        result = dataset.build(self.root, self.destination)
        rows = {row["order_id"]: row for row in self.read_orders()}
        self.assertEqual(result["decision_rows"], 3)
        self.assertEqual(set(rows), {"late", "timely", "unfinished"})
        self.assertEqual({key: float(row["slack_hours"]) for key, row in rows.items()},
                         {"late": 11, "timely": 22, "unfinished": 33})
        self.assertEqual({key: int(row["late"]) for key, row in rows.items()},
                         {"late": 1, "timely": 0, "unfinished": 1})
        for row in rows.values():
            self.assertEqual(row["official_won_orders"], "3")
            self.assertEqual(row["official_on_time_orders"], "1")
            self.assertEqual(row["partition"], "development")

    def test_receipt_must_bind_world_seed_policy_hash_and_completion(self) -> None:
        changes = [
            ("world", lambda value: value.update(world_id="different-world")),
            ("seed", lambda value: value["config"].update(seed_group="different-seed")),
            ("policy", lambda value: value["config"].update(policy="different-policy")),
            ("bundle_hash", lambda value: value["evidence"].update(sha256="0" * 64)),
            ("completion", lambda value: value.update(state="interrupted")),
        ]
        for name, mutate in changes:
            with self.subTest(mismatch=name):
                receipt = copy.deepcopy(self.receipt)
                mutate(receipt)
                self.receipt_path.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    dataset.build(self.root, self.destination)

    def test_snapshot_identity_must_match_envelope_even_with_valid_hash(self) -> None:
        self.bundle["snapshot"]["worldId"] = "another-world"
        self.write_bundle_and_receipt()
        with self.assertRaises(ValueError):
            dataset.build(self.root, self.destination)

    def test_feature_at_response_deadline_or_later_is_rejected(self) -> None:
        for at in (540, 541):
            with self.subTest(at=at):
                self.records[1]["at"] = at
                self.write_features()
                with self.assertRaises(ValueError):
                    dataset.build(self.root, self.destination)

    def test_last_quoted_price_mismatch_is_rejected(self) -> None:
        self.records[1]["quoted_price"] += 1
        self.write_features()
        with self.assertRaises(ValueError):
            dataset.build(self.root, self.destination)

    def test_missing_chosen_option_cannot_use_other_offered_option(self) -> None:
        self.records = [row for row in self.records if not (row["order_id"] == "late" and row["option"] == "next_day")]
        self.write_features()
        with self.assertRaises(ValueError):
            dataset.build(self.root, self.destination)

    def test_reveal_outcome_and_choice_must_agree_with_won_order(self) -> None:
        for change in ({"outcome": "lost"}, {"option": "same_day"}):
            with self.subTest(reveal_change=change):
                self.bundle = example_bundle()
                self.bundle["reveal"]["requests"][0].update(change)
                self.write_bundle_and_receipt()
                with self.assertRaises(ValueError):
                    dataset.build(self.root, self.destination)

    def test_feature_world_mismatch_is_rejected(self) -> None:
        self.records[1]["world_id"] = "another-world"
        self.write_features()
        with self.assertRaises(ValueError):
            dataset.build(self.root, self.destination)

    def test_empty_feature_rebuild_refreshes_csv_instead_of_reusing_old_rows(self) -> None:
        dataset.build(self.root, self.destination)
        self.assertEqual(len(self.read_orders()), 3)
        self.feature_path.unlink()
        result = dataset.build(self.root, self.destination)
        self.assertEqual(result["decision_rows"], 0)
        self.assertEqual(self.read_orders(), [])
        with open(self.destination / "orders.csv", newline="") as stream:
            header = next(csv.reader(stream))
        self.assertIn("late", header)
        self.assertTrue(set(FEATURE_NAMES).issubset(header))

    def test_historical_export_does_not_invent_features_or_blind_status(self) -> None:
        self.feature_path.unlink()
        self.receipt_path.unlink()
        result = dataset.build(self.root, self.destination)
        self.assertEqual(result["decision_rows"], 0)
        self.assertEqual(result["worlds"][0]["partition"], "historical")
        self.assertEqual(self.read_orders(), [])


if __name__ == "__main__":
    unittest.main()
