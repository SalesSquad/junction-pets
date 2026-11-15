"""Live second reader for the scribe demo: Nemotron 3.5 Super VL reads one SYNTHETIC demo note now.

The protocol is imported unchanged from scribe/nemotron/reader.py: read_note with version v3 (expression format,
local validation, grounding check, one repair retry, enable_thinking on), the same system prompt and repair
message; code resolves the dates (scribe/v2/data_tools.resolve_expression). The request body is the one
scribe/nemotron/common.py Nemotron.chat sends: model "nemotron-3.5-super-vl", temperature 0, max_tokens from
reader.py, chat_template_kwargs.enable_thinking. Only the transport differs: one attempt per call with the Python
standard library (urllib), bounded by a deadline, and no ledger or request log, so the frozen evaluation's files
under data/ stay untouched.

One JSON object on stdin: {"note_text": str, "note_date": "YYYY-MM-DD", "id": str?, "timeout_s": number?}.
One JSON line on stdout:
  {"ok": true, "prediction": {...} | null, "model": ..., "version": "v3", "latency_ms": int, "calls": int,
   "flagged": bool, "raw": str}
  {"ok": false, "kind": "no_key" | "network" | "timeout" | "http" | "input" | "error", "error": str}

Environment: VERDA_INFERENCE_BASE_URL and VERDA_INFERENCE_KEY (load them with
`set -a; . ~/.config/verda-inference/env; set +a`). The key is read from the environment only; it is never printed,
logged or written. Hosted endpoints receive SYNTHETIC text only. A person confirms every extracted event.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import pathlib
import re
import socket
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True  # importing the reader must not leave __pycache__ files in scribe/
sys.path.insert(0, str(ROOT / "scribe" / "nemotron"))

import common as NC  # noqa: E402  scribe/nemotron/common.py (MODEL; its client and ledger are not used here)
import reader as R  # noqa: E402  scribe/nemotron/reader.py (read_note, CONFIG, prompts: unchanged)

VERSION = "v3"
DEFAULT_TIMEOUT_S = 42.0  # the server kills this process at 45 s


class Failure(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _clean(text):
    """An error message with the key, the bearer header and URLs removed, at most 200 characters."""
    s = str(text)
    key = os.environ.get("VERDA_INFERENCE_KEY") or ""
    if key:
        s = s.replace(key, "***")
    s = re.sub(r"(?i)bearer\s+\S+", "Bearer ***", s)
    s = re.sub(r"https?://\S+", "<endpoint>", s)
    return s[:200]


def make_chat(base_url, key, deadline, urlopen=urllib.request.urlopen):
    """chat(messages, max_tokens, thinking, tag) as read_note expects it; one HTTP attempt, bounded by deadline."""
    url = base_url.rstrip("/") + "/chat/completions"

    async def chat(messages, max_tokens, thinking, tag):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            raise Failure("timeout", f"no time left for the {tag.split(':')[-1]} call")
        body = dict(model=NC.MODEL, messages=messages, temperature=0.0, max_tokens=max_tokens,
                    chat_template_kwargs={"enable_thinking": bool(thinking)})
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "sama-scribe-demo/1"})
        t = time.monotonic()
        try:
            with urlopen(req, timeout=remaining) as resp:
                status = getattr(resp, "status", 200)
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            raise Failure("http", f"the endpoint answered HTTP {exc.code}") from None
        except (TimeoutError, socket.timeout):
            raise Failure("timeout", "the endpoint did not answer in time") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise Failure("timeout", "the endpoint did not answer in time") from None
            raise Failure("network", "the endpoint could not be reached (" + _clean(type(exc.reason).__name__) + ")") from None
        except OSError as exc:
            raise Failure("network", "the endpoint could not be reached (" + _clean(type(exc).__name__) + ")") from None
        if status != 200:
            raise Failure("http", f"the endpoint answered HTTP {status}")
        try:
            result = json.loads(payload)
            choice = result["choices"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            raise Failure("error", "the endpoint returned no chat completion") from None
        msg = choice.get("message") or {}
        return dict(text=msg.get("content") or "", reasoning=msg.get("reasoning_content") or msg.get("reasoning") or "",
                    usage=result.get("usage") or {}, seconds=round(time.monotonic() - t, 2),
                    finish_reason=choice.get("finish_reason"))

    return chat


def read_live(request, env=None, urlopen=urllib.request.urlopen):
    """One note through the frozen v3 protocol. Returns the stdout object (never raises)."""
    env = os.environ if env is None else env
    try:
        text, date = request.get("note_text"), request.get("note_date")
        if not isinstance(text, str) or not text.strip() or len(text) > 6000:
            raise Failure("input", "note_text must be a non-empty string of at most 6000 characters")
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise Failure("input", "note_date must be YYYY-MM-DD")
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            raise Failure("input", "note_date must be a real date") from None
        base, key = env.get("VERDA_INFERENCE_BASE_URL"), env.get("VERDA_INFERENCE_KEY")
        if not base or not key:
            raise Failure("no_key", "no endpoint key in the server environment")
        timeout_s = min(float(request.get("timeout_s") or DEFAULT_TIMEOUT_S), DEFAULT_TIMEOUT_S)
        t0 = time.monotonic()
        row = {"id": request.get("id") or "live", "note_text": text, "note_date": date}
        out = asyncio.run(R.read_note(row, VERSION, make_chat(base, key, t0 + timeout_s, urlopen)))
        return dict(ok=True, prediction=out["prediction"], model=NC.MODEL, version=VERSION,
                    latency_ms=int(round((time.monotonic() - t0) * 1000)), calls=out["calls"],
                    flagged=out["flagged"], raw=out["raw"][:4000])
    except Failure as exc:
        return dict(ok=False, kind=exc.kind, error=_clean(exc))
    except Exception as exc:  # never a traceback on stdout: the type only
        return dict(ok=False, kind="error", error="the live reader failed (" + type(exc).__name__ + ")")


def main():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        if not isinstance(request, dict):
            raise ValueError
    except ValueError:
        request = {}
    sys.stdout.write(json.dumps(read_live(request), ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
