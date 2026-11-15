#!/usr/bin/env python3
"""Typed-decision clients for TypeSafe Jev and the OpenAI Decisions API.

Experiment-only helper (unranked practice and offline review). Keys come from the
environment or the owner's local env files (~/.config/typesafe/env,
~/.config/openai/factory-decisions.env); they are never printed or logged.

    decide("jev", state, [Question(...)]) -> ({name: Answer}, usage, latency_ms)
"""
from __future__ import annotations

import atexit
import json
import os
import pathlib
import ssl
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

PROVIDERS = {
    "jev": {"url": "https://api.typesafe.ai/v1/systemone", "model": "jev-1.13.0",
            "key_env": "TYPESAFE_API_KEY", "key_file": ".config/typesafe/env", "usd_per_m": 0.042},
    "openai": {"url": "https://api.openai.com/v1/decisions", "model": "gpt-6-luna",
               "key_env": "OPENAI_API_KEY", "key_file": ".config/openai/factory-decisions.env",
               "usd_per_m": 0.10},
}
USAGE: Counter[str] = Counter()
_KEYS: dict[str, str] = {}


@dataclass
class Question:
    name: str
    instructions: str
    choices: list[tuple[str, str]] = field(default_factory=list)  # empty = yes/no


@dataclass
class Answer:
    choice: str | None
    probabilities: dict[str, float]
    yes: float | None
    confidence: float | None


@atexit.register
def _report() -> None:
    if USAGE:
        cost = sum(USAGE[f"{p}_input_tokens"] * s["usd_per_m"] / 1e6 for p, s in PROVIDERS.items())
        print("AI_USAGE=" + json.dumps({**dict(sorted(USAGE.items())), "usd": round(cost, 5)}), flush=True)


def _key(provider: str) -> str:
    if provider in _KEYS:
        return _KEYS[provider]
    spec = PROVIDERS[provider]
    value = os.environ.get(spec["key_env"], "")
    if not value:
        path = pathlib.Path.home() / spec["key_file"]
        for line in path.read_text().splitlines():
            name, sep, raw = line.partition("=")
            if sep and name.removeprefix("export ").strip() == spec["key_env"]:
                value = raw.strip().strip('"').strip("'")
    if not value:
        raise RuntimeError(f"{provider}: key not configured")
    _KEYS[provider] = value
    return value


def _ssl() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_CTX = _ssl()


def wire(provider: str, state: Any, questions: list[Question]) -> dict[str, Any]:
    spec = PROVIDERS[provider]
    if provider == "jev":
        qs: dict[str, Any] = {}
        for q in questions:
            if q.choices:
                qs[q.name] = {"type": "choice", "instructions": q.instructions,
                              "criteria": {v: d for v, d in q.choices}}
            else:
                qs[q.name] = {"type": "noul", "instructions": q.instructions}
        return {"model": spec["model"], "state": state, "questions": qs}
    text = state if isinstance(state, str) else json.dumps(state, separators=(",", ":"), sort_keys=True)
    out = []
    for q in questions:
        if q.choices:
            out.append({"type": "choice", "name": q.name, "instructions": q.instructions,
                        "choices": [{"value": v, "description": d} for v, d in q.choices]})
        else:
            out.append({"type": "predicate", "name": q.name, "instructions": q.instructions})
    return {"model": spec["model"], "input": text, "questions": out}


def normalize(provider: str, body: dict[str, Any]) -> dict[str, Answer]:
    answers: dict[str, Answer] = {}
    raw = body.get("answers")
    items = raw.items() if isinstance(raw, dict) else ((a.get("name"), a) for a in raw or [])
    for name, a in items:
        kind = a.get("type")
        if kind in ("noul", "predicate", "boolean"):
            p = a.get("noul", a.get("probability"))
            answers[name] = Answer(None, {}, float(p) if p is not None else None, None)
        elif kind == "choice":
            probs = a.get("probabilities") or {}
            if isinstance(probs, list):
                probs = {str(x["value"]): float(x["probability"]) for x in probs}
            answers[name] = Answer(str(a.get("choice")), {str(k): float(v) for k, v in probs.items()},
                                   None, a.get("confidence"))
        else:  # refusal or unknown
            answers[name] = Answer(None, {}, None, None)
    return answers


def decide(provider: str, state: Any, questions: list[Question], timeout: float = 8.0
           ) -> tuple[dict[str, Answer], dict[str, Any], float]:
    spec = PROVIDERS[provider]
    data = json.dumps(wire(provider, state, questions)).encode()
    req = urllib.request.Request(spec["url"], data=data, method="POST", headers={
        "content-type": "application/json", "authorization": "Bearer " + _key(provider)})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
            body = json.loads(resp.read())
    except Exception:
        USAGE[f"{provider}_errors"] += 1
        raise
    ms = (time.monotonic() - t0) * 1000
    usage = body.get("usage") or {}
    USAGE[f"{provider}_calls"] += 1
    USAGE[f"{provider}_input_tokens"] += int(usage.get("input_tokens") or 0)
    USAGE[f"{provider}_ms"] += int(ms)
    return normalize(provider, body), usage, ms


if __name__ == "__main__":  # connectivity smoke test, prints no secrets
    import sys
    q = [Question("late_risk", "Is a late delivery likely for this order?",
                  [("high", "Little real working-time buffer"), ("low", "Ample buffer and drivers")])]
    for prov in sys.argv[1:] or ["jev", "openai"]:
        try:
            ans, use, ms = decide(prov, {"slack_hours": 2, "weekend_between": True}, q)
            print(prov, "OK", {k: vars(v) for k, v in ans.items()}, use, f"{ms:.0f} ms")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if hasattr(exc, "read"):
                try:
                    msg += " " + exc.read().decode()[:300]  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
            print(prov, "FAIL", type(exc).__name__, msg[:400])
