"""The schema under the grammar engine vLLM uses (xgrammar). Skipped when xgrammar is not installed.

The system interpreter does not have xgrammar. To run these:
    uv venv --python 3.12 serve/.venv && uv pip install --python serve/.venv/bin/python xgrammar
    serve/.venv/bin/python -m unittest discover -s serve/tests

vLLM v0.29.0 compiles a JSON schema with
    compiler.compile_json_schema(schema, any_whitespace=not disable_any_whitespace)
(vllm/v1/structured_output/backend_xgrammar.py). Grammar.from_json_schema with the
same any_whitespace argument builds the same grammar without a tokenizer, so these
tests say which strings constrained decoding can and cannot produce. They do not
run Gemma and say nothing about what the model prefers.
"""

import json
import unittest

import support
import client

try:
    import xgrammar
    from xgrammar.testing import _is_grammar_accept_string as accepts
except ImportError:  # pragma: no cover
    xgrammar = None


@unittest.skipIf(xgrammar is None, "xgrammar not installed in this interpreter")
class GrammarEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.absolute_schema = client.load_schema("absolute")
        cls.expression_schema = client.load_schema("expression")
        cls.absolute = xgrammar.Grammar.from_json_schema(
            json.dumps(cls.absolute_schema, ensure_ascii=False), any_whitespace=True)
        cls.expression = xgrammar.Grammar.from_json_schema(
            json.dumps(cls.expression_schema, ensure_ascii=False), any_whitespace=True)
        cls.targets = support.targets()

    def test_every_training_target_can_be_generated(self):
        for row in self.targets:
            self.assertTrue(accepts(self.absolute, row["target_json"]), row["id"])

    def test_every_expression_answer_can_be_generated(self):
        for row in self.targets:
            answer = support.compact(support.expression_json(row))
            self.assertTrue(accepts(self.expression, answer), row["id"])
            self.assertFalse(accepts(self.absolute, answer), row["id"])

    def test_malformed_answers_cannot_be_generated(self):
        self.assertTrue(accepts(self.absolute, support.compact(support.GOOD_ABSOLUTE)))
        for name, bad in support.malformed_absolute().items():
            self.assertFalse(accepts(self.absolute, support.compact(bad)), name)
        for good in support.GOOD_EXPRESSIONS:
            self.assertTrue(accepts(self.expression, support.compact(support.expression_answer(good))), good)
        for bad in support.BAD_EXPRESSIONS:
            self.assertFalse(accepts(self.expression, support.compact(support.expression_answer(bad))), repr(bad))

    def test_grammar_and_client_validator_agree_except_on_key_order(self):
        cases = dict(support.malformed_absolute(), valid=support.GOOD_ABSOLUTE,
                     empty={"entry_route": "PRIVATE", "events": []})
        for name, obj in cases.items():
            self.assertEqual(accepts(self.absolute, support.compact(obj)),
                             client.validate(obj, self.absolute_schema) == [], name)
        reordered = {"events": support.GOOD_ABSOLUTE["events"], "entry_route": "PRIVATE"}
        self.assertEqual(client.validate(reordered, self.absolute_schema), [])  # JSON has no key order
        self.assertFalse(accepts(self.absolute, support.compact(reordered)))  # the grammar fixes schema order

    def test_whitespace_modes(self):
        compact = self.targets[0]["target_json"]
        spaced = json.dumps(json.loads(compact), ensure_ascii=False)
        pretty = json.dumps(json.loads(compact), ensure_ascii=False, indent=2)
        for text in (compact, spaced, pretty):
            self.assertTrue(accepts(self.absolute, text))
        # What vLLM's disable_any_whitespace=true turns into. It does NOT mean compact JSON:
        # the grammar then demands ", " and ": " and rejects the training format.
        strict = xgrammar.Grammar.from_json_schema(
            json.dumps(self.absolute_schema, ensure_ascii=False), any_whitespace=False)
        self.assertFalse(accepts(strict, compact))
        self.assertTrue(accepts(strict, spaced))
        entrypoint = (support.SERVE / "entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("""DEFAULT_STRUCTURED_OUTPUTS_CONFIG='{"backend": "xgrammar"}'""", entrypoint)

    def test_non_ascii_must_be_raw_utf8(self):
        answer = support.expression_answer("12 päivää sitten")
        self.assertTrue(accepts(self.expression, support.compact(answer)))
        escaped = json.dumps(answer, separators=(",", ":"))  # ä escapes
        self.assertIn("\\u00e4", escaped)
        self.assertFalse(accepts(self.expression, escaped))
        self.assertEqual(client.validate(json.loads(escaped), self.expression_schema), [])


if __name__ == "__main__":
    unittest.main()
