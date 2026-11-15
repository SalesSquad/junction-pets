"""Focused numeric/provenance checks; no CUDA, model loading or HTTP."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import extract_nvidia as extraction


class ExtractionContractTests(unittest.TestCase):
    def test_actual_ocr_upper_lower_polarity(self):
        result = extraction.normalize_ocr([{"text": "AB-123", "confidence": .9,
                                            "left": .1, "right": .7, "upper": .8, "lower": .2}])
        self.assertEqual(result["spans"][0]["box_normalized"], [.1, .2, .7, .8])

    def test_bad_geometry_and_nonfinite_rejected(self):
        baseline = {"text": "AB", "confidence": .9, "left": .1, "right": .7, "upper": .8, "lower": .2}
        for changes in ({"lower": .9}, {"left": .7}, {"upper": float("nan")},
                        {"confidence": 1.1}, {"confidence": True}, {"lower": -.1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                extraction.normalize_ocr([{**baseline, **changes}])

    def test_empty_ocr_remains_valid_observation(self):
        self.assertEqual(extraction.normalize_ocr([]), {"status": "ok", "spans": []})

    def test_manifest_rejects_truth_fields_redirects_and_duplicates(self):
        image_sha = "b" * 64
        row = {"image_id": "img-" + image_sha, "sha256": image_sha,
               "path": "source/images/small/ab/abcd.jpg",
               "url": "https://amazon-berkeley-objects.s3.amazonaws.com/images/small/ab/abcd.jpg"}
        manifest = {"schema": "meta_r6_images_v1", "source_commit": "a" * 40,
                    "dataset_sha256": "c" * 64, "images": [row]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(manifest))
            parsed, sha = extraction.load_manifest(path, "a" * 40)
            self.assertEqual(parsed, manifest)
            self.assertEqual(sha, hashlib.sha256(path.read_bytes()).hexdigest())
            invalids = [{**manifest, "truth": "forbidden"},
                        {**manifest, "images": [{**row, "url": "https://example.com/image.jpg"}]},
                        {**manifest, "images": [row, row]},
                        {**manifest, "source_commit": "d" * 40},
                        {**manifest, "images": [{**row, "product_id": "leak"}]}]
            for invalid in invalids:
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    extraction.load_manifest(path, "a" * 40)

    def test_raw_nonfinite_preserved_without_becoming_valid_span(self):
        raw = extraction.raw_json_value({"confidence": float("nan")})
        self.assertEqual(raw, {"confidence": {"nonfinite_number": "nan"}})
        json.dumps(raw, allow_nan=False)

    def test_canonical_weight_digest_matches_shared_contract(self):
        files = [{"path": "a.pth", "sha256": "f" * 64, "size_bytes": 12}]
        expected = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(extraction.digest(extraction.canonical(files)), expected)


if __name__ == "__main__":
    unittest.main()
