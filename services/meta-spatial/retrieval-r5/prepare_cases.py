#!/usr/bin/env python3
"""Freeze eight label-blind development cases and verify/download only their pixels."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import urllib.request

from protocol import WORK_ID, image_bytes

DATASET_SHA256 = "bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c"
R4_REPORT_SHA256 = "8eda9a3d532b931bc93a765e555bc9008ce9d3c781d1c9efef583e6db515ca80"
PUBLIC_BASE = "https://amazon-berkeley-objects.s3.amazonaws.com/"
PUBLIC_PATH = re.compile(r"source/images/small/[a-z0-9]{2}/[a-z0-9]+\.jpg")
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024


def sha(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular_input_file_required")
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def stable_key(value):
    return hashlib.sha256((WORK_ID + ":" + value).encode()).hexdigest()


def choose_queries(rows, records):
    """Uses only dev ID/confidence/family; no target correctness or rank."""
    eligible = []
    seen = set()
    for row in rows:
        if row["split"] != "dev":
            continue
        pid = row["query_id"]
        if pid in seen or pid not in records or records[pid]["split"] != "dev":
            raise ValueError("invalid_or_duplicate_dev_query")
        seen.add(pid)
        confidence = float(row["confidence"])
        if not math.isfinite(confidence):
            raise ValueError("nonfinite_selection_confidence")
        eligible.append({"query_id": pid, "confidence": confidence,
                         "family_id": records[pid]["family_id"]})
    if len(eligible) != sum(r["split"] == "dev" for r in records.values()):
        raise ValueError("incomplete_development_query_metrics")
    if len(eligible) < 8:
        raise ValueError("insufficient_development_queries")
    eligible.sort(key=lambda row: (row["confidence"], row["query_id"]))
    choices = defaultdict(dict)
    for index, row in enumerate(eligible):
        quartile = min(3, index * 4 // len(eligible)) + 1
        row = {**row, "confidence_quartile": quartile}
        family = row["family_id"]
        previous = choices[quartile].get(family)
        if previous is None or stable_key(row["query_id"]) < stable_key(previous["query_id"]):
            choices[quartile][family] = row
    # Eight-slot bipartite matching avoids a greedy cross-quartile family conflict.
    slots = [q for q in range(1, 5) for _ in range(2)]
    family_slot = {}
    def assign(slot, visited):
        for family in sorted(choices[slots[slot]], key=stable_key):
            if family in visited:
                continue
            visited.add(family)
            if family not in family_slot or assign(family_slot[family], visited):
                family_slot[family] = slot
                return True
        return False
    for slot in range(8):
        if not assign(slot, set()):
            raise ValueError("eight_distinct_families_across_quartiles_unavailable")
    selected = [None] * 8
    for family, slot in family_slot.items():
        selected[slot] = choices[slots[slot]][family]
    return selected


def top_candidates(path, selected, records):
    wanted = {row["query_id"] for row in selected}
    scores = {pid: {} for pid in wanted}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["split"] != "dev" or row["query_id"] not in wanted:
                continue
            query, candidate = row["query_id"], row["candidate_id"]
            score = float(row["rank_score"])
            if candidate not in records or records[candidate]["split"] != "dev" or not math.isfinite(score):
                raise ValueError("invalid_candidate_prediction")
            if candidate in scores[query]:
                raise ValueError("duplicate_candidate_prediction")
            scores[query][candidate] = score
    result = {}
    for query, values in scores.items():
        if len(values) != 100:
            raise ValueError("expected_original_100_candidate_pool")
        result[query] = sorted(values.items(), key=lambda item: (-item[1], item[0]))[:3]
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("public_image_redirect_refused")


def safe_image_path(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("image_path_outside_dataset")
    path = root / rel
    for ancestor in [path, *path.parents]:
        if ancestor == root.parent:
            break
        if ancestor.is_symlink():
            raise ValueError("image_symlink_refused")
    if not path.resolve().is_relative_to(root):
        raise ValueError("image_path_outside_dataset")
    return path


def admit_image(root, view, allow_download, downloads):
    relative, expected = view["path"], view["sha256"]
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("invalid_expected_image_hash")
    path = safe_image_path(root, relative)
    if not path.exists():
        if not allow_download:
            raise ValueError("image_missing:" + relative)
        if not PUBLIC_PATH.fullmatch(relative):
            raise ValueError("public_image_path_not_allowed")
        url = PUBLIC_BASE + relative.removeprefix("source/")
        request = urllib.request.Request(url, headers={"User-Agent": "MetaLensR5/1.0"})
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(request, timeout=30) as response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError("unexpected_public_image_response")
            raw = response.read(MAX_DOWNLOAD_BYTES + 1)
        actual = hashlib.sha256(raw).hexdigest()
        if len(raw) > MAX_DOWNLOAD_BYTES or actual != expected:
            raise ValueError("download_size_or_image_hash_mismatch:" + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = safe_image_path(root, relative)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".r5-", delete=False) as handle:
                temp = Path(handle.name); handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            os.link(temp, path)  # Atomic new-file creation; never replace an existing path.
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        downloads.append({"path": relative, "source_url": url, "bytes": len(raw),
                          "sha256": actual, "status": "downloaded_and_hash_verified"})
    if sha(path) != expected:
        raise ValueError("existing_image_hash_mismatch:" + relative)
    item = {"image_path": str(path), "image_sha256": expected}
    image_bytes(item, root)
    return item


def build(args):
    dataset_hash, report_hash = sha(args.dataset), sha(args.r4_report)
    if dataset_hash != DATASET_SHA256 or report_hash != R4_REPORT_SHA256:
        raise ValueError("pinned_dataset_or_r4_report_mismatch")
    dataset = json.loads(args.dataset.read_text())
    report = json.loads(args.r4_report.read_text())
    report_artifacts = {row["path"]: row["sha256"] for row in report["artifacts"]}
    input_hashes = {"dataset": dataset_hash, "r4_report": report_hash,
                    "predictions": sha(args.predictions), "query_metrics": sha(args.query_metrics)}
    if (input_hashes["predictions"] != report_artifacts["predictions.csv"] or
            input_hashes["query_metrics"] != report_artifacts["query_metrics.csv"]):
        raise ValueError("r4_output_hash_mismatch")
    if dataset.get("kind") != "meta.public-abo-retrieval" or dataset.get("license") != "CC-BY-4.0":
        raise ValueError("public_dataset_contract_mismatch")
    records = {r["product_id"]: r for r in dataset["records"]}
    if len(records) != len(dataset["records"]):
        raise ValueError("duplicate_dataset_product")
    with args.query_metrics.open(newline="", encoding="utf-8") as handle:
        selected = choose_queries(csv.DictReader(handle), records)
    ranked = top_candidates(args.predictions, selected, records)
    root = args.image_root
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("absolute_nonsymlink_image_root_required")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve(strict=True)
    views = {}
    for query in selected:
        pid = query["query_id"]
        required = [records[pid]["views"][1]] + [records[cid]["views"][0] for cid, _ in ranked[pid]]
        for view in required:
            previous = views.get(view["path"])
            if previous is not None and previous["sha256"] != view["sha256"]:
                raise ValueError("inconsistent_image_path_hash")
            views[view["path"]] = view
    if len(views) > 32:
        raise ValueError("selected_image_budget_exceeded")
    downloads = []
    admitted = {path: admit_image(root, view, args.download_missing_public, downloads)
                for path, view in sorted(views.items())}
    cases, truths = [], []
    for index, chosen in enumerate(selected):
        pid = chosen["query_id"]; case_id = "q" + str(index + 1).zfill(4)
        query = {**admitted[records[pid]["views"][1]["path"]], "source_view_index": 1}
        rank_map = {cid: (rank + 1, score) for rank, (cid, score) in enumerate(ranked[pid])}
        presented = sorted(rank_map, key=lambda cid: stable_key(case_id + ":" + cid))
        candidates, truth_candidates = [], []
        true_alias = None
        for position, cid in enumerate(presented):
            alias = "c" + str(position + 1).zfill(2)
            item = admitted[records[cid]["views"][0]["path"]]
            if item["image_sha256"] == query["image_sha256"]:
                raise ValueError("query_image_in_selected_gallery")
            candidates.append({"alias": alias, **item, "source_view_index": 0})
            if cid == pid:
                true_alias = alias
            truth_candidates.append({"alias": alias, "candidate_id": cid,
                                     "candidate_family": records[cid]["family_id"],
                                     "r4_rank": rank_map[cid][0], "rank_score": rank_map[cid][1],
                                     "exact_correct": cid == pid})
        cases.append({"case_id": case_id, "split": "dev", "image_root": str(root),
                      "confidence_quartile": chosen["confidence_quartile"],
                      "query": query, "candidates": candidates})
        truths.append({"case_id": case_id, "split": "dev", "query_id": pid,
                       "query_family": records[pid]["family_id"], "truth_candidate_alias": true_alias,
                       "baseline_correct": ranked[pid][0][0] == pid,
                       "baseline_candidate_id": ranked[pid][0][0],
                       "baseline_rank_score": ranked[pid][0][1], "candidates": truth_candidates})
    for name, path in [("dataset", args.dataset), ("r4_report", args.r4_report),
                       ("predictions", args.predictions), ("query_metrics", args.query_metrics)]:
        if sha(path) != input_hashes[name]:
            raise ValueError("source_input_changed_during_preparation")
    source_hashes = {name: sha(Path(__file__).parent / name) for name in ("prepare_cases.py", "protocol.py")}
    manifest = {"schema_version": 1, "work_id": WORK_ID, "source_commit": args.source_commit,
                "source_hashes": source_hashes, "input_hashes": input_hashes,
                "input_paths": {name: str(getattr(args, name)) for name in
                                ("dataset", "r4_report", "predictions", "query_metrics")},
                "selection": "two queries per confidence quartile; eight distinct dev families; SHA256 stable selection; correctness never consulted",
                "candidate_policy": "original R4 top3; hash-permuted presentation; aliases assigned after permutation; no truth injection",
                "cases": cases, "query_count": 8, "distinct_families": 8,
                "unique_image_files": len(views), "downloads": downloads,
                "downloaded_bytes": sum(row["bytes"] for row in downloads),
                "query_metadata_in_prompts": False, "candidate_metadata_in_prompts": False,
                "extra_view_observed": False, "qualification": False, "action_authorized": False}
    truth = {"schema_version": 1, "work_id": WORK_ID, "cases": truths,
             "use": "local evaluation only; never provider input", "input_hashes": input_hashes,
             "truth_candidate_alias_semantics": "null when exact product is outside frozen top3; never inject a candidate"}
    write_json(args.output / "evaluation_truth.json", truth)
    manifest["evaluation_truth_sha256"] = sha(args.output / "evaluation_truth.json")
    write_json(args.output / "cases.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "image-root", "predictions", "query-metrics", "r4-report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--download-missing-public", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("full source commit required")
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must be new; preserve prior evidence")
    args.output.mkdir(parents=True)
    try:
        manifest = build(args)
    except Exception as error:
        write_json(args.output / "failure.json", {"schema_version": 1, "status": "FAIL",
                   "error_type": type(error).__name__, "error": str(error), "qualification": False})
        raise
    print(json.dumps({"status": "PREPARED", "queries": manifest["query_count"],
                      "unique_images": manifest["unique_image_files"], "downloaded_bytes": manifest["downloaded_bytes"],
                      "cases_sha256": sha(args.output / "cases.json"), "qualification": False}), flush=True)


if __name__ == "__main__":
    main()
