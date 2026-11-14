#!/usr/bin/env python3
"""Verify 18 source-bound source-only Chibi Lens adversarial fault receipts.

No GPU/ML model training is performed here; six original ML feedback folds
were already trained under CRACI 43647042519. This script checks *new fault
families* across HB selector (#190), scene8 admission (#194) and PR208 gate,
and explicitly refuses model/field approval based on synthetic evidence.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

WORK_ID = "CHIBI-LENS-SIX-FAULT-20261115"
GATE_BLOB = "7267e11a1bdc211dbede9d09374ceed7a61f4692"
SELECTOR_BLOB = "53d72a8d0beb74788cd44081274179bce8114e22"
NUMERIC_ORIGINAL = "2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
NUMERIC_SCENE8 = "4c29e622d2dd4f709792ef0c41e7a09d28f16020ef941b5b64a1cc8469ae464d"
SOURCE_PR208 = "2e338f72ac6e912b23b38b66526c2cb645852868"

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Missing ordinary source-bound receipt: " + str(path))
    record = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(record, dict):
        raise RuntimeError("Unexpected non-dictionary fault receipt")
    return record

def audit(root: Path, output: Path | None = None) -> dict:
    if not root.is_dir():
        raise RuntimeError("Missing owned source evidence directory")
    field = root / "field-gate-six.json"
    f = load(field)
    if (f.get("pr208SourceCommit") != SOURCE_PR208 or
        f.get("pr208GateGitBlob") != GATE_BLOB or
        f.get("allPass") is not True or
        f.get("syntheticControls") != 6 or
        f.get("mutatedFaultCasesDenied") != 6 or
        f.get("modelAccuracyOrProductQualityProven") is not False or
        f.get("noModelDeploymentOrIdentityAuthorization") is not True):
        raise RuntimeError("Field gate source or provenance unqualified")
    if len(f.get("rounds", [])) != 6:
        raise RuntimeError("Six source-bound full-frame rounds required")
    families = set()
    checked = [(field, digest(field))]
    for index, sample in enumerate(f["rounds"], 1):
        if (sample.get("round") != index or
            sample.get("maliciousOutcome") != "DENIED" or
            sample.get("realWorldFieldQualification") is not False or
            sample.get("syntheticControlInternalThresholdPassed") is not True or
            not set(sample.get("requiredFailures", [])).issubset(sample.get("actualReasons", []))):
            raise RuntimeError("Unqualified source field fault round " + str(index))
        families.add(sample.get("faultFamily"))
    if len(families) != 6:
        raise RuntimeError("Duplicate full-frame fault type")
    kinds = {"selector": set(), "scene8": set()}
    for sub in ("selector", "scene8"):
        for index in range(1, 7):
            path = root / sub / f"round-{index}.json"
            rec = load(path)
            if rec.get("round") != index:
                raise RuntimeError("Missing unique fault round " + str(path))
            if sub == "selector":
                if (rec.get("selectorSourceGitBlob") != SELECTOR_BLOB or
                    rec.get("syntheticCalibrationOnly") is not True or
                    rec.get("realFieldQualified") is not False or
                    rec.get("modelWeightsFitted") is not False or
                    rec.get("historicalTrainingTestScenesReopened") is not False or
                    rec.get("actualStatus") != rec.get("expectedStatus")):
                    raise RuntimeError("Invalid HB selector source-safety receipt")
                kinds[sub].add(rec.get("testFamily"))
            else:
                if (rec.get("originalSourceSha256") != NUMERIC_ORIGINAL or
                    rec.get("freshScene8Sha256") != NUMERIC_SCENE8 or
                    rec.get("actualOutcome") != "DENIED" or
                    rec.get("expectedOutcome") != "DENIED" or
                    rec.get("noNewTestScoreOrProductClaim") is not True or
                    rec.get("syntheticMutationNotModelTraining") is not True):
                    raise RuntimeError("Invalid HB scene8 admission/claim receipt")
                kinds[sub].add(rec.get("fault"))
            checked.append((path, digest(path)))
    if any(len(group) != 6 for group in kinds.values()):
        raise RuntimeError("Duplicated source fault family")
    all_files = sorted(p for p in root.rglob("*.json") if p.is_file())
    if len(all_files) != 13:
        raise RuntimeError("Unexpected evidence file count " + str(len(all_files)))
    report = {
        "schema": "junction.chibi-lens.six-fault-consolidation.v1",
        "workId": WORK_ID,
        "sourcePR190SelectorGitBlob": SELECTOR_BLOB,
        "sourcePR194OldNumericalSHA256": NUMERIC_ORIGINAL,
        "sourcePR194FreshScene8SHA256": NUMERIC_SCENE8,
        "sourcePR208": SOURCE_PR208,
        "sourcePR208GateGitBlob": GATE_BLOB,
        "sixSelectorBoundsVerified": 6,
        "sixScene8SourceTamperAndClaimDenials": 6,
        "sixFullFrameGTPrivacyStatProvenanceDenials": 6,
        "totalSeparateAdversarialFamilies": 18,
        "newModelWeightsTrained": 0,
        "independentNewRealWorldFieldQualification": False,
        "productModelApprovedOrDeployed": False,
        "CRACITrainingJobsRerun": 0,
        "previousOriginalHBSourceTrainFoldsPreserved": True,
        "openDetectorTrainingSourceOwnerPR": 215,
        "nextRequirement": "PR215 independently frozen detector plus new rights-cleared multi-scene/device and unknown-class evaluation",
        "sourceReportedFiles": [
            {"path": str(path.relative_to(root)), "sha256": sha}
            for path, sha in sorted(checked, key=lambda t: str(t[0]))
        ]
    }
    if output is not None:
        if output.exists():
            raise FileExistsError("Refuse overwriting source-bound research audit")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    r = audit(args.root, args.output)
    print(json.dumps({
        "sixByThree": 18,
        "receiptFiles": len(r["sourceReportedFiles"]),
        "realFieldQualified": False,
        "newMLFits": 0,
        "trainingJobsRerun": 0,
    }, sort_keys=True))
