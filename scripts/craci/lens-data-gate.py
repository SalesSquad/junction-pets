#!/usr/bin/env python3
"""Fail-closed privacy, license and byte-provenance gate for Lens R training.

No private files are read by this command. The only admission presently
implemented is the exact approved MIT-licensed PUBLIC BOP YCB-V numeric fixture.
There is intentionally NO flag to override consent/privacy/rights reviews.
"""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_ID = "bop-ycbv-test-public-mit"
SOURCE_ARCHIVE = "c0c11251849877e7b2f373f6c7acf54739dc69d0fb2649c20050ca977bf5513d"
LICENSE_PAGE = "https://bop.felk.cvut.cz/datasets/"
EXPECTED_CSV = "c2374f53bc510b6655623f5fa05bb23d08bd1531f24b0aa4e2bcdccab11899a6"
EXPECTED_PARQUET = "be31ea09fcbaeb2adb67cdcbd9a248b65bf5444defe293cbc48cf4c29c37b491"
STATUSES = {"approved_public_benchmark_only", "quarantined_not_training",
            "synthetic_only_not_real_training"}


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(1024*1024), b""):
            h.update(part)
    return h.hexdigest()


def admit(register: Path, source_id: str, fixture_dir: Path):
    data = json.loads(register.read_text(encoding="utf8"))
    if data.get("schema") != "chibi.lens.source-register.v1":
        raise ValueError("Untrusted source register schema")
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) > 64:
        raise ValueError("Missing or unbounded source register")
    ids = [s.get("id") for s in sources]
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError("Duplicate or empty source IDs")
    for source in sources:
        if source.get("status") not in STATUSES:
            raise ValueError("Unreviewed/unknown status must not be treated as training permission")
        if (source.get("status") != "approved_public_benchmark_only" and
                (source.get("cloud_numeric_features") or source.get("raw_pixels_cloud"))):
            raise ValueError("Private, synthetic or unreviewed source incorrectly allowed in cloud")
    matches = [s for s in sources if s["id"] == source_id]
    if len(matches) != 1:
        raise ValueError("Requested source is missing or ambiguous")
    source = matches[0]
    if (source_id != SOURCE_ID or
            source["kind"] != "real_public_object_images" or
            source["status"] != "approved_public_benchmark_only" or
            source["license"] != "MIT" or
            source.get("license_evidence") != LICENSE_PAGE or
            source.get("source_archive_sha256") != SOURCE_ARCHIVE or
            source.get("source_bytes") != 660198701 or
            not source.get("cloud_numeric_features") or
            source.get("raw_pixels_cloud") is not False):
        raise ValueError("Source is NOT admitted for cloud training")

    known_files = {"real-object-features.csv", "real-object-features.parquet",
                   "admission.json"}
    if not fixture_dir.is_dir() or set(p.name for p in fixture_dir.iterdir()) != known_files:
        raise ValueError("Public feature fixture files mismatch or extra files present")
    for name in known_files:
        p = fixture_dir / name
        if p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1:
            raise ValueError("Unsafe local file type for public derived features")
    receipt = json.loads((fixture_dir / "admission.json").read_text(encoding="utf8"))
    if (receipt.get("schema") != "chibi.lens.real-source-admission.v1" or
            receipt.get("status") != "approved_public_benchmark_only" or
            receipt.get("sourceArchiveSha256") != SOURCE_ARCHIVE or
            receipt.get("sourceLicense") != "MIT" or
            receipt.get("officialLicenseEvidence") != LICENSE_PAGE or
            receipt.get("rawPixelsExported") is not False or
            receipt.get("physicalIdentityVerified") is not False or
            receipt.get("actionAuthorized") is not False or
            receipt.get("notBopLeaderboardComparable") is not True or
            receipt.get("realCameraObjectCropFeatures") != 1255 or
            receipt.get("uniqueRealFrames") != 825 or
            receipt.get("csvSha256") != EXPECTED_CSV or
            receipt.get("parquetSha256") != EXPECTED_PARQUET):
        raise ValueError("Feature admission receipt or privacy claim invalid")
    csv = fixture_dir / "real-object-features.csv"
    parquet = fixture_dir / "real-object-features.parquet"
    if digest(csv) != EXPECTED_CSV or digest(parquet) != EXPECTED_PARQUET:
        raise ValueError("Feature bytes do not match admitted public source")
    if csv.stat().st_size > 4_000_000 or parquet.stat().st_size > 4_000_000:
        raise ValueError("Unexpected derived fixture byte volume")

    return {
        "schema": "chibi.lens.cloud-admission.v1",
        "workId": data["work_id"], "sourceId": source_id,
        "sourceArchiveSha256": SOURCE_ARCHIVE,
        "derivedCsvSha256": EXPECTED_CSV,
        "derivedParquetSha256": EXPECTED_PARQUET,
        "realPixelObjectCrops": 1255, "uniquePublicFrames": 825,
        "license": "MIT", "privacyScope": "approved_public_object_features_only",
        "familyMediaAccessed": False, "privateOCRAccessed": False,
        "rawPixelsUploaded": False, "cloudTrainingEligible": True,
        "rightsAndDigest": "source-reported, pinned official dataset + SHA256",
        "realDeviceIdentityVerified": False, "actionAuthorized": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--register", type=Path, required=True)
    p.add_argument("--source-id", required=True)
    p.add_argument("--fixture-dir", type=Path, required=True)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    report = admit(args.register, args.source_id, args.fixture_dir)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf8") as f:
            f.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
