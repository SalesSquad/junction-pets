"""Stress set v1: the code gate. No network.

A written note passes when
  1. every date string of the specification (facts and distractors) appears verbatim (version 1's pattern:
     not inside a longer word, case-sensitive);
  2. after masking those strings, no other date or time reference is left (phrases.UNDECLARED_RE);
  3. the word count is inside the curriculum's bounds;
  4. every fact's string resolves to the answer key:
       standard absolute forms   the frozen resolver's written_dates()            (scribe/v3/resolve.py, frozen)
       standard days/weeks       the frozen resolver's relative_spans(arm "A")    (scribe/v3/resolve.py, frozen)
       held-out phrasings        the generator's own arithmetic (phrases.heldout_days)
       vague phrases             present verbatim; their answer is "send to a person", never a date.
The frozen hashes in data/scribe/v4/resolver/freeze.json are checked before the resolver is used.
SYNTHETIC notes only. A person confirms every extracted event.
"""

import datetime as dt
import functools
import hashlib
import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import phrases as P  # noqa: E402

FREEZE = ROOT / "data/scribe/v4/resolver/freeze.json"
ABSOLUTE = ("numeric", "long", "no_year", "month")
RELATIVE = ("days", "weeks")


@functools.lru_cache(maxsize=1)
def resolver():
    """(module, freeze record, sha256 of freeze.json). Refuses to run when the frozen files changed."""
    spec = importlib.util.spec_from_file_location("scribe_v3_resolve_frozen", ROOT / "scribe/v3/resolve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rec = mod.check_frozen()  # SystemExit if scribe/v3/resolve.py or lexicon.py differ from the freeze
    return mod, rec, hashlib.sha256(FREEZE.read_bytes()).hexdigest()


def date_pattern(expression):
    return r"(?<!\w)" + re.escape(expression) + r"(?!\w)"


def family_of(x):
    return x.get("family") or x.get("form") or "numeric"


def resolve_check(spec, note_text):
    """One record per fact and distractor: present?, the date its string resolves to, ok?, and how."""
    R = resolver()[0]
    note = dt.date.fromisoformat(spec["note_date"])
    written = R.written_dates(note_text, note)
    spans_a = R.relative_spans(note_text, note, "A")
    spans_a2 = R.relative_spans(note_text, note, "A'")
    person_a2 = R.needs_person_spans(note_text, "A'")
    out = []
    for role, items in (("fact", spec["facts"]), ("distractor", spec["distractors"])):
        for x in items:
            fam, expr = family_of(x), x["expression"]
            present = bool(re.search(date_pattern(expr), note_text))
            if fam in ABSOLUTE:
                method = "frozen resolver written_dates"
                resolved = x["date"] if x["date"] in written else None
                ok = present and resolved is not None
            elif fam in RELATIVE:
                method = "frozen resolver relative_spans arm A"
                hits = [s["date"] for s in spans_a if s["phrase"] == expr]
                resolved = x["date"] if x["date"] in hits else (hits[0] if hits else None)
                ok = present and x["date"] in hits
            elif fam in P.HELDOUT_FAMILIES:
                method = "generator arithmetic (phrases.heldout_days)"
                resolved = (note - dt.timedelta(days=P.heldout_days(expr))).isoformat()
                ok = present and resolved == x["date"]
            elif fam == "vague":
                method = "declared vague phrase: send to a person"
                resolved = None
                ok = present and expr in P.VAGUE
            else:
                raise ValueError(f"unknown family {fam!r}")
            out.append(
                dict(
                    role=role,
                    expression=expr,
                    family=fam,
                    present=present,
                    key_date=x["date"],
                    resolved_date=resolved,
                    ok=ok,
                    method=method,
                    # information only, never used to accept a note: what the frozen arm A' rule does with the string
                    frozen_aprime_resolves=any(expr in s["phrase"] or s["phrase"] in expr for s in spans_a2 if s["source"] == "lexicon"),
                    frozen_aprime_to_person=any(s["phrase"] == expr or s["phrase"] in expr for s in person_a2),
                )
            )
    return out


def code_check(spec, note_text):
    note_text = note_text or ""
    items = spec["facts"] + spec["distractors"]
    counts = {x["expression"]: len(re.findall(date_pattern(x["expression"]), note_text)) for x in items}
    missing = [e for e, n in counts.items() if n == 0]
    masked = note_text
    for e in sorted(counts, key=len, reverse=True):
        masked = re.sub(date_pattern(e), " DATE ", masked)
    extra = P.undeclared(masked)
    words = len(note_text.split())
    lo, hi = spec["word_bounds"]
    resolution = resolve_check(spec, note_text)
    failures = [f"missing_date_string:{e}" for e in missing]
    failures += [f"undeclared_date:{e}" for e in extra]
    if not lo <= words <= hi:
        failures.append(f"words:{words} outside {lo}-{hi}")
    failures += [f"not_resolved_to_key:{r['expression']}" for r in resolution if r["present"] and not r["ok"]]
    return dict(passed=not failures, failures=failures, words=words, counts=counts, resolution=resolution)
