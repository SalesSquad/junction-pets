"""Shared settings and process state: env names, where the ledger and cache live, the gemini-only switch."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Env names are read with every prefix in this list, first match wins. Consumers may add their own prefix for
# backwards compatibility (pet-voice adds "PET_VOICE_", so PET_VOICE_OPENAI=0 keeps working).
ENV_PREFIXES = ["SSVOICE_"]

EXHAUSTED: set[str] = set()  # models that returned a per-day quota error (or a hard stop) in this process
GEMINI_ONLY = {"on": False}  # no `openai*:` model is ever tried; failures say GEMINI_ONLY_EXHAUSTED


def _env_only(name: str) -> str | None:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(prefix + name)
        if value is not None:
            return value
    return None


_SETTINGS: dict = {"key": None, "data": {}}


def settings_path() -> Path:
    return home() / "settings.json"


def settings() -> dict:
    """This machine's non-secret defaults (e.g. which Keychain item holds a key), set with `python3 -m ssvoice settings`."""
    p = settings_path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {}
    if _SETTINGS["key"] != (str(p), mtime):
        try:
            data = json.loads(p.read_text())
            _SETTINGS.update(key=(str(p), mtime), data=data if isinstance(data, dict) else {})
        except (OSError, ValueError):
            _SETTINGS.update(key=(str(p), mtime), data={})
    return _SETTINGS["data"]


_SECRET_LIKE = re.compile(r"sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}")


def set_setting(name: str, value: str | None) -> dict:
    """Write (or with None remove) one setting. Settings are pointers and switches, never secrets."""
    if value is not None and (name.upper().endswith(("_API_KEY", "_TOKEN", "_SECRET")) or _SECRET_LIKE.search(str(value))):
        raise ValueError("settings.json holds pointers (e.g. a Keychain item name), never a key")
    data = dict(settings())
    if value is None:
        data.pop(name, None)
    else:
        data[name] = value
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, p)
    _SETTINGS["key"] = None
    return data


def env(name: str, default: str | None = None) -> str | None:
    """An environment variable (any prefix) wins; then this machine's settings.json; then the default."""
    value = _env_only(name)
    if value is not None:
        return value
    value = settings().get(name)
    return default if value is None else str(value)


def flag(name: str, default: bool = False) -> bool:
    value = env(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes", "on")


def gemini_only() -> bool:
    return GEMINI_ONLY["on"] or flag("GEMINI_ONLY")


def set_gemini_only(on: bool = True) -> None:
    """Process switch. Child processes inherit it only if the caller also exports SSVOICE_GEMINI_ONLY=1."""
    GEMINI_ONLY["on"] = on


def home() -> Path:
    """State that should survive: the quota ledger. SSVOICE_HOME overrides (tests use a temp dir)."""
    given = _env_only("HOME")
    if given:
        return Path(given)
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/SalesSquadVoice"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "ssvoice"


def cache_dir() -> Path:
    """Audio cache: purgeable by design (macOS Caches), size-capped by cache.prune()."""
    given = env("CACHE_DIR")
    if given:
        return Path(given)
    if sys.platform == "darwin":
        return Path.home() / "Library/Caches/SalesSquadVoice"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ssvoice"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
