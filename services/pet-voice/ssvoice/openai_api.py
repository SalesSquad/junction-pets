"""OpenAI speech and text, from two projects with different rules.

paid   — the owner's ordinary key (Keychain "OpenAI API Key" / "openai", or OPENAI_API_KEY). Always the last resort,
         behind a per-process call cap (SSVOICE_OPENAI_MAX_CALLS, default 150).
shared — a separate project with data sharing enabled, whose traffic earns OpenAI's complimentary daily tokens on the
         listed text models (e.g. gpt-5.4-mini). OpenAI uses that traffic for evaluation and training, so the router
         only sends `privacy="public"` requests here (synthetic dialogue, demos), never private data. Speech, Realtime
         and transcription are not on the complimentary list, so this project is text-only. Keychain item
         "OpenAI API Key (data sharing)" / "openai-shared" (or SSVOICE_OPENAI_SHARED_API_KEY); a daily token budget
         (SSVOICE_OPENAI_SHARED_DAILY_TOKENS, default 2,000,000 — under the 2.5M lower-tier group) stops it before
         usage would be billed.

SSVOICE_OPENAI=0 disables both; SSVOICE_OPENAI_SHARED=0 disables only the shared project.
gpt-4o-mini-tts on /v1/audio/speech shuts down 6 Jan 2027 (migrate to the Realtime API).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zlib

from . import config, ledger
from .audio import normalize_audio
from .errors import ProviderError
from .gemini import FEMALE_VOICES, NoRedirect

API = "https://api.openai.com/v1"
KEYCHAIN = {"paid": ("OpenAI API Key", "openai"), "shared": ("OpenAI API Key (data sharing)", "openai-shared")}
PREFIX = {"paid": "openai:", "shared": "openai-shared:"}
STT_MODEL = "gpt-4o-mini-transcribe"
FEMALE = ["marin", "coral", "nova", "shimmer", "sage"]
MALE = ["cedar", "ash", "onyx", "verse", "ballad", "echo"]
CALLS = {"n": 0}
_KEYS: dict = {}


def max_calls() -> int:
    return int(config.env("OPENAI_MAX_CALLS", "150"))


def shared_budget() -> int:
    return int(config.env("OPENAI_SHARED_DAILY_TOKENS", "2000000"))


def read_key(project: str = "paid") -> str | None:
    """None disables that project. Never printed or written."""
    if config.env("OPENAI", "1") == "0" or (project == "shared" and config.env("OPENAI_SHARED", "1") == "0"):
        return None
    if project not in _KEYS:
        key = (os.environ.get("OPENAI_API_KEY", "") if project == "paid" else config.env("OPENAI_SHARED_API_KEY", "")).strip()
        if not key:
            service, account = KEYCHAIN[project]
            try:
                r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", service, "-a", account, "-w"],
                                   capture_output=True, text=True, timeout=20)
                key = r.stdout.strip() if r.returncode == 0 else ""
            except (OSError, subprocess.TimeoutExpired):
                key = ""
        _KEYS[project] = key if len(key) > 20 else None
    return _KEYS[project]


def voice_for(name: str, gender: str | None = None) -> str:
    """A stable OpenAI voice of the same gender as a Gemini voice (or the gender a voice design names)."""
    female = gender == "female" if gender else name in FEMALE_VOICES
    pool = FEMALE if female else MALE
    return pool[zlib.crc32(name.encode()) % len(pool)]


def post(path: str, timeout: float = 90, payload: dict | None = None, multipart: tuple[dict, tuple[str, bytes, str]] | None = None,
         project: str = "paid") -> bytes:
    if config.gemini_only():
        raise ProviderError(0, "GEMINI_ONLY", "OpenAI call blocked by --gemini-only")
    key = read_key(project)
    if not key:
        raise ProviderError(0, "NO_KEY", f"OpenAI {project} project disabled: no key")
    if CALLS["n"] >= max_calls():
        raise ProviderError(0, "OPENAI_CAP", f"spend guard: {max_calls()} OpenAI calls in this process", daily=True)
    model = str((payload or {}).get("model") or (multipart[0].get("model") if multipart else "") or path)
    label = PREFIX[project] + model
    if project == "shared" and ledger.today(PREFIX["shared"])["tokens"] >= shared_budget():
        raise ProviderError(0, "SHARED_BUDGET", f"complimentary-token budget {shared_budget()} used today", daily=True)
    CALLS["n"] += 1
    headers = {"Authorization": f"Bearer {key}"}
    if multipart:
        fields, (fname, blob, mime) = multipart
        boundary = f"----ssvoice{uuid.uuid4().hex}"
        body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
                 + blob + f"\r\n--{boundary}--\r\n".encode())
        headers["content-type"] = f"multipart/form-data; boundary={boundary}"
    else:
        body = json.dumps(payload).encode()
        headers["content-type"] = "application/json"
    req = urllib.request.Request(f"{API}/{path}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        try:
            info = json.loads(e.read().decode("utf-8", "replace")).get("error", {})
        except (ValueError, AttributeError):
            info = {}
        code = str(info.get("code") or info.get("type") or "")
        err = ProviderError(e.code, code, str(info.get("message") or "")[:400], daily=code == "insufficient_quota")
        ledger.record(label, False, error=err)
        raise err
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        err = ProviderError(0, "TIMEOUT" if "timed out" in str(e).lower() else "NETWORK", type(e).__name__)
        ledger.record(label, False, error=err)
        raise err
    tokens = 0
    if raw[:1] == b"{":
        try:
            tokens = int((json.loads(raw).get("usage") or {}).get("total_tokens") or 0)
        except (ValueError, AttributeError, TypeError):
            tokens = 0
    ledger.record(label, True, tokens=tokens)
    return raw


def speak(text: str, voice: str, style: str, model: str = "gpt-4o-mini-tts") -> bytes:
    """Paid project only: speech is not on the complimentary-token list."""
    instructions = (style or "natural, expressive") + ". Speak in the language the text is written in, with a native accent."
    raw = post("audio/speech", payload={"model": model, "voice": voice, "input": text, "instructions": instructions,
                                        "response_format": "wav"})
    return normalize_audio(raw, "audio/wav")


def transcribe(wav: bytes, model: str = STT_MODEL) -> str:
    """Paid project only: transcription is not on the complimentary-token list."""
    raw = post("audio/transcriptions", timeout=60, multipart=({"model": model, "response_format": "json"},
                                                             ("turn.wav", wav, "audio/wav")))
    return str(json.loads(raw).get("text", "")).strip()


def to_json_schema(s: dict) -> dict:
    """Gemini responseSchema -> strict OpenAI JSON schema (lower-case types, every property required, no extras)."""
    out = {"type": str(s.get("type", "string")).lower()}
    for k in ("description", "enum"):
        if k in s:
            out[k] = s[k]
    if out["type"] == "object":
        props = s.get("properties", {})
        out.update({"properties": {k: to_json_schema(v) for k, v in props.items()}, "required": list(props),
                    "additionalProperties": False})
    if out["type"] == "array":
        out["items"] = to_json_schema(s.get("items", {"type": "STRING"}))
    return out


def ask_json(system: str, prompt: str, schema: dict, audio: bytes | None, model: str, log: list,
             project: str = "paid") -> tuple[dict, float]:
    """Structured reply from an OpenAI text model. Audio is transcribed first on the paid project; the shared
    (complimentary) project takes text only, so callers pass a transcript they already have."""
    label, t0 = PREFIX[project] + model, time.monotonic()
    try:
        if audio:
            if project == "shared":
                raise ProviderError(0, "AUDIO_NOT_FREE", "the shared project is text-only; pass a transcript instead")
            prompt = f"Transcript of the audio you just heard (transcribed for you):\n{transcribe(audio)}\n\n{prompt}"
        body = {"model": model, "instructions": system, "input": prompt, "reasoning": {"effort": "low"}, "max_output_tokens": 3000,
                "text": {"format": {"type": "json_schema", "name": "reply", "schema": to_json_schema(schema), "strict": True}}}
        raw = post("responses", timeout=60, payload=body) if project == "paid" else \
            post("responses", timeout=60, payload=body, project=project)
        data = json.loads(raw)
        text = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                       for c in item.get("content", []) if c.get("type") == "output_text").strip()
        return json.loads(text), time.monotonic() - t0
    except ProviderError as e:
        log.append(e.record(label))
        if e.daily or e.code in ("NO_KEY", "OPENAI_CAP", "SHARED_BUDGET"):
            config.EXHAUSTED.add(label)
        raise
    except (ValueError, KeyError) as e:
        log.append({"model": label, "status": 200, "code": "BAD_JSON", "message": str(e)[:160]})
        raise ProviderError(200, "BAD_JSON", str(e)[:160])
