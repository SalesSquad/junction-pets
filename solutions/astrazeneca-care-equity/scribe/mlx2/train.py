"""LoRA training of one step 3 arm with mlx-lm (one MLX process at a time). SYNTHETIC notes only.

Recipe matched to the CUDA runs of data/scribe/v3/student/RUNS.md where mlx-lm allows: LoRA rank 16, alpha 32
(MLX scale 2.0), dropout 0, all seven projections of every layer, AdamW without weight decay, learning rate 2e-4 with
5% linear warm-up then cosine to 0, 324 optimiser steps at an effective batch of 16 (5,184 training examples), prompt
masked, stop token supervised (chat template), seed 20261114. Differences: mlx-lm has no gradient-norm clipping (CUDA
used 1.0); the effective batch comes from mlx-lm gradient accumulation (--grad-accumulation-steps) over smaller
minibatches; batches are length-grouped by mlx-lm.

A watchdog stops the run (and only this run) when free disk falls below 6 GiB or swap use grows by more than the
--swap-growth-gb limit over its value at the start.

  scribe/.venv/bin/python scribe/mlx2/train.py --arm A-270m-abs
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import m2common as C

ARMS = {
    "A-270m-abs": {"base": "270m", "format": "absolute", "data": "chat/absolute", "batch": 2},
    "B-270m-expr-aug": {"base": "270m", "format": "expression", "data": "chat/expression-aug", "batch": 2},
    "C-1b-expr-aug": {"base": "1b", "format": "expression", "data": "chat/expression-aug", "batch": 1},
}
STEPS, EFFECTIVE_BATCH, LR, WARMUP_FRACTION, SEED = 324, 16, 2e-4, 0.05, 20261114
KEYS = ["self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj", "self_attn.o_proj",
        "mlp.gate_proj", "mlp.up_proj", "mlp.down_proj"]
MAX_SEQ = 1536


def swap_used_gb():
    out = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    m = re.search(r"used = ([\d.]+)M", out)
    return float(m[1]) / 1024 if m else 0.0


def disk_free_gb():
    return shutil.disk_usage(str(C.ROOT)).free / 1024**3


def config_for(arm, batch):
    spec = ARMS[arm]
    accum = EFFECTIVE_BATCH // batch
    warmup = math.ceil(WARMUP_FRACTION * STEPS)
    adapter = C.ART / arm / "adapter"
    return {
        "model": C.BASES[spec["base"]]["mlx"],
        "train": True,
        "data": str(C.OUT / spec["data"]),
        "fine_tune_type": "lora",
        "optimizer": "adamw",
        "optimizer_config": {"adamw": {"weight_decay": 0.0}},
        "seed": SEED,
        "num_layers": -1,
        "batch_size": batch,
        "grad_accumulation_steps": accum,
        "iters": STEPS * accum,  # mlx-lm counts minibatches; the optimiser steps every `accum` of them
        "learning_rate": LR,
        "lr_schedule": {"name": "cosine_decay", "arguments": [LR, STEPS - warmup, 0.0], "warmup": warmup, "warmup_init": 0.0},
        "steps_per_report": 4 * accum,
        "steps_per_eval": STEPS * accum // 4,
        "val_batches": max(1, 48 // batch),
        "save_every": 50 * accum,
        "max_seq_length": MAX_SEQ,
        "mask_prompt": True,
        "grad_checkpoint": False,
        "clear_cache_threshold": 0,
        "adapter_path": str(adapter),
        "lora_parameters": {"rank": 16, "scale": 2.0, "dropout": 0.0, "keys": KEYS},
    }


def longest_example(cfg):
    """Token length of the longest training example (full chat), so nothing is silently truncated."""
    import mlx_lm  # noqa: F401  (environment check)
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(cfg["model"])
    longest = 0
    for name in ("train.jsonl", "valid.jsonl"):
        for line in open(os.path.join(cfg["data"], name), encoding="utf-8"):
            text = tok.apply_chat_template(json.loads(line)["messages"], tokenize=False)
            longest = max(longest, len(tok.encode(text, add_special_tokens=False)))
    return longest


def write_yaml(path, cfg):
    # JSON is valid YAML; mlx-lm reads the file with yaml.safe_load.
    path.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--batch", type=int, help="minibatch size (default per arm); accumulation fills up to 16")
    ap.add_argument("--swap-growth-gb", type=float, default=16.0)
    ap.add_argument("--max-iters", type=int, default=0, help="smoke test only: stop after this many minibatches")
    args = ap.parse_args(argv)
    spec = ARMS[args.arm]
    batch = args.batch or spec["batch"]
    if EFFECTIVE_BATCH % batch:
        raise SystemExit("batch must divide 16")
    cfg = config_for(args.arm, batch)
    run_dir = C.ART / args.arm
    if args.max_iters:
        run_dir = C.ART / f"smoke-{args.arm}"
        cfg["iters"] = args.max_iters
        cfg["adapter_path"] = str(run_dir / "adapter")
        cfg["steps_per_report"] = max(1, args.max_iters // 4)
        cfg["steps_per_eval"] = 10**9
        cfg["val_batches"] = 1
        cfg["save_every"] = 10**9
    run_dir.mkdir(parents=True, exist_ok=True)
    longest = longest_example(cfg)
    if longest > MAX_SEQ:
        raise SystemExit(f"an example has {longest} tokens > {MAX_SEQ}; refusing to truncate")
    cfg_path = run_dir / "mlx-lora-config.yaml"
    write_yaml(cfg_path, cfg)
    log_path = run_dir / "train.log"
    cmd = [str(C.MLX_PY), "-c",
           "import mlx.core as mx, sys; mx.set_cache_limit(1024**3); sys.argv=['mlx_lm.lora','-c',sys.argv[1]]; "
           "from mlx_lm.lora import main; main(); print('PEAK_MEM_GB', mx.get_peak_memory() / 1e9, flush=True)", str(cfg_path)]
    start = {"ts": C.now(), "swap_used_gb": round(swap_used_gb(), 2), "disk_free_gb": round(disk_free_gb(), 2)}
    env = dict(os.environ, HF_HUB_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    t0 = time.monotonic()
    killed = {}
    samples = []
    with log_path.open("w", encoding="utf-8") as logf:
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, cwd=str(C.ROOT), env=env)

        def watch():
            while proc.poll() is None:
                s, d = swap_used_gb(), disk_free_gb()
                samples.append({"t": round(time.monotonic() - t0), "swap_used_gb": round(s, 2), "disk_free_gb": round(d, 2)})
                if d < 6 or s - start["swap_used_gb"] > args.swap_growth_gb:
                    killed.update(reason=f"watchdog: disk_free_gb={d:.2f} swap_growth_gb={s - start['swap_used_gb']:.2f}")
                    proc.terminate()
                    return
                time.sleep(15)

        th = threading.Thread(target=watch, daemon=True)
        th.start()
        rc = proc.wait()
        th.join(timeout=1)
    wall = time.monotonic() - t0
    text = re.sub(r"\x1b\[[0-9;]*m", "", log_path.read_text(encoding="utf-8", errors="replace"))
    peaks = [float(x) for x in re.findall(r"(?:Peak mem|PEAK_MEM_GB) ([\d.]+)", text)]
    weights = run_dir / "adapter/adapters.safetensors"
    result = {
        "arm": args.arm, **spec, "batch": batch, "grad_accumulation_steps": cfg["grad_accumulation_steps"],
        "iters": cfg["iters"], "optimizer_steps": cfg["iters"] // cfg["grad_accumulation_steps"],
        "training_examples": cfg["iters"] * batch, "longest_example_tokens": longest,
        "returncode": rc, "killed": killed or None, "wall_seconds": round(wall, 1), "start": start, "end": C.now(),
        "peak_memory_gb_reported": max(peaks) if peaks else None,
        "max_swap_used_gb": max((x["swap_used_gb"] for x in samples), default=None),
        "min_disk_free_gb": min((x["disk_free_gb"] for x in samples), default=None),
        "adapter": C.rel(run_dir / "adapter"),
        "adapter_sha256": C.sha256_file(weights) if weights.exists() else None,
        "config": C.rel(cfg_path), "log": C.rel(log_path),
    }
    C.save_json(run_dir / "train-result.json", result)
    status = "ok" if rc == 0 and not killed and weights.exists() else "failed"
    C.log(f"train-{args.arm}" + ("-smoke" if args.max_iters else ""), " ".join(["scribe/mlx2/train.py", "--arm", args.arm, "--batch", str(batch)]
                                                                         + (["--max-iters", str(args.max_iters)] if args.max_iters else [])),
          inputs={"data": C.rel(cfg["data"]), "base": C.BASES[spec["base"]]["repo"]},
          outputs={"adapter": result["adapter"], "adapter_sha256": result["adapter_sha256"], "log": result["log"]},
          metrics={k: result[k] for k in ("batch", "grad_accumulation_steps", "iters", "optimizer_steps", "training_examples",
                                          "wall_seconds", "peak_memory_gb_reported", "max_swap_used_gb", "killed", "returncode")},
          status=status)
    print(json.dumps(result, indent=1))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
