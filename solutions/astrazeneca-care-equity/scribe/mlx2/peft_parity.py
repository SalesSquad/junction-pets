"""CPU check that the exported PEFT adapter reproduces the MLX outputs. SYNTHETIC validation notes only.

Two stages, because serve/.venv (torch, transformers, peft) has no pyarrow:
  scribe/.venv/bin/python scribe/mlx2/peft_parity.py rows --arm A-270m-abs --n 10
      writes data/scribe/v4/mlx/parity/<arm>-rows.jsonl (id, note_date, note_text of the first n val notes)
  HF_HUB_OFFLINE=1 serve/.venv/bin/python scribe/mlx2/peft_parity.py run --arm A-270m-abs
      greedy decoding on CPU with base + scribe/v4/artifacts/<arm>/peft and the arm's prompt, compared with the MLX
      raw output of the same note (outputs/<arm>/val.jsonl); writes parity/<arm>.json and one run-log line.
Greedy decoding on different back ends (MLX bf16 on the GPU, PyTorch float32 on the CPU) can differ slightly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import m2common as C


def cmd_rows(args):
    rows = C.load_split("val")[: args.n]
    out = C.OUT / "parity" / f"{args.arm}-rows.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], "note_date": r["note_date"], "note_text": r["note_text"]}, ensure_ascii=False) + "\n")
    print(C.rel(out), len(rows))


def cmd_run(args):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    import infer
    import score

    manifest = json.loads((C.OUT / "adapters-v1.json").read_text())["arms"][args.arm]
    fmt = manifest["format"]
    base = args.base or manifest["peft_base"]
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.float32)
    model = PeftModel.from_pretrained(model, str(C.ROOT / manifest["peft_adapter"]))
    model.eval()
    rows = C.load_rows(C.OUT / "parity" / f"{args.arm}-rows.jsonl")
    mlx = {json.loads(x)["id"]: json.loads(x) for x in (C.OUT / "outputs" / args.arm / "val.jsonl").read_text().splitlines() if x.strip()}
    eot = tok.convert_tokens_to_ids("<end_of_turn>")
    stops = [t for t in {tok.eos_token_id, eot} if isinstance(t, int)]
    results = []
    t0 = time.monotonic()
    for r in rows:
        prompt = tok.apply_chat_template(infer.messages_for(fmt, r), tokenize=False, add_generation_prompt=True)
        ids = tok(prompt, add_special_tokens=False, return_tensors="pt")
        ts = time.monotonic()
        with torch.no_grad():
            gen = model.generate(**ids, max_new_tokens=384, do_sample=False, eos_token_id=stops)
        text = tok.decode(gen[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
        cpu_pred = score.parse(fmt, text, r)[0]
        mlx_pred = score.parse(fmt, mlx[r["id"]]["raw"], r)[0]
        key = "code" if fmt == "expression" else "A'"
        results.append({"id": r["id"], "same_as_mlx": text.strip() == mlx[r["id"]]["raw"].strip(),
                        "same_resolved_prediction": cpu_pred[key] == mlx_pred[key] and cpu_pred[key] is not None,
                        "cpu_raw": text, "seconds": round(time.monotonic() - ts, 2)})
    same = sum(x["same_as_mlx"] for x in results)
    same_pred = sum(x["same_resolved_prediction"] for x in results)
    doc = {"synthetic": True, "arm": args.arm, "base": base, "peft_adapter": manifest["peft_adapter"], "dtype": "float32",
           "device": "cpu", "notes": len(results), "identical_raw_output": same, "identical_resolved_prediction": same_pred,
           "mean_seconds_per_note": round(sum(x["seconds"] for x in results) / len(results), 2), "records": results}
    C.save_json(C.OUT / "parity" / f"{args.arm}.json", doc)
    C.log(f"peft-parity-{args.arm}", f"serve/.venv/bin/python scribe/mlx2/peft_parity.py run --arm {args.arm}",
          inputs={"rows": C.rel(C.OUT / "parity" / f"{args.arm}-rows.jsonl"), "peft": manifest["peft_adapter"], "base": base},
          outputs={"file": C.rel(C.OUT / "parity" / f"{args.arm}.json")},
          metrics={"identical_raw_output": f"{same}/{len(results)}", "identical_resolved_prediction": f"{same_pred}/{len(results)}", "mean_seconds_per_note": doc["mean_seconds_per_note"],
                   "wall_seconds": round(time.monotonic() - t0, 1)})
    print(json.dumps({k: v for k, v in doc.items() if k != "records"}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("rows")
    a.add_argument("--arm", required=True)
    a.add_argument("--n", type=int, default=10)
    a = sub.add_parser("run")
    a.add_argument("--arm", required=True)
    a.add_argument("--base", help="Hugging Face id or local path of the PEFT base (default: the manifest's peft_base)")
    args = ap.parse_args(argv)
    {"rows": cmd_rows, "run": cmd_run}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
