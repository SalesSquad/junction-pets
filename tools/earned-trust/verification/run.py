#!/usr/bin/env python3
"""Run one frozen behavioral probe against two exact public source revisions.

The output is local integrity evidence, not a signature or human approval.
Build failures and missing observations are inconclusive, never bug reproduction.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

BASE = "32258fdbee4bcd653c79f51b4376b5103c6f4d27"
HEAD = "9df83c38409c8bfad0517aebffe48211eda4a5b4"
CASE = "MP2283-metadata-generic-struct-resolver"
FILES = ("Program.cs", "FrozenCheck.csproj", "global.json", "fixtures/Library.cs", "fixtures/Application.cs", "run.py")
SDK_HASH = "7f69bda047de1f952286be330a5e858171ded952d1aa24169e62212f90a27149e63b636c88ad313a6e3ec860da31f8c547ff4ab6808103a070f7fb26ba99c1c7"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def execute(command: list[str], cwd: Path, log: Path, env: dict[str, str], timeout: int) -> tuple[int | None, str | None]:
    """Keep complete process output; distinguish timeouts from command failure."""
    with log.open("w") as handle:
        handle.write(json.dumps({"command": command, "cwd": str(cwd)}) + "\n")
        handle.flush()
        try:
            completed = subprocess.run(command, cwd=cwd, env=env, stdout=handle,
                                       stderr=subprocess.STDOUT, timeout=timeout, check=False)
            return completed.returncode, None
        except subprocess.TimeoutExpired:
            handle.write("\nEARNED_TRUST_PROCESS_TIMEOUT\n")
            return None, "process-timeout"
        except OSError as exc:
            handle.write("\n" + str(exc) + "\n")
            return None, "process-unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--dotnet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path, help="Verified installer metadata; copied as provenance, not trusted as attestation.")
    args = parser.parse_args()
    repo, dotnet, output = args.repo.resolve(), args.dotnet.resolve(), args.output.resolve()
    frozen = Path(__file__).resolve().parent
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier run.
    manifest = {name: digest(frozen / name) for name in FILES}
    save(output / "frozen-manifest.json", manifest)
    env = dict(os.environ, DOTNET_ROOT=str(dotnet.parent), DOTNET_CLI_TELEMETRY_OPTOUT="1",
               DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
               NUGET_PACKAGES=str(output.parent / "nuget-packages"),
               DOTNET_CLI_HOME=str(output.parent / "dotnet-cli"))
    # Choose the explicit compatibility SDK from the frozen overlay. The
    # archived upstream global.json remains untouched and is hashed below.
    version = subprocess.run([str(dotnet), "--version"], cwd=frozen, env=env,
                             capture_output=True, text=True, check=False)
    (output / "sdk-version.log").write_text(version.stdout + version.stderr)
    if version.returncode or version.stdout.strip() != "9.0.100":
        raise RuntimeError("The frozen harness requires exactly SDK 9.0.100; see sdk-version.log.")
    runtimes = subprocess.run([str(dotnet), "--list-runtimes"], cwd=frozen, env=env,
                              capture_output=True, text=True, check=False)
    (output / "runtimes.log").write_text(runtimes.stdout + runtimes.stderr)
    receipt: dict = {
        "schemaVersion": 1,
        "workId": "TIETO-MACOS-20261115",
        "caseId": CASE,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": {"url": "https://github.com/te-industry-tech-office/junction26-messagepack-csharp", "baseSha": BASE, "headSha": HEAD},
        "harness": {"path": "tools/earned-trust/verification", "sha256": canonical_digest(manifest),
                    "inputSha256": canonical_digest({name: manifest[name] for name in FILES if name.startswith("fixtures/")}),
                    "files": manifest},
        "environment": {"sdkVersion": "9.0.100", "runtimeTarget": "net8.0", "sdkArchiveSha512": SDK_HASH,
                        "os": platform.platform(), "runtimes": runtimes.stdout.strip().splitlines(),
                        "compatibilityExperiment": True, "originalSdkVersion": "8.0.402",
                        "originalSdkExecuted": False},
        "revisions": [],
        "conclusion": {"status": "inconclusive", "reason": "Run has not completed."},
        "humanDecision": None,
        "authentication": {"type": "local-sha256-integrity", "signedRunner": False},
    }
    if args.toolchain:
        metadata = json.loads(args.toolchain.read_text())
        save(output / "toolchain.json", metadata)
        receipt["environment"]["toolchainMetadataSha256"] = digest(output / "toolchain.json")
    save(output / "differential.json", receipt)

    for role, revision in (("base", BASE), ("head", HEAD)):
        print(f"Preparing {role} {revision}", flush=True)
        area = output / role
        source, harness = area / "source", area / "harness"
        source.mkdir(parents=True)
        harness.mkdir()
        archive = area / "source.tar"
        with archive.open("wb") as handle:
            subprocess.run(["git", "-C", str(repo), "archive", revision], stdout=handle, check=True)
        # The upstream Nerdbank.GitVersioning task needs genuine Git metadata.
        # A local clone contains only committed public source; task edits in
        # the coordinator's working tree are never copied into these builds.
        subprocess.run(["git", "clone", "--shared", "--no-checkout", str(repo), str(source)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", revision], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"]):
            raise RuntimeError("Isolated public source checkout is not clean.")
        for name in FILES:
            target = harness / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(frozen / name, target)
        copied_manifest = {name: digest(harness / name) for name in FILES}
        if copied_manifest != manifest:
            raise RuntimeError("Frozen harness bytes changed during copy.")
        source_tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", revision + "^{tree}"], text=True).strip()
        result: dict = {
            "role": role, "sourceSha": revision, "sourceTree": source_tree,
            "sourceArchiveSha256": digest(archive), "upstreamGlobalJsonSha256": digest(source / "global.json"),
            "harnessSha256": canonical_digest(copied_manifest), "executionOverlaySha256": manifest["global.json"],
            "status": "inconclusive", "exitCode": None, "diagnostics": [],
            "generatedResolver": {"expectedHintName": "App.AppResolver.g.cs", "present": None},
            "tests": {"passed": 0, "failed": 0, "skipped": 0}, "logs": [],
        }
        build_log = area / "build.log"
        build_command = [str(dotnet), "build", "FrozenCheck.csproj", "-c", "Release", "--nologo", "-v:minimal", "-m:1",
                         "-p:EarnedTrustSourceRoot=" + str(source)]
        print(f"Building {role} with SDK 9.0.100 (net8.0 probe)", flush=True)
        build_code, build_error = execute(build_command, harness, build_log, env, 600)
        result["build"] = {"exitCode": build_code, "error": build_error, "command": build_command}
        result["logs"].append({"path": str(build_log.relative_to(output)), "sha256": digest(build_log)})
        observation = area / "observation.json"
        if build_code == 0:
            run_log = area / "probe.log"
            run_command = [str(dotnet), str(harness / "bin/Release/net8.0/FrozenCheck.dll"), str(observation)]
            run_code, run_error = execute(run_command, harness, run_log, env, 120)
            result["exitCode"] = run_code
            result["execution"] = {"command": run_command, "error": run_error}
            result["logs"].append({"path": str(run_log.relative_to(output)), "sha256": digest(run_log)})
            if observation.exists() and run_error is None:
                observed = json.loads(observation.read_text())
                result["observation"] = {"path": str(observation.relative_to(output)), "sha256": digest(observation)}
                checks = observed.get("checks", {})
                expected_failure = (checks.get("analyzerDidNotCrash") is False or
                                    checks.get("generatorDidNotCrash") is False or
                                    checks.get("consumerResolverGenerated") is False)
                result["diagnostics"] = observed.get("diagnostics", [])
                result["generatedResolver"] = observed.get("generatedResolver", result["generatedResolver"])
                if observed.get("caseId") == CASE and run_code == 0 and observed.get("status") == "pass" and checks and all(checks.values()):
                    result["status"], result["tests"] = "pass", {"passed": 1, "failed": 0, "skipped": 0}
                elif observed.get("caseId") == CASE and run_code == 1 and observed.get("status") == "fail" and expected_failure:
                    result["status"], result["tests"] = "fail", {"passed": 0, "failed": 1, "skipped": 0}
                    result["reason"] = "Measured issue-specific analyzer/generator crash or missing consumer resolver."
                else:
                    result["reason"] = "Probe output did not establish the expected issue-specific behavior."
            else:
                result["reason"] = "Probe did not finish with a complete observation."
        else:
            result["reason"] = "Build/restore/environment failure: behavioral probe did not execute."
        receipt["revisions"].append(result)
        save(output / "differential.json", receipt)
        print(f"{role}: {result['status']}", flush=True)

    base, head = receipt["revisions"]
    if base["status"] == "fail" and head["status"] == "pass":
        receipt["conclusion"] = {"status": "demonstrated", "reason": "The identical frozen probe reproduced issue-specific failure on the base and passed on the supplied patch."}
    elif "inconclusive" in {base["status"], head["status"]}:
        receipt["conclusion"] = {"status": "inconclusive", "reason": "At least one revision lacks completed issue-specific behavioral evidence."}
    else:
        receipt["conclusion"] = {"status": "not-demonstrated", "reason": "Completed observations do not show base failure followed by patched success."}
    save(output / "differential.json", receipt)
    print(json.dumps(receipt["conclusion"]), flush=True)
    return 0 if receipt["conclusion"]["status"] == "demonstrated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
