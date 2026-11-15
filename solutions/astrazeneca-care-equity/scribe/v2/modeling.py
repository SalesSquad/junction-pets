"""Model, tokenizer and adapter handling (GPU side). torch, transformers and peft are imported lazily
so that importing this module costs nothing on a machine without them.

Gemma 3 settings taken from the research step (transformers 5.23.0, peft 0.21.3):
- load with dtype=bfloat16 and attn_implementation="sdpa"; float16 overflows on Gemma 3;
- AutoModelForCausalLM picks Gemma3ForCausalLM for 270M/1B and Gemma3ForConditionalGeneration for 4B,
  and the multimodal class trains and generates on text alone;
- no modules_to_save on an -it base (it would add the whole embedding matrix and vLLM rejects it);
- EVA needs one pass over training batches before training; PiSSA and OLoRA rewrite the base weights
  and are saved converted back to a plain LoRA.

"smoke" mode builds a tiny randomly initialised Gemma 3 with a local tokenizer, on CPU, to test the
wiring without downloading anything. Its numbers mean nothing and are never written to the repo.
"""

from __future__ import annotations

import pathlib

import _paths  # noqa: F401
from config import BASES

SMOKE_SEED = 1234


def require_gpu():
    import torch

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("a CUDA GPU with bfloat16 support is required (float16 overflows on Gemma 3)")
    return torch.device("cuda")


def load_tokenizer(base, smoke=None):
    from transformers import AutoTokenizer

    if smoke:
        tok = AutoTokenizer.from_pretrained(smoke["tokenizer"])
    else:
        tok = AutoTokenizer.from_pretrained(BASES[base]["repo"], revision=BASES[base]["revision"])
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    return tok


def _tiny(base, tok):
    """Tiny random Gemma 3 with the tokenizer's vocabulary; multimodal class for the 4B stand-in."""
    import torch
    from transformers import (
        Gemma3Config,
        Gemma3ForCausalLM,
        Gemma3ForConditionalGeneration,
        Gemma3TextConfig,
        SiglipVisionConfig,
    )

    torch.manual_seed(SMOKE_SEED)
    text = Gemma3TextConfig(
        vocab_size=len(tok),
        hidden_size=48,
        intermediate_size=96,
        num_hidden_layers=2,
        num_attention_heads=2,
        num_key_value_heads=1,
        head_dim=24,
        max_position_embeddings=2048,
        sliding_window=512,
        pad_token_id=tok.pad_token_id,
        bos_token_id=tok.bos_token_id,
        eos_token_id=tok.eos_token_id,
    )
    if BASES[base]["multimodal"]:
        vision = SiglipVisionConfig(
            hidden_size=32, intermediate_size=64, num_hidden_layers=1, num_attention_heads=2, image_size=28, patch_size=14
        )
        return Gemma3ForConditionalGeneration(
            Gemma3Config(text_config=text.to_dict(), vision_config=vision.to_dict(), mm_tokens_per_image=4)
        )
    return Gemma3ForCausalLM(text)


def load_base(base, smoke=None, tok=None, full_precision=False):
    """The base model on its device. full_precision keeps float32 master weights (full fine-tune)."""
    import torch
    from transformers import AutoModelForCausalLM

    if smoke:
        return _tiny(base, tok or load_tokenizer(base, smoke)).to("cpu")
    device = require_gpu()
    model = AutoModelForCausalLM.from_pretrained(
        BASES[base]["repo"],
        revision=BASES[base]["revision"],
        dtype=torch.float32 if full_precision else torch.bfloat16,
        attn_implementation="sdpa",
    )
    return model.to(device)


def count_parameters(model):
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total": total, "trainable": trainable}


def adapter_modules(model):
    """Names of the modules that received a LoRA adapter."""
    return sorted({n.rsplit(".lora_A", 1)[0] for n, _ in model.named_modules() if ".lora_A" in n})


def add_adapter(model, cfg, eva_batches=None, init_dir=None):
    """Attach the adapter described by cfg. Returns (model, info)."""
    info = {"method": cfg.method, "init": cfg.init}
    if not cfg.is_adapter:
        for p in model.parameters():
            p.requires_grad_(True)
        info.update(count_parameters(model), adapters=0, adapters_in_vision_tower=0)
        return model, info
    from peft import LoraConfig, get_peft_model

    kwargs = cfg.lora_kwargs()
    if cfg.init == "eva":
        from peft import EvaConfig, initialize_lora_eva_weights

        if eva_batches is None:
            raise ValueError("EVA initialisation needs training batches")
        model = get_peft_model(model, LoraConfig(eva_config=EvaConfig(rho=2.0), **kwargs), low_cpu_mem_usage=True)
        # EVA only needs the activations entering the adapted layers, so its forward passes skip the
        # 262k-token output head (the default forward would compute full logits for every batch).
        initialize_lora_eva_weights(
            model,
            eva_batches,
            forward_fn=lambda m, inputs: core_model(m).model(
                input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"]
            ),
        )
        info["eva_rank_pattern_entries"] = len(model.peft_config["default"].rank_pattern or {})
    else:
        model = get_peft_model(model, LoraConfig(**kwargs))
    if cfg.init in ("pissa", "olora"):
        # These initialisations change the base weights. Keeping the initial adapter lets
        # save_pretrained convert the trained adapter back to a plain LoRA on the original base.
        if init_dir is None:
            raise ValueError(f"{cfg.init} needs a directory for the initial adapter")
        model.peft_config["default"].init_lora_weights = True
        model.save_pretrained(str(init_dir))
        info["initial_adapter"] = str(init_dir)
    names = adapter_modules(model)
    info.update(
        count_parameters(model),
        adapters=len(names),
        adapters_in_vision_tower=sum("vision" in n for n in names),
        scaling=cfg.scaling,
    )
    if not names:
        raise RuntimeError("the target expression matched no module")
    if info["adapters_in_vision_tower"]:
        raise RuntimeError("adapters were attached to the vision tower; the target expression is wrong")
    return model, info


def core_model(model):
    """The transformers model inside a PEFT wrapper (or the model itself)."""
    return model.get_base_model() if hasattr(model, "get_base_model") else model


def answer_only_loss(model, input_ids, attention_mask, labels):
    """Cross-entropy on the supervised positions, with the output head applied to those positions only.

    The stock forward pass computes logits over the 262k-token vocabulary for every position and the
    loss then discards the unsupervised ones (about 85% of the tokens of a note). Projecting only the
    answer positions gives the same loss (checked against the stock loss at the start of every run)
    with a fraction of the memory: at batch 16 and about 520 tokens the full logits alone are roughly
    2.2 billion numbers.
    """
    import torch

    core = core_model(model)
    hidden = core.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
    targets = labels[:, 1:]
    mask = targets != -100
    logits = core.lm_head(hidden[:, :-1][mask])
    cap = getattr(core.config, "final_logit_softcapping", None)
    if cap is None:
        cap = getattr(getattr(core.config, "text_config", None), "final_logit_softcapping", None)
    if cap is not None:
        logits = torch.tanh(logits / cap) * cap
    return torch.nn.functional.cross_entropy(logits.float(), targets[mask])


def loss_paths_agree(model, batch):
    """Compare the answer-only loss with the stock loss on one small batch: (agree, stock, answer_only)."""
    import torch

    with torch.no_grad():
        stock = float(model(**batch).loss)
        ours = float(answer_only_loss(model, batch["input_ids"], batch["attention_mask"], batch["labels"]))
    return abs(stock - ours) <= 1e-3 + 2e-2 * abs(stock), stock, ours


def make_optimizer(model, cfg):
    """LoRA+ optimiser, or None to let the Trainer build its default AdamW."""
    if not cfg.loraplus_ratio:
        return None
    import torch
    from peft.optimizers import create_loraplus_optimizer

    return create_loraplus_optimizer(
        model=model,
        optimizer_cls=torch.optim.AdamW,
        lr=cfg.learning_rate,
        loraplus_lr_ratio=cfg.loraplus_ratio,
        loraplus_weight_decay=cfg.weight_decay,
    )


def save_trained(model, tok, cfg, out_dir, init_dir=None):
    """Save what is needed to evaluate or serve the run later. Returns {kind, path, ...}."""
    out_dir = pathlib.Path(out_dir)
    if not cfg.is_adapter:
        path = out_dir / "model"
        model.save_pretrained(str(path))
        tok.save_pretrained(str(path))
        return {"kind": "full", "path": str(path)}
    path = out_dir / "adapter"
    info = {"kind": "adapter", "path": str(path)}
    if cfg.init in ("pissa", "olora"):
        model.save_pretrained(str(path), path_initial_model_for_weight_conversion=str(init_dir))
        info["converted_to_plain_lora"] = True
        info["saved_rank"] = 2 * cfg.rank
    else:
        model.save_pretrained(str(path))
    return info  # the tokenizer is the pinned base tokenizer; it is not copied next to every adapter


def load_system(spec, smoke=None):
    """Load a system for evaluation: (model, tokenizer).

    spec: {"kind": "base" | "adapter" | "full", "base": size key, "path": saved directory or None}
    """
    import torch

    tok = load_tokenizer(spec["base"], smoke)
    kind = spec["kind"]
    if kind == "full":
        from transformers import AutoModelForCausalLM

        model = AutoModelForCausalLM.from_pretrained(spec["path"], dtype=torch.float32)
        model = model.to("cpu" if smoke else require_gpu())
    else:
        model = load_base(spec["base"], smoke, tok)
        if kind == "adapter":
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, spec["path"])
        elif kind != "base":
            raise ValueError(f"unknown system kind {kind!r}")
    model.eval()
    return model, tok


def gpu_summary():
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return {"name": props.name, "memory_bytes": props.total_memory}
    except Exception:
        pass
    return None
