#!/usr/bin/env python3
"""Read-only Verda job-state adapter -> owner-only immutable inbox receipts.

Never calls Verda API, starts hardware, reads SSH credentials or claims GPU success.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")
HEX = re.compile(r"^[a-f0-9]{64}$")
SAFE_ID = re.compile(r"^[a-z][a-z0-9._-]{2,95}$")
SOURCE = "SalesSquad/agents"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def owner_folder(path: Path) -> None:
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("approved folder must be absolute, not a symlink")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("approved folder must be owner-only")


def immutable_file(path: Path, data: bytes) -> bool:
    if path.is_symlink():
        raise ValueError("receipt destination is symlink")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ValueError("immutable receipt conflict")
        return False
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return True


def emit_jobs(db: Path, registry: Path, inbox: Path, receipts: Path) -> dict:
    for p in (inbox, receipts, receipts / "verda"):
        owner_folder(p)
    if db.is_symlink() or not db.is_file() or db.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Verda jobs DB unavailable or invalid")
    uri = db.resolve(strict=True).as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2)
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("SELECT job_id, state, gpus, updated, spec FROM jobs ORDER BY updated, job_id LIMIT 5001").fetchall()
    finally:
        conn.close()
    if len(rows) > 5000:
        raise ValueError("too many jobs: explicit bounded reconciliation needed")
    imported = 0
    present = 0
    skipped = 0
    for job_id, state, gpus, updated, raw_spec in rows:
        if not isinstance(job_id, str) or not SAFE_ID.fullmatch(job_id):
            skipped += 1
            continue
        if state not in ("stopped", "running", "reserved", "unknown", "stopping"):
            skipped += 1
            continue
        if not isinstance(gpus, int) or isinstance(gpus, bool) or not 1 <= gpus <= 64:
            skipped += 1
            continue
        if not isinstance(updated, (int, float)) or not 0 < updated < 4102444800:
            skipped += 1
            continue
        spec = json.loads(raw_spec)
        source_commit = spec.get("source_commit")
        if not isinstance(source_commit, str) or not SHA.fullmatch(source_commit):
            skipped += 1
            continue
        # Previously imported Verda jobs (the six November 13 leases) are already
        # represented as non-promotable records in the registry.
        legacy = registry / "runs" / ("verda.lease." + job_id + ".json")
        if legacy.is_file() and state == "stopped":
            old = json.loads(legacy.read_text())
            old_time = dt.datetime.fromisoformat(old["capturedAt"].replace("Z", "+00:00")).timestamp()
            if abs(old_time - updated) < 0.002:
                present += 1
                continue
        timestamp = int(updated * 1000)
        run_id = "verda.auto." + job_id + "." + str(timestamp)
        if not SAFE_ID.fullmatch(run_id):
            skipped += 1
            continue
        observed = dt.datetime.fromtimestamp(updated, tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        receipt = {
            "runId": run_id,
            "jobId": job_id,
            "state": state,
            "observedAt": observed,
            "sourceCommit": source_commit,
            "requestedGpuCount": gpus,
            "evidenceClass": "local-read-only-coordinator-db",
        }
        receipt_bytes = canonical(receipt)
        digest = hashlib.sha256(receipt_bytes).hexdigest()
        run = {
            "schemaVersion": 1,
            "runId": run_id,
            "projectId": "verda",
            "taskId": "junction.verda-capacity",
            "kind": "gpu-probe",
            "capturedAt": observed,
            "status": "incomplete",
            "source": {"repository": SOURCE, "commit": source_commit},
            "evidence": {
                "level": "local-receipt-unverified",
                "ref": "https://github.com/SalesSquad/agents/commit/" + source_commit,
                "receiptSha256": digest,
            },
            "dataset": None, "evaluation": None, "artifact": None,
            "metrics": [{"id": "requested-gpu-count", "value": gpus, "unit": "count", "direction": "higher", "samples": 1}],
            "limitations": [
                "Local coordinator state only: not signed by Verda or proof that any GPU kernel completed.",
                "Running/stopped/reserved is capacity metadata, not a training success or model-quality gate.",
                "Source and timestamps are from owner-side local SQLite; no provider costs/keys/remote media are copied.",
            ],
            "policySha256": None,
        }
        envelope = {
            "schemaVersion": 1,
            "run": run,
            "receipt": {"runId": run_id, "path": "verda/" + run_id + ".json", "sha256": digest},
        }
        rc = immutable_file(receipts / "verda" / (run_id + ".json"), receipt_bytes)
        ec = immutable_file(inbox / (run_id + ".json"), canonical(envelope))
        if rc or ec:
            imported += 1
        else:
            present += 1
    return {"observed": len(rows), "envelopesCreated": imported, "existing": present, "unadmitted": skipped, "providerAttestationVerified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--inbox", required=True, type=Path)
    parser.add_argument("--receipts-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(emit_jobs(args.db, args.registry, args.inbox, args.receipts_root), sort_keys=True))
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError, json.JSONDecodeError):
        print(json.dumps({"error": "verda collector failed closed", "success": False}))
        sys.exit(1)
