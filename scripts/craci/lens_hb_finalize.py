#!/usr/bin/env python3
"""Bind locally extracted Apple Vision 768d features to real public BOP HB.

No original PNG, RGB crop, mask, file path or private user data in output.
Pre-register split, known labels and hard negatives before generating model
scores. All image embedding extraction happens on verified local macOS only.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ZIP_SHA="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
SOURCE="bop-hb-val-primesense-public-cc0"
DIMS=768
TRAIN_SCENES=[5,9]
CAL_SCENES=[10]
TEST_SCENES=[11]
KNOWN={"12","15"}
NEGATIVE={"3","22","23"}
FEATURES=[f"v{i:03}" for i in range(DIMS)]
HIST=[f"c{i:02}" for i in range(48)]


def sha_file(path: Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(1<<20),b""):
            h.update(part)
    return h.hexdigest()


def finalize(prepared: Path, vision: Path, out: Path, swift_source: Path, extractor: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not prepared.is_dir() or not vision.is_file() or not out.is_dir() or list(out.iterdir()):
        raise RuntimeError("Prepared observations or fresh empty output missing")
    meta=json.loads((prepared/"rowmeta.json").read_text())
    prepared_receipt=json.loads((prepared/"preparation.json").read_text())
    if prepared_receipt.get("sourceArchivePointerSha256")!=ZIP_SHA:
        raise RuntimeError("Archive pointer changed")
    manifest_lines=(prepared/"manifest.tsv").read_text().splitlines()
    if len(manifest_lines)!=len(meta):
        raise RuntimeError("Manifest row count mismatches public metadata")
    records={}
    first_dims=set()
    with vision.open("r",encoding="utf8") as fh:
        for line in fh:
            r=json.loads(line)
            key=r.get("row_id")
            if key in records or not isinstance(key,str):
                raise RuntimeError("Duplicate or malformed Vision feature")
            vector=r.get("embedding")
            if (r.get("source")!="PUBLIC_HB_CC0" or
                r.get("vision_revision")!=2 or
                r.get("vision_element_type")!="float32" or
                r.get("elements")!=DIMS or
                not isinstance(vector,list) or len(vector)!=DIMS or
                not all(isinstance(v,(float,int)) and math.isfinite(v) for v in vector)):
                raise RuntimeError("Apple Vision model or feature version changed")
            length=math.sqrt(sum(float(x)**2 for x in vector))
            if not math.isfinite(length) or length<1e-9:
                raise RuntimeError("Empty Vision image vector")
            records[key]=[round(float(x)/length,8) for x in vector]
            first_dims.add(r["elements"])
    if set(x["row_id"] for x in meta)!=set(records) or first_dims!={DIMS}:
        raise RuntimeError("Visual vectors incomplete or did not match image identities")
    seen_scene_class={}
    rows=[]
    for i,record in enumerate(meta):
        row_id=record["row_id"]
        if manifest_lines[i]!=row_id+"\t"+record["file"]:
            raise RuntimeError("Mismatch in ordered local image registry")
        if not (prepared/record["file"]).is_file() or sha_file(prepared/record["file"])!=record["crop_sha256"]:
            raise RuntimeError("Image crop unexpectedly modified during extraction")
        split=record["split"]
        scene=record["scene_id"]
        label=str(record["object_id"])
        allowed={"train":TRAIN_SCENES,"cal":CAL_SCENES,"test":TEST_SCENES}
        if (split not in allowed or scene not in allowed[split] or
                label not in (KNOWN | NEGATIVE)):
            raise RuntimeError("Ground-truth scene/class admission failed")
        if split=="train" and label not in KNOWN:
            raise RuntimeError("Distractor class leaked into known-class training")
        if record["known"]!=(label in KNOWN):
            raise RuntimeError("Known class status contradicts ground truth")
        if record["label"]!=(label if label in KNOWN else "UNKNOWN"):
            raise RuntimeError("Unknown open-set label mismatch")
        if len(record["hist"])!=48 or not all(0<=x<=1 for x in record["hist"]):
            raise RuntimeError("Invalid baseline histograms")
        seen_scene_class[(split,scene,label)]=seen_scene_class.get((split,scene,label),0)+1
        values={
           "source":SOURCE,"license":"CC0-1.0","modality":"REAL_RGB_MASKED",
           "row_id":row_id,"split":split,"scene_id":scene,
           "frame_id":record["frame_id"],
           "object_id":int(label),"label":record["label"],
           "known_class":record["known"],
           "visible_fraction":record["bbox_visible_fraction"],
           "mask_coverage":record["visible_mask_coverage"],
           "source_frame_sha256":record["source_frame_sha256"],
           "crop_sha256":record["crop_sha256"],
        }
        values.update({k:v for k,v in zip(HIST,record["hist"])})
        values.update({k:v for k,v in zip(FEATURES,records[row_id])})
        rows.append(values)
    for split,scenes in (("train",TRAIN_SCENES),("cal",CAL_SCENES),("test",TEST_SCENES)):
        for scene in scenes:
            for label in KNOWN:
                if seen_scene_class.get((split,scene,label),0)<25:
                    raise RuntimeError("Insufficient known real class examples per physical scene")
    for split in ("cal","test"):
        for label in NEGATIVE:
            if seen_scene_class.get((split,{"cal":10,"test":11}[split],label),0)<25:
                raise RuntimeError("Insufficient unknown class hard negatives")
    if len(set(r["row_id"] for r in rows))!=len(rows):
        raise RuntimeError("Duplicate image sample")
    if len(set((r["scene_id"],r["frame_id"]) for r in rows))>4*48:
        raise RuntimeError("Unexpected extra real camera frame groups")

    table=pa.Table.from_pylist(rows)
    table=table.replace_schema_metadata({
       "license":"CC0-1.0","source":"BOP HomebrewedDB RGB PrimeSense VALIDATION",
       "archive_sha256_from_HF":"8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f",
       "photos_and_ocr_in_training":"none",
       "AppleVisionRevision":"VNGenerateImageFeaturePrintRequest revision 2",
       "train_scene":"5,9","cal_scene":"10","test_scene":"11",
       "heldout_ground_truth":"never used for model selection"})
    parquet=out/"public-hb-object-features.parquet"
    pq.write_table(table,parquet,compression="zstd",row_group_size=256)
    if pq.read_table(parquet).num_rows!=len(rows):
        raise RuntimeError("Parquet round trip discrepancy")
    csv_file=out/"public-hb-object-features.csv"
    columns=[key for key in table.column_names
             if key not in ("source_frame_sha256","crop_sha256")]
    with csv_file.open("x",newline="",encoding="utf8") as fh:
        writer=csv.DictWriter(fh,fieldnames=columns,lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k:row[k] for k in columns})
    manifest={
       "schema":"chibi.lens.hb.real-feature-admission.v1",
       "sourceLicense":"CC0-1.0",
       "sourceAttribution":"HomebrewedDB: Kaskman et al. ICCVW 2019, BOP official benchmark",
       "sourceURL":"https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip",
       "licenseURL":"https://bop.felk.cvut.cz/datasets/",
       "sourceArchivePointerSHA256":ZIP_SHA,
       "sourceArchivePointerSizeBytes":2354714266,
       "sourceBytesVerification":"Official HF pointer and every selected ZIP member CRC32; not full 2.35GB rehash",
       "featureExtractor":"VNGenerateImageFeaturePrintRequest",
       "revision":2,"vectorDimension":DIMS,
       "visionSwiftSourceSHA256":sha_file(swift_source),
       "preparationPythonSHA256":sha_file(extractor),
       "localVisionJSONLsha256":sha_file(vision),
       "numericCSVsha256":sha_file(csv_file),
       "numericParquetSHA256":sha_file(parquet),
       "realPublicCameraCrops":len(rows),
       "distinctPublicFrames":len(set((r["scene_id"],r["frame_id"]) for r in rows)),
       "recordCountBySplitClass":{"/".join(map(str,k)):v for k,v in sorted(seen_scene_class.items())},
       "sceneSplit":{"train":TRAIN_SCENES,"cal":CAL_SCENES,"test":TEST_SCENES},
       "knownClasses":[12,15],"unknownClassesForCalAndTest":[3,22,23],
       "allKnownClassesInAllScenes":True,
       "backgroundMaskedBeforeEmbedding":True,
       "rawPixelsInCloud":False,"privatePersonalMediaUsed":False,
       "childOrFamilyMediaUsed":False,"personalOCRUsed":False,
       "notOfficialBOPBenchmarkScore":True,
       "sourceReportedNotProviderAttested":True,
       "realWearableEvaluation":False,"physicalIdentityVerified":False,
       "actionAuthorized":False
    }
    (out/"admission.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"rows":len(rows),"frames":manifest["distinctPublicFrames"],
        "counts":manifest["recordCountBySplitClass"],
        "csvSha":manifest["numericCSVsha256"],"parquetSha":manifest["numericParquetSHA256"]},sort_keys=True))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--prepared",type=Path,required=True)
    p.add_argument("--vision",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    home=Path(__file__).parent
    finalize(a.prepared,a.vision,a.out,home/"LensHBFeaturePrint.swift",
             home/"lens_hb_prepare.py")


if __name__=="__main__":
    main()
