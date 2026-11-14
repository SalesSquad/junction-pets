"""GPU only. No model downloads occur on import."""

import argparse
import math
import pathlib
import time

from common import DATA, log, save
from prompts import messages

DEFAULT = "unsloth/gemma-3-4b-it"
FALLBACK = "unsloth/gemma-3-1b-it"


def load_model(name):
    import torch
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        Gemma3ForConditionalGeneration,
    )

    config = AutoConfig.from_pretrained(name)
    cls = (
        Gemma3ForConditionalGeneration
        if config.model_type == "gemma3"
        else AutoModelForCausalLM
    )
    return cls.from_pretrained(
        name, torch_dtype=torch.bfloat16, attn_implementation="sdpa"
    )


def encode(row, tok, max_length=768):
    prompt = tok.apply_chat_template(
        messages(row), tokenize=False, add_generation_prompt=True
    )
    full = tok.apply_chat_template(
        messages(row) + [{"role": "assistant", "content": row["target_json"]}],
        tokenize=False,
        add_generation_prompt=False,
    )
    if (
        not full.startswith(prompt)
        or full[len(prompt) : len(prompt) + len(row["target_json"])]
        != row["target_json"]
    ):
        raise ValueError("chat prefix mismatch; cannot safely mask assistant")
    encoded = tok(full, add_special_tokens=False, return_offsets_mapping=True)
    b = encoded["input_ids"]
    start = len(prompt)
    end = start + len(row["target_json"])
    # Repair 2026-11-14: also supervise the end-of-turn marker that follows the JSON.
    # The original mask left the stop token unsupervised, so the adapter never learned to stop.
    if full[end:].startswith("<end_of_turn>"):
        end += len("<end_of_turn>")
    if len(b) > max_length:
        raise ValueError(
            f"example {row['id']} exceeds {max_length}; refusing target truncation"
        )
    labels = [
        token if hi > start and lo < end else -100
        for token, (lo, hi) in zip(b, encoded["offset_mapping"])
    ]
    if not any(x != -100 for x in labels):
        raise ValueError("empty assistant label span")
    return {"input_ids": b, "attention_mask": [1] * len(b), "labels": labels}


def main():
    import pyarrow.parquet as pq
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoTokenizer,
        Trainer,
        TrainerCallback,
        TrainingArguments,
        set_seed,
    )

    p = argparse.ArgumentParser()
    p.add_argument("--base-model", default=DEFAULT)
    p.add_argument("--fallback-model", default=FALLBACK)
    p.add_argument("--allow-fallback", action="store_true")
    p.add_argument("--dataset", default=str(DATA / "dataset-v1"))
    p.add_argument("--output", default=str(DATA / "adapter-v1"))
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument(
        "--max-minutes",
        type=float,
        default=0,
        help="wall-clock cap on the training loop; 0 disables",
    )
    args = p.parse_args()
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("bf16 CUDA GPU required")
    set_seed(20261114)
    name = args.base_model
    try:
        model = load_model(name)
    except (OSError, torch.cuda.OutOfMemoryError):
        if not args.allow_fallback:
            raise
        import gc

        gc.collect()
        torch.cuda.empty_cache()
        name = args.fallback_model
        model = load_model(name)
    tok = AutoTokenizer.from_pretrained(name)
    tok.padding_side = "right"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    # Select language modules only, excluding vision tower/projector explicitly.
    suffixes = {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    }
    targets = [
        n
        for n, m in model.named_modules()
        if n.split(".")[-1] in suffixes
        and "vision" not in n
        and "multi_modal_projector" not in n
    ]
    if not targets:
        raise RuntimeError("no language projection targets")
    model = get_peft_model(
        model,
        LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            target_modules=targets,
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    model.config.use_cache = False
    train = [
        encode(r, tok)
        for r in pq.read_table(pathlib.Path(args.dataset) / "train.parquet").to_pylist()
    ]
    val = [
        encode(r, tok)
        for r in pq.read_table(pathlib.Path(args.dataset) / "val.parquet").to_pylist()
    ]
    if not train or not val:
        raise RuntimeError("empty train/val")

    def collate(batch):
        n = max(len(x["input_ids"]) for x in batch)
        return {
            k: torch.tensor(
                [
                    x[k]
                    + [
                        (
                            -100
                            if k == "labels"
                            else tok.pad_token_id
                            if k == "input_ids"
                            else 0
                        )
                    ]
                    * (n - len(x[k]))
                    for x in batch
                ]
            )
            for k in ["input_ids", "attention_mask", "labels"]
        }

    steps = math.ceil(math.ceil(len(train) / args.batch_size) / args.grad_accum)
    half = max(1, math.ceil(steps / 2))
    out = pathlib.Path(args.output)
    config = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        bf16=True,
        max_grad_norm=1.0,
        eval_strategy="steps",
        eval_steps=half,
        save_strategy="no",
        logging_steps=1,
        report_to="none",
        seed=20261114,
        data_seed=20261114,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        remove_unused_columns=False,
    )

    class TimeCap(TrainerCallback):
        """Stop the loop once the wall-clock cap is exceeded (checked after each optimiser step)."""

        def __init__(self, minutes):
            self.limit = minutes * 60
            self.start = None
            self.hit = False

        def on_train_begin(self, args, state, control, **kwargs):
            self.start = time.monotonic()

        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step % 5 == 0:
                print(
                    f"PROGRESS step={state.global_step}/{state.max_steps} seconds={time.monotonic() - self.start:.0f}",
                    flush=True,
                )
            if self.limit and time.monotonic() - self.start > self.limit:
                self.hit = True
                control.should_training_stop = True

    cap = TimeCap(args.max_minutes)
    trainer = Trainer(
        model=model,
        args=config,
        train_dataset=train,
        eval_dataset=val,
        data_collator=collate,
        callbacks=[cap],
    )
    log(
        "training_start",
        inputs={
            "base_model": name,
            "train": len(train),
            "val": len(val),
            "seed": 20261114,
        },
    )
    torch.cuda.reset_peak_memory_stats()
    t0 = time.monotonic()
    trainer.train()
    train_seconds = time.monotonic() - t0
    trainer.evaluate()
    model.save_pretrained(out)
    tok.save_pretrained(out)
    save(out / "loss-curve.json", trainer.state.log_history)
    save(
        out / "training-config.json",
        {
            "base_model": name,
            "max_length": 768,
            "seed": 20261114,
            "targets": targets,
            "eval_steps": half,
            "epochs_requested": args.epochs,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "max_minutes": args.max_minutes,
            "time_cap_hit": cap.hit,
            "global_step": trainer.state.global_step,
            "planned_steps": trainer.state.max_steps,
            "epochs_completed": trainer.state.epoch,
            "train_seconds": train_seconds,
            "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
            "stop_token_supervised": True,
            "lora": {"r": 16, "alpha": 32, "dropout": 0.05},
            "learning_rate": 2e-4,
        },
    )
    log(
        "training_complete",
        outputs=[str(out)],
        metrics={
            "global_step": trainer.state.global_step,
            "train_seconds": train_seconds,
            "time_cap_hit": cap.hit,
        },
    )


if __name__ == "__main__":
    main()
