"""Shared fixtures for the version-2 unit tests: no torch, no model, no network."""

import json
import pathlib
import sys

V2 = pathlib.Path(__file__).resolve().parents[1]
if str(V2) not in sys.path:
    sys.path.insert(0, str(V2))
import _paths  # noqa: E402,F401  (puts scribe/v2 first and scribe second on sys.path)

import config as cfgmod  # noqa: E402

SPECIAL = ["<pad>", "<eos>", "<bos>", "<unk>", "<start_of_turn>", "<end_of_turn>"]
MULTI = ['{"', '":"', '","', '":[', "]}", '"}', "DAY", "MONTH", "202", "20", "-0", "-1", "entry", "route", "events", "REFERRAL", "_SENT"]
CHARS = [chr(c) for c in range(0x20, 0x7F)] + list("äöåÄÖÅ\n")


class FakeTokenizer:
    """Gemma-shaped tokenizer: chat template with one <bos>, special tokens, greedy longest match."""

    bos_token_id = 2
    eos_token_id = 5  # the Gemma mirrors set eos to <end_of_turn>
    pad_token_id = 0
    unk_token_id = 3
    padding_side = "right"

    def __init__(self, mangle=False):
        self.pieces = SPECIAL + MULTI + [c for c in CHARS if c not in MULTI]
        self.ids = {p: i for i, p in enumerate(self.pieces)}
        self.all_special_ids = list(range(len(SPECIAL)))
        self.added_tokens_decoder = {i: SPECIAL[i] for i in range(len(SPECIAL))}
        self._by_length = sorted(self.pieces, key=len, reverse=True)
        self.mangle = mangle

    def get_vocab(self):
        return dict(self.ids)

    def convert_tokens_to_ids(self, token):
        return self.ids.get(token, self.unk_token_id)

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        system = "".join(m["content"] + "\n\n" for m in messages if m["role"] == "system")
        text = "<bos>"
        first = True
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            content = m["content"].strip()
            if self.mangle and role == "model":
                content = content.replace('"', "'")
            text += f"<start_of_turn>{role}\n{system if first else ''}{content}<end_of_turn>\n"
            first = False
        if add_generation_prompt:
            text += "<start_of_turn>model\n"
        return text

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        ids, offsets, pos = [], [], 0
        if add_special_tokens:
            ids.append(self.bos_token_id)
            offsets.append((0, 0))
        while pos < len(text):
            piece = next((p for p in self._by_length if text.startswith(p, pos)), None)
            if piece is None:
                piece_id, width = self.unk_token_id, 1
            else:
                piece_id, width = self.ids[piece], len(piece)
            ids.append(piece_id)
            offsets.append((pos, pos + width))
            pos += width
        out = {"input_ids": ids}
        if return_offsets_mapping:
            out["offset_mapping"] = offsets
        return out

    def decode(self, ids, skip_special_tokens=False):
        return "".join(self.pieces[i] for i in ids if not (skip_special_tokens and i in self.all_special_ids))


def note_row(i, writer="nemotron", kind="standard", events=None, route="SCREENING"):
    events = (
        [{"type": "REFERRAL_SENT", "date": "2025-03-04", "precision": "DAY"}] if events is None else events
    )
    target = {"entry_route": route, "events": events}
    return {
        "id": f"note-{i:04d}",
        "note_date": "2025-06-01",
        "note_text": "Lähete on lähetetty 4.3.2025. Vointi on vakaa.",
        "target_json": json.dumps(target, ensure_ascii=False, separators=(",", ":")),
        "writer": writer,
        "kind": kind,
        "distractors": [],
        "date_forms": ["numeric"] if events else [],
    }


def run_result(cfg, outcomes, seconds_per_step=1.0, seconds_per_note=0.1, status="ok", poison_test=None):
    """A run result shaped like train.py's result.json, with given validation outcomes."""
    n = len(outcomes)
    exact = sum(outcomes) / n
    result = {
        "config": cfg.to_dict(),
        "config_id": cfg.config_id,
        "description": cfgmod.describe(cfg),
        "status": status,
        "eligible": status == "ok",
        "serving_notes": cfg.serving_notes(),
        "loss_path": {"path": "answer-only head"},
        "train": {
            "global_step": cfg.max_steps,
            "planned_steps": cfg.max_steps,
            "time_cap_hit": False,
            "train_seconds": seconds_per_step * cfg.max_steps,
            "seconds_per_step": seconds_per_step,
            "peak_gpu_memory_bytes": 8 * 2**30,
            "final_eval_loss": 0.1,
            "eval_loss_curve": [],
        },
        "val": {
            "metrics": {
                "n": n,
                "note_exact_match": {"value": exact, "n": n, "ci95": [max(0.0, exact - 0.05), min(1.0, exact + 0.05)]},
                "event_f1": exact,
                "route_accuracy": {"value": exact, "n": n, "ci95": [0.0, 1.0]},
                "invalid_output": {"value": 0.0, "n": n, "ci95": [0.0, 0.02]},
                "ids": [f"val-{i:04d}" for i in range(n)],
                "outcomes": list(outcomes),
                "confidences": [-0.001 if ok else -0.5 for ok in outcomes],
            },
            "by_split": {
                "val_nemotron": {"n": n, "note_exact_match": {"value": exact, "n": n, "ci95": [0.0, 1.0]}},
            },
            "decoding": {"seconds_per_note": seconds_per_note, "constraint": {"backend": "none", "detail": ""}},
        },
        "seconds": {"encode": 1.0, "load": 5.0, "eval_loss": 1.0, "train": seconds_per_step * cfg.max_steps, "total": 0.0},
        "artifacts": {"saved": {"kind": "adapter" if cfg.is_adapter else "full", "path": f"/fake/{cfg.name}/adapter"}},
    }
    if poison_test is not None:
        # Test metrics that would change every decision if any selection code looked at them.
        result["test"] = {"metrics": {"note_exact_match": {"value": poison_test}, "outcomes": [poison_test > 0.5] * n}}
        result["test_exact_match"] = poison_test
    return result


def outcomes(n, correct, shift=0):
    """n booleans with `correct` True values, the errors starting at index `shift`."""
    wrong = set(range(shift, shift + (n - correct)))
    return [i not in wrong for i in range(n)]


def eval_result(system, splits, n_per_split=40, exact=0.8, backend="none"):
    """An evaluation shaped like evaluate.py's output."""
    blocks = {}
    for k, name in enumerate(splits):
        ok = outcomes(n_per_split, round(exact * n_per_split), shift=k)
        writer = "haiku" if "haiku" in name else "nemotron"
        group = {
            "n": n_per_split,
            "note_exact_match": {"value": sum(ok) / n_per_split, "n": n_per_split, "ci95": [0.6, 0.9]},
            "event_f1": 0.9,
            "invalid_output": {"value": 0.0, "n": n_per_split, "ci95": [0.0, 0.1]},
        }
        blocks[name] = {
            "metrics": dict(
                group,
                route_accuracy={"value": 0.95, "n": n_per_split, "ci95": [0.8, 1.0]},
                by_writer={writer: group},
                by_kind={"standard": group},
                ids=[f"{name}-{i:04d}" for i in range(n_per_split)],
                outcomes=ok,
                confidences=[-0.001 if x else -0.7 for x in ok],
                risk_coverage={"largest_empirical_coverage": {"0.01": 0.0, "0.05": 0.5}, "limit": "empirical"},
            ),
            "decoding": {"constraint": {"backend": backend, "detail": ""}, "seconds": 1.0},
        }
    return {"system": system, "splits": blocks}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def settings(budget_minutes, **over):
    base = dict(
        budget_minutes=budget_minutes,
        steps=324,
        final_steps=0,
        retrain_final=False,
        sizes=cfgmod.SIZE_LADDER,
        extras=("270m_full",),
        with_eva=False,
        v1_base="4b",
        frozen_path="/fake/selection-frozen.json",
        n_val=250,
        n_test={"test_nemotron": 500, "test_haiku": 46},
        val_splits=["val_nemotron"],
        test_splits=["test_nemotron", "test_haiku"],
        expression_available=(True, ""),
        haiku_train_available=(True, ""),
        data={"val": {"val_nemotron": {"rows": 250, "source": "fake"}}},
        notes=[],
    )
    base.update(over)
    return base
