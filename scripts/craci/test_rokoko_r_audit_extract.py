"""Focused provenance guards for the source-bound Rokoko R statistical extractor."""
import hashlib
import io
import unittest
import zipfile

from rokoko_r_audit_extract import original, sha


class OriginalPartTests(unittest.TestCase):
    def build(self, tamper_inner=False, tamper_archive=False, extra=False):
        raw = b'{"training_only":true}'
        stored = raw + (b"!" if tamper_inner else b"")
        inner_bytes = io.BytesIO()
        with zipfile.ZipFile(inner_bytes, "w") as inner:
            inner.writestr("training.json.part000", stored)
            if extra:
                inner.writestr("../unexpected", b"no")
        packed = inner_bytes.getvalue()
        expected_packed = hashlib.sha256(packed).hexdigest()
        source = {
            "original_bytes": len(raw),
            "original_sha256": sha(raw),
            "parts": [{
                "archive": "training.json.part000.zip",
                "archive_bytes": len(packed),
                "archive_sha256": "0"*64 if tamper_archive else expected_packed,
                "entry": "training.json.part000",
                "raw_bytes": len(raw),
                "raw_sha256": sha(raw),
            }]
        }
        outer_bytes = io.BytesIO()
        with zipfile.ZipFile(outer_bytes, "w") as outer:
            outer.writestr("artifacts/prospective/training.json.part000.zip", packed)
        outer_bytes.seek(0)
        return outer_bytes, source, raw

    def test_exact_original(self):
        stream, source, raw = self.build()
        with zipfile.ZipFile(stream) as outer:
            self.assertEqual(original(outer, source), raw)

    def test_reject_original_sha_or_length_change(self):
        stream, source, _ = self.build(tamper_inner=True)
        with zipfile.ZipFile(stream) as outer:
            with self.assertRaisesRegex(ValueError, "raw part"):
                original(outer, source)

    def test_reject_archive_sha_change(self):
        stream, source, _ = self.build(tamper_archive=True)
        with zipfile.ZipFile(stream) as outer:
            with self.assertRaisesRegex(ValueError, "archive part SHA"):
                original(outer, source)

    def test_reject_unexpected_nested_files(self):
        stream, source, _ = self.build(extra=True)
        with zipfile.ZipFile(stream) as outer:
            with self.assertRaisesRegex(ValueError, "unexpected inner"):
                original(outer, source)


if __name__ == "__main__":
    unittest.main()
