#!/usr/bin/env python3
"""Source-bound retrospective audit for the 3 CRACI/R Lens improvements.

This is posthoc REAL-public-image experimental evidence only. Does not grant
deployment, identity, consent or tool authorization; no provider attestation.
"""
import argparse
import json
from pathlib import Path
import zipfile

SOURCE_SHA = "08645c6d83e4fc47093a16220de36098f3f1e1b6"
DATA_SHA = "a6d1ca17664544645a3fc26a7d8d9caba6c1d85b58bea00afc0125e991b9a015"
ARCHIVE_SHA = "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
RUNS = {"risk-upper": 43636400308,
        "metadata-shield": 43636605103,
        "hard-negative": 43636605103}


def load_job(root):
    receipt = json.loads((root/"receipt.json").read_text())
    report_path = root/"artifacts/lens-r3/training-report.json"
    report = json.loads(report_path.read_text())
    admission = json.loads((root/"artifacts/lens-r3/cloud-admission.json").read_text())
    scene_meta = json.loads((root/"artifacts/lens-r3/scene-metadata.json").read_text())
    with zipfile.ZipFile(root/"artifacts/lens-r3/trained-models.zip") as z:
        if set(z.namelist()) != {"training-report.json", "trained-models.rds"}:
            raise RuntimeError("Missing model archive entry")
        if z.read("training-report.json") != report_path.read_bytes():
            raise RuntimeError("Model ZIP report mismatch")
        if z.getinfo("trained-models.rds").file_size < 100:
            raise RuntimeError("Missing actual R model bytes")
    binding = receipt.get("binding") or {}
    if (receipt.get("status") != "succeeded" or receipt.get("issues") or
        not receipt.get("sourceVerified") or not receipt.get("harnessVerified")
        or binding.get("sourceSha") != SOURCE_SHA
        or binding.get("harnessSha") != SOURCE_SHA):
        raise RuntimeError("Model receipt incomplete/unpinned")
    if (admission.get("featureCSVsha256") != DATA_SHA or
        admission.get("sourceArchiveSHA256") != ARCHIVE_SHA or
        admission.get("publicDataOnly") is not True or
        admission.get("rawPixelsUploaded") is not False or
        admission.get("familyMediaUsed") is not False or
        admission.get("personalOCRUsed") is not False or
        admission.get("groundTruthMetadataEvaluationOnly") is not True):
        raise RuntimeError("Private data or provenance boundary violated")
    if (scene_meta.get("sourceArchiveSha256") != ARCHIVE_SHA or
        scene_meta.get("noPersonalPhotos") is not True or
        scene_meta.get("noFramePayloads") is not True):
        raise RuntimeError("Scene provenance failed")
    if (report.get("schema") != "chibi.lens.r3.improvement-study.v1" or
        report.get("sourceArchiveSHA256") != ARCHIVE_SHA or
        report.get("featureCSVsha256") != DATA_SHA or
        report.get("qualifiesForDeployment") is not False or
        report.get("physicalIdentityVerified") is not False or
        report.get("toolAuthorizationGranted") is not False or
        report.get("scientificQualification") !=
          "POSTHOC_EXPLORATORY_ONLY_SAME_PRIOR_BOP_SCENES" or
        report.get("trainCases") != 525 or
        report.get("calibrationCases") != 225 or
        report.get("testCases") != 225):
        raise RuntimeError("Inaccurate model report claims")
    name = report.get("method")
    if name not in RUNS or str(RUNS[name]) not in root.name:
        raise RuntimeError("Method belongs to a different source-bound run")
    for partition in ("baselineCalibration","baselineHeldout",
                      "selectedCalibration","selectedHeldout"):
        m=report[partition]
        if not (m.get("cases") == 225 and
                m["accepted"]+m["abstained"]==225 and
                m["correctAccepted"]+m["wrongAccepted"]==m["accepted"]):
            raise RuntimeError(f"Impossible confusion matrix: {name}/{partition}")
    if report["selectedCalibration"]["wrongAccepted"]>11:
        raise RuntimeError("Calibration constraint exceeded")
    if set(report.get("metadataSlices",{})) != {"scene","sourceClass","brightness"}:
        raise RuntimeError("Metadata explainability missing")
    if report["method"] == "risk-upper" and (
        "exactOneSided95CalibrationBound" not in report["methodDetails"]):
        raise RuntimeError("Missing exact binomial risk evidence")
    if report["method"] == "metadata-shield" and (
        "testBlockedOOD" not in report["methodDetails"]):
        raise RuntimeError("Missing OOD rejection evidence")
    if report["method"] == "hard-negative" and (
        "trainOnlyFoldReports" not in report["methodDetails"] or
        len(report["methodDetails"]["trainOnlyFoldReports"]) != 4):
        raise RuntimeError("Missing four out-of-training-scene teacher folds")
    chosen = report["selectedHeldout"]
    base = report["baselineHeldout"]
    return {
        "method": name, "sourceRunId": RUNS[name],
        "RModelArtifactPresent": True,
        "calibrationWrong": report["selectedCalibration"]["wrongAccepted"],
        "holdoutCorrect": chosen["correctAccepted"],
        "holdoutWrong": chosen["wrongAccepted"],
        "holdoutAbstained": chosen["abstained"],
        "holdoutWrongFraction": chosen["wrongRate"],
        "baselineCorrect": base["correctAccepted"],
        "baselineWrong": base["wrongAccepted"],
        "deltaAcceptedWrong": chosen["wrongAccepted"]-base["wrongAccepted"],
        "deltaAcceptedCorrect": chosen["correctAccepted"]-base["correctAccepted"],
        "descriptiveStrictThreshold": report["wouldPassDescriptiveStrictGate"],
        "deployable": False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pilot",type=Path,required=True)
    p.add_argument("--remaining",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    jobs=[]
    for folder,expected in ((a.pilot,1),(a.remaining,2)):
        paths=sorted(x for x in folder.iterdir() if x.is_dir() and x.name.startswith("craci-lens-r3-"))
        if len(paths)!=expected:
            raise RuntimeError(f"Expected {expected} completed task-owned artifacts, got {len(paths)}")
        jobs.extend(load_job(x) for x in paths)
    if set(j["method"] for j in jobs)!=set(RUNS):
        raise RuntimeError("An R3 improvement method was not run or was duplicated")
    output={
        "schema":"chibi.lens.r3.source-bound-result.v1",
        "harnessSha":SOURCE_SHA, "sourceFeatureCSVsha":DATA_SHA,
        "sourceImageArchiveSha":ARCHIVE_SHA,
        "sourceReportedNotProviderAttested":True,
        "realPublicCameraCropsNotPersonalGlasses":True,
        "posthocReusedTestScene":True,
        "candidateDeploymentAllowed":False,
        "actualProviderBillingEUR":None,
        "verifiedDistinctRuns":2,"verifiedMethods":3,
        "trainedModelsInSourceBoundArchives":3,
        "descriptiveSafeMethods":sum(bool(j["descriptiveStrictThreshold"]) for j in jobs),
        "methods":sorted(jobs,key=lambda x:x["method"]),
    }
    if a.out.exists():raise RuntimeError("Refuse to overwrite prior evidence")
    a.out.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print(json.dumps({k:output[k] for k in (
        "verifiedMethods","trainedModelsInSourceBoundArchives","descriptiveSafeMethods",
        "candidateDeploymentAllowed")},sort_keys=True))
    for j in output["methods"]:
        print(json.dumps(j,sort_keys=True))


if __name__=="__main__":
    main()
