#!/usr/bin/env python3
"""Read-only exact-source audit of the Chibi Lens public-image CRACI run.

Validates runner-produced evidence against immutable source, provenance and
thresholds. This is not a vendor-signed attestation or production acceptance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile

SOURCE = "c15dc0c023a46c7d9a83e442d1a0e90abe7bab24"
ARCHIVE = "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
CSV_SHA = "c2374f53bc510b6655623f5fa05bb23d08bd1531f24b0aa4e2bcdccab11899a6"
PROFILES = {"all": 48, "color": 24, "spatial": 16, "gradient": 8}


def read_exact(directory):
    receipt = json.loads((directory / "receipt.json").read_text())
    result_path = directory / "artifacts/lens-real/training-report.json"
    result = json.loads(result_path.read_text())
    admission = json.loads(
        (directory / "artifacts/lens-real/cloud-admission.json").read_text())
    with zipfile.ZipFile(directory / "artifacts/lens-real/trained-models.zip") as archive:
        assert sorted(archive.namelist()) == sorted(
            ["training-report.json", "trained-models.rds"])
        if archive.getinfo("trained-models.rds").file_size < 100:
            raise RuntimeError("Trained R model is missing")
        if archive.read("training-report.json") != result_path.read_bytes():
            raise RuntimeError("Frozen report differs from model ZIP")
    if (receipt.get("status") != "succeeded" or receipt.get("issues")
            or receipt.get("sourceVerified") is not True
            or receipt.get("harnessVerified") is not True):
        raise RuntimeError("Failed or unauthenticated source evidence")
    binding = receipt.get("binding", {})
    if (binding.get("sourceSha") != SOURCE
            or binding.get("harnessSha") != SOURCE
            or receipt.get("evidenceLevel") != "source-reported"):
        raise RuntimeError("Unverified exact run provenance")
    if (admission.get("sourceArchiveSha256") != ARCHIVE
            or admission.get("derivedCsvSha256") != CSV_SHA
            or admission.get("cloudTrainingEligible") is not True
            or admission.get("familyMediaAccessed") is not False
            or admission.get("privateOCRAccessed") is not False
            or admission.get("rawPixelsUploaded") is not False):
        raise RuntimeError("Cloud source-admission boundary violated")
    if (result.get("sourceArchiveSha256") != ARCHIVE
            or result.get("featureCSVsha256") != CSV_SHA
            or result.get("sourceKind") != "real_ycbv_mit_rgb_pixels"
            or result.get("licensed") != "MIT"
            or result.get("physicalIdentityVerified") is not False
            or result.get("actionAuthorized") is not False
            or result.get("providerAttested") is not False
            or result.get("calExamples") != 375
            or result.get("testExamples") != 300
            or result.get("trainExamples") != 580):
        raise RuntimeError("Invalid model evaluation or data provenance")
    profile = result.get("featureProfile")
    if profile not in PROFILES or result.get("featureCount") != PROFILES[profile]:
        raise RuntimeError("Profile or allowed feature count mismatch")
    if set(result.get("modelFamilies", [])) != {"centroid", "multinom", "tree"}:
        raise RuntimeError("A model family was not actually evaluated")
    calibrations = result.get("calibration", {})
    heldout = result.get("heldoutTest", {})
    if set(calibrations) != {"centroid", "multinom", "tree"} or set(heldout) != set(calibrations):
        raise RuntimeError("Missing calibration or test comparator")
    winner = result.get("selected")
    if winner not in calibrations:
        raise RuntimeError("Selected model missing from evidence")
    for key, models, count in (
        ("calibration", calibrations, 375), ("test", heldout, 300)):
        for name, row in models.items():
            if (row.get("examples") != count
                or row.get("accepted", 0) + row.get("abstained", 0) != count
                or row.get("acceptedCorrect", 0) + row.get("wrongAccepted", 0)
                   != row.get("accepted", -1)):
                raise RuntimeError("Model confusion/count contradiction")
            if (row.get("wrongAccepted", 0) / count -
                row.get("wrongCandidateFraction", -1) > 1e-7):
                raise RuntimeError("Model wrong-accept rate mismatch")
            if key == "calibration" and row["wrongCandidateFraction"] > 0.050001:
                raise RuntimeError("Calibration false-candidate objective broken")
    selected = heldout[winner]
    baseline = heldout["centroid"]
    true_safe_gain = (winner != "centroid"
                      and selected["wrongCandidateFraction"] <= 0.05
                      and selected["correctCoverage"] > baseline["correctCoverage"]
                      and selected["wrongCandidateFraction"] <= baseline["wrongCandidateFraction"])
    return {
        "profile": profile,
        "features": PROFILES[profile],
        "selected": winner,
        "train": result["trainExamples"], "cal": result["calExamples"],
        "test": result["testExamples"],
        "calibrationWrong": calibrations[winner]["wrongAccepted"],
        "testCorrectCoverage": selected["correctCoverage"],
        "testWrongAccepted": selected["wrongAccepted"],
        "testWrongFraction": selected["wrongCandidateFraction"],
        "testAbstentions": selected["abstained"],
        "testBaselineCorrectCoverage": baseline["correctCoverage"],
        "testBaselineWrongAccepted": baseline["wrongAccepted"],
        "relativeGainClaim": result["qualityClaim"],
        "passesStrictAbsoluteTestRiskGate": true_safe_gain,
        "testClassBreakdown": selected["classBreakdown"],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    roots = sorted(q for q in args.root.iterdir()
                   if q.is_dir() and q.name.startswith("craci-lens-real-"))
    if len(roots) != 4:
        raise RuntimeError(f"Expected exactly four source-bound training jobs; got {len(roots)}")
    rows = [read_exact(root) for root in roots]
    if set(row["profile"] for row in rows) != set(PROFILES):
        raise RuntimeError("Profile missing or duplicated")
    report = {
        "schema": "chibi.lens.real-source-r-audit.v1",
        "runId": 43633058307,
        "harnessSourceSha": SOURCE,
        "dataArchiveSha": ARCHIVE,
        "derivedFeaturesSha": CSV_SHA,
        "verifiedReceipts": len(rows),
        "trainedProfiles": len(rows),
        "actualModelFits": 8,
        "realCropsPerProfile": 1255,
        "allStrictRiskGatesPassed": all(r["passesStrictAbsoluteTestRiskGate"] for r in rows),
        "safePromotionCandidates": sum(r["passesStrictAbsoluteTestRiskGate"] for r in rows),
        "syntheticSource": False,
        "sourceReportedNotProviderAttested": True,
        "officialBopLeaderboardResult": False,
        "wearableIdentityOrAuthorizationQualified": False,
        "actualProviderCost": None,
        "profiles": sorted(rows, key=lambda r:r["profile"]),
    }
    if args.out.exists():
        raise RuntimeError("Audit file exists; do not overwrite frozen result")
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps({k:report[k] for k in ("runId", "verifiedReceipts",
        "trainedProfiles", "actualModelFits", "safePromotionCandidates")},sort_keys=True))


if __name__ == "__main__":
    main()
