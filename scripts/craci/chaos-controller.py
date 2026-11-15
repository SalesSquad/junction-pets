#!/usr/bin/env python3
"""Bounded Mac Mini CRACI Chaos Lab dispatch loop, with an append-only ledger.

Only a previously qualified cloud wave may unlock another distinct wave. This
does not create provider secrets, raise account limits or claim known billing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

REPO = "SalesSquad/junction-pets"
WORKFLOW = "craci-pilot.yml"
BRANCH = "codex/craci-chaos-lab-20261114"
STOP = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)
MIN_GAP_SECONDS = 13 * 60
RUNNER_HEADROOM_SECONDS = 16 * 60
# planning 2 vCPU*5 min + 4 cells*2 vCPU*15 min, at assumed EUR 0.0025 per vCPU-min.
RESERVE_EUR = (2 * 5 + 4 * 2 * 15) * 0.0025
PROFILES = ("provenance", "network", "control", "evidence")


def now():
    return datetime.now(timezone.utc)


def gh(args, timeout=60):
    process = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    if process.returncode:
        raise RuntimeError(f"GH_EXIT_{process.returncode}")
    return process.stdout.strip()


def gh_json(args):
    return json.loads(gh(args))


def record(path, **fields):
    row = {"at": now().isoformat(), **fields}
    with path.open("a", encoding="utf8") as output:
        output.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    print(json.dumps(row, separators=(",", ":"), sort_keys=True), flush=True)


def journal_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf8") as source:
        return [json.loads(line) for line in source if line.strip()]


def validate_intent_history(rows):
    """An uncertain remote dispatch is never silently skipped after restart."""
    intents = [row["epoch"] for row in rows if row.get("type") == "dispatch-attempt"]
    dispatched = [row["epoch"] for row in rows if row.get("type") == "dispatched"]
    if len(intents) != len(set(intents)) or len(dispatched) != len(set(dispatched)):
        raise RuntimeError("DUPLICATE_DISPATCH_LEDGER")
    unconfirmed = set(intents) - set(dispatched)
    unrecorded = set(dispatched) - set(intents)
    if unconfirmed or unrecorded:
        # A remote GH run might exist even though the client lost its ACK.
        # Stopping is safer than dispatching a later epoch while this is unknown.
        raise RuntimeError("UNRESOLVED_DISPATCH_INTENT")


def recent_runs():
    return gh_json(["run", "list", "--repo", REPO, "--workflow", WORKFLOW,
                    "--limit", "100", "--json",
                    "databaseId,status,conclusion,event,headSha,displayTitle,createdAt"])


def verify_remote(sha):
    credit = gh_json(["api", f"repos/{REPO}/actions/variables/CRACI_CREDIT_WINDOW_OPEN"])
    if credit.get("value") != "true":
        raise RuntimeError("CREDIT_WINDOW_CLOSED")
    remote = gh_json(["api", f"repos/{REPO}/git/ref/heads/{BRANCH}"])
    if remote.get("object", {}).get("sha") != sha:
        raise RuntimeError("SOURCE_PIN_CHANGED")


def verified_owned(path, latest):
    history = journal_rows(path)
    own = {row["runId"]: row["epoch"] for row in history if row.get("type") == "dispatched"}
    completed = {row["runId"] for row in history if row.get("type") == "verified-success"}
    by_id = {row["databaseId"]: row for row in latest}
    for run_id, epoch in sorted(own.items()):
        if run_id in completed:
            continue
        outcome = by_id.get(run_id)
        if outcome is None:
            raise RuntimeError(f"UNVERIFIED_RUN_{run_id}")
        if outcome["status"] != "completed":
            return False
        if outcome["conclusion"] != "success":
            raise RuntimeError(f"FAILED_RUN_{run_id}")
        details = gh_json(["run", "view", str(run_id), "--repo", REPO, "--json", "jobs"])
        jobs = [job for job in details.get("jobs", [])
                if job.get("name", "").startswith("Chaos Lab /")]
        if len(jobs) != 4 or any(job.get("conclusion") != "success" for job in jobs):
            raise RuntimeError(f"UNVERIFIED_JOBS_{run_id}")
        for profile in PROFILES:
            if len([job for job in jobs if job.get("name", "").startswith(f"Chaos Lab / {profile} /")]) != 1:
                raise RuntimeError(f"MISSING_PROFILE_{run_id}")
        artifacts = gh_json(["api", f"repos/{REPO}/actions/runs/{run_id}/artifacts"])
        expected = {f"craci-chaos-chaos-{epoch}-{profile}-{run_id}-1" for profile in PROFILES}
        found = {item["name"] for item in artifacts.get("artifacts", [])
                 if not item.get("expired", True)}
        if not expected.issubset(found):
            raise RuntimeError(f"MISSING_RECEIPTS_{run_id}")
        record(path, type="verified-success", runId=run_id, epoch=epoch,
               jobs=len(jobs), receipts=len(expected))
    return True


def locate_new_run(since, sha, excluded):
    for _ in range(8):
        for run in recent_runs():
            created = datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
            if (run["databaseId"] not in excluded and run["event"] == "workflow_dispatch"
                    and run["headSha"] == sha and "CRACI chaos-lab /" in run["displayTitle"]
                    and created >= since - timedelta(seconds=12)):
                return run["databaseId"]
        time.sleep(4)
    raise RuntimeError("DISPATCH_UNCERTAIN_NO_RETRY")


def cancel_own_active(path):
    history = journal_rows(path)
    own = {row["runId"] for row in history if row.get("type") == "dispatched"}
    try:
        active = {run["databaseId"] for run in recent_runs()
                  if run["status"] in ("queued", "in_progress", "waiting", "pending")}
    except Exception as error:
        record(path, type="stop-check-failed", code=type(error).__name__)
        return
    for run_id in sorted(own & active):
        try:
            gh(["run", "cancel", str(run_id), "--repo", REPO])
            record(path, type="cancel-requested", runId=run_id)
        except Exception as error:
            record(path, type="cancel-error", runId=run_id, code=type(error).__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--start-epoch", type=int, default=3)
    parser.add_argument("--max-epochs", type=int, default=4)
    parser.add_argument("--max-estimate-eur", type=float, default=5)
    args = parser.parse_args()
    if not re.fullmatch("[a-f0-9]{40}", args.sha):
        parser.error("Exact full lowercase HEAD SHA required")
    if not (3 <= args.start_epoch <= 12 and 1 <= args.max_epochs <= 6 and
            args.start_epoch + args.max_epochs - 1 <= 12):
        parser.error("Invalid bounded epoch range")
    if not (RESERVE_EUR <= args.max_estimate_eur <= 5):
        parser.error("Chaos estimate cap must be at most 5 EUR")
    if now() >= STOP or now() + timedelta(seconds=RUNNER_HEADROOM_SECONDS) >= STOP:
        parser.error("No time for one bounded CRACI job before hard stop")
    journal = Path(args.journal).resolve()
    if journal.parent != Path("/private/tmp") or not journal.name.startswith("craci-chaos-"):
        parser.error("Task-owned /private/tmp/craci-chaos-* journal required")
    lock = os.open(journal.with_suffix(".lock"), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    details = os.fstat(lock)
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise RuntimeError("UNSAFE_LOCK_FILE")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError("CONTROLLER_ALREADY_RUNNING") from error
    history = journal_rows(journal)
    validate_intent_history(history)
    attempted = {r["epoch"] for r in history if r.get("type") == "dispatch-attempt"}
    reservations = len(attempted) * RESERVE_EUR
    record(journal, type="start", sourceCommit=args.sha, hardStop=STOP.isoformat(),
           estimatedReservedEur=round(reservations, 4), actualProviderBillEur=None)
    last_dispatched = [r for r in history if r.get("type") == "dispatched"]
    last_dispatch = (datetime.fromisoformat(last_dispatched[-1]["at"])
                     if last_dispatched else None)
    try:
        while now() + timedelta(seconds=RUNNER_HEADROOM_SECONDS) < STOP:
            verify_remote(args.sha)
            latest = recent_runs()
            if not verified_owned(journal, latest):
                time.sleep(45)
                continue
            active = [row for row in latest if row["status"] in
                      ("queued", "in_progress", "waiting", "pending")]
            if active or (last_dispatch and (now() - last_dispatch).total_seconds() < MIN_GAP_SECONDS):
                time.sleep(45)
                continue
            epoch = next((value for value in range(args.start_epoch,
                           args.start_epoch + args.max_epochs) if value not in attempted), None)
            if epoch is None:
                record(journal, type="all-epochs-complete")
                break
            if reservations + RESERVE_EUR > args.max_estimate_eur:
                record(journal, type="reservation-cap", estimatedReservedEur=round(reservations, 4))
                break
            record(journal, type="dispatch-attempt", epoch=epoch,
                   estimatedIncrementEur=RESERVE_EUR)
            attempted.add(epoch)
            reservations += RESERVE_EUR
            before = now()
            gh(["workflow", "run", WORKFLOW, "--repo", REPO, "--ref", BRANCH,
                "-f", "workload=chaos-lab", "-f", f"epoch={epoch}", "-f", f"source_sha={args.sha}"])
            run_id = locate_new_run(before, args.sha, {run["databaseId"] for run in latest})
            record(journal, type="dispatched", epoch=epoch, runId=run_id,
                   url=f"https://github.com/{REPO}/actions/runs/{run_id}",
                   estimatedReservedEur=round(reservations, 4))
            last_dispatch = now()
        # If the last wave completes before cutoff, verify it too.
        if now() + timedelta(seconds=20) < STOP:
            verified_owned(journal, recent_runs())
    except Exception as error:
        record(journal, type="stopped-on-error", reason=str(error)[:100])
    finally:
        # Keep only this controller's durable tmux process alive for the hard
        # stop. Earlier admissions do not license a job to run after 18:00Z.
        while now() < STOP:
            time.sleep(min(45, max(1, (STOP-now()).total_seconds())))
        if now() >= STOP:
            cancel_own_active(journal)
        record(journal, type="finish", estimatedReservedEur=round(reservations, 4),
               actualProviderBillEur=None)
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


if __name__ == "__main__":
    main()
