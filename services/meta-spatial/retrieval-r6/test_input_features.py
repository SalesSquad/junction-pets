import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import build_features as features
import prepare_inputs as prepare


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def small_dataset():
    rows = []
    for split, count in (("train", 2), ("dev", 2), ("cal", 1)):
        for number in range(count):
            pid = split + str(number)
            views = [{"sha256": digest(pid + str(view)), "path": "source/images/small/aa/" + digest(pid + str(view)) + ".jpg"}
                     for view in range(2)]
            rows.append({"product_id": pid, "family_id": "family-" + pid, "split": split,
                         "metadata_text": "CANDIDATE_CATALOG_ONLY model 12", "text_hint": "FORBIDDEN_QUERY_HINT", "views": views})
    return {"kind": "meta.public-abo-retrieval", "license": "CC-BY-4.0", "records": rows,
            "counts": {"train": 2, "dev": 2, "cal": 1}}


def candidate_file(path, records, truths):
    truth_by_id = {r["product_id"]: r for r in truths}
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=prepare.R4_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for query in records:
            for candidate in records:
                if candidate["split"] != query["split"]:
                    continue
                q, c = query["product_id"], candidate["product_id"]
                writer.writerow({"split": query["split"], "query_id": q, "candidate_id": c,
                    "query_family": truth_by_id[q]["family_id"], "candidate_family": truth_by_id[c]["family_id"],
                    "label": str(int(q == c)), **{name: "0.20000000000000001" for name in prepare.R4_FEATURES},
                    "baseline_rank": "1" if q == c else "2", "visual_rank": "1", "text_rank": "2"})


def observation(image, text="MODEL-12 34", vector=(1.0, 0.0)):
    return {"image_id": image["image_id"], "sha256": image["sha256"],
            "ocr": {"status": "ok", "spans": [{"text": text, "confidence": 0.9, "box_normalized": [0, 0, 1, 1]}] if text else []},
            "radio": {"dimension": len(vector), "embedding": list(vector)}}


class InputFeatureTests(unittest.TestCase):
    def test_image_projection_is_label_free_and_holdout_free(self):
        dataset = small_dataset()
        records, truths, images, admission = prepare.project_dataset(dataset, expected_counts={"train": 2, "dev": 2})
        self.assertEqual((len(records), len(truths), admission["image_slots"], len(images)), (4, 4, 8, 8))
        encoded = json.dumps(images)
        self.assertNotIn("CANDIDATE_CATALOG_ONLY", encoded)
        self.assertNotIn("FORBIDDEN_QUERY_HINT", encoded)
        self.assertNotIn("family-", encoded)
        self.assertNotIn(dataset["records"][-1]["views"][0]["sha256"], encoded)
        self.assertEqual(records[0]["query_image_id"], "img-" + dataset["records"][0]["views"][1]["sha256"])
        bad = copy.deepcopy(dataset)
        bad["records"][2]["family_id"] = bad["records"][0]["family_id"]
        with self.assertRaisesRegex(ValueError, "family_split_overlap"):
            prepare.project_dataset(bad, expected_counts={"train": 2, "dev": 2})
        bad = copy.deepcopy(dataset)
        bad["records"][-1]["views"][0] = bad["records"][0]["views"][0]
        with self.assertRaisesRegex(ValueError, "image_hash_split_overlap"):
            prepare.project_dataset(bad, expected_counts={"train": 2, "dev": 2})

    def test_actual_source_pins_cannot_accept_synthetic_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); dataset = root / "dataset.json"; dataset.write_text(json.dumps(small_dataset()))
            with self.assertRaisesRegex(ValueError, "pinned_dataset_mismatch"):
                prepare.prepare(dataset, root / "candidates.csv", root / "report.json", root / "out", {})
            report = root / "report.json"; report.write_text("{}")
            with self.assertRaisesRegex(ValueError, "pinned_r4_report_mismatch"):
                prepare.load_r4_report(report)

    def test_candidate_numeric_bytes_and_pool_are_preserved(self):
        records, truths, _, _ = prepare.project_dataset(small_dataset(), expected_counts={"train": 2, "dev": 2})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, output = root / "source.csv", root / "output.csv"
            candidate_file(source, records, truths)
            result = prepare.copy_candidates(source, output, records, truths, candidate_limit=2)
            self.assertEqual(result["rows"], {"train": 4, "dev": 4})
            self.assertEqual(source.read_bytes(), output.read_bytes())
            self.assertIn(b"0.20000000000000001", output.read_bytes())
            with source.open("ab") as handle:
                handle.write(source.read_bytes().splitlines(keepends=True)[1])
            with self.assertRaisesRegex(ValueError, "duplicate_query_candidate"):
                prepare.copy_candidates(source, root / "duplicate.csv", records, truths, candidate_limit=2)

    def test_positive_negative_and_empty_ocr_numerics(self):
        image = {"image_id": "img-" + digest("pixel"), "sha256": digest("pixel")}
        query = features.parse_observation(observation(image), image)
        gallery = features.parse_observation(observation(image, "model 12", (0.6, 0.8)), image)
        value = features.pair_features(query, gallery, features.tokens("series 34"))
        self.assertAlmostEqual(value["f_radio"], 0.6)
        self.assertAlmostEqual(value["f_ocr_visual_match"], 2 / 3)
        self.assertAlmostEqual(value["f_ocr_catalog_match"], 1 / 4)
        self.assertEqual((value["f_ocr_digit_match"], value["f_ocr_digit_conflict"]), (1, 0))
        negative = features.parse_observation(observation(image, "wrong 99", (-1.0, 0.0)), image)
        value = features.pair_features(query, negative, features.tokens("other 56"))
        self.assertEqual([value[name] for name in features.NEW_FEATURES], [-1, 0, 0, 0, 1])
        empty = features.parse_observation(observation(image, ""), image)
        value = features.pair_features(empty, empty, features.tokens(""))
        self.assertEqual([value[name] for name in features.NEW_FEATURES], [1, 0, 0, 0, 0])

    def test_observation_missing_duplicate_hash_dimension_and_norm_reject(self):
        image = {"image_id": "img-" + digest("pixel"), "sha256": digest("pixel")}
        row = observation(image)
        for change, error in (({"sha256": digest("different")}, "image_hash"),
                              ({"radio": {"dimension": 2, "embedding": [2, 0]}}, "unit_normalized"),
                              ({"radio": {"dimension": 2, "embedding": [float("nan"), 0]}}, "nonfinite")):
            with self.assertRaisesRegex(ValueError, error):
                features.parse_observation({**row, **change}, image)
        with self.assertRaisesRegex(ValueError, "dimension_mismatch"):
            features.parse_observation(row, image, dimension=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"; path.write_text("")
            with self.assertRaisesRegex(ValueError, "missing_image"):
                features.load_observations(path, {image["image_id"]: image})
            path.write_text((json.dumps(row) + "\n") * 2)
            with self.assertRaisesRegex(ValueError, "duplicate_observation"):
                features.load_observations(path, {image["image_id"]: image})

    def test_extractor_hash_pins_and_completeness(self):
        models = {}
        for name, pin in features.MODEL_PINS.items():
            files = [{"path": "weights.bin", "sha256": digest(name), "size_bytes": 10}]
            models[name] = {**pin, "files": files, "weights_sha256": features.canonical_hash(files)}
        summary = {"status": "complete", "complete": True, "input_sha256": digest("input"),
                   "observations_sha256": digest("observations"), "source_commit": "a" * 40,
                   "source_sha256": digest("extractor"), "models": models,
                   "counts": {"expected_images": 8, "observed_images": 8, "failed_images": 0}}
        features.validate_extraction(summary, 8, digest("input"), digest("observations"))
        for key, value, error in (("status", "pilot_complete", "complete_extraction"),
                                  ("observations_sha256", digest("tampered"), "artifact_binding"),
                                  ("source_sha256", None, "source_hash")):
            with self.assertRaisesRegex(ValueError, error):
                features.validate_extraction({**summary, key: value}, 8, digest("input"), digest("observations"))
        broken = copy.deepcopy(summary); broken["models"]["radio"]["files"][0]["sha256"] = digest("changed")
        with self.assertRaisesRegex(ValueError, "weights_aggregate"):
            features.validate_extraction(broken, 8, digest("input"), digest("observations"))

    def test_frozen_score_join_keeps_bytes_and_rejects_wrong_identity(self):
        records, truths, images, _ = prepare.project_dataset(small_dataset(), expected_counts={"train": 2, "dev": 2})
        record_map = {r["product_id"]: r for r in records}; truth_map = {r["product_id"]: r for r in truths}
        observed = {i["image_id"]: features.parse_observation(observation(i), i) for i in images}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); candidate, predictions = root / "candidates.csv", root / "predictions.csv"
            candidate_file(candidate, records, truths)
            with candidate.open() as handle:
                rows = list(csv.DictReader(handle))
            with predictions.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("split", "query_id", "candidate_id", "rank_score")); writer.writeheader()
                writer.writerows({**{k: r[k] for k in ("split", "query_id", "candidate_id")}, "rank_score": "0.123456789012345"} for r in rows)
            output = root / "features.csv"
            features.export_features(candidate, predictions, output, record_map, truth_map, observed, candidate_limit=2)
            original_lines, output_lines = candidate.read_bytes().splitlines(), output.read_bytes().splitlines()
            for before, after in zip(original_lines[1:], output_lines[1:]):
                self.assertTrue(after.startswith(before + b","))
                self.assertTrue(after.endswith(b",0.123456789012345"))
            predictions.write_text(predictions.read_text().replace("train,train0,train0", "train,train0,WRONG", 1))
            with self.assertRaisesRegex(ValueError, "prediction_identity_or_order"):
                features.export_features(candidate, predictions, root / "bad.csv", record_map, truth_map, observed, candidate_limit=2)


if __name__ == "__main__":
    unittest.main()
