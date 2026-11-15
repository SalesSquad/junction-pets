"""Integration check against the real scribe/v2/data_tools.py (written by another step).

Skipped while that file does not exist. It fails loudly if the names or the meaning of the expression
format drift away from what the training and evaluation code expects.
"""

import json
import unittest

import fakes
import constrained
import data_iface
import formats
import train
from sample import sample

HAVE = (fakes.V2 / "data_tools.py").exists()


def sampled_rows(n=300, seed=4242):
    rows = []
    i = 0
    while len(rows) < n:
        i += 1
        try:
            row = sample(i, seed=seed)
        except ValueError:  # the version-1 sampler rejects a few index/seed pairs
            continue
        row["note_text"] = "Merkintä. " + " ".join(f"{f['meaning']} {f['expression']}." for f in row["facts"])
        rows.append(data_iface.normalise(row))
    return rows


@unittest.skipUnless(HAVE, "scribe/v2/data_tools.py does not exist yet")
class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = sampled_rows()
        cls.fmt = formats.get_format("expression")

    def test_every_role_is_provided(self):
        for role in ("load", "messages", "target", "resolve", "schema"):
            self.assertIsNotNone(data_iface.lookup(role, required=False), role)

    def test_targets_resolve_to_the_labels(self):
        self.assertEqual(formats.available("expression", self.rows), (True, ""))
        forms = {form for row in self.rows for form in row["date_forms"]}
        self.assertEqual(forms, {"numeric", "long", "no_year", "days", "weeks", "month"})

    def test_schema_compiles_and_contains_every_target(self):
        A = constrained.Automaton()
        root = constrained.compile_schema(A, self.fmt.schema())
        for row in self.rows:
            target = self.fmt.target(row)
            self.assertTrue(A.matches(root, target), target)
            self.assertEqual(target, json.dumps(json.loads(target), ensure_ascii=False, separators=(",", ":")))
        self.assertFalse(A.matches(root, self.rows[0]["target_json"]))  # the absolute text is another language

    def test_constrained_decoding_and_encoding_work_for_the_expression_format(self):
        tok = fakes.FakeTokenizer()
        eot = tok.convert_tokens_to_ids("<end_of_turn>")
        constraint, info = constrained.build_constraint(tok, self.fmt.schema(), [eot], tok.pad_token_id, "auto")
        self.assertEqual(info["backend"], "native-dfa")
        for row in self.rows[:40]:
            target = self.fmt.target(row)
            ids = tok(target)["input_ids"]
            constraint.start()
            for i, token in enumerate(ids):
                self.assertIn(token, constraint.step(0, ids[:i]))
            self.assertEqual(constraint.step(0, ids), [eot])
            enc = train.encode(row, tok, self.fmt, max_length=4096)
            supervised = [t for t in enc["labels"] if t != train.IGNORE]
            self.assertEqual(tok.decode(supervised), target + "<end_of_turn>")

    def test_wrong_expression_is_scored_as_wrong_not_as_unparsable(self):
        row = next(r for r in self.rows if "days" in r["date_forms"])
        target = json.loads(self.fmt.target(row))
        for event in target["events"]:
            if event["date"]["kind"] == "DAYS_AGO":
                event["date"]["n"] += 1
        prediction, mode, _ = formats.interpret(self.fmt, json.dumps(target), row)
        self.assertEqual(mode, "strict")
        self.assertIsNotNone(prediction)
        self.assertNotEqual(prediction, json.loads(row["target_json"]))
        self.assertEqual(formats.interpret(self.fmt, row["target_json"], row)[:2], (None, "failed"))


if __name__ == "__main__":
    unittest.main()
