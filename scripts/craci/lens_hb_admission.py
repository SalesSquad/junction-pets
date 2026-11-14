#!/usr/bin/env python3
"""Fail-closed admission of PUBLIC CC0 BOP HB masked Vision numeric features.

No private images, OCR, personal screenshot archives, family photos or user
capture paths are read. There is no generic license or SHA override flag.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ARCHIVE="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
CSV="2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
PARQUET="2b10ed5c8d062a2feee9115fb0c7700521debb38be86ab32377474c893660248"
ID="bop-hb-val-primesense-cc0"
FILES={"admission.json":None,
       "public-hb-object-features.csv":CSV,
       "public-hb-object-features.parquet":PARQUET}

def digest(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def admit(root:Path,register:Path):
    if not root.is_dir() or not register.is_file():
        raise ValueError("Missing verified public fixture or registry")
    if set(f.name for f in root.iterdir())!=set(FILES):
        raise ValueError("Unexpected image, secret, or unreviewed data file")
    for name,sha in FILES.items():
        p=root/name
        if p.is_symlink() or not p.is_file() or p.stat().st_nlink !=1:
            raise ValueError("Unsafe fixture source file path/link")
        if p.stat().st_size>20_000_000:
            raise ValueError("Unbounded public numeric fixture volume")
        if sha and digest(p)!=sha:
            raise ValueError("Source-bound numerical SHA256 mismatch")
    source=json.loads(register.read_text())
    if source.get("schema")!="chibi.lens.source-register.v1":
        raise ValueError("Untrusted source register")
    sources=source.get("sources")
    if not isinstance(sources,list) or not 1<=len(sources)<=64:
        raise ValueError("Unbounded or empty source inventory")
    ids=[x.get("id") for x in sources]
    if len(set(ids))!=len(ids) or ID not in ids:
        raise ValueError("Source ID missing or duplicated")
    for entry in sources:
        if entry.get("status")!="approved_public_benchmark_only" and (
            entry.get("cloud_numeric_features") or entry.get("raw_pixels_cloud")):
            raise ValueError("Private, family or unreviewed source wrongly approved")
    allowed=next(x for x in sources if x["id"]==ID)
    if (allowed.get("kind")!="real_public_object_images" or
        allowed.get("status")!="approved_public_benchmark_only" or
        allowed.get("license")!="CC0-1.0" or
        allowed.get("source_archive_sha256")!=ARCHIVE or
        allowed.get("derived_csv_sha256")!=CSV or
        allowed.get("derived_parquet_sha256")!=PARQUET or
        allowed.get("cloud_numeric_features") is not True or
        allowed.get("raw_pixels_cloud") is not False):
        raise ValueError("New real-public source not explicitly registered")
    a=json.loads((root/"admission.json").read_text())
    if (a.get("schema")!="chibi.lens.hb.real-feature-admission.v1" or
        a.get("sourceLicense")!="CC0-1.0" or
        a.get("sourceArchivePointerSHA256")!=ARCHIVE or
        a.get("numericCSVsha256")!=CSV or
        a.get("numericParquetSHA256")!=PARQUET or
        a.get("revision")!=2 or
        a.get("vectorDimension")!=768 or
        a.get("realPublicCameraCrops")!=655 or
        a.get("distinctPublicFrames")!=192 or
        a.get("sceneSplit")!={"train":[5,9],"cal":[10],"test":[11]} or
        a.get("knownClasses")!=[12,15] or
        a.get("unknownClassesForCalAndTest")!=[3,22,23] or
        a.get("allKnownClassesInAllScenes") is not True or
        a.get("backgroundMaskedBeforeEmbedding") is not True or
        a.get("rawPixelsInCloud") is not False or
        a.get("privatePersonalMediaUsed") is not False or
        a.get("childOrFamilyMediaUsed") is not False or
        a.get("personalOCRUsed") is not False or
        a.get("realWearableEvaluation") is not False or
        a.get("physicalIdentityVerified") is not False or
        a.get("actionAuthorized") is not False):
        raise ValueError("HB source scientific/privacy admission changed")
    return {
      "schema":"chibi.lens.hb.cloud-admission.v1",
      "workId":"CHIBI-LENS-ROOTCAUSE-FIX-20261114",
      "publicDataset":"BOP HomebrewedDB VAL PrimeSense",
      "sourceLicense":"CC0-1.0",
      "sourceArchivePointerSHA256":ARCHIVE,
      "numericCSVsha256":CSV,
      "numericParquetSHA256":PARQUET,
      "sourceProof":"Official HF pointer and selected ZIP member CRC; no full archive hash re-check",
      "sourceNumberOfPhysicalScenes":4,
      "knownClassesPresentAllScenes":True,
      "unknownOpenSetNegativesIncluded":True,
      "cameraRGBPublicOnly":True,
      "onDeviceAppleVisionEmbedding":True,
      "localOriginalRGBUploaded":False,
      "privateOCRUsed":False,
      "familyPhotosUsed":False,
      "cloudTrainingEligible":True,
      "sourceReportedNotProviderAttested":True,
      "noAutomaticProductModelPromotion":True,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--register",type=Path,required=True)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    result=admit(a.root,a.register)
    payload=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        with a.out.open("x") as f:f.write(payload)
    print(payload,end="")

if __name__=="__main__":
    main()
