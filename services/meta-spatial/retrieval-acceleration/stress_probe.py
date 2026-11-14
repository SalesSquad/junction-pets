"""One fixed synthetic follow-up experiment; no model/provider calls or qualification.

Six isolated performance children and one numerical/concurrency diagnostic child.
Linux CPU hard limits total at most 85 CPU seconds (6*11 + 6 + 13 parent).
The explicit after-fix mode runs only two 50k cases (hard total57 CPU seconds),
captures fixed-workload memory before a separately reported pinned-source parity
comparison, and writes distinct receipts. Original baseline receipts stay intact.
Fresh-index timing includes preparation over resident synthetic input, not disk I/O
or a controlled cold hardware cache. Amortization rows are arithmetic projections
from measured medians, not separately executed throughput experiments.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import statistics
import subprocess
import sys
import time
import traceback
import types

ROOT = Path(__file__).resolve().parent
SEED = 20261114
DECLARED_SOURCE_COMMIT = "4210b617b087a63a52b0ea1d09ae33b2df9d6d46"
EXPECTED_SOURCE = {
    "candidate_index.py": "c104e41c7e0a1ad9cd97d883ec0ee1ef4f24c4db56496e6e2b7edb3cca54dcaf",
    "contract.py": "45c7a2b1295e5fd4818125481d68fbeffbbe95b7e1ba2c9a0e3adf04e74708d9",
}
BASELINE_CANDIDATE_SHA256 = EXPECTED_SOURCE["candidate_index.py"]
AFTER_FIX = False
REFERENCE_SOURCE = None
PERFORMANCE_CASES = [(50_000, "identity"), (50_000, "residual"),
                     (128, "identity"), (128, "residual"),
                     (4096, "identity"), (4096, "residual")]
THREAD_ENV = {key: "1" for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS",
                                  "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                                  "NUMEXPR_NUM_THREADS")}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def source_hashes():
    return {name: digest((ROOT / name).read_bytes()) for name in EXPECTED_SOURCE}


def rss():
    # Linux ru_maxrss is KiB; current RSS comes from resident pages in /proc.
    resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
    return {"current_rss_bytes": resident_pages * os.sysconf("SC_PAGE_SIZE"),
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}


def timed(operation):
    wall, cpu = time.perf_counter(), time.process_time()
    value = operation()
    return value, {"wall_seconds": time.perf_counter() - wall,
                   "cpu_seconds": time.process_time() - cpu}


def cpu_limit(soft, hard):
    def exhausted(signum, frame):
        raise RuntimeError("fixed_experiment_cpu_budget_exhausted")
    signal.signal(signal.SIGXCPU, exhausted)
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))


def unit_random(np, rows, rng):
    # Bounded generation temporaries keep synthetic construction below the
    # implementation's full-gallery preparation peak.
    result = np.empty((rows, 768), dtype=np.float32)
    for offset in range(0, rows, 1024):
        block = result[offset:offset + 1024]
        block[:] = rng.standard_normal(block.shape, dtype=np.float32)
        block /= np.linalg.norm(block, axis=1, keepdims=True)
    return result


def array_sha(array):
    return digest(memoryview(array).cast("B"))


def query_results_sha(result):
    return digest(json.dumps(result["queries"], sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8"))


def performance(record, rows, mode):
    import numpy as np
    from candidate_index import PreparedCandidateIndex
    record["environment"]["numpy"] = np.__version__
    record["memory"] = {"after_import": rss()}
    gallery = unit_random(np, rows, np.random.default_rng(SEED + rows))
    queries = unit_random(np, 128, np.random.default_rng(SEED + rows + 1))
    ids = tuple(f"synthetic-g-{i}" for i in range(rows))
    query_ids = tuple(f"synthetic-q-{i}" for i in range(len(queries)))
    weights = {}
    if mode == "residual":
        rng = np.random.default_rng(SEED + 2)
        weights = {"a": rng.standard_normal((768, 64), dtype=np.float32) * .001,
                   "b": rng.standard_normal((64, 768), dtype=np.float32) * .001}
    record.update(gallery_rows=rows, query_rows=128, top_k=128, mode=mode,
                  input_sha256={"gallery": array_sha(gallery), "queries": array_sha(queries),
                                **{key: array_sha(value) for key, value in weights.items()}},
                  gallery_input_bytes=gallery.nbytes,
                  seed_recipe={"gallery": SEED + rows, "queries": SEED + rows + 1,
                               "weights_if_present": SEED + 2})
    record["memory"]["inputs_resident"] = rss()
    index, preparation = timed(lambda: PreparedCandidateIndex(gallery, ids, **weights))
    record["preparation"] = preparation
    record["memory"]["after_preparation"] = rss()
    record["index_bindings"] = index.describe()["bindings"]
    record["maximum_score_chunk_bytes"] = index.describe()["limits"]["maximum_score_chunk_bytes"]
    record["warm_single_query"] = []
    # One explicitly recorded warmup, then five measured single-query searches.
    _, record["single_query_warmup"] = timed(lambda: index.search(queries[:1], query_ids[:1], 128, 1))
    for _ in range(5):
        _, measurement = timed(lambda: index.search(queries[:1], query_ids[:1], 128, 1))
        record["warm_single_query"].append(measurement)
    record["batch_searches"] = []
    result_digests = {}
    for batch_size in (1, 16, 128):
        timings = []
        for _ in range(2):
            result, measurement = timed(lambda: index.search(queries, query_ids, 128, batch_size))
            timings.append(measurement)
            assert len(result["queries"]) == 128
            assert all(len(item["candidates"]) == 128 for item in result["queries"])
            assert result["index"]["bindings"] == record["index_bindings"]
        record["batch_searches"].append({"batch_size": batch_size, "query_count_each": 128,
                                         "samples": timings, "memory_after": rss()})
        result_digests[str(batch_size)] = query_results_sha(result)
        del result
    record["memory"]["after_reused_searches"] = rss()
    # Drop the prepared instance before reconstruction. The original caller's
    # feature array remains resident in both fresh and reused measurements.
    del index
    record["fresh_index_single_query"] = []
    def fresh_call():
        fresh = PreparedCandidateIndex(gallery, ids, **weights)
        result = fresh.search(queries[:1], query_ids[:1], 128, 1)
        assert result["index"]["bindings"] == record["index_bindings"]
        return result
    for _ in range(2):
        result, measurement = timed(fresh_call)
        record["fresh_index_single_query"].append(measurement)
        del result
    warm = statistics.median(item["wall_seconds"] for item in record["warm_single_query"])
    fresh = statistics.median(item["wall_seconds"] for item in record["fresh_index_single_query"])
    prep = preparation["wall_seconds"]
    record["amortization_estimates"] = {
        "basis": "median warm/fresh search; one observed preparation; resident input; no catalog changes",
        "warm_single_query_median_seconds": warm,
        "fresh_index_single_query_median_seconds": fresh,
        "strict_reuse_break_even_queries": math.floor(prep / (fresh - warm)) + 1 if fresh > warm else None,
        "preparation_equivalent_warm_queries": prep / warm,
        "rows": [{"queries_per_catalog_version": n, "fresh_each_query_seconds": n * fresh,
                  "prepare_once_then_reuse_seconds": prep + n * warm,
                  "estimated_speed_ratio": n * fresh / (prep + n * warm)} for n in (1, 2, 8, 32)]}
    record["memory"]["final"] = rss()
    record["fixed_workload_final_process_memory"] = record["memory"]["final"]
    record["query_results_sha256_by_batch"] = result_digests
    record["denominators"] = {"initial_preparations": 1, "warmup_searches": 1,
                               "warm_single_query_searches": 5, "batch_searches": 6,
                               "queries_across_batch_searches": 768,
                               "fresh_index_single_query_searches": 2}
    if REFERENCE_SOURCE is not None:
        reference_raw = Path(REFERENCE_SOURCE).read_bytes()
        if digest(reference_raw) != BASELINE_CANDIDATE_SHA256:
            raise RuntimeError("baseline_reference_source_hash_mismatch")
        module = types.ModuleType("meta_acceleration_memory_baseline")
        sys.modules[module.__name__] = module
        exec(compile(reference_raw, str(REFERENCE_SOURCE), "exec"), module.__dict__)
        started_wall, started_cpu = time.perf_counter(), time.process_time()
        baseline = module.PreparedCandidateIndex(gallery, ids, **weights)
        baseline_digests = {}
        for batch_size in (1, 16, 128):
            baseline_result = baseline.search(queries, query_ids, 128, batch_size)
            baseline_digests[str(batch_size)] = query_results_sha(baseline_result)
        binding_equal = baseline.describe()["bindings"] == record["index_bindings"]
        record["baseline_comparison"] = {
            "reference_source_sha256": BASELINE_CANDIDATE_SHA256,
            "fixed_source_sha256": EXPECTED_SOURCE["candidate_index.py"],
            "all_bindings_identical": binding_equal,
            "baseline_query_results_sha256_by_batch": baseline_digests,
            "fixed_query_results_sha256_by_batch": result_digests,
            "all_query_results_identical": baseline_digests == result_digests,
            "query_rows_per_batch": 128, "batch_shapes": 3,
            "candidate_positions_compared": 3 * 128 * 128,
            "wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds": time.process_time() - started_cpu,
            "memory_scope": "This comparison occurs after fixed-only RSS is frozen; final process RSS includes baseline allocations"}
        assert binding_equal and baseline_digests == result_digests


def diagnostics(record):
    from concurrent.futures import ThreadPoolExecutor
    import numpy as np
    from candidate_index import PreparedCandidateIndex
    record["environment"]["numpy"] = np.__version__
    rng = np.random.default_rng(SEED + 71)
    anchor = unit_random(np, 1, rng)
    perturbations = unit_random(np, 512, rng)
    scales = np.linspace(1e-4, 8e-4, 512, dtype=np.float32)[:, None]
    gallery = np.asarray(anchor + perturbations * scales, dtype=np.float32)
    gallery /= np.linalg.norm(gallery, axis=1, keepdims=True)
    queries = np.repeat(anchor, 32, axis=0)
    index = PreparedCandidateIndex(gallery, [f"near-{i}" for i in range(512)])
    query_ids = [f"q-{i}" for i in range(32)]
    double = queries.astype(np.float64) @ gallery.astype(np.float64).T
    reference = np.argsort(-double, axis=1, kind="stable")[:, :128]
    records, reference_batch = [], None
    for batch in (1, 16, 128):
        result = index.search(queries, query_ids, 128, batch)
        repeat = index.search(queries, query_ids, 128, batch)
        ranks = np.asarray([[item["gallery_index"] for item in row["candidates"]]
                            for row in result["queries"]])
        score_errors = []
        membership_differences = []
        for row, selected in enumerate(ranks):
            observed = np.asarray([item["score"] for item in result["queries"][row]["candidates"]])
            score_errors.extend(abs(observed - double[row, selected]).tolist())
            membership_differences.append(128 - len(set(selected) & set(reference[row])))
        compared = reference_batch if reference_batch is not None else ranks
        records.append({"batch_size": batch, "query_rows": 32, "top_k": 128,
                        "repeat_exact_same_output": result == repeat,
                        "top1_differs_from_float64_queries": int(np.count_nonzero(ranks[:, 0] != reference[:, 0])),
                        "rank_positions_differ_from_float64": int(np.count_nonzero(ranks != reference)),
                        "top128_members_missing_vs_float64_per_query": membership_differences,
                        "rank_positions_differ_from_batch1": int(np.count_nonzero(ranks != compared)),
                        "top1_differs_from_batch1_queries": int(np.count_nonzero(ranks[:, 0] != compared[:, 0])),
                        "max_selected_score_absolute_error_vs_float64": max(score_errors),
                        "first_query_first16_indices": ranks[0, :16].tolist()})
        if reference_batch is None:
            reference_batch = ranks
    record["near_ties"] = {"gallery_rows": 512, "query_rows": 32, "top_k": 128,
                           "seed": SEED + 71, "gallery_sha256": array_sha(gallery),
                           "query_sha256": array_sha(queries),
                           "diagnostic_reference": "float64 dot products over the same supplied float32 identity rows; not a new ranking contract",
                           "float64_top1_minus_top2": float(double[0, reference[0, 0]] - double[0, reference[0, 1]]),
                           "float64_first_query_first16_indices": reference[0, :16].tolist(),
                           "cases": records,
                           "denominators": {"batch_shapes": 3, "searches_per_batch_shape": 2,
                                            "rank_positions_per_shape": 4096, "query_rows_per_shape": 32}}
    gallery = unit_random(np, 4096, np.random.default_rng(SEED + 72))
    queries = unit_random(np, 32, np.random.default_rng(SEED + 73))
    ids = [f"concurrent-{i}" for i in range(len(gallery))]
    index = PreparedCandidateIndex(gallery, ids)
    binding = index.describe()["bindings"]["index_sha256"]
    def search_block(offset):
        return index.search(queries[offset:offset + 16], [f"q-{i}" for i in range(offset, offset + 16)], 128, 16)
    sequential, seq_time = timed(lambda: [search_block(i) for i in (0, 16)])
    def concurrent_calls():
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(search_block, (0, 16)))
    concurrent, con_time = timed(concurrent_calls)
    record["concurrent_readers"] = {"reader_count": 2, "queries_per_reader": 16,
                                    "same_results_as_sequential": concurrent == sequential,
                                    "same_index_binding_after": binding == index.describe()["bindings"]["index_sha256"],
                                    "sequential": seq_time, "concurrent": con_time,
                                    "memory_after": rss()}
    # A stale immutable instance deliberately remains unchanged. This is a host
    # cache invalidation example, not a freshness guarantee from the index.
    original_binding = index.describe()["bindings"]["index_sha256"]
    gallery[0] = gallery[1]
    new_index = PreparedCandidateIndex(gallery, ids)
    record["catalog_churn_example"] = {"old_instance_retains_original_binding": original_binding == index.describe()["bindings"]["index_sha256"],
                                        "new_instance_binding_changes": original_binding != new_index.describe()["bindings"]["index_sha256"],
                                        "host_must_switch_instance_for_new_catalog": True,
                                        "changed_input_rows": 1, "gallery_rows": 4096}
    assert concurrent == sequential
    assert record["catalog_churn_example"]["new_instance_binding_changes"]


def child(case):
    if AFTER_FIX:
        cpu_limit(18, 19)
    else:
        cpu_limit(5, 6) if case == "diagnostics" else cpu_limit(10, 11)
    start = time.perf_counter()
    record = {"schema_version": 1, "kind": "meta.retrieval-acceleration.synthetic-stress-case",
              "case": case, "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "declared_source_commit": DECLARED_SOURCE_COMMIT,
              "source_sha256_before": source_hashes(), "probe_sha256": digest(Path(__file__).read_bytes()),
              "synthetic_only": True, "qualification": False, "action_authorized": False,
              "physical_identity_verified": False, "model_quality_evaluated": False,
              "provider_calls": 0, "gpu_calls": 0, "seed": SEED,
              "after_fix": AFTER_FIX,
              "declared_commit_role": "baseline reference; exact file hashes bind uncommitted repair" if AFTER_FIX else "parent-declared baseline",
              "environment": {"python": platform.python_version(), "platform": platform.platform(),
                              "thread_environment": {key: os.environ.get(key) for key in THREAD_ENV}}}
    try:
        if record["source_sha256_before"] != EXPECTED_SOURCE:
            raise RuntimeError("source_bytes_do_not_match_declared_fixed_experiment")
        if any(os.environ.get(key) != value for key, value in THREAD_ENV.items()):
            raise RuntimeError("single_blas_thread_environment_required")
        if case == "diagnostics":
            diagnostics(record)
        else:
            rows, mode = case.split("-")
            performance(record, int(rows), mode)
        record["status"] = "COMPLETE"
    except Exception as exc:
        record["status"] = "FAILED"
        record["error"] = {"type": type(exc).__name__, "message": str(exc),
                           "traceback": traceback.format_exc()}
    record["source_sha256_after"] = source_hashes()
    record["source_stable"] = record["source_sha256_before"] == record["source_sha256_after"]
    if not record["source_stable"]:
        record["status"] = "FAILED_SOURCE_CHANGED"
    record["total_wall_seconds"] = time.perf_counter() - start
    record["total_cpu_seconds"] = time.process_time()
    record["final_process_memory"] = rss()
    print(json.dumps(record, sort_keys=True, allow_nan=False))
    return 0 if record["status"] == "COMPLETE" else 1


def parent(output):
    # Leave inherited hard allowance sufficient for children; this process has
    # a three-second soft deadline, and all eight hard limits sum to 85 seconds.
    cpu_limit(3, 19 if AFTER_FIX else 13)
    output.mkdir(parents=True, exist_ok=True)
    cases = (["50000-identity", "50000-residual"] if AFTER_FIX else
             [f"{rows}-{mode}" for rows, mode in PERFORMANCE_CASES] + ["diagnostics"])
    prefix = "index-stress-after-fix" if AFTER_FIX else "index-stress"
    # Never overwrite earlier success or failure evidence.
    paths = [output / f"{prefix}-{case}.json" for case in cases]
    paths += [output / f"{prefix}.json", output / f"{prefix}.txt"]
    if any(path.exists() for path in paths):
        raise FileExistsError("fixed_experiment_receipt_already_exists")
    environment = dict(os.environ, **THREAD_ENV, PYTHONDONTWRITEBYTECODE="1")
    receipts = []
    for case, path in zip(cases, paths):
        started = time.perf_counter()
        try:
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", case]
            if AFTER_FIX:
                command += ["--after-fix", "--candidate-sha256", EXPECTED_SOURCE["candidate_index.py"],
                            "--reference-source", str(REFERENCE_SOURCE)]
            process = subprocess.run(command,
                                     env=environment, capture_output=True, text=True, timeout=35)
            receipt = json.loads(process.stdout) if process.stdout.strip() else {
                "case": case, "status": "PROCESS_FAILED_WITHOUT_JSON", "returncode": process.returncode}
            if process.stderr:
                receipt["stderr"] = process.stderr
            receipt["process_returncode"] = process.returncode
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            receipt = {"case": case, "status": "PROCESS_FAILED", "error": str(exc),
                       "wall_seconds": time.perf_counter() - started}
        with path.open("x", encoding="utf-8") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        receipts.append({"case": case, "file": path.name, "sha256": digest(path.read_bytes()),
                         "status": receipt["status"]})
        print(json.dumps({"case": case, "status": receipt["status"],
                          "memory": receipt.get("memory"), "preparation": receipt.get("preparation"),
                          "total_cpu_seconds": receipt.get("total_cpu_seconds")}), flush=True)
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    summary = {"schema_version": 1, "kind": "meta.retrieval-acceleration.synthetic-stress-summary",
               "declared_source_commit": DECLARED_SOURCE_COMMIT, "source_sha256": source_hashes(),
               "probe_sha256": digest(Path(__file__).read_bytes()), "seed": SEED,
               "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "synthetic_only": True, "qualification": False, "action_authorized": False,
               "physical_identity_verified": False, "model_quality_evaluated": False,
               "provider_calls": 0, "gpu_calls": 0,
               "after_fix": AFTER_FIX,
               "declared_commit_role": "baseline reference; exact file hashes bind uncommitted repair" if AFTER_FIX else "parent-declared baseline",
               "planned_cases": len(cases), "completed_cases": sum(row["status"] == "COMPLETE" for row in receipts),
               "cpu_hard_limit_total_seconds": 57 if AFTER_FIX else 85,
               "observed_parent_cpu_seconds": time.process_time(),
               "observed_child_cpu_seconds": usage.ru_utime + usage.ru_stime,
               "measurement_limits": ["Fresh index over resident inputs; no disk I/O or cold hardware-cache control",
                                      "Peak RSS is per isolated process and includes caller inputs and preparation temporaries",
                                      "Amortization values are estimates for an unchanged catalog and adapter",
                                      "Near-tie float64 reference is diagnostic only, not product ranking policy",
                                      "Two-thread example cannot establish safety of arbitrary host-level cache replacement"],
               "receipts": receipts}
    with (output / f"{prefix}.json").open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    with (output / f"{prefix}.txt").open("x", encoding="utf-8") as handle:
        handle.write(f"Synthetic fixed stress experiment: {summary['completed_cases']}/{len(cases)} cases complete.\n")
        handle.write(f"Child CPU seconds: {summary['observed_child_cpu_seconds']:.6f}; parent: {summary['observed_parent_cpu_seconds']:.6f}.\n")
        for row in receipts:
            handle.write(f"{row['case']}: {row['status']} {row['file']} sha256={row['sha256']}\n")
        handle.write("No model quality evaluation, provider/GPU calls or qualification. See JSON per-case raw measurements.\n")
    print(json.dumps(summary, sort_keys=True, allow_nan=False), flush=True)
    return 0 if summary["completed_cases"] == len(cases) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=[f"{rows}-{mode}" for rows, mode in PERFORMANCE_CASES] + ["diagnostics"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "followup-20261114")
    parser.add_argument("--after-fix", action="store_true")
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--reference-source", type=Path)
    args = parser.parse_args()
    if args.after_fix:
        if not args.candidate_sha256 or len(args.candidate_sha256) != 64 or not args.reference_source:
            parser.error("After-fix mode requires exact --candidate-sha256 and pinned --reference-source")
        if args.child and args.child not in {"50000-identity", "50000-residual"}:
            parser.error("After-fix mode is limited to the two fixed 50k cases")
        EXPECTED_SOURCE = {**EXPECTED_SOURCE, "candidate_index.py": args.candidate_sha256}
        AFTER_FIX = True
        REFERENCE_SOURCE = args.reference_source.resolve()
    elif args.candidate_sha256 or args.reference_source:
        parser.error("Explicit repaired source selection requires --after-fix")
    raise SystemExit(child(args.child) if args.child else parent(args.output_dir))
