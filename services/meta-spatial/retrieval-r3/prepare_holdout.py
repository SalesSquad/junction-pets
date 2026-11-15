#!/usr/bin/env python3
"""Seal a new public ABO calibration/test cohort without reading model scores.

All 16 source metadata shards are grouped before selecting any new product.
Every global component linked to R2 is excluded. After downloading two distinct
photographs, exact image-byte components are merged with the entire prior cohort
and any linked component is excluded again. Grouping is a reproducible heuristic,
not proof against all perceptual duplicates or foundation-model pretraining.
"""
from __future__ import annotations

import argparse
import copy
import csv
import gzip
import importlib.util
import io
import json
import os
import threading
import time
import urllib.error
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from pathlib import Path


PRIOR_DATASET_SHA256 = "bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c"
R2_PREPARER_SHA256 = "d8428e707666e0ab5e2f94d71e639ededdfce9ff845139af1abc0617b958b59e"


def load_r2():
    import hashlib

    path = Path(__file__).resolve().parent.parent / "retrieval-r2" / "prepare_data.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != R2_PREPARER_SHA256:
        raise ValueError("r2_preparer_source_hash_mismatch")
    spec = importlib.util.spec_from_file_location("r3_frozen_abo_preparer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r2 = load_r2()


def metadata_keys(record):
    """Include all raw-row aliases, even from rows unsuitable for acquisition."""
    return set(r2.family_keys(record)) | set(record.get("metadata_family_keys", []))


def ingest_metadata_record(records_by_id, raw):
    """Retain graph edges from every valid item ID before eligibility filtering.

    R2's acquisition parser intentionally rejects one-image, non-English and
    unknown-category records. Those records can still bridge two other products
    and must participate in the family graph. Every duplicate row and language
    contributes keys, even when an eligible row supplies the final query fields.
    """
    pid = raw.get("item_id")
    if not isinstance(pid, str) or not pid.strip():
        return
    image_ids = [raw.get("main_image_id")]
    if isinstance(raw.get("other_image_id"), list):
        image_ids += raw["other_image_id"]
    image_ids = list(dict.fromkeys(i for i in image_ids if isinstance(i, str) and i))
    titles = r2.values(raw, "item_name", english=False) or [""]
    brands = r2.values(raw, "brand", english=False) or [""]
    categories = r2.values(raw, "product_type", english=False) or ["UNKNOWN"]
    models = r2.values(raw, "model_number", english=False)
    variants = [value for key in ("color", "size", "pattern")
                for value in r2.values(raw, key, english=False)]
    base = {"product_id": pid, "title": titles[0], "brand": brands[0],
            "category": categories[0], "image_ids": image_ids,
            "model_numbers": models, "variant_attributes": variants, "titles": {}}
    keys = set()
    for title, brand, category in product(titles, brands, categories):
        keys.update(r2.family_keys({**base, "title": title, "brand": brand, "category": category}))
    for item in raw.get("item_name", []) or []:
        if isinstance(item, dict) and isinstance(item.get("value"), str):
            base["titles"].setdefault(item.get("language_tag") or "und", item["value"])
    # Pass only the normalized image list to the historical acquisition parser.
    # A malformed optional image list cannot remove otherwise valid graph edges.
    acquisition_raw = {**raw, "main_image_id": image_ids[0] if image_ids else None,
                       "other_image_id": image_ids[1:]}
    eligible = r2.parse_record(acquisition_raw)
    current = eligible if eligible is not None else base
    current["acquisition_eligible"] = eligible is not None
    current["metadata_family_keys"] = sorted(keys)
    previous = records_by_id.get(pid)
    if previous is not None:
        # Prefer the first eligible row for the public English query fields;
        # retain every row's family aliases independently of that preference.
        if previous["acquisition_eligible"] or not current["acquisition_eligible"]:
            chosen, other = previous, current
        else:
            chosen, other = current, previous
        chosen["image_ids"] = list(dict.fromkeys(chosen["image_ids"] + other["image_ids"]))
        chosen["model_numbers"] = list(dict.fromkeys(chosen["model_numbers"] + other["model_numbers"]))
        chosen["variant_attributes"] = list(dict.fromkeys(chosen["variant_attributes"] + other["variant_attributes"]))
        for language, title in other["titles"].items():
            chosen["titles"].setdefault(language, title)
        chosen["metadata_family_keys"] = sorted(metadata_keys(chosen) | metadata_keys(other))
        current = chosen
    records_by_id[pid] = current


def group_all_metadata(records):
    """Closure over every metadata alias, not only acquisition-row fields."""
    uf, seen = r2.UnionFind(r["product_id"] for r in records), {}
    for record in sorted(records, key=lambda r: r["product_id"]):
        for key in metadata_keys(record):
            if key in seen:
                uf.join(record["product_id"], seen[key])
            else:
                seen[key] = record["product_id"]
    components = defaultdict(list)
    for record in records:
        components[uf.find(record["product_id"])].append(record)
    for component in components.values():
        family_id = r2.stable("ABO-family-v1\n" + "\n".join(sorted(r["product_id"] for r in component)))
        for record in component:
            record["family_id"] = family_id
    return components


def check_deadline(deadline):
    if time.monotonic() > deadline:
        raise RuntimeError("preparation_deadline_exceeded")


def checked_cached_source(prior_root, key, expected_sha, receipts, deadline):
    """Read only a source whose bytes were sealed by the original R2 dataset."""
    check_deadline(deadline)
    path = prior_root / "source" / key
    if path.is_symlink() or not path.resolve().is_relative_to(prior_root.resolve()):
        raise ValueError("prior_cache_path_escape")
    data = path.read_bytes()
    digest = r2.sha256(data)
    if digest != expected_sha:
        raise ValueError("prior_cache_source_hash_mismatch:" + key)
    receipts.append({"url": r2.BASE + key, "path": "source/" + key,
                     "sha256": digest, "bytes": len(data),
                     "cache_reused": True, "cache_owner": "prior_r2_read_only"})
    return data


def exclude_prior_global_components(records, prior_records):
    """Exclude transitive metadata families, including old aliases absent now."""
    prior_ids = {r["product_id"] for r in prior_records}
    prior_keys = {key for r in prior_records for key in metadata_keys(r)}
    components = group_all_metadata(records)
    retained, excluded = [], []
    for component in components.values():
        hits = sorted(r["product_id"] for r in component
                      if r["product_id"] in prior_ids
                      or any(k in prior_keys for k in metadata_keys(r)))
        family = component[0]["family_id"]
        for record in component:
            record["global_family_id"] = family
        if hits:
            excluded.append({"global_family_id": family,
                             "product_ids": sorted(r["product_id"] for r in component),
                             "direct_prior_link_product_ids": hits})
        else:
            retained.append(component)
    return retained, excluded


def select_components(components, image_map, max_products):
    """Fixed category round robin; no model output or score is an input."""
    eligible = []
    for component in components:
        if len(component) > 50:
            continue
        candidates = [r for r in component if r.get("acquisition_eligible", True)
                      and sum(i in image_map for i in r["image_ids"]) >= 2]
        if candidates:
            eligible.append(candidates)
    queues = defaultdict(deque)
    for component in sorted(eligible, key=lambda c: r2.stable("R3-select-v1:" + c[0]["global_family_id"])):
        queues[component[0]["category"]].append(component)
    selected = []
    while queues and len(selected) < max_products:
        for category in sorted(list(queues), key=lambda c: r2.stable("R3-category-v1:" + c)):
            component = queues[category].popleft()
            if len(selected) + len(component) <= max_products:
                selected.extend(component)
            if not queues[category]:
                del queues[category]
    return selected, len(eligible)


def exclude_prior_byte_components(records, prior_records):
    """Rejoin original global families and exclude transitive prior-byte links."""
    prior_ids = {r["product_id"] for r in prior_records}
    if prior_ids & {r["product_id"] for r in records}:
        raise ValueError("prior_product_reselected")
    # The helper's prior_family key keeps a global component together even when
    # its connecting variants were not successfully downloaded or selected.
    old_copies = copy.deepcopy(prior_records)
    components = r2.group_records(records + old_copies, include_bytes=True)
    retained, excluded = [], []
    for component in components.values():
        old = [r for r in component if r["product_id"] in prior_ids]
        new = [r for r in component if r["product_id"] not in prior_ids]
        if old and new:
            excluded.append({"fresh_product_ids": sorted(r["product_id"] for r in new),
                             "prior_product_ids": sorted(r["product_id"] for r in old),
                             "reason": "transitive_prior_family_or_image_byte_link"})
        elif new:
            retained.append(new)
    return retained, excluded


def assign_splits(components):
    records = []
    for component in components:
        family = component[0]["family_id"]
        split = "cal" if int(r2.stable("R3-fresh-cal-test-v1:" + family)[:16], 16) % 2 == 0 else "test"
        for record in component:
            record["split"] = split
            records.append(record)
    return sorted(records, key=lambda r: r["product_id"])


def collision_proof(records, prior_records):
    """Fail closed on known product/key/byte/global-family contamination."""
    prior_ids = {r["product_id"] for r in prior_records}
    prior_keys = {k for r in prior_records for k in metadata_keys(r)}
    prior_bytes = {v["sha256"] for r in prior_records for v in r["views"]}
    keys_by_split, bytes_by_split, globals_by_split, families_by_split = {}, {}, {}, {}
    for split in ("cal", "test"):
        subset = [r for r in records if r["split"] == split]
        keys_by_split[split] = {k for r in subset for k in metadata_keys(r)}
        bytes_by_split[split] = {v["sha256"] for r in subset for v in r["views"]}
        globals_by_split[split] = {r["global_family_id"] for r in subset}
        families_by_split[split] = {r["family_id"] for r in subset}
    checks = {
        "prior_product_overlap": len(prior_ids & {r["product_id"] for r in records}),
        "prior_family_key_overlap": len(prior_keys & set.union(*keys_by_split.values())),
        "prior_image_byte_overlap": len(prior_bytes & set.union(*bytes_by_split.values())),
        "cal_test_family_key_overlap": len(keys_by_split["cal"] & keys_by_split["test"]),
        "cal_test_image_byte_overlap": len(bytes_by_split["cal"] & bytes_by_split["test"]),
        "cal_test_global_family_overlap": len(globals_by_split["cal"] & globals_by_split["test"]),
        "cal_test_family_overlap": len(families_by_split["cal"] & families_by_split["test"]),
    }
    if any(checks.values()):
        raise ValueError("fresh_holdout_collision:" + json.dumps(checks, sort_keys=True))
    if len({r["product_id"] for r in records}) != len(records):
        raise ValueError("duplicate_product_id")
    if any(len(r["views"]) != 2 or len({v["sha256"] for v in r["views"]}) != 2 for r in records):
        raise ValueError("two_distinct_views_required")
    return checks


def seal_manifest(output, manifest):
    """Never overwrite a sealed cohort, even if another producer races us."""
    if (output / "dataset.json").exists() or (output / "dataset.sha256").exists():
        raise FileExistsError("output_already_sealed")
    payload = r2.canonical(manifest)
    digest = r2.sha256(payload)
    with (output / "dataset.json").open("xb") as stream:
        stream.write(payload)
    with (output / "dataset.sha256").open("x") as stream:
        stream.write(digest + "\n")
    return digest


def prepare(args):
    started = time.monotonic()
    deadline = started + args.max_seconds
    prior_root, output = args.prior_data.resolve(), args.output.resolve()
    if output == prior_root or output.is_relative_to(prior_root) or prior_root.is_relative_to(output):
        raise ValueError("output_must_be_separate_from_prior_data")
    if (output / "dataset.json").exists() or (output / "dataset.sha256").exists():
        raise FileExistsError("output_already_sealed")
    prior_bytes = (prior_root / "dataset.json").read_bytes()
    if r2.sha256(prior_bytes) != PRIOR_DATASET_SHA256:
        raise ValueError("prior_dataset_hash_mismatch")
    prior = json.loads(prior_bytes)
    source_hashes = {s["path"]: s["sha256"] for s in prior["sources"]}
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".prepare-lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        cached_receipts = []
        def source(key):
            return checked_cached_source(prior_root, key, source_hashes["source/" + key], cached_receipts, deadline)

        license_bytes = source("LICENSE-CC-BY-4.0.txt")
        records_by_id = {}
        for shard in range(16):
            data = source(f"listings/metadata/listings_{shard:x}.json.gz")
            for line in gzip.decompress(data).splitlines():
                ingest_metadata_record(records_by_id, json.loads(line))
            print(json.dumps({"stage": "fresh_metadata", "shard": shard,
                              "graph_products": len(records_by_id),
                              "acquisition_eligible_products": sum(r["acquisition_eligible"] for r in records_by_id.values())}), flush=True)
        image_csv = source("images/metadata/images.csv.gz")
        image_map = {r["image_id"]: r for r in csv.DictReader(io.StringIO(gzip.decompress(image_csv).decode("utf-8")))}
        global_records = list(records_by_id.values())
        clean_components, excluded_metadata = exclude_prior_global_components(global_records, prior["records"])
        selected, eligible_components = select_components(clean_components, image_map, args.max_products)
        if not selected:
            raise RuntimeError("no_fresh_products_available")
        check_deadline(deadline)
        selection_receipt = {"schema_version": 1, "prior_dataset_sha256": PRIOR_DATASET_SHA256,
                             "selector": "R3-category-round-robin-v1_whole_global_families",
                             "selected_product_ids": [r["product_id"] for r in selected],
                             "selected_global_families": sorted({r["global_family_id"] for r in selected}),
                             "model_scores_read": False}
        (output / "selection-before-download.json").write_bytes(r2.canonical(selection_receipt))
        downloader = r2.Downloader(output, args.max_download_bytes, deadline)
        from PIL import Image
        downloaded, cache_lock = {}, threading.Lock()

        def acquire(record):
            views, failures = [], []
            for image_id in record["image_ids"]:
                if image_id not in image_map:
                    continue
                try:
                    check_deadline(deadline)
                    key = "images/small/" + image_map[image_id]["path"]
                    with cache_lock:
                        view = downloaded.get(key)
                    if view is None:
                        data, path = downloader.get(key, 8388608)
                        with Image.open(io.BytesIO(data)) as im:
                            im.load()
                            width, height = im.size
                            if min(width, height) < 32 or max(width, height) > 4096:
                                raise ValueError("unsupported_image_dimensions")
                        view = {"image_id": image_id, "path": str(path.relative_to(output)),
                                "sha256": r2.sha256(data), "width": width, "height": height}
                        with cache_lock:
                            downloaded[key] = view
                    if view["sha256"] not in {v["sha256"] for v in views}:
                        views.append(dict(view))
                    if len(views) == 2:
                        record["views"] = views
                        return record, failures
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                    failures.append({"product_id": record["product_id"], "image_id": image_id,
                                     "reason": type(exc).__name__})
            failures.append({"product_id": record["product_id"], "reason": "no_two_distinct_valid_photographs"})
            return None, failures

        successes, drops = [], []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for index, (record, failures) in enumerate(pool.map(acquire, selected)):
                drops.extend(failures)
                if record is not None:
                    successes.append(record)
                if index % 100 == 0:
                    print(json.dumps({"stage": "fresh_images", "processed": index + 1,
                                      "complete_products": len(successes), "bytes": downloader.total_bytes}), flush=True)
        check_deadline(deadline)
        fresh_components, excluded_bytes = exclude_prior_byte_components(successes, prior["records"])
        records = assign_splits(fresh_components)
        proof = collision_proof(records, prior["records"])
        counts = Counter(r["split"] for r in records)
        family_counts = {s: len({r["family_id"] for r in records if r["split"] == s}) for s in ("cal", "test")}
        if min(family_counts.values()) < args.min_families_per_split:
            raise RuntimeError("insufficient_fresh_families:" + json.dumps(family_counts, sort_keys=True))
        manifest = {
            "schema_version": 1, "kind": "meta.public-abo-fresh-r3-holdout",
            "license": "CC-BY-4.0", "attribution": "Amazon.com; ABO dataset by Collins et al., CVPR 2022",
            "license_sha256": r2.sha256(license_bytes), "prior_dataset_sha256": PRIOR_DATASET_SHA256,
            "r2_preparer_sha256": R2_PREPARER_SHA256,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "split_policy": "All16_global_metadata_family_exclusion_then_exact_byte_transitive_exclusion_then_R3_familyhash_cal50_test50",
            "split_limitations": ["Heuristic grouping cannot prove all visually identical variants grouped",
                                  "Foundation model pretraining overlap is unknown",
                                  "Public catalog photographs are not wearable-camera field data",
                                  "Fresh test is same-catalog and is not category-held-out OOD"],
            "model_scores_read": False, "counts": dict(counts), "family_counts": family_counts,
            "source_metadata_products": len(global_records), "eligible_fresh_components": eligible_components,
            "source_acquisition_eligible_products": sum(r["acquisition_eligible"] for r in global_records),
            "selected_before_download": len(selected), "successful_before_byte_exclusion": len(successes),
            "exclusion_proof": proof,
            "excluded_metadata_components": excluded_metadata, "excluded_byte_components": excluded_bytes,
            "download_bytes": downloader.total_bytes,
            "cached_metadata_bytes_read": sum(s["bytes"] for s in cached_receipts),
            "preparation_seconds": time.monotonic() - started,
            "selection_before_download_sha256": r2.sha256((output / "selection-before-download.json").read_bytes()),
            "sources": sorted(cached_receipts + downloader.receipts, key=lambda s: (s["cache_reused"], s["path"])),
            "drops": drops, "records": records,
        }
        check_deadline(deadline)
        digest = seal_manifest(output, manifest)
        print(json.dumps({"stage": "FRESH_SEALED", "dataset_sha256": digest, "counts": dict(counts),
                          "family_counts": family_counts, "download_bytes": downloader.total_bytes}), flush=True)
        return manifest
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-products", type=int, default=2400)
    parser.add_argument("--min-families-per-split", type=int, default=400)
    parser.add_argument("--max-seconds", type=int, default=900)
    parser.add_argument("--max-download-bytes", type=int, default=500000000)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if not (800 <= args.max_products <= 10000 and 300 <= args.min_families_per_split <= 4000
            and args.min_families_per_split * 2 <= args.max_products
            and 60 <= args.max_seconds <= 3600 and 1 <= args.workers <= 16
            and 1 <= args.max_download_bytes <= 2000000000):
        parser.error("bounded limits required")
    prepare(args)


if __name__ == "__main__":
    main()
