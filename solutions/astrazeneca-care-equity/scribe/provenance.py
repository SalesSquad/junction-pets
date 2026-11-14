"""Write data/scribe/provenance-v1.json: which models, versions and terms the version-1 scribe used.

Everything that a run log or a file records is read from there: runs/scribe.jsonl (teacher and verifier
calls of the dataset build), runs/train.jsonl (GPU box set-up, MLX fallback), the cached model snapshot
and its card (scribe/artifacts/hf-cache, git-ignored), data/scribe/models.json, data/scribe/dataset-stats.json,
and the two same-day files that recorded the verifier version (data/claim-check/eval-v1.json,
data/narratives/fi-v1.json). Fields that came from pages a person opened (the Gemma terms) and the
integrator's statements that no log holds are carried over from the previous provenance file and marked so.

Run: scribe/.venv/bin/python scribe/provenance.py
SYNTHETIC project; research artefact, not a medical device.
"""

import collections
import datetime
import hashlib
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data/scribe"
OUT = DATA / "provenance-v1.json"


def read_log(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines() if x.strip()]


def step(log, name):
    return next((d for d in log if d.get("step") == name), None)


def calls(log, name):
    """Per model id: number of calls, first and last timestamp, statuses."""
    out = {}
    for d in log:
        if d.get("step") == name:
            m = (d.get("inputs") or {}).get("model")
            e = out.setdefault(m, {"calls": 0, "first_utc": d["ts"], "last_utc": d["ts"], "status": collections.Counter(), "cost_usd_logged": 0})
            e["calls"] += 1
            e["first_utc"], e["last_utc"] = min(e["first_utc"], d["ts"]), max(e["last_utc"], d["ts"])
            e["status"][d.get("status")] += 1
            e["cost_usd_logged"] += d.get("cost_usd") is not None
    for e in out.values():
        e["status"] = dict(e["status"])
    return out


def card_fields(readme):
    front = readme.split("---")[1] if readme.startswith("---") else ""
    get = lambda k: (re.search(rf"^{k}:\s*(.+)$", front, re.M) or [None, None])[1]
    conv = re.search(r"using mlx-lm version \*\*([\w.]+)\*\*", readme)
    return {"upstream_repository": get("base_model"), "licence_tag": get("license"),
            "converted_with": f"mlx-lm {conv[1]} (as stated on the model card)" if conv else None}


def utc(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def sha256_file(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def main():
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    scribe_log, train_log = read_log(ROOT / "runs/scribe.jsonl"), read_log(ROOT / "runs/train.jsonl")
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    # --- base model of the MLX fallback
    fb = step(train_log, "local_fallback_setup")
    repo, snap = fb["inputs"]["base_model"], fb["inputs"]["snapshot"]
    cache = ROOT / "scribe/artifacts/hf-cache/hub" / ("models--" + repo.replace("/", "--"))
    base = {"repository": repo, "snapshot": snap, "snapshot_source": "runs/train.jsonl, step local_fallback_setup"}
    snapdir = cache / "snapshots" / snap
    if snapdir.exists():
        weights = snapdir / "model.safetensors"
        base.update(card_fields((snapdir / "README.md").read_text()))
        base.update({
            "weights_file": weights.name,
            "weights_bytes": weights.stat().st_size,
            "weights_bytes_in_run_log": fb["metrics"].get("model_safetensors_bytes"),
            "weights_sha256": sha256_file(weights),
            "sha256_computed": f"by scribe/provenance.py on {today} from the cached snapshot (scribe/artifacts/hf-cache, git-ignored)",
            "source_of_card_fields": "README.md of the cached snapshot",
        })
    else:
        prev = old.get("base_model", {})
        base.update({k: prev.get(k) for k in ("upstream_repository", "licence_tag", "converted_with", "weights_file", "weights_bytes", "weights_sha256")})
        base["sha256_computed"] = "not recomputed: the cached snapshot is absent here; value carried over from the previous provenance file"

    # --- the planned GPU run (not executed) and the frameworks that did run
    gs = step(train_log, "gpu_setup")
    check_path = DATA / "cuda-path-check-v1.json"
    check = json.loads(check_path.read_text()) if check_path.exists() else None
    planned = {
        "repository": gs["inputs"]["base_model"], "snapshot": gs["inputs"]["snapshot"],
        "libraries_installed_on_gpu_box": {k: gs["metrics"].get(k) for k in ("torch", "transformers", "peft", "accelerate")},
        "training_executed": False,
        "why": "the GPU box stopped answering after set-up and came back with a changed SSH host key (runs/train.jsonl)",
        "version1_script_compatible_with_those_libraries": None if check is None else check["would_construct"],
        "keywords_rejected": None if check is None else check["keywords_rejected"],
        "compatibility_check": "data/scribe/cuda-path-check-v1.json (scribe/check_cuda_path.py)",
        "superseded_by": "scribe/v2, which pins the library versions and uses integer warm-up steps",
    }
    framework = {"mlx": fb["metrics"].get("mlx"), "mlx_lm": fb["metrics"].get("mlx_lm"), "source": "runs/train.jsonl, step local_fallback_setup"}

    # --- teacher and verifier of the dataset build
    teacher, verifier = calls(scribe_log, "teacher_call"), calls(scribe_log, "verifier_call")
    models_json = json.loads((DATA / "models.json").read_text())
    gen = (HERE / "generate.py").read_text()
    service = re.search(r"https://api\.typesafe\.ai/v1/\w+", gen)
    same_day = []
    for rel, pick in (("data/claim-check/eval-v1.json", lambda d: (d.get("model"), d.get("ranAt"))),
                      ("data/narratives/fi-v1.json", lambda d: ((d.get("verifier") or {}).get("model"), d.get("generatedAt")))):
        p = ROOT / rel
        if p.exists():
            model, at = pick(json.loads(p.read_text()))
            same_day.append({"file": rel, "model": model, "at_utc": at})
    first_call = min((v["first_utc"] for v in verifier.values()), default=None)
    aliases = sorted(m for m in verifier if m)
    old_t, old_terms = old.get("teacher", {}), old.get("terms", {})
    stats = json.loads((DATA / "dataset-stats.json").read_text())
    tokens, cost = stats["usage"]["typesafe_tokens"], stats["typesafe_cost_usd"]

    out = {
        "synthetic": True,
        "written_by": "scribe/provenance.py",
        "base_model": base,
        "framework": framework,
        "planned_model": planned,
        "terms": {**{k: old_terms.get(k) for k in ("gemma_terms_of_use", "gemma_prohibited_use_policy", "prohibited_use_policy_read_utc", "relevant_restriction", "terms_of_use_page")},
                  "source": "carried over from the previous provenance file: pages opened by the integrator on 2026-11-14, not re-opened by this script"},
        "teacher": {
            "model_id": ", ".join(sorted(m for m in teacher if m)),
            "calls": {m: v for m, v in teacher.items()},
            "models_discovered": models_json.get("ids"),
            "version": "not logged: each teacher call records the model id only",
            "endpoint": "OpenAI-compatible endpoint of the Verda inference service; the base URL came from the environment and is not in the run log; GET /models discovery in data/scribe/models.json",
            "endpoint_host": old_t.get("endpoint_host"),
            "endpoint_host_source": "recorded by the integrator; not in runs/scribe.jsonl",
            "price": "not logged: cost_usd is null in every teacher call" if all(v["cost_usd_logged"] == 0 for v in teacher.values()) else "see runs/scribe.jsonl",
            "terms": old_t.get("terms", "not recorded"),
        },
        "verifier": {
            "service": f"TypeSafe System One ({service[0]})" if service else "TypeSafe System One",
            "model_alias_requested": aliases[0] if len(aliases) == 1 else aliases,
            "calls": sum(v["calls"] for v in verifier.values()),
            "calls_by_alias": verifier,
            "resolved_version": f"not captured: the {sum(v['calls'] for v in verifier.values()):,} verifier calls of the dataset build logged only the alias",
            "same_day_versions_recorded_elsewhere": same_day,
            "same_day_reference": "; ".join(f"{x['file']} recorded {x['model']} at {x['at_utc']}" for x in same_day)
            + (f". {'Both are' if len(same_day) > 1 else 'It is'} {'before' if all(utc(x['at_utc']) < utc(first_call) for x in same_day) else 'not all before'} "
               f"the first verifier call of the dataset build ({first_call}); that the build resolved to the same version is likely but was not recorded" if same_day else ""),
            "next_time": "request a pinned version and store the model field of each response",
        },
        "independent_writer": {
            "helper_call": (step(train_log, "haiku_write_notes") or {}).get("command"),
            "model": (old.get("independent_writer") or {}).get("model"),
            "model_source": "recorded by the integrator; the run log names the helper, not a model version",
            "calls_file": "data/scribe/train-artifacts/haiku-calls.json",
            "calls": len(json.loads((DATA / "train-artifacts/haiku-calls.json").read_text())),
        },
        "cost": {
            "typesafe_cost_usd_in_dataset_card": cost,
            "how": f"computed, not billed: {tokens:,} tokens x USD {cost / tokens * 1e6:.3f} per million tokens",
            "price_source": "the project owner's stated price (scribe/README.md); no invoice was read",
        },
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"base_weights_sha256": base.get("weights_sha256"), "teacher": {m: v["calls"] for m, v in teacher.items()},
                      "verifier": {m: v["calls"] for m, v in verifier.items()}, "same_day": same_day, "planned": planned["repository"]}))


if __name__ == "__main__":
    main()
