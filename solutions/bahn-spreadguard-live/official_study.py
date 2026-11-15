#!/usr/bin/env python3
"""Source-bound, unranked Spread experiments and read-only evidence export.

No board/final entrypoint is exposed. Credentials come only from the official
SDK environment. Each created world ID is durably recorded before play, and an
interrupted run is resumed rather than silently recreated. No worlds are deleted.
"""
from __future__ import annotations

import argparse
import copy
import csv
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from spread import starter
from spread.client import Client


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    with open(temporary, "wb") as stream:
        stream.write(gzip.compress(data, mtime=0) if path.suffix == ".gz" else data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def read_json(path: Path) -> Any:
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def provenance(model: str | None = None) -> dict[str, Any]:
    here = Path(__file__).resolve().parent
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here,
                            capture_output=True, text=True)
    names = ["official_study.py", "dispatch.py", "discovery_experiment.py",
             "admission_experiment.py", "reliability_experiment.py", "typed_notes.py",
             "notes_experiment.py"]
    hashes = {name: hashlib.sha256((here / name).read_bytes()).hexdigest()
              for name in names if (here / name).exists()}
    return {"source_sha": result.stdout.strip() if result.returncode == 0 else None,
            "files_sha256": hashes,
            "model_sha256": hashlib.sha256(Path(model).read_bytes()).hexdigest() if model else None,
            "sdk_version": "0.1.0"}


def export_world(client: Client, world_id: str, output: Path, seed: str,
                 policy: str, source: dict | None = None) -> dict:
    world = client.world(world_id)
    snapshot = world.snapshot()
    if snapshot["now"] < snapshot["endsAt"]:
        raise ValueError("Export requires a completed world; no clock is advanced by export")
    bundle = {"schemaVersion": 1, "world_id": world_id, "seed_group": seed,
              "policy": policy, "source": source or {}, "score": world.score(),
              "snapshot": snapshot, "events": world.events(),
              "reveal": world.reveal(), "roster": world.roster(), "map": client.map()}
    target = output / (world_id + ".json.gz")
    atomic_json(target, bundle)
    return {"world_id": world_id, "seed_group": seed, "policy": policy,
            "bundle": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "score": bundle["score"], "event_count": len(bundle["events"])}


def resolve_configuration(args: argparse.Namespace) -> None:
    """Freeze effective environment defaults before any sponsor mutation."""
    from reliability_experiment import DEFAULT_LATE_THRESHOLD, _threshold, load_model

    args.model = args.model or os.getenv("SPREAD_RELIABILITY_MODEL") or None
    model = load_model(args.model) if args.model else None
    if args.policy == "learned" and model is None:
        raise ValueError("learned policy requires --model")
    if args.policy == "notes" and model is not None:
        raise ValueError("notes policy cannot be combined with a learned model")
    threshold = args.late_threshold
    if threshold is None and os.getenv("SPREAD_RELIABILITY_LATE_THRESHOLD"):
        threshold = float(os.environ["SPREAD_RELIABILITY_LATE_THRESHOLD"])
    args.late_threshold = _threshold(threshold if threshold is not None else
                                    model.threshold if model else DEFAULT_LATE_THRESHOLD)
    if os.getenv("SPREAD_GUARD_POLICY", "risk_budget") != "risk_budget":
        raise ValueError("reliability ablations require the frozen risk_budget fee policy")


def run_practice(args: argparse.Namespace) -> None:
    resolve_configuration(args)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    # Two invocations must never create/play different worlds in one receipt
    # directory or interleave decision rows. Fails before opening the client.
    with (output / ".study.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _run_practice_locked(args)


def _run_practice_locked(args: argparse.Namespace) -> None:
    from reliability_experiment import ReliabilityDesk, features_for

    resolve_configuration(args)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "run.json"
    feature_path = output / "decision_features.jsonl"
    source = provenance(args.model)
    config = {"seed_group": args.seed, "policy": args.policy,
              "partition": args.partition, "model_sha256": source["model_sha256"],
              "files_sha256": source["files_sha256"], "late_threshold": args.late_threshold}
    prior = read_json(receipt_path) if receipt_path.exists() else None
    if prior and prior["config"] != config:
        raise ValueError("Existing run receipt configuration differs; choose a new output directory")
    if prior and prior.get("state") == "completed":
        print(json.dumps(prior, sort_keys=True), flush=True)
        return
    client = Client()
    if prior:
        if "world_id" not in prior:
            raise ValueError("World creation may have succeeded without a receipt; reconcile the recorded creation intent before retrying")
        world = client.world(prior["world_id"])
    else:
        prior = {"schemaVersion": 1, "state": "creation_pending", "config": config,
                 "source": source, "created_at_unix": time.time(),
                 "world_ids_before": [row["worldId"] for row in client.worlds()]}
        atomic_json(receipt_path, prior)
        world = client.create(level=8, seed=args.seed, board=False)
        prior.update(state="created", world_id=world.id)
        atomic_json(receipt_path, prior)
    print("WORLD_BOUND " + world.id + " " + args.policy + " " + args.seed, flush=True)
    snapshot = world.snapshot()

    if args.policy == "notes":
        from notes_experiment import NotesDesk
        policy_class = NotesDesk
    else:
        policy_class = ReliabilityDesk

    class RecordedDesk(policy_class):
        def quote(self, request: dict[str, Any]) -> None:
            if self.now < request["respondBy"]:
                records = [{"world_id": world.id, "seed_group": args.seed,
                            "policy": args.policy, "partition": args.partition,
                            "order_id": request["id"], "option": option["kind"],
                            "at": self.now, "features": features_for(request, option, self)}
                           for option in request["options"]]
            else:
                records = []
            super().quote(request)
            quote = next((action for action in reversed(self.outbox)
                          if action.get("type") == "quote"
                          and action.get("requestId") == request["id"]), None)
            if records:
                with open(feature_path, "a", encoding="utf-8") as stream:
                    for record in records:
                        record["quoted_price"] = (quote or {}).get("prices", {}).get(record["option"])
                        stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()

    desk = RecordedDesk(world, 8, snapshot["now"], mode=args.policy,
                        model_path=args.model, late_threshold=args.late_threshold)
    if prior["state"] != "created" or snapshot["now"] > 0:
        desk.rejoin(snapshot, world.events())
    prior["state"] = "running"
    atomic_json(receipt_path, prior)
    elapsed, handled, max_decision_ms, action_failures = time.monotonic(), 0, 0.0, 0
    try:
        while desk.now < snapshot["endsAt"]:
            actions, desk.outbox = desk.outbox, []
            step = world.advance(until=starter.WAKE_ON,
                                 max=min(snapshot["endsAt"], (desk.now // 1440 + 1) * 1440),
                                 actions=actions)
            action_failures += sum(result.get("ok") is False for result in step["results"])
            desk.read_results(actions, step["results"])
            desk.now = step["now"]
            for event in step["events"]:
                before = time.perf_counter()
                desk.handle(event)
                max_decision_ms = max(max_decision_ms, (time.perf_counter() - before) * 1000)
                handled += 1
        evidence = export_world(client, world.id, output, args.seed, args.policy, source)
        prior.update(state="completed", evidence=evidence, elapsed_seconds=time.monotonic() - elapsed,
                     events_handled=handled, max_handler_ms=max_decision_ms,
                     action_failures=action_failures, completed_at_unix=time.time())
        prior["policy_counts"] = dict(desk.counts)
        if hasattr(desk, "notes_summary"):
            prior["notes"] = desk.notes_summary()
        atomic_json(receipt_path, prior)
        print("RUN_COMPLETE " + json.dumps(prior, sort_keys=True), flush=True)
    except BaseException as error:
        prior.update(state="interrupted", error_type=type(error).__name__, observed_now=desk.now)
        atomic_json(receipt_path, prior)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    export = subs.add_parser("export")
    export.add_argument("--world", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--seed", required=True)
    export.add_argument("--policy", required=True)
    run = subs.add_parser("run")
    run.add_argument("--seed", required=True)
    run.add_argument("--policy", choices=["baseline", "deadline", "capacity", "learned", "trust", "notes"], required=True)
    run.add_argument("--partition", choices=["development", "blind"], required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--model")
    run.add_argument("--late-threshold", type=float, default=None)
    args = parser.parse_args()
    if args.command == "export":
        print(json.dumps(export_world(Client(), args.world, Path(args.output), args.seed, args.policy), sort_keys=True))
    else:
        run_practice(args)


if __name__ == "__main__":
    main()
