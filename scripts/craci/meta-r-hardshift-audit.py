#!/usr/bin/env python3
"""Audit exact CRACI Meta R artifact receipts and synthetic model results.

Read-only on untrusted GitHub artifact bytes. Never deploy or select a runtime
model; SHA256 is a consistency check, not a provider signed attestation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

SOURCE = "634f1e0e6cb2de46bcf0a783532d46c23f513d11"
EXPECTED = {"train": 20_000, "cal": 5_000, "shifted": 5_000,
            "normal_holdout": 5_000}
ARTIFACTS = {"dataset.csv", "dataset-receipt.json",
             "training-report.json", "trained-models.rds"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--harness-sha", required=True)
    ap.add_argument("--run-id", type=int, required=True)
    args = ap.parse_args()
    if len(args.harness_sha) != 40 or any(ch not in "0123456789abcdef" for ch in args.harness_sha):
        raise RuntimeError("Full exact harness SHA required")
    root = args.root.resolve()
    if not root.is_dir():
        raise RuntimeError("Missing run evidence root")
    dirs = sorted(p for p in root.iterdir()
                  if p.is_dir() and p.name.startswith("craci-meta-r-"))
    if len(dirs) != 24:
        raise RuntimeError(f"Expected 24 cohort receipts, found {len(dirs)}")
    rows = []
    seen_seeds = set()
    old_seeds = set()
    for i in range(8):
        old_seeds.update((110001+i*10007, 220003+i*10009, 330007+i*10037))
    for i in range(12):
        old_seeds.update((510001+i*10007,610003+i*10009,710007+i*10037,
                          810011+i*10039,910013+i*10043))
    for directory in dirs:
        receipt = json.loads((directory / "receipt.json").read_text())
        report = json.loads(
            (directory / "artifacts/meta-r/training-report.json").read_text())
        dataset = json.loads(
            (directory / "artifacts/meta-r/dataset-receipt.json").read_text())
        zipped = directory / "artifacts/meta-r/training-evidence.zip"
        with zipfile.ZipFile(zipped) as archive:
            if not ARTIFACTS.issubset(set(archive.namelist())):
                raise RuntimeError(f"Model or data evidence missing: {directory.name}")
            if archive.getinfo("trained-models.rds").file_size < 100:
                raise RuntimeError("Empty RDS model file")
            if (hashlib.sha256(archive.read("dataset.csv")).hexdigest()
                    != dataset["dataset_sha256"]):
                raise RuntimeError("Dataset SHA256 mismatch")
            if (archive.read("training-report.json")
                    != (directory/"artifacts/meta-r/training-report.json").read_bytes()):
                raise RuntimeError("Packaged report mismatch")

        bind = receipt.get("binding", {})
        if (receipt["status"] != "succeeded" or receipt.get("issues")
                or not receipt.get("sourceVerified")
                or not receipt.get("harnessVerified")
                or bind.get("sourceSha") != SOURCE
                or bind.get("harnessSha") != args.harness_sha):
            raise RuntimeError(f"Unqualified source receipt: {directory.name}")
        cohort = report["cohort"]
        if (not 0 <= cohort < 24 or dataset["cohort"] != cohort
                or report["sourceCommit"] != SOURCE
                or dataset["source_sha"] != SOURCE
                or dataset["counts"] != EXPECTED
                or report["datasetSha256"] != dataset["dataset_sha256"]
                or report["candidateCount"] != 4
                or report["trainingCases"] != 20000
                or report["calibrationCases"] != 5000
                or report["independentShiftedCases"] != 5000
                or report["independentNormalCases"] != 5000
                or report["calibrationDomain"] != "shifted_test"
                or report["trainingProfile"] != "hardshift24_blinded_stress_holdout"
                or not dataset["robust_training"]
                or dataset.get("profile") != "hardshift24"
                or dataset.get("stress_variant") != cohort % 4
                or dataset.get("stress_split_only") != "shifted"
                or report.get("stressVariant") != cohort % 4
                or report.get("heldoutComparisons") != 24
                or report.get("familywiseAlpha") != 0.05
                or not isinstance(report.get("selectedHardNegativeFprNoWorse"), bool)):
            raise RuntimeError(f"Training provenance mismatch: {directory.name}")

        seeds = dataset["seed_sets"]
        if len(seeds) != 5 or len(set(seeds.values())) != 5:
            raise RuntimeError("Missing or repeated split seed")
        if set(seeds.values()) & (seen_seeds | old_seeds | {117, 919, 1327}):
            raise RuntimeError("Overlapping original or held-out seed")
        seen_seeds.update(seeds.values())
        if report["identityVerified"] or report["actionAuthorized"] or                 not report["syntheticScoreModelOnly"] or report["realCameraModel"]:
            raise RuntimeError("Unsafe claim in training report")

        winner = report["calibratedCandidate"]
        cal = report["calibration"]
        shifted = report["shiftedHoldout"]
        normal = report["normalHoldout"]
        assert winner in cal and winner in shifted and winner in normal
        if any(cal[name]["fpr"] > 0.05 + 1e-10 for name in (
                "baseline_calibrated", "glm_main", "glm_interaction",
                "tree_d3", "tree_d5")):
            raise RuntimeError("Calibration false-candidate rate target broken")
        selected = shifted[winner]
        baseline = shifted["baseline_calibrated"]
        expected_hard_negative_safety = (
            selected["hard_negative_fpr"] is None or
            selected["hard_negative_fpr"] <= baseline["hard_negative_fpr"])
        if report["selectedHardNegativeFprNoWorse"] != expected_hard_negative_safety:
            raise RuntimeError("Hard-negative safety evidence mismatch")
        normal_sel = normal[winner]
        normal_base = normal["baseline_calibrated"]
        ci = report["pairedBootstrapFamilywise24"]
        if len(ci) != 2 or ci[0] > ci[1] or ci[0] > report["pairedBootstrap95pct"][0]:
            raise RuntimeError("Familywise/95 interval inconsistency")
        if report["qualityClaim"] == "EXPLORATORY_SYNTHETIC_HELDOUT_GAIN":
            if not (winner != "baseline_calibrated" and
                    selected["recall"] > baseline["recall"] and
                    selected["fpr"] <= baseline["fpr"] and ci[0] > 0 and
                    selected["hard_negative_fpr"] <= baseline["hard_negative_fpr"] and
                    normal_sel["fpr"] <= normal_base["fpr"] + 0.01):
                raise RuntimeError("Unsafe synthetic improvement claim")

        rows.append({
            "cohort": cohort, "winner": winner, "quality": report["qualityClaim"],
            "shiftedFpr": selected["fpr"], "shiftedBaselineFpr": baseline["fpr"],
            "shiftedRecall": selected["recall"],
            "shiftedBaselineRecall": baseline["recall"],
            "normalFpr": normal_sel["fpr"],
            "normalBaselineFpr": normal_base["fpr"],
            "paired95CI": ci,
        })

    if sorted(row["cohort"] for row in rows) != list(range(24)):
        raise RuntimeError("Missing or duplicate cohorts")
    if len(seen_seeds) != 120:
        raise RuntimeError("Unexpected source seed count")
    winners = {}
    for row in rows:
        winners[row["winner"]] = winners.get(row["winner"], 0) + 1
    result = {
        "workId": "CRACI-META-R-HARDSHIFT-2X-20261114",
        "sourcePinned": SOURCE, "harnessPinned": args.harness_sha,
        "runId": args.run_id, "verifiedJobs": len(rows),
        "newRModelFits": 96, "syntheticObservations": 840000,
        "disjointSeeds": len(seen_seeds),
        "winnerCounts": winners,
        "exploratoryPositiveQualifiers": sum(
            r["quality"] == "EXPLORATORY_SYNTHETIC_HELDOUT_GAIN" for r in rows),
        "providerBilling": None,
        "providerSignedAttestation": False,
        "cameraIdentityOrAuthQualified": False,
        "cohorts": sorted(rows, key=lambda x: x["cohort"]),
    }
    if args.out.exists():
        raise RuntimeError("Audit output already exists; never overwrite evidence")
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({k:result[k] for k in ("runId","verifiedJobs",
        "newRModelFits","syntheticObservations","disjointSeeds",
        "winnerCounts","exploratoryPositiveQualifiers")},sort_keys=True))


if __name__ == "__main__":
    main()
