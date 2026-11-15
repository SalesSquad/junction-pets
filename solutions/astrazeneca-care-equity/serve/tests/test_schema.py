"""serve/schema.json: enums, acceptance of every dataset target, rejection of malformed output."""

import copy
import json
import unittest

import support  # noqa: F401  (sets sys.path)
import client
import prompts as v1_prompts
import sample


def xgrammar_unsupported(schema):
    """Port of has_xgrammar_unsupported_json_features from vLLM v0.29.0
    (vllm/v1/structured_output/backend_xgrammar.py), which rejects a request
    before the grammar is compiled."""
    supported_formats = {
        "email", "date", "time", "date-time", "duration", "ipv4", "ipv6", "hostname", "uuid",
        "uri", "uri-reference", "uri-template", "json-pointer", "relative-json-pointer",
    }

    def check(obj):
        if not isinstance(obj, dict):
            return False
        if obj.get("type") in ("integer", "number") and "multipleOf" in obj:
            return True
        if obj.get("type") == "array" and any(
            k in obj for k in ("uniqueItems", "contains", "minContains", "maxContains")
        ):
            return True
        if obj.get("type") == "string" and "format" in obj and obj["format"] not in supported_formats:
            return True
        if (
            obj.get("type") == "string"
            and ("pattern" in obj or "format" in obj)
            and ("minLength" in obj or "maxLength" in obj)
        ):
            return True
        if obj.get("type") == "object" and any(k in obj for k in ("patternProperties", "propertyNames")):
            return True
        for value in obj.values():
            if isinstance(value, dict) and check(value):
                return True
            if isinstance(value, list) and any(isinstance(i, dict) and check(i) for i in value):
                return True
        return False

    return check(schema)


class SchemaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(client.SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.absolute = client.load_schema("absolute")
        cls.expression = client.load_schema("expression")
        cls.targets = support.targets()

    def test_enums_equal_training_code(self):
        for schema in (self.absolute, self.expression):
            self.assertEqual(schema["properties"]["entry_route"]["enum"], list(sample.ROUTES))
            self.assertEqual(schema["properties"]["events"]["items"]["properties"]["type"]["enum"], sample.TYPES)
        self.assertEqual(list(client.MONTHS), sample.MONTHS)
        pattern = self.expression["properties"]["events"]["items"]["properties"]["expression"]["pattern"]
        self.assertEqual(pattern.count("|".join(sample.MONTHS)), 2)

    def test_enums_equal_event_log_contract(self):
        contract = support.eventlog_contract()
        self.assertEqual(set(sample.TYPES), set(contract["EVENT_TYPES"]))
        self.assertEqual(list(sample.ROUTES), contract["ENTRY_ROUTES"])
        self.assertEqual(
            self.absolute["properties"]["events"]["items"]["properties"]["precision"]["enum"],
            contract["DATE_PRECISIONS"],
        )

    def test_key_order_equals_training_targets(self):
        first = json.loads(self.targets[0]["target_json"])
        self.assertEqual(list(self.absolute["properties"]), list(first))
        self.assertEqual(list(self.absolute["properties"]["events"]["items"]["properties"]), list(first["events"][0]))
        self.assertEqual(self.absolute["required"], list(first))

    def test_no_keyword_rejected_by_vllm_xgrammar_check(self):
        self.assertFalse(xgrammar_unsupported(self.absolute))
        self.assertFalse(xgrammar_unsupported(self.expression))
        bad = copy.deepcopy(self.absolute)
        bad["properties"]["events"]["items"]["properties"]["date"]["maxLength"] = 10
        self.assertTrue(xgrammar_unsupported(bad))

    def test_every_dataset_target_is_valid_absolute(self):
        self.assertEqual(len(self.targets), 4456)
        for row in self.targets:
            target = json.loads(row["target_json"])
            self.assertEqual(client.validate(target, self.absolute), [], row["id"])
            self.assertEqual(client.validate(target, self.document), [], row["id"])
            self.assertEqual(v1_prompts.canonicalise(target), target)
            # The exact training string is compact JSON in schema key order.
            self.assertEqual(support.compact(target), row["target_json"])

    def test_every_dataset_target_is_valid_expression(self):
        events = 0
        for row in self.targets:
            answer = support.expression_json(row)
            events += len(answer["events"])
            self.assertEqual(client.validate(answer, self.expression), [], row["id"])
            self.assertEqual(client.validate(answer, self.document), [], row["id"])
            self.assertNotEqual(client.validate(answer, self.absolute), [])
        self.assertEqual(events, sum(len(json.loads(r["target_json"])["events"]) for r in self.targets))

    def test_malformed_absolute_is_rejected(self):
        self.assertEqual(client.validate(support.GOOD_ABSOLUTE, self.absolute), [])
        cases = support.malformed_absolute()
        self.assertEqual(len(cases), 23)
        for name, bad in cases.items():
            self.assertNotEqual(client.validate(bad, self.absolute), [], name)

    def test_malformed_expression_is_rejected(self):
        for good in support.GOOD_EXPRESSIONS:
            self.assertEqual(client.validate(support.expression_answer(good), self.expression), [], good)
        for bad in support.BAD_EXPRESSIONS:
            self.assertNotEqual(client.validate(support.expression_answer(bad), self.expression), [], repr(bad))
        with_precision = support.expression_answer("5.3.")
        with_precision["events"][0]["precision"] = "DAY"
        self.assertNotEqual(client.validate(with_precision, self.expression), [])

    def test_validator_refuses_unknown_keywords(self):
        with self.assertRaises(client.ScribeError):
            client.validate([], {"type": "array", "uniqueItems": True})
        with self.assertRaises(client.ScribeError):
            client.validate({}, {"type": "object", "patternProperties": {}})

    def test_validator_length_and_all_of(self):
        schema = {"allOf": [{"type": "string", "minLength": 2}, {"maxLength": 4}], "format": "date"}
        self.assertEqual(client.validate("abc", schema), [])
        self.assertNotEqual(client.validate("a", schema), [])
        self.assertNotEqual(client.validate("abcde", schema), [])

    def test_patterns_are_portable(self):
        """No lookaround, backreference, non-capturing group or class shorthand: the
        same pattern text must mean the same in Python re and in Rust-style engines."""
        for schema, key in ((self.absolute, "date"), (self.expression, "expression")):
            pattern = schema["properties"]["events"]["items"]["properties"][key]["pattern"]
            for token in ("(?", "\\d", "\\w", "\\s", "\\b", "\\1", "*", "+"):
                self.assertNotIn(token, pattern, (key, token))
            self.assertTrue(pattern.startswith("^") and pattern.endswith("$"))


if __name__ == "__main__":
    unittest.main()
