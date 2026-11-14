import json
import random
import unittest

import fakes
import constrained as k
import formats
from prompts import canonicalise


class Engine(unittest.TestCase):
    def test_literals_alternatives_and_repetition(self):
        A = k.Automaton()
        node = A.seq(A.lit("ab"), A.alt(A.lit("c"), A.lit("de")), A.repeat(A.chars("x"), 1, 2))
        for text, ok in (("abcx", True), ("abdexx", True), ("abc", False), ("abcxxx", False), ("abdx", False), ("", False)):
            self.assertEqual(A.matches(node, text), ok, text)
        self.assertEqual(A.walk(node, "abq"), k.NULL)
        self.assertEqual(set(A.first_chars(A.walk(node, "ab"))), {"c", "d"})
        self.assertTrue(A.matches(A.star(A.lit("ab")), "ababab"))
        self.assertTrue(A.matches(A.star(A.lit("ab")), ""))

    def test_pattern_subset(self):
        A = k.Automaton()
        date = k.parse_pattern(A, r"^(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
        for text, ok in (("2025-03-04", True), ("1999-12-31", True), ("2025-13-01", False), ("2025-00-10", False), ("2025-3-4", False), ("2025-03-32", False), ("3025-01-01", False)):
            self.assertEqual(A.matches(date, text), ok, text)
        self.assertTrue(A.matches(k.parse_pattern(A, r"^\d+(?:\.\d{1,2})?$"), "12.5"))
        self.assertFalse(A.matches(k.parse_pattern(A, r"^\d+(?:\.\d{1,2})?$"), "12.555"))
        self.assertTrue(A.matches(k.parse_pattern(A, r"^[a-c]x*y?$"), "bxxx"))
        for bad in ("abc", r"^[^a]$", r"^a*?$", r"^(?=a)a$", r"^a{2$"):
            with self.assertRaises(k.Unsupported, msg=bad):
                k.parse_pattern(A, bad)

    def test_schema_subset(self):
        A = k.Automaton()
        schema = {
            "type": "object",
            "properties": {
                "a": {"enum": ["X", "Y"]},
                "n": {"type": "integer", "minimum": 0, "maximum": 99},
                "flag": {"type": "boolean"},
                "items": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"const": "k"}},
            },
            "required": ["a", "items"],
        }
        node = k.compile_schema(A, schema)
        for text, ok in (
            ('{"a":"X","n":7,"flag":true,"items":["k"]}', True),
            ('{"a":"Y","items":["k","k"]}', True),
            ('{"a":"Y","n":42,"items":["k"]}', True),
            ('{"a":"Z","items":["k"]}', False),
            ('{"a":"X","items":[]}', False),
            ('{"a":"X","items":["k","k","k"]}', False),
            ('{"items":["k"],"a":"X"}', False),  # key order is fixed
            ('{"a":"X","n":007,"items":["k"]}', False),
            ('{"a": "X","items":["k"]}', False),  # no whitespace
        ):
            self.assertEqual(A.matches(node, text), ok, text)
        for bad in ({"type": "number"}, {"allOf": [{}]}, {"type": "string", "pattern": "^a$", "maxLength": 3}, {"type": "string", "format": "email"}):
            with self.assertRaises(k.Unsupported):
                k.compile_schema(k.Automaton(), bad)

    def test_absolute_schema_is_the_canonical_text(self):
        A = k.Automaton()
        root = k.compile_schema(A, formats.ABSOLUTE_SCHEMA)
        good = fakes.note_row(1)["target_json"]
        empty = fakes.note_row(2, events=[])["target_json"]
        self.assertTrue(A.matches(root, good))
        self.assertTrue(A.matches(root, empty))
        self.assertFalse(A.matches(root, good.replace("SCREENING", "HOSPITAL")))
        self.assertFalse(A.matches(root, good.replace("2025-03-04", "4.3.2025")))
        self.assertFalse(A.matches(root, json.dumps(json.loads(good))))  # default separators add spaces
        self.assertFalse(A.matches(root, good[:-1]))


class Decoding(unittest.TestCase):
    def setUp(self):
        self.tok = fakes.FakeTokenizer()
        self.eot = self.tok.convert_tokens_to_ids("<end_of_turn>")
        self.c = k.NativeConstraint(self.tok, formats.ABSOLUTE_SCHEMA, [self.eot], self.tok.pad_token_id)

    def walk(self, rng, limit=600):
        self.c.start()
        ids = []
        while len(ids) < limit:
            allowed = self.c.step(0, ids)
            ids.append(rng.choice(allowed))
            if ids[-1] == self.eot:
                break
        return ids

    def test_any_allowed_path_is_canonical_json(self):
        rng = random.Random(7)
        for _ in range(200):
            ids = self.walk(rng)
            self.assertEqual(ids[-1], self.eot)
            text = self.tok.decode(ids[:-1])
            value = json.loads(text)
            self.assertEqual(text, json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            self.assertIn(value["entry_route"], formats.ROUTES)
            self.assertLessEqual(len(value["events"]), 8)
            for event in value["events"]:
                self.assertEqual(list(event), ["type", "date", "precision"])
                self.assertIn(event["type"], formats.TYPES)
            try:  # calendar validity is the post-check's job, not the grammar's
                canonicalise(value)
            except ValueError:
                pass

    def test_gold_tokenisation_is_always_allowed(self):
        for row in (fakes.note_row(1), fakes.note_row(2, events=[]), fakes.note_row(3, route="EMERGENCY")):
            ids = self.tok(row["target_json"])["input_ids"]
            self.c.start()
            for i, token in enumerate(ids):
                self.assertIn(token, self.c.step(0, ids[:i]))
            self.assertEqual(self.c.step(0, ids), [self.eot])  # complete: only the stop token remains

    def test_multi_character_tokens_and_specials(self):
        first = self.c.allowed(self.c.root)
        pieces = {self.tok.pieces[i] for i in first}
        self.assertEqual(pieces, {"{", '{"'})
        self.assertFalse(set(first) & set(self.tok.all_special_ids))

    def test_rows_are_tracked_independently_and_padded_after_stop(self):
        self.c.start()
        ids = self.tok(fakes.note_row(1)["target_json"])["input_ids"]
        self.assertEqual(self.c.step(0, ids + [self.eot]), [self.tok.pad_token_id])
        self.assertEqual(self.c.step(0, ids + [self.eot, self.tok.pad_token_id]), [self.tok.pad_token_id])
        self.assertIn(self.tok.ids['{"'], self.c.step(1, []))
        fn = self.c.prefix_fn(prompt_len=3)
        self.assertEqual(fn(2, [9, 9, 9] + ids), [self.eot])

    def test_backend_selection_is_recorded(self):
        constraint, info = k.build_constraint(self.tok, formats.ABSOLUTE_SCHEMA, [self.eot], 0, "auto")
        self.assertEqual((constraint.backend, info["backend"], info["requested"]), ("native-dfa", "native-dfa", "auto"))
        constraint, info = k.build_constraint(self.tok, formats.ABSOLUTE_SCHEMA, [self.eot], 0, "off")
        self.assertIsNone(constraint)
        self.assertEqual(info["backend"], "none")
        constraint, info = k.build_constraint(self.tok, None, [self.eot], 0, "auto")
        self.assertIsNone(constraint)
        self.assertIn("no JSON schema", info["detail"])
        constraint, info = k.build_constraint(self.tok, {"type": "number"}, [self.eot], 0, "native")
        self.assertIsNone(constraint)
        self.assertIn("tolerant parsing", info["detail"])
        self.assertIn("native-dfa", info["detail"])


if __name__ == "__main__":
    unittest.main()
