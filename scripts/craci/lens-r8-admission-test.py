#!/usr/bin/env python3
"""Focused public-only cloud admission tests; no owner private data touched."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"fixtures/lens-ycbv-contrast-r8-20261114"
REG=ROOT/"docs/CHIBI_LENS_DATA_SOURCE_REGISTER_20261114.json"
spec=importlib.util.spec_from_file_location("r8_gate",ROOT/"scripts/craci/lens-r8-admission.py")
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class Admission(unittest.TestCase):
    def test_public_exact_bytes(self):
        r=gate.admit(SRC,REG)
        self.assertTrue(r["sourceBound"])
        self.assertFalse(r["familyMediaUsed"])
        self.assertFalse(r["rawPixelsUploaded"])

    def test_no_private_training(self):
        src=json.loads(REG.read_text())
        for row in src["sources"]:
            if row["id"]=="screenshotcontext-personal":
                row["cloud_numeric_features"]=True
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)/"registry.json"
            p.write_text(json.dumps(src))
            with self.assertRaisesRegex(ValueError,"Forbidden private"):
                gate.admit(SRC,p)

    def test_no_unapproved_license(self):
        src=json.loads(REG.read_text())
        for row in src["sources"]:
            if row["id"]==gate.SOURCE_REGISTRY_ID:
                row["license"]="PRIVATE_ONLY"
        with tempfile.TemporaryDirectory() as scratch:
            p=Path(scratch)/"registry.json"
            p.write_text(json.dumps(src))
            with self.assertRaisesRegex(ValueError,"Source license"):
                gate.admit(SRC,p)

    def test_no_modified_feature_bytes(self):
        with tempfile.TemporaryDirectory() as scratch:
            dest=Path(scratch)
            for f in gate.FILES:
                shutil.copy2(SRC/f,dest/f)
            with (dest/"contrast-features.csv").open("a") as f:f.write("tamper")
            with self.assertRaisesRegex(ValueError,"SHA256"):
                gate.admit(dest,REG)

    def test_no_unreviewed_directory_entry(self):
        with tempfile.TemporaryDirectory() as scratch:
            dest=Path(scratch)
            for f in gate.FILES:
                shutil.copy2(SRC/f,dest/f)
            (dest/"private-photo.jpg").write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError,"Missing or extra"):
                gate.admit(dest,REG)


if __name__=="__main__":
    unittest.main()
