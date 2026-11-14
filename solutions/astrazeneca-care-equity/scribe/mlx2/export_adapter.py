"""Export a trained step 3 adapter for the step 8 evaluator and the CPU demo. SYNTHETIC training data only.

Each arm keeps two loadable forms under scribe/v4/artifacts/<arm>/ (git-ignored):
  adapter/  MLX LoRA (adapter_config.json + adapters.safetensors), loaded by
            mlx_lm.load(<MLX base>, adapter_path=...) or by scribe/mlx2/infer.py --adapter
  peft/     the same tensors in PEFT layout (serve/convert_mlx_adapter.py, bit-for-bit transposition), loaded by
            PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(<peft base>), ".../peft")
The manifest data/scribe/v4/mlx/adapters-v1.json lists paths, hashes, base models, the output format and the prompt
function each arm was trained with.

  scribe/.venv/bin/python scribe/mlx2/export_adapter.py --arm B-270m-expr-aug
"""

from __future__ import annotations

import argparse
import json
import sys

import m2common as C

sys.path.insert(0, str(C.ROOT / "serve"))
import convert_mlx_adapter  # noqa: E402

PROMPTS = {"absolute": "scribe/prompts.py messages(row)", "expression": "scribe/v2/data_tools.py expression_messages(row)"}
RESOLUTION = {"absolute": "scribe/v3/resolve.py repair(prediction, note_text, note_date, \"A'\") after canonicalise",
              "expression": "scribe/v2/data_tools.py resolve_expression(output, note_date)"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arm", required=True)
    args = ap.parse_args(argv)
    run = C.ART / args.arm
    result = json.loads((run / "train-result.json").read_text())
    base = C.BASES[result["base"]]
    record = convert_mlx_adapter.convert(run / "adapter", run / "peft", base["peft_base"])
    manifest_path = C.OUT / "adapters-v1.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"synthetic": True, "arms": {}}
    manifest["how_to_load"] = {
        "mlx": "scribe/artifacts/mlx-venv/bin/python scribe/mlx2/infer.py --base <270m|1b> --format <format> "
               "--adapter scribe/v4/artifacts/<arm>/adapter --input <rows.parquet|jsonl> --output <out.jsonl>; then "
               "scribe/mlx2/score.py-style resolution (see 'resolution').",
        "peft": "transformers AutoModelForCausalLM.from_pretrained(<peft_base>) + peft PeftModel.from_pretrained(model, "
                "'scribe/v4/artifacts/<arm>/peft'); chat template of the base tokenizer, add_generation_prompt=True, greedy.",
        "offline_base": "The local MLX base snapshot directory (mlx_base_path) also loads in transformers as "
                        "Gemma3ForCausalLM; peft_parity.py used it for the 1B arm because unsloth/gemma-3-1b-it is not "
                        "cached here (data/scribe/v4/mlx/parity/).",
        "note": "The MLX base snapshots are mlx-community bf16 conversions of the same Gemma 3 weights as the PEFT base "
                "ids; Gemma Terms of Use apply. Every output is a proposal a person confirms.",
    }
    manifest["arms"][args.arm] = {
        "format": result["format"],
        "prompt": PROMPTS[result["format"]],
        "resolution": RESOLUTION[result["format"]],
        "mlx_base": base["repo"], "mlx_base_path": C.rel(base["mlx"]),
        "mlx_adapter": C.rel(run / "adapter"), "mlx_adapter_sha256": result["adapter_sha256"],
        "peft_base": base["peft_base"], "peft_adapter": C.rel(run / "peft"), "peft_adapter_sha256": record["output_sha256"],
        "converter": record["converter"], "training": C.rel(run / "train-result.json"),
    }
    C.save_json(manifest_path, manifest)
    C.log(f"export-adapter-{args.arm}", f"scribe/.venv/bin/python scribe/mlx2/export_adapter.py --arm {args.arm}",
          inputs={"mlx_adapter": C.rel(run / "adapter")}, outputs={"peft": C.rel(run / "peft"), "manifest": C.rel(manifest_path)},
          metrics={"tensors": record["tensors"], "modules": record["modules"], "peft_lora_alpha": record["peft_lora_alpha"]})
    print(json.dumps(manifest["arms"][args.arm], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
