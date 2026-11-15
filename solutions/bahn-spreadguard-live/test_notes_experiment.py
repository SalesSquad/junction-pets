"""Bounded note-to-action checks; fixtures never contact the sponsor service."""
from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

from spread import starter

from notes_experiment import NotesDesk, supported_constraints
from reliability_experiment import ReliabilityDesk
from test_dispatch import FakeWorld, request, won_order


def noted_request(text: str) -> dict:
    value = request()
    value["arrivedAt"] = 480
    value["respondBy"] = 495
    value["note"] = {"text": text, "lang": "en"}
    value["legs"][0]["pickup"]["window"] = {"from": 540, "to": 4200}
    value["legs"][0]["delivery"]["window"] = {"from": 540, "to": 4200}
    value["options"] = [{"kind": "within_3_days", "deadline": 4200, "listPriceCents": 14000}]
    return value


class NotesActionContracts(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {
            "SPREAD_GUARD_POLICY": "risk_budget",
            "SPREAD_RELIABILITY_MODEL": "",
            "SPREAD_RELIABILITY_LATE_THRESHOLD": "",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def desk(self, request_value: dict, kind=NotesDesk):
        desk = kind(FakeWorld(), 8, 480, mode="baseline")
        desk.requests[request_value["id"]] = request_value
        return desk

    def test_ready_tomorrow_reaches_wire_as_lower_bound_on_original_order(self) -> None:
        value = noted_request("Ready tomorrow at 14:00.")
        original = copy.deepcopy(value)
        order = won_order(value)
        order["legs"][0]["pickup"]["window"] = {"from": 540, "to": 4200}
        order_original = copy.deepcopy(order)
        desk = self.desk(value)
        desk.post(order, [0])
        action = desk.outbox[-1]
        self.assertEqual(action["stops"][0]["window"], {"from": 2280, "to": 4200})
        self.assertEqual(value, original)
        self.assertEqual(order, order_original)
        self.assertEqual(action["schedule"], self.desk(value, ReliabilityDesk).fees_for(order, 1))
        self.assertEqual(desk.notes_summary()["orders_with_added_post_constraints"], 1)
        self.assertEqual(desk.notes_summary()["orders_with_changed_post_actions"], 1)

    def test_payment_release_manual_and_plates_propagate_without_early_pickup(self) -> None:
        value = noted_request("Payment after 13:30. Manual gearbox. No plates.")
        constraints, reason = supported_constraints(value)
        self.assertEqual(reason, "supported")
        self.assertEqual(constraints.releaseAt, 810)
        desk = self.desk(value)
        order = won_order(value)
        desk.post(order, [0])
        action = desk.outbox[-1]
        self.assertTrue(action["audience"]["manualLicence"])
        self.assertTrue(action["stops"][0]["withPlates"])
        self.assertEqual(action["stops"][0]["window"]["from"], 810)

    def test_explicit_negative_requirements_do_not_become_positive(self) -> None:
        value = noted_request("Not manual. Has plates.")
        self.assertEqual(supported_constraints(value)[1], "supported")
        desk = self.desk(value)
        desk.post(won_order(value), [0])
        action = desk.outbox[-1]
        self.assertFalse(action["audience"]["manualLicence"])
        self.assertFalse(action["stops"][0]["withPlates"])

    def test_retry_constraints_are_never_weakened(self) -> None:
        value = noted_request("Ready at 13:00. Not manual. Has plates.")
        desk = self.desk(value)
        desk.post(won_order(value), [0], starter.Retry(900, manual_licence=True, plates=True))
        action = desk.outbox[-1]
        self.assertEqual(action["stops"][0]["window"]["from"], 900)
        self.assertTrue(action["audience"]["manualLicence"])
        self.assertTrue(action["stops"][0]["withPlates"])

    def test_quote_slack_uses_one_parser_and_does_not_change_confirmed_deadlines(self) -> None:
        value = noted_request("Ready tomorrow at 14:00.")
        original = copy.deepcopy(value)
        desk = self.desk(value)
        captured = []

        def record_slack(_self, req, option):
            captured.append((copy.deepcopy(req), copy.deepcopy(option)))
            return 777

        with patch.object(ReliabilityDesk, "_slack", record_slack):
            self.assertEqual(desk._slack(value, value["options"][0]), 777)
        transformed, option = captured[0]
        self.assertIsNone(transformed["note"])
        self.assertEqual(transformed["legs"][0]["pickup"]["window"]["from"], 2280)
        self.assertEqual(option["deadline"], original["options"][0]["deadline"])
        self.assertEqual(value, original)

    def test_recurring_hours_and_unknown_or_ambiguous_notes_keep_baseline(self) -> None:
        texts = ["Pickup weekdays 9-14.", "Ready at 13:00. Please call Anna.",
                 "Ready at 13:00. Ready at 15:00.", "Maybe ready tomorrow at 14:00."]
        for text in texts:
            with self.subTest(note=text):
                value = noted_request(text)
                self.assertIsNone(supported_constraints(value)[0])
                baseline = self.desk(value, ReliabilityDesk)
                candidate = self.desk(value)
                self.assertEqual(candidate._slack(value, value["options"][0]),
                                 baseline._slack(value, value["options"][0]))
                order = won_order(value)
                baseline.post(copy.deepcopy(order), [0])
                candidate.post(copy.deepcopy(order), [0])
                self.assertEqual(candidate.outbox, baseline.outbox)

    def test_unscoped_trade_in_never_broadcasts_new_constraints(self) -> None:
        value = noted_request("Ready tomorrow at 14:00. No plates.")
        value["legs"].append(copy.deepcopy(value["legs"][0]))
        self.assertEqual(supported_constraints(value)[1], "unscoped")
        candidate, baseline = self.desk(value), self.desk(value, ReliabilityDesk)
        self.assertEqual(candidate._slack(value, value["options"][0]),
                         baseline._slack(value, value["options"][0]))

    def test_impossible_private_ready_time_never_widens_seller_slot(self) -> None:
        value = noted_request("Ready at 15:00.")
        value["legs"][0]["pickup"]["privateAddress"] = True
        value["legs"][0]["pickup"]["window"] = {"from": 600, "to": 840}
        candidate = self.desk(value)
        self.assertEqual(candidate._slack(value, value["options"][0]), -10000)
        candidate.post(won_order(value), [0])
        self.assertEqual(candidate.outbox, [])
        self.assertEqual(candidate.note_counts["unrepresentable_private_bound"], 1)

    def test_eligibility_counts_are_distinct_from_action_change_counts(self) -> None:
        value = noted_request("Manual gearbox.")
        candidate = self.desk(value)
        candidate.quote(value)
        candidate.quote(value)
        self.assertEqual(candidate.notes_summary()["unique_requests"], 1)
        self.assertEqual(candidate.notes_summary()["eligible_requests"], 1)
        self.assertEqual(candidate.notes_summary()["orders_with_added_post_constraints"], 0)
        candidate.post(won_order(value), [0])
        self.assertEqual(candidate.notes_summary()["orders_with_added_post_constraints"], 1)
        # Baseline already understands this simple manual requirement.
        self.assertEqual(candidate.notes_summary()["orders_with_changed_post_actions"], 0)

    def test_sdk_global_desk_is_unchanged_and_policy_mixtures_are_rejected(self) -> None:
        original = starter.Desk
        NotesDesk(FakeWorld(), 8, 480)
        self.assertIs(starter.Desk, original)
        with self.assertRaises(ValueError):
            NotesDesk(FakeWorld(), 8, 480, mode="learned")
        with self.assertRaises(ValueError):
            NotesDesk(FakeWorld(), 8, 480, model_path="unused-model.json")
        with patch.dict(os.environ, {"SPREAD_RELIABILITY_MODEL": "unused-model.json"}):
            with self.assertRaises(ValueError):
                NotesDesk(FakeWorld(), 8, 480)


if __name__ == "__main__":
    unittest.main()
