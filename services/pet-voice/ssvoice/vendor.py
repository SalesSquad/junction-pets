"""Copy this package into a consumer repo as a pinned, self-contained copy (stdlib only, no install step).

The source of truth is SalesSquad/agents voice/ssvoice. A consumer that must run on its own (a hackathon submission,
a cloud environment without this repo) gets `<target>/ssvoice/` plus VENDORED.json naming the source commit and a
sha256 per file. Never edit a vendored copy: change the source here, land it, and vendor again.

  python3 -m ssvoice vendor <target-dir>          # write or refresh <target-dir>/ssvoice
  python3 -m ssvoice vendor <target-dir> --check  # local edits? older than this source?
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
REPOSITORY, SOURCE_PATH = "SalesSquad/agents", "voice/ssvoice"


def _files(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.py"))}


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(SOURCE), *args], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def vendor(target_dir: Path) -> dict:
    dst = Path(target_dir) / "ssvoice"
    dst.mkdir(parents=True, exist_ok=True)
    files = _files(SOURCE)
    for stale in dst.glob("*.py"):
        if stale.name not in files:
            stale.unlink()
    for name in files:
        shutil.copyfile(SOURCE / name, dst / name)
    receipt = {"schema": "salessquad.voice.vendored/v1", "source": {"repository": REPOSITORY, "path": SOURCE_PATH,
               "commit": _git("rev-parse", "HEAD") or None, "dirty": bool(_git("status", "--porcelain", "--", "."))},
               "vendoredAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "files": files,
               "note": "Generated copy. Edit the source in SalesSquad/agents voice/ssvoice and vendor again."}
    (dst / "VENDORED.json").write_text(json.dumps(receipt, indent=1) + "\n")
    return receipt


def check(target_dir: Path) -> dict:
    """locallyEdited: files changed since vendoring. behindSource: files that differ from this source checkout."""
    dst = Path(target_dir) / "ssvoice"
    try:
        receipt = json.loads((dst / "VENDORED.json").read_text())
    except (OSError, ValueError):
        return {"ok": False, "error": f"no VENDORED.json in {dst}"}
    have, source = _files(dst), _files(SOURCE)
    edited = sorted(n for n, h in receipt.get("files", {}).items() if have.get(n) != h)
    edited += sorted(n for n in have if n not in receipt.get("files", {}))
    behind = sorted(n for n in set(have) | set(source) if have.get(n) != source.get(n))
    return {"ok": not edited and not behind, "locallyEdited": edited, "behindSource": behind,
            "vendoredFrom": receipt.get("source", {}).get("commit")}
