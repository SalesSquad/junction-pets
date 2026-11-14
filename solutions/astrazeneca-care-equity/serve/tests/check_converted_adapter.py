"""Manual check, not a unit test: does the converted PEFT adapter behave like the MLX adapter?

Loads the Gemma 3 1B base weights that are already on this machine (the MLX bf16 snapshot uses
Hugging Face key names), applies serve/build/adapter-v1-peft with PEFT, decodes greedily on CPU
and compares each answer with the answer the MLX run stored in data/scribe/eval-v1.json
(adapter_raw). Needs torch, transformers and peft (serve/.venv):

    serve/.venv/bin/python serve/tests/check_converted_adapter.py --limit 20

Identical text is the strict criterion. Small numeric differences between MLX bf16 on the Apple
GPU and PyTorch float32 on the CPU can flip a near-tie, so a mismatch is reported, not hidden.
"""

import argparse
import glob
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scribe"))
sys.path.insert(0, str(ROOT / "serve"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=str(ROOT / "serve/build/adapter-v1-peft"))
    parser.add_argument("--base", default=None, help="local directory of the base model (default: the MLX bf16 snapshot)")
    parser.add_argument("--notes", default=str(ROOT / "serve/fixtures/heldout-v1.jsonl"))
    parser.add_argument("--reference", default=str(ROOT / "data/scribe/eval-v1.json"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default=None)
    parser.add_argument("--device", default="cpu", choices=["cpu", "mps"],
                        help="mps uses the Apple GPU (much faster); cpu is the reference")
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from prompts import messages, parse_output

    base = args.base or sorted(glob.glob(str(
        ROOT / "scribe/artifacts/hf-cache/hub/models--mlx-community--gemma-3-1b-it-bf16/snapshots/*")))[0]
    reference = {p["id"]: p for p in json.loads(pathlib.Path(args.reference).read_text())["predictions"]}
    rows = [json.loads(line) for line in pathlib.Path(args.notes).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if r["id"] in reference][: args.limit]
    torch.manual_seed(0)
    torch.set_grad_enabled(False)
    tok = AutoTokenizer.from_pretrained(base)
    model, info = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32, output_loading_info=True)
    loading = {k: len(v) if hasattr(v, "__len__") else v for k, v in info.items()}
    model = PeftModel.from_pretrained(model, args.adapter)
    model.to(args.device)
    model.eval()
    lora_modules = sum(1 for n, _ in model.named_modules() if n.endswith(".lora_A.default"))
    stop = [tok.eos_token_id, tok.convert_tokens_to_ids("<end_of_turn>")]
    results = []
    started = time.monotonic()
    for row in rows:
        prompt = tok.apply_chat_template(messages(row), tokenize=False, add_generation_prompt=True)
        x = tok(prompt, return_tensors="pt", add_special_tokens=False).to(args.device)
        out = model.generate(**x, do_sample=False, max_new_tokens=384, eos_token_id=stop, pad_token_id=tok.pad_token_id)
        text = tok.decode(out[0, x["input_ids"].shape[1]:], skip_special_tokens=True)
        expected = reference[row["id"]]["adapter_raw"]
        try:
            parsed = parse_output(text)
        except Exception:
            parsed = None
        results.append({
            "id": row["id"],
            "identical_text": text == expected,
            "identical_canonical": parsed == reference[row["id"]]["adapter"],
            "matches_label": parsed == json.loads(row["target_json"]),
            "mlx_matches_label": reference[row["id"]]["adapter"] == json.loads(row["target_json"]),
            "peft_text": text,
            "mlx_text": expected,
        })
        print(f"{len(results)}/{len(rows)} identical_text={results[-1]['identical_text']}", flush=True)
        if not results[-1]["identical_text"]:
            print("  PEFT: " + text, flush=True)
            print("  MLX : " + expected, flush=True)
        if args.out:  # written after every note, so an interrupted run still leaves its results
            pathlib.Path(args.out).write_text(json.dumps({"results": results}, ensure_ascii=False, indent=1))
    summary = {
        "base": base,
        "adapter": args.adapter,
        "versions": {"torch": torch.__version__, "transformers": __import__("transformers").__version__, "peft": __import__("peft").__version__},
        "device": args.device, "dtype": "float32", "decoding": "greedy, max_new_tokens 384",
        "base_loading_info": loading,
        "lora_modules_attached": lora_modules,
        "notes": len(results),
        "identical_text": sum(r["identical_text"] for r in results),
        "identical_canonical": sum(r["identical_canonical"] for r in results),
        "peft_matches_label": sum(r["matches_label"] for r in results),
        "mlx_matches_label": sum(r["mlx_matches_label"] for r in results),
        "seconds": round(time.monotonic() - started, 1),
        "synthetic": True,
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
