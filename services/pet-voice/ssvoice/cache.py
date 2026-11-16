"""Content-addressed audio cache: the same text, voice, style and model is synthesized once.

Demo rebuilds, listening-page A/B pairs and resumed runs ask for audio that was already made; on the free tiers each
of those requests costs one of ~10 daily calls. The cache lives in a purgeable folder (macOS Caches) and is pruned to
SSVOICE_CACHE_MAX_MB (default 1024) oldest-first. SSVOICE_CACHE=0 turns it off; `fresh=True` on a request skips it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import config

_PUTS = {"n": 0}


def enabled() -> bool:
    return config.flag("CACHE", True)


def root() -> Path:
    return config.cache_dir() / "audio"


def key(kind: str, model: str, text: str, voice: str, style: str) -> str:
    return hashlib.sha256(json.dumps([kind, model, voice, style, text], ensure_ascii=False).encode()).hexdigest()


def _paths(k: str) -> tuple[Path, Path]:
    d = root() / k[:2]
    return d / f"{k}.wav", d / f"{k}.json"


def get(k: str) -> tuple[bytes, dict] | None:
    if not enabled():
        return None
    wav_p, meta_p = _paths(k)
    try:
        wav, meta = wav_p.read_bytes(), json.loads(meta_p.read_text())
    except (OSError, ValueError):
        return None
    try:
        os.utime(wav_p)
    except OSError:
        pass
    return wav, meta


def put(k: str, wav: bytes, meta: dict) -> None:
    if not enabled():
        return
    wav_p, meta_p = _paths(k)
    try:
        wav_p.parent.mkdir(parents=True, exist_ok=True)
        for p, data in ((wav_p, wav), (meta_p, json.dumps(meta, ensure_ascii=False).encode())):
            tmp = p.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)
    except OSError:
        return
    _PUTS["n"] += 1
    if _PUTS["n"] % 25 == 0:
        prune()


def _files() -> list[Path]:
    return [p for p in root().glob("*/*.wav") if p.is_file()] if root().exists() else []


def prune(max_mb: float | None = None) -> dict:
    """Delete the least recently used clips until the cache is under 90 % of its cap."""
    cap = float(max_mb if max_mb is not None else config.env("CACHE_MAX_MB", "1024")) * 1024 * 1024
    files = sorted(_files(), key=lambda p: p.stat().st_mtime)
    total, removed = sum(p.stat().st_size for p in files), 0
    if total > cap:
        for p in files:
            if total <= cap * 0.9:
                break
            size = p.stat().st_size
            for q in (p, p.with_suffix(".json")):
                try:
                    q.unlink()
                except OSError:
                    pass
            total -= size
            removed += 1
    return {"files": len(files) - removed, "bytes": total, "removed": removed}


def stats() -> dict:
    files = _files()
    return {"enabled": enabled(), "path": str(root()), "files": len(files), "bytes": sum(p.stat().st_size for p in files)}
