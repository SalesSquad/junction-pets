"""Small local, no-Harbor qualification of reward integrity and task metadata."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from evaluate import evaluate, make_cases


def run() -> None:
    task = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
    assert 0 < manifest["timeouts"]["verifier_execution_sec"] <= 120
    assert (task / "instruction.md").is_file()
    assert (task / "environment" / "Dockerfile").is_file()
    assert (task / "solution" / "solve.sh").is_file()
    assert (task / "tests" / "test.sh").is_file()

    oracle = task / "solution" / "reconcile.py"
    cases = make_cases()
    reference = evaluate(oracle, cases)
    assert reference["reward"] == 1.0, reference

    empty = evaluate(task / "tests" / "baselines" / "absent.py", cases)
    assert empty["reward"] == 0.0, empty

    early = evaluate(task / "tests" / "baselines" / "stop_early.py", cases)
    assert early["reward"] <= 0.1, early

    blanket = evaluate(task / "tests" / "baselines" / "all_escalate.py", cases)
    assert blanket["reward"] < 0.4, blanket

    fabricated = evaluate(task / "tests" / "baselines" / "all_paid.py", cases)
    assert fabricated["reward"] == 0.0 and fabricated["unsafeAction"], fabricated

    tamper = evaluate(task / "tests" / "baselines" / "tamper_input.py", cases)
    assert tamper["reward"] == 0.0 and tamper["tamperedInput"], tamper

    with tempfile.TemporaryDirectory(prefix="afterquery-harbor-local-") as directory:
        # End-to-end CLI on the sample the agent sees. This is not a Harbor run.
        sample_output = Path(directory) / "sample.json"
        completed = subprocess.run([
            sys.executable, str(oracle), "--input", str(task / "environment/data/orders.json"),
            "--output", str(sample_output),
        ], check=False, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
        report = json.loads(sample_output.read_text(encoding="utf-8"))
        assert [row["state"] for row in report["orders"]] == ["PAID", "BLOCKED", "UNKNOWN", "RETRYABLE"]
        assert report["orphanEventIds"] == ["E-08"]

        # Verify the score file format is a Harbor-compatible bounded float.
        receipt_dir = Path(directory) / "verifier"
        completed = subprocess.run([
            sys.executable, str(task / "tests/evaluate.py"), "--solver", str(oracle),
            "--reward-dir", str(receipt_dir),
        ], check=False, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr
        assert float((receipt_dir / "reward.txt").read_text()) == 1.0
        assert json.loads((receipt_dir / "details.json").read_text())["matchedCases"] == len(cases)

    print(json.dumps({"result": "PASS_LOCAL_ONLY", "cases": len(cases),
                      "oracleReward": reference["reward"], "noOp": empty["reward"],
                      "stopEarly": early["reward"], "allEscalate": blanket["reward"],
                      "fabricatedPaid": fabricated["reward"], "inputTamper": tamper["reward"]},
                     sort_keys=True))


if __name__ == "__main__":
    run()
