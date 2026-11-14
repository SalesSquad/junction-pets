#!/usr/bin/env python3
"""One bounded synthetic CPU comparison against the unchanged R3 runtime.

This measures repeated use of one gallery. It measures no model accuracy,
provider latency, GPU speed, camera workload or product acceptance coverage.
"""
from __future__ import annotations

import os
for _name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np

from candidate_index import PreparedCandidateIndex
from cli import R3_HELPER_SHA256, write_new_json
from contract import advisory_fields

ROOT = Path(__file__).resolve().parent
R3_RUNTIME_SHA256 = "e2bb3096ef062758fc956a81b780f4954bbc7224465cc787bec16a77c406328d"


def load_reference():
    hashes = {}
    for name, expected in (("visual_adapter", R3_HELPER_SHA256), ("runtime", R3_RUNTIME_SHA256)):
        path = ROOT.parent / "retrieval-r3" / (name + ".py")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected:
            raise ValueError("reference_source_hash_mismatch:" + name)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        exec(compile(raw, str(path), "exec"), module.__dict__)
        hashes[name + ".py"] = digest
    return module.VisualRetrievalAdapter, hashes


def unit(rng, count):
    value = rng.standard_normal((count, 768), dtype=np.float32)
    return value / np.linalg.norm(value, axis=1, keepdims=True)


def compare(output):
    # Frozen workload; not parameter-searched for the largest speedup.
    seed, gallery_rows, query_rows, repeats, top_k = 20261114, 4096, 32, 3, 5
    rng = np.random.default_rng(seed)
    gallery, queries = unit(rng, gallery_rows), unit(rng, query_rows)
    a = rng.normal(0, .02, (768, 64)).astype(np.float32)
    b = rng.normal(0, .02, (64, 768)).astype(np.float32)
    ids = [f"gallery-{i:05}" for i in range(gallery_rows)]
    adapter_type, reference_hashes = load_reference()
    reference = adapter_type({"a": a, "b": b}, None, "FAIL", "0" * 64, "0" * 64)
    # Warm both algorithms once; warmup is excluded and explicitly counted.
    reference.propose(queries[0], gallery, ids)
    PreparedCandidateIndex(gallery, ids, a, b).search(queries[0], ["warmup"], top_k=top_k)
    runs = []
    max_score_delta = 0.0
    for repetition in range(repeats):
        def old_run():
            start = time.perf_counter()
            rows = [reference.propose(query, gallery, ids)[0] for query in queries]
            return rows, time.perf_counter() - start

        def new_run():
            start = time.perf_counter()
            index = PreparedCandidateIndex(gallery, ids, a, b)
            prepared = time.perf_counter() - start
            start = time.perf_counter()
            rows = [index.search(query, [f"query-{i}"], top_k=top_k, batch_size=1)
                    for i, query in enumerate(queries)]
            return rows, prepared, time.perf_counter() - start, index.describe()

        # Alternate order to reduce a fixed order bias; no discarded repeats.
        if repetition % 2:
            new, preparation, prepared_search, description = new_run()
            old, original = old_run()
        else:
            old, original = old_run()
            new, preparation, prepared_search, description = new_run()
        for old_row, new_row in zip(old, new):
            expected = old_row["research_ranking"]
            actual = new_row["queries"][0]["candidates"]
            if [x["product_id"] for x in expected] != [x["candidate_id"] for x in actual]:
                raise AssertionError("synthetic_top5_order_mismatch")
            left = np.array([x["similarity"] for x in expected])
            right = np.array([x["score"] for x in actual])
            delta = float(np.max(np.abs(left - right)))
            max_score_delta = max(max_score_delta, delta)
            np.testing.assert_allclose(left, right, rtol=0, atol=2e-6)
        runs.append({"repeat": repetition + 1, "original_seconds": original,
                     "prepared_index_seconds": preparation,
                     "prepared_search_seconds": prepared_search,
                     "prepared_total_seconds": preparation + prepared_search,
                     "total_speedup": original / (preparation + prepared_search)})
    old_median = statistics.median(x["original_seconds"] for x in runs)
    total_median = statistics.median(x["prepared_total_seconds"] for x in runs)
    steady_median = statistics.median(x["prepared_search_seconds"] for x in runs)
    try:
        from threadpoolctl import threadpool_info
        pools = [{k: pool.get(k) for k in ("internal_api", "num_threads", "version", "architecture")}
                 for pool in threadpool_info() if pool.get("user_api") == "blas"]
    except ModuleNotFoundError:
        pools = None
    result = {
        **advisory_fields("meta.retrieval-acceleration.synthetic-benchmark"),
        "status": "PASS", "evidence_mode": "SYNTHETIC", "seed": seed,
        "workload": {"gallery_rows": gallery_rows, "query_rows": query_rows,
                     "dimension": 768, "adapter_rank": 64, "top_k": top_k,
                     "repeats": repeats, "warmup_calls_per_algorithm": 1,
                     "query_delivery": "one query per call, unchanged gallery"},
        "runs": runs,
        "median": {"original_seconds": old_median, "prepared_total_seconds": total_median,
                   "prepared_search_seconds": steady_median,
                   "total_speedup_including_preparation": old_median / total_median,
                   "steady_state_speedup": old_median / steady_median},
        "parity": {"query_comparisons": query_rows * repeats,
                   "top5_ids_and_order_equal": True, "score_atol": 2e-6,
                   "max_absolute_score_difference": max_score_delta},
        "gallery_projections_per_32_queries": {"original": query_rows, "prepared": 1},
        "index_bindings": description["bindings"],
        "reference_sources_sha256": reference_hashes,
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in ("benchmark.py", "candidate_index.py", "cli.py", "contract.py")},
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "platform": platform.platform(), "machine": platform.machine(),
                        "requested_blas_threads": 1,
                        "observed_blas_pools": pools,
                        "thread_environment": {name: os.environ[name] for name in
                                               ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS")}},
        "provider_calls": 0, "gpu_instances": 0, "new_provider_compute_cost_usd": 0,
        "model_quality_evaluated": False, "training_performed": False,
        "limitations": ["Synthetic CPU workload, not an end-to-end glasses or model benchmark",
                        "No claim of faster NVIDIA inference or improved retrieval recall",
                        "Amortization depends on gallery reuse; changed gallery or weights require a new index",
                        "Different BLAS devices and batch shapes may change near-tied float32 ranks"],
    }
    write_new_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = compare(parser.parse_args().output)
    print(json.dumps({"status": result["status"], "median": result["median"], "parity": result["parity"]}))
