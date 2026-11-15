#!/usr/bin/env python3
"""Attach the local frozen #2283 experiment to its review packet.

Verify and retain the actual receipt and observation bytes. No status is promoted
because a subprocess exited zero, and no runner-authentication claim is created.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath
import re
import shutil

from build_packets import BASE, CASES, digest

CASE = "MP2283-metadata-generic-struct-resolver"
FROZEN_FILES = {"Program.cs", "FrozenCheck.csproj", "global.json", "fixtures/Library.cs", "fixtures/Application.cs", "run.py"}
FIXTURE_FILES = {"fixtures/Library.cs", "fixtures/Application.cs"}


def checked_file(root: Path, relative: str, expected: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe receipt artifact path")
    candidate = root
    for component in path.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            raise ValueError("Receipt artifacts may not be symlinks")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Receipt artifact must be a regular contained file")
    if resolved.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Receipt artifact exceeds 2 MiB")
    if digest(resolved.read_bytes()) != expected:
        raise ValueError(f"Receipt artifact digest mismatch: {relative}")
    return resolved


def observation_status(run: dict, observed: dict | None) -> str:
    if run.get("build", {}).get("exitCode") != 0 or run.get("build", {}).get("error") is not None:
        if run.get("status") in ("pass", "fail"):
            raise ValueError("A failed build cannot produce behavioral evidence")
        return "error"
    if run.get("execution", {}).get("error") is not None:
        if run.get("status") in ("pass", "fail"):
            raise ValueError("An execution error cannot produce behavioral evidence")
        return "error"
    if observed is None or observed.get("caseId") != CASE:
        return "error"
    if run.get("status") in ("pass", "fail") and (observed.get("status") != run["status"] or observed.get("tests") != run.get("tests")):
        raise ValueError("Observation and receipt outcomes contradict each other")
    checks = observed.get("checks", {})
    expected = {"libraryCompiled", "analyzerDidNotCrash", "generatorDidNotCrash",
                "noBlockingDiagnostics", "generatedCodeCompiles", "consumerResolverGenerated"}
    if set(checks) != expected or not all(isinstance(x, bool) for x in checks.values()):
        if run.get("status") in ("pass", "fail"):
            raise ValueError("A behavioral result must contain every frozen assertion")
        return "error"
    resolver = observed.get("generatedResolver", {})
    if (resolver.get("expectedHintName") != "App.AppResolver.g.cs"
            or resolver.get("present") is not checks["consumerResolverGenerated"]
            or run.get("generatedResolver") != resolver):
        raise ValueError("Resolver observation contradicts the asserted result")
    if run.get("status") == "pass" and run.get("exitCode") == 0 and all(checks.values()):
        if run.get("tests") != {"passed": 1, "failed": 0, "skipped": 0}:
            raise ValueError("Unexpected successful probe counts")
        return "pass"
    target_failed = (not checks["analyzerDidNotCrash"] or not checks["generatorDidNotCrash"]
                     or not checks["consumerResolverGenerated"])
    if (run.get("status") == "fail" and run.get("exitCode") == 1
            and checks["libraryCompiled"] and target_failed):
        if run.get("tests") != {"passed": 0, "failed": 1, "skipped": 0}:
            raise ValueError("Unexpected failing probe counts")
        return "fail"
    return "error"


def attach(receipt_path: Path, packet_path: Path) -> dict:
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    packet = json.loads(packet_path.read_text())
    expected_head = CASES["2283"]["sha"]
    if (receipt.get("schemaVersion") != 1 or receipt.get("caseId") != CASE
            or receipt.get("repository", {}).get("baseSha") != BASE
            or receipt.get("repository", {}).get("headSha") != expected_head
            or packet.get("source", {}).get("baseSha") != BASE
            or packet.get("source", {}).get("headSha") != expected_head):
        raise ValueError("Receipt and packet must bind the exact official #2283 source pair")
    harness = receipt["harness"]
    manifest = harness["files"]
    if (not isinstance(manifest, dict) or set(manifest) != FROZEN_FILES
            or any(not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v) for v in manifest.values())):
        raise ValueError("The frozen manifest must bind all six exact experiment inputs")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    if digest(canonical) != harness["sha256"]:
        raise ValueError("Frozen manifest digest mismatch")
    fixture_manifest = {name: manifest[name] for name in FIXTURE_FILES}
    if digest(json.dumps(fixture_manifest, sort_keys=True, separators=(",", ":")).encode()) != harness.get("inputSha256"):
        raise ValueError("Frozen input digest mismatch")
    revisions = receipt["revisions"]
    if len(revisions) != 2 or {r["role"] for r in revisions} != {"base", "head"}:
        raise ValueError("Exactly one base and one head observation are required")
    by_role = {r["role"]: r for r in revisions}
    artifacts: list[tuple[Path, Path]] = []
    evidence = packet_path.parent / "evidence"
    outcomes, logs, summaries = {}, {}, []
    for role, expected_source in (("base", BASE), ("head", expected_head)):
        run = by_role[role]
        if run["sourceSha"] != expected_source or run["harnessSha256"] != harness["sha256"]:
            raise ValueError("Source or frozen experiment identity mismatch")
        if run.get("executionOverlaySha256") != manifest["global.json"]:
            raise ValueError("Execution overlay is not the frozen configuration")
        # The manifest binds all runner, input and configuration bytes in each
        # independently built experiment, not merely a declared checksum string.
        for name, expected_hash in manifest.items():
            checked_file(receipt_path.parent, f"{role}/harness/{name}", expected_hash)
        for log in run["logs"]:
            source = checked_file(receipt_path.parent, log["path"], log["sha256"])
            artifacts.append((source, evidence / role / source.name))
        observation = run.get("observation")
        if observation:
            source = checked_file(receipt_path.parent, observation["path"], observation["sha256"])
            observed = json.loads(source.read_text())
            artifacts.append((source, evidence / role / "observation.json"))
            log_relative = f"evidence/{role}/observation.json"
            log_hash = observation["sha256"]
        else:
            observed = None
            source = checked_file(receipt_path.parent, run["logs"][0]["path"], run["logs"][0]["sha256"])
            log_relative = f"evidence/{role}/{source.name}"
            log_hash = run["logs"][0]["sha256"]
        outcomes[role] = observation_status(run, observed)
        logs[role] = (log_relative, log_hash)
        codes = sorted({d["id"] for d in (observed or {}).get("diagnostics", [])})
        resolver = (observed or {}).get("generatedResolver", {}).get("present")
        summaries.append(f"{role.capitalize()}: {outcomes[role]}; diagnostics {', '.join(codes) or 'none'}; expected resolver present: {resolver}.")
    check = {
        "id": "frozen-2283", "title": "Frozen external-assembly generator check",
        "requirementId": "MP-2283", "kind": "differential", "evidence": "observed",
        "baseOutcome": outcomes["base"], "headOutcome": outcomes["head"],
        "baseSourceSha": BASE, "headSourceSha": expected_head,
        "baseHarnessSha256": harness["sha256"], "headHarnessSha256": harness["sha256"],
        "baseLog": logs["base"][0], "headLog": logs["head"][0],
        "baseLogSha256": logs["base"][1], "headLogSha256": logs["head"][1],
        "limitations": summaries + [
            "One frozen input in a disclosed SDK 9.0.100 / net8.0 Linux compatibility experiment.",
            "The original SDK 8 pin and original Windows/.NET 10 issue environment were not executed in this experiment.",
            "Generated consumer compilation is checked; serialization round-trip behavior is outside this probe.",
            "Local logs and their digests are preserved; this is not a signed or independently authenticated runner attestation.",
        ],
    }
    packet["checks"] = [c for c in packet["checks"] if c["id"] != check["id"]] + [check]
    claim = {"id": "fix-2283", "title": "The supplied patch resolves the reproduced metadata-generic generator failure",
             "requirementId": "MP-2283", "kind": "fix", "checkIds": [check["id"]],
             "paths": ["src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs"]}
    packet["claims"] = [claim] + [c for c in packet["claims"] if c["id"] != claim["id"]]
    packet["generatedAt"] = receipt["createdAt"]
    packet["provenance"] = {
        "toolchain": "SDK 9.0.100; .NET 8 runtime; Roslyn 4.12; Linux; frozen two-assembly probe",
        "origin": "local-execution",
        "note": f"Same frozen experiment on exact official base/head. Raw local receipt SHA-256: {digest(receipt_bytes)}. Hashes verify local bytes, not runner identity.",
    }
    packet["limitations"] = [
        "The behavioral claim covers one frozen #2283 reproduction, not every valid type shape or other issue.",
        "The SDK/compiler compatibility overlay is explicit; no original-environment or production qualification is implied.",
        "Imported evidence remains a declared local record; matching hashes do not authenticate a runner or person.",
        "The application records local review decisions and performs no merge, release or model inference.",
    ]
    for source, destination in artifacts:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "differential.json").write_bytes(receipt_bytes)
    (evidence / "frozen-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    packet_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n")
    return {"base": outcomes["base"], "head": outcomes["head"], "packetSha256": digest(packet_path.read_bytes()),
            "harnessSha256": harness["sha256"], "receiptSha256": digest(receipt_bytes)}


def create_control(packet_path: Path, control_path: Path) -> None:
    """Use a real pass→pass sub-observation to illustrate an invalid inference."""
    packet = json.loads(packet_path.read_text())
    original = next(c for c in packet["checks"] if c["id"] == "frozen-2283")
    for role in ("base", "head"):
        source = checked_file(packet_path.parent, original[f"{role}Log"], original[f"{role}LogSha256"])
        observed = json.loads(source.read_text())
        if observed.get("checks", {}).get("generatedCodeCompiles") is not True:
            raise ValueError("The pass/pass compilation control must be actually observed on both revisions")
    control = copy.deepcopy(packet)
    control["packetId"] = "tieto-2283-control"
    control["title"] = "Counterexample: a green build"
    control["requirement"]["details"] = (
        "A deliberate unsupported inference for the demo: both generated-code compilations succeed, "
        "but the base analyzer/generator crashes and its resolver is absent. The review desk must refuse "
        "the claim that compiler success alone proves the fix.")
    check = copy.deepcopy(original)
    check.update({"id": "compilation-control", "title": "Generated-code compilation succeeds on both versions",
                  "baseOutcome": "pass", "headOutcome": "pass"})
    check["limitations"] = [
        "This check reads the actual generatedCodeCompiles sub-observation, which is true on both revisions.",
        "The full base probe still fails: AD0001/CS8785 and missing resolver. A green compiler alone misses the bug.",
        "The attached claim is deliberately unsupported so the refusal is visible. These are real observations, not invented test outcomes.",
    ]
    control["checks"] = [check]
    control["claims"] = [{"id": "unsupported-compilation-assurance", "title": "Both compilations pass, therefore the fix is proven",
                          "requirementId": "MP-2283", "kind": "fix", "checkIds": [check["id"]],
                          "paths": ["src/MessagePack.SourceGenerator/CodeAnalysis/TypeCollector.cs"]}]
    control["provenance"]["origin"] = "local-execution-control"
    control["limitations"] = ["This is an adversarial control over the same official change, not a fifth organizer issue."] + control["limitations"]
    control_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(packet_path.parent / "evidence", control_path.parent / "evidence", dirs_exist_ok=True)
    control_path.write_text(json.dumps(control, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--control-packet", type=Path, help="Optional explicit adversarial demonstration packet")
    args = parser.parse_args()
    print(json.dumps(attach(args.receipt.resolve(), args.packet.resolve()), indent=2))
    if args.control_packet:
        create_control(args.packet.resolve(), args.control_packet.resolve())
        print("Created pass/pass control from actual generated-code compilation observations.")
