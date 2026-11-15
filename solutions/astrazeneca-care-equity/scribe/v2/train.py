"""One training run = one RunConfig. GPU only (except the wiring test with --smoke-tokenizer).

What a run does:
  1. loads the pinned base model in bfloat16 with sdpa attention (a full fine-tune keeps float32
     master weights and uses bfloat16 autocast);
  2. encodes every note with the Gemma chat template: one <bos>, loss only on the answer and its
     closing <end_of_turn>, no truncation (an over-long example stops the run);
  3. trains for a fixed number of optimisation steps with a fixed seed, evaluating the masked loss
     on validation at fixed intervals;
  4. saves the adapter (or the full model), the loss curve, and result.json with validation metrics
     from greedy generation, wall-clock times, throughput and peak memory.

It never reads a test split.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import time
import traceback

import _paths  # noqa: F401
import config as cfgmod
import data_iface
import evaluate
import formats
import modeling
from core import ARTIFACTS, load_json, log, save_json, versions

EOT = "<end_of_turn>"
IGNORE = -100


def encode(row, tok, fmt, max_length=1024, supervise_stop=True):
    """Token ids with labels on the answer (and its <end_of_turn>) only. Works with any tokenizer
    that has a chat template and returns character offsets, so it is unit-tested without a model."""
    msgs = fmt.messages(row)
    target = fmt.target(row)
    prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    full = tok.apply_chat_template(
        msgs + [{"role": "assistant", "content": target}], tokenize=False, add_generation_prompt=False
    )
    if not full.startswith(prompt) or not full[len(prompt) :].startswith(target):
        raise ValueError("chat template drift: the answer does not directly follow the generation prompt")
    start = len(prompt)
    end = start + len(target)
    if supervise_stop:
        if not full[end:].startswith(EOT):
            raise ValueError("chat template does not close the answer with <end_of_turn>")
        end += len(EOT)
    enc = tok(full, add_special_tokens=False, return_offsets_mapping=True)  # the template already has <bos>
    ids = list(enc["input_ids"])
    if len(ids) > max_length:
        raise ValueError(f"example {row['id']} has {len(ids)} tokens (limit {max_length}); refusing to truncate")
    labels = [t if (hi > start and lo < end) else IGNORE for t, (lo, hi) in zip(ids, enc["offset_mapping"])]
    supervised = [t for t in labels if t != IGNORE]
    if not supervised:
        raise ValueError("empty answer span")
    bos = getattr(tok, "bos_token_id", None)
    if bos is not None and ids.count(bos) != 1:
        raise ValueError(f"expected exactly one <bos>, found {ids.count(bos)}")
    if supervise_stop and supervised[-1] != tok.convert_tokens_to_ids(EOT):
        raise ValueError("the last supervised token is not <end_of_turn>")
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels}


def make_collate(pad_id):
    def collate(batch):
        import torch

        n = max(len(x["input_ids"]) for x in batch)
        pad = {"input_ids": pad_id, "attention_mask": 0, "labels": IGNORE}
        return {k: torch.tensor([x[k] + [pad[k]] * (n - len(x[k])) for x in batch]) for k in pad}

    return collate


def _length_stats(encoded):
    lengths = sorted(len(x["input_ids"]) for x in encoded)
    answer = [sum(t != IGNORE for t in x["labels"]) for x in encoded]
    return {
        "examples": len(lengths),
        "tokens": sum(lengths),
        "max": lengths[-1],
        "median": lengths[len(lengths) // 2],
        "answer_tokens": sum(answer),
        "answer_max": max(answer),
    }


def run(
    cfg, out_dir, max_minutes=0.0, smoke=None, limit_train=0, limit_val=0, save=True, eval_batch_size=16, full_logits=False
):
    import torch
    from transformers import Trainer, TrainerCallback, TrainingArguments, set_seed

    clock = {"start": time.monotonic()}
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ok, why = formats.available(cfg.output_format)
    if not ok:
        raise RuntimeError(f"output format {cfg.output_format!r} is unavailable: {why}")
    fmt = formats.get_format(cfg.output_format)
    set_seed(cfg.seed)

    tok = modeling.load_tokenizer(cfg.base, smoke)
    train_rows, train_sources = data_iface.training_rows(cfg.train_data)
    val_sets, val_sources = data_iface.heldout_rows("val")
    if not val_sets:
        raise RuntimeError("no validation split is available")
    if limit_val:  # wiring tests: the first N notes of every validation split, as evaluate.py --limit does
        val_sets = {name: rows[:limit_val] for name, rows in val_sets.items()}
    val_rows = [dict(r, split=name) for name, rows in val_sets.items() for r in rows]
    if limit_train:
        train_rows = train_rows[:limit_train]
    data_iface.assert_disjoint(train_rows, val_rows, "validation")

    tok.padding_side = "right"
    train = [encode(r, tok, fmt, cfg.max_length, cfg.supervise_stop_token) for r in train_rows]
    val = [encode(r, tok, fmt, cfg.max_length, cfg.supervise_stop_token) for r in val_rows]
    train_stats, val_stats = _length_stats(train), _length_stats(val)
    max_new_tokens = max(48, max(train_stats["answer_max"], val_stats["answer_max"]) + 16)
    clock["encoded"] = time.monotonic()

    model = modeling.load_base(cfg.base, smoke, tok, full_precision=not cfg.is_adapter)
    device = next(model.parameters()).device
    if cfg.gradient_checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    collate = make_collate(tok.pad_token_id)
    eva_batches = None
    if cfg.init == "eva":
        eva_batches = torch.utils.data.DataLoader(
            train, batch_size=8, collate_fn=lambda b: {k: v.to(device) for k, v in collate(b).items()}
        )
    model, adapter_info = modeling.add_adapter(model, cfg, eva_batches, init_dir=out_dir / "initial-adapter")
    model.config.use_cache = False
    clock["loaded"] = time.monotonic()

    class Clock(TrainerCallback):
        def __init__(self):
            self.limit = max_minutes * 60
            self.start = None
            self.hit = False
            self.calibration = None

        def on_train_begin(self, args, state, control, **kwargs):
            self.start = time.monotonic()

        def on_step_end(self, args, state, control, **kwargs):
            elapsed = time.monotonic() - self.start
            if state.global_step == 20:
                self.calibration = {"steps": 20, "seconds": elapsed}
            if state.global_step % 10 == 0:
                print(f"PROGRESS step={state.global_step}/{state.max_steps} seconds={elapsed:.0f}", flush=True)
            if self.limit and elapsed > self.limit:
                self.hit = True
                control.should_training_stop = True

    watch = Clock()
    on_gpu = device.type == "cuda"
    args = TrainingArguments(
        output_dir=str(out_dir / "checkpoints"),
        learning_rate=cfg.learning_rate,
        lr_scheduler_type=cfg.scheduler,
        warmup_steps=cfg.warmup_steps,  # an integer works on Transformers 4 and 5; warmup_ratio is gone in 5
        weight_decay=cfg.weight_decay,
        max_steps=cfg.max_steps,
        max_grad_norm=cfg.max_grad_norm,
        per_device_train_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        per_device_eval_batch_size=cfg.batch_size,
        eval_strategy="steps",
        eval_steps=cfg.eval_every,
        save_strategy="no",
        logging_steps=5,
        report_to="none",
        seed=cfg.seed,
        data_seed=cfg.seed,
        bf16=on_gpu,
        use_cpu=not on_gpu,
        remove_unused_columns=False,
    )
    optimizer = modeling.make_optimizer(model, cfg)

    class AnswerOnlyTrainer(Trainer):
        """Same loss as the stock Trainer, with the output head applied to answer positions only."""

        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
            loss = modeling.answer_only_loss(model, inputs["input_ids"], inputs["attention_mask"], inputs["labels"])
            return (loss, {"loss": loss}) if return_outputs else loss

    # Self-check on two examples: the answer-only loss must equal the stock loss, otherwise use the stock path.
    loss_path = {"path": "stock (requested)" if full_logits else "answer-only head"}
    if not full_logits:
        probe = {k: v.to(device) for k, v in collate(train[:2]).items()}
        try:
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=on_gpu):
                agree, stock, ours = modeling.loss_paths_agree(model, probe)
            loss_path.update(stock_loss=stock, answer_only_loss=ours, agree=agree)
            if not agree:
                loss_path["path"] = "stock (self-check disagreed)"
        except Exception as e:  # unexpected model layout: keep the stock path and say so
            loss_path.update(path="stock (self-check failed)", error=f"{type(e).__name__}: {e}"[:300])
    trainer_cls = AnswerOnlyTrainer if loss_path["path"] == "answer-only head" else Trainer
    trainer = trainer_cls(
        model=model,
        args=args,
        train_dataset=train,
        eval_dataset=val,
        data_collator=collate,
        callbacks=[watch],
        **({"optimizers": (optimizer, None)} if optimizer is not None else {}),
    )
    if on_gpu:
        torch.cuda.reset_peak_memory_stats()

    base_result = {
        "schema": "scribe-v2-run-v1",
        "synthetic": True,
        "smoke": bool(smoke),
        "config": cfg.to_dict(),
        "config_id": cfg.config_id,
        "description": cfgmod.describe(cfg),
        "base": {k: cfgmod.BASES[cfg.base][k] for k in ("repo", "revision")},
        "versions": versions(),
        "gpu": modeling.gpu_summary(),
        "data": {
            "train": train_sources,
            "val": val_sources,
            "train_tokens": train_stats,
            "val_tokens": val_stats,
            "limit_train": limit_train,
            "limit_val": limit_val,
        },
        "adapter": adapter_info,
        "loss_path": loss_path,
        "serving_notes": cfg.serving_notes(),
        "max_new_tokens": max_new_tokens,
    }

    oom = getattr(torch, "OutOfMemoryError", torch.cuda.OutOfMemoryError)
    try:
        trainer.train()
    except oom as e:
        result = dict(base_result, status="oom", error=str(e)[:500], eligible=False)
        save_json(out_dir / "result.json", result)
        return result
    train_seconds = time.monotonic() - watch.start
    clock["trained"] = time.monotonic()
    final_eval = trainer.evaluate()
    clock["eval_loss"] = time.monotonic()

    history = trainer.state.log_history
    save_json(out_dir / "loss-curve.json", history)
    steps_done = trainer.state.global_step
    mean_tokens = train_stats["tokens"] / train_stats["examples"]
    saved = modeling.save_trained(model, tok, cfg, out_dir, out_dir / "initial-adapter") if save else None

    # Validation by greedy generation: the numbers every selection is made on.
    model.config.use_cache = True
    records, decoding = evaluate.predict(model, tok, val_rows, fmt, "off", eval_batch_size, max_new_tokens)
    clock["generated"] = time.monotonic()
    val_metrics = evaluate.score(val_rows, records)
    by_split = {}
    for name in val_sets:
        idx = [i for i, r in enumerate(val_rows) if r["split"] == name]
        if idx:
            sub = evaluate.score([val_rows[i] for i in idx], [records[i] for i in idx])
            by_split[name] = {k: sub[k] for k in ("n", "note_exact_match", "event_f1", "route_accuracy", "invalid_output")}
    save_json(out_dir / "val-records.json", records)

    complete = steps_done >= cfg.max_steps and not watch.hit
    result = dict(
        base_result,
        status="ok" if complete else "time_cap",
        eligible=complete,  # a run stopped by the time cap did not get the same number of steps
        train={
            "global_step": steps_done,
            "planned_steps": cfg.max_steps,
            "time_cap_minutes": max_minutes,
            "time_cap_hit": watch.hit,
            "train_seconds": train_seconds,
            "seconds_per_step": train_seconds / steps_done if steps_done else None,
            "approx_tokens_per_second": steps_done * cfg.effective_batch * mean_tokens / train_seconds
            if train_seconds
            else None,
            "calibration_first_20_steps": watch.calibration,
            "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated() if on_gpu else None,
            "final_eval_loss": final_eval.get("eval_loss"),
            "eval_loss_curve": [
                {"step": step, "eval_loss": loss}
                for step, loss in sorted({h["step"]: h["eval_loss"] for h in history if "eval_loss" in h}.items())
            ],
            "train_loss_curve": [{"step": h["step"], "loss": h["loss"]} for h in history if "loss" in h],
        },
        val={"metrics": val_metrics, "by_split": by_split, "decoding": decoding},
        seconds={
            "encode": clock["encoded"] - clock["start"],
            "load": clock["loaded"] - clock["encoded"],
            "train": train_seconds,
            "eval_loss": clock["eval_loss"] - clock["trained"],
            "generate": clock["generated"] - clock["eval_loss"],
            "total": time.monotonic() - clock["start"],
        },
        artifacts={
            "saved": saved,
            "loss_curve": str(out_dir / "loss-curve.json"),
            "val_records": str(out_dir / "val-records.json"),
        },
    )
    save_json(out_dir / "result.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description="Train and validate one version-2 configuration.")
    p.add_argument("--config-json", help="file with a RunConfig dictionary")
    p.add_argument("--preset", choices=["control", "v1"], help="default LoRA control or the version-1 recipe")
    p.add_argument("--base", default="1b", choices=list(cfgmod.BASES))
    p.add_argument("--steps", type=int, default=cfgmod.DEFAULT_STEPS)
    p.add_argument("--out", default=None, help="run directory (default scribe/v2/artifacts/<name>-<config id>)")
    p.add_argument("--max-minutes", type=float, default=0, help="wall-clock cap on the training loop; 0 disables")
    p.add_argument("--eval-batch-size", type=int, default=16)
    p.add_argument("--batch-size", type=int, default=0, help="override the per-device batch (e.g. after an OOM)")
    p.add_argument("--grad-accum", type=int, default=0, help="override gradient accumulation")
    p.add_argument("--full-logits", action="store_true", help="use the stock loss path (logits for every position)")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--limit-train", type=int, default=0, help="first N training notes only (wiring tests)")
    p.add_argument("--limit-val", type=int, default=0)
    p.add_argument("--smoke-tokenizer", default=None, help="wiring test: tiny random model with this local tokenizer")
    args = p.parse_args()

    if args.config_json:
        cfg = cfgmod.RunConfig.from_dict(load_json(args.config_json))
    elif args.preset == "v1":
        cfg = cfgmod.v1_recipe(args.base, args.steps)
    elif args.preset == "control":
        cfg = cfgmod.control(args.base, args.steps)
    else:
        p.error("give --config-json or --preset")
    if args.batch_size or args.grad_accum:
        cfg = cfg.with_(batch_size=args.batch_size or cfg.batch_size, grad_accum=args.grad_accum or cfg.grad_accum)
    out_dir = pathlib.Path(args.out) if args.out else ARTIFACTS / f"{cfg.name}-{cfg.config_id}"
    smoke = {"tokenizer": args.smoke_tokenizer} if args.smoke_tokenizer else None
    try:
        result = run(
            cfg,
            out_dir,
            args.max_minutes,
            smoke,
            args.limit_train,
            args.limit_val,
            not args.no_save,
            args.eval_batch_size,
            args.full_logits,
        )
    except Exception as e:  # leave a truthful record for the ablation runner, then fail loudly
        out_dir.mkdir(parents=True, exist_ok=True)
        save_json(
            out_dir / "result.json",
            {
                "schema": "scribe-v2-run-v1",
                "smoke": bool(smoke),
                "config": cfg.to_dict(),
                "config_id": cfg.config_id,
                "status": "error",
                "eligible": False,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-4000:],
                "versions": versions(),
            },
        )
        if not smoke:
            log("v2_train", command=f"train.py {cfg.name}", inputs=cfg.to_dict(), status="error", metrics={"error": str(e)[:300]})
        raise
    if not smoke:
        val = result.get("val", {}).get("metrics", {})
        log(
            "v2_train",
            command=f"train.py {cfg.name}",
            inputs={"config_id": cfg.config_id, "description": cfgmod.describe(cfg)},
            outputs=[str(out_dir / "result.json")],
            metrics={
                "status": result["status"],
                "steps": result.get("train", {}).get("global_step"),
                "train_seconds": result.get("train", {}).get("train_seconds"),
                "val_note_exact_match": (val.get("note_exact_match") or {}).get("value"),
                "val_n": val.get("n"),
            },
            status="ok" if result["status"] in ("ok", "time_cap") else "error",
        )
    val = result.get("val", {}).get("metrics", {})
    em = (val.get("note_exact_match") or {}).get("value")
    print(f"RESULT {cfg.name} status={result['status']} val_exact_match={em} total_seconds={result.get('seconds', {}).get('total')}")
    if math.isnan(result.get("train", {}).get("final_eval_loss") or 0.0):
        raise SystemExit("validation loss is NaN")


if __name__ == "__main__":
    main()
