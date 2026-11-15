"""Date expressions are resolved in code, identically to the generator's own parser."""

import datetime
import json
import unittest

import support
import client
import prompts as v1_prompts
import sample


class ResolveExpression(unittest.TestCase):
    NOTE = "2024-10-24"

    def test_six_forms(self):
        cases = {
            "5.3.2024": ("2024-03-05", "DAY"),
            "05.03.2024": ("2024-03-05", "DAY"),
            "5.3.": ("2024-03-05", "DAY"),
            "5. maaliskuuta 2024": ("2024-03-05", "DAY"),
            "maaliskuussa 2024": ("2024-03-01", "MONTH"),
            "kesäkuussa 2023": ("2023-06-01", "MONTH"),
            "12 päivää sitten": ("2024-10-12", "DAY"),
            "41 viikkoa sitten": ("2024-01-11", "DAY"),
            " 3 viikkoa sitten ": ("2024-10-03", "DAY"),
        }
        for expression, expected in cases.items():
            self.assertEqual(client.resolve_expression(expression, self.NOTE), expected, expression)

    def test_missing_year_means_note_year(self):
        self.assertEqual(client.resolve_expression("31.12.", "2025-01-02"), ("2025-12-31", "DAY"))
        self.assertEqual(client.resolve_expression("29.2.", "2024-06-01"), ("2024-02-29", "DAY"))

    def test_relative_dates_cross_year_and_leap_day(self):
        self.assertEqual(client.resolve_expression("10 päivää sitten", "2025-01-05"), ("2024-12-26", "DAY"))
        self.assertEqual(client.resolve_expression("1 viikkoa sitten", "2024-03-06"), ("2024-02-28", "DAY"))
        self.assertEqual(client.resolve_expression("1 päivää sitten", "2024-03-01"), ("2024-02-29", "DAY"))

    def test_note_date_types(self):
        for note in ("2024-10-24", datetime.date(2024, 10, 24), datetime.datetime(2024, 10, 24, 9, 30)):
            self.assertEqual(client.resolve_expression("1 päivää sitten", note), ("2024-10-23", "DAY"))

    def test_impossible_or_unsupported_raises(self):
        for bad in ["31.2.2024", "29.2.2023", "31.4.", "0.3.2024", "5.13.2024", "0 päivää sitten",
                    "eilen", "viime viikolla", "3 kuukautta sitten", "2024-03-05", "5.3.24", "",
                    "Maaliskuussa 2024", "5. maaliskuu 2024", "12 päivää", "5.3.2024 ja 6.3.2024"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                client.resolve_expression(bad, self.NOTE)

    def test_equals_generator_parser_on_every_dataset_fact(self):
        checked = 0
        for row in support.targets():
            note = datetime.date.fromisoformat(row["note_date"])
            for fact in row["facts"]:
                date, precision = sample.parse_date(fact["expression"], note)
                self.assertEqual(
                    client.resolve_expression(fact["expression"], row["note_date"]),
                    (date.isoformat(), precision),
                    fact["expression"],
                )
                self.assertEqual((date.isoformat(), precision), (fact["date"], fact["precision"]))
                checked += 1
        self.assertEqual(checked, 11254)  # every fact of the 4456 rows

    def test_expression_answers_decode_to_the_absolute_target(self):
        schema = client.load_schema("expression")
        for row in support.targets():
            decoded = client.decode_output(
                support.compact(support.expression_json(row)), "expression", row["note_date"],
                v1_prompts.canonicalise, schema)
            self.assertEqual(decoded["errors"], [], row["id"])
            self.assertEqual(decoded["canonical"], json.loads(row["target_json"]), row["id"])

    def test_calendar_error_in_expression_goes_to_errors(self):
        schema = client.load_schema("expression")
        answer = '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","expression":"31.2.2024"}]}'
        self.assertEqual(client.validate(json.loads(answer), schema), [])  # the pattern cannot see the calendar
        decoded = client.decode_output(answer, "expression", "2024-06-01", v1_prompts.canonicalise, schema)
        self.assertIsNone(decoded["canonical"])
        self.assertTrue(decoded["errors"][0].startswith("unresolved_expression"))


class DecodeAbsolute(unittest.TestCase):
    def setUp(self):
        self.schema = client.load_schema("absolute")

    def decode(self, text, note="2024-06-01"):
        return client.decode_output(text, "absolute", note, v1_prompts.canonicalise, self.schema)

    def test_sorts_and_strips_fences(self):
        text = '```json\n{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","date":"2024-03-05","precision":"DAY"},{"type":"FIRST_CONTACT","date":"2024-01-01","precision":"MONTH"}]}\n```'
        decoded = self.decode(text)
        self.assertEqual(decoded["errors"], [])
        self.assertEqual([e["type"] for e in decoded["canonical"]["events"]], ["FIRST_CONTACT", "DIAGNOSIS"])
        self.assertEqual(decoded["canonical"], v1_prompts.parse_output(text))

    def test_calendar_and_month_precision_checked_after_the_pattern(self):
        for date, precision in [("2024-02-30", "DAY"), ("2023-02-29", "DAY"), ("2024-03-05", "MONTH")]:
            text = json.dumps({"entry_route": "PRIVATE", "events": [{"type": "DIAGNOSIS", "date": date, "precision": precision}]})
            self.assertEqual(client.validate(json.loads(text), self.schema), [])
            decoded = self.decode(text)
            self.assertIsNone(decoded["canonical"], date)
            self.assertTrue(decoded["errors"][0].startswith("not_canonical"), date)

    def test_flags(self):
        def one(date):
            return json.dumps({"entry_route": "PRIVATE", "events": [{"type": "DIAGNOSIS", "date": date, "precision": "DAY"}]})

        self.assertEqual(self.decode(one("2024-06-01"))["flags"], [])
        self.assertEqual(self.decode(one("2024-06-02"))["flags"], ["event_after_note_date"])
        self.assertEqual(self.decode(one("1967-12-05"))["flags"], ["event_older_than_lookback"])
        twice = json.dumps({"entry_route": "PRIVATE", "events": [{"type": "DIAGNOSIS", "date": "2024-03-05", "precision": "DAY"}] * 2})
        self.assertEqual(self.decode(twice)["flags"], ["duplicate_event"])

    def test_not_json_and_wrong_shape(self):
        self.assertTrue(self.decode("Potilaalla on")["errors"][0].startswith("not_json"))
        self.assertTrue(self.decode('{"entry_route":"PRIVATE"}')["errors"][0].startswith("schema"))
        self.assertTrue(self.decode('{"entry_route":"PRIVATE","events":[{"type":"X","date":"2024-01-01","precision":"DAY"}]}')["errors"][0].startswith("schema"))


if __name__ == "__main__":
    unittest.main()
