"""Two narrow judges for a (note, claimed answer) pair: TypeSafe System One "Jev" and OpenAI Decisions.

Both are asked THE SAME questions about the same note:
  event_<i>  yes/no  the note states that <definition of the event type> happened on <ISO date>
  unlisted   yes/no  the note states a dated cancer-pathway event that is not in the claimed list
  route      choice  entry route, one of five fixed values

Answers are cached on disk by a hash of the request, so nothing is paid twice. Every request is
reserved against a per-service token ledger before it is sent; a failed attempt keeps its reservation.
A refused, failed or malformed answer has no probabilities and can never count as a pass.
All text is synthetic. Nothing here is for clinical use.
"""

import asyncio
import datetime as dt
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scribe"))

from sample import ROUTES, TYPES  # noqa: E402  (version 1, read only)
from verify import ENGLISH  # noqa: E402

OUT = ROOT / "data/scribe/v3/judges"
RUNLOG = ROOT / "runs/judges.jsonl"
POLICY = OUT / "policy.json"

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
TYPESAFE_MODEL = "jev-latest"
TYPESAFE_USD_PER_TOKEN = 0.042 / 1e6  # owner's price: USD 0.042 per million tokens
OPENAI_URL = "https://api.openai.com/v1/decisions"
OPENAI_MODEL = "gpt-6-luna"

ROUTE_DESCRIPTIONS = {
    "PUBLIC_PRIMARY": "public primary health care, a health centre (julkinen perusterveydenhuolto, terveyskeskus)",
    "OCCUPATIONAL": "occupational health care (työterveyshuolto)",
    "PRIVATE": "private health care (yksityinen terveydenhuolto, yksityinen lääkäriasema)",
    "EMERGENCY": "emergency department (päivystys)",
    "SCREENING": "cancer screening programme (seulonta)",
}
assert set(ROUTE_DESCRIPTIONS) == set(ROUTES)

PATHWAY_EVENTS = (
    "Cancer-pathway events are: reported onset of cancer-related symptoms, first contact with healthcare about "
    "cancer-related symptoms, physician assessment on the cancer pathway, cancer referral sent, cancer referral "
    "received, cancer specialist visit, cancer diagnosis confirmed, multidisciplinary team treatment decision and "
    "cancer treatment started."
)


class BudgetStop(RuntimeError):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def log(step, **kw):
    """One JSON line per executed step in runs/judges.jsonl."""
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(ts=now(), step=step, host=socket.gethostname(), command=kw.pop("command", " ".join(sys.argv)))
    for k in ("inputs", "outputs", "metrics", "cost_usd", "status"):
        rec[k] = kw.pop(k, None)
    rec.update(kw)
    with RUNLOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---- the questions (identical content for both judges) ------------------------------------------


def when(event):
    if event.get("precision", "DAY") == "MONTH":
        return f"in the calendar month {event['date'][:7]} (the note gives the month, not an exact day)"
    return f"on {event['date']}"


def offset_hint(note_date, event):
    """Question set v2: code does the date arithmetic and tells the judge the offset from the note date."""
    if event.get("precision", "DAY") != "DAY":
        return ""
    n = (dt.date.fromisoformat(note_date) - dt.date.fromisoformat(event["date"])).days
    if n == 0:
        return " (that is the note date itself)"
    if n < 0:
        return f" (that is {-n} days after the note date {note_date})"
    w, d = divmod(n, 7)
    weeks = (f", i.e. {w} weeks" + (f" and {d} days" if d else "")) if w else ""
    return f" (that is {n} days{weeks} before the note date {note_date})"


def build_questions(note_date, events, question_set="v1"):
    """Ordered list of {name, kind, text[, choices]}. The claimed route is not shown to the judge.
    v1: the questions as specified. v2: the same, plus the day offset of each DAY-precision date."""
    if question_set not in ("v1", "v2"):
        raise ValueError(question_set)
    qs = []
    for i, e in enumerate(events):
        hint = offset_hint(note_date, e) if question_set == "v2" else ""
        qs.append(
            dict(
                name=f"event_{i}",
                kind="predicate",
                text=f"The note states that {ENGLISH[e['type']]} ({e['type']}) happened {when(e)}{hint}; relative "
                f"expressions (days, weeks or months ago, a date without a year) are resolved against the note "
                f"date {note_date}. A plan, a future appointment, a negation, another kind of event or another "
                f"date does not count. Is this statement true?",
            )
        )
    listing = "; ".join(f"{ENGLISH[e['type']]} ({e['type']}) {when(e)}" for e in events) or "(the list is empty)"
    qs.append(
        dict(
            name="unlisted",
            kind="predicate",
            text=f"The note states a dated cancer-pathway event that is not in this list: {listing}. "
            f"{PATHWAY_EVENTS} An event is not in the list when its type or its date differs from every list "
            f"entry; relative expressions are resolved against the note date {note_date}. Birth dates, care "
            f"unrelated to cancer and future appointments do not count. Is this statement true?",
        )
    )
    qs.append(
        dict(
            name="route",
            kind="choice",
            text="Through which entry route did the patient enter the cancer pathway according to the note?",
            choices=ROUTE_DESCRIPTIONS,
        )
    )
    return qs


def jev_body(note_text, note_date, events, question_set="v1"):
    questions = {}
    for q in build_questions(note_date, events, question_set):
        questions[q["name"]] = (
            {"type": "noul", "instructions": q["text"]}
            if q["kind"] == "predicate"
            else {"type": "choice", "instructions": q["text"], "criteria": dict(q["choices"])}
        )
    return dict(model=TYPESAFE_MODEL, state={"note_date": note_date, "note": note_text}, questions=questions)


def decisions_body(note_text, note_date, events):
    questions = []
    for q in build_questions(note_date, events):
        item = {"type": q["kind"], "name": q["name"], "instructions": q["text"]}
        if q["kind"] == "choice":
            item["choices"] = [{"value": k, "description": v} for k, v in q["choices"].items()]
        questions.append(item)
    return dict(model=OPENAI_MODEL, input=f"Note date: {note_date}\n\nNote:\n{note_text}", questions=questions)


def request_hash(body):
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# ---- parsing: anything unexpected raises, and the caller records an error -----------------------


def _prob(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 <= x <= 1:
        raise ValueError("probability out of range or not a number")
    return float(x)


def parse_jev(result, names):
    answers = result["answers"]
    if set(answers) != set(names):
        raise ValueError("answer names differ from question names")
    probs, dist = {}, {}
    for n in names:
        a = answers[n]
        if n == "route":
            dist = {k: _prob(v) for k, v in a["probabilities"].items()}
            if set(dist) != set(ROUTES) or a["choice"] not in ROUTES:
                raise ValueError("route answer is not one of the fixed choices")
            choice = a["choice"]
        else:
            probs[n] = _prob(a["noul"])
    usage = result["usage"]
    return probs, choice, dist, dict(input_tokens=int(usage["input_tokens"]), output_tokens=int(usage["output_tokens"]))


def parse_decisions(result, names):
    answers = {a["name"]: a for a in result["answers"]}
    if set(answers) != set(names) or len(result["answers"]) != len(names):
        raise ValueError("answer names differ from question names")
    probs, dist = {}, {}
    for n in names:
        a = answers[n]
        if a.get("type") == "refusal":
            raise ValueError(f"refusal on {n}")
        if n == "route":
            if a.get("type") != "choice":
                raise ValueError("route answer is not a choice")
            dist = {p["value"]: _prob(p["probability"]) for p in a["probabilities"]}
            if set(dist) != set(ROUTES) or a["choice"] not in ROUTES:
                raise ValueError("route answer is not one of the fixed choices")
            choice = a["choice"]
        else:
            if a.get("type") != "predicate":
                raise ValueError(f"{n} answer is not a predicate")
            probs[n] = _prob(a["probability"])
    usage = result["usage"]
    inp = int(usage["input_tokens"])
    out = int(usage.get("output_tokens", 0))
    if isinstance(usage.get("total_tokens"), int) and usage["total_tokens"] > inp + out:
        out = usage["total_tokens"] - inp  # count everything the provider counted
    return probs, choice, dist, dict(input_tokens=inp, output_tokens=out)


# ---- ledger and cache ---------------------------------------------------------------------------


class Ledger:
    """Token ledger with a hard limit. A request is reserved before it is sent; a failed attempt keeps
    its reservation because it may have been billed."""

    def __init__(self, path, limit_tokens, reserve_tokens, usd_per_token=None):
        self.path, self.limit, self.reserve, self.usd_per_token = Path(path), limit_tokens, reserve_tokens, usd_per_token
        self.d = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else dict(requests=0, tokens=0, input_tokens=0, output_tokens=0, reserved_tokens=0, failed_attempts=0)
        )

    def _save(self):
        self.d["updated"] = now()
        if self.usd_per_token is not None:
            self.d["cost_usd"] = self.d["tokens"] * self.usd_per_token
            self.d["cost_usd_counting_reservations"] = (self.d["tokens"] + self.d["reserved_tokens"]) * self.usd_per_token
        save_json(self.path, self.d)

    def committed(self):
        return self.d["tokens"] + self.d["reserved_tokens"]

    def open(self):
        if self.committed() + self.reserve > self.limit:
            raise BudgetStop(f"budget reached: {self.committed()} of {int(self.limit)} tokens committed")
        self.d["reserved_tokens"] += self.reserve
        self.d["requests"] += 1
        self._save()

    def settle(self, usage):
        self.d["input_tokens"] += usage["input_tokens"]
        self.d["output_tokens"] += usage["output_tokens"]
        self.d["tokens"] += usage["input_tokens"] + usage["output_tokens"]
        self.d["reserved_tokens"] -= self.reserve
        self._save()

    def fail(self):
        self.d["failed_attempts"] += 1
        self._save()


async def httpx_post(url, headers, body, _client={}):
    """Default transport: (status code, parsed JSON or None). One shared client per event loop."""
    import httpx

    loop = asyncio.get_running_loop()
    if _client.get("loop") is not loop:
        _client.update(loop=loop, client=httpx.AsyncClient(timeout=120))
    r = await _client["client"].post(url, headers=headers, json=body)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


class Judges:
    """Both judges behind one cache, two ledgers and an injectable transport (tests pass a fake `post`)."""

    def __init__(self, out_dir=OUT, post=None, max_usd_typesafe=2.0, max_tokens_openai=500_000, concurrency=None, env=None):
        self.out = Path(out_dir)
        self.post = post or httpx_post
        self.env = os.environ if env is None else env
        c = dict(jev=12, decisions=8, **(concurrency or {}))
        self.sem = {k: asyncio.Semaphore(v) for k, v in c.items()}
        self.ledger = dict(
            jev=Ledger(self.out / "usage-typesafe.json", max_usd_typesafe / TYPESAFE_USD_PER_TOKEN, 20_000, TYPESAFE_USD_PER_TOKEN),
            decisions=Ledger(self.out / "usage-openai.json", max_tokens_openai, 3_000),
        )
        self._locks = {}
        self.stats = dict(jev=dict(cached=0, paid=0, errors=0, budget_stop=0), decisions=dict(cached=0, paid=0, errors=0, budget_stop=0))

    def _cache(self, judge, h):
        return self.out / "cache" / judge / f"{h}.json"

    async def _ask(self, judge, body, key_name, url, parse, claimed_route, n_events, question_set="v1"):
        names = [f"event_{i}" for i in range(n_events)] + ["unlisted", "route"]
        h = request_hash(body)
        base = dict(judge=judge, model=body["model"], question_set=question_set, request_sha256=h, n_events=n_events, claimed_route=claimed_route)
        # one lock per request hash: two identical requests in flight at once are paid once
        async with self._locks.setdefault((judge, h), asyncio.Lock()):
            return await self._ask_locked(judge, body, key_name, url, parse, names, base, h)

    async def _ask_locked(self, judge, body, key_name, url, parse, names, base, h):
        path = self._cache(judge, h)
        if path.exists():
            rec = json.loads(path.read_text())
            self.stats[judge]["cached"] += 1
            return self._finish(base, rec, cached=True)
        if not self.env.get(key_name):
            self.stats[judge]["errors"] += 1
            return dict(base, error="NOT_CONFIGURED", probabilities={}, cached=False)
        async with self.sem[judge]:
            try:
                self.ledger[judge].open()
            except BudgetStop as e:
                self.stats[judge]["budget_stop"] += 1
                return dict(base, error="BUDGET_STOP: " + str(e), probabilities={}, cached=False)
            t = time.monotonic()
            try:
                status, result = await self.post(url, {"Authorization": "Bearer " + self.env[key_name]}, body)
                latency = time.monotonic() - t
                if status != 200:
                    detail = ""
                    if isinstance(result, dict) and isinstance(result.get("error"), dict):
                        detail = " " + str(result["error"].get("code") or result["error"].get("type") or "")
                    raise RuntimeError(f"HTTP {status}{detail}".strip())
                probs, choice, dist, usage = parse(result, names)
            except Exception as e:  # never retried automatically; the reservation stays
                self.ledger[judge].fail()
                self.stats[judge]["errors"] += 1
                msg = str(e) if isinstance(e, (RuntimeError, ValueError, KeyError)) else type(e).__name__
                return dict(base, error=f"{type(e).__name__}: {msg}"[:200], probabilities={}, cached=False)
            self.ledger[judge].settle(usage)
            self.stats[judge]["paid"] += 1
            rec = dict(probabilities=probs, route_choice=choice, route_distribution=dist, usage=usage, latency_s=round(latency, 3), ts=now())
            save_json(path, rec)
            return self._finish(base, rec, cached=False)

    @staticmethod
    def _finish(base, rec, cached):
        probs = dict(rec["probabilities"])
        probs["route"] = rec["route_distribution"].get(base["claimed_route"], 0.0)  # probability of the CLAIMED route
        return dict(
            base,
            error=None,
            probabilities=probs,
            route_choice=rec["route_choice"],
            route_distribution=rec["route_distribution"],
            usage=rec["usage"],
            latency_s=rec["latency_s"],
            cached=cached,
        )

    async def jev(self, note_text, note_date, entry_route, events, question_set="v1"):
        body = jev_body(note_text, note_date, events, question_set)
        return await self._ask("jev", body, "TYPESAFE_API_KEY", TYPESAFE_URL, parse_jev, entry_route, len(events), question_set)

    async def jev_hint(self, note_text, note_date, entry_route, events):
        """Jev with question set v2 (day offsets computed by code). Same ledger and cache as `jev`."""
        return await self.jev(note_text, note_date, entry_route, events, question_set="v2")

    async def decisions(self, note_text, note_date, entry_route, events):
        body = decisions_body(note_text, note_date, events)
        return await self._ask("decisions", body, "OPENAI_API_KEY", OPENAI_URL, parse_decisions, entry_route, len(events))


def judge_jev(note_text, note_date, entry_route, events, **kw):
    """Synchronous convenience wrapper: per-question probabilities, token usage and latency from Jev."""
    return asyncio.run(Judges(**kw).jev(note_text, note_date, entry_route, events))


def judge_decisions(note_text, note_date, entry_route, events, **kw):
    """Synchronous convenience wrapper: per-question probabilities, token usage and latency from Decisions."""
    return asyncio.run(Judges(**kw).decisions(note_text, note_date, entry_route, events))


# ---- acceptance ---------------------------------------------------------------------------------


def judge_pass(res, th):
    """True only for a complete, well-formed answer that clears every threshold."""
    if not isinstance(res, dict) or res.get("error") or not isinstance(th, dict):
        return False
    p, n = res.get("probabilities") or {}, res.get("n_events")
    if not isinstance(n, int):
        return False
    need = [f"event_{i}" for i in range(n)] + ["unlisted", "route"]
    for k in need:
        v = p.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            return False
    if res.get("route_choice") != res.get("claimed_route"):
        return False
    return (
        all(p[f"event_{i}"] >= th["event_min"] for i in range(n))
        and p["unlisted"] < th["unlisted_max"]
        and p["route"] >= th["route_min"]
    )


def rule_pass(rule, results, thresholds):
    """rule: 'jev' | 'decisions' | 'both' | 'either' (| 'jev_hint' inside the benchmark). A missing judge never passes."""
    j = judge_pass(results.get("jev"), thresholds.get("jev"))
    d = judge_pass(results.get("decisions"), thresholds.get("decisions"))
    h = judge_pass(results.get("jev_hint"), thresholds.get("jev_hint"))
    return {"jev": j, "decisions": d, "both": j and d, "either": j or d, "jev_hint": h}[rule]


def load_policy(path=POLICY):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None
