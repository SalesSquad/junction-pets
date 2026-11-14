#!/usr/bin/env python3
"""Six independent source-bound negative rounds for the public HB scene8 gate.

Only already-public numeric data; no images, training, threshold fitting, test
metric re-evaluation, or production permissions. Each round creates a distinct
temporary data/manifest mutation and proves the unchanged gate fails closed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

WORK_ID = "CHIBI-LENS-SIX-SCENE8-20261115"
CASES = (
    "tampered_numeric_row",
    "duplicated_source_row",
    "outside_source_symlink",
    "revoked_public_license",
    "false_both_class_qualification",
    "train_scene_leakage",
)
ORIGINAL_SOURCE_SHA = "2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
FRESH_SCENE8_SHA = "4c29e622d2dd4f709792ef0c41e7a09d28f16020ef941b5b64a1cc8469ae464d"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gate(source: Path):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("Missing original ordinary source gate")
    spec = importlib.util.spec_from_file_location("public_hb8_gate", source)
    if not spec or not spec.loader:
        raise RuntimeError("Could not load source-bound gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "admit", None)):
        raise RuntimeError("Missing exact-source admit()")
    return module


def run(source_root: Path, round_number: int, out: Path | None) -> dict:
    if round_number not in range(1, 7):
        raise ValueError("Exactly six preregistered rounds only")
    script = source_root / "scripts/craci/lens_hb_scene8_admission.py"
    old = source_root / "fixtures/lens-hb-cc0-vision-20261114/public-hb-object-features.csv"
    fresh = source_root / "fixtures/lens-hb-scene8-ood-20261114/fresh-scene8-public-ood.csv"
    manifest = source_root / "fixtures/lens-hb-scene8-ood-20261114/admission.json"
    if digest(old) != ORIGINAL_SOURCE_SHA or digest(fresh) != FRESH_SCENE8_SHA:
        raise RuntimeError("Do not test changed public source samples")
    gate = load_gate(script)
    control = gate.admit(old, fresh, manifest)
    if control["knownPresent"] != [15] or control["knownAbsent"] != [12] or \
       control["modelTrainingOnHeldoutAllowed"] is not False or \
       control["actionAuthorized"] is not False:
        raise RuntimeError("Original source gate accepted an unsafe calibration or claim")
    with tempfile.TemporaryDirectory(prefix=f"lens-scene8-round-{round_number}-") as directory:
        temp = Path(directory)
        m = temp / "candidate.json"
        csvfile = temp / "candidate.csv"
        m.write_bytes(manifest.read_bytes())
        v = json.loads(m.read_text())
        expected = ""
        if round_number == 1:
            with fresh.open(newline="", encoding="utf8") as input_file:
                reader = csv.DictReader(input_file)
                rows = list(reader)
                fields = reader.fieldnames
            if len(rows) != 282 or not fields:
                raise RuntimeError("Expected source sample mutated")
            rows[round_number - 1]["v000"] = "0.9999999"
            with csvfile.open("x", newline="", encoding="utf8") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            expected = "Source SHA256 mismatch"
        elif round_number == 2:
            with fresh.open(newline="", encoding="utf8") as input_file:
                reader = csv.DictReader(input_file)
                rows = list(reader)
                fields = reader.fieldnames
            if len(rows) != 282 or not fields:
                raise RuntimeError("Expected source row total")
            rows.append(dict(rows[0]))
            with csvfile.open("x", newline="", encoding="utf8") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            expected = "Source SHA256 mismatch"
        elif round_number == 3:
            csvfile.symlink_to(fresh)
            expected = "Only pinned ordinary public numerical files"
        else:
            shutil.copyfile(fresh, csvfile)
            if round_number == 4:
                v["sourceLicense"] = "revoked_not_approved"
            elif round_number == 5:
                v["canQualifyTwoClassObjectRecognition"] = True
            else:
                v["sourceTrainScenes"] = [5, 8]
            m.write_text(json.dumps(v, sort_keys=True) + "\n")
            expected = "Untrusted public source rights, split or claim"
        if csvfile.exists() and not csvfile.is_symlink() and \
           round_number in (1, 2) and digest(csvfile) == FRESH_SCENE8_SHA:
            raise RuntimeError("Mutation unexpectedly preserved source hash")
        try:
            gate.admit(old, csvfile, m)
        except RuntimeError as error:
            message = str(error)
            if expected not in message:
                raise RuntimeError(f"Unexpected denial for {CASES[round_number - 1]}: {message}")
        else:
            raise RuntimeError(f"FAIL OPEN: {CASES[round_number - 1]}")
    receipt = {
        "schema": "junction.chibi-lens.scene8-six-fault.v1",
        "workId": WORK_ID,
        "round": round_number,
        "sourceGatePath": "scripts/craci/lens_hb_scene8_admission.py",
        "originalSourceSha256": ORIGINAL_SOURCE_SHA,
        "freshScene8Sha256": FRESH_SCENE8_SHA,
        "fault": CASES[round_number - 1],
        "expectedOutcome": "DENIED",
        "actualOutcome": "DENIED",
        "syntheticMutationNotModelTraining": True,
        "previouslyExposedScene8UsedOnlyForSourceTamperChecks": True,
        "noNewTestScoreOrProductClaim": True,
    }
    if out is not None:
        if out.exists():
            raise FileExistsError("Do not overwrite a source-bound fault receipt")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--round", type=int, required=True, choices=range(1, 7))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    record = run(args.source_root, args.round, args.out)
    print(json.dumps({
        "round": record["round"], "fault": record["fault"],
        "outcome": record["actualOutcome"], "productionOrMLQualified": False
    }, sort_keys=True))


if __name__ == "__main__":
    main()
