#!/usr/bin/env python3
"""Audit original-vs-repaired CRACI public HomebrewedDB selection receipts.

The two repaired jobs reuse historical heldout scene 11 and are only exploratory
SOURCE BUG REPAIR evidence. This tool does not deploy, attest provider billing,
grant wearable identity, or alter the original experiment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import zipfile

ORIGINAL_SHA="3f8d57cbd47e07be97137e03121205248e88d56f"
REPAIRED_SHA="8ef3dab472aeda585d61d5fd650d5002c59c1ca9"
DATA_SHA="2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
ARCHIVE_SHA="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"


def audit_one(folder,sha):
    candidates=sorted(folder.glob("craci-lens-hb-*"))
    if not candidates:
        raise RuntimeError(f"Missing source-bound HB CRACI archive: {folder}")
    reports=[]
    for root in candidates:
        if not root.is_dir():
            raise RuntimeError("Unexpected artifact entry")
        receipt=json.loads((root/"receipt.json").read_text())
        reportfile=root/"artifacts/lens-hb/training-report.json"
        report=json.loads(reportfile.read_text())
        admission=json.loads((root/"artifacts/lens-hb/cloud-admission.json").read_text())
        with zipfile.ZipFile(root/"artifacts/lens-hb/trained-models.zip") as z:
            if set(z.namelist())!={"training-report.json","trained-models.rds"}:
                raise RuntimeError("Missing immutable model evidence")
            if z.read("training-report.json")!=reportfile.read_bytes():
                raise RuntimeError("Report mismatch with model archive")
            if z.getinfo("trained-models.rds").file_size < 100:
                raise RuntimeError("Empty trained model bytes")
        bind=receipt.get("binding") or {}
        if (receipt.get("status")!="succeeded" or receipt.get("issues")
            or receipt.get("sourceVerified") is not True
            or receipt.get("harnessVerified") is not True
            or bind.get("sourceSha")!=sha or bind.get("harnessSha")!=sha
            or bind.get("workload")!="lens-hb-vision"):
            raise RuntimeError("Source/harness unqualified")
        if (admission.get("cloudTrainingEligible") is not True or
            admission.get("numericCSVsha256")!=DATA_SHA or
            admission.get("sourceArchivePointerSHA256")!=ARCHIVE_SHA or
            admission.get("localOriginalRGBUploaded") is not False or
            admission.get("privateOCRUsed") is not False or
            admission.get("familyPhotosUsed") is not False):
            raise RuntimeError("Private data/provenance gate failed")
        baseline=report["heldoutBaseline"]
        selected=report["heldoutSelected"]
        cal=report["calibrationSelected"]
        if (report.get("sourceNumericCSVsha256")!=DATA_SHA
            or report.get("sourceArchivePointerSha256")!=ARCHIVE_SHA
            or report.get("deploymentAllowed") is not False
            or report.get("physicalIdentityVerified") is not False
            or report.get("agentActionAuthorized") is not False
            or report.get("trainExamples")!=186
            or report.get("calibrationExamples")!=234
            or report.get("testExamples")!=235
            or selected["knownCount"]!=93 or selected["unknownCount"]!=142):
            raise RuntimeError("Invalid source-scoped scientific claim")
        for part in (baseline,selected,cal):
            if (part["accepted"]+part["abstained"]!=part["n"]
                or part["correctKnown"]+part["wrongTotal"]!=part["accepted"]):
                raise RuntimeError("Impossible accepted/wrong confusion counts")
        if cal["wrongTotal"]>11:
            raise RuntimeError("Calibration exceeded 5% empirical risk threshold")
        if sha==REPAIRED_SHA and (
            report.get("sourceSelectorRepair")!="CALIBRATION_FIRST_SAFE_PARETO_FILTER_THEN_RANK"
            or report.get("sourceDefectRepairRetest") is not True
            or report.get("previouslyReportedHeldoutBaseline") is not True):
            raise RuntimeError("Repaired source concealed historical test re-exposure")
        reports.append({"modelFamily":report["modelFamily"],
              "selectedCandidate":report["selectedCandidate"],
              "correctKnown":selected["correctKnown"],
              "knownCount":selected["knownCount"],
              "wrongAccepted":selected["wrongTotal"],
              "testCases":selected["n"],
              "unknownFalseAccepted":selected["unknownAccepted"],
              "unknownCount":selected["unknownCount"],
              "accepted":selected["accepted"],
              "acceptedPrecision":selected["acceptedPrecision"],
              "calibrationCorrectKnown":cal["correctKnown"],
              "calibrationWrong":cal["wrongTotal"],
              "calibrationAccepted":cal["accepted"],
              "scientificClaim":report["scientificClaim"],
              "descriptiveSafetyCriteriaMet":report["descriptiveSafetyCriteriaMet"]})
    return reports


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original-pilot",type=Path,required=True)
    p.add_argument("--original-remaining",type=Path,required=True)
    p.add_argument("--repair",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    original=audit_one(args.original_pilot,ORIGINAL_SHA)+audit_one(args.original_remaining,ORIGINAL_SHA)
    repaired=audit_one(args.repair,REPAIRED_SHA)
    if (set(x["modelFamily"] for x in original)!={"color","vision_prototype","vision_pca","vision_guard"}
        or set(x["modelFamily"] for x in repaired)!={"vision_prototype","vision_guard"}):
        raise RuntimeError("Expected four original and two distinct repaired model jobs")
    if any(x["accepted"]!=0 or x["correctKnown"]!=0 for x in original):
        raise RuntimeError("Repaired baseline source defect not reproduced")
    for report in repaired:
        if not (report["correctKnown"]==74 and report["wrongAccepted"]==3
            and report["unknownFalseAccepted"]==2 and report["accepted"]==77
            and report["calibrationCorrectKnown"]==56 and report["calibrationWrong"]==0):
            raise RuntimeError("Unexpected corrected source outcome")
    summary={
      "workId":"CHIBI-LENS-ROOTCAUSE-FIX-20261114",
      "originalSourceSha":ORIGINAL_SHA,
      "correctedSourceSha":REPAIRED_SHA,
      "sourceArchivePointerSha":ARCHIVE_SHA,
      "numericFeatureCSVsha":DATA_SHA,
      "originalRunIds":[43640473902,43640703367],
      "repairedRunId":43643014716,
      "originalModelJobsVerified":len(original),
      "repairedModelJobsVerified":len(repaired),
      "historicalSourceBug":"BEST_CANDIDATE_PICKED_BEFORE_STRICT_RISK_ELIGIBILITY_FILTER",
      "regressionScope":"ONLY_VISION_PROTOTYPE_AND_VISION_GUARD_CHANGED_HISTORICAL_SOURCE",
      "knownCoverage":"74/93 = 79.57% heldout source-scoped",
      "wrongAccepted":"3/235 = 1.28% total heldout source-scoped",
      "unknownFalseAccepted":"2/142 = 1.41% unknown heldout source-scoped",
      "precisionAccepted":"74/77 = 96.10% heldout source-scoped",
      "allPriorModelWeightsPreserved":True,
      "trueIndependentFinalRevalidation":False,
      "priorHeldoutSceneAlreadySeenInHistoricalRun":True,
      "fieldCameraOrProductGeneralizationProven":False,
      "physicalIdentityOrActionAuthorizationGranted":False,
      "providerSignedAttestation":False,
      "actualProviderCostEur":None,
      "modelDeployed":False,
      "originalModels":sorted(original,key=lambda x:x["modelFamily"]),
      "correctedModels":sorted(repaired,key=lambda x:x["modelFamily"]),
    }
    if args.output.exists():raise RuntimeError("Refuse to overwrite audit output")
    args.output.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:summary[k] for k in ("originalModelJobsVerified",
        "repairedModelJobsVerified","knownCoverage","wrongAccepted",
        "unknownFalseAccepted","precisionAccepted","modelDeployed")},sort_keys=True))


if __name__=="__main__":
    main()
