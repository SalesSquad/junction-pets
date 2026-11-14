#!/usr/bin/env python3
"""Portable negative-evidence guards; real raw qualification uses diagnose_train CLI."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("v10_hybrid_diagnostic", HERE / "diagnose_train.py")
assert spec is not None and spec.loader is not None
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DiagnosticEvidenceContracts(unittest.TestCase):
    def test_original_receipt_and_raw_sha_not_self_derived(self):
        self.assertEqual(d.RECEIPT_SHA, "59e200ce7570157f643174b9f0d8dce8a9c47fdf99aa5080afaab8b7da337e6f")
        self.assertEqual(d.RAW_SHA, "cbaeacd5a7a2a46a30e6b63afeb12614552da032b68e78a6a90fa7d75c49101a")
        self.assertEqual(d.RUN_ID, "craci.43645486985.1.0627c4e23e4a1296")
        self.assertEqual(d.PRODUCT_SHA, "87c91de52cef5c3e745115f737abc4ab8d654a32")

    def test_missing_original_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "ORIGINAL_EVIDENCE_MISSING"):
                d.diagnose(Path(root), Path(root), Path(root) / "unavailable.json")

    def test_forged_receipt_must_not_pass_sha(self):
        with tempfile.TemporaryDirectory() as root:
            forged = Path(root) / "receipt.json"
            forged.write_text('{"status":"succeeded","runId":"fake"}\n', encoding="utf8")
            with self.assertRaisesRegex(ValueError, "ORIGINAL_EVIDENCE_SHA_MISMATCH"):
                d.diagnose(Path(root), Path(root), forged)

    def test_json_hash_is_stable_and_key_order_independent(self):
        self.assertEqual(d.digest({"seed": 1, "mode": "train"}),
                         d.digest({"mode": "train", "seed": 1}))
        self.assertNotEqual(d.digest({"seed": 1}), d.digest({"seed": 2}))


if __name__ == "__main__":
    unittest.main()
