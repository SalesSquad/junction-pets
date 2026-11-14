"""Leakage and seal regressions; every source/output root is synthetic."""
from __future__ import annotations

import copy
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from prepare_holdout import (assign_splits, checked_cached_source,
                             collision_proof, exclude_prior_byte_components,
                             exclude_prior_global_components, ingest_metadata_record,
                             metadata_keys, prepare,
                             seal_manifest, select_components)


def record(pid, images=None, model=None, family=None, hashes=None):
    images = images or [pid + "-main", pid + "-other"]
    hashes = hashes or [pid + "-bytes-main", pid + "-bytes-other"]
    return {"product_id": pid, "title": pid, "brand": "fixture",
            "category": "OBJECT", "image_ids": images,
            "model_numbers": [model] if model else [], "variant_attributes": [],
            "family_id": family or pid + "-family",
            "global_family_id": family or pid + "-family",
            "views": [{"image_id": image, "sha256": digest,
                       "path": "source/images/" + image + ".jpg"}
                      for image, digest in zip(images, hashes)]}


def raw_record(pid, images=None, model=None, language="en_US", category="OBJECT"):
    images = images or [pid + "-main", pid + "-other"]
    return {"item_id": pid, "main_image_id": images[0], "other_image_id": images[1:],
            "item_name": [{"value": pid, "language_tag": language}],
            "brand": [{"value": "fixture"}],
            "product_type": [{"value": category}] if category else [],
            "model_number": [{"value": model}] if model else []}


class HoldoutLeakageTests(unittest.TestCase):
    def test_raw_ineligible_bridge_still_excludes_connected_fresh_product(self):
        for bridge in (
            raw_record("bridge", images=["prior-main"], model="MODEL-ABC"),
            raw_record("bridge", images=["prior-main", "bridge-other"], model="MODEL-ABC", language="de_DE"),
            raw_record("bridge", images=["prior-main", "bridge-other"], model="MODEL-ABC", category=None),
        ):
            with self.subTest(bridge=bridge):
                old = record("old", images=["prior-main", "prior-other"])
                by_id = {}
                for raw in [raw_record("old", images=old["image_ids"]), bridge,
                            raw_record("fresh", model="MODEL-ABC"), raw_record("safe")]:
                    ingest_metadata_record(by_id, raw)
                self.assertFalse(by_id["bridge"]["acquisition_eligible"])
                self.assertEqual(len(by_id), 4, "ineligible graph vertices must be retained")
                components, exclusions = exclude_prior_global_components(list(by_id.values()), [old])
                self.assertEqual([r["product_id"] for c in components for r in c], ["safe"])
                self.assertEqual(set(exclusions[0]["product_ids"]), {"old", "bridge", "fresh"})

    def test_raw_duplicate_rows_keep_every_language_title_and_model_alias(self):
        by_id = {}
        first = raw_record("bridge", images=["old-image"], model="MODEL-ABC", language="de_DE")
        first["item_name"] = [{"value": "Vier deutsche Worte bleiben", "language_tag": "de_DE"}]
        second = raw_record("bridge", model="MODEL-OTHER")
        second["item_name"] = [{"value": "Four English words remain", "language_tag": "en_US"}]
        ingest_metadata_record(by_id, first)
        ingest_metadata_record(by_id, second)
        bridge = by_id["bridge"]
        self.assertTrue(bridge["acquisition_eligible"])
        self.assertIn("old-image", bridge["image_ids"])
        keys = metadata_keys(bridge)
        self.assertIn("model:fixture:model abc", keys)
        self.assertIn("model:fixture:model other", keys)
        self.assertIn("title:OBJECT:fixture:vier deutsche worte bleiben", keys)
        self.assertIn("title:OBJECT:fixture:four english words remain", keys)
        ingest_metadata_record(by_id, raw_record("fresh", model="MODEL-ABC"))
        old = record("old", images=["old-image", "old-other"])
        components, exclusions = exclude_prior_global_components(list(by_id.values()), [old])
        self.assertEqual(components, [])
        self.assertEqual(set(exclusions[0]["product_ids"]), {"bridge", "fresh"})

    def test_acquisition_filter_keeps_global_family_from_graph_only_bridge(self):
        by_id = {}
        for raw in [raw_record("bridge", images=["bridge-main"], model="MODEL-ABC"),
                    raw_record("fresh", model="MODEL-ABC")]:
            ingest_metadata_record(by_id, raw)
        components, exclusions = exclude_prior_global_components(list(by_id.values()), [record("old")])
        self.assertEqual(exclusions, [])
        images = {image: {} for r in by_id.values() for image in r["image_ids"]}
        selected, _ = select_components(components, images, 10)
        self.assertEqual([r["product_id"] for r in selected], ["fresh"])
        self.assertEqual(selected[0]["global_family_id"], by_id["bridge"]["global_family_id"])

    def test_global_exclusion_is_transitive_before_selection(self):
        old = record("old", images=["prior-main", "prior-other"])
        bridge = record("bridge", images=["prior-main", "bridge-other"], model="MODEL-ABC")
        distant = record("distant", model="MODEL-ABC")
        safe = record("safe")
        components, exclusions = exclude_prior_global_components(
            [copy.deepcopy(old), bridge, distant, safe], [old])
        self.assertEqual([[r["product_id"] for r in c] for c in components], [["safe"]])
        self.assertEqual(set(exclusions[0]["product_ids"]), {"old", "bridge", "distant"})

    def test_prior_alias_excludes_family_even_if_old_id_is_absent(self):
        old = record("old", model="OLD-ALIAS")
        variant = record("variant", model="OLD-ALIAS")
        components, exclusions = exclude_prior_global_components([variant, record("safe")], [old])
        self.assertEqual([r["product_id"] for c in components for r in c], ["safe"])
        self.assertEqual(exclusions[0]["product_ids"], ["variant"])

    def test_byte_exclusion_propagates_through_global_family_and_other_bytes(self):
        old = record("old", hashes=["old-main", "old-other"])
        before = copy.deepcopy(old)
        a = record("a", family="global-AB", hashes=["a-main", "bridge-AC"])
        b = record("b", family="global-AB", hashes=["old-main", "b-other"])
        c = record("c", family="global-C", hashes=["bridge-AC", "c-other"])
        safe = record("safe")
        components, exclusions = exclude_prior_byte_components([a, b, c, safe], [old])
        self.assertEqual([r["product_id"] for c in components for r in c], ["safe"])
        self.assertEqual(set(exclusions[0]["fresh_product_ids"]), {"a", "b", "c"})
        self.assertEqual(old, before, "must not mutate prior evidence in memory")

    def test_byte_merged_families_remain_in_one_split(self):
        a = record("a", hashes=["shared", "a-other"])
        b = record("b", hashes=["shared", "b-other"])
        components, exclusions = exclude_prior_byte_components([a, b, record("safe")], [record("old")])
        self.assertEqual(exclusions, [])
        records = assign_splits(components)
        by_id = {r["product_id"]: r for r in records}
        self.assertEqual(by_id["a"]["split"], by_id["b"]["split"])
        self.assertEqual(by_id["a"]["family_id"], by_id["b"]["family_id"])
        self.assertTrue(all(value == 0 for value in collision_proof(records, [record("old")]).values()))

    def test_collision_audit_rejects_forged_cross_split_byte_overlap(self):
        a = record("a", hashes=["shared", "a-other"])
        b = record("b", hashes=["shared", "b-other"])
        a["split"], b["split"] = "cal", "test"
        with self.assertRaisesRegex(ValueError, "fresh_holdout_collision"):
            collision_proof([a, b], [record("old")])

    def test_selection_keeps_whole_global_components_and_is_deterministic(self):
        a, b, c = record("a", family="AB"), record("b", family="AB"), record("c")
        components = [[a, b], [c]]
        images = {image: {} for r in [a, b, c] for image in r["image_ids"]}
        first, _ = select_components(components, images, 2)
        second, _ = select_components(list(reversed(components)), images, 2)
        self.assertEqual([r["product_id"] for r in first], [r["product_id"] for r in second])
        ids = {r["product_id"] for r in first}
        self.assertLessEqual(len(first), 2)
        self.assertEqual("a" in ids, "b" in ids)

    def test_seal_is_exclusive_and_preserves_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            digest = seal_manifest(root, {"records": [{"product_id": "first"}]})
            original = (root / "dataset.json").read_bytes()
            with self.assertRaisesRegex(FileExistsError, "output_already_sealed"):
                seal_manifest(root, {"records": []})
            self.assertEqual((root / "dataset.json").read_bytes(), original)
            self.assertEqual((root / "dataset.sha256").read_text().strip(), digest)

    def test_prepare_rejects_sealed_output_before_reading_prior_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.mkdir()
            seal_manifest(output, {"records": []})
            args = SimpleNamespace(prior_data=Path(tmp) / "missing-prior", output=output, max_seconds=60)
            with self.assertRaisesRegex(FileExistsError, "output_already_sealed"):
                prepare(args)

    def test_cached_source_bytes_must_match_prior_sealed_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source").mkdir()
            path = root / "source" / "fixture.json"
            path.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "prior_cache_source_hash_mismatch"):
                checked_cached_source(root, "fixture.json", "0" * 64, [], time.monotonic() + 5)
            self.assertEqual(path.read_bytes(), b"changed source")


if __name__ == "__main__":
    unittest.main()
