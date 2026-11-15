"""Write data/scribe/manifest-eval-v1.json (hashes of the files of the training and evaluation stage) and
rewrite the descriptive fields of data/scribe/manifest.json (the dataset-build manifest) so that they say
what actually ran. The hash map of manifest.json and its build counters are kept exactly as written at the
end of the dataset build: version 2 checks the version-1 inputs against that hash map.

Facts about what ran are read from runs/train.jsonl and data/scribe/cuda-path-check-v1.json.
Run: scribe/.venv/bin/python scribe/manifest_eval.py        SYNTHETIC data only."""
import datetime, hashlib, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = ["scribe/mlx_fallback.py", "scribe/post_eval.py", "scribe/results_md.py", "scribe/manifest_eval.py", "scribe/metrics.py", "scribe/evaluate.py",
         "scribe/train_lora.py", "scribe/build_dataset.py", "scribe/prompts.py", "scribe/sample.py", "scribe/verify.py", "scribe/tests/test_scribe.py",
         "scribe/provenance.py", "scribe/check_cuda_path.py", "scribe/run_gpu.sh",
         "scribe/README.md", "scribe/RESULTS.md", "data/scribe/eval-v1.json", "data/scribe/post-eval-v1.json", "data/scribe/provenance-v1.json",
         "data/scribe/cuda-path-check-v1.json",
         "data/scribe/haiku-test.jsonl", "data/scribe/dataset-v1/train.parquet", "data/scribe/dataset-v1/val.parquet", "data/scribe/dataset-v1/test.parquet",
         "data/scribe/dataset-v1/CARD.md", "data/scribe/dataset-v1/ERRATA.md",
         "scribe/artifacts/adapter-v1/adapters.safetensors", "scribe/artifacts/mlx-eval/adapter-val.jsonl", "scribe/artifacts/mlx-eval/adapter-test-rest.jsonl",
         "scribe/artifacts/mlx-eval/base.jsonl", "scribe/artifacts/mlx-eval/adapter-0.jsonl", "scribe/artifacts/mlx-eval/adapter-1.jsonl"]
KEEP = ("sha256", "git_operations", "teacher_requests_conservatively_counted", "completed_notes", "interrupted_requests_counted_against_cap")


def run_step(log, name):
    return next((d for d in log if d.get("step") == name), None)


def what_ran(log, check):
    """What happened after the dataset build, from the run log and the CUDA-path check."""
    gs, tr, fb = run_step(log, "gpu_setup"), run_step(log, "local_train"), run_step(log, "local_fallback_setup")
    key = run_step(log, "gpu_host_key_changed")
    return {
        "gpu_training_on_planned_model": {
            "executed": bool(check and check.get("training_attempt_on_gpu_box_logged")),
            "model": gs["inputs"]["base_model"] if gs else None,
            "run_log": (key or {}).get("metrics", {}).get("action"),
            "version1_script_would_construct_training_arguments": None if not check else check["would_construct"],
            "keywords_rejected": None if not check else check["keywords_rejected"],
            "libraries_on_box": None if not gs else {k: gs["metrics"].get(k) for k in ("torch", "transformers", "peft", "accelerate")},
            "sources": ["runs/train.jsonl", "data/scribe/cuda-path-check-v1.json"],
        },
        "mlx_fallback_training": {
            "executed": tr is not None and tr.get("status") == "ok",
            "model": (fb or {}).get("inputs", {}).get("base_model"),
            "iterations": (tr or {}).get("metrics", {}).get("iterations"),
            "where": "a local MacBook Pro with MLX (host name in the run log)",
            "source": "runs/train.jsonl, step local_train",
        },
        "evaluation": {
            "executed": (ROOT / "data/scribe/eval-v1.json").exists(),
            "files": [f for f in ("data/scribe/eval-v1.json", "data/scribe/post-eval-v1.json") if (ROOT / f).exists()],
        },
        "superseded_by": "scribe/v2 (pinned library versions, integer warm-up steps); the version-1 CUDA files are kept unchanged and are not to be used",
    }


if __name__ == "__main__":
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = [json.loads(x) for x in (ROOT / "runs/train.jsonl").read_text().splitlines() if x.strip()]
    cp = ROOT / "data/scribe/cuda-path-check-v1.json"
    check = json.loads(cp.read_text()) if cp.exists() else None
    ran = what_ran(log, check)

    # --- data/scribe/manifest.json: hash map and build counters as written; descriptive fields rewritten
    build_path = ROOT / "data/scribe/manifest.json"
    build = json.loads(build_path.read_text())
    old = build["sha256"]
    at_build = build.get("at_dataset_build") or {k: build[k] for k in ("training_executed", "evaluation_executed") if k in build}
    current = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in old if (ROOT / f).exists()}
    new_build = {k: build[k] for k in KEEP if k in build}
    new_build.update({
        "scope": "dataset build of scribe v1. The hash map and the build counters above were written at the end of the build, before any "
                 "training, and are kept as written: version 2 checks the version-1 inputs against this hash map.",
        "at_dataset_build": at_build,
        "since_then": ran,
        "hash_map_files_changed_since": sorted(f for f in old if current.get(f) not in (None, old[f])),
        "hash_map_files_missing_now": sorted(f for f in old if f not in current),
        "later_stage_manifest": "data/scribe/manifest-eval-v1.json",
        "descriptive_fields_written_by": f"scribe/manifest_eval.py at {now}",
    })
    build_path.write_text(json.dumps(new_build, indent=2) + "\n")

    # --- data/scribe/manifest-eval-v1.json
    files = FILES + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "data/scribe/train-artifacts").iterdir())
    present = [f for f in files if (ROOT / f).exists()]
    sha = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in present}
    tr = ran["mlx_fallback_training"]
    ev = json.loads((ROOT / "data/scribe/eval-v1.json").read_text())["counts"]
    pe = json.loads((ROOT / "data/scribe/post-eval-v1.json").read_text())
    evaluation = (f"base and adapter on {ev['test']} seeded test notes and {ev['extra_test']} Haiku notes; adapter on "
                  f"{len(pe['predictions']['val'])} validation notes and the other {len(pe['predictions']['test_other_300'])} test notes")
    man = {"scope": "training and evaluation stage of scribe v1 (MLX fallback) and the checks added after review",
           "written_utc": now,
           "training_executed": tr["executed"], "training": f"mlx_lm lora, {tr['iterations']} iterations on {tr['model']} (not the planned {ran['gpu_training_on_planned_model']['model']} CUDA run, which was never trained)",
           "evaluation_executed": ran["evaluation"]["executed"],
           "evaluation": evaluation,
           "git_operations": 0, "git_ignored_files": [f for f in present if f.startswith("scribe/artifacts/")],
           "missing_files": [f for f in files if f not in present],
           "unchanged_since_dataset_build_manifest": sorted(f for f in present if f in old and old[f] == sha[f]),
           "changed_since_dataset_build_manifest": sorted(f for f in present if f in old and old[f] != sha[f]), "sha256": sha}
    (ROOT / "data/scribe/manifest-eval-v1.json").write_text(json.dumps(man, indent=1) + "\n")
    print(json.dumps({"files": len(present), "missing": man["missing_files"], "changed": man["changed_since_dataset_build_manifest"],
                      "build_manifest_hash_map_kept": json.loads(build_path.read_text())["sha256"] == old}))
