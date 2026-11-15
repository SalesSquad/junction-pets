#!/usr/bin/env python3
"""Convert an MLX-LM LoRA adapter into the PEFT layout that vLLM serves. Standard library only.

Why this exists: the version-1 adapter was trained with mlx-lm on a Mac
(scribe/artifacts/adapter-v1/adapters.safetensors, base mlx-community/gemma-3-1b-it-bf16).
vLLM reads PEFT adapters only: adapter_config.json plus adapter_model.safetensors with
keys base_model.model.<module>.lora_A.weight and .lora_B.weight.

The mapping, read from mlx_lm/tuner/lora.py (mlx-lm 0.32.2) and from PEFT's LoRA layer:

    MLX   y = W x + scale * (x @ lora_a) @ lora_b       lora_a: (in, r)   lora_b: (r, out)
    PEFT  y = W x + (lora_alpha / r) * B (A x)          A: (r, in)        B: (out, r)

    A = lora_a transposed, B = lora_b transposed, lora_alpha = scale * r

Tensor values are copied bit for bit; only the element order changes (transposition).
MLX module paths (model.layers.N.self_attn.q_proj ...) are the Hugging Face paths of the
text-only Gemma 3 models, so they are kept and prefixed with base_model.model.

Scope: text-only models whose MLX and Hugging Face module paths are the same (Gemma 3
270M and 1B). The multimodal Gemma 3 4B nests the language model under another prefix
and is not handled; adapters trained with PEFT (scribe/train_lora.py, scribe/v2) need no
conversion at all.

Usage:
    python serve/convert_mlx_adapter.py scribe/artifacts/adapter-v1 serve/build/adapter-v1-peft \\
        --base-model unsloth/gemma-3-1b-it
"""

import argparse
import array
import hashlib
import json
import pathlib
import struct
import sys

ITEM_BYTES = {"F64": 8, "F32": 4, "F16": 2, "BF16": 2, "I64": 8, "I32": 4, "I16": 2, "I8": 1, "U8": 1, "BOOL": 1}
ARRAY_CODE = {1: "B", 2: "H", 4: "I", 8: "Q"}  # opaque fixed-size units: values are never interpreted


def read_safetensors(path):
    """Return ({name: (dtype, shape, raw bytes)}, metadata) for a .safetensors file."""
    raw = pathlib.Path(path).read_bytes()
    if len(raw) < 8:
        raise ValueError(f"{path}: not a safetensors file")
    (size,) = struct.unpack("<Q", raw[:8])
    header = json.loads(raw[8 : 8 + size].decode("utf-8"))
    body = memoryview(raw)[8 + size :]
    metadata = header.pop("__metadata__", None)
    tensors = {}
    for name, info in header.items():
        begin, end = info["data_offsets"]
        count = 1
        for dim in info["shape"]:
            count *= dim
        if end - begin != count * ITEM_BYTES[info["dtype"]]:
            raise ValueError(f"{path}: {name} has {end - begin} bytes, shape {info['shape']} needs {count * ITEM_BYTES[info['dtype']]}")
        tensors[name] = (info["dtype"], list(info["shape"]), bytes(body[begin:end]))
    return tensors, metadata


def write_safetensors(path, tensors, metadata=None):
    """Write {name: (dtype, shape, raw bytes)} in sorted key order."""
    header = {"__metadata__": metadata} if metadata else {}
    offset = 0
    for name in sorted(tensors):
        dtype, shape, data = tensors[name]
        header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [offset, offset + len(data)]}
        offset += len(data)
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 8)  # the format asks for an 8-byte aligned header
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(encoded)))
        handle.write(encoded)
        for name in sorted(tensors):
            handle.write(tensors[name][2])


def transpose(data, rows, cols, item_bytes):
    """Row-major bytes of a (rows, cols) matrix -> row-major bytes of its (cols, rows) transpose."""
    source = array.array(ARRAY_CODE[item_bytes])
    source.frombytes(data)
    if len(source) != rows * cols:
        raise ValueError("matrix size does not match its shape")
    target = array.array(ARRAY_CODE[item_bytes], bytes(len(data)))
    for column in range(cols):
        target[column * rows : (column + 1) * rows] = source[column::cols]
    return target.tobytes()


def convert(source_dir, output_dir, base_model, adapter_file="adapters.safetensors"):
    source_dir, output_dir = pathlib.Path(source_dir), pathlib.Path(output_dir)
    weights = source_dir / adapter_file
    config = json.loads((source_dir / "adapter_config.json").read_text(encoding="utf-8"))
    if config.get("fine_tune_type", "lora") != "lora":
        raise ValueError(f"fine_tune_type {config.get('fine_tune_type')!r} is not plain LoRA; only LoRA converts")
    parameters = config["lora_parameters"]
    rank, scale = int(parameters["rank"]), float(parameters["scale"])
    alpha = scale * rank
    tensors, _ = read_safetensors(weights)
    modules = sorted({name.rsplit(".", 1)[0] for name in tensors})
    converted = {}
    for module in modules:
        try:
            a_dtype, a_shape, a_data = tensors[module + ".lora_a"]
            b_dtype, b_shape, b_data = tensors[module + ".lora_b"]
        except KeyError:
            raise ValueError(f"{module}: needs both lora_a and lora_b")
        if len(a_shape) != 2 or len(b_shape) != 2 or a_shape[1] != rank or b_shape[0] != rank:
            raise ValueError(f"{module}: shapes {a_shape} and {b_shape} are not (in, {rank}) and ({rank}, out)")
        prefix = "base_model.model." + module
        converted[prefix + ".lora_A.weight"] = (
            a_dtype, [a_shape[1], a_shape[0]], transpose(a_data, a_shape[0], a_shape[1], ITEM_BYTES[a_dtype]))
        converted[prefix + ".lora_B.weight"] = (
            b_dtype, [b_shape[1], b_shape[0]], transpose(b_data, b_shape[0], b_shape[1], ITEM_BYTES[b_dtype]))
    if len(converted) != len(tensors):
        extra = sorted(n for n in tensors if not n.endswith((".lora_a", ".lora_b")))
        raise ValueError(f"unexpected tensors in the MLX adapter: {extra[:5]}")
    targets = sorted({module.rsplit(".", 1)[1] for module in modules})
    output_dir.mkdir(parents=True, exist_ok=True)
    write_safetensors(output_dir / "adapter_model.safetensors", converted, {"format": "pt"})
    peft_config = {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "base_model_name_or_path": base_model,
        "r": rank,
        "lora_alpha": int(alpha) if alpha == int(alpha) else alpha,
        "lora_dropout": float(parameters.get("dropout", 0.0)),
        "target_modules": targets,
        "bias": "none",
        "fan_in_fan_out": False,
        "inference_mode": True,
        "init_lora_weights": True,
        "modules_to_save": None,
        "use_dora": False,
        "use_rslora": False,
    }
    (output_dir / "adapter_config.json").write_text(json.dumps(peft_config, indent=2) + "\n", encoding="utf-8")
    record = {
        "converter": "serve/convert_mlx_adapter.py",
        "source": str(weights),
        "source_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "source_base_model": config.get("model"),
        "served_base_model": base_model,
        "mlx_rank": rank,
        "mlx_scale": scale,
        "peft_lora_alpha": peft_config["lora_alpha"],
        "modules": len(modules),
        "tensors": len(converted),
        "target_modules": targets,
        "output_sha256": hashlib.sha256((output_dir / "adapter_model.safetensors").read_bytes()).hexdigest(),
        "synthetic_training_data": True,
    }
    # training-config.json is what serve/entrypoint.sh cross-checks against SCRIBE_BASE_MODEL.
    (output_dir / "training-config.json").write_text(
        json.dumps({"base_model": base_model, "converted_from_mlx": record}, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", help="MLX adapter directory (adapter_config.json, adapters.safetensors)")
    parser.add_argument("output", help="directory to write the PEFT adapter into")
    parser.add_argument("--base-model", required=True,
                        help="Hugging Face id the server will load, e.g. unsloth/gemma-3-1b-it")
    parser.add_argument("--adapter-file", default="adapters.safetensors")
    args = parser.parse_args(argv)
    try:
        record = convert(args.source, args.output, args.base_model, args.adapter_file)
    except (OSError, ValueError, KeyError) as exc:
        print(f"conversion failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
