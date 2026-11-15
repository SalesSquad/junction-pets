"""Teaching round 2: the teacher protocol around NVIDIA Nemotron 3.5 Super VL on Verda.

Per specification: (a) WRITE the note, (b) code check, (c) BLIND READ-BACK by a fresh teacher call that
sees only the note, the note date and the event-type definitions, (d) at most ONE REPAIR with the precise
difference, then (b) and (c) again. Every attempt is recorded. A note is never dropped because the
read-back disagrees; the flag is kept for the judges and the audit.

The call (URL, headers, model, enable_thinking=false), the model discovery, the retry rule and the
concurrency (12) follow scribe/generate.py. Everything is SYNTHETIC; not for clinical use.

Run from the project root (keys only in the environment of the command):
    scribe/.venv/bin/python scribe/teacher2/protocol.py preflight
    scribe/.venv/bin/python scribe/teacher2/protocol.py run --limit 40          # pilot
    scribe/.venv/bin/python scribe/teacher2/protocol.py run --deadline 19:03    # the rest
    scribe/.venv/bin/python scribe/teacher2/protocol.py finalise
"""

import argparse
import asyncio
import collections
import datetime as dt
import json
import os
import pathlib
import random
import re
import socket
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "scribe" / "v2"), str(ROOT / "scribe"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import data_tools  # noqa: E402  scribe/v2, read only: the expression format and its date arithmetic

import verify  # noqa: E402  version 1 code check, unchanged
from prompts import canonicalise  # noqa: E402
from sample import ROUTES, TYPES  # noqa: E402

MODEL = "nemotron-3.5-super-vl"
CAP = 5500
CONCURRENCY = 12  # scribe/generate.py: asyncio.Semaphore(12)
OUT = ROOT / "data/scribe/v3/teacher"
CACHE = OUT / "cache"
LEDGER = OUT / "ledger.json"  # next to the cache; never reset
RUNLOG = ROOT / "runs/teacher2.jsonl"
CURRICULA = ("hard_standard", "careful", "no_event", "long_multi_visit", "terse")
# words: (code-check bounds, target given to the writer, max_tokens of the write call)
LENGTH = {
    "hard_standard": ((60, 140), (85, 120), 650),
    "careful": ((60, 140), (85, 120), 650),
    "no_event": ((60, 140), (80, 110), 650),
    "long_multi_visit": ((110, 260), (150, 220), 1200),
    "terse": ((25, 90), (35, 70), 450),
}
_FILL = "Kuvaa nykyvointia, toimintakykyä, arjessa selviytymistä ja potilaan saamaa yleistä neuvontaa riittävän laajasti, yhteensä {lo}–{hi} sanaa. Älä tiivistä alle {lo} sanaan. Palauta vain valmis merkintä: ei sanamäärää, ei laskelmia, ei kommentteja, ei luonnoksia."
CLOSING = {  # scribe/generate.py reached its length the same way: a minimum number of full sentences
    "hard_standard": "Kirjoita vähintään 14 kokonaista virkettä. " + _FILL,
    "careful": "Kirjoita vähintään 14 kokonaista virkettä. " + _FILL,
    "no_event": "Kirjoita vähintään 12 kokonaista virkettä. " + _FILL,
    "long_multi_visit": "Kirjoita vähintään 22 kokonaista virkettä. " + _FILL,
    "terse": "Kirjoita sähkösanomatyyliin, yhteensä {lo}–{hi} sanaa. Palauta vain valmis merkintä: ei sanamäärää, ei laskelmia, ei kommentteja, ei luonnoksia.",
}
DIFFERENCE_CLASSES = ("missing_event", "extra_event", "wrong_date", "wrong_type", "wrong_route", "invalid_output")

DEFINITIONS = {
    "SYMPTOM_ONSET_REPORTED": "the patient's own report of when the symptoms behind the cancer suspicion began",
    "FIRST_CONTACT": "the patient got in touch with healthcare about these symptoms for the first time (a call, a message or a walk-in answered by a nurse or a booking service); no physician examined the patient then",
    "PHYSICIAN_ASSESSMENT": "a physician of the entry service (health centre, occupational health, private clinic, emergency department or screening unit) examined and assessed the patient; not a nurse, not the treating specialist in specialised care",
    "REFERRAL_SENT": "the referring physician wrote the referral and sent it to specialised care; this is not its arrival",
    "REFERRAL_RECEIVED": "the referral arrived at the specialised-care unit and was registered there; this is not its sending",
    "SPECIALIST_VISIT": "the patient attended the appointment of the treating specialist in specialised care",
    "DIAGNOSIS": "the cancer diagnosis was confirmed",
    "MDT_DECISION": "the multidisciplinary meeting decided on treatment",
    "TREATMENT_START": "the first cancer treatment started",
}

WRITE_SYSTEM = (
    "You write one short SYNTHETIC Finnish clinical-style note from a specification. The patient is invented; use no names. "
    "A program checks the note and an independent reader then lists the dated cancer-pathway events in it, so the note must say exactly what the specification says: nothing missing, nothing added, every date string intact.\n"
    "RULES\n"
    "1. Finnish, in the register of a real patient record. One paragraph, no heading, no list, no line break, no Markdown, no quotation marks. Do not begin with the name of the note style.\n"
    "2. State every line of FACTS. Add no other cancer-pathway step, with or without a date: no extra contact, physician assessment, referral sent or received, specialist appointment, confirmed diagnosis, team decision or start of treatment.\n"
    "3. Every string of DATE STRINGS appears exactly once, character for character: same digits, dots, spaces, lower-case letters and inflection. Do not add a year or a day to it. Never begin a sentence with a month string such as 'marraskuussa 2025'.\n"
    "4. No other date or time reference of any kind: not the note date, no tänään, eilen, huomenna, viime viikolla, viime kuussa, no bare year, no month name, no weekday, no 'N viikon kuluttua', no duration. No digit outside the date strings (no age, laboratory value, dose, clock time, stage).\n"
    "5. One date string belongs to one fact. The words next to each date string must make clear what happened then.\n"
    "6. Text in [square brackets] and after 'ilman päivämäärää:' is an explanation in English. Express what it means in your own Finnish; never copy it and never translate it word for word. A line marked [not a pathway event] or [has not happened yet] must be written so that nobody can read it as a completed cancer-pathway step.\n"
    "7. The note must contain one sentence that says in so many words through which service the patient entered the cancer pathway ('syöpäpolun tuloreitti'), or, when the first line is 'asiointipaikka', in which service this ordinary contact takes place. Use the Finnish name of the service as given.\n"
    "8. Reach the length with neutral undated content: how the patient feels now, functional ability, coping at home, general counselling. Never invent examinations, visits or treatments with a time.\n"
    "Return only the finished note. Never output a word count, a draft, a comment or anything in English."
)

READBACK_SYSTEM = (
    "You read one Finnish clinical-style note and list the completed, dated cancer-pathway events it states. You see only the note and its note date.\n"
    'Return only compact JSON: {"entry_route":"...","events":[{"type":"...","date":DATE}]}\n'
    "Copy each date the way the note states it; do not calculate dates. DATE is "
    '{"kind":"ABSOLUTE","date":"YYYY-MM-DD"} for a full date (a date without a year lies in the year of the note date), '
    '{"kind":"MONTH","year":Y,"month":M} when the note gives only a month and a year, '
    '{"kind":"DAYS_AGO","n":N} for "N päivää sitten" and {"kind":"WEEKS_AGO","n":N} for "N viikkoa sitten".\n'
    "Event types:\n"
    + "\n".join(f"- {t}: {DEFINITIONS[t]}" for t in TYPES)
    + "\nEntry routes: "
    + ", ".join(f"{k} ({v})" for k, v in ROUTES.items())
    + ". entry_route is the service through which the patient entered the cancer pathway; if the note is not about a cancer pathway, it is the service where the contact takes place.\n"
    "Rules: list only events that the note states as having happened, each with its date. "
    "Ignore birth dates, vaccinations, unrelated or non-cancer care, cancer history without a date, and appointments that have not happened yet. Do not infer events that are not stated. "
    "If there is no such event, return an empty events list. List events in the order their dates appear in the note. No explanation, no Markdown."
)


# ---- small helpers ------------------------------------------------------------------------------


def now():
    return dt.datetime.now(dt.timezone.utc)


def log(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=None, status="ok"):
    RUNLOG.parent.mkdir(exist_ok=True)
    line = dict(
        ts=now().isoformat(timespec="seconds"),
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
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---- ledger -------------------------------------------------------------------------------------


class CapReached(RuntimeError):
    pass


class DeadlineReached(RuntimeError):
    pass


class Ledger:
    """Counts every teacher request attempt in a file. The count only grows; there is no reset."""

    def __init__(self, path=LEDGER, cap=CAP):
        self.path = pathlib.Path(path)
        self.cap = cap
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"teacher_requests": 0}
        self.data["cap"] = cap

    @property
    def requests(self):
        return self.data["teacher_requests"]

    def reserve(self):
        """Count one request before it is sent; refuse when the cap is reached."""
        if self.data["teacher_requests"] >= self.cap:
            raise CapReached(f"teacher cap {self.cap} reached")
        self.data["teacher_requests"] += 1
        save(self.path, self.data)
        return self.data["teacher_requests"]


# ---- code check ---------------------------------------------------------------------------------


def code_check(spec, note_text):
    """scribe/verify.py code_check (required date strings present, no undeclared date), unchanged.

    `passed` uses version 1's 60-140 word rule for the three version-2 kinds and the stated bounds of
    LENGTH for the two new curricula (long notes and terse notes cannot fit 60-140 by design).
    """
    raw = verify.code_check(dict(note_text=note_text, facts=spec["facts"], distractors=spec["distractors"]))
    lo, hi = LENGTH[spec["curriculum"]][0]
    failures = [f"missing_date_string:{s}" for s in raw["missing"]]
    failures += [f"undeclared_date:{s}" for s in raw["extra"]]
    if not lo <= raw["words"] <= hi:
        failures.append(f"words:{raw['words']} outside {lo}-{hi}")
    return dict(passed=not failures, failures=failures, words=raw["words"], v1_ok=raw["ok"])


# ---- read-back difference -----------------------------------------------------------------------


def parse_readback(text, note_date=None):
    """Canonical absolute answer from the reader's text, or raise ValueError.

    The reader answers in version 2's expression format (it copies "12 päivää sitten" as DAYS_AGO 12);
    scribe/v2/data_tools.resolve_expression does the date arithmetic. An answer that is already in the
    absolute version-1 format is accepted as well.
    """
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    if not s.startswith("{"):
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("no JSON object")
        s = s[a : b + 1]
    try:
        obj = json.loads(s)
        events = obj.get("events") if isinstance(obj, dict) else None
        if note_date and isinstance(events, list) and any(isinstance(e, dict) and isinstance(e.get("date"), dict) for e in events):
            return data_tools.resolve_expression(obj, note_date)
        return canonicalise(obj)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"{type(exc).__name__}: {exc}") from None


def classify(truth, answer):
    """Differences between the answer key and the read-back answer (both canonical dicts).

    Classes: wrong_route; then, among events that do not match exactly (type, date, precision):
    wrong_date (same type, other date or precision), wrong_type (same date, other type),
    missing_event (in the key, not read), extra_event (read, not in the key).
    """
    out = []
    if truth["entry_route"] != answer["entry_route"]:
        out.append({"class": "wrong_route", "expected": truth["entry_route"], "got": answer["entry_route"]})
    key = lambda e: (e["type"], e["date"], e["precision"])  # noqa: E731
    want = [dict(e) for e in truth["events"]]
    got = [dict(e) for e in answer["events"]]
    for e in list(want):
        for g in got:
            if key(g) == key(e):
                want.remove(e)
                got.remove(g)
                break
    for e in list(want):  # same type, nearest date
        same = [g for g in got if g["type"] == e["type"]]
        if same:
            day = dt.date.fromisoformat(e["date"])
            g = min(same, key=lambda g: (abs((dt.date.fromisoformat(g["date"]) - day).days), g["date"]))
            out.append({"class": "wrong_date", "expected": e, "got": g})
            want.remove(e)
            got.remove(g)
    for e in list(want):  # same date, other type
        same = [g for g in got if g["date"] == e["date"]]
        if same:
            g = same[0]
            out.append({"class": "wrong_type", "expected": e, "got": g})
            want.remove(e)
            got.remove(g)
    out += [{"class": "missing_event", "expected": e, "got": None} for e in want]
    out += [{"class": "extra_event", "expected": None, "got": g} for g in got]
    return out


def truth_of(spec):
    return canonicalise(spec["ground_truth"])


# ---- prompts ------------------------------------------------------------------------------------


def write_messages(spec):
    lo, hi = LENGTH[spec["curriculum"]][1]
    lines = [
        f"STYLE: {spec['style']}",
        f"LENGTH: {lo} to {hi} whitespace-separated words.",
        f"NOTE DATE (only so that relative strings make sense; never print it): {spec['note_date']}",
        "FACTS:",
    ]
    lines += [f"- {x}" for x in spec["facts_fi"]]
    strings = list(spec["date_strings"])
    if spec["curriculum"] == "long_multi_visit":  # list them in the telling order, not in time order
        where = {s: k for k, line in enumerate(spec["facts_fi"]) for s in strings if line.endswith(": " + s)}
        strings.sort(key=lambda s: where.get(s, len(where)))
    lines.append("DATE STRINGS (each exactly once, character for character): " + " | ".join(f"'{s}'" for s in strings))
    if spec["curriculum"] == "long_multi_visit":
        lines.append(
            "TELLING ORDER: the date strings must appear in the note in exactly this order, first to last: "
            + " -> ".join(f"'{s}'" for s in strings)
            + f". The first dated sentence of the note is the one with '{strings[0]}'. This order is not the order in time; keep it anyway."
        )
    if spec["wording"]:
        lines.append("BINDING INSTRUCTIONS FOR THIS NOTE:")
        lines += [f"- {w}" for w in spec["wording"]]
    lines.append(CLOSING[spec["curriculum"]].format(lo=lo, hi=hi))
    return [{"role": "system", "content": WRITE_SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def readback_messages(note_date, note_text):
    return [
        {"role": "system", "content": READBACK_SYSTEM},
        {"role": "user", "content": f"Note date: {note_date}\n{note_text}"},
    ]


def _fact_for(spec, event):
    for f in spec["facts"]:
        if event and (f["type"], f["date"]) == (event["type"], event["date"]):
            return f
    return None


def _string_for(spec, date):
    for x in spec["facts"] + spec["distractors"]:
        if x["date"] == date:
            return x
    return None


def describe(spec, check, readback):
    """The precise difference, in words, for the single repair request."""
    out = []
    for failure in check["failures"]:
        name, _, value = failure.partition(":")
        if name == "missing_date_string":
            out.append(f"The date string '{value}' is missing or altered. It must appear exactly once, character for character.")
        elif name == "undeclared_date":
            out.append(f"'{value}' looks like a date or time reference that is not in the specification. Remove it (no other date, year, month, relative time or digit).")
        else:
            lo, hi = LENGTH[spec["curriculum"]][1]
            much = "short" if check["words"] < lo else "long"
            out.append(f"The note has {check['words']} words, which is too {much}. Write {lo} to {hi} words" + (": add full sentences of neutral undated content (current condition, functional ability, coping at home, general counselling)." if much == "short" else "."))
    for d in (readback or {}).get("differences", []):
        e, g = d.get("expected"), d.get("got")
        if d["class"] == "wrong_route":
            out.append(f"An independent reader understood the service as '{ROUTES.get(g, g)}' instead of '{ROUTES[e]}'. Name the service unmistakably and mention no other service as the entry point.")
        elif d["class"] == "missing_event":
            f = _fact_for(spec, e)
            out.append(f"An independent reader did not find this fact as a completed event: {f['meaning']} ({DEFINITIONS[e['type']]}) at '{f['expression']}'. State it plainly next to that date string.")
        elif d["class"] == "extra_event":
            x = _string_for(spec, g["date"])
            where = f"at '{x['expression']}' (which is: {x['meaning']})" if x else f"dated {g['date']}"
            out.append(f"An independent reader found an event that is not in the specification: '{DEFINITIONS[g['type']]}' {where}. Rewrite so that nothing there can be read as that completed cancer-pathway step.")
        elif d["class"] == "wrong_date":
            f = _fact_for(spec, e)
            out.append(f"An independent reader dated '{f['meaning']}' to {g['date']} ({g['precision']}) instead of '{f['expression']}' (= {e['date']}, {e['precision']}). Put that date string directly with that fact and no other date near it.")
        elif d["class"] == "wrong_type":
            f = _fact_for(spec, e)
            out.append(f"An independent reader read the event at '{f['expression']}' as '{DEFINITIONS[g['type']]}', but it is: {f['meaning']} ({DEFINITIONS[e['type']]}). Choose the actor and the verb so that it cannot be misread.")
        else:
            out.append("An independent reader could not extract a clear list of dated events from the note. Make each dated fact a plain statement.")
    return out


def repair_messages(spec, note_text, problems):
    base = write_messages(spec)
    return base + [
        {"role": "assistant", "content": note_text},
        {
            "role": "user",
            "content": "Your note was checked by a program and by an independent reader who saw only the note. Problems found:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nRewrite the whole note once so that every problem is fixed and every rule and fact of the specification still holds. Return only the note.",
        },
    ]


# ---- the protocol for one specification ---------------------------------------------------------


async def _attempt(spec, action, messages, chat, number):
    lo_hi, _, max_tokens = LENGTH[spec["curriculum"]]
    reply = await chat(action, messages, max_tokens, 0.65 if action == "write" else 0.4)
    note = (reply["text"] or "").strip()
    attempt = dict(
        attempt=number,
        action=action,
        note_text=note,
        code_check=code_check(spec, note),
        readback=None,
        calls=[dict(kind=action, usage=reply.get("usage", {}), seconds=reply.get("seconds"))],
    )
    if attempt["code_check"]["passed"]:  # a note that fails the code check is not read back
        reply = await chat("readback", readback_messages(spec["note_date"], note), 700, 0.0)
        attempt["calls"].append(dict(kind="readback", usage=reply.get("usage", {}), seconds=reply.get("seconds")))
        try:
            answer = parse_readback(reply["text"], spec["note_date"])
            differences = classify(truth_of(spec), answer)
            attempt["readback"] = dict(consistent=not differences, differences=differences, answer=answer)
        except ValueError as exc:
            attempt["readback"] = dict(
                consistent=False,
                differences=[{"class": "invalid_output", "expected": None, "got": str(exc)[:200]}],
                answer=None,
                raw=(reply["text"] or "")[:1500],
            )
    return attempt


def told_order(facts, note_text):
    """Whether the dated events are told in time order: 'chronological', 'out_of_order', 'unknown' or None."""
    if len(facts) < 2:
        return None
    placed = []
    for f in facts:
        hit = re.search(data_tools.date_pattern(f["expression"]), note_text)
        if not hit:
            return "unknown"  # a date string is missing from the note
        placed.append((hit.start(), f["date"], f["type"]))
    told = [x[1:] for x in sorted(placed)]
    return "chronological" if told == sorted(told) else "out_of_order"


def clean(attempt):
    return attempt["code_check"]["passed"] and bool(attempt["readback"]) and attempt["readback"]["consistent"]


def select(attempts):
    """The attempt kept as the candidate: best (code check, read-back); the later one on a tie."""
    score = lambda a: (a["code_check"]["passed"], bool(a["readback"]) and a["readback"]["consistent"], a["attempt"])  # noqa: E731
    return max(attempts, key=score)


async def run_protocol(spec, chat):
    """chat(kind, messages, max_tokens, temperature) -> {"text", "usage", "seconds"}; one repair at most."""
    attempts = [await _attempt(spec, "write", write_messages(spec), chat, 1)]
    if not clean(attempts[0]):
        problems = describe(spec, attempts[0]["code_check"], attempts[0]["readback"])
        attempts[0]["repair_request"] = problems
        attempts.append(await _attempt(spec, "repair", repair_messages(spec, attempts[0]["note_text"], problems), chat, 2))
    return attempts


def candidate(spec, attempts):
    """One line of candidates.jsonl."""
    final = select(attempts)
    truth = truth_of(spec)
    row = dict(
        id=spec["id"],
        note_text=final["note_text"],
        note_date=spec["note_date"],
        style=spec["style"],
        entry_route=truth["entry_route"],
        events=truth["events"],
        target_json=compact(truth),
        expression_json=None,
        date_forms=spec["date_forms"],
        distractors=spec["distractors"],
        kind=spec["kind"],
        focus=spec["focus"],
        writer=MODEL,
        teacher_model=MODEL,
        synthetic=True,
        round=2,
        curriculum=spec["curriculum"],
        code_check=dict(passed=final["code_check"]["passed"], failures=final["code_check"]["failures"]),
        readback=(
            dict(consistent=final["readback"]["consistent"], differences=final["readback"]["differences"])
            if final["readback"]
            else dict(consistent=None, differences=[])
        ),
        repaired=final["action"] == "repair",
        attempts=attempts,
        facts=spec["facts"],
        words=final["code_check"]["words"],
        repair_attempted=len(attempts) > 1,
        selected_attempt=final["attempt"],
        teacher_calls=sum(len(a["calls"]) for a in attempts),
        told_order=told_order(spec["facts"], final["note_text"]),
    )
    try:
        expression = data_tools.to_expression(dict(row, ground_truth=truth))
        row["expression_json"] = compact(expression)
    except Exception as exc:  # the string of a missing date cannot be ordered; keep the reason
        row["expression_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return row


# ---- teacher client -----------------------------------------------------------------------------


class Teacher:
    def __init__(self, ledger, deadline=None):
        import httpx

        self.ledger = ledger
        self.deadline = deadline
        self.client = httpx.AsyncClient(timeout=120)
        self.url = os.environ["VERDA_INFERENCE_BASE_URL"].rstrip("/")
        self.errors = collections.Counter()
        self.sent = collections.Counter()

    async def models(self):
        r = await self.client.get(self.url + "/models", headers={"Authorization": "Bearer " + os.environ["VERDA_INFERENCE_KEY"]})
        r.raise_for_status()
        return [x["id"] for x in r.json()["data"]]

    async def chat(self, kind, messages, max_tokens, temperature):
        for attempt in range(4):  # scribe/generate.py: four attempts, each one counted
            if self.deadline and time.time() > self.deadline:
                raise DeadlineReached()
            self.ledger.reserve()
            self.sent[kind] += 1
            t = time.monotonic()
            try:
                resp = await self.client.post(
                    self.url + "/chat/completions",
                    headers={"Authorization": "Bearer " + os.environ["VERDA_INFERENCE_KEY"]},
                    json=dict(
                        model=MODEL,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        chat_template_kwargs={"enable_thinking": False},
                    ),
                )
                if resp.status_code != 200:
                    raise RuntimeError("HTTP " + str(resp.status_code))
                result = resp.json()
                return dict(
                    text=result["choices"][0]["message"]["content"] or "",
                    usage=result.get("usage", {}),
                    seconds=round(time.monotonic() - t, 2),
                )
            except Exception as exc:
                self.errors[str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__] += 1
                if attempt == 3:
                    raise
                await asyncio.sleep(2**attempt + random.random())


# ---- runner -------------------------------------------------------------------------------------


def cache_path(ident):
    return CACHE / f"{ident}.json"


async def run(specs, deadline=None, command="", extra=None):
    ledger = Ledger()
    teacher = Teacher(ledger, deadline)
    sem = asyncio.Semaphore(CONCURRENCY)
    counts = collections.Counter()
    start_requests = ledger.requests
    t0 = time.monotonic()

    async def one(spec):
        if cache_path(spec["id"]).exists():
            counts["cached"] += 1
            return
        async with sem:
            if deadline and time.time() > deadline:
                counts["not_started_deadline"] += 1
                return
            try:
                attempts = await run_protocol(spec, teacher.chat)
                save(cache_path(spec["id"]), dict(id=spec["id"], curriculum=spec["curriculum"], attempts=attempts, finished_utc=now().isoformat(timespec="seconds"), **(extra or {})))
                counts["completed"] += 1
            except CapReached:
                counts["stopped_cap"] += 1
            except DeadlineReached:
                counts["stopped_deadline"] += 1
            except Exception as exc:
                counts["error:" + type(exc).__name__] += 1

    tasks = [asyncio.create_task(one(s)) for s in specs]
    timeout = None if not deadline else max(1.0, deadline - time.time() + 100)
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    counts["cancelled_at_hard_stop"] += len(pending)
    await teacher.client.aclose()
    seconds = round(time.monotonic() - t0, 1)
    metrics = dict(
        specifications=len(specs),
        outcome=dict(counts),
        teacher_requests_this_run=ledger.requests - start_requests,
        teacher_requests_ledger=ledger.requests,
        cap=ledger.cap,
        requests_by_kind=dict(teacher.sent),
        request_errors=dict(teacher.errors),
        wall_seconds=seconds,
    )
    times = OUT / "run-times.json"
    history = json.loads(times.read_text()) if times.exists() else []
    history.append(dict(ts=now().isoformat(timespec="seconds"), command=command, **metrics))
    save(times, history)
    log("teacher_run", command=command, inputs={"model": MODEL, "specs": "data/scribe/v3/teacher/specs.jsonl"}, outputs=["data/scribe/v3/teacher/cache/"], metrics=metrics)
    print(json.dumps(metrics))
    return metrics


SUPERSEDED = OUT / "superseded"


def regenerate_long(deadline=None):
    """Write again the long notes that the teacher told in time order (the curriculum asks for the opposite).

    The earlier record of such a specification moves to superseded/ and stays there; it is restored when
    the new run does not finish. Run once, after the full run, with the telling order stated explicitly.
    """
    from specs import load_specs

    todo = []
    for spec in load_specs():
        path = cache_path(spec["id"])
        if spec["curriculum"] != "long_multi_visit" or not path.exists():
            continue
        record = json.loads(path.read_text())
        if not record.get("regenerated") and told_order(spec["facts"], select(record["attempts"])["note_text"]) == "chronological":
            todo.append(spec)
    SUPERSEDED.mkdir(parents=True, exist_ok=True)
    for spec in todo:
        cache_path(spec["id"]).replace(SUPERSEDED / f"{spec['id']}.json")
    extra = dict(regenerated=True, regenerated_reason="first note was told in chronological order; telling order stated explicitly", superseded=f"data/scribe/v3/teacher/superseded/")
    metrics = asyncio.run(run(todo, deadline, "protocol.py regen-long", extra))
    restored = 0
    for spec in todo:
        if not cache_path(spec["id"]).exists():
            cache_path(spec["id"]).write_text((SUPERSEDED / f"{spec['id']}.json").read_text())
            restored += 1
    log("regenerate_long", command="protocol.py regen-long", outputs=["data/scribe/v3/teacher/superseded/"], metrics=dict(selected=len(todo), restored_unfinished=restored, teacher_requests=metrics["teacher_requests_this_run"]))
    print(json.dumps(dict(selected=len(todo), restored_unfinished=restored)))


async def preflight():
    teacher = Teacher(Ledger())
    ids = await teacher.models()
    await teacher.client.aclose()
    save(OUT / "models.json", {"ids": ids})
    metrics = {"requested_model_available": MODEL in ids, "models": len(ids)}
    log("models", command="protocol.py preflight", outputs=["data/scribe/v3/teacher/models.json"], metrics=metrics)
    print(json.dumps(metrics))
    return MODEL in ids


# ---- outputs ------------------------------------------------------------------------------------


def rate(k, n):
    return dict(numerator=k, denominator=n, rate=round(k / n, 4) if n else None)


def summarise(rows, n_specs):
    first = [r["attempts"][0] for r in rows]
    read_first = [a for a in first if a["readback"]]
    repaired = [r for r in rows if r["repair_attempted"]]
    read_final = [r for r in rows if r["readback"]["consistent"] is not None]
    return dict(
        specifications=n_specs,
        completed=len(rows),
        code_check_pass_first_attempt=rate(sum(a["code_check"]["passed"] for a in first), len(first)),
        code_check_pass_final=rate(sum(r["code_check"]["passed"] for r in rows), len(rows)),
        readback_consistent_first_attempt=rate(sum(a["readback"]["consistent"] for a in read_first), len(read_first)),
        readback_consistent_final=rate(sum(bool(r["readback"]["consistent"]) for r in read_final), len(read_final)),
        clean_first_attempt=rate(sum(clean(a) for a in first), len(first)),
        clean_final=rate(sum(r["code_check"]["passed"] and bool(r["readback"]["consistent"]) for r in rows), len(rows)),
        repair_attempted=rate(len(repaired), len(rows)),
        repair_success=rate(sum(clean(r["attempts"][1]) for r in repaired), len(repaired)),
        first_readback_difference_classes=dict(
            collections.Counter(d["class"] for a in read_first for d in a["readback"]["differences"])
        ),
        final_readback_difference_classes=dict(collections.Counter(d["class"] for r in rows for d in r["readback"]["differences"])),
        told_out_of_chronological_order=rate(
            sum(r["told_order"] == "out_of_order" for r in rows), sum(r["told_order"] in ("out_of_order", "chronological") for r in rows)
        ),
        regenerated=sum(bool(r.get("regenerated")) for r in rows),
    )


def _calls_in(directory):
    """Teacher calls recorded in the records of a directory (0 when it does not exist)."""
    total = 0
    for path in sorted(pathlib.Path(directory).glob("*.json")):
        total += sum(len(a["calls"]) for a in json.loads(path.read_text())["attempts"])
    return total


def finalise():
    from specs import load_specs

    specs = load_specs()
    rows = []
    for spec in specs:
        path = cache_path(spec["id"])
        if path.exists():
            record = json.loads(path.read_text())
            rows.append(dict(candidate(spec, record["attempts"]), regenerated=bool(record.get("regenerated"))))
    with (OUT / "candidates.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"teacher_requests": 0}
    times = json.loads((OUT / "run-times.json").read_text()) if (OUT / "run-times.json").exists() else []
    calls = collections.Counter(c["kind"] for r in rows for a in r["attempts"] for c in a["calls"])
    errors = collections.Counter()
    for t in times:
        errors.update(t.get("request_errors", {}))
    stats = dict(
        round=2,
        teacher_model=MODEL,
        generated_utc=now().isoformat(timespec="seconds"),
        synthetic=True,
        requests=dict(
            teacher_requests_ledger=ledger["teacher_requests"],
            cap=CAP,
            calls_in_completed_specifications=dict(calls),
            calls_in_completed_specifications_total=sum(calls.values()),
            requests_outside_candidates=dict(
                total=ledger["teacher_requests"] - sum(calls.values()),
                pilot1_first_prompts_notes_kept_in_pilot1_not_used=_calls_in(OUT / "pilot1" / "cache"),
                superseded_long_notes_told_in_time_order_kept_in_superseded=_calls_in(SUPERSEDED),
                lost_unrecorded_replies_of_one_aborted_pilot_run_import_error=ledger["teacher_requests"]
                - sum(calls.values())
                - _calls_in(OUT / "pilot1" / "cache")
                - _calls_in(SUPERSEDED),
            ),
            request_errors=dict(errors),
        ),
        wall_seconds=dict(total=round(sum(t["wall_seconds"] for t in times), 1), runs=[dict(command=t["command"], wall_seconds=t["wall_seconds"], teacher_requests=t["teacher_requests_this_run"]) for t in times]),
        specifications=dict(target=1600, built=len(specs), completed=len(rows), not_completed=len(specs) - len(rows)),
        definitions=dict(
            code_check="scribe/verify.py code_check: every planned date string present, nothing else looks like a date; words 60-140 for hard_standard, careful, no_event; 110-260 for long_multi_visit; 25-90 for terse",
            readback="a fresh teacher call that sees only the note, the note date and the event-type definitions; consistent = its canonical JSON equals the answer key exactly; run only on a note that passed the code check",
            repair="one rewrite when the first note failed the code check or the read-back; repair_success = the rewritten note passes the code check and its read-back equals the answer key",
            final="the kept note: the attempt with the better (code check, read-back) result, the rewrite on a tie",
            denominators="first-attempt read-back: first notes that passed the code check; final read-back: kept notes that were read back; repair_success: specifications with a repair",
            told_out_of_chronological_order="among kept notes with two or more events and every event date string present: the date strings do not appear in time order",
            regenerated="long_multi_visit specifications whose first protocol run gave a note told in time order were run through the protocol once more with the telling order stated explicitly; the earlier record is in superseded/ and is not in these rates",
        ),
        overall=summarise(rows, len(specs)),
        per_curriculum={
            name: summarise([r for r in rows if r["curriculum"] == name], sum(s["curriculum"] == name for s in specs)) for name in CURRICULA
        },
    )
    save(OUT / "stats.json", stats)
    log(
        "teacher_outputs",
        command="protocol.py finalise",
        inputs=["data/scribe/v3/teacher/cache/", "data/scribe/v3/teacher/specs.jsonl"],
        outputs=["data/scribe/v3/teacher/candidates.jsonl", "data/scribe/v3/teacher/stats.json"],
        metrics=dict(candidates=len(rows), teacher_requests_ledger=ledger["teacher_requests"], overall=stats["overall"]),
    )
    print(json.dumps(dict(candidates=len(rows), requests=ledger["teacher_requests"], overall=stats["overall"]), ensure_ascii=False))
    return stats


def _deadline(text):
    if not text:
        return None
    h, m = map(int, text.split(":"))
    d = now().replace(hour=h, minute=m, second=0, microsecond=0)
    return d.timestamp()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["preflight", "run", "finalise", "regen-long"])
    p.add_argument("--limit", type=int)
    p.add_argument("--deadline", help="UTC HH:MM today; no request is started after it")
    args = p.parse_args(argv)
    if args.command == "preflight":
        return 0 if asyncio.run(preflight()) else 1
    if args.command == "regen-long":
        regenerate_long(_deadline(args.deadline))
        return 0
    if args.command == "finalise":
        finalise()
        return 0
    from specs import load_specs

    specs = load_specs()
    if args.limit:
        specs = specs[: args.limit]
    command = "protocol.py run" + (f" --limit {args.limit}" if args.limit else "") + (f" --deadline {args.deadline}" if args.deadline else "")
    asyncio.run(run(specs, _deadline(args.deadline), command))
    return 0


if __name__ == "__main__":
    sys.exit(main())
