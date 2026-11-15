"""Shared plumbing for Lane B: the Nemotron 3.5 Super VL client, its request ledger and the run log.

Request style, retry rule and ledger follow scribe/generate.py and scribe/teacher2/protocol.py:
OpenAI-compatible POST {VERDA_INFERENCE_BASE_URL}/chat/completions, model "nemotron-3.5-super-vl",
chat_template_kwargs={"enable_thinking": ...}, four attempts with exponential back-off, every attempt
counted in a ledger file before it is sent. Concurrency is capped at 8 (the endpoint is shared with
another lane).

Keys are read from the process environment only; they are never logged or written. Hosted endpoints
receive SYNTHETIC text only. Not for clinical use: a person confirms every extracted event.
"""

from __future__ import annotations

import asyncio
import collections
import datetime as dt
import json
import os
import pathlib
import random
import socket
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "scribe" / "v2"), str(ROOT / "scribe"), str(HERE)):  # HERE ends up first
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

MODEL = "nemotron-3.5-super-vl"
CONCURRENCY = 8  # shared endpoint: this lane stays at 8 or less
CAP = 6000  # request attempts this lane may send in total (ledger never resets)
OUT = ROOT / "data/scribe/nemotron"
LEDGER = OUT / "ledger.json"
REQUESTS = OUT / "requests.jsonl"  # one line per attempt: no prompt, no key
RUNLOG = ROOT / "runs/laneB-step4.jsonl"


def now():
    return dt.datetime.now(dt.timezone.utc)


def save(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(path)


def log(step, command="", inputs=None, outputs=None, metrics=None, cost_usd=None, status="ok"):
    """One JSON line per executed step in runs/laneB-step4.jsonl."""
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


class CapReached(RuntimeError):
    pass


class Ledger:
    """Counts every request attempt before it is sent. The count only grows."""

    def __init__(self, path=LEDGER, cap=CAP):
        self.path = pathlib.Path(path)
        self.cap = cap
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"requests": 0}
        self.data["cap"] = cap

    @property
    def requests(self):
        return self.data["requests"]

    def reserve(self):
        if self.data["requests"] >= self.cap:
            raise CapReached(f"cap {self.cap} reached")
        self.data["requests"] += 1
        save(self.path, self.data)
        return self.data["requests"]


class Nemotron:
    """Async chat client. chat(...) -> dict(text, reasoning, tool_calls, usage, seconds, finish_reason)."""

    def __init__(self, ledger=None, concurrency=CONCURRENCY, deadline=None, timeout=180):
        import httpx

        self.ledger = ledger or Ledger()
        self.sem = asyncio.Semaphore(min(concurrency, CONCURRENCY))
        self.deadline = deadline
        self.client = httpx.AsyncClient(timeout=timeout)
        self.url = os.environ["VERDA_INFERENCE_BASE_URL"].rstrip("/")
        self.errors = collections.Counter()
        self.sent = collections.Counter()
        self.tokens = collections.Counter()

    def _record(self, **fields):
        REQUESTS.parent.mkdir(parents=True, exist_ok=True)
        with REQUESTS.open("a") as f:
            f.write(json.dumps(dict(ts=now().isoformat(timespec="seconds"), **fields), ensure_ascii=False) + "\n")

    async def chat(self, messages, max_tokens=700, temperature=0.0, thinking=False, tag="", **extra):
        body = dict(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            chat_template_kwargs={"enable_thinking": bool(thinking)},
            **extra,
        )
        async with self.sem:
            for attempt in range(4):  # scribe/generate.py: four attempts, each one counted
                if self.deadline and time.time() > self.deadline:
                    raise TimeoutError("lane deadline reached")
                number = self.ledger.reserve()
                self.sent[tag] += 1
                t = time.monotonic()
                try:
                    resp = await self.client.post(
                        self.url + "/chat/completions",
                        headers={"Authorization": "Bearer " + os.environ["VERDA_INFERENCE_KEY"]},
                        json=body,
                    )
                    if resp.status_code != 200:
                        raise RuntimeError("HTTP " + str(resp.status_code))
                    result = resp.json()
                    choice = result["choices"][0]
                    msg = choice.get("message") or {}
                    usage = result.get("usage") or {}
                    seconds = round(time.monotonic() - t, 2)
                    for k in ("prompt_tokens", "completion_tokens"):
                        self.tokens[k] += int(usage.get(k) or 0)
                    self._record(n=number, tag=tag, attempt=attempt, status="ok", seconds=seconds, usage=usage, finish_reason=choice.get("finish_reason"))
                    return dict(
                        text=msg.get("content") or "",
                        reasoning=msg.get("reasoning_content") or msg.get("reasoning") or "",
                        tool_calls=msg.get("tool_calls") or [],
                        usage=usage,
                        seconds=seconds,
                        finish_reason=choice.get("finish_reason"),
                    )
                except Exception as exc:
                    detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                    self.errors[detail] += 1
                    self._record(n=number, tag=tag, attempt=attempt, status="error", seconds=round(time.monotonic() - t, 2), error=detail)
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2**attempt + random.random())

    async def models(self):
        r = await self.client.get(self.url + "/models", headers={"Authorization": "Bearer " + os.environ["VERDA_INFERENCE_KEY"]})
        r.raise_for_status()
        return [x["id"] for x in r.json()["data"]]

    async def close(self):
        await self.client.aclose()
