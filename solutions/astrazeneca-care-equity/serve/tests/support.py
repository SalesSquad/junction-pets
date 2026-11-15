"""Shared paths and loaders for the serve tests (standard library only)."""

import ast
import gzip
import json
import pathlib
import sys

TESTS = pathlib.Path(__file__).resolve().parent
SERVE = TESTS.parent
ROOT = SERVE.parent
SCRIBE = ROOT / "scribe"
for extra in (str(SERVE), str(SCRIBE), str(TESTS)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

HELDOUT = SERVE / "fixtures" / "heldout-v1.jsonl"
TARGETS = TESTS / "fixtures" / "targets-v1.jsonl.gz"
EXPRESSION_PROMPTS = TESTS / "fixtures" / "prompts_expression.py"


def heldout():
    return [json.loads(line) for line in HELDOUT.read_text(encoding="utf-8").splitlines() if line.strip()]


def targets():
    with gzip.open(TARGETS, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def expression_json(row):
    """The expression-format answer for one fixture row, in note order of the facts."""
    target = json.loads(row["target_json"])
    return {
        "entry_route": target["entry_route"],
        "events": [{"type": f["type"], "expression": f["expression"]} for f in row["facts"]],
    }


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def user_content(row):
    return f"Note date: {row['note_date']}\n{row['note_text']}"


def eventlog_contract():
    """EVENT_TYPES, ENTRY_ROUTES, SOURCES and the pathway_events column names, read
    from eventlog/schema.py with ast so that pyarrow is not needed."""
    tree = ast.parse((ROOT / "eventlog" / "schema.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("EVENT_TYPES", "ENTRY_ROUTES", "SOURCES", "DATE_PRECISIONS"):
                out[name] = ast.literal_eval(node.value)
            if name == "pathway_events":
                columns = []
                for sub in ast.walk(node.value):
                    if (
                        isinstance(sub, ast.Tuple)
                        and len(sub.elts) == 2
                        and isinstance(sub.elts[0], ast.Constant)
                        and isinstance(sub.elts[0].value, str)
                    ):
                        columns.append((sub.lineno, sub.col_offset, sub.elts[0].value))
                out["columns"] = [name for _, _, name in sorted(columns)]
    return out


GOOD_ABSOLUTE = {"entry_route": "PRIVATE", "events": [{"type": "DIAGNOSIS", "date": "2024-03-05", "precision": "DAY"}]}


def malformed_absolute():
    """Answers that must be rejected in the absolute format, by name."""
    import copy

    def mutate(fn):
        bad = copy.deepcopy(GOOD_ABSOLUTE)
        fn(bad)
        return bad

    return {
        "unknown route": mutate(lambda x: x.__setitem__("entry_route", "PUBLIC")),
        "route lower case": mutate(lambda x: x.__setitem__("entry_route", "private")),
        "missing events": {"entry_route": "PRIVATE"},
        "missing route": {"events": []},
        "extra top-level key": mutate(lambda x: x.__setitem__("note", "x")),
        "events not a list": mutate(lambda x: x.__setitem__("events", {})),
        "event not an object": mutate(lambda x: x.__setitem__("events", ["DIAGNOSIS"])),
        "unknown event type": mutate(lambda x: x["events"][0].__setitem__("type", "BIOPSY")),
        "missing precision": mutate(lambda x: x["events"][0].pop("precision")),
        "extra event key": mutate(lambda x: x["events"][0].__setitem__("confidence", 1)),
        "precision YEAR": mutate(lambda x: x["events"][0].__setitem__("precision", "YEAR")),
        "date not a string": mutate(lambda x: x["events"][0].__setitem__("date", 20240305)),
        "finnish date": mutate(lambda x: x["events"][0].__setitem__("date", "5.3.2024")),
        "month 13": mutate(lambda x: x["events"][0].__setitem__("date", "2024-13-01")),
        "day 00": mutate(lambda x: x["events"][0].__setitem__("date", "2024-03-00")),
        "day 32": mutate(lambda x: x["events"][0].__setitem__("date", "2024-03-32")),
        "no zero padding": mutate(lambda x: x["events"][0].__setitem__("date", "2024-3-5")),
        "datetime": mutate(lambda x: x["events"][0].__setitem__("date", "2024-03-05T00:00:00")),
        "trailing newline": mutate(lambda x: x["events"][0].__setitem__("date", "2024-03-05\n")),
        "year 1800": mutate(lambda x: x["events"][0].__setitem__("date", "1800-03-05")),
        "ten events": mutate(lambda x: x.__setitem__("events", x["events"] * 10)),
        "top-level list": [GOOD_ABSOLUTE],
        "expression event": {"entry_route": "PRIVATE", "events": [{"type": "DIAGNOSIS", "expression": "5.3.2024"}]},
    }


GOOD_EXPRESSIONS = ["5.3.2024", "05.03.2024", "5.3.", "5. maaliskuuta 2024", "maaliskuussa 2024",
                    "12 päivää sitten", "3 viikkoa sitten", "31.12.1999", "259 päivää sitten",
                    "kesäkuussa 2023", "1. heinäkuuta 2025"]
BAD_EXPRESSIONS = ["2024-03-05", "5.3", "5.13.2024", "32.1.2024", "0.1.2024", "5. maaliskuu 2024",
                   "Maaliskuussa 2024", "maaliskuussa", "0 päivää sitten", "12 paivaa sitten",
                   "3 kuukautta sitten", "eilen", "", " 5.3.2024", "5.3.2024 ", "5.3.2024\n",
                   "12 päivää sitten ja 5.3.2024", "5.3.24"]


def expression_answer(expression):
    return {"entry_route": "SCREENING", "events": [{"type": "REFERRAL_SENT", "expression": expression}]}
