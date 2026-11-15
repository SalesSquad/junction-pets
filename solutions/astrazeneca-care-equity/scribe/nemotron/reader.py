"""Step 4: Nemotron 3.5 Super VL as the cascade's escalation reader, with a measured prompt ladder.

SYNTHETIC notes only. Not for clinical use: every extracted event is pre-filled for one-click
confirmation or flagged as needing editing; a person confirms every event either way.

Versions (each adds exactly one change to the one before it, so each step can be credited):
  v0   absolute format: Nemotron writes calendar dates itself (resolves "N päivää sitten" in its head).
  v1   expression format: Nemotron copies each date the way the note prints it ("12 päivää sitten" ->
       {"kind":"DAYS_AGO","n":12}); scribe/v2/data_tools.resolve_expression does the arithmetic.
  v2   v1 + local validation (JSON, resolve_expression, serve/schema.json $defs/absolute through
       serve/client.validate, no event after the note date, no duplicate event) and one repair retry
       that names the exact problems.
  v2g  v2 + a grounding check in the same validator: every date the model returns must correspond to a
       date string that is printed in the note (code, no model). Same single repair retry.
  v3   v2g with enable_thinking on (initial call and repair).
  v1rep  v1 run a second time, unchanged: measures how much answers move between identical runs at
       temperature 0 (batched serving is not bit-deterministic). Not a candidate for selection.

Selection rule, fixed before the validation run: the version with the highest validation exact match;
on an exact tie, the one with fewer mean calls per note (thinking counts as the more expensive). The
selected version then reads the 700 test notes once.

    set -a; . ~/.config/verda-inference/env; set +a
    scribe/.venv/bin/python scribe/nemotron/reader.py run --split val --versions v0,v1,v2,v2g,v3
    scribe/.venv/bin/python scribe/nemotron/reader.py run --split test --versions v2g
    scribe/.venv/bin/python scribe/nemotron/reader.py report
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import importlib.util
import json
import re
import sys
import time

import common as C
import data_tools
from prompts import canonicalise
from sample import ROUTES, TYPES

# teacher2's event-type definitions, imported read-only (the round-2 read-back used them)
sys.path.insert(0, str(C.ROOT / "scribe" / "teacher2"))
from protocol import DEFINITIONS  # noqa: E402

# serve/client.py's JSON-Schema validator and serve/schema.json, imported read-only
_spec = importlib.util.spec_from_file_location("sama_serve_client", C.ROOT / "serve" / "client.py")
serve_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve_client)
ABSOLUTE_SCHEMA = serve_client.load_schema("absolute")

VERSIONS = ("v0", "v1", "v1rep", "v2", "v2g", "v3")
CONFIG = {
    "v0": dict(fmt="absolute", validate=False, ground=False, thinking=False),
    "v1": dict(fmt="expression", validate=False, ground=False, thinking=False),
    # a replicate of v1 (same prompt, same settings): the run-to-run noise floor at temperature 0
    "v1rep": dict(fmt="expression", validate=False, ground=False, thinking=False),
    "v2": dict(fmt="expression", validate=True, ground=False, thinking=False),
    "v2g": dict(fmt="expression", validate=True, ground=True, thinking=False),
    "v3": dict(fmt="expression", validate=True, ground=True, thinking=True),
}
SPLITS = {"val": ("val",), "test": ("test_nemotron", "test_haiku")}
DATASET = C.ROOT / "data/scribe/v2/dataset"
CACHE = C.OUT / "cache"
MAX_TOKENS = 700
MAX_TOKENS_THINKING = 8000

# ---- prompts ------------------------------------------------------------------------------------

_INTRO = (
    "You read one SYNTHETIC Finnish clinical-style note and list the completed, dated cancer-pathway events it states. "
    "You see only the note and its note date.\n"
)
_FORMAT = {
    "absolute": (
        'Return only compact JSON: {"entry_route":"...","events":[{"type":"...","date":"YYYY-MM-DD","precision":"DAY|MONTH"}]}\n'
        "Give every date as a calendar date. Resolve relative dates against the note date yourself: "
        '"N päivää sitten" is N days before the note date and "N viikkoa sitten" is N weeks before the note date. '
        "A date without a year lies in the year of the note date. When the note gives only a month and a year, "
        "use the first day of that month with precision MONTH; every other date has precision DAY.\n"
    ),
    "expression": (
        'Return only compact JSON: {"entry_route":"...","events":[{"type":"...","date":DATE}]}\n'
        "Copy each date the way the note states it; do not calculate dates. DATE is "
        '{"kind":"ABSOLUTE","date":"YYYY-MM-DD"} for a full date (a date without a year lies in the year of the note date), '
        '{"kind":"MONTH","year":Y,"month":M} when the note gives only a month and a year, '
        '{"kind":"DAYS_AGO","n":N} for "N päivää sitten" and {"kind":"WEEKS_AGO","n":N} for "N viikkoa sitten".\n'
    ),
}
_REST = (
    "Event types:\n"
    + "\n".join(f"- {t}: {DEFINITIONS[t]}" for t in TYPES)
    + "\nEntry routes: "
    + ", ".join(f"{k} ({v})" for k, v in ROUTES.items())
    + ". entry_route is the service through which the patient entered the cancer pathway; if the note is not about a cancer pathway, it is the service where the contact takes place.\n"
    "Rules: list only events that the note states as having happened, each with its date. "
    "Ignore birth dates, vaccinations, unrelated or non-cancer care, cancer history without a date, and appointments that have not happened yet. Do not infer events that are not stated. "
    "If there is no such event, return an empty events list. List events in the order their dates appear in the note. No explanation, no Markdown."
)


def system_prompt(fmt):
    """v0 and v1 differ only in the date-format paragraph."""
    return _INTRO + _FORMAT[fmt] + _REST


def messages(row, fmt):
    return [
        {"role": "system", "content": system_prompt(fmt)},
        {"role": "user", "content": f"Note date: {row['note_date']}\n{row['note_text']}"},
    ]


def repair_messages(row, fmt, raw, problems):
    return messages(row, fmt) + [
        {"role": "assistant", "content": raw},
        {
            "role": "user",
            "content": "A program checked your answer against the output schema and the note. Problems found:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nAnswer once more for the same note, fixing every problem and keeping every rule. Return only the JSON.",
        },
    ]


# ---- parsing and local validation ---------------------------------------------------------------


def extract_json(text):
    s = re.sub(r"(?s)^.*</think>", "", (text or "").strip()).strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    if not s.startswith("{"):
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("no JSON object")
        s = s[a : b + 1]
    return json.loads(s)


def parse(text, note_date, fmt):
    """(canonical prediction, raw object) or raise ValueError."""
    try:
        obj = extract_json(text)
        if fmt == "absolute":
            return canonicalise(obj), obj
        return data_tools.resolve_expression(obj, note_date), obj
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"{type(exc).__name__}: {exc}"[:300]) from None


def printed_dates(note_text, note_date):
    """Every date string printed in the note, read by code (the six forms of scribe/sample.py)."""
    found = dict(absolute=set(), month=set(), days=set(), weeks=set())
    for m in data_tools._RE_RELATIVE.finditer(note_text):
        found["weeks" if m[2] == "viikkoa" else "days"].add(int(m[1]))
    for m in data_tools._RE_MONTH.finditer(note_text):
        found["month"].add((int(m[2]), data_tools._MONTH_NUMBER[m[1]]))
    for rx in (data_tools._RE_LONG, data_tools._RE_NUMERIC):
        for m in rx.finditer(note_text):
            try:
                e = data_tools.parse_expression(m[0], note_date)
            except ValueError:
                continue
            if e["kind"] == "ABSOLUTE":
                found["absolute"].add(e["date"])
    return found


def grounding_problems(obj, note_text, note_date):
    """Dates in the expression answer that match no date string printed in the note."""
    found = printed_dates(note_text, note_date)
    problems = []
    for i, event in enumerate(obj.get("events") or []):
        d = event.get("date") if isinstance(event, dict) else None
        if not isinstance(d, dict):
            continue
        kind = d.get("kind")
        ok = (
            (kind == "ABSOLUTE" and d.get("date") in found["absolute"])
            or (kind == "MONTH" and (d.get("year"), d.get("month")) in found["month"])
            or (kind == "DAYS_AGO" and d.get("n") in found["days"])
            or (kind == "WEEKS_AGO" and d.get("n") in found["weeks"])
        )
        if not ok:
            problems.append(
                f"events[{i}] ({event.get('type')}): the date {json.dumps(d, ensure_ascii=False)} matches no date string printed in the note. "
                'Copy the date exactly as the note prints it: "N päivää sitten" is {"kind":"DAYS_AGO","n":N}, "N viikkoa sitten" is {"kind":"WEEKS_AGO","n":N}; never calculate a date.'
            )
    return problems


def check(text, row, cfg):
    """Local validation. Returns (prediction or None, raw object or None, list of problems)."""
    try:
        pred, obj = parse(text, row["note_date"], cfg["fmt"])
    except ValueError as exc:
        return None, None, [f"the answer is not a valid {cfg['fmt']}-format JSON object: {exc}"]
    problems = [f"schema: {p}" for p in serve_client.validate(pred, ABSOLUTE_SCHEMA)]
    note = dt.date.fromisoformat(row["note_date"])
    seen = set()
    for e in pred["events"]:
        if dt.date.fromisoformat(e["date"]) > note:
            problems.append(f"the {e['type']} event resolves to {e['date']}, after the note date {row['note_date']}; only completed events belong in the list")
        if (e["type"], e["date"]) in seen:
            problems.append(f"the {e['type']} event on {e['date']} is listed twice")
        seen.add((e["type"], e["date"]))
    if cfg["ground"]:
        problems += grounding_problems(obj, row["note_text"], row["note_date"])
    return pred, obj, problems


# ---- the protocol for one note ------------------------------------------------------------------


async def read_note(row, version, chat):
    """chat(messages, max_tokens, thinking, tag) -> {"text","reasoning","usage","seconds","finish_reason"}."""
    cfg = CONFIG[version]
    max_tokens = MAX_TOKENS_THINKING if cfg["thinking"] else MAX_TOKENS
    attempts = []
    r = await chat(messages(row, cfg["fmt"]), max_tokens, cfg["thinking"], f"{version}:read")
    pred, _, problems = check(r["text"], row, cfg) if cfg["validate"] else _plain(r["text"], row, cfg)
    attempts.append(dict(action="read", raw=r["text"], reasoning_chars=len(r.get("reasoning") or ""), seconds=r["seconds"], usage=r["usage"], finish_reason=r["finish_reason"], problems=problems, parsed=pred is not None))
    final = 0
    if cfg["validate"] and problems:
        r2 = await chat(repair_messages(row, cfg["fmt"], r["text"], problems), max_tokens, cfg["thinking"], f"{version}:repair")
        pred2, _, problems2 = check(r2["text"], row, cfg)
        attempts.append(dict(action="repair", raw=r2["text"], reasoning_chars=len(r2.get("reasoning") or ""), seconds=r2["seconds"], usage=r2["usage"], finish_reason=r2["finish_reason"], problems=problems2, parsed=pred2 is not None))
        # keep the repair when it passes, or when the first answer did not parse at all
        if not problems2 or (pred is None and pred2 is not None):
            final, pred = 1, pred2
    return dict(
        id=row["id"],
        version=version,
        prediction=pred,
        raw=attempts[final]["raw"],
        selected_attempt=final,
        flagged=bool(attempts[final]["problems"]),
        attempts=attempts,
        latency=round(sum(a["seconds"] for a in attempts), 2),
        calls=len(attempts),
    )


def _plain(text, row, cfg):
    try:
        pred, obj = parse(text, row["note_date"], cfg["fmt"])
        return pred, obj, []
    except ValueError as exc:
        return None, None, [str(exc)]


# ---- data ---------------------------------------------------------------------------------------


def load(split, limit=None):
    import pyarrow.parquet as pq

    rows = []
    for name in SPLITS[split]:
        for r in pq.read_table(DATASET / f"{name}.parquet").to_pylist():
            rows.append(dict(r, split=name))
    return rows[:limit] if limit else rows


def cache_path(version, split, ident):
    return CACHE / version / split / f"{ident}.json"


async def run(split, versions, limit=None, deadline=None, command=""):
    rows = load(split, limit)
    client = C.Nemotron(deadline=deadline)
    start = client.ledger.requests
    t0 = time.monotonic()
    counts = collections.Counter()

    async def chat(msgs, max_tokens, thinking, tag):
        return await client.chat(msgs, max_tokens=max_tokens, temperature=0.0, thinking=thinking, tag=tag)

    async def one(row, version):
        path = cache_path(version, split, row["id"])
        if path.exists():
            counts[f"{version}:cached"] += 1
            return
        try:
            out = await read_note(row, version, chat)
            C.save(path, dict(out, finished_utc=C.now().isoformat(timespec="seconds")))
            counts[f"{version}:done"] += 1
        except Exception as exc:  # recorded, the note stays unread and is re-tried on the next run
            counts[f"{version}:error:{type(exc).__name__}"] += 1

    try:
        for version in versions:  # one version at a time keeps the per-version timing clean
            tv = time.monotonic()
            await asyncio.gather(*(one(r, version) for r in rows))
            counts[f"{version}:wall_seconds"] = round(time.monotonic() - tv, 1)
    finally:
        await client.close()
    metrics = dict(
        split=split,
        notes=len(rows),
        versions=list(versions),
        outcome=dict(counts),
        requests_this_run=client.ledger.requests - start,
        requests_ledger=client.ledger.requests,
        requests_by_tag=dict(client.sent),
        tokens=dict(client.tokens),
        request_errors=dict(client.errors),
        wall_seconds=round(time.monotonic() - t0, 1),
    )
    C.log("4_reader_run", command=command, inputs={"model": C.MODEL, "split": split, "dataset": f"data/scribe/v2/dataset ({'+'.join(SPLITS[split])})", "SYNTHETIC": True}, outputs=[f"data/scribe/nemotron/cache/<version>/{split}/"], metrics=metrics, cost_usd=None)
    print(json.dumps(metrics, ensure_ascii=False))
    return metrics


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--split", choices=sorted(SPLITS), required=True)
    r.add_argument("--versions", default="v0,v1,v2,v2g,v3")
    r.add_argument("--limit", type=int)
    r.add_argument("--deadline", help="HH:MM UTC; no new request after it")
    s = sub.add_parser("report")
    s.add_argument("--selected")
    a = p.parse_args(argv)
    command = "scribe/.venv/bin/python scribe/nemotron/reader.py " + " ".join(argv if argv is not None else sys.argv[1:])
    if a.cmd == "run":
        versions = [v for v in a.versions.split(",") if v]
        bad = [v for v in versions if v not in VERSIONS]
        if bad:
            raise SystemExit(f"unknown version(s) {bad}")
        deadline = None
        if a.deadline:
            hh, mm = map(int, a.deadline.split(":"))
            d = C.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
            if d < C.now() - dt.timedelta(hours=12):
                d += dt.timedelta(days=1)
            deadline = d.timestamp()
        asyncio.run(run(a.split, versions, a.limit, deadline, command))
    else:
        import reader_report

        reader_report.main(a.selected, command)


if __name__ == "__main__":
    main()
