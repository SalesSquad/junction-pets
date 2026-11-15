#!/usr/bin/env python3
"""Independent read-only audit of every public HB scene-diverse RGB frame.

Checks public ZIP member CRC and original PNG SHA, then compares decoded
resized RGB pixel bytes to task-owned local PNG. No BOP GT, labels, masks,
personal photos or OCR are downloaded; never opens scene13 annotations.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from hashlib import sha256
import io
import json
from pathlib import Path

URL="https://huggingface.co/datasets/bop-benchmark/hb/resolve/main/hb_val_primesense.zip"
SHA="8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f"
BYTES=2354714266


def check_public_frames(root:Path,output:Path,max_workers:int)->dict:
    from PIL import Image
    from lens_hb_range import ZipHTTP
    from lens_hb_domain_train import read_manifest,file_sha256
    if output.exists():
        raise RuntimeError("Refuse overwrite source audit receipt")
    if max_workers not in (1,2,3,4):
        raise ValueError("Bound public archive network readers to <=4")
    manifest,manifest_sha=read_manifest(root)
    if (manifest.get("schema")!="chibi.lens.hb.domain-detector-diverse-data.v2" or
        manifest.get("plan")!="diverse" or
        manifest.get("sourceArchivePointerSHA256")!=SHA):
        raise RuntimeError("Only fixed public CC0 diverse source can be audited")
    entries=manifest["samples"]
    if len(entries)!=208:
        raise RuntimeError("Unqualified dataset size")
    source=ZipHTTP(URL,SHA,BYTES)
    def check(entry):
        scene=int(entry["scene_id"])
        frame=int(entry["frame_id"])
        member=f"val_primesense/{scene:06d}/rgb/{frame:06d}.png"
        # ZipHTTP never asks for scene GT here; independent original bytes.
        original=source.read(member,max_size=8_000_000)
        if sha256(original).hexdigest()!=entry["source_png_sha256"]:
            raise RuntimeError(f"Public RGB source image substituted: {scene}:{frame}")
        with Image.open(io.BytesIO(original)) as img:
            if img.format!="PNG":
                raise RuntimeError("Original BOP member not a PNG")
            img.load()
            resized=img.convert("RGB").resize((320,240),Image.Resampling.BILINEAR)
            expected_pixels=resized.tobytes()
        with Image.open(root/entry["file"]) as actual:
            if actual.format!="PNG":
                raise RuntimeError("Local task-owned image not PNG")
            actual.load()
            rgb=actual.convert("RGB")
            if rgb.size!=(320,240) or rgb.tobytes()!=expected_pixels:
                raise RuntimeError(f"Public RGB crop pixels differ from source: {scene}:{frame}")
        return entry["split"],scene,frame,sha256(original).hexdigest()
    counts=Counter()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures={pool.submit(check,r):r for r in entries}
        for i,future in enumerate(as_completed(futures),start=1):
            split,scene,frame,digest=future.result()
            counts[(split,scene)]+=1
            if i%25==0:
                print("SOURCE_MEMBER_CRC_SHA_AND_RGB_VERIFIED",i,flush=True)
    if sum(counts.values())!=208 or len(counts)!=12:
        raise RuntimeError("Incomplete BOP source verification")
    result={
      "schema":"chibi.lens.hb.public-source-byte-audit.v1",
      "workId":"CHIBI-LENS-DOMAIN-DETECTOR-V2-20261115",
      "sourceArchivePointerSHA256":SHA,
      "sourceArchivePointerSize":BYTES,
      "archiveFullyRehashed":False,
      "archiveMemberCRCChecked":True,
      "everyOriginalPNGsha256Verified":True,
      "everyLocalResizedPixelVerified":True,
      "sourceManifestSHA256":manifest_sha,
      "verifiedPublicRGBFrames":sum(counts.values()),
      "sourceScenes":{f"{split}/{scene}":n
                      for (split,scene),n in sorted(counts.items())},
      "trainedAndCalibratedOnSealedLabels":False,
      "scene13GTOrMaskRead":False,
      "privateMediaRead":False,
      "providerSignedAttestation":False,
      "licensedCC0SourceClaim":"official BOP HomebrewedDB public validation archive",
    }
    with output.open("x",encoding="utf8") as f:
        f.write(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--workers",type=int,default=4)
    a=p.parse_args()
    result=check_public_frames(a.data_root,a.output,a.workers)
    print("SOURCE_AUDIT_COMPLETE",json.dumps({
        "verified":result["verifiedPublicRGBFrames"],
        "manifest_sha":result["sourceManifestSHA256"],
        "GT13_not_read":result["scene13GTOrMaskRead"] is False,
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
