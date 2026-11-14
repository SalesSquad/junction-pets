#!/usr/bin/env python3
"""Bounded CRACI Immune tournament dispatcher. No provider secrets or top-ups.

Uses the existing authenticated GitHub CLI on the owner's verified Mac Mini.
The journal is append-only and makes dispatch ambiguity a STOP, never a retry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = "SalesSquad/junction-pets"
WORKFLOW = "craci-pilot.yml"
BRANCH = "codex/craci-immune-20261114-3h"
STAGES = 12
INTERVAL_SECONDS = 15 * 60
GUARD_SECONDS = 16 * 60
# Conservatively above the observed list rate: two 2-vCPU planning minutes*5
# plus 4 runners x 4-vCPU x 15 minutes, at EUR 0.0025/vCPU-minute.
MAX_RESERVED_EUR_PER_DISPATCH = (2 * 5 + 4 * 4 * 15) * 0.0025


def utc_now():
    return datetime.now(timezone.utc)


def invoke(arguments, timeout=45):
    result = subprocess.run(["gh", *arguments], text=True, capture_output=True,
                            timeout=timeout, check=False)
    if result.returncode != 0:
        # GitHub output can include URLs/diagnostics; do not copy it to the
        # durable log, which contains only short non-sensitive error codes.
        raise RuntimeError(f"GH_EXIT_{result.returncode}")
    return result.stdout.strip()


def github_json(arguments):
    return json.loads(invoke(arguments))


def log_event(path, event):
    entry = {"at": utc_now().isoformat(), **event}
    with path.open("a", encoding="utf8") as file:
        file.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        file.flush()
    print(json.dumps(entry, sort_keys=True), flush=True)


def read_history(path):
    if not path.exists():
        return []
    with path.open(encoding="utf8") as file:
        return [json.loads(line) for line in file if line.strip()]


def runs():
    return github_json(["run", "list", "--repo", REPO, "--workflow", WORKFLOW,
                        "--limit", "100", "--json",
                        "databaseId,status,conclusion,event,headSha,createdAt,displayTitle"])


def connected_and_open(expected_sha):
    value = github_json(["api", f"repos/{REPO}/actions/variables/CRACI_CREDIT_WINDOW_OPEN"])
    if value.get("value") != "true":
        raise RuntimeError("CREDIT_WINDOW_CLOSED")
    ref = github_json(["api", f"repos/{REPO}/git/ref/heads/{BRANCH}"])
    if ref.get("object", {}).get("sha") != expected_sha:
        raise RuntimeError("HARNESS_SHA_CHANGED")


def find_run(after, expected_sha, exclude):
    for attempt in range(6):
        for run in runs():
            created = datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
            if (run["databaseId"] not in exclude and run["event"] == "workflow_dispatch"
                    and run["headSha"] == expected_sha
                    and "CRACI immune-tournament" in run["displayTitle"]
                    and created >= after - timedelta(seconds=12)):
                return run
        time.sleep(4)
    return None


def cancel_owned_active(path):
    history = read_history(path)
    own = {row["runId"] for row in history if row.get("type") == "dispatched"}
    if not own:
        return
    try:
        active = {row["databaseId"] for row in runs() if row["status"] in ("queued", "in_progress", "waiting", "pending")}
    except Exception as error:
        log_event(path, {"type": "stop-check-failed", "reason": str(error)})
        return
    for run_id in sorted(active & own):
        try:
            invoke(["run", "cancel", str(run_id), "--repo", REPO])
            log_event(path, {"type": "cancel-requested", "runId": run_id})
        except Exception as error:
            log_event(path, {"type": "cancel-failed", "runId": run_id, "reason": str(error)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--stop-at", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--max-eur", type=float, default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if len(args.sha) != 40 or not all(c in "0123456789abcdef" for c in args.sha):
        parser.error("full lower-case source SHA required")
    deadline = datetime.fromisoformat(args.stop_at.replace("Z", "+00:00"))
    if deadline.tzinfo is None or deadline <= utc_now() or deadline > utc_now() + timedelta(hours=3):
        parser.error("deadline must be in the next three hours")
    if not (0 < args.max_eur <= 300):
        parser.error("budget must be within the owner's 300 EUR cap")
    journal = Path(args.journal).resolve()
    if journal.parent != Path("/private/tmp") or not journal.name.startswith("craci-immune-"):
        parser.error("journal must be isolated in /private/tmp")
    start = utc_now()
    history = read_history(journal)
    used = {row["epoch"] for row in history if row.get("type") in ("dispatch-attempt", "dispatched")}
    reservations = sum(MAX_RESERVED_EUR_PER_DISPATCH for row in history if row.get("type") == "dispatch-attempt")
    log_event(journal, {"type": "start", "expectedSha": args.sha,
                        "stopAt": deadline.isoformat(), "reservedEstimateEur": round(reservations, 4)})
    try:
        for epoch in range(1, STAGES + 1):
            target = start + timedelta(seconds=(epoch - 1) * INTERVAL_SECONDS)
            while utc_now() < target and utc_now() < deadline:
                time.sleep(min(30, max(1, (target - utc_now()).total_seconds())))
            if utc_now() + timedelta(seconds=GUARD_SECONDS) >= deadline:
                log_event(journal, {"type": "deadline-guard", "epoch": epoch})
                break
            if epoch in used:
                continue
            connected_and_open(args.sha)
            current = runs()
            active = [row for row in current if row["status"] in ("queued", "in_progress", "waiting", "pending")]
            if active:
                log_event(journal, {"type": "skipped-capacity", "epoch": epoch, "activeRuns": len(active)})
                continue
            if reservations + MAX_RESERVED_EUR_PER_DISPATCH > args.max_eur:
                log_event(journal, {"type": "budget-stop", "epoch": epoch,
                                    "reservedEstimateEur": round(reservations, 4)})
                break
            # Record intent *before* side effect; unknown dispatch delivery stops
            # the controller and is never repeated automatically.
            log_event(journal, {"type": "dispatch-attempt", "epoch": epoch,
                                "maxAdditionalEstimateEur": MAX_RESERVED_EUR_PER_DISPATCH})
            used.add(epoch)
            reservations += MAX_RESERVED_EUR_PER_DISPATCH
            before = utc_now()
            invoke(["workflow", "run", WORKFLOW, "--repo", REPO, "--ref", BRANCH,
                    "-f", "workload=immune-tournament", "-f", f"epoch={epoch}",
                    "-f", f"source_sha={args.sha}"])
            found = find_run(before, args.sha, {row["databaseId"] for row in current})
            if found is None:
                log_event(journal, {"type": "in-doubt-stop", "epoch": epoch})
                break
            log_event(journal, {"type": "dispatched", "epoch": epoch, "runId": found["databaseId"],
                                "url": f"https://github.com/{REPO}/actions/runs/{found['databaseId']}",
                                "reservedTotalEstimateEur": round(reservations, 4)})
            if args.once:
                break
        while not args.once and utc_now() < deadline:
            time.sleep(min(30, max(1, (deadline - utc_now()).total_seconds())))
    except Exception as error:
        log_event(journal, {"type": "stopped-on-error", "reason": str(error)})
    finally:
        if not args.once and utc_now() >= deadline:
            cancel_owned_active(journal)
        log_event(journal, {"type": "finish", "reservedEstimateEur": round(reservations, 4),
                            "actualProviderBillEur": None})


if __name__ == "__main__":
    main()
