"""Quota ledger: one small JSON file per machine that every voice process reads and writes.

Every provider request is counted here (per UTC day and model, with tokens when the provider reports them), and a
per-day quota error sets a cooldown that lasts until the provider's reset. The router puts cooling models last, so the
next process does not burn a call to rediscover a spent quota. A failure to read or write the ledger never breaks a
voice call: it is bookkeeping, not a gate. Not yet shared across machines (the Gemini key's quota is per project, so a
second Mac's calls are invisible here) — see voice/README.md.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl; the ledger is then best-effort without a lock
    fcntl = None

SCHEMA = "salessquad.voice.ledger/v1"
KEEP_DAYS = 14


def path() -> Path:
    return config.home() / "ledger.json"


def enabled() -> bool:
    return config.flag("LEDGER", True)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_reset(model: str, at: datetime | None = None) -> datetime:
    """OpenAI's complimentary tokens reset at 00:00 UTC; Gemini per-day quotas at midnight Pacific (08:00 UTC in winter)."""
    at = at or _utc()
    if model.startswith("openai"):
        return (at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        from zoneinfo import ZoneInfo
        local = at.astimezone(ZoneInfo("America/Los_Angeles"))
        midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight.astimezone(timezone.utc)
    except Exception:  # no tz database: the winter value
        reset = at.replace(hour=8, minute=0, second=0, microsecond=0)
        return reset if reset > at else reset + timedelta(days=1)


def _empty() -> dict:
    return {"schema": SCHEMA, "days": {}, "cooldownUntil": {}}


def _read(p: Path) -> dict:
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) and data.get("schema") == SCHEMA else _empty()
    except (OSError, ValueError):
        return _empty()


@contextmanager
def _locked():
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(".lock"), "a+") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            data = _read(p)
            yield data
            tmp = p.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True))
            os.replace(tmp, p)
        finally:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_UN)


def record(model: str, ok: bool, *, error=None, tokens: int = 0) -> None:
    """Count one provider request. `error` is a ProviderError; a per-day one starts a cooldown until the reset."""
    if not enabled():
        return
    try:
        at = _utc()
        with _locked() as data:
            day = data["days"].setdefault(at.strftime("%Y-%m-%d"), {})
            row = day.setdefault(model, {"ok": 0, "fail": 0, "daily": 0, "tokens": 0})
            row["ok" if ok else "fail"] += 1
            row["tokens"] += int(tokens or 0)
            cool = data.setdefault("cooldownUntil", {})
            if ok:
                cool.pop(model, None)
            elif error is not None and getattr(error, "daily", False):
                row["daily"] += 1
                wait = getattr(error, "retry_after", None)
                until = at + timedelta(seconds=wait) if wait and wait > 60 else next_reset(model, at)
                cool[model] = _iso(until)
            keep = (at - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
            for old in [d for d in data["days"] if d < keep]:
                del data["days"][old]
    except (OSError, ValueError, KeyError, TypeError):
        pass


def cooldowns() -> dict[str, str]:
    """Models still inside a per-day cooldown on this machine: {model: until (UTC ISO)}."""
    if not enabled():
        return {}
    now = config.now()
    return {m: until for m, until in (_read(path()).get("cooldownUntil") or {}).items() if until > now}


def today(prefix: str = "") -> dict:
    """Summed counts for models starting with `prefix` on the current UTC day."""
    rows = _read(path())["days"].get(_utc().strftime("%Y-%m-%d"), {}) if enabled() else {}
    out = {"ok": 0, "fail": 0, "daily": 0, "tokens": 0}
    for model, row in rows.items():
        if model.startswith(prefix):
            for k in out:
                out[k] += int(row.get(k, 0))
    return out


def summary() -> dict:
    data = _read(path())
    return {"path": str(path()), "enabled": enabled(), "today": data["days"].get(_utc().strftime("%Y-%m-%d"), {}),
            "cooling": cooldowns()}
