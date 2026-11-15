"""Output formats of the scribe: what the model is asked for, what it must emit, how that is scored.

"absolute"   the version-1 format: canonical JSON with absolute ISO dates (the model resolves
             "3 viikkoa sitten" against the note date itself).
"expression" the model copies each date as an expression and code resolves it against the note date.
             Prompt, target text, resolution and schema all come from scribe/v2/data_tools.py through
             data_iface; scoring always happens on the resolved absolute form.

Standard library only (plus the version-1 prompts module).
"""

from __future__ import annotations

import json
import re

import _paths  # noqa: F401
import data_iface
from prompts import canonicalise, messages as v1_messages
from sample import ROUTES, TYPES

PARSE_ERRORS = (ValueError, KeyError, TypeError, AttributeError, IndexError)

# Syntax only: enumerations, key order and the shape of a date. Calendar validity (31 February,
# month precision on a day other than the first) is checked afterwards by canonicalise().
ABSOLUTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entry_route", "events"],
    "properties": {
        "entry_route": {"enum": list(ROUTES)},
        "events": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "date", "precision"],
                "properties": {
                    "type": {"enum": list(TYPES)},
                    "date": {
                        "type": "string",
                        "pattern": "^(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$",
                    },
                    "precision": {"enum": ["DAY", "MONTH"]},
                },
            },
        },
    },
}


def tolerant_json(text):
    """Parse model output into a JSON value: (value, mode).

    mode is "strict" when the whole output (code fences removed) is JSON, and "tolerant" when the first
    complete JSON object had to be cut out of surrounding text. Raises ValueError when there is none.
    """
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()).strip()
    try:
        return json.loads(s), "strict"
    except ValueError:
        pass
    start = s.find("{")
    if start < 0:
        raise ValueError("no JSON object in output")
    value, _ = json.JSONDecoder().raw_decode(s[start:])
    return value, "tolerant"


class AbsoluteFormat:
    name = "absolute"

    def messages(self, row):
        return v1_messages(row)

    def target(self, row):
        return row["target_json"]

    def schema(self):
        return ABSOLUTE_SCHEMA

    def to_absolute(self, value, row):
        return canonicalise(value)


class ExpressionFormat:
    name = "expression"

    def messages(self, row):
        return data_iface.lookup("messages")(row)

    def target(self, row):
        target = data_iface.lookup("target")(row)
        return target if isinstance(target, str) else json.dumps(target, ensure_ascii=False, separators=(",", ":"))

    def schema(self):
        schema = data_iface.lookup("schema", required=False)
        return schema() if callable(schema) else schema

    def to_absolute(self, value, row):
        return canonicalise(data_iface.lookup("resolve")(value, row["note_date"]))


_FORMATS = {"absolute": AbsoluteFormat, "expression": ExpressionFormat}


def get_format(name):
    if name not in _FORMATS:
        raise ValueError(f"unknown output format {name!r}")
    return _FORMATS[name]()


def available(name, rows=None):
    """Whether a format can be used right now, and if not, why: (bool, reason).

    With rows, every row must survive the round trip target text -> parse -> absolute form and come
    back as its own label. That catches a data_tools function with another signature or meaning
    before any GPU time is spent on the format.
    """
    if name == "absolute":
        return True, ""
    try:
        for role in ("messages", "target", "resolve"):
            data_iface.lookup(role)
    except data_iface.DataToolsMissing as e:
        return False, str(e)
    fmt, failures, first = get_format(name), 0, ""
    for row in rows or []:
        try:
            fmt.messages(row)
            prediction, _, error = interpret(fmt, fmt.target(row), row)
            ok = prediction == json.loads(row["target_json"])
            error = error or "resolved target differs from the label"
        except Exception as e:  # any failure inside data_tools counts as "not usable"
            ok, error = False, f"{type(e).__name__}: {e}"
        if not ok:
            failures += 1
            first = first or f"{row['id']}: {error}"
    if failures:
        return False, f"round trip failed on {failures} of {len(rows)} rows (first: {first})"
    return True, ""


def interpret(fmt, text, row):
    """Model output -> (absolute canonical prediction or None, parse mode, error text)."""
    try:
        value, mode = tolerant_json(text)
        return fmt.to_absolute(value, row), mode, ""
    except PARSE_ERRORS as e:
        return None, "failed", f"{type(e).__name__}: {e}"
