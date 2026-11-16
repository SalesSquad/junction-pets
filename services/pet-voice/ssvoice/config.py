"""Shared settings and process state: env names, where the ledger and cache live, the gemini-only switch."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Env names are read with every prefix in this list, first match wins. Consumers may add their own prefix for
# backwards compatibility (pet-voice adds "PET_VOICE_", so PET_VOICE_OPENAI=0 keeps working).
ENV_PREFIXES = ["SSVOICE_"]

EXHAUSTED: set[str] = set()  # models that returned a per-day quota error (or a hard stop) in this process
GEMINI_ONLY = {"on": False}  # no `openai*:` model is ever tried; failures say GEMINI_ONLY_EXHAUSTED


def env(name: str, default: str | None = None) -> str | None:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(prefix + name)
        if value is not None:
            return value
    return default


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
    given = env("HOME")
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
