#!/usr/bin/env python3
"""Fail-closed CRACI admission for the exact public real YCBV R8 metadata data.

Never reads or copies family/child images, ScreenshotContext archives, OCR,
personal glasses capture or event videos. SHA/source license are pre-pinned.
"""
import argparse
import hashlib
import json
from pathlib import Path

ARCHIVE_SHA="c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
CSV_SHA="a6d1ca17664544645a3fc26a7d8d9caba6c1d85b58bea00afc0125e991b9a015"
PARQUET_SHA="e7862adbefc0679c28223363893e722d0bb2d91335865a14fc1cca6ac891fa14"
METADATA_SHA="7a66a3ad7d96d9dca5c688e639ab71bdf87e4b81a9b2ffdf349b2c1766a1aae6"
SOURCE_REGISTRY_ID="bop-ycbv-contrast-r8-mit"
FILES={"contrast-features.csv":CSV_SHA,
       "contrast-features.parquet":PARQUET_SHA,
       "scene-metadata.json":METADATA_SHA,
       "admission.json":None}


def digest(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()


def admit(root,registry):
    if not root.is_dir() or set(q.name for q in root.iterdir())!=set(FILES):
        raise ValueError("Missing or extra unreviewed files")
    for name,want in FILES.items():
        p=root/name
        if p.is_symlink() or not p.is_file() or p.stat().st_nlink!=1:
            raise ValueError("Unexpected source file type/link")
        if p.stat().st_size>4_000_000:
            raise ValueError("Data volume not bounded")
        if want and digest(p)!=want:
            raise ValueError("Admitted SHA256 mismatch")
    a=json.loads((root/"admission.json").read_text())
    m=json.loads((root/"scene-metadata.json").read_text())
    register=json.loads(registry.read_text())
    if register.get("schema")!="chibi.lens.source-register.v1":
        raise ValueError("Source registry schema")
    sources=register.get("sources")
    if not isinstance(sources,list) or len(sources)>64:
        raise ValueError("Registry absent/unbounded")
    ids=[x.get("id") for x in sources]
    if len(ids)!=len(set(ids)) or SOURCE_REGISTRY_ID not in ids:
        raise ValueError("Duplicate/missing source entry")
    for row in sources:
        if row.get("status")!="approved_public_benchmark_only" and (
            row.get("cloud_numeric_features") or row.get("raw_pixels_cloud")):
            raise ValueError("Forbidden private source escalation")
    allowed=[s for s in sources if s["id"]==SOURCE_REGISTRY_ID][0]
    if (allowed.get("status")!="approved_public_benchmark_only" or
        allowed.get("license")!="MIT" or
        allowed.get("kind")!="real_public_object_images" or
        allowed.get("source_archive_sha256")!=ARCHIVE_SHA or
        allowed.get("derived_csv_sha256")!=CSV_SHA or
        allowed.get("derived_parquet_sha256")!=PARQUET_SHA or
        allowed.get("source_metadata_sha256")!=METADATA_SHA or
        allowed.get("cloud_numeric_features") is not True or
        allowed.get("raw_pixels_cloud") is not False):
        raise ValueError("Source license or approved exact digest missing")
    if (a.get("schema")!="chibi.lens.real-contrast-source.v1" or
        a.get("license")!="MIT" or
        a.get("sourceArchiveSha256")!=ARCHIVE_SHA or
        a.get("csvSha256")!=CSV_SHA or
        a.get("parquetSha256")!=PARQUET_SHA or
        a.get("sceneMetadataSha256")!=METADATA_SHA or
        a.get("trainingAllowed") is not True or
        a.get("rawPixelsCloud") is not False or
        a.get("familyOrUserPhotos") is not False or
        a.get("inferenceHasGroundTruthVisibility") is not False or
        a.get("sourceCropCount")!=975 or a.get("sourceImageCount")!=600):
        raise ValueError("Real source admission contract mismatch")
    expected_splits={"train":[48,49,51,54],"cal":[55],"test":[56,57,58]}
    if (a.get("sourceSceneGroups")!=expected_splits or
        m.get("schema")!="chibi.lens.public-scene-metadata.v1" or
        m.get("sourceArchiveSha256")!=ARCHIVE_SHA or
        m.get("sceneSplits")!=expected_splits or
        m.get("objectClasses")!=[1,3,12] or
        m.get("noPersonalPhotos") is not True or
        m.get("noOCR") is not True or
        m.get("noFramePayloads") is not True):
        raise ValueError("Scene/metadata provenance contract mismatch")
    return {
      "schema":"chibi.lens.r8-cloud-admission.v1",
      "workId":"CHIBI-LENS-R8-METADATA-20261114",
      "sourceId":SOURCE_REGISTRY_ID,
      "sourceLicense":"MIT",
      "sourceArchiveSHA256":ARCHIVE_SHA,
      "featureCSVsha256":CSV_SHA,
      "featureParquetSHA256":PARQUET_SHA,
      "sceneMetadataSHA256":METADATA_SHA,
      "physicalCameraRGB":True,"publicDataOnly":True,
      "rawPixelsUploaded":False,"familyMediaUsed":False,
      "personalOCRUsed":False,
      "observedMetadataOnlyForInference":True,
      "groundTruthMetadataEvaluationOnly":True,
      "sceneHeldout":True,"newObjectClasses":[1,3,12],
      "sourceBound":True,"providerAttested":False,
      "wearableIdentityVerified":False,"actionAuthorizationGranted":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--register",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    report=admit(a.fixture,a.register)
    payload=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        with a.out.open("x") as f:f.write(payload)
    print(payload,end="")


if __name__=="__main__":
    main()
