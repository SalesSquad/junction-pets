#!/usr/bin/env python3
"""Qualify the real sponsor CSV importer; no financial or browser qualification."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


SPONSOR_COMMIT = "fbdecdedf1a1f49dd641c2e6b9f2b62d0dc0cc8f"
CSV_SIZE = 362796501
CSV_SHA256 = "49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63"
COLUMNS = (
    "customer_id", "bank_account_id", "tx_date", "tx_timestamp", "category",
    "tx_amount_eur", "balance_after_eur", "transaction_type", "merchant_id",
    "mcc_code",
)
MAX_ROWS = 10000
MAX_SAFE_CENTS = 9007199254740991
IMPORT_TIMEOUT_SECONDS = 300


class QualificationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise QualificationError(message)


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def file_identity(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def verify_csv_bytes(path):
    before = file_identity(path)
    require(before[2] == CSV_SIZE, "Sponsor CSV size differs from the pinned LFS object")
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)
    require(byte_count == CSV_SIZE, "Sponsor CSV changed length while hashing")
    require(digest.hexdigest() == CSV_SHA256, "Sponsor CSV SHA256 differs from the pinned LFS object")
    require(file_identity(path) == before, "Sponsor CSV changed while hashing")
    return before


def valid_cents(value, field, line_number):
    # Keep source strings unchanged. No floats, locale guessing or rounding.
    require(
        re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]{1,2})?", value) is not None,
        f"Invalid exact-cent spelling in {field} at source line {line_number}",
    )
    magnitude = value[1:] if value.startswith(("+", "-")) else value
    whole, dot, fraction = magnitude.partition(".")
    cents = int(whole) * 100 + (int(fraction.ljust(2, "0")) if dot else 0)
    require(cents <= MAX_SAFE_CENTS, f"Unsafe cent magnitude in {field} at source line {line_number}")
    return -cents if value.startswith("-") else cents


def independently_select(path):
    customer = None
    selected = []
    record_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        header = reader.fieldnames
        require(header is not None, "Sponsor CSV has no header")
        require(
            len(header) == len(COLUMNS) and len(set(header)) == len(COLUMNS)
            and set(header) == set(COLUMNS),
            "Sponsor CSV must have exactly the ten distinct expected columns",
        )
        require(reader.line_num == 1, "Sponsor CSV header must occupy one physical line")
        for row in reader:
            record_count += 1
            source_line = reader.line_num
            require(None not in row and all(value is not None for value in row.values()),
                    f"CSV column-count mismatch at source line {source_line}")
            require(all("\n" not in value and "\r" not in value for value in row.values()),
                    f"Embedded CSV newlines unsupported at source line {source_line}")
            candidate = row["customer_id"]
            if customer is None and candidate.strip():
                require(candidate == candidate.strip(),
                        f"Ambiguous customer-ID whitespace at source line {source_line}")
                customer = candidate
            if customer is None or candidate != customer:
                continue
            for field in ("tx_amount_eur", "balance_after_eur"):
                valid_cents(row[field], field, source_line)
            expected = {field: row[field] for field in COLUMNS}
            expected["sourceLine"] = source_line
            selected.append(expected)
            require(len(selected) <= MAX_ROWS, "Selected customer exceeds the 10000-row importer cap")
    require(customer is not None and selected, "No nonempty synthetic customer was found")
    return customer, selected, record_count


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Importer JSON contains a duplicate object key")
        result[key] = value
    return result


def run_importer(importer, csv_path, customer, output, source_root):
    # Never print command arguments or child output: they can contain row data.
    return subprocess.run(
        ["node", str(importer), str(csv_path), customer, str(output)],
        cwd=source_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=IMPORT_TIMEOUT_SECONDS,
        check=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve(strict=True)
    csv_path = args.csv.resolve(strict=True)
    require(not os.path.lexists(args.output), "Output must be a new task-owned file")
    output = args.output.resolve()
    require(output != csv_path, "Output cannot replace sponsor input")
    require(source_root not in output.parents and output != source_root,
            "Output must be outside the source checkout")

    expected_sha = os.environ.get("CRACI_SOURCE_SHA", "")
    require(re.fullmatch(r"[0-9a-fA-F]{40}", expected_sha) is not None,
            "CRACI_SOURCE_SHA must be an explicit full 40-hex commit SHA")
    git = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
    )
    require(git.returncode == 0, "Unable to resolve target checkout HEAD")
    source_sha = git.stdout.decode("ascii", errors="strict").strip()
    require(source_sha == expected_sha.lower(), "Target HEAD differs from CRACI_SOURCE_SHA")
    importer = source_root / "solutions/s-pankki-economic-trainer/src/import-sponsor.mjs"
    require(importer.is_file(), "Pinned target does not contain the sponsor importer")
    importer_sha256 = digest_bytes(importer.read_bytes())

    identity = verify_csv_bytes(csv_path)
    customer, expected_rows, record_count = independently_select(csv_path)
    require(file_identity(csv_path) == identity, "Sponsor CSV changed during independent parsing")
    require(not os.path.lexists(output), "Output appeared before importer invocation")

    imported = run_importer(importer, csv_path, customer, output, source_root)
    require(imported.returncode == 0,
            f"Importer failed: exit={imported.returncode}; stderr_sha256={digest_bytes(imported.stderr)}")
    require(output.is_file() and not output.is_symlink(), "Importer did not create a regular output file")
    output_bytes = output.read_bytes()
    actual_rows = json.loads(output_bytes, object_pairs_hook=unique_json_object)
    require(actual_rows == expected_rows,
            "Importer JSON differs from independently parsed fields or original physical line numbers")

    # Exercise the real CLI a second time against the same output, not a mock.
    duplicate = run_importer(importer, csv_path, customer, output, source_root)
    require(duplicate.returncode != 0, "Importer unexpectedly accepted an existing output path")
    require(b"EEXIST" in duplicate.stderr,
            "Duplicate invocation failed for a reason other than exclusive-create protection")
    require(output.is_file() and not output.is_symlink(), "Duplicate invocation replaced output with another file type")
    require(output.read_bytes() == output_bytes, "Duplicate invocation changed existing output bytes")
    require(file_identity(csv_path) == identity, "Sponsor CSV changed during importer qualification")
    require(digest_bytes(importer.read_bytes()) == importer_sha256,
            "Importer source changed during qualification")

    print(json.dumps({
        "status": "passed",
        "scope": "synthetic-sponsor-importer-and-provenance-only",
        "source_sha": source_sha,
        "importer_sha256": importer_sha256,
        "sponsor_commit": SPONSOR_COMMIT,
        "csv_bytes": CSV_SIZE,
        "csv_sha256": CSV_SHA256,
        "csv_records_scanned": record_count,
        "selected_customers": 1,
        "selected_rows": len(expected_rows),
        "exact_cent_values_checked": 2 * len(expected_rows),
        "source_line_provenance": "exact-match",
        "output_bytes": len(output_bytes),
        "output_sha256": digest_bytes(output_bytes),
        "duplicate_overwrite": "refused-with-unchanged-bytes",
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except QualificationError as error:
        print(json.dumps({"status": "failed", "scope": "synthetic-sponsor-importer-and-provenance-only", "error": str(error)}), file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # Exception messages from CSV/JSON/subprocess can include source values.
        print(json.dumps({"status": "failed", "scope": "synthetic-sponsor-importer-and-provenance-only", "error_type": type(error).__name__, "error": "Qualification could not complete; source values and child output withheld"}), file=sys.stderr)
        sys.exit(1)
