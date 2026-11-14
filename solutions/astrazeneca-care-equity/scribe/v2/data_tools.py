"""Version-2 data tools for the SAMA pathway scribe. SYNTHETIC text only; not for clinical use.

What is here
  expression format   parse_expression, to_expression, expression_target, resolve_expression,
                      EXPRESSION_SCHEMA, expression_messages. The model copies each date the way the note
                      prints it ("12 päivää sitten" -> {"kind":"DAYS_AGO","n":12}) and code does the date
                      arithmetic. Standard library only, so it also runs on the GPU box.
  split loader        load_split(name) for train_nemotron, train_haiku, val_nemotron, val_haiku,
                      test_nemotron, test_haiku (the names scribe/v2/data_iface.py asks for) and for the
                      file names train, val, rejected.
  dataset build       coverage -> verify -> build, as a command line:
                        scribe/.venv/bin/python scribe/v2/data_tools.py coverage
                        scribe/.venv/bin/python scribe/v2/data_tools.py verify [--limit N]
                        scribe/.venv/bin/python scribe/v2/data_tools.py build
                      The two gates are the version-1 ones, imported unchanged from scribe/verify.py:
                      code_check (planned and unplanned dates, 60-140 words), then TypeSafe Jev with
                      verify.questions / verify.accept. A note without a pathway event gets one Noul
                      ("does the note describe any dated cancer-pathway event") that must be below 0.5.

Nothing in this file edits a version-1 file, a slice file or a writer file. Keys are read from the
process environment only and are never written anywhere.
"""

from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import socket
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import _paths  # puts scribe/v2 and scribe on sys.path
from prompts import canonicalise  # version 1
from sample import MONTHS, ROUTES, TYPES  # version 1

ROOT = _paths.ROOT
DATA = ROOT / "data/scribe"
V2 = DATA / "v2"
SLICES = V2 / "slices"
RAW = V2 / "haiku-raw"
VERIFY_CACHE = V2 / "verify"
LEDGER = V2 / "typesafe-usage.json"
COVERAGE = V2 / "coverage.json"
DATASET = V2 / "dataset"
STATS = V2 / "dataset-stats.json"
RUNLOG = ROOT / "runs/v2-data.jsonl"

WRITER_NEMOTRON = "nemotron-3.5-super-vl"
WRITER_HAIKU = "claude-haiku-5-5"
KINDS = ("standard", "careful", "no_event")
FILES = ("train", "val", "test_nemotron", "test_haiku", "rejected")
TEST_HAIKU_N = 200
VAL_HAIKU_N = 60
HELDOUT_SEED = "sama-scribe-v2-heldout-21661114"

PRICE_PER_TOKEN = 0.042 / 1e6  # owner's TypeSafe price: USD 0.042 per million tokens
SPEND_LIMIT_USD = 3.0  # limit given for this step
SPEND_STOP_USD = 2.5  # the code stops here, reservations included
RESERVE_TOKENS = 100_000  # held per request in flight; kept for a failed attempt (version-1 rule)


# ---- expression format (standard library only) --------------------------------------------------

EXPRESSION_KINDS = ("ABSOLUTE", "MONTH", "DAYS_AGO", "WEEKS_AGO")
_MONTH_NUMBER = {name: i for i, name in enumerate(MONTHS, 1)}
_MONTH_ALT = "|".join(MONTHS)
_RE_LONG = re.compile(r"(\d{1,2})\. (" + _MONTH_ALT + r")kuuta (\d{4})")
_RE_MONTH = re.compile(r"(" + _MONTH_ALT + r")kuussa (\d{4})")
_RE_RELATIVE = re.compile(r"(\d+) (päivää|viikkoa) sitten")
_RE_NUMERIC = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?")
MAX_AGO = 100_000

EXPRESSION_SYSTEM = (
    "Extract completed cancer-pathway events only. Return only compact JSON "
    '{"entry_route":...,"events":[{"type":...,"date":DATE}]}. Event types: '
    + ", ".join(TYPES)
    + ". Routes: "
    + ", ".join(ROUTES)
    + ". Copy each date the way the note states it; do not calculate dates. DATE is "
    '{"kind":"ABSOLUTE","date":"YYYY-MM-DD"} for a full date (a missing year means the note year), '
    '{"kind":"MONTH","year":Y,"month":M} when the note gives only a month and a year, '
    '{"kind":"DAYS_AGO","n":N} for "N päivää sitten" and {"kind":"WEEKS_AGO","n":N} for "N viikkoa sitten". '
    "Ignore birth dates, unrelated visits and future appointments. "
    "List events in the order their dates appear in the note. Do not infer undocumented events."
)

_ISO_DATE = "^(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"


def _date_object(kind, properties):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", *properties],
        "properties": {"kind": {"const": kind}, **properties},
    }


# Syntax only. Calendar validity and the numeric ranges are checked by resolve_expression().
EXPRESSION_SCHEMA = {
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
                "required": ["type", "date"],
                "properties": {
                    "type": {"enum": list(TYPES)},
                    "date": {
                        "oneOf": [
                            _date_object("ABSOLUTE", {"date": {"type": "string", "pattern": _ISO_DATE}}),
                            _date_object(
                                "MONTH",
                                {
                                    "year": {"type": "integer", "minimum": 1900, "maximum": 2099},
                                    "month": {"type": "integer", "minimum": 1, "maximum": 12},
                                },
                            ),
                            _date_object("DAYS_AGO", {"n": {"type": "integer", "minimum": 0, "maximum": 9999}}),
                            _date_object("WEEKS_AGO", {"n": {"type": "integer", "minimum": 0, "maximum": 999}}),
                        ]
                    },
                },
            },
        },
    },
}


def _as_date(value):
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _exact_keys(obj, keys, what):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise ValueError(f"{what} must have exactly the keys {sorted(keys)}")


def parse_expression(text, note_date):
    """A date string exactly as a note prints it -> the expression object for that string.

    "3.2.2025", "3.2." and "3. helmikuuta 2025" are ABSOLUTE (a string without a year takes the year of
    the note date), "helmikuussa 2025" is MONTH, "12 päivää sitten" is DAYS_AGO and "8 viikkoa sitten"
    is WEEKS_AGO. Anything else raises ValueError.
    """
    note = _as_date(note_date)
    m = _RE_RELATIVE.fullmatch(text)
    if m:
        return {"kind": "WEEKS_AGO" if m[2] == "viikkoa" else "DAYS_AGO", "n": int(m[1])}
    m = _RE_MONTH.fullmatch(text)
    if m:
        return {"kind": "MONTH", "year": int(m[2]), "month": _MONTH_NUMBER[m[1]]}
    m = _RE_LONG.fullmatch(text)
    if m:
        return {"kind": "ABSOLUTE", "date": dt.date(int(m[3]), _MONTH_NUMBER[m[2]], int(m[1])).isoformat()}
    m = _RE_NUMERIC.fullmatch(text)
    if m:
        year = int(m[3]) if m[3] else note.year
        return {"kind": "ABSOLUTE", "date": dt.date(year, int(m[2]), int(m[1])).isoformat()}
    raise ValueError(f"not a known date string: {text!r}")


def resolve_date(expression, note_date):
    """One expression object -> (ISO date, precision). All date arithmetic of the scribe is here."""
    note = _as_date(note_date)
    if not isinstance(expression, dict):
        raise ValueError("date must be an object")
    kind = expression.get("kind")
    if kind == "ABSOLUTE":
        _exact_keys(expression, ("kind", "date"), "an ABSOLUTE date")
        if not isinstance(expression["date"], str):
            raise ValueError("ABSOLUTE date must be a string")
        day = dt.date.fromisoformat(expression["date"])
        if day.isoformat() != expression["date"]:
            raise ValueError("ABSOLUTE date must be YYYY-MM-DD")
        return day.isoformat(), "DAY"
    if kind == "MONTH":
        _exact_keys(expression, ("kind", "year", "month"), "a MONTH date")
        year, month = _integer(expression["year"], "year"), _integer(expression["month"], "month")
        return dt.date(year, month, 1).isoformat(), "MONTH"
    if kind in ("DAYS_AGO", "WEEKS_AGO"):
        _exact_keys(expression, ("kind", "n"), f"a {kind} date")
        n = _integer(expression["n"], "n")
        if not 0 <= n <= MAX_AGO:
            raise ValueError(f"n must be between 0 and {MAX_AGO}")
        try:
            day = note - dt.timedelta(days=n * (7 if kind == "WEEKS_AGO" else 1))
        except OverflowError as e:
            raise ValueError(f"{kind} {n} is before the calendar starts") from e
        return day.isoformat(), "DAY"
    raise ValueError(f"unknown date kind {kind!r}; expected one of {EXPRESSION_KINDS}")


def resolve_expression(obj, note_date):
    """Expression-format object + note date -> the absolute, canonical version-1 target (a dict).

    Raises ValueError, KeyError or TypeError on anything that is not a well-formed expression object.
    """
    _exact_keys(obj, ("entry_route", "events"), "the output")
    if not isinstance(obj["events"], list):
        raise ValueError("events must be a list")
    events = []
    for event in obj["events"]:
        _exact_keys(event, ("type", "date"), "an event")
        date, precision = resolve_date(event["date"], note_date)
        events.append({"type": event["type"], "date": date, "precision": precision})
    return canonicalise({"entry_route": obj["entry_route"], "events": events})


def _compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def date_pattern(expression):
    """The pattern version 1's code_check uses to find a date string in a note."""
    return r"(?<!\w)" + re.escape(expression) + r"(?!\w)"


def to_expression(row):
    """The expression-format target of a row, as a dict.

    Needs row["facts"] (each with type and the printed "expression"), row["note_date"] and
    row["entry_route"] (or ground_truth / target_json). Events are listed in the order their date strings
    first appear in the note; a string that is not in the note (a rejected note) sorts last. Ties and
    missing strings keep the canonical order (date, then type).
    """
    truth = row.get("ground_truth") or (json.loads(row["target_json"]) if row.get("target_json") else row)
    route = truth["entry_route"]
    facts = row.get("facts")
    if facts is None:
        if not truth["events"]:
            return {"entry_route": route, "events": []}
        raise ValueError("row has no 'facts', so the printed date strings are unknown")
    text = row.get("note_text") or ""
    canonical = sorted(facts, key=lambda f: (f["date"], f["type"]))
    keyed = []
    for i, fact in enumerate(canonical):
        hit = re.search(date_pattern(fact["expression"]), text)
        keyed.append((hit.start() if hit else len(text) + 1, i, fact))
    return {
        "entry_route": route,
        "events": [
            {"type": fact["type"], "date": parse_expression(fact["expression"], row["note_date"])}
            for _, _, fact in sorted(keyed, key=lambda k: k[:2])
        ],
    }


def expression_target(row):
    """The exact text the model must emit in the expression format (compact JSON)."""
    if row.get("expression_json"):
        return row["expression_json"]
    return _compact(to_expression(row))


def expression_messages(row):
    """Chat messages (system + user) that ask for the expression format. The user turn equals version 1."""
    return [
        {"role": "system", "content": EXPRESSION_SYSTEM},
        {"role": "user", "content": f"Note date: {row['note_date']}\n{row['note_text']}"},
    ]


def expression_schema():
    return EXPRESSION_SCHEMA


# ---- run log and small helpers ------------------------------------------------------------------


def log(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=0, status="ok"):
    """Append one JSON line to runs/v2-data.jsonl."""
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    line = dict(
        ts=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        step=step,
        host=socket.gethostname(),
        command=command,
        inputs=inputs,
        outputs=outputs,
        metrics=metrics,
        cost_usd=cost_usd,
        status=status,
    )
    with RUNLOG.open("a") as f:
        f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    return line


def save_json(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(pathlib.Path(path).resolve().relative_to(ROOT))


# ---- step 1: specifications, writer files, coverage ---------------------------------------------


def load_specs():
    """{id: specification} from data/scribe/v2/slices/slice-*.json."""
    specs = {}
    for path in sorted(SLICES.glob("slice-*.json")):
        for spec in json.loads(path.read_text()):
            if spec["id"] in specs:
                raise ValueError(f"specification id twice: {spec['id']}")
            specs[spec["id"]] = spec
    return specs


def _salvage(text):
    """Every JSON object that can be decoded from a text that is not valid JSON as a whole.

    Objects are decoded as they stand; nothing inside a string is changed. Text between objects
    (a Markdown fence, a stray comma, a truncated tail) is skipped.
    """
    decoder = json.JSONDecoder()
    out, pos = [], 0
    while True:
        pos = text.find("{", pos)
        if pos < 0:
            return out
        try:
            value, end = decoder.raw_decode(text, pos)
        except ValueError:
            pos += 1
            continue
        if isinstance(value, dict):
            out.append(value)
        pos = end


def read_part(path):
    """One writer file -> (list of decoded objects, report). Never changes a note."""
    report = {"file": path.name, "bytes": path.stat().st_size, "valid_json": True, "error": None, "objects": 0}
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        report.update(valid_json=False, error=f"not UTF-8: {e}", salvaged_objects=0)
        return [], report
    try:
        data = json.loads(text)
    except ValueError as e:
        data = _salvage(text)
        report.update(valid_json=False, error=str(e)[:200], salvaged_objects=len(data))
    if not isinstance(data, list):
        report["shape"] = f"top level is {type(data).__name__}, not a list"
        data = [data]
    report["objects"] = len(data)
    return data, report


def load_notes(specs=None):
    """All writer notes joined to their specifications: (notes by id, coverage report)."""
    specs = specs or load_specs()
    notes, files, problems = {}, [], []
    for path in sorted(RAW.glob("slice-*-part*.json")):
        data, report = read_part(path)
        m = re.fullmatch(r"slice-(\d+)-part(\d+)\.json", path.name)
        kept = 0
        for item in data:
            where = {"file": path.name}
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                problems.append({**where, "problem": "object without a string id"})
                continue
            ident = item["id"]
            if ident not in specs:
                problems.append({**where, "problem": "id is not in any specification", "id": ident})
                continue
            text = item.get("note_text")
            if not isinstance(text, str) or not text.strip():
                problems.append({**where, "problem": "note_text missing or empty", "id": ident})
                continue
            if set(item) != {"id", "note_text"}:
                problems.append({**where, "problem": f"extra keys {sorted(set(item) - {'id', 'note_text'})}; kept", "id": ident})
            if ident in notes:
                same = notes[ident]["note_text"] == text
                problems.append(
                    {**where, "problem": f"id already in {notes[ident]['file']} ({'same' if same else 'different'} text); first kept", "id": ident}
                )
                continue
            spec = specs[ident]
            if m and (int(m[1]), int(m[2])) != (spec["slice"], spec["part"]):
                problems.append({**where, "problem": f"belongs to slice {spec['slice']} part {spec['part']}; kept", "id": ident})
            notes[ident] = {"note_text": text, "file": path.name}
            kept += 1
        report["notes_kept"] = kept
        files.append(report)
    per_slice = {}
    for spec in specs.values():
        s = per_slice.setdefault(
            f"slice-{spec['slice']:02d}",
            {"specifications": 0, "notes": 0, "missing_ids": [], "by_kind": {k: {"specifications": 0, "notes": 0} for k in KINDS}},
        )
        s["specifications"] += 1
        s["by_kind"][spec["kind"]]["specifications"] += 1
        if spec["id"] in notes:
            s["notes"] += 1
            s["by_kind"][spec["kind"]]["notes"] += 1
        else:
            s["missing_ids"].append(spec["id"])
    report = {
        "specifications": len(specs),
        "files": len(files),
        "files_not_valid_json": [f["file"] for f in files if not f["valid_json"]],
        "notes": len(notes),
        "missing": len(specs) - len(notes),
        "notes_by_kind": dict(collections.Counter(specs[i]["kind"] for i in notes)),
        "specifications_by_kind": dict(collections.Counter(s["kind"] for s in specs.values())),
        "per_slice": dict(sorted(per_slice.items())),
        "per_file": files,
        "problems": problems,
    }
    return notes, report


def joined_rows(specs=None, notes=None):
    """One row per written note, in the shape the version-1 code expects (answer key at top level)."""
    specs = specs or load_specs()
    if notes is None:
        notes, _ = load_notes(specs)
    rows = []
    for ident in sorted(notes):
        spec = specs[ident]
        truth = canonicalise(spec["ground_truth"])
        rows.append(
            {
                **spec,
                **truth,
                "target_json": _compact(truth),
                "note_text": notes[ident]["note_text"],
                "source_file": notes[ident]["file"],
                "writer": WRITER_HAIKU,
                "teacher_model": WRITER_HAIKU,
            }
        )
    return rows


def coverage(_args=None):
    specs = load_specs()
    _, report = load_notes(specs)
    save_json(COVERAGE, report)
    summary = {k: report[k] for k in ("specifications", "files", "files_not_valid_json", "notes", "missing", "notes_by_kind")}
    summary["per_slice"] = {k: f"{v['notes']}/{v['specifications']}" for k, v in report["per_slice"].items()}
    summary["problems"] = len(report["problems"])
    log(
        "load_writer_files",
        command="data_tools.py coverage",
        inputs={"slices": relative(SLICES), "haiku_raw": relative(RAW)},
        outputs=[relative(COVERAGE)],
        metrics=summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for p in report["problems"]:
        print("problem:", json.dumps(p, ensure_ascii=False))
    return report


# ---- step 2: the two gates ----------------------------------------------------------------------

NO_EVENT_KEY = "any_event"
NO_EVENT_QUESTION = (
    "Does the note describe any dated cancer-pathway event? Cancer-pathway events are: reported onset of "
    "cancer-related symptoms, first contact with healthcare about cancer-related symptoms, physician assessment "
    "on the cancer pathway, cancer referral sent or received, cancer specialist visit, cancer diagnosis "
    "confirmed, multidisciplinary team treatment decision and cancer treatment started. Care that is unrelated "
    "to cancer (vaccination, prescription renewal, dental check, minor complaint, routine check-up, screening "
    "for something other than cancer, a referral or a specialist visit for a non-cancer condition), birth dates "
    "and future appointments do not count."
)


def no_event_questions():
    return {NO_EVENT_KEY: {"type": "noul", "instructions": NO_EVENT_QUESTION}}


def no_event_accept(p):
    return set(p) == {NO_EVENT_KEY} and 0 <= p[NO_EVENT_KEY] < 0.5


def gate_for(row):
    """(gate name, Jev state, questions, accept function) for one row."""
    import verify  # version 1, unchanged

    if row["kind"] == "no_event":
        state = {"note": row["note_text"], "note_date": row["note_date"]}
        return "no_event_single_noul", state, no_event_questions(), no_event_accept
    state = {
        "note": row["note_text"],
        "note_date": row["note_date"],
        "expected_events": row["facts"],
        "entry_route": row["entry_route"],
    }
    return "v1_questions", state, verify.questions(row), verify.accept


def note_sha(row):
    return hashlib.sha256(row["note_text"].encode()).hexdigest()


def cache_path(ident):
    return VERIFY_CACHE / f"{ident}.json"


def cached(row):
    path = cache_path(row["id"])
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    return record if record.get("note_sha256") == note_sha(row) else None


class BudgetStop(RuntimeError):
    pass


class Jev:
    """TypeSafe System One client with a persistent token ledger (same request shape as version 1)."""

    URL = "https://api.typesafe.ai/v1/systemone"
    MODEL = "jev-latest"

    def __init__(self, concurrency=12):
        import asyncio

        import httpx

        self.ledger = (
            json.loads(LEDGER.read_text())
            if LEDGER.exists()
            else dict(typesafe_tokens=0, input_tokens=0, output_tokens=0, typesafe_requests=0, failed_attempts=0, typesafe_reserved=0)
        )
        self.sem = asyncio.Semaphore(concurrency)
        self.client = httpx.AsyncClient(timeout=120)

    def spent_usd(self, extra_tokens=0):
        return (self.ledger["typesafe_tokens"] + self.ledger["typesafe_reserved"] + extra_tokens) * PRICE_PER_TOKEN

    async def ask(self, state, questions):
        import asyncio
        import os
        import random

        for attempt in range(4):
            if self.spent_usd(RESERVE_TOKENS) > SPEND_STOP_USD:
                raise BudgetStop(f"conservative spend stop at USD {SPEND_STOP_USD}")
            self.ledger["typesafe_reserved"] += RESERVE_TOKENS
            self.ledger["typesafe_requests"] += 1
            save_json(LEDGER, self.ledger)
            try:
                resp = await self.client.post(
                    self.URL,
                    headers={"Authorization": "Bearer " + os.environ["TYPESAFE_API_KEY"]},
                    json=dict(model=self.MODEL, state=state, questions=questions),
                )
                if resp.status_code != 200:
                    raise RuntimeError("HTTP " + str(resp.status_code))
                result = resp.json()
                usage = result.get("usage", {})
                if "input_tokens" not in usage or "output_tokens" not in usage:
                    raise RuntimeError("missing token usage")
                if set(result.get("answers", {})) != set(questions):
                    raise RuntimeError("missing verifier answers")
                probabilities = {k: float(v["noul"]) for k, v in result["answers"].items()}
            except Exception as exc:
                # A failed attempt may have been billed: its reservation stays (version-1 rule).
                self.ledger["failed_attempts"] += 1
                save_json(LEDGER, self.ledger)
                if attempt == 3:
                    raise RuntimeError(str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__) from None
                await asyncio.sleep(2**attempt + random.random())
                continue
            self.ledger["input_tokens"] += usage["input_tokens"]
            self.ledger["output_tokens"] += usage["output_tokens"]
            self.ledger["typesafe_tokens"] += usage["input_tokens"] + usage["output_tokens"]
            self.ledger["typesafe_reserved"] -= RESERVE_TOKENS
            save_json(LEDGER, self.ledger)
            return probabilities, {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]}


async def _verify(rows, concurrency):
    import asyncio

    import verify  # version 1, unchanged

    jev = Jev(concurrency)
    done = {"cached": 0, "code_check_failed": 0, "judged": 0, "errors": 0, "budget_stop": 0}

    async def one(row):
        record = cached(row)
        if record is not None and "accepted" in record:
            done["cached"] += 1
            return record
        record = {
            "id": row["id"],
            "kind": row["kind"],
            "note_sha256": note_sha(row),
            "code_check": verify.code_check(row),
            "gate": None,
            "verifier_probabilities": {},
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        if not record["code_check"]["ok"]:
            record["accepted"] = False
            done["code_check_failed"] += 1
            save_json(cache_path(row["id"]), record)
            return record
        gate, state, questions, accept = gate_for(row)
        record.update(gate=gate, model=Jev.MODEL)
        async with jev.sem:
            try:
                record["verifier_probabilities"], record["usage"] = await jev.ask(state, questions)
            except BudgetStop as e:
                done["budget_stop"] += 1
                record["error"] = str(e)
                return record  # not cached: nothing was asked
            except Exception as e:
                done["errors"] += 1
                record["error"] = str(e)
                save_json(cache_path(row["id"]), record)
                return record
        record["accepted"] = bool(accept(record["verifier_probabilities"]))
        done["judged"] += 1
        save_json(cache_path(row["id"]), record)
        return record

    try:
        records = await asyncio.gather(*(one(r) for r in rows))
    finally:
        await jev.client.aclose()
    return records, done, jev.ledger


def verify_notes(args):
    import asyncio
    import os
    import time

    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is not in the environment; nothing was sent")
    rows = joined_rows()
    if args.kind:
        rows = [r for r in rows if r["kind"] == args.kind]
    if args.limit:
        rows = sorted(rows, key=lambda r: hashlib.sha256(("pilot:" + r["id"]).encode()).hexdigest())[: args.limit]
    before = json.loads(LEDGER.read_text())["typesafe_tokens"] if LEDGER.exists() else 0
    t = time.monotonic()
    records, done, ledger = asyncio.run(_verify(rows, args.concurrency))
    tokens = ledger["typesafe_tokens"] - before
    metrics = {
        "notes": len(rows),
        **done,
        "accepted": sum(bool(r.get("accepted")) for r in records),
        "seconds": round(time.monotonic() - t, 1),
        "typesafe_tokens_this_step": tokens,
        "ledger": ledger,
        "ledger_cost_usd": ledger["typesafe_tokens"] * PRICE_PER_TOKEN,
    }
    log(
        "verify_notes",
        command="data_tools.py verify" + (f" --limit {args.limit}" if args.limit else "") + (f" --kind {args.kind}" if args.kind else ""),
        inputs={"gates": ["scribe/verify.py code_check", "TypeSafe Jev: verify.questions + verify.accept; no_event: one Noul < 0.5"], "model": Jev.MODEL},
        outputs=[relative(VERIFY_CACHE), relative(LEDGER)],
        metrics=metrics,
        cost_usd=tokens * PRICE_PER_TOKEN,
        status="ok" if not (done["errors"] or done["budget_stop"]) else "incomplete",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return records


CONTROL = V2 / "no-event-gate-control.json"
CONTROL_N = 60


async def _control(rows):
    import asyncio

    jev = Jev()

    async def one(row):
        async with jev.sem:
            p, usage = await jev.ask({"note": row["note_text"], "note_date": row["note_date"]}, no_event_questions())
        return {"id": row["id"], "kind": row["kind"], "events": len(row["events"]), NO_EVENT_KEY: p[NO_EVENT_KEY], "usage": usage}

    try:
        return await asyncio.gather(*(one(r) for r in rows)), jev.ledger
    finally:
        await jev.client.aclose()


def control(_args=None):
    """Positive control for the no_event gate: ask its one question about notes that do hold events.

    The gate is only worth something if it says "yes" for such notes. The notes are accepted Haiku notes
    with at least one event; nothing in the dataset depends on the outcome.
    """
    import asyncio
    import os

    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is not in the environment; nothing was sent")
    rows = [r for r in joined_rows() if r["events"] and (cached(r) or {}).get("accepted")]
    rows = sorted(rows, key=lambda r: hashlib.sha256(("control:" + r["id"]).encode()).hexdigest())[:CONTROL_N]
    before = json.loads(LEDGER.read_text())["typesafe_tokens"] if LEDGER.exists() else 0
    answers, ledger = asyncio.run(_control(rows))
    flagged = sum(a[NO_EVENT_KEY] >= 0.5 for a in answers)
    tokens = ledger["typesafe_tokens"] - before
    out = {
        "question": NO_EVENT_QUESTION,
        "notes": "accepted Haiku notes with at least one pathway event (a fixed pseudo-random subset)",
        "judged_to_contain_an_event": wilson(flagged, len(answers)),
        "lowest_probability": min(a[NO_EVENT_KEY] for a in answers),
        "typesafe_tokens": tokens,
        "answers": answers,
    }
    save_json(CONTROL, out)
    metrics = {k: out[k] for k in ("judged_to_contain_an_event", "lowest_probability", "typesafe_tokens")}
    log("no_event_gate_positive_control", command="data_tools.py control", outputs=[relative(CONTROL)], metrics=metrics, cost_usd=tokens * PRICE_PER_TOKEN)
    print(json.dumps(metrics, ensure_ascii=False, indent=1))
    return out


# ---- step 3: dataset ----------------------------------------------------------------------------


def schema():
    import pyarrow as pa

    event = pa.struct([("type", pa.string()), ("date", pa.string()), ("precision", pa.string())])
    distractor = pa.struct([("kind", pa.string()), ("expression", pa.string()), ("date", pa.string()), ("meaning", pa.string())])
    fact = pa.struct(
        [
            ("type", pa.string()),
            ("date", pa.string()),
            ("precision", pa.string()),
            ("expression", pa.string()),
            ("form", pa.string()),
            ("meaning", pa.string()),
        ]
    )
    return pa.schema(
        [
            # the version-1 columns, same names, types and order
            ("id", pa.string()),
            ("split", pa.string()),
            ("note_text", pa.string()),
            ("note_date", pa.string()),
            ("style", pa.string()),
            ("entry_route", pa.string()),
            ("events", pa.list_(event)),
            ("target_json", pa.string()),
            ("date_forms", pa.list_(pa.string())),
            ("teacher_model", pa.string()),
            ("verifier_probabilities", pa.map_(pa.string(), pa.float64())),
            ("accepted", pa.bool_()),
            ("synthetic", pa.bool_()),
            ("distractors", pa.list_(distractor)),
            # new in version 2
            ("writer", pa.string()),
            ("kind", pa.string()),
            ("expression_json", pa.string()),
            ("focus", pa.string()),
            ("facts", pa.list_(fact)),
            ("reject_stage", pa.string()),
        ]
    )


V1_COLUMNS = (
    "id",
    "split",
    "note_text",
    "note_date",
    "style",
    "entry_route",
    "events",
    "target_json",
    "date_forms",
    "teacher_model",
    "verifier_probabilities",
    "accepted",
    "synthetic",
    "distractors",
)
_FACT_KEYS = ("type", "date", "precision", "expression", "form", "meaning")
_DISTRACTOR_KEYS = ("kind", "expression", "date", "meaning")


def v1_rows():
    """Version-1 rows per split, each joined to its cached generation record for the printed date strings."""
    import pyarrow.parquet as pq

    by_key = {}
    for path in sorted((DATA / "cache").glob("*.json")):
        record = json.loads(path.read_text())
        if "accepted" in record and "note_text" in record:
            by_key.setdefault((record["id"], record["note_text"]), record)
    out = {}
    for split in ("train", "val", "test", "rejected"):
        rows = pq.read_table(DATA / f"dataset-v1/{split}.parquet").to_pylist()
        for row in rows:
            record = by_key[(row["id"], row["note_text"])]
            facts = [{k: f[k] for k in _FACT_KEYS} for f in record["facts"]]
            events = sorted(({k: f[k] for k in ("type", "date", "precision")} for f in facts), key=lambda e: (e["date"], e["type"]))
            if events != row["events"]:
                raise ValueError(f"cached facts do not match the version-1 row {row['id']}")
            row["facts"] = facts
            row["writer"] = WRITER_NEMOTRON
            row["kind"] = "standard"
            row["focus"] = "sampler_v1"
            row["reject_stage"] = None if row["accepted"] else ("verifier" if record["code_check"]["ok"] else "code_check")
        out[split] = rows
    return out


def allocate(counts, total):
    """Proportional allocation of `total` over strata by largest remainder: {stratum: n}."""
    population = sum(counts.values())
    if total > population:
        raise ValueError(f"cannot hold out {total} of {population}")
    exact = {k: total * v / population for k, v in counts.items()}
    out = {k: int(exact[k]) for k in counts}
    for k in sorted(counts, key=lambda k: (-(exact[k] - out[k]), k))[: total - sum(out.values())]:
        out[k] += 1
    return out


def heldout_order(ident):
    return hashlib.sha256(f"{HELDOUT_SEED}:{ident}".encode()).hexdigest()


def assign_haiku(accepted_rows):
    """{id: 'test_haiku' | 'val' | 'train'} for the accepted Haiku rows, stratified by kind."""
    by_kind = collections.defaultdict(list)
    for row in accepted_rows:
        by_kind[row["kind"]].append(row["id"])
    counts = {k: len(v) for k, v in by_kind.items()}
    test = allocate(counts, TEST_HAIKU_N)
    val = allocate({k: counts[k] - test[k] for k in counts}, VAL_HAIKU_N)
    out = {}
    for kind, ids in by_kind.items():
        ids = sorted(ids, key=heldout_order)
        for i, ident in enumerate(ids):
            out[ident] = "test_haiku" if i < test[kind] else "val" if i < test[kind] + val[kind] else "train"
    return out, {"accepted_by_kind": counts, "test_haiku_by_kind": test, "val_haiku_by_kind": val}


def _pack(row, split):
    packed = {name: row.get(name) for name in schema().names}
    packed["split"] = split
    probabilities = row.get("verifier_probabilities") or {}
    packed["verifier_probabilities"] = list(probabilities.items()) if isinstance(probabilities, dict) else list(probabilities)
    packed["facts"] = [{k: f[k] for k in _FACT_KEYS} for f in row["facts"]]
    packed["distractors"] = [{k: d[k] for k in _DISTRACTOR_KEYS} for d in row["distractors"]]
    packed["expression_json"] = _compact(to_expression(row))
    resolved = _compact(resolve_expression(json.loads(packed["expression_json"]), row["note_date"]))
    if resolved != row["target_json"]:
        raise ValueError(f"expression target of {row['id']} does not resolve to its absolute target")
    return packed


def wilson(k, n):
    from metrics import wilson as v1_wilson  # version 1

    return {"k": k, **v1_wilson(k, n)}


def build(_args=None):
    import pyarrow as pa
    import pyarrow.parquet as pq

    specs = load_specs()
    notes, cover = load_notes(specs)
    save_json(COVERAGE, cover)
    rows = joined_rows(specs, notes)
    unverified = []
    for row in rows:
        record = cached(row)
        if record is None or "accepted" not in record:
            unverified.append(row["id"])
            continue
        row["code_check"] = record["code_check"]
        row["verifier_probabilities"] = record["verifier_probabilities"]
        row["accepted"] = record["accepted"]
        row["gate"] = record["gate"]
        row["reject_stage"] = None if record["accepted"] else ("verifier" if record["code_check"]["ok"] else "code_check")
    verified = [r for r in rows if "accepted" in r]
    accepted = [r for r in verified if r["accepted"]]
    assignment, heldout = assign_haiku(accepted)

    v1 = v1_rows()
    files = {
        "train": v1["train"] + [r for r in accepted if assignment[r["id"]] == "train"],
        "val": v1["val"] + [r for r in accepted if assignment[r["id"]] == "val"],
        "test_nemotron": v1["test"],
        "test_haiku": [r for r in accepted if assignment[r["id"]] == "test_haiku"],
        "rejected": v1["rejected"] + [r for r in verified if not r["accepted"]],
    }
    DATASET.mkdir(parents=True, exist_ok=True)
    seen, counts, outputs = {}, {}, {}
    expression_kinds = collections.Counter()
    for split, split_rows in files.items():
        packed = [_pack(r, split) for r in split_rows]
        for p in packed:
            if p["id"] in seen:
                raise ValueError(f"id {p['id']} is in {seen[p['id']]} and {split}")
            seen[p["id"]] = split
            if split != "rejected":
                expression_kinds.update(e["date"]["kind"] for e in json.loads(p["expression_json"])["events"])
        path = DATASET / f"{split}.parquet"
        pq.write_table(pa.Table.from_pylist(packed, schema=schema()), path, compression="zstd")
        outputs[relative(path)] = {"sha256": sha256_file(path), "bytes": path.stat().st_size, "rows": len(packed)}
        by_writer = collections.Counter(p["writer"] for p in packed)
        by_kind = collections.Counter(p["kind"] for p in packed)
        by_both = collections.Counter(f"{p['writer']}|{p['kind']}" for p in packed)
        counts[split] = {
            "rows": len(packed),
            "by_writer": dict(sorted(by_writer.items())),
            "by_kind": dict(sorted(by_kind.items())),
            "by_writer_and_kind": dict(sorted(by_both.items())),
        }

    def rates(subset):
        n = len(subset)
        failed = sum(not r["code_check"]["ok"] for r in subset)
        passed = n - failed
        rejected = sum(r["code_check"]["ok"] and not r["accepted"] for r in subset)
        return {
            "notes": n,
            "code_check_failure": wilson(failed, n),
            "jev_rejection_given_code_pass": wilson(rejected, passed),
            "accepted": wilson(n - failed - rejected, n),
        }

    reasons = collections.Counter()
    for r in verified:
        c = r["code_check"]
        if not c["ok"]:
            reasons["planned_date_string_missing"] += bool(c["missing"])
            reasons["unplanned_date_found"] += bool(c["extra"])
            reasons["length_outside_60_140_words"] += not 60 <= c["words"] <= 140
    jev_reasons = collections.Counter()
    for r in verified:
        if r["code_check"]["ok"] and not r["accepted"]:
            p = r["verifier_probabilities"]
            if r["kind"] == "no_event":
                jev_reasons["no_event_note_judged_to_contain_a_pathway_event"] += 1
                continue
            jev_reasons["event_below_0.8"] += any(v < 0.8 for k, v in p.items() if k.startswith("event_"))
            jev_reasons["route_below_0.8"] += p["route"] < 0.8
            jev_reasons["unlisted_event_at_or_above_0.5"] += p["unlisted"] >= 0.5
            jev_reasons["distractor_at_or_above_0.5"] += any(v >= 0.5 for k, v in p.items() if k.startswith("distractor_"))
    repeated = sum(
        any(len(re.findall(date_pattern(s), r["note_text"])) > 1 for s in r["date_strings"]) for r in accepted
    )
    by_focus = collections.defaultdict(lambda: [0, 0])
    by_type = collections.defaultdict(lambda: [0, 0])
    for r in verified:
        by_focus[r["focus"]][1] += 1
        by_focus[r["focus"]][0] += not r["accepted"]
        if r["code_check"]["ok"] and r["kind"] != "no_event":
            for i, fact in enumerate(r["facts"]):
                by_type[fact["type"]][1] += 1
                by_type[fact["type"]][0] += r["verifier_probabilities"][f"event_{i}"] < 0.8
    control_result = json.loads(CONTROL.read_text()) if CONTROL.exists() else None
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    verify_usage = [json.loads(cache_path(r["id"]).read_text()).get("usage") for r in verified]
    verify_tokens = sum(u["input_tokens"] + u["output_tokens"] for u in verify_usage if u)
    control_tokens = json.loads(CONTROL.read_text())["typesafe_tokens"] if CONTROL.exists() else 0
    stats = {
        "schemaVersion": "scribe-dataset-v2-stats",
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "synthetic_only": True,
        "counts": counts,
        "total_rows": sum(c["rows"] for c in counts.values()),
        "haiku": {
            "writer": WRITER_HAIKU,
            "specifications": cover["specifications"],
            "writer_files": cover["files"],
            "writer_files_not_valid_json": cover["files_not_valid_json"],
            "notes_loaded": cover["notes"],
            "specifications_without_note": cover["missing"],
            "specifications_without_note_ids": [i for v in cover["per_slice"].values() for i in v["missing_ids"]],
            "notes_per_slice": {k: v["notes"] for k, v in cover["per_slice"].items()},
            "load_problems": len(cover["problems"]),
            "notes_not_verified": len(unverified),
            "all_kinds": rates(verified),
            "by_kind": {k: rates([r for r in verified if r["kind"] == k]) for k in KINDS},
            "code_check_failure_reasons": dict(reasons),
            "jev_rejection_reasons": dict(jev_reasons),
            "rejected_by_focus": {k: {"rejected": v[0], "notes": v[1]} for k, v in sorted(by_focus.items())},
            "events_scored_below_0.8_by_type": {k: {"below": by_type[k][0], "events": by_type[k][1]} for k in TYPES if k in by_type},
            "accepted_notes_with_a_date_string_printed_more_than_once": repeated,
            "no_event_gate_positive_control": None
            if control_result is None
            else {
                "what": "the no_event question asked about accepted Haiku notes that do hold pathway events",
                "judged_to_contain_an_event": control_result["judged_to_contain_an_event"],
                "lowest_probability": control_result["lowest_probability"],
            },
            "no_event_highest_probability": max((r["verifier_probabilities"][NO_EVENT_KEY] for r in verified if r["kind"] == "no_event"), default=None),
            "gates": {
                "code_check": "scribe/verify.py code_check, unchanged",
                "jev_standard_and_careful": "scribe/verify.py questions + accept, unchanged (events and route >= 0.8; unlisted and distractors < 0.5)",
                "jev_no_event": {"question": NO_EVENT_QUESTION, "rule": "noul < 0.5"},
                "model": Jev.MODEL,
            },
        },
        "heldout": {"rule": "per kind, ids sorted by sha256(seed:id); first to test_haiku, next to val, rest to train", "seed": HELDOUT_SEED, **heldout},
        "expression_target": {
            "kinds_in_train_val_test": dict(sorted(expression_kinds.items())),
            "rows_checked_to_resolve_to_absolute_target": sum(c["rows"] for c in counts.values()),
            "rows_that_do_not_resolve": 0,
            "event_order": "order in which the date strings first appear in the note",
        },
        "typesafe": {
            "tokens": ledger.get("typesafe_tokens"),
            "input_tokens": ledger.get("input_tokens"),
            "output_tokens": ledger.get("output_tokens"),
            "requests": ledger.get("typesafe_requests"),
            "tokens_verifying_notes": verify_tokens,
            "requests_verifying_notes": sum(u is not None for u in verify_usage),
            "tokens_no_event_gate_positive_control": control_tokens,
            "failed_attempts": ledger.get("failed_attempts"),
            "tokens_still_reserved_for_failed_attempts": ledger.get("typesafe_reserved"),
            "price_usd_per_million_tokens": 0.042,
            "cost_usd": None if not ledger else ledger["typesafe_tokens"] * PRICE_PER_TOKEN,
            "cost_usd_counting_reservations": None if not ledger else (ledger["typesafe_tokens"] + ledger["typesafe_reserved"]) * PRICE_PER_TOKEN,
            "limit_usd": SPEND_LIMIT_USD,
        },
        "inputs": {
            "version_1": {f"data/scribe/dataset-v1/{s}.parquet": sha256_file(DATA / f"dataset-v1/{s}.parquet") for s in ("train", "val", "test", "rejected")},
            "writer_instructions_sha256": sha256_file(V2 / "WRITER_INSTRUCTIONS.md"),
            "scribe_verify_py_sha256": sha256_file(ROOT / "scribe/verify.py"),
        },
        "outputs": outputs,
    }
    save_json(STATS, stats)
    (DATASET / "CARD.md").write_text(card(stats))
    log(
        "build_dataset",
        command="data_tools.py build",
        inputs={"version_1": "data/scribe/dataset-v1", "haiku_raw": relative(RAW), "verify_cache": relative(VERIFY_CACHE)},
        outputs=[*outputs, relative(STATS), relative(DATASET / "CARD.md")],
        metrics={
            "rows": {k: v["rows"] for k, v in counts.items()},
            "haiku_accepted": len(accepted),
            "haiku_rejected": len(verified) - len(accepted),
            "haiku_not_verified": len(unverified),
            "heldout": heldout,
        },
        status="ok" if not unverified else "incomplete",
    )
    print(json.dumps({"counts": counts, "heldout": heldout, "not_verified": len(unverified)}, ensure_ascii=False, indent=1))
    return stats


def _rate(w):
    if w["value"] is None:
        return "no notes"
    return f"{w['k']} of {w['n']} ({100 * w['value']:.1f} %, 95 % interval {100 * w['ci95'][0]:.1f} to {100 * w['ci95'][1]:.1f} %)"


def card(stats):
    c, h, t = stats["counts"], stats["haiku"], stats["typesafe"]
    lines = [
        "# SAMA pathway scribe dataset v2",
        "",
        "SYNTHETIC ONLY. Every note is invented text written by a language model from a sampled answer key.",
        "No real patients, clinicians or patient text. A research artefact, not a medical device, and not for clinical use.",
        "",
        "The task: read one Finnish clinical-style note and its note date, and return the entry route and the",
        "dated cancer-pathway events as canonical JSON. Version 2 adds a second writer (Claude Haiku) to the",
        "Nemotron notes of version 1, notes without any pathway event, notes built around two wording traps",
        "(referral sent versus received; first contact versus physician assessment versus specialist visit), and a",
        "second target format in which the model copies each date as printed and code does the date arithmetic.",
        "",
        "## Files",
        "",
        "| file | rows | " + WRITER_NEMOTRON + " | " + WRITER_HAIKU + " | standard | careful | no_event |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for split in FILES:
        s = c[split]
        lines.append(
            f"| `{split}.parquet` | {s['rows']} | {s['by_writer'].get(WRITER_NEMOTRON, 0)} | {s['by_writer'].get(WRITER_HAIKU, 0)} | "
            + " | ".join(str(s["by_kind"].get(k, 0)) for k in KINDS)
            + " |"
        )
    lines += [
        "",
        "- `train` = version-1 train + the accepted Haiku notes that are not held out.",
        f"- `val` = version-1 val + {VAL_HAIKU_N} accepted Haiku notes.",
        "- `test_nemotron` = version-1 test, the same rows in the same order.",
        f"- `test_haiku` = {TEST_HAIKU_N} accepted Haiku notes, held out and stratified by kind: "
        + ", ".join(f"{k} {v}" for k, v in sorted(stats["heldout"]["test_haiku_by_kind"].items()))
        + ".",
        "- `rejected` = version-1 rejected + the Haiku notes that failed a gate. Not for training.",
        "",
        "No id occurs in two files. For a note with events the id is the SHA-256 of its answer key (route and",
        "events), so identical ground truth cannot sit on both sides of a split. A note without events has one of",
        "only five possible answers (a route and an empty list), so there the id also covers the dated content.",
        "The hold-out is fixed by a hash of the id (`heldout` in the statistics file), not by file order.",
        "",
        "## Columns",
        "",
        "The version-1 columns keep their names, types and order: `id`, `split`, `note_text`, `note_date`, `style`,",
        "`entry_route`, `events`, `target_json`, `date_forms`, `teacher_model`, `verifier_probabilities`, `accepted`,",
        "`synthetic`, `distractors`. `split` holds the name of the version-2 file; every other version-1 value of a",
        "version-1 row is unchanged. New columns:",
        "",
        "| column | content |",
        "| --- | --- |",
        f"| `writer` | `{WRITER_NEMOTRON}` or `{WRITER_HAIKU}` |",
        "| `kind` | `standard`, `careful` or `no_event` (all version-1 rows are `standard`) |",
        "| `expression_json` | the expression target, see below |",
        "| `focus` | what the specification was built to exercise, e.g. `referral_sent_only`, `non_cancer_lookalike` |",
        "| `facts` | the events with the date string printed in the note (`expression`) and its form |",
        "| `reject_stage` | `code_check` or `verifier` in `rejected.parquet`, otherwise empty |",
        "",
        "## The expression target",
        "",
        "`target_json` gives absolute dates, so the model has to turn `12 päivää sitten` into a calendar date.",
        "`expression_json` holds the same events with each date as the note states it:",
        "",
        "```",
        '{"kind":"ABSOLUTE","date":"YYYY-MM-DD"}   3.2.2025, 3. helmikuuta 2025, and 3.2. (year of the note date)',
        '{"kind":"MONTH","year":Y,"month":M}       helmikuussa 2025',
        '{"kind":"DAYS_AGO","n":N}                 12 päivää sitten',
        '{"kind":"WEEKS_AGO","n":N}                8 viikkoa sitten',
        "```",
        "",
        "Events are listed in the order their date strings first appear in the note, so that no date comparison is",
        "needed to order them. `scribe/v2/data_tools.py` has the resolver (`resolve_expression(obj, note_date)`), the",
        "prompt (`expression_messages`) and a JSON schema for constrained decoding (`EXPRESSION_SCHEMA`). A test",
        f"resolves the expression target of all {stats['expression_target']['rows_checked_to_resolve_to_absolute_target']} rows against the note date and compares the result with",
        "`target_json`; the build refuses to write a row that does not match. Date kinds in train, val and test: "
        + ", ".join(f"{k} {v}" for k, v in stats["expression_target"]["kinds_in_train_val_test"].items())
        + ".",
        "",
        "## How the Haiku notes were made and checked",
        "",
        f"{h['specifications']} specifications (900 standard, 150 careful, 150 no_event) were sampled by code with seeds that",
        "differ from version 1; none shares an id or an answer key with version 1 or the earlier 60-note Haiku pilot.",
        f"Twelve Claude Haiku agents wrote the notes from `WRITER_INSTRUCTIONS.md`. {h['notes_loaded']} notes were delivered in",
        f"{h['writer_files']} files"
        + (", all valid JSON" if not h["writer_files_not_valid_json"] else f"; not valid JSON: {', '.join(h['writer_files_not_valid_json'])}")
        + f"; {h['specifications_without_note']} specification(s) have no note. Note text was not edited.",
        "The writers were told to leave a note out rather than break a rule, and one reported checking its notes",
        "with a script, so the code-check rate below describes delivered notes.",
        "",
        "Both gates are the version-1 ones, imported unchanged from `scribe/verify.py`:",
        "",
        "1. Code check: every planned date string is present, nothing else looks like a date, 60 to 140 words.",
        "2. TypeSafe Jev (`jev-latest`): one Noul per event and one for the route (each at least 0.8), one for any",
        "   unlisted event and one per non-event date (each below 0.5). A `no_event` note gets a single Noul, whether",
        "   the note describes any dated cancer-pathway event, which must be below 0.5.",
        "",
        "| kind | notes | code check failed | Jev rejected, of those that passed the code check | accepted |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, r in [("all", h["all_kinds"]), *[(k, h["by_kind"][k]) for k in KINDS]]:
        lines.append(f"| {name} | {r['notes']} | {_rate(r['code_check_failure'])} | {_rate(r['jev_rejection_given_code_pass'])} | {_rate(r['accepted'])} |")
    lines += [
        "",
        "Intervals are Wilson 95 % intervals. Reasons for a code-check failure (a note can have several): "
        + (", ".join(f"{k.replace('_', ' ')} {v}" for k, v in h["code_check_failure_reasons"].items()) or "none")
        + ". Reasons for a Jev rejection (a note can have several): "
        + (", ".join(f"{k.replace('_', ' ')} {v}" for k, v in h["jev_rejection_reasons"].items()) or "none")
        + ".",
        "",
        "Rejected notes by what the specification exercised: "
        + ", ".join(f"{k} {v['rejected']} of {v['notes']}" for k, v in h["rejected_by_focus"].items() if v["rejected"])
        + ". Events scored below 0.8, by type: "
        + ", ".join(f"{k} {v['below']} of {v['events']}" for k, v in h["events_scored_below_0.8_by_type"].items())
        + ".",
        "",
        *(
            []
            if h["no_event_gate_positive_control"] is None
            else [
                f"The single `no_event` question gave at most {h['no_event_highest_probability']} for the {h['by_kind']['no_event']['notes']} `no_event` notes. As a positive control",
                "the same question was asked about accepted Haiku notes that do hold pathway events: "
                + _rate(h["no_event_gate_positive_control"]["judged_to_contain_an_event"])
                + f" were judged to contain one, lowest probability {h['no_event_gate_positive_control']['lowest_probability']}.",
                "",
            ]
        ),
        (
            f"TypeSafe use for this step: {t['requests']} requests, {t['tokens']} tokens ({t['input_tokens']} in, {t['output_tokens']} out), "
            f"USD {t['cost_usd']:.6f} at USD 0.042 per million tokens; {t['failed_attempts']} failed attempt(s). Of these, "
            f"{t['requests_verifying_notes']} requests and {t['tokens_verifying_notes']} tokens verified notes and "
            f"{t['tokens_no_event_gate_positive_control']} tokens were the positive control. The limit was USD {t['limit_usd']:.0f}."
        ),
        "",
        "## Limits",
        "",
        "- A Jev probability is a model judgment. Passing both gates does not prove that a label is right, and the",
        "  thresholds are the version-1 ones. In version 1 a stricter second Jev pass disagreed with 43 of 60 sampled",
        "  accepted notes, while an independent reader found 2 indefensible labels in 60 (the version-1 card and",
        "  `data/scribe/label-audit-v1.json`). Neither audit has been run on the Haiku notes.",
        "- The accepted Haiku notes are the ones Jev scored highly. Most rejections were a route score below 0.8, so",
        "  train, val and `test_haiku` over-represent the ways of stating the route that Jev reads as explicit.",
        "  `test_haiku` was filtered by the same gate as the training notes and is not an unfiltered sample of the writer.",
        "- `test_haiku`, `val` and `train` Haiku notes come from the same 12 writer sessions (slices): notes were held out",
        "  by a hash of their id within each kind, not by session (`assign_haiku`). A run trained on Haiku notes is",
        "  therefore tested on notes from sessions it saw in training, which favours it. No near-duplicates were found",
        "  (review of 2026-11-14, `runs/review-findings-v2.json` finding 8), but a session-disjoint Haiku test set, for",
        "  example two whole slices held out, is needed before claiming that Haiku training generalises across sessions.",
        "- The `no_event` gate asks one question. It does not check that the note names the service given as",
        "  `entry_route`; by convention the route of a note without events is the service where the contact takes place.",
        (
            "- The code check would accept a date string that is printed more than once; "
            f"{h['accepted_notes_with_a_date_string_printed_more_than_once']} accepted Haiku note(s) do that."
        ),
        "- A date without a year (`3.2.`) is ABSOLUTE in the expression target, so the model still has to copy the",
        "  year from the note date for that one form.",
        "- The Finnish of the specifications and the notes has not been reviewed by a Finnish clinician.",
        "- Sampled answer keys are a language-coverage design (uniform event subsets, evenly spread routes), not",
        "  Finnish epidemiology. Two writers are still only two writers; real records will differ from both.",
        "- Nothing here establishes how well a model trained on this data extracts events.",
        "",
        "Exact numbers, hashes of inputs and outputs: `data/scribe/v2/dataset-stats.json`. Reproduce with",
        "`scribe/.venv/bin/python scribe/v2/data_tools.py build`; test with",
        "`scribe/.venv/bin/python -m unittest discover -s data/scribe/v2/tests`.",
        "",
    ]
    return "\n".join(lines)


# ---- split loader used by scribe/v2/data_iface.py ------------------------------------------------

_SPLIT_FILES = {
    "train_nemotron": ("train", WRITER_NEMOTRON),
    "train_haiku": ("train", WRITER_HAIKU),
    "val_nemotron": ("val", WRITER_NEMOTRON),
    "val_haiku": ("val", WRITER_HAIKU),
    "test_nemotron": ("test_nemotron", None),
    "test_haiku": ("test_haiku", None),
    "train": ("train", None),
    "val": ("val", None),
    "rejected": ("rejected", None),
}


def load_split(name):
    """Rows (dicts) of one split. Raises FileNotFoundError until the dataset has been built."""
    if name not in _SPLIT_FILES:
        raise ValueError(f"unknown split {name!r}; expected one of {sorted(_SPLIT_FILES)}")
    import pyarrow.parquet as pq

    stem, writer = _SPLIT_FILES[name]
    path = DATASET / f"{stem}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run data_tools.py build")
    rows = pq.read_table(path).to_pylist()
    if writer:
        rows = [r for r in rows if r["writer"] == writer]
    for row in rows:
        row["verifier_probabilities"] = dict(row["verifier_probabilities"] or [])
    return rows


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="step", required=True)
    sub.add_parser("coverage").set_defaults(run=coverage)
    v = sub.add_parser("verify")
    v.add_argument("--limit", type=int, default=0, help="verify only this many notes (a fixed pseudo-random subset)")
    v.add_argument("--kind", choices=KINDS)
    v.add_argument("--concurrency", type=int, default=12)
    v.set_defaults(run=verify_notes)
    sub.add_parser("control").set_defaults(run=control)
    sub.add_parser("build").set_defaults(run=build)
    args = parser.parse_args(argv)
    args.run(args)


if __name__ == "__main__":
    main()
