"""Consequential note-boundary fixtures; no synthetic accuracy claim."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from evaluate_notes import compare_field, evaluate
from typed_notes import note_adjusted_request, parse_notes


def request(text, day=0):
    return {"id": "R1", "arrivedAt": day * 1440 + 480,
            "note": {"text": text, "language": "fi"},
            "legs": [{"pickup": {"window": {"from": day * 1440 + 480, "to": (day + 5) * 1440},
                                    "privateAddress": False,
                                    "hours": {"opens": 480, "closes": 1200, "weekdays": [0, 1, 2, 3, 4], "saturday": None}},
                      "delivery": {"window": {"from": day * 1440 + 480, "to": (day + 5) * 1440},
                                     "privateAddress": False,
                                     "hours": {"opens": 480, "closes": 1200, "weekdays": [0, 1, 2, 3, 4], "saturday": None}}}],
            "options": [{"kind": "next_day", "deadline": (day + 1) * 1440 + 1200}]}


class NoteBoundaryTests(unittest.TestCase):
    def test_relative_day_uses_request_arrival(self):
        self.assertEqual(parse_notes(request("Auto valmis huomenna klo 13.30", 2)).readyAt, 3 * 1440 + 810)

    def test_day_after_tomorrow_not_counted_as_tomorrow(self):
        self.assertEqual(parse_notes(request("Ready the day after tomorrow at 14:00")).readyAt, 2 * 1440 + 840)

    def test_swedish_named_weekday(self):
        self.assertEqual(parse_notes(request("Klar först på onsdag kl 12")).readyAt, 2 * 1440 + 720)

    def test_payment_not_before_is_lower_bound(self):
        self.assertEqual(parse_notes(request("Maksun jälkeen, ei ennen klo 13.30")).releaseAt, 810)

    def test_tighter_delivery_deadline(self):
        self.assertEqual(parse_notes(request("Must be at destination by tomorrow 17:00")).noteDeadline, 1440 + 1020)

    def test_correction_drops_old_clock(self):
        self.assertEqual(parse_notes(request("Ready tomorrow at 15:00, correction: 16:00")).readyAt, 1440 + 960)

    def test_denied_clock_is_not_a_bound(self):
        self.assertEqual(parse_notes(request("Ready not at 3pm, at 4pm")).readyAt, 960)

    def test_half_three_is_half_before_three(self):
        self.assertEqual(parse_notes(request("Ready tomorrow at half three")).readyAt, 1440 + 870)

    def test_hours_remain_structured(self):
        parsed = parse_notes(request("Nouto arkisin ennen klo 14"))
        self.assertEqual(parsed.pickupHours, {"closes": 840, "weekdays": [0, 1, 2, 3, 4]})
        self.assertIsNone(parsed.pickupBefore)

    def test_receiving_hours_are_not_order_deadline(self):
        parsed = parse_notes(request("Vastaanotto klo 16 asti"))
        self.assertEqual(parsed.deliveryHours, {"closes": 960})
        self.assertIsNone(parsed.noteDeadline)

    def test_multiple_facts_separate_clauses(self):
        parsed = parse_notes(request("Manuaalivaihteisto; car has no plates; auto vielä kesärenkailla"))
        self.assertTrue(parsed.manualRequired)
        self.assertTrue(parsed.platesRequired)
        self.assertTrue(parsed.summerTyres)

    def test_absent_and_denied_are_distinct(self):
        self.assertIsNone(parse_notes(request("Thank you!")).manualRequired)
        self.assertFalse(parse_notes(request("Not manual")).manualRequired)

    def test_conflicting_times_abstain(self):
        parsed = parse_notes(request("Ready at 13:00 or 16:00"))
        self.assertIsNone(parsed.readyAt)
        self.assertTrue(parsed.ambiguous)

    def test_multiple_legs_require_scope(self):
        req = request("Ready tomorrow at 14:00")
        req["legs"].append(copy.deepcopy(req["legs"][0]))
        parsed = parse_notes(req)
        self.assertEqual(parsed.scope, "unscoped_multi_leg")
        self.assertIsNone(parsed.readyAt)
        self.assertEqual(note_adjusted_request(req), req)

    def test_adjustment_does_not_mutate_original(self):
        req = request("Ready tomorrow at 14:00")
        before = copy.deepcopy(req)
        changed = note_adjusted_request(req)
        self.assertEqual(req, before)
        self.assertEqual(changed["legs"][0]["pickup"]["window"]["from"], 1440 + 840)

    def test_impossible_window_raises(self):
        req = request("Ready tomorrow at 14:00")
        req["legs"][0]["pickup"]["window"]["to"] = 1000
        with self.assertRaises(ValueError):
            note_adjusted_request(req)

    def test_bad_clock_does_not_become_fact(self):
        self.assertIsNone(parse_notes(request("Ready at 25:00")).readyAt)
        self.assertIsNone(parse_notes(request("Ready at 12:99")).readyAt)

    def test_clock_sentence_end_separates_stops(self):
        parsed = parse_notes(request("Noudettavissa arkisin klo 10-16.30. Oltava perillä viimeistään maanantaina klo 20!", 3))
        self.assertEqual(parsed.pickupHours, {"opens": 600, "closes": 990, "weekdays": [0, 1, 2, 3, 4]})
        self.assertEqual(parsed.noteDeadline, 7 * 1440 + 1200)
        self.assertIsNone(parsed.deliveryHours)

    def test_suffix_hours_separate_pickup_and_delivery(self):
        parsed = parse_notes(request("Pitää hakea ennen 15. Kohde auki 9:stä 21:een"))
        self.assertEqual(parsed.pickupHours, {"closes": 900})
        self.assertEqual(parsed.deliveryHours, {"opens": 540, "closes": 1260})

    def test_finnish_word_time_and_supported_typo(self):
        self.assertEqual(parse_notes(request("Huomenna neljalta valmis, ilmoita kun lahdet", 2)).readyAt, 3 * 1440 + 960)

    def test_finnish_correction_and_hours(self):
        parsed = parse_notes(request("Auto valmis vasta huomenna klo 10, eikun klo 9. Nouto arkisin 9-16", 2))
        self.assertEqual(parsed.readyAt, 3 * 1440 + 540)
        self.assertEqual(parsed.pickupHours, {"opens": 540, "closes": 960, "weekdays": [0, 1, 2, 3, 4]})

    def test_ready_now_is_arrival_time(self):
        req = request("Auto valmiina, haettavissa heti")
        req["arrivedAt"] = 623
        self.assertEqual(parse_notes(req).readyAt, 623)

    def test_date_specific_hours_are_not_daily_hours(self):
        parsed = parse_notes(request("Nouto huomenna klo 10-16"))
        self.assertIsNone(parsed.pickupHours)
        self.assertTrue(parsed.unknown)
        parsed = parse_notes(request("Vastaanotto huomenna klo 16 asti"))
        self.assertIsNone(parsed.deliveryHours)
        self.assertIsNone(parsed.noteDeadline)

    def test_negative_readiness_without_before_is_unknown(self):
        parsed = parse_notes(request("Not ready at 15:00"))
        self.assertIsNone(parsed.readyAt)
        self.assertTrue(parsed.unknown)

    def test_negated_readiness_before_is_supported(self):
        self.assertEqual(parse_notes(request("Not ready before tomorrow 13:00")).readyAt, 1440 + 780)

    def test_uncertain_readiness_is_unknown(self):
        for text in ["Maybe ready at 15:00", "Ehkä valmis klo 15", "Might be ready at 15:00"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_notes(request(text)).readyAt)

    def test_plate_absence_variants(self):
        for text in ["Kilvet poistettu, ota koekilvet", "Auto ilman kilpiä", "Unregistered, needs trade plates", "rekisterikilvet irrotettu", "Ei rekkareita, koekilvt tarvitaan"]:
            with self.subTest(text=text):
                self.assertTrue(parse_notes(request(text)).platesRequired)

    def test_trade_plate_negation(self):
        self.assertFalse(parse_notes(request("Does not need trade plates")).platesRequired)
        self.assertFalse(parse_notes(request("Trade plates are not required")).platesRequired)

    def test_tyres_in_boot_do_not_assert_driving_tyres(self):
        self.assertIsNone(parse_notes(request("Extra summer tyres in boot")).summerTyres)

    def test_conditional_requirement_is_unknown(self):
        self.assertIsNone(parse_notes(request("Call if no plates")).platesRequired)

    def test_day_abbreviation_does_not_split_sentence(self):
        self.assertEqual(parse_notes(request("Valmis to. klo 12")).readyAt, 3 * 1440 + 720)

    def test_dotless_finnish_weekdays_with_clock_marker(self):
        parsed = parse_notes(request("Noudettavissa aikaisintaan to klo 8. Perillä to klo 19 mennessä", 1))
        self.assertEqual(parsed.readyAt, 3 * 1440 + 480)
        self.assertEqual(parsed.noteDeadline, 3 * 1440 + 1140)
        self.assertEqual(parse_notes(request("Voi noutaa ke klo 14.30 alkaen")).readyAt, 2 * 1440 + 870)
        self.assertEqual(parse_notes(request("Perillä ma klo 20 mennessä", 2)).noteDeadline, 7 * 1440 + 1200)

    def test_english_to_is_not_a_finnish_weekday(self):
        parsed = parse_notes(request("Deliver to destination by 17:00"))
        self.assertEqual(parsed.noteDeadline, 1020)

    def test_swedish_short_weekday(self):
        self.assertEqual(parse_notes(request("Måste vara framme senast mån kl 12.30", 4)).noteDeadline, 7 * 1440 + 750)

    def test_observed_tomorrow_typo_does_not_fall_back_to_today(self):
        self.assertEqual(parse_notes(request("Oltava perillä viimeistään huomnna klo 19.00", 3)).noteDeadline, 4 * 1440 + 1140)

    def test_cargo_tyres_multilingual_and_observed_typos(self):
        for text in ["Lisäksi 4 kesärengasta tavaratilassa", "Liskäsi 4 kesärengasta tavaratilassa", "Lisäksi 4 kesärengasta tavaraatilassa", "lisäksi 4 kesärengasta tavaratilasssa", "Lisäksi 4 kesärengasta tavaraitlassa", "Sommardäcken i bakluckan, följer med", "sommardäcken i bakuckan, följer med"]:
            with self.subTest(text=text):
                parsed = parse_notes(request(text))
                self.assertIsNone(parsed.summerTyres)
                self.assertTrue(parsed.unknown)

    def test_buyer_pays_first_is_release_not_readiness(self):
        parsed = parse_notes(request("Buyer pays first, pickup from tomorrow 11:30", 3))
        self.assertEqual(parsed.releaseAt, 4 * 1440 + 690)
        self.assertIsNone(parsed.readyAt)

    def test_contact_filler_does_not_change_hours_scope(self):
        parsed = parse_notes(request("Mille auki arkisin 7–20, soita asiakkaalle tuntia ennen perillä oloa"))
        self.assertEqual(parsed.pickupHours, {"opens": 420, "closes": 1200, "weekdays": [0, 1, 2, 3, 4]})
        self.assertIsNone(parsed.deliveryHours)

    def test_contact_instruction_is_not_a_pickup_bound(self):
        self.assertIsNone(parse_notes(request("Call before pickup at 14:00")).pickupBefore)
        self.assertIsNone(parse_notes(request("Call before pickup at 14:00")).pickupHours)

    def test_short_latest_and_contact_filler_preserve_deadline(self):
        parsed = parse_notes(request("Toimitus perille viim. ma klo 15, soita asiakkaalle tuntia ennen perillä oloa", 3))
        self.assertEqual(parsed.noteDeadline, 7 * 1440 + 900)

    def test_observed_receiving_typo_preserves_hours_scope(self):
        parsed = parse_notes(request("Vastaaanottava liike auki 7-20"))
        self.assertEqual(parsed.deliveryHours, {"opens": 420, "closes": 1200})
        self.assertIsNone(parsed.pickupHours)

    def test_requirement_does_not_hide_unresolved_clock(self):
        for text, field in [("Manual gearbox, not before 16:00.", "manualRequired"),
                            ("Car has no plates, not before 16:00.", "platesRequired"),
                            ("Summer tyres, until 16:00.", "summerTyres")]:
            with self.subTest(text=text):
                parsed = parse_notes(request(text))
                self.assertTrue(getattr(parsed, field))
                self.assertIsNone(parsed.readyAt)
                self.assertNotIn("readyAt", parsed.evidence)
                self.assertTrue(any(reason.startswith("unparsed_temporal_constraint:") for reason in parsed.unknown))

    def test_requirement_does_not_hide_unresolved_temporal_forms(self):
        for text in ["Manual gearbox, ready before tomorrow.", "Manual gearbox, 14:00-16:00.",
                     "Manual gearbox, ready at 25:00.", "Manual gearbox, pickup at noon."]:
            with self.subTest(text=text):
                parsed = parse_notes(request(text))
                self.assertTrue(parsed.manualRequired)
                self.assertTrue(parsed.unknown)
                self.assertIsNone(parsed.readyAt)

    def test_supported_hours_do_not_hide_another_unresolved_clock(self):
        parsed = parse_notes(request("Manual gearbox, pickup hours 9-16, appointment at 17:00"))
        self.assertEqual(parsed.pickupHours, {"opens": 540, "closes": 960})
        self.assertTrue(parsed.unknown)
        self.assertIsNone(parsed.readyAt)

    def test_supported_clock_does_not_hide_invalid_hours(self):
        parsed = parse_notes(request("Manual gearbox, ready at 13:00, pickup hours 20-9"))
        self.assertEqual(parsed.readyAt, 780)
        self.assertIsNone(parsed.pickupHours)
        self.assertTrue(parsed.unknown)

    def test_supported_requirement_and_clock_remain_complete(self):
        parsed = parse_notes(request("Manual gearbox, ready after 16:00"))
        self.assertTrue(parsed.manualRequired)
        self.assertEqual(parsed.readyAt, 960)
        self.assertFalse(parsed.unknown)
        self.assertFalse(parsed.ambiguous)

    def test_discarded_contact_tail_does_not_hide_timing(self):
        parsed = parse_notes(request("Manual gearbox, call before 16:00"))
        self.assertTrue(parsed.manualRequired)
        self.assertTrue(parsed.unknown)
        self.assertIsNone(parsed.readyAt)


class NoteEvaluationTests(unittest.TestCase):
    def test_nonbinding_note_deadline_is_separate(self):
        self.assertEqual(compare_field("noteDeadline", 3000, {"noteDeadline": None}, request(""), {"deadline": 2500}), "nonbinding")
        self.assertEqual(compare_field("noteDeadline", 2000, {"noteDeadline": None}, request(""), {"deadline": 2500}), "false_assertion")

    def test_partial_hours_compare_only_asserted_components(self):
        truth = {"pickupHours": {"opens": 480, "closes": 840, "weekdays": [0, 1, 2, 3, 4], "saturday": None}}
        self.assertEqual(compare_field("pickupHours", {"closes": 840}, truth, request(""), {}), "correct")
        self.assertEqual(compare_field("pickupHours", {"closes": 900}, truth, request(""), {}), "false_assertion")

    def test_ready_before_public_window_is_nonbinding(self):
        self.assertEqual(compare_field("readyAt", 400, {"readyAt": 480}, request(""), {}), "correct")

    def test_unknown_is_not_correct(self):
        self.assertEqual(compare_field("manualRequired", None, {"manualGearbox": False}, request(""), {}), "unknown")

    def test_bundle_evaluation_keeps_provenance_and_unknowns(self):
        req = request("Car has no plates")
        bundle = {"world_id": "test-world", "snapshot": {"orders": [{"id": "R1", "deadline": 2640}]},
                  "reveal": {"requests": [{"request": req}], "orders": [{"orderId": "R1", "legs": [{"needsPlates": True, "manualGearbox": False}]}]}}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bundle.json.gz"
            source.write_bytes(gzip.compress(json.dumps(bundle).encode()))
            result = evaluate([source])
        self.assertEqual(result["fields"]["platesRequired"]["correct"], 1)
        self.assertEqual(result["fields"]["manualRequired"]["unknown"], 1)
        self.assertIsNone(result["fields"]["manualRequired"]["assertion_precision"])
        self.assertEqual(result["sources"][0]["world_id"], "test-world")
        self.assertEqual(len(result["sources"][0]["bundle_sha256"]), 64)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bundle.json.gz"
            source.write_bytes(gzip.compress(json.dumps(bundle).encode()))
            with self.assertRaisesRegex(ValueError, "Duplicate world_id"):
                evaluate([source, source])


if __name__ == "__main__":
    unittest.main()
