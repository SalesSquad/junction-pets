#!/usr/bin/env python3
"""Extract PUBLIC real-image YCB-V object-crop features; no family media.

Pre-registered scene-heldout trial, not a BOP leaderboard evaluation. Source
is the BOP-HuggingFace ycbv_test_bop19.zip original archive (MIT license).
The script never sends image pixels/OCR/user data outside the local host.
"""
from __future__ import annotations
import argparse
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import zipfile

ARCHIVE_SHA256 = "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
SOURCE_URL = "https://huggingface.co/datasets/bop-benchmark/ycbv/resolve/main/ycbv_test_bop19.zip"
SOURCE_PAGE = "https://bop.felk.cvut.cz/datasets/"
LICENSE = "MIT"
OBJECT_IDS = (4, 6, 9, 15)
SCENE_SPLITS = {
    "train": (48, 49, 50, 51, 54, 55, 58),
    "cal": (52, 53, 56, 57),
    "test": (59,),
}
FEATURE_SCHEMA = "chibi.lens.ycbv.real-pixel-features.v1"
KEY_RE = re.compile(r"^[0-9]{1,6}$")


def digest_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(1 << 20), b""):
            h.update(piece)
    return h.hexdigest()


def image_features(image) -> list[float]:
    """48 cheap visual features, computed only from BOP real object pixels."""
    from PIL import Image, ImageStat
    rgb = image.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR)
    pixels = list(rgb.getdata())
    n = len(pixels)
    channels = [[px[c] for px in pixels] for c in range(3)]
    histogram = [sum(v // 32 == bin_ for v in channel) / n
                 for channel in channels for bin_ in range(8)]
    mono = list(rgb.convert("L").getdata())
    cells = [sum(mono[y * 32 + x] for y in range(cy * 8, (cy + 1) * 8)
                 for x in range(cx * 8, (cx + 1) * 8)) / (64 * 255)
             for cy in range(4) for cx in range(4)]
    gradient = []
    for gy in range(2):
        for gx in range(2):
            horiz = sum(abs(mono[y*32+x] - mono[y*32+x-1])
                        for y in range(gy*16, gy*16+16)
                        for x in range(gx*16+1, gx*16+16))
            vert = sum(abs(mono[y*32+x] - mono[(y-1)*32+x])
                       for y in range(gy*16+1, gy*16+16)
                       for x in range(gx*16, gx*16+16))
            gradient += [horiz/(16*15*255), vert/(15*16*255)]
    values = histogram + cells + gradient
    if len(values) != 48 or not all(0 <= v <= 1 for v in values):
        raise RuntimeError("Unbounded visual feature")
    return [round(float(x), 9) for x in values]


def export(archive: Path, output: Path, frames_per_scene: int):
    from PIL import Image, ImageFile
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not 10 <= frames_per_scene <= 75:
        raise ValueError("Need 10..75 distinct real frames per scene")
    if not output.is_dir() or any(output.iterdir()):
        raise RuntimeError("Output root must exist and be empty, no overwrite")
    actual_sha = digest_file(archive)
    if actual_sha != ARCHIVE_SHA256:
        raise RuntimeError("Pinned public dataset archive SHA256 mismatch")
    if set().union(*map(set, SCENE_SPLITS.values())) != set(range(48, 60)):
        raise RuntimeError("Incomplete scene split")
    if sum(len(x) for x in SCENE_SPLITS.values()) != 12:
        raise RuntimeError("Scene split overlap")

    rows, rejected, class_count = [], Counter(), Counter()
    with zipfile.ZipFile(archive, "r") as z:
        entries = set(z.namelist())
        for path in entries:
            # Never unpack source-supplied paths, and reject zip-slip even when
            # producer directly reads members by exact constructed paths.
            if path.startswith("/") or ".." in Path(path).parts or "\\" in path:
                raise RuntimeError("Unsafe upstream archive path")
        for split, scenes in SCENE_SPLITS.items():
            for scene in scenes:
                root = f"test/{scene:06d}/"
                gt_path = root+"scene_gt.json"
                info_path = root+"scene_gt_info.json"
                if gt_path not in entries or info_path not in entries:
                    raise RuntimeError("Missing exact BOP scene annotation")
                gt = json.loads(z.read(gt_path))
                info = json.loads(z.read(info_path))
                choices = sorted(set(gt).intersection(info), key=int)
                if len(choices) < frames_per_scene:
                    raise RuntimeError("Not enough annotated real frames")
                # Evenly sample within each REAL scene. No seed based on labels.
                ids = [choices[(i * len(choices)) // frames_per_scene]
                       for i in range(frames_per_scene)]
                if len(set(ids)) != frames_per_scene:
                    raise RuntimeError("Frame overlap inside scene")
                for frame_id in ids:
                    if not KEY_RE.fullmatch(frame_id):
                        raise RuntimeError("Non-numeric BOP frame ID")
                    name = root+"rgb/"+f"{int(frame_id):06d}.png"
                    if name not in entries:
                        raise RuntimeError("Missing recorded RGB source image")
                    zinfo = z.getinfo(name)
                    if zinfo.file_size > 6_000_000:
                        raise RuntimeError("Oversize source frame")
                    payload = z.read(name)
                    if sha256(payload).digest() == b"\0"*32:
                        raise RuntimeError("Invalid image digest")
                    with Image.open(io.BytesIO(payload)) as im:
                        if im.format != "PNG":
                            raise RuntimeError("Expected actual BOP PNG")
                        im.load()
                        image = im.convert("RGB")
                        width, height = image.size
                    if not 200 <= width <= 3000 or not 200 <= height <= 3000:
                        raise RuntimeError("Unexpected camera size")
                    objects = gt[frame_id]
                    objects_info = info[frame_id]
                    if len(objects) != len(objects_info):
                        raise RuntimeError("BOP annotation alignment invalid")
                    for idx, (obj, data) in enumerate(zip(objects, objects_info)):
                        label = int(obj["obj_id"])
                        if label not in OBJECT_IDS:
                            continue
                        bbox = data.get("bbox_visib")
                        if not isinstance(bbox, list) or len(bbox) != 4:
                            rejected["missing_bbox"] += 1
                            continue
                        x, y, w, h = (int(v) for v in bbox)
                        if (w < 24 or h < 24 or x < 0 or y < 0 or
                                x+w > width or y+h > height):
                            rejected["small_or_invalid_bbox"] += 1
                            continue
                        vis = float(data.get("visib_fract", 0))
                        if vis < 0.20:
                            rejected["low_visibility"] += 1
                            continue
                        crop = image.crop((x, y, x+w, y+h))
                        features = image_features(crop)
                        if not (0 <= vis <= 1):
                            raise RuntimeError("Invalid visibility fraction")
                        row = {
                            "source": "bop-ycbv-mit",
                            "license": LICENSE,
                            "modality": "REAL_RGB",
                            "split": split,
                            "scene_id": scene,
                            "frame_id": int(frame_id),
                            "object_id": label,
                            "visible_fraction": round(vis, 6),
                            "frame_sha256": sha256(payload).hexdigest(),
                            "crop_group_id": sha256(
                                f"{scene}:{frame_id}:{label}".encode()).hexdigest(),
                        }
                        row.update({f"f{i:02d}": val
                                    for i, val in enumerate(features)})
                        rows.append(row)
                        class_count[(split, label)] += 1

    for split in SCENE_SPLITS:
        for label in OBJECT_IDS:
            if class_count[(split, label)] < 10:
                raise RuntimeError(f"Too few real labeled crops {split}/{label}")
    if len(set(r["crop_group_id"] for r in rows)) != len(rows):
        raise RuntimeError("Repeated crop identity across splits")
    if len({r["frame_sha256"] for r in rows}) < 100:
        raise RuntimeError("Insufficient physically distinct frames")
    if set().union(*(set(SCENE_SPLITS[s]) for s in SCENE_SPLITS)) != set(range(48,60)):
        raise RuntimeError("Unrecognized split scene")

    table = pa.Table.from_pylist(rows)
    table = table.replace_schema_metadata({
        "dataset": "bop-ycbv", "license": "MIT", "kind": FEATURE_SCHEMA,
        "source_archive_sha256": ARCHIVE_SHA256,
        "pii": "PUBLIC_OBJECT_IMAGES_ONLY_NO_PERSONAL_USER_DATA",
    })
    pq.write_table(table, output / "real-object-features.parquet",
                   compression="zstd", row_group_size=512)
    readback = pq.read_table(output / "real-object-features.parquet")
    if readback.num_rows != len(rows) or readback.num_columns != table.num_columns:
        raise RuntimeError("Parquet round trip incomplete")

    # Portable CSV for the existing R/CRACI runner; images remain local.
    import csv
    fields = [col for col in table.column_names if col not in
              ("frame_sha256", "crop_group_id")]
    with (output/"real-object-features.csv").open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({field: row[field] for field in fields})
    evidence = {
        "schema": "chibi.lens.real-source-admission.v1",
        "status": "approved_public_benchmark_only",
        "datasetId": "bop-ycbv-test-bop19",
        "sourceUrl": SOURCE_URL,
        "officialLicenseEvidence": SOURCE_PAGE,
        "sourceLicense": "MIT",
        "sourceArchiveSha256": ARCHIVE_SHA256,
        "sourceArchiveBytes": archive.stat().st_size,
        "realCameraObjectCropFeatures": len(rows),
        "uniqueRealFrames": len({r["frame_sha256"] for r in rows}),
        "framesPerScene": frames_per_scene,
        "splitScenes": {k:list(v) for k,v in SCENE_SPLITS.items()},
        "objectClasses": list(OBJECT_IDS),
        "countsBySplitAndClass": {f"{s}:{l}": class_count[(s,l)]
                                  for s in SCENE_SPLITS for l in OBJECT_IDS},
        "rejected": dict(rejected),
        "parquetSha256": digest_file(output/"real-object-features.parquet"),
        "csvSha256": digest_file(output/"real-object-features.csv"),
        "sourceReported": True, "providerAttested": False,
        "rawPixelsExported": False,
        "licenseUse": "internal-permissive-research-derivatives",
        "notBopLeaderboardComparable": True,
        "physicalIdentityVerified": False, "actionAuthorized": False,
        "excluded": [
            "private owner ceremony recordings", "family camera media",
            "ScreenshotContext personal iCloud archives", "Taimi Lens vault",
        ],
        "claim": "Real physical object pixels + BOP label ground truth, no private family data",
    }
    (output/"admission.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"admitted":len(rows),"distinct_frames":evidence["uniqueRealFrames"],
                      "parquetSha256":evidence["parquetSha256"],
                      "csvSha256":evidence["csvSha256"],
                      "counts":evidence["countsBySplitAndClass"]},sort_keys=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames-per-scene", type=int, default=75)
    a=p.parse_args()
    export(a.archive, a.out, a.frames_per_scene)


if __name__ == "__main__":
    main()
