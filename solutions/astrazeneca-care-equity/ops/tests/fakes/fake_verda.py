#!/usr/bin/env python3
"""Fake `verda` CLI for ops/tests. It never opens a network connection.

State and scripted behaviour live in $FAKE_VERDA_DIR:
  scenario.json  what to do (prices, the result of each `vm create` in order, delete results,
                 machines that exist already and do not belong to the tool)
  state.json     machines and counters
  calls.jsonl    every invocation, one JSON object per line

Error output follows the shape observed from verda 1.10.0 on 2026-11-14 with read-only calls:
  stderr {"error": {"code": ..., "message": ..., "details": {"status": <http>}}}
  exit 4 for API_ERROR, 5 for NOT_FOUND, 3 for AUTH_ERROR.
The 503 body text and the success output of create/delete were NOT captured from the real
service (nothing was created while this tool was written); they are modelled here.
"""
import fcntl
import json
import os
import sys
import time
import uuid
from pathlib import Path

D = Path(os.environ["FAKE_VERDA_DIR"])


def fail(code, message, status=None, rc=4):
    err = {"code": code, "message": message}
    if status is not None:
        err["details"] = {"status": status}
    sys.stderr.write(json.dumps({"error": err}, indent=2) + "\n")
    sys.exit(rc)


def not_found(what="Instance"):
    fail("NOT_FOUND", json.dumps({"code": "not_found", "message": f"{what} not found"}), 404, rc=5)


class State:
    def __enter__(self):
        self.lock = open(D / "state.lock", "w")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        p = D / "state.json"
        self.s = json.loads(p.read_text()) if p.exists() else None
        if self.s is None:
            self.s = {"vms": {}, "creates": 0, "deletes": 0}
            for i, row in enumerate(SCENARIO.get("existing", [])):
                vid = row.get("id") or str(uuid.UUID(int=i + 1))
                self.s["vms"][vid] = {"id": vid, "hostname": row["hostname"], "status": row.get("status", "running"),
                                      "statuses": [row.get("status", "running")], "describes": 0, "ip": f"10.66.0.{i + 1}",
                                      "instance_type": row.get("instance_type", "other"), "location": "FIN-01",
                                      "is_spot": False, "deleted": False, "volumes_deleted": False, "foreign": True,
                                      "os_volume_id": str(uuid.uuid4())}
        return self.s

    def __exit__(self, *exc):
        tmp = D / "state.json.tmp"
        tmp.write_text(json.dumps(self.s, indent=1))
        os.replace(tmp, D / "state.json")
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()


def flag(args, name, default=None):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def public(vm):
    return {"id": vm["id"], "hostname": vm["hostname"], "status": vm["status"], "instance_type": vm["instance_type"],
            "location": vm["location"], "ip": vm["ip"] if vm["status"] == "running" else None, "is_spot": vm["is_spot"],
            "os_volume_id": vm["os_volume_id"], "volume_ids": [vm["os_volume_id"]]}


def main():
    argv = sys.argv[1:]
    with open(D / "calls.jsonl", "a") as f:
        f.write(json.dumps({"argv": argv, "t": time.time()}) + "\n")
    if not argv or argv[0] != "--agent" or argv[-2:] != ["-o", "json"]:
        fail("FAKE_CONTRACT", "the tool must call `verda --agent ... -o json`", rc=64)
    args = argv[1:-2]
    if args[:1] == ["--timeout"]:
        args = args[2:]
    cmd = tuple(args[:2])

    if cmd == ("cost", "estimate"):
        itype = flag(args, "--type")
        prices = SCENARIO.get("prices", {}).get(itype)
        if not prices:
            fail("API_ERROR", f'API error 400: {{"code":"invalid_request","message":"unknown instance type {itype}"}}', 400)
        hourly = prices["spot" if "--spot" in args else "ondemand"]
        print(json.dumps({"instance_type": itype, "instance": {"hourly": hourly}, "os_volume": {"hourly": 0.0},
                          "total": {"hourly": hourly, "daily": hourly * 24}}))
        return

    if cmd == ("vm", "list"):
        with State() as s:
            print(json.dumps([public(v) for v in s["vms"].values() if not v["deleted"]]))
        return

    if cmd == ("vm", "create"):
        missing = [k for k in ("--kind", "--instance-type", "--os", "--hostname") if flag(args, k) is None]
        if missing:
            fail("MISSING_REQUIRED_FLAGS", "missing flags", rc=2)
        with State() as s:
            plan = SCENARIO.get("create") or [{"result": "ok"}]
            spec = plan[min(s["creates"], len(plan) - 1)]
            s["creates"] += 1
            result = spec.get("result", "ok")
            vm = None
            if result in ("ok", "ok_no_id", "timeout_created", "slow_created", "503_created", "ok_foreign_id"):
                vid = str(uuid.uuid4())
                statuses = spec.get("statuses", ["provisioning", "running"])
                vm = {"id": vid, "hostname": flag(args, "--hostname"), "status": statuses[0], "statuses": statuses,
                      "describes": 0, "ip": f"10.77.0.{s['creates']}", "instance_type": flag(args, "--instance-type"),
                      "location": flag(args, "--location", "FIN-01"), "is_spot": "--is-spot" in args, "deleted": False,
                      "volumes_deleted": False, "foreign": False, "os_volume_id": str(uuid.uuid4()),
                      "spot_policy": flag(args, "--os-volume-on-spot-discontinue")}
                s["vms"][vid] = vm
        if result in ("503", "503_created"):  # 503_created: a gateway answers 503 although the API created the machine
            fail("API_ERROR", 'API error 503: {"code":"service_unavailable","message":"Not enough resources available"}', 503)
        if result == "validation":
            fail("API_ERROR", 'API error 400: {"code":"invalid_request","message":"image not available"}', 400)
        if result in ("timeout", "timeout_created"):
            fail("API_ERROR", 'Post "https://api.invalid/v1/instances": context deadline exceeded '
                              "(Client.Timeout exceeded while awaiting headers)")
        if result == "slow_created":
            time.sleep(spec.get("delay", 30))
        if result == "ok_no_id":
            print(json.dumps({"status": "accepted"}))
            return
        if result == "ok_foreign_id":  # create output carrying the id of a machine that is not the new one
            with State() as s:
                foreign = next(v for v in s["vms"].values() if v["foreign"])
            print(json.dumps({"id": foreign["id"], "status": "accepted"}))
            return
        print(json.dumps({"id": vm["id"], "hostname": vm["hostname"], "status": "accepted"}))
        return

    if cmd == ("vm", "describe"):
        with State() as s:
            vm = s["vms"].get(args[2]) if len(args) > 2 else None
            if vm is not None and vm["foreign"] and SCENARIO.get("describe_fails_for_foreign"):
                fail("API_ERROR", 'API error 500: {"code":"internal","message":"describe failed"}', 500)
            if vm is not None and vm["deleted"] and SCENARIO.get("describe_fails_after_delete"):
                fail("API_ERROR", 'API error 500: {"code":"internal","message":"describe failed"}', 500)
            if vm is None or vm["deleted"]:
                not_found()
            i = min(vm["describes"], len(vm["statuses"]) - 1)
            vm["status"] = vm["statuses"][i]
            vm["describes"] += 1
            print(json.dumps(public(vm)))
        return

    if cmd == ("vm", "delete"):
        if "--yes" not in args:
            fail("CONFIRMATION_REQUIRED", 'destructive action "delete" requires --yes in agent mode', rc=2)
        with State() as s:
            plan = SCENARIO.get("delete") or [{"result": "ok"}]
            spec = plan[min(s["deletes"], len(plan) - 1)]
            s["deletes"] += 1
            targets = [args[2]] if len(args) > 2 and not args[2].startswith("-") else []
            if "--all" in args:  # the tool must never do this; if it did, the damage would be visible
                targets = [v["id"] for v in s["vms"].values() if not v["deleted"]]
            if spec.get("result") == "fail":
                fail("API_ERROR", 'API error 500: {"code":"internal","message":"delete failed"}', 500)
            for vid in targets:
                vm = s["vms"].get(vid)
                if vm is None or vm["deleted"]:
                    not_found()
                vm["deleted"] = True
                vm["volumes_deleted"] = "--with-volumes" in args
            print(json.dumps({"ids": targets, "status": "completed"}))
        return

    if cmd == ("volume", "describe"):
        with State() as s:
            for vm in s["vms"].values():
                if vm["os_volume_id"] == (args[2] if len(args) > 2 else None):
                    if vm["volumes_deleted"]:
                        not_found("Volume")
                    print(json.dumps({"id": vm["os_volume_id"], "status": "detached" if vm["deleted"] else "attached"}))
                    return
        not_found("Volume")

    fail("FAKE_UNKNOWN_COMMAND", "fake verda does not implement: " + " ".join(args), rc=64)


SCENARIO = json.loads((D / "scenario.json").read_text())
main()
