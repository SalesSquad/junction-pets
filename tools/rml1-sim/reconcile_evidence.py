#!/usr/bin/env python3
"""Reconcile separately executed RML1 developer receipts without inventing host qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import re

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 1_048_576
REQUIRED_JUNCTION = {
    "rust_sim_unit_tests", "rust_sim_parallel", "rust_sim_serial_replay",
    "rust_sim_byte_identical_replay",
    "junction_34_real_offline_capability_fixtures",
}

class Refused(ValueError):
    pass

def sha(value, length=40):
    if not isinstance(value, str) or not (SHA40 if length == 40 else SHA64).fullmatch(value):
        raise Refused("invalid_sha")
    return value

def read_receipt(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
        raise Refused("receipt_unavailable_or_oversized")
    raw = p.read_bytes()
    if len(raw) > MAX_BYTES:
        raise Refused("receipt_oversized")
    try:
        obj = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as e:
        raise Refused("receipt_not_json") from e
    if not isinstance(obj, dict):
        raise Refused("receipt_must_be_object")
    return obj, hashlib.sha256(raw).hexdigest()

def steps_by_name(data):
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) > 32:
        raise Refused("invalid_steps")
    if any(not isinstance(s, dict) or not isinstance(s.get("name"), str) for s in steps):
        raise Refused("invalid_step_entry")
    names = [s["name"] for s in steps]
    if len(set(names)) != len(names):
        raise Refused("duplicate_steps")
    return {s["name"]: s for s in steps}

def junction(data, source_sha, min_seeds):
    if data.get("schema") != "rml1.developer-integration/v1":
        raise Refused("wrong_junction_schema")
    if data.get("junction_source_sha") != sha(source_sha):
        raise Refused("junction_source_mismatch")
    if data.get("qualified") is not False or data.get("runtime_authorized") is not False or data.get("generated_r_executed") is not False:
        raise Refused("junction_authority_claim")
    if data.get("overall") not in ("pass", "incomplete"):
        raise Refused("junction_not_successful")
    by = steps_by_name(data)
    if not REQUIRED_JUNCTION.issubset(by) or any(by[k].get("status") != "pass" for k in REQUIRED_JUNCTION):
        raise Refused("junction_required_steps_not_passed")
    sim = data.get("simulation")
    if not isinstance(sim, dict) or type(sim.get("scenarios")) is not int or sim["scenarios"] < min_seeds:
        raise Refused("junction_seed_coverage")
    if sim.get("runtime_authorized") is not False or not re.fullmatch("[0-9a-f]{16}", str(sim.get("checksum"))):
        raise Refused("junction_bad_simulation_receipt")
    factory_ok = all(by.get(name, {}).get("status") == "pass" for name in (
        "factory_broker_unit_tests", "factory_broker_build", "factory_native_benign_canary"))
    if factory_ok:
        sha(data.get("factory_source_sha"))
        if data.get("platform") != "linux":
            raise Refused("factory_canary_not_native_linux")
    if data.get("overall") == "pass" and not factory_ok:
        raise Refused("junction_false_complete")
    return {"status": "pass", "seed_count": sim["scenarios"], "factory_in_same_run": factory_ok,
            "factory_source_sha": data.get("factory_source_sha") if factory_ok else None}

def chibi(data, source_sha, min_seeds):
    if data.get("schema") != "chibi.seeded-factory-simulation/v1":
        raise Refused("wrong_chibi_schema")
    if data.get("passed") is not True or data.get("lane") != "market":
        raise Refused("chibi_not_successful_market")
    if data.get("head_before") != sha(source_sha) or data.get("head_after") != source_sha:
        raise Refused("chibi_source_mismatch")
    if data.get("live_egress") is not False or data.get("external_credentials") != "excluded":
        raise Refused("chibi_effect_or_credentials")
    if data.get("postgres_cleanup") != "not_required" or data.get("campaign_start") != 0:
        raise Refused("chibi_not_offline_market")
    if type(data.get("campaign_count")) is not int or data["campaign_count"] < min_seeds:
        raise Refused("chibi_seed_coverage")
    sha(data.get("cargo_lock_sha256"), 64)
    suites = data.get("suites")
    if not isinstance(suites, list) or len(suites) != 1:
        raise Refused("chibi_suite_shape")
    market = suites[0]
    if not isinstance(market, dict) or market.get("scenario") != "agent_market" or market.get("failed") != 0 or market.get("passed") != 10 or market.get("exit_code") != 0:
        raise Refused("chibi_market_tests_missing")
    packet = market.get("campaign")
    if not isinstance(packet, dict) or packet.get("schema") != "chibi.synthetic-campaign/v1" or packet.get("start") != 0 or packet.get("count") != data["campaign_count"] or packet.get("liveEgress") is not False:
        raise Refused("chibi_market_packet_invalid")
    sha(packet.get("traceSha256"), 64)
    if type(packet.get("events")) is not int or packet["events"] < min_seeds * 6:
        raise Refused("chibi_events_missing")
    return {"status": "pass", "seed_count": data["campaign_count"], "trace_sha256": packet["traceSha256"]}

def reconcile(junction_data, junction_sha, chibi_data=None, chibi_sha=None, min_junction=100000, min_chibi=10000):
    result = {"schema": "rml1.cross-host-developer-evidence/v1",
              "runtime_authorized": False, "qualified": False,
              "authenticated_host_evidence": False,
              "scope": "untrusted-source-receipts-not-OCI-or-seccomp-attestation",
              "junction": junction(junction_data, junction_sha, min_junction),
              "chibi": {"status": "not_run"}}
    if chibi_data is not None:
        if chibi_sha is None:
            raise Refused("missing_chibi_source_pin")
        result["chibi"] = chibi(chibi_data, chibi_sha, min_chibi)
    result["factory"] = {"status": "pass" if result["junction"]["factory_in_same_run"] else "not_run"}
    result["coverage"] = ("pass" if result["chibi"]["status"] == "pass" and
                          result["factory"]["status"] == "pass" else "incomplete")
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junction", type=Path, required=True)
    parser.add_argument("--junction-sha", required=True)
    parser.add_argument("--chibi", type=Path)
    parser.add_argument("--chibi-sha")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.chibi) != bool(args.chibi_sha):
        parser.error("chibi receipt and SHA must be supplied together")
    try:
        j, j_hash = read_receipt(args.junction)
        c, c_hash = read_receipt(args.chibi) if args.chibi else (None, None)
        result = reconcile(j, args.junction_sha, c, args.chibi_sha)
        result["input_sha256"] = {"junction": j_hash, "chibi": c_hash}
        if args.out.is_symlink():
            raise Refused("output_is_symlink")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"coverage": result["coverage"], "out": str(args.out),
                          "runtime_authorized": False}))
        return 0 if result["coverage"] == "pass" else 2
    except (OSError, Refused) as e:
        parser.exit(1, f"REFUSED: {e}\n")

if __name__ == "__main__":
    raise SystemExit(main())
