"""Offline qualification: the Harbor verifier never executes agent-authored code.

Local fixture generation runs an oracle/baseline BEFORE scoring only. It does
not claim a Docker trial, a Harbor trial or any model credit allocation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from evaluate import SOURCE_SHA256, evaluate_artifact, evaluate_report, make_cases


def execute_before_verifier(solver: Path, source: Path, output: Path) -> subprocess.CompletedProcess:
    output.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run([
        sys.executable, str(solver), "--input", str(source), "--output", str(output),
    ], check=False, text=True, capture_output=True, timeout=8)


def run() -> None:
    task = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.4"
    assert manifest["artifacts"] == ["/app/output", "/app/data/orders.json"]
    assert manifest["verifier"]["environment_mode"] == "separate"
    assert 0 < manifest["verifier"]["timeout_sec"] <= 120
    for element in ["instruction.md", "environment/Dockerfile", "solution/solve.sh",
                    "tests/test.sh", "tests/Dockerfile"]:
        assert (task / element).is_file(), element

    verifier_source = (task / "tests/evaluate.py").read_text(encoding="utf-8")
    assert "subprocess" not in verifier_source and "importlib" not in verifier_source
    assert "--solver" not in verifier_source and "/app/reconcile.py" not in verifier_source
    assert "--solver" not in (task / "tests/test.sh").read_text(encoding="utf-8")
    assert "COPY . /tests/" in (task / "tests/Dockerfile").read_text(encoding="utf-8")

    oracle = task / "solution/reconcile.py"
    sample = task / "environment/data/orders.json"
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == SOURCE_SHA256
    cases = make_cases()
    assert len(cases) == 37

    # Thirty-seven varied offline oracle checks, run in a separate preparation
    # phase and scored only from their resulting JSON values.
    with tempfile.TemporaryDirectory(prefix="afterquery-harbor-local-") as directory:
        base = Path(directory)
        for index, item in enumerate(cases):
            source = base / f"case-{index}.input.json"
            result = base / f"case-{index}.output.json"
            source.write_text(json.dumps(item.payload), encoding="utf-8")
            done = execute_before_verifier(oracle, source, result)
            assert done.returncode == 0, (item.name, done.stderr)
            check = evaluate_report(json.loads(result.read_text(encoding="utf-8")), item)
            assert check["reward"] == 1.0, (item.name, check)

        # The actual Harbor artifact is scored as a single 38-order task.
        fresh_input = base / "orders.json"
        fresh_input.write_bytes(sample.read_bytes())
        artifact = base / "decisions.json"
        done = execute_before_verifier(oracle, fresh_input, artifact)
        assert done.returncode == 0, done.stderr
        reference = evaluate_artifact(fresh_input, artifact)
        assert reference["reward"] == 1.0 and reference["matchedOrders"] == 38, reference

        missing = evaluate_artifact(fresh_input, base / "absent.json")
        assert missing["reward"] == 0, missing

        for malformed in [[], {"schemaVersion": True, "orders": [], "orphanEventIds": []},
                          {"schemaVersion": 1, "orders": [{"orderId": []}], "orphanEventIds": []},
                          {"schemaVersion": 1, "orders": [{
                              "orderId": "O-100", "totalCents": 2598, "state": {},
                              "nextAction": [], "receiptId": None, "evidenceEventIds": []}],
                           "orphanEventIds": []}]:
            bad = base / "malformed.json"
            bad.write_text(json.dumps(malformed), encoding="utf-8")
            result = evaluate_artifact(fresh_input, bad)
            assert result["reward"] == 0 and not result["unsafeAction"], result

        baseline_results = {}
        for baseline in ["stop_early", "all_escalate", "all_paid"]:
            candidate = base / f"{baseline}.json"
            done = execute_before_verifier(task / f"tests/baselines/{baseline}.py", fresh_input, candidate)
            assert done.returncode == 0, (baseline, done.stderr)
            baseline_results[baseline] = evaluate_artifact(fresh_input, candidate)
        assert baseline_results["stop_early"]["reward"] < 0.1
        assert baseline_results["all_escalate"]["reward"] < 0.4
        assert baseline_results["all_paid"]["reward"] == 0
        assert baseline_results["all_paid"]["unsafeAction"]

        tamper_input = base / "tampered-orders.json"
        tamper_input.write_bytes(sample.read_bytes())
        done = execute_before_verifier(task / "tests/baselines/tamper_input.py",
                                       tamper_input, base / "tampered-output.json")
        assert done.returncode == 0, done.stderr
        tampered = evaluate_artifact(tamper_input, base / "tampered-output.json")
        assert tampered["reward"] == 0 and tampered["tamperedInput"], tampered

        # Exact regression for the P0 exploit: an attacker-owned reconcile.py
        # that looks up expected answers when /tests appears must NEVER run in
        # verifier phase. Even if it exists next to an artifact, the verifier
        # only reads JSON. A poison marker would be written if it were executed.
        attacker = base / "reconcile.py"
        marker = base / "EXECUTED_ATTEMPT_TO_LEAK"
        attacker.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('p0')\n"
            "exec(Path('/tests/evaluate.py').read_text())\n",
            encoding="utf-8",
        )
        forged = base / "forged.json"
        forged.write_text(json.dumps({"schemaVersion": 1, "orders": [], "orphanEventIds": []}))
        exploit_result = evaluate_artifact(fresh_input, forged)
        assert exploit_result["reward"] == 0 and not marker.exists(), exploit_result

        receipt_dir = base / "verifier"
        completed = subprocess.run([
            sys.executable, str(task / "tests/evaluate.py"), "--source", str(fresh_input),
            "--artifact", str(artifact), "--reward-dir", str(receipt_dir),
        ], check=False, capture_output=True, text=True, timeout=8, cwd=base)
        assert completed.returncode == 0, completed.stderr
        assert float((receipt_dir / "reward.txt").read_text()) == 1.0
        assert json.loads((receipt_dir / "details.json").read_text())["matchedOrders"] == 38
        assert not marker.exists(), "verifier executed untrusted solver"

        print(json.dumps({"result": "PASS_LOCAL_ONLY", "oracleCases": len(cases),
                          "challengeOrders": reference["totalOrders"],
                          "oracleReward": reference["reward"], "noOp": missing["reward"],
                          "stopEarly": baseline_results["stop_early"]["reward"],
                          "allEscalate": baseline_results["all_escalate"]["reward"],
                          "fabricatedPaid": baseline_results["all_paid"]["reward"],
                          "inputTamper": tampered["reward"],
                          "p0HiddenTestExfil": exploit_result["reward"]}, sort_keys=True))


if __name__ == "__main__":
    run()
