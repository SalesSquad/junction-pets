"""Predeclared synthetic model stability study; never select a winner on holdout."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(os.environ["SOURCE_DIR"]).resolve()
expected = os.environ["EXPECTED_SOURCE_SHA"]
assert len(expected) == 40 and all(c in "0123456789abcdef" for c in expected)
assert subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == expected
relative = "services/meta-spatial/ml/candidate_model.py"
path = root / relative
assert path.read_bytes() == subprocess.check_output(["git", "-C", str(root), "show", f"{expected}:{relative}"])
spec = importlib.util.spec_from_file_location("craci_candidate_model", path)
model_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model_module
spec.loader.exec_module(model_module)
seeds = (101, 211, 307, 401, 503, 601, 701, 809, 907, 1009, 1103, 1201)
shard = int(os.environ["CRACI_SHARD"])
assert shard in range(4)
selected = seeds[shard * 3:shard * 3 + 3]
assert not set(selected) & {model_module.VALIDATION_SEED, model_module.TEST_SEED}

def independently_count(model, examples):
    counts = dict(trueCandidate=0, falseCandidate=0, correctAbstainOnNegative=0, missedPositive=0)
    for example in examples:
        linear = model["bias"]
        for index, observed in enumerate(example.features):
            linear += model["weights"][index] * (observed - model["means"][index]) / model["scales"][index]
        probability = 1 / (1 + math.exp(-linear))
        positive = probability >= model["candidate_threshold"]
        key = ("trueCandidate" if positive else "missedPositive") if example.same_object else ("falseCandidate" if positive else "correctAbstainOnNegative")
        counts[key] += 1
        proposal = model_module.candidate_proposal(model, dict(zip(model_module.FEATURES, example.features)))
        assert proposal["kind"] == ("candidate" if positive else "abstain")
        assert proposal["identityVerified"] is False and proposal["actionAuthorized"] is False
        assert abs(proposal["candidateProbability"] - probability) <= 0.00000051
    return counts

failed = 0
for seed in selected:
    start = time.monotonic()
    try:
        model = model_module.train(seed)
        assert model["training"]["seed"] == seed
        assert model["training"]["examples"] == 3000 and model["training"]["epochs"] == 180
        assert model["training"]["validationSeed"] == 919 and model["training"]["separateShiftedTestSeed"] == 1327
        assert model["validation"]["falseCandidateRate"] <= 0.050001
        fixed = model_module.synthetic_examples(1327, 1500, domain="shifted_test")
        # Additional disjoint holdout stream is never used for training/calibration.
        extra_seed = 200000 + seed
        extra = model_module.synthetic_examples(extra_seed, 10000, domain="shifted_test")
        reports = {}
        for label, examples in [("fixed_shifted_holdout", fixed), ("additional_shifted_holdout", extra)]:
            values = model_module.metrics(model, examples)
            counts = independently_count(model, examples)
            assert all(values[key] == value for key, value in counts.items())
            assert sum(counts.values()) == len(examples)
            reports[label] = values
        model_bytes = json.dumps(model, sort_keys=True, allow_nan=False).encode()
        print(json.dumps({"scope": "synthetic-score-model-seed-stability", "status": "passed",
            "source_sha": expected, "source_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "training_seed": seed, "additional_holdout_seed": extra_seed,
            "train_examples": 3000, "epochs": 180, "validation": model["validation"],
            "holdouts": reports, "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
            "duration_seconds": round(time.monotonic() - start, 3),
            "selected_for_deployment": False, "real_camera_or_hardware_qualified": False}, sort_keys=True))
    except Exception as error:
        failed += 1
        print(json.dumps({"status": "failed", "source_sha": expected, "training_seed": seed,
            "error_type": type(error).__name__, "error": str(error)[:500]}))
if failed:
    raise SystemExit(1)
