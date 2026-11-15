"""Would the version-1 CUDA path (scribe/run_gpu.sh -> scribe/train_lora.py) have trained on the GPU box?

Reads the keyword arguments that scribe/train_lora.py passes to transformers.TrainingArguments (from the
source, with ast) and checks each against the TrainingArguments signature of the transformers installed
in the interpreter that runs this script. Run it with an interpreter whose transformers version equals
the one the GPU box had (runs/train.jsonl, step gpu_setup), for example:

    scribe/artifacts/mlx-venv/bin/python scribe/check_cuda_path.py    # transformers 5.23.0, no torch needed

Writes data/scribe/cuda-path-check-v1.json. Nothing is trained or downloaded. SYNTHETIC project; research
artefact, not a medical device.
"""

import ast
import datetime
import inspect
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def training_argument_keywords(source):
    """Keyword names of every TrainingArguments(...) call in a Python source text, with line numbers."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "TrainingArguments":
            out.append({"line": node.lineno, "keywords": [k.arg for k in node.keywords if k.arg]})
    return out


def run_log(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines() if x.strip()]


def run_log_step(path, step):
    return next((d for d in run_log(path) if d.get("step") == step), None)


def unpinned_installs(shell_text, packages=("torch", "transformers", "peft", "accelerate")):
    """Packages named in a pip install line of a shell script without an == pin."""
    found = {}
    for line in shell_text.splitlines():
        if "pip install" in line and not line.lstrip().startswith("#"):
            for pkg in packages:
                for m in re.finditer(rf"(?<![\w-]){pkg}(==[\w.]+)?(?![\w-])", line):
                    found[pkg] = found.get(pkg) or bool(m.group(1))
    return sorted(p for p, pinned in found.items() if not pinned)


def main():
    import transformers
    from transformers import TrainingArguments

    accepted = set(inspect.signature(TrainingArguments.__init__).parameters)
    calls = training_argument_keywords((HERE / "train_lora.py").read_text())
    rejected = sorted({k for c in calls for k in c["keywords"] if k not in accepted})
    setup = run_log_step(ROOT / "runs/train.jsonl", "gpu_setup")
    box = (setup or {}).get("metrics", {})
    out = {
        "synthetic_project": True,
        "checked_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "question": "would scribe/train_lora.py (version 1) construct its TrainingArguments under the transformers version installed on the GPU box",
        "script": "scribe/train_lora.py",
        "training_arguments_calls": calls,
        "transformers_here": transformers.__version__,
        "interpreter": str(pathlib.Path(sys.executable).relative_to(ROOT)) if pathlib.Path(sys.executable).is_relative_to(ROOT) else "outside the project",
        "transformers_on_gpu_box": box.get("transformers"),
        "gpu_box_versions_from_run_log": {k: box.get(k) for k in ("torch", "transformers", "peft", "accelerate")},
        "same_version_as_gpu_box": transformers.__version__ == box.get("transformers"),
        "keywords_rejected": rejected,
        "would_construct": not rejected,
        "run_gpu_sh_unpinned_packages": unpinned_installs((HERE / "run_gpu.sh").read_text()),
        "gpu_steps_in_run_log": [{"ts": d["ts"], "step": d["step"], "status": d["status"]} for d in run_log(ROOT / "runs/train.jsonl") if "gpu" in d["step"]],
        "gpu_host_key_changed_action": ((run_log_step(ROOT / "runs/train.jsonl", "gpu_host_key_changed") or {}).get("metrics") or {}).get("action"),
        "training_attempt_on_gpu_box_logged": any(d.get("host") == (setup or {}).get("host") and "train" in d["step"] for d in run_log(ROOT / "runs/train.jsonl")),
        "superseded_by": "scribe/v2 (run_gpu.sh pins torch, transformers, peft and accelerate; train.py uses integer warm-up steps)",
    }
    (ROOT / "data/scribe/cuda-path-check-v1.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("transformers_here", "transformers_on_gpu_box", "keywords_rejected", "would_construct", "run_gpu_sh_unpinned_packages")}))


if __name__ == "__main__":
    main()
