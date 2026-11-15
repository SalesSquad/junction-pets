#!/usr/bin/env python3
"""Two-child, same-future experiment from an owned paused practice world.

Never creates/advances a parent, enters a board/final, deletes a world, or fits
a model. The official fork contract supplies the same future draws; observable
snapshot/history hashes verify the common starting state, not hidden RNG state.
Fork delivery uncertainty stops safely instead of issuing a duplicate fork.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any

from spread import starter
from spread.client import Client

from official_study import atomic_json, export_world, provenance, read_json
from reliability_experiment import MODES, ReliabilityDesk, features_for, load_model


FORK_CONTRACT = "https://spread.bahnexpress.com/kit/API.md#practice-worlds"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def save(path: Path, value: Any) -> None:
    atomic_json(path, value)
    # The world ID must survive a process crash before any child decision.
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def source_provenance(model_path: str | None) -> dict[str, Any]:
    result = provenance(model_path)
    result["files_sha256"]["fork_study.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    import spread.client
    import spread.types
    result["sdk_files_sha256"] = {
        Path(module.__file__).name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in (spread.client, spread.types, starter)
    }
    return result


def require_practice(summary: dict[str, Any], *, allow_ended: bool = False,
                     parent_id: str | None = None) -> None:
    if summary.get("kind") != "practice" or "boardRun" not in summary \
            or summary["boardRun"] is not None or summary.get("season") is not None:
        raise ValueError("Only explicitly unranked owned practice worlds are permitted")
    if type(summary.get("ended")) is not bool or (summary["ended"] and not allow_ended):
        raise ValueError("An ended or unverified world cannot be forked/started")
    if parent_id is not None and summary.get("parent") != parent_id:
        raise ValueError("Child does not have the recorded parent")
    if type(summary.get("level")) is not int or not 1 <= summary["level"] <= 8:
        raise ValueError("Invalid official practice level")


def find_world(worlds: list[dict[str, Any]], world_id: str) -> dict[str, Any]:
    matches = [item for item in worlds if item.get("worldId") == world_id]
    if len(matches) != 1:
        raise ValueError(f"World {world_id} is not uniquely visible in this team's worlds")
    return matches[0]


def state_fingerprint(snapshot: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    if type(snapshot.get("now")) is not int or type(snapshot.get("endsAt")) is not int:
        raise ValueError("Snapshot has no verified integer clock")
    sequences = [event["seq"] for event in history]
    if sequences != sorted(set(sequences)) or any(event["at"] > snapshot["now"] for event in history):
        raise ValueError("History must be unique, chronological, and no later than the snapshot")
    public_state = {key: value for key, value in snapshot.items() if key != "worldId"}
    return {"now": snapshot["now"], "ends_at": snapshot["endsAt"],
            "snapshot_sha256": digest(public_state), "history_sha256": digest(history),
            "history_count": len(history), "last_seq": sequences[-1] if sequences else -1}


def read_stable_state(world: Any) -> tuple[dict, list, dict]:
    first = world.snapshot()
    history = world.events()
    second = world.snapshot()
    if digest(first) != digest(second):
        raise ValueError("World changed while reading it; stop its other writer first")
    return second, history, state_fingerprint(second, history)


def _family_root(world_id: str, worlds: list[dict[str, Any]]) -> str:
    lookup = {world["worldId"]: world for world in worlds}
    visited = set()
    while world_id in lookup and lookup[world_id].get("parent"):
        if world_id in visited:
            raise ValueError("World ancestry contains a cycle")
        visited.add(world_id)
        world_id = lookup[world_id]["parent"]
    return world_id


def check_model_separation(model: Any, parent_id: str, worlds: list[dict[str, Any]],
                           seed_group: str | None) -> None:
    if model is None:
        return
    root = _family_root(parent_id, worlds)
    if any(_family_root(world_id, worlds) == root for world_id in model.training["world_ids"]):
        raise ValueError("Model training overlaps this parent/fork family")
    training_groups = model.training.get("seed_groups", [])
    if seed_group is not None and seed_group in training_groups:
        raise ValueError("Model training overlaps the declared seed group")


def _verify_parent(parent: Any, expected: dict[str, Any]) -> None:
    snapshot, _, fingerprint = read_stable_state(parent)
    if snapshot["now"] >= snapshot["endsAt"] or fingerprint != expected:
        raise ValueError("Parent no longer has the pinned paused starting state")


def _verify_child(client: Any, child_id: str, receipt: dict) -> tuple[dict, list]:
    summary = find_world(client.worlds(), child_id)
    require_practice(summary, parent_id=receipt["config"]["parent_id"])
    if summary["level"] != receipt["parent"]["level"]:
        raise ValueError("Child level differs from parent")
    snapshot, history, fingerprint = read_stable_state(client.world(child_id))
    if fingerprint != receipt["parent"]["fingerprint"]:
        raise ValueError("Child does not have the exact pinned public state/history")
    return snapshot, history


def ensure_child(client: Any, parent: Any, receipt: dict, role: str, path: Path,
                 recover_id: str | None = None) -> None:
    child = receipt["children"].setdefault(role, {"state": "not_created"})
    if child.get("world_id"):
        if recover_id and recover_id != child["world_id"]:
            raise ValueError("Recovery cannot replace an already recorded child")
        return
    _verify_parent(parent, receipt["parent"]["fingerprint"])
    worlds = client.worlds()
    if child["state"] != "not_created":
        # A successful request can lose its response. Never repeat that POST.
        before = set(child.get("world_ids_before", []))
        candidates = [item["worldId"] for item in worlds
                      if item.get("parent") == parent.id and item["worldId"] not in before]
        child["reconciliation_candidates"] = candidates
        save(path, receipt)
        if recover_id is None or recover_id not in candidates:
            raise ValueError(f"Uncertain {role} fork was not retried; inspect recorded candidates and use --recover-{role}")
        other_ids = {item.get("world_id") for item in receipt["children"].values()}
        if recover_id in other_ids:
            raise ValueError("Both policies cannot use the same child")
        _verify_child(client, recover_id, receipt)
        child.update(world_id=recover_id, state="created", recovered_at_unix=time.time())
        save(path, receipt)
        return
    if recover_id:
        raise ValueError("Recovery requires an existing uncertain fork intent")
    active = sum(item.get("kind") == "practice" and not item.get("ended", True) for item in worlds)
    missing = sum(not item.get("world_id") for item in receipt["children"].values())
    if active + missing > 8:
        raise ValueError("Insufficient official practice slots for both children")
    child.update(state="fork_intent", world_ids_before=[item["worldId"] for item in worlds],
                 requested_at_unix=time.time())
    save(path, receipt)
    try:
        result = parent.fork()
    except BaseException as error:
        child.update(state="fork_delivery_unknown", error_type=type(error).__name__)
        save(path, receipt)
        raise
    # Save the returned ID before validation, desk creation, or any action.
    child.update(world_id=result.id, state="created", created_at_unix=time.time())
    save(path, receipt)
    if result.id == parent.id or any(item.get("world_id") == result.id
                                     for name, item in receipt["children"].items() if name != role):
        raise ValueError("Fork returned a duplicate child/parent identity; no child was played")
    _verify_child(client, result.id, receipt)
    _verify_parent(parent, receipt["parent"]["fingerprint"])


def play_child(client: Any, receipt: dict, role: str, output: Path, receipt_path: Path,
               model_path: str | None) -> None:
    child = receipt["children"][role]
    if child.get("state") == "completed":
        return
    world = client.world(child["world_id"])
    summary = find_world(client.worlds(), world.id)
    require_practice(summary, allow_ended=child.get("state") != "created",
                     parent_id=receipt["config"]["parent_id"])
    snapshot, history, fingerprint = read_stable_state(world)
    if child.get("state") == "created" and fingerprint != receipt["parent"]["fingerprint"]:
        raise ValueError("Child changed after pair verification and before its first action")
    config = receipt["config"]
    if snapshot["now"] < snapshot["endsAt"] and (
        child.get("steps", 0) >= config["max_steps"]
        or child.get("elapsed_seconds", 0) >= config["max_wall_seconds"]
    ):
        child.update(state="paused_bound", observed_now=snapshot["now"])
        save(receipt_path, receipt)
        return
    policy = "baseline" if role == "baseline" else config["candidate"]
    feature_path = output / role / "decision_features.jsonl"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    child.update(state="running", observed_now=snapshot["now"])
    save(receipt_path, receipt)

    class RecordedDesk(ReliabilityDesk):
        def quote(self, request: dict[str, Any]) -> None:
            rows = [{"world_id": world.id, "parent_world_id": config["parent_id"],
                     "seed_group": receipt["future_group"], "policy": policy,
                     "partition": "development", "experiment": "same_future_fork",
                     "order_id": request["id"], "option": option["kind"], "at": self.now,
                     "features": features_for(request, option, self)}
                    for option in request["options"] if self.now < request["respondBy"]]
            super().quote(request)
            quote = next((action for action in reversed(self.outbox)
                          if action.get("type") == "quote" and action.get("requestId") == request["id"]), {})
            if rows:
                with feature_path.open("a", encoding="utf-8") as stream:
                    for row in rows:
                        row["quoted_price"] = quote.get("prices", {}).get(row["option"])
                        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

    started = time.monotonic()
    try:
        if snapshot["now"] < snapshot["endsAt"]:
            desk = RecordedDesk(world, summary["level"], snapshot["now"], mode=policy,
                                model_path=model_path if role == "candidate" else None,
                                late_threshold=config["late_threshold"])
            # Rebuild trust, ledger, reservations, current gigs and seen seqs.
            # First child advance repeats all history; seen prevents double use.
            desk.rejoin(copy.deepcopy(snapshot), copy.deepcopy(history))
            while desk.now < snapshot["endsAt"]:
                if child.get("steps", 0) >= config["max_steps"] \
                        or child.get("elapsed_seconds", 0) + time.monotonic() - started >= config["max_wall_seconds"]:
                    child.update(state="paused_bound", observed_now=desk.now)
                    break
                before = desk.now
                actions, desk.outbox = desk.outbox, []
                child.update(last_intent_at=before, last_actions_sha256=digest(actions),
                             steps=child.get("steps", 0) + 1)
                save(receipt_path, receipt)
                step = world.advance(until=starter.WAKE_ON,
                                     max=min(snapshot["endsAt"], (desk.now // 1440 + 1) * 1440),
                                     actions=actions)
                if not before <= step["now"] <= snapshot["endsAt"]:
                    raise ValueError("Official child clock moved outside the allowed interval")
                child["action_failures"] = child.get("action_failures", 0) + sum(
                    result.get("ok") is False for result in step["results"])
                desk.read_results(actions, step["results"])
                desk.now = step["now"]
                for event in step["events"]:
                    desk.handle(event)
                child["observed_now"] = desk.now
            if desk.now >= snapshot["endsAt"]:
                child["state"] = "completed"
        else:
            child["state"] = "completed"  # interrupted after last acknowledged advance
        child["score"] = world.score()
    except BaseException as error:
        child.update(state="interrupted", error_type=type(error).__name__)
        raise
    finally:
        child["elapsed_seconds"] = child.get("elapsed_seconds", 0) + time.monotonic() - started
        save(receipt_path, receipt)


def run(args: argparse.Namespace, client: Any | None = None) -> dict:
    if args.candidate not in MODES or not 1 <= args.max_steps <= 50000 \
            or not 1 <= args.max_wall_seconds <= 3600 or not 1 <= args.max_minutes <= 20160:
        raise ValueError("Invalid candidate or bounded experiment limits")
    if args.late_threshold is not None and (not math.isfinite(args.late_threshold)
                                          or not 0 < args.late_threshold < 1):
        raise ValueError("late threshold must be strictly between zero and one")
    model = load_model(args.model) if args.model else None
    if args.candidate == "learned" and model is None:
        raise ValueError("learned candidate requires an explicit model")
    if os.getenv("SPREAD_GUARD_POLICY", "risk_budget") != "risk_budget":
        raise ValueError("Frozen risk_budget policy is required")
    # Environment-only model/thresholds would escape the recorded configuration.
    if os.getenv("SPREAD_RELIABILITY_MODEL") or os.getenv("SPREAD_RELIABILITY_LATE_THRESHOLD"):
        raise ValueError("Pass model/threshold explicitly, without reliability environment overrides")
    source = source_provenance(args.model)
    config = {"parent_id": args.parent, "candidate": args.candidate,
              "seed_group": args.seed_group, "source": source,
              "late_threshold": args.late_threshold, "max_steps": args.max_steps,
              "max_wall_seconds": args.max_wall_seconds, "max_minutes": args.max_minutes}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "fork_run.json"
    with (output / ".fork_study.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        receipt = read_json(path) if path.exists() else None
        if receipt and receipt["config"] != config:
            raise ValueError("Resume source/configuration differs from the frozen receipt")
        if receipt and receipt.get("state") == "completed":
            return receipt
        client = client or Client()
        worlds = client.worlds()
        summary = find_world(worlds, args.parent)
        require_practice(summary)
        check_model_separation(model, args.parent, worlds, args.seed_group)
        parent = client.world(args.parent)
        if receipt is None:
            snapshot, history, fingerprint = read_stable_state(parent)
            remaining = snapshot["endsAt"] - snapshot["now"]
            if not 0 < remaining <= args.max_minutes:
                raise ValueError("Parent is ended or remaining simulation exceeds --max-minutes")
            receipt = {"schemaVersion": 1, "state": "prepared", "config": config,
                       "created_at_unix": time.time(),
                       "parent": {"world_id": args.parent, "level": summary["level"],
                                  "fingerprint": fingerprint, "initial_score": snapshot.get("score")},
                       "future_group": f"fork:{args.parent}:{fingerprint['snapshot_sha256'][:16]}",
                       "seed": args.seed_group, "seed_provenance": "caller_label" if args.seed_group else "unknown",
                       "same_future_evidence": {"official_contract": FORK_CONTRACT,
                                                "hidden_rng_observed": False},
                       "children": {role: {"state": "not_created"} for role in ("baseline", "candidate")}}
            save(output / "parent_snapshot.json.gz", snapshot)
            save(output / "parent_history.json.gz", history)
            save(path, receipt)
        for role in ("baseline", "candidate"):
            ensure_child(client, parent, receipt, role, path, getattr(args, f"recover_{role}", None))
        child_ids = [item["world_id"] for item in receipt["children"].values()]
        if len(set(child_ids)) != 2 or args.parent in child_ids:
            raise ValueError("Two distinct child worlds are required")
        if receipt["state"] != "pair_verified":
            for role in ("baseline", "candidate"):
                if receipt["children"][role]["state"] == "created":
                    _verify_child(client, receipt["children"][role]["world_id"], receipt)
            receipt["state"] = "pair_verified"
            save(path, receipt)
        # Both child IDs and their equal starting state are durable before play.
        for role in ("baseline", "candidate"):
            if source_provenance(args.model) != source:
                raise ValueError("Decision source/model changed during the experiment")
            play_child(client, receipt, role, output, path, args.model)
        if source_provenance(args.model) != source:
            raise ValueError("Decision source/model changed during the experiment")
        if all(item["state"] == "completed" for item in receipt["children"].values()):
            # Reveal only after BOTH fixed-policy runs finish; never a feature.
            for role, child in receipt["children"].items():
                child["evidence"] = export_world(client, child["world_id"], output / role,
                                                 receipt["future_group"],
                                                 "baseline" if role == "baseline" else args.candidate, source)
            baseline, candidate = (receipt["children"][role]["score"] for role in ("baseline", "candidate"))
            receipt["comparison"] = {
                "margin_delta_cents": candidate["marginCents"] - baseline["marginCents"],
                "on_time_delta_percentage_points": 100 * (candidate["onTimeShare"] - baseline["onTimeShare"]),
                "won_orders_delta": candidate["wonOrders"] - baseline["wonOrders"],
                "scope": "one shared-future conditional comparison; not independent worlds or final qualification",
            }
            receipt["state"] = "completed"
            save(path, receipt)
        return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--candidate", choices=MODES, required=True)
    parser.add_argument("--seed-group", help="Optional owner-provided label; API does not expose the seed")
    parser.add_argument("--model")
    parser.add_argument("--late-threshold", type=float)
    parser.add_argument("--max-steps", type=int, default=10000)
    parser.add_argument("--max-wall-seconds", type=int, default=900)
    parser.add_argument("--max-minutes", type=int, default=20160)
    parser.add_argument("--recover-baseline")
    parser.add_argument("--recover-candidate")
    args = parser.parse_args()
    print(json.dumps(run(args), sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
