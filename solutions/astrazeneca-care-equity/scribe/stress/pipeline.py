"""Stress set v1 pipeline (NVIDIA_OPTIONS.md step 5). SYNTHETIC notes only; not for clinical use.

  scribe/.venv/bin/python scribe/stress/pipeline.py specs                      answer keys (no network), written once
  scribe/.venv/bin/python scribe/stress/pipeline.py write --limit 12           pilot: Nemotron writes, code gate
  scribe/.venv/bin/python scribe/stress/pipeline.py write --deadline 00:45     the rest (no request starts later)
  scribe/.venv/bin/python scribe/stress/pipeline.py gate                       TypeSafe Jev gate (current policy.json)
  scribe/.venv/bin/python scribe/stress/pipeline.py freeze                     parquet + sha256 + preregistration, once
  scribe/.venv/bin/python scribe/stress/pipeline.py status

Writer: NVIDIA Nemotron 3.5 Super VL on the event endpoint (VERDA_INFERENCE_BASE_URL), with the request style,
enable_thinking=false, retry rule and request ledger of scribe/teacher2/protocol.py, at concurrency 6 (the endpoint is
shared with another lane). The writer is told to copy every date string verbatim; a note that fails the code gate
gets at most two rewrites with the exact problems. There is NO Nemotron read-back: the Nemotron reader is one of the
systems this set will score, so it must not select the notes. Gate = code check (scribe/stress/check.py), then Jev.

Keys only in the environment of the command:
  set -a; . ~/.config/verda-inference/env; . ~/.config/typesafe/env; set +a
Writes only data/scribe/stress/ and runs/laneA-step5.jsonl (plus the shared Jev cache and ledger of scribe/judges).
No training script may read data/scribe/stress/.
"""

import argparse
import asyncio
import collections
import datetime as dt
import hashlib
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

import check as C  # noqa: E402
import phrases as P  # noqa: E402
import specs as SP  # noqa: E402
from sample import ROUTES  # noqa: E402

MODEL = "nemotron-3.5-super-vl"
PROMPT_VERSION = "stress-writer-v1"
CONCURRENCY = 6
CAP = 1300  # request attempts counted in the ledger; never reset
MAX_REPAIRS = 2
OUT = SP.OUT
CACHE = OUT / "cache"
LEDGER = OUT / "ledger.json"
REQUESTS = OUT / "requests.jsonl"
RUNLOG = ROOT / "runs/laneA-step5.jsonl"
PARQUET = OUT / "stress-v1.parquet"
PREREG = OUT / "preregistration.json"
JEV_USD_CAP = 1.00  # at most USD 1.00 of new Jev spend for this agent

WRITE_SYSTEM = (
    "You write one short SYNTHETIC Finnish clinical-style note from a specification. The patient is invented; use no names. "
    "A program checks the note and an independent reader then lists the dated cancer-pathway events in it, so the note must say exactly what the specification says: nothing missing, nothing added, every date string intact.\n"
    "RULES\n"
    "1. Finnish, in the register of a real patient record. One paragraph, no heading, no list, no line break, no Markdown, no quotation marks. Do not begin with the name of the note style.\n"
    "2. State every line of FACTS. Add no other cancer-pathway step, with or without a date: no extra contact, physician assessment, referral sent or received, specialist appointment, confirmed diagnosis, team decision or start of treatment.\n"
    "3. Every string of DATE STRINGS appears exactly once, character for character: same digits, dots, spaces, letters and inflection. "
    "Some are written in words (for example 'yhdeksän päivää sitten' or 'toissapäivänä'): keep them in words; never turn words into digits or digits into words. "
    "Do not add a year or a day to any of them. Never begin a sentence with a date string; keep it in lower case inside the sentence.\n"
    "4. No other date or time reference of any kind besides the DATE STRINGS: not the note date, no tänään, eilen, huomenna, toissapäivänä, viime viikolla, viime kuussa, "
    "no bare year, no month name, no weekday, no 'N viikon kuluttua', no duration, no time abbreviation (vk, pv, kk, vrk). No digit outside the date strings (no age, laboratory value, dose, clock time, stage).\n"
    "5. One date string belongs to one fact. The words next to each date string must make clear what happened then.\n"
    "6. Text in [square brackets] and after 'ilman päivämäärää:' is an explanation in English. Express what it means in your own Finnish; never copy it and never translate it word for word. "
    "A line marked [not a pathway event] or [has not happened yet] must be written so that nobody can read it as a completed cancer-pathway step.\n"
    "7. The note must contain one sentence that says in so many words through which service the patient entered the cancer pathway ('syöpäpolun tuloreitti'), "
    "or, when the first line is 'asiointipaikka', in which service this ordinary contact takes place. Use the Finnish name of the service as given.\n"
    "8. Reach the length with neutral undated content: how the patient feels now, functional ability, coping at home, general counselling. Never invent examinations, visits or treatments with a time.\n"
    "Return only the finished note. Never output a word count, a draft, a comment or anything in English."
)
_FILL = "Kuvaa nykyvointia, toimintakykyä, arjessa selviytymistä ja potilaan saamaa yleistä neuvontaa riittävän laajasti, yhteensä {lo}–{hi} sanaa. Älä tiivistä alle {lo} sanaan. Palauta vain valmis merkintä: ei sanamäärää, ei laskelmia, ei kommentteja, ei luonnoksia."
_TERSE = "Kirjoita sähkösanomatyyliin, yhteensä {lo}–{hi} sanaa, ei yli {hi} sanaa. Palauta vain valmis merkintä: ei sanamäärää, ei laskelmia, ei kommentteja, ei luonnoksia."
CLOSING = {
    "standard": "Kirjoita vähintään 12 kokonaista virkettä. " + _FILL,
    "no_event": "Kirjoita vähintään 11 kokonaista virkettä. " + _FILL,
    "long": "Kirjoita vähintään 22 kokonaista virkettä. " + _FILL,
    "terse": _TERSE,
    "no_event_terse": _TERSE,
}


def now():
    return dt.datetime.now(dt.timezone.utc)


def stamp():
    return now().strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(p):
    return str(pathlib.Path(p).resolve().relative_to(ROOT))


def log(step, command, inputs=None, outputs=None, metrics=None, cost_usd=0.0, status="ok"):
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(ts=stamp(), step=step, host=socket.gethostname(), command=command, inputs=inputs, outputs=outputs,
               metrics=metrics, cost_usd=cost_usd, status=status)
    with RUNLOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def save(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# ---- prompts ------------------------------------------------------------------------------------


def write_messages(spec):
    lo, hi = spec["writer_length"]
    lines = [
        f"STYLE: {spec['style']}",
        f"LENGTH: {lo} to {hi} whitespace-separated words.",
        f"NOTE DATE (only so that relative strings make sense; never print it): {spec['note_date']}",
        "FACTS:",
    ]
    lines += [f"- {x}" for x in spec["facts_fi"]]
    lines.append("DATE STRINGS (each exactly once, character for character): " + " | ".join(f"'{s}'" for s in spec["date_strings"]))
    if spec["wording"]:
        lines.append("BINDING INSTRUCTIONS FOR THIS NOTE:")
        lines += [f"- {w}" for w in spec["wording"]]
    lines.append(CLOSING[spec["curriculum"]].format(lo=lo, hi=hi))
    return [{"role": "system", "content": WRITE_SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def describe(spec, result):
    out = []
    lo, hi = spec["writer_length"]
    for failure in result["failures"]:
        name, _, value = failure.partition(":")
        if name == "missing_date_string":
            out.append(f"The date string '{value}' is missing or altered. It must appear exactly once, character for character, in lower case inside a sentence (not at its start).")
        elif name == "undeclared_date":
            out.append(f"'{value}' is a date or time reference that is not in the specification. Remove it (no other date, year, month, weekday, relative time, duration or digit).")
        elif name == "not_resolved_to_key":
            out.append(f"The date string '{value}' is not written as given. Copy it exactly.")
        else:
            much = "short" if result["words"] < lo else "long"
            out.append(f"The note has {result['words']} words, which is too {much}. Write {lo} to {hi} words" + (": add full sentences of neutral undated content (current condition, functional ability, coping at home, general counselling)." if much == "short" else ": cut neutral content, keep every fact and every date string."))
    return out


def repair_messages(spec, note_text, problems):
    return write_messages(spec) + [
        {"role": "assistant", "content": note_text},
        {
            "role": "user",
            "content": "Your note was checked by a program. Problems found:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nRewrite the whole note once so that every problem is fixed and every rule and fact of the specification still holds. Return only the note.",
        },
    ]


# ---- writer client (request style of scribe/teacher2/protocol.py) -------------------------------


class CapReached(RuntimeError):
    pass


class DeadlineReached(RuntimeError):
    pass


class Ledger:
    """Counts every request attempt before it is sent. The count only grows; there is no reset."""

    def __init__(self, path=LEDGER, cap=CAP):
        self.path = pathlib.Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"requests": 0}
        self.data["cap"] = cap
        self.data["model"] = MODEL

    @property
    def requests(self):
        return self.data["requests"]

    def reserve(self):
        if self.data["requests"] >= self.data["cap"]:
            raise CapReached(f"request cap {self.data['cap']} reached")
        self.data["requests"] += 1
        self.data["updated"] = stamp()
        save(self.path, self.data)
        return self.data["requests"]


class Writer:
    def __init__(self, ledger, deadline=None):
        import httpx

        self.ledger = ledger
        self.deadline = deadline
        self.client = httpx.AsyncClient(timeout=180)
        self.url = os.environ["VERDA_INFERENCE_BASE_URL"].rstrip("/")
        self.errors = collections.Counter()
        self.sent = collections.Counter()
        self.tokens = collections.Counter()

    def record(self, **kw):
        REQUESTS.parent.mkdir(parents=True, exist_ok=True)
        with REQUESTS.open("a") as f:
            f.write(json.dumps(dict(ts=stamp(), model=MODEL, **kw), ensure_ascii=False) + "\n")

    async def chat(self, spec_id, kind, messages, max_tokens, temperature):
        for attempt in range(4):  # scribe/generate.py and teacher2: four attempts, each one counted
            if self.deadline and time.time() > self.deadline:
                raise DeadlineReached()
            number = self.ledger.reserve()
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
                usage = result.get("usage", {})
                for k in ("prompt_tokens", "completion_tokens"):
                    self.tokens[k] += int(usage.get(k) or 0)
                seconds = round(time.monotonic() - t, 2)
                self.record(request=number, spec=spec_id, kind=kind, attempt=attempt, status="ok", seconds=seconds, usage=usage,
                            finish_reason=result["choices"][0].get("finish_reason"))
                return dict(text=result["choices"][0]["message"]["content"] or "", usage=usage, seconds=seconds,
                            finish_reason=result["choices"][0].get("finish_reason"))
            except Exception as exc:
                err = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                self.errors[err] += 1
                self.record(request=number, spec=spec_id, kind=kind, attempt=attempt, status="error", error=err,
                            seconds=round(time.monotonic() - t, 2))
                if attempt == 3:
                    raise
                await asyncio.sleep(2**attempt + random.random())


def clean_text(text):
    """The model's reply as the note: surrounding whitespace and quotation marks removed, nothing else."""
    t = (text or "").strip()
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'”":
        t = t[1:-1].strip()
    return t


async def write_one(spec, writer):
    max_tokens = SP.LENGTH[spec["curriculum"]][2]
    attempts = []
    messages = write_messages(spec)
    for number in range(1, MAX_REPAIRS + 2):
        action = "write" if number == 1 else "repair"
        reply = await writer.chat(spec["id"], action, messages, max_tokens, 0.65 if action == "write" else 0.4)
        note = clean_text(reply["text"])
        result = C.code_check(spec, note)
        attempts.append(dict(attempt=number, action=action, note_text=note, code_check=result, usage=reply["usage"],
                             seconds=reply["seconds"], finish_reason=reply.get("finish_reason")))
        if result["passed"]:
            break
        problems = describe(spec, result)
        attempts[-1]["repair_request"] = problems
        if number <= MAX_REPAIRS:
            messages = repair_messages(spec, note, problems)
    return attempts


def final_attempt(attempts):
    """The kept note: the first attempt that passed the code gate, else the last one."""
    for a in attempts:
        if a["code_check"]["passed"]:
            return a
    return attempts[-1]


def cache_path(ident):
    return CACHE / f"{ident}.json"


async def run_write(specs, deadline=None, command=""):
    ledger = Ledger()
    writer = Writer(ledger, deadline)
    sem = asyncio.Semaphore(CONCURRENCY)
    counts = collections.Counter()
    start = ledger.requests
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
                attempts = await write_one(spec, writer)
                save(cache_path(spec["id"]), dict(id=spec["id"], curriculum=spec["curriculum"], writer_model=MODEL,
                                                  prompt_version=PROMPT_VERSION, attempts=attempts, finished_utc=stamp()))
                counts["completed"] += 1
                counts["code_gate_passed"] += final_attempt(attempts)["code_check"]["passed"]
            except CapReached:
                counts["stopped_cap"] += 1
            except DeadlineReached:
                counts["stopped_deadline"] += 1
            except Exception as exc:
                counts["error:" + type(exc).__name__] += 1

    tasks = [asyncio.create_task(one(s)) for s in specs]
    timeout = None if not deadline else max(1.0, deadline - time.time() + 240)
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    counts["cancelled_at_hard_stop"] += len(pending)
    await writer.client.aclose()
    metrics = dict(
        specifications=len(specs),
        outcome=dict(counts),
        requests_this_run=ledger.requests - start,
        requests_ledger=ledger.requests,
        cap=CAP,
        requests_by_kind=dict(writer.sent),
        request_errors=dict(writer.errors),
        tokens=dict(writer.tokens),
        concurrency=CONCURRENCY,
        wall_seconds=round(time.monotonic() - t0, 1),
    )
    log("write", command, inputs=["data/scribe/stress/specs.jsonl"], outputs=["data/scribe/stress/cache/", rel(LEDGER), rel(REQUESTS)],
        metrics=metrics, cost_usd=None, status="ok" if not any(k.startswith("error") for k in counts) else "partial")
    print(json.dumps(metrics, ensure_ascii=False))
    return metrics


# ---- gate ---------------------------------------------------------------------------------------


def records():
    """(spec, cache record or None) for every specification, in spec order."""
    out = []
    for spec in SP.load_specs():
        path = cache_path(spec["id"])
        out.append((spec, json.loads(path.read_text()) if path.exists() else None))
    return out


def claim_events(spec):
    """Events shown to Jev: the precise answer key plus each vague fact at its nominal date (MONTH for 'viime kuussa')."""
    events = [dict(e) for e in spec["ground_truth"]["events"]]
    events += [dict(type=v["type"], date=v["nominal_date"], precision=v["nominal_precision"]) for v in spec["vague_events"]]
    return sorted(events, key=lambda e: (e["date"], e["type"]))


def cmd_gate(args):
    sys.path.insert(0, str(ROOT / "scribe" / "judges"))
    import core
    import run as judges_run

    C.resolver()  # refuses when the frozen resolver changed
    pairs = []
    rerun = collections.Counter()
    for spec, rec in records():
        if not rec:
            continue
        final = final_attempt(rec["attempts"])
        again = C.code_check(spec, final["note_text"])  # deterministic: the stored verdict must reproduce
        rerun["same" if again["passed"] == final["code_check"]["passed"] else "differs"] += 1
        if again["passed"]:
            pairs.append(dict(id=spec["id"], note_text=final["note_text"], note_date=spec["note_date"],
                              entry_route=spec["entry_route"], events=claim_events(spec)))
    inp = OUT / "jev-pairs.jsonl"
    inp.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs))
    usage_path = core.OUT / "usage-typesafe.json"
    before = json.loads(usage_path.read_text()) if usage_path.exists() else {"tokens": 0, "reserved_tokens": 0}
    committed_usd = (before.get("tokens", 0) + before.get("reserved_tokens", 0)) * core.TYPESAFE_USD_PER_TOKEN
    cap = committed_usd + args.max_new_usd
    summary = judges_run.run_file(inp, OUT / "jev-answers.jsonl", judges=("jev",), max_usd_typesafe=cap)
    new_tokens = summary["tokens_this_run"]["jev"]
    cost = new_tokens * core.TYPESAFE_USD_PER_TOKEN
    metrics = dict(pairs=len(pairs), rule=summary["rule"], passed=summary["passed"], errors=summary["errors"], stats=summary["stats"],
                   jev_tokens_this_run=new_tokens, jev_usd_this_run=round(cost, 6), ledger_cap_usd=round(cap, 6),
                   code_check_reproduced=dict(rerun), policy=rel(core.POLICY), policy_sha256=sha256_file(core.POLICY),
                   seconds=summary["seconds"])
    log("jev_gate", "scribe/.venv/bin/python scribe/stress/pipeline.py gate", inputs=[rel(inp), rel(core.POLICY)],
        outputs=["data/scribe/stress/jev-answers.jsonl", "data/scribe/v3/judges/cache/jev/", "data/scribe/v3/judges/usage-typesafe.json"],
        metrics=metrics, cost_usd=round(cost, 6), status="ok" if not any(summary["errors"].values()) else "partial")
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


# ---- freeze -------------------------------------------------------------------------------------


def expression_of(spec, note_text):
    """Expression-format target (scribe/v2 format) for a note without vague facts; events in order of appearance."""
    import data_tools

    keyed = []
    for i, f in enumerate(sorted(spec["facts"], key=lambda f: (f["date"], f["type"]))):
        if f["family"] in P.STANDARD_FORMS:
            date = data_tools.parse_expression(f["expression"], spec["note_date"])
        elif f["family"] == "heldout_toissa":
            date = {"kind": "DAYS_AGO", "n": 2}
        elif f["family"] == "heldout_days_word":
            date = {"kind": "DAYS_AGO", "n": P.heldout_days(f["expression"])}
        elif f["family"] == "heldout_weeks_word":
            date = {"kind": "WEEKS_AGO", "n": P.heldout_days(f["expression"]) // 7}
        else:
            return None
        hit = re.search(C.date_pattern(f["expression"]), note_text)
        keyed.append((hit.start() if hit else len(note_text) + 1, i, {"type": f["type"], "date": date}))
    obj = {"entry_route": spec["entry_route"], "events": [e for _, _, e in sorted(keyed, key=lambda k: k[:2])]}
    if data_tools.resolve_expression(obj, spec["note_date"]) != spec["ground_truth"]:
        raise AssertionError(f"expression round trip failed for {spec['id']}")
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def gate_rows():
    answers = {}
    path = OUT / "jev-answers.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                answers[row["id"]] = row
    rows, reasons = [], collections.Counter()
    for spec, rec in records():
        if not rec:
            reasons["not_written"] += 1
            continue
        final = final_attempt(rec["attempts"])
        cc = C.code_check(spec, final["note_text"])
        ans = answers.get(spec["id"])
        jev = (ans or {}).get("judges", {}).get("jev") or {}
        jev_pass = bool(ans and ans.get("pass"))
        if not cc["passed"]:
            stage = "code_check"
        elif not ans:
            stage = "jev_missing"
        elif jev.get("error"):
            stage = "jev_error"
        elif not jev_pass:
            stage = "jev"
        else:
            stage = None
        reasons[stage or "accepted"] += 1
        rows.append((spec, rec, final, cc, ans, jev, stage))
    return rows, reasons


def to_row(spec, rec, final, cc, ans, jev, stage):
    truth = spec["ground_truth"]
    fams = [f["family"] for f in spec["facts"]]
    return dict(
        id=spec["id"],
        split="stress",
        set=spec["set"],
        note_text=final["note_text"],
        note_date=spec["note_date"],
        style=spec["style"],
        entry_route=spec["entry_route"],
        events=truth["events"],
        target_json=json.dumps(truth, ensure_ascii=False, separators=(",", ":")),
        expression_json=expression_of(spec, final["note_text"]) if (stage is None and not spec["has_vague"]) else None,
        vague_json=json.dumps(spec["vague_events"], ensure_ascii=False, separators=(",", ":")),
        date_forms=fams,
        heldout_families=sorted({f for f in fams if f in P.HELDOUT_FAMILIES}),
        facts_json=json.dumps(spec["facts"], ensure_ascii=False, separators=(",", ":")),
        distractors_json=json.dumps(spec["distractors"], ensure_ascii=False, separators=(",", ":")),
        kind=spec["kind"],
        curriculum=spec["curriculum"],
        phrase_plan=spec["phrase_plan"],
        focus=spec["focus"],
        has_heldout=spec["has_heldout"],
        has_vague=spec["has_vague"],
        distractor_heldout=bool(spec.get("distractor_heldout")),
        n_events=len(truth["events"]),
        words=cc["words"],
        writer=MODEL,
        writer_prompt_version=rec.get("prompt_version"),
        writer_attempts=len(rec["attempts"]),
        repaired=final["attempt"] > 1,
        code_check_passed=cc["passed"],
        code_check_failures_json=json.dumps(cc["failures"], ensure_ascii=False),
        resolution_json=json.dumps(cc["resolution"], ensure_ascii=False, separators=(",", ":")),
        jev_pass=bool(ans and ans.get("pass")),
        jev_probabilities_json=json.dumps(jev.get("probabilities") or {}, ensure_ascii=False, sort_keys=True),
        jev_route_choice=jev.get("route_choice"),
        reject_stage=stage,
        accepted=stage is None,
        synthetic=True,
    )


def slice_counts(rows):
    c = collections.Counter()
    for r in rows:
        c["notes"] += 1
        c["with_events"] += r["n_events"] > 0 or r["has_vague"]
        c["heldout_slice (>=1 held-out fact, no vague fact)"] += r["has_heldout"] and not r["has_vague"]
        c["standard_slice (>=1 event, six standard forms only)"] += r["kind"] == "standard" and not r["has_heldout"] and not r["has_vague"]
        c["vague_slice"] += r["has_vague"]
        c["no_event"] += r["kind"] == "no_event"
        c["no_event_with_heldout_distractor"] += r["distractor_heldout"]
        c["curriculum:" + r["curriculum"]] += 1
        for f in r["heldout_families"]:
            c["heldout_family:" + f] += 1
    return dict(c)


def preregistration(rows, sha, freeze_rec, freeze_sha, created):
    return dict(
        schema="scribe-stress-preregistration-v1",
        frozen=True,
        frozen_utc=created,
        synthetic=True,
        set=SP.SET,
        file=rel(PARQUET),
        sha256=sha,
        rows=len(rows),
        slices=slice_counts(rows),
        purpose="Primary test set of NVIDIA_OPTIONS.md step 8: does a model that copies the date phrase while code counts (arm B) beat a "
        "careful Finnish rule (arm A') on date phrasings that no training note and no resolver lexicon contains?",
        written_before_any_system_saw_the_set=(
            "This file, the parquet and its sha256 were written before any scored system (A, A', B, C or the Nemotron reader) saw a stress note. "
            "Only the writer (Nemotron 3.5 Super VL, which wrote the notes) and the TypeSafe Jev gate saw them. No Nemotron read-back was used "
            "to select notes."
        ),
        resolver_freeze=dict(file=rel(C.FREEZE), sha256=freeze_sha, frozen_at_utc=freeze_rec["frozen_at_utc"], files=freeze_rec["files"]),
        systems={
            "A": "Gemma 3 270M, absolute-date format (step 3 control arm A on MLX); if step 3 does not produce arm A before step 8, the stored "
            "C-270m-all-v2data adapter is used instead, and which one is recorded before scoring. Post-processing: frozen resolver arm A "
            "(scribe/v3/resolve.py repair, digits only).",
            "A'": "The same model output as A, post-processed by frozen resolver arm A' (digits plus lexicon fi-relative-lexicon-v1). "
            "A and A' share one generation; they differ only in the frozen rule.",
            "B": "Gemma 3 270M, expression format with training-split phrase augmentation (step 3 arm B; number words 1-6, 'eilen', "
            "'viikko sitten'); dates computed by scribe/v2/data_tools.resolve_expression. No lexicon.",
            "C": "Gemma 3 1B, expression format (step 3 arm C), scored only if it was trained because B looked promising on validation.",
            "nemotron_reader": "Nemotron 3.5 Super VL as the cascade's escalation reader, the prompt version Lane B selects on validation in "
            "step 4 (its prompt sha256 recorded before scoring). Secondary system, not in the primary comparison. Caveat: the same model "
            "wrote these notes, so its score here is optimistic.",
        },
        endpoint="Note-level exact match: the canonical answer (entry route plus every event with type, date and precision) after the "
        "system's own date code equals the answer key (target_json). An output that cannot be parsed or validated is wrong.",
        primary=dict(
            comparison="B against A'",
            slice="heldout: notes with at least one pathway fact in a held-out phrasing (number words 7-12 or 'toissapäivänä') and no vague fact",
            test="exact two-sided McNemar test on paired note-level exact match",
            success="B - A' >= 0.10 (10 points) with McNemar p < 0.01 on the heldout slice, AND B >= 0.85 exact match on the standard slice",
            if_A_prime_wins="the headline is: a careful Finnish rule beats the learned reader on these phrasings",
            source="NVIDIA_OPTIONS.md section 3.2, step 8 (success criteria written before the set existed)",
        ),
        secondary=[
            "Exact match with Wilson 95% intervals for every system on: heldout, standard, no_event (and no_event with a held-out distractor), by length curriculum (standard, terse, long) and by held-out family.",
            "A against A' on the heldout slice (expected: equal, because the frozen lexicon excludes these phrasings by design).",
            "Interval error in days per event where the type matches; parse failures.",
            "Cascade (step 8): at thresholds chosen on validation only, the share of notes pre-filled correctly for one-click confirmation and the error among them; target at least 60% with 5% or less error (against 263/700 today). A person confirms every note.",
        ],
        vague_scoring=dict(
            slice="vague: notes with one pathway fact phrased vaguely ('pari viikkoa sitten', 'viime kuussa', 'muutama päivä sitten', 'kuukausi sitten', 'pari kuukautta sitten'); correct outcome: send to a person",
            outcomes={
                "sent_to_person": "the system flags the phrase or the note for a person (for A': resolve() needs_person contains the phrase)",
                "invented_precise_date": "not flagged, and the output has an event of the vague fact's type with DAY precision",
                "month_without_flag": "not flagged, and the event is output with MONTH precision",
                "dropped": "not flagged, and no event of that type is output",
            },
            precise_part="exact match of the other (precise) events and the route, reported separately",
            question="does a system invent a precise date where the note gives none?",
        ),
        multiplicity="One primary comparison (B against A' on the heldout slice); everything else is descriptive and reported with Wilson intervals, without a success claim.",
        fallback=f"Not used: {len(rows)} notes passed both gates (kill threshold 150), so no code-rendered phrasing shift of validation notes was built.",
        scored_once="Each system is scored on this set exactly once, after its configuration is frozen on validation. No prompt, threshold, "
        "training or selection choice may use this set. A rerun is allowed only to repair a crash before any score is read, and it is logged.",
        not_for_training="No training or augmentation script may read data/scribe/stress/. The held-out phrasings must stay out of every training split.",
        construction=dict(
            answer_keys="scribe/stress/specs.py: scribe/sample.py with new seeds (from 28261114), last fact(s) re-phrased; ids checked against "
            "data/scribe/dataset-v1, v2/dataset, v3/dataset and the v3 teacher specs (0 collisions)",
            writer=f"{MODEL} on the event endpoint, prompt {PROMPT_VERSION}, enable_thinking off, at most {MAX_REPAIRS} rewrites after a failed code check",
            code_gate="scribe/stress/check.py: every date string verbatim; no undeclared date or time reference; word bounds; standard forms resolve to the key "
            "with the frozen resolver, held-out phrasings with the generator's own arithmetic",
            jev_gate="scribe/judges (rule and thresholds of data/scribe/v3/judges/policy.json, question set v2); vague facts asked at their nominal date",
        ),
        limitations=[
            "SYNTHETIC notes from one writer model (Nemotron 3.5 Super VL); the students were trained mostly on Nemotron-written notes, so writer style is not new.",
            "The Jev gate and the code gate select notes that state the key clearly; real notes are messier.",
            "Finnish only. No Swedish slice was built.",
        ],
    )


def cmd_freeze(args):
    import pyarrow as pa
    import pyarrow.parquet as pq

    if PARQUET.exists() or PREREG.exists():
        raise SystemExit("stress-v1.parquet or preregistration.json exists; the freeze is written once")
    mod, freeze_rec, freeze_sha = C.resolver()
    rows_all, reasons = gate_rows()
    built = [to_row(*r) for r in rows_all]
    accepted = sorted([r for r in built if r["accepted"]], key=lambda r: r["id"])
    rejected = sorted([r for r in built if not r["accepted"]], key=lambda r: r["id"])
    if len(accepted) < args.min_rows:
        raise SystemExit(f"only {len(accepted)} accepted notes (< {args.min_rows}); not freezing")
    pq.write_table(pa.Table.from_pylist(accepted), PARQUET)
    sha = sha256_file(PARQUET)
    (OUT / "stress-v1.parquet.sha256").write_text(f"{sha}  stress-v1.parquet\n")
    created = stamp()
    prereg = preregistration(accepted, sha, freeze_rec, freeze_sha, created)
    PREREG.write_text(json.dumps(prereg, ensure_ascii=False, indent=1) + "\n")
    if rejected:
        pq.write_table(pa.Table.from_pylist(rejected), OUT / "rejected-v1.parquet")
    by = lambda rows, key: dict(collections.Counter(r[key] for r in rows))  # noqa: E731
    summary = dict(
        set=SP.SET,
        created_utc=created,
        synthetic=True,
        specifications=len(SP.load_specs()),
        written=len(built),
        accepted=len(accepted),
        outcome=dict(reasons),
        accepted_by_curriculum=by(accepted, "curriculum"),
        accepted_by_phrase_plan=by(accepted, "phrase_plan"),
        rejected_by_phrase_plan_and_stage=dict(collections.Counter(f"{r['phrase_plan']}/{r['reject_stage']}" for r in rejected)),
        accepted_with_heldout_fact=sum(r["has_heldout"] for r in accepted),
        accepted_heldout_share=round(sum(r["has_heldout"] for r in accepted) / len(accepted), 4) if accepted else None,
        accepted_repaired=sum(r["repaired"] for r in accepted),
        slices=slice_counts(accepted),
        words=dict(min=min(r["words"] for r in accepted), max=max(r["words"] for r in accepted)) if accepted else None,
        frozen_aprime_on_heldout_strings=dict(collections.Counter(
            ("resolves" if x["frozen_aprime_resolves"] else "does_not_resolve")
            for r in accepted for x in json.loads(r["resolution_json"]) if x["family"] in P.HELDOUT_FAMILIES)),
        frozen_aprime_on_vague_strings=dict(collections.Counter(
            ("to_person" if x["frozen_aprime_to_person"] else "not_flagged")
            for r in accepted for x in json.loads(r["resolution_json"]) if x["family"] == "vague")),
        parquet=rel(PARQUET),
        sha256=sha,
        preregistration=rel(PREREG),
    )
    save(OUT / "gate-summary.json", summary)
    log("freeze", "scribe/.venv/bin/python scribe/stress/pipeline.py freeze", inputs=["data/scribe/stress/specs.jsonl", "data/scribe/stress/cache/",
        "data/scribe/stress/jev-answers.jsonl", rel(C.FREEZE)], outputs=[rel(PARQUET), "data/scribe/stress/stress-v1.parquet.sha256", rel(PREREG),
        "data/scribe/stress/rejected-v1.parquet", "data/scribe/stress/gate-summary.json"],
        metrics={k: summary[k] for k in ("specifications", "written", "accepted", "outcome", "accepted_heldout_share", "sha256")}, cost_usd=0.0)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


# ---- other commands -----------------------------------------------------------------------------


def cmd_specs(args):
    specs, summary = SP.build_all()
    SP.write_specs(specs, summary)
    log("specs", "scribe/.venv/bin/python scribe/stress/pipeline.py specs", inputs=summary["ids_checked_against"]["files"] + ["scribe/sample.py", "data/scribe/v2/slices/_build_slices.py"],
        outputs=["data/scribe/stress/specs.jsonl", "data/scribe/stress/specs-summary.json"],
        metrics={k: summary[k] for k in ("specifications", "built", "phrase_plan", "notes_with_heldout_fact", "notes_with_vague_fact", "no_event_notes", "fact_families")}
        | dict(id_collisions=0, ids_checked=summary["ids_checked_against"]["ids"], seeds=summary["seeds"]))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("builders", "ids_checked_against")}, ensure_ascii=False))


def _deadline(text):
    if not text:
        return None
    h, m = map(int, text.split(":"))
    d = now().replace(hour=h, minute=m, second=0, microsecond=0)
    if d < now() - dt.timedelta(hours=6):  # a time after midnight UTC
        d += dt.timedelta(days=1)
    return d.timestamp()


def cmd_write(args):
    C.resolver()
    specs = SP.load_specs()
    if args.limit:
        specs = specs[: args.limit]
    command = "scribe/.venv/bin/python scribe/stress/pipeline.py write" + (f" --limit {args.limit}" if args.limit else "") + (f" --deadline {args.deadline}" if args.deadline else "")
    asyncio.run(run_write(specs, _deadline(args.deadline), command))


def cmd_status(args):
    rows = records()
    done = [(s, r) for s, r in rows if r]
    passed = [s for s, r in done if final_attempt(r["attempts"])["code_check"]["passed"]]
    fails = collections.Counter(f.split(":")[0] for s, r in done for f in final_attempt(r["attempts"])["code_check"]["failures"])
    first = collections.Counter(f.split(":")[0] for s, r in done for f in r["attempts"][0]["code_check"]["failures"])
    print(json.dumps(dict(specs=len(rows), written=len(done), code_gate_passed=len(passed),
                          passed_by_plan=dict(collections.Counter(s["phrase_plan"] for s in passed)),
                          written_by_plan=dict(collections.Counter(s["phrase_plan"] for s, _ in done)),
                          final_failure_kinds=dict(fails), first_attempt_failure_kinds=dict(first),
                          ledger=json.loads(LEDGER.read_text()) if LEDGER.exists() else None), ensure_ascii=False, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("specs").set_defaults(func=cmd_specs)
    w = sub.add_parser("write")
    w.add_argument("--limit", type=int)
    w.add_argument("--deadline", help="UTC HH:MM; no request starts after it")
    w.set_defaults(func=cmd_write)
    g = sub.add_parser("gate")
    g.add_argument("--max-new-usd", type=float, default=0.50)
    g.set_defaults(func=cmd_gate)
    f = sub.add_parser("freeze")
    f.add_argument("--min-rows", type=int, default=1)
    f.set_defaults(func=cmd_freeze)
    sub.add_parser("status").set_defaults(func=cmd_status)
    args = p.parse_args(argv)
    if getattr(args, "max_new_usd", 0) > JEV_USD_CAP:
        raise SystemExit(f"--max-new-usd is capped at {JEV_USD_CAP}")
    args.func(args)


if __name__ == "__main__":
    main()
