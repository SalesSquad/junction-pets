#!/usr/bin/env python3
"""Targeted rights, private-data and integrity guard for real public HB."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"fixtures/lens-hb-cc0-vision-20261114"
REG=ROOT/"docs/CHIBI_LENS_DATA_SOURCE_REGISTER_20261114.json"
spec=importlib.util.spec_from_file_location("hb_gate",ROOT/"scripts/craci/lens_hb_admission.py")
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class Admission(unittest.TestCase):
    def test_public_real_numeric_only(self):
        r=gate.admit(SRC,REG)
        self.assertTrue(r["cloudTrainingEligible"])
        self.assertTrue(r["knownClassesPresentAllScenes"])
        self.assertFalse(r["localOriginalRGBUploaded"])
        self.assertFalse(r["familyPhotosUsed"])
        self.assertFalse(r["privateOCRUsed"])

    def test_private_source_status_cannot_approve_cloud(self):
        source=json.loads(REG.read_text())
        for entry in source["sources"]:
            if entry["id"]=="screenshotcontext-personal":
                entry["cloud_numeric_features"]=True
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"register.json"
            p.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError,"Private"):
                gate.admit(SRC,p)

    def test_unlicensed_source_is_rejected(self):
        source=json.loads(REG.read_text())
        for entry in source["sources"]:
            if entry["id"]==gate.ID:
                entry["license"]="PRIVATE_ONLY"
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"register.json"
            p.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError,"not explicitly registered"):
                gate.admit(SRC,p)

    def test_tampered_vision_feature_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for f in gate.FILES:
                shutil.copy2(SRC/f,base/f)
            with (base/"public-hb-object-features.csv").open("a") as f:
                f.write("tampered-private-feature")
            with self.assertRaisesRegex(ValueError,"SHA256"):
                gate.admit(base,REG)

    def test_extraneous_photo_disallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for f in gate.FILES:shutil.copy2(SRC/f,base/f)
            (base/"family.jpg").write_bytes(b"private")
            with self.assertRaisesRegex(ValueError,"unreviewed"):
                gate.admit(base,REG)


if __name__=="__main__":
    unittest.main()
