"""Experiment configurations for the version-2 pathway-scribe comparison. Standard library only.

One RunConfig is one training run. The staged grid (size ladder, adapter method and initialisation,
output format, training data) is generated here so that it can be tested without a GPU.

Where the values come from (research step of 2026-11-14, sources opened that day):
- Base models are the ungated Unsloth mirrors of Gemma 3 with pinned revisions (licence: Gemma Terms
  of Use). Parameter counts are the ones reported by the Hugging Face API for those repositories.
- Target modules are a regular expression restricted to the language model. A suffix list such as
  ["q_proj", ...] also attaches adapters to the SigLIP vision tower of the 4B model.
- rsLoRA scales by alpha / sqrt(r), LoRA and DoRA by alpha / r.
- LoRA+ is an optimiser (peft.optimizers.create_loraplus_optimizer), not a LoraConfig flag.
- 1,716 training notes at an effective batch of 16 are 108 optimisation steps per epoch, 324 for three.
None of these settings has been run on a GPU by the step that wrote this file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import math

SEED = 20261114
DEFAULT_STEPS = 324
STEPS_PER_EPOCH = 108

BASES = {
    "270m": {
        "repo": "unsloth/gemma-3-270m-it",
        "revision": "23cf460f6bb16954176b3ddcc8d4f250501458a9",
        "parameters": 268_098_176,
        "multimodal": False,
    },
    "1b": {
        "repo": "unsloth/gemma-3-1b-it",
        "revision": "5b11413a10db4e486ef16a20101fd028f8f2499c",
        "parameters": 999_885_952,
        "multimodal": False,
    },
    "4b": {
        "repo": "unsloth/gemma-3-4b-it",
        "revision": "bf46152c47f5dd20b896357cb51abc4c03b8ee8c",
        "parameters": 4_300_079_472,
        "multimodal": True,
    },
}
SIZE_LADDER = ("270m", "1b", "4b")

_LAYER = r"(?:.*\.)?(?:language_model|model)\.layers\.\d+\."
TARGETS = {
    "attn_mlp": _LAYER + r"(?:self_attn\.(?:q_proj|k_proj|v_proj|o_proj)|mlp\.(?:gate_proj|up_proj|down_proj))",
    "attn": _LAYER + r"self_attn\.(?:q_proj|k_proj|v_proj|o_proj)",
    "mlp": _LAYER + r"mlp\.(?:gate_proj|up_proj|down_proj)",
}

METHODS = ("lora", "rslora", "dora", "full")
INITS = ("default", "pissa", "olora", "eva")
# PEFT init_lora_weights value per initialisation. "pissa_niter_4" is the fast-SVD form of PiSSA.
INIT_LORA_WEIGHTS = {"default": True, "pissa": "pissa_niter_4", "olora": "olora", "eva": "eva"}
FORMATS = ("absolute", "expression")
TRAIN_DATA = ("nemotron", "nemotron+haiku")

# (per-device batch, gradient accumulation); the effective batch is 16 for every size.
BATCH = {"270m": (16, 1), "1b": (16, 1), "4b": (8, 2)}
LORA_LR = 2e-4
FULL_FINETUNE_LR = 5e-5
LORAPLUS_RATIO = 16.0


class ConfigError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class RunConfig:
    name: str
    base: str = "1b"
    method: str = "lora"  # lora | rslora | dora | full (full fine-tune, no adapter)
    init: str = "default"  # default | pissa | olora | eva
    loraplus_ratio: float = 0.0  # 0 = off, otherwise learning-rate ratio of the B matrices
    rank: int = 16
    alpha: float = 32.0
    dropout: float = 0.0
    targets: str = "attn_mlp"
    output_format: str = "absolute"  # absolute | expression
    train_data: str = "nemotron"  # nemotron | nemotron+haiku
    learning_rate: float = LORA_LR
    max_steps: int = DEFAULT_STEPS
    batch_size: int = 16
    grad_accum: int = 1
    eval_every: int = STEPS_PER_EPOCH
    warmup_fraction: float = 0.05
    scheduler: str = "cosine"
    weight_decay: float = 0.0
    max_grad_norm: float = 1.0
    max_length: int = 1024  # guard only: longer examples are refused, never truncated
    gradient_checkpointing: bool = False
    supervise_stop_token: bool = True
    seed: int = SEED

    def __post_init__(self):
        self.validate()

    # ---- derived values -------------------------------------------------------------------
    @property
    def is_adapter(self):
        return self.method != "full"

    @property
    def effective_batch(self):
        return self.batch_size * self.grad_accum

    @property
    def scaling(self):
        """Multiplier applied to the low-rank update; None for a full fine-tune."""
        if not self.is_adapter:
            return None
        return self.alpha / math.sqrt(self.rank) if self.method == "rslora" else self.alpha / self.rank

    @property
    def warmup_steps(self):
        return math.ceil(self.warmup_fraction * self.max_steps)

    @property
    def config_id(self):
        """Hash of everything except the display name: equal settings give equal ids."""
        d = self.to_dict()
        d.pop("name")
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]

    @property
    def recipe_id(self):
        """Like config_id, but blind to how the effective batch is split into batch and accumulation
        (an out-of-memory retry halves one and doubles the other without changing the recipe)."""
        d = self.to_dict()
        for key in ("name", "batch_size", "grad_accum"):
            d.pop(key)
        d["effective_batch"] = self.effective_batch
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]

    # ---- validation -----------------------------------------------------------------------
    def validate(self):
        def need(ok, message):
            if not ok:
                raise ConfigError(f"{self.name}: {message}")

        need(self.base in BASES, f"unknown base {self.base!r}")
        need(self.method in METHODS, f"unknown method {self.method!r}")
        need(self.init in INITS, f"unknown init {self.init!r}")
        need(self.targets in TARGETS, f"unknown targets {self.targets!r}")
        need(self.output_format in FORMATS, f"unknown output format {self.output_format!r}")
        need(self.train_data in TRAIN_DATA, f"unknown training data {self.train_data!r}")
        need(self.rank >= 1 and self.alpha > 0, "rank and alpha must be positive")
        need(0 <= self.dropout < 1, "dropout must be in [0, 1)")
        need(self.max_steps >= 1 and 1 <= self.eval_every, "steps and eval interval must be positive")
        need(self.batch_size >= 1 and self.grad_accum >= 1, "batch settings must be positive")
        need(self.learning_rate > 0, "learning rate must be positive")
        need(self.loraplus_ratio == 0 or self.loraplus_ratio >= 1, "LoRA+ ratio is 0 (off) or at least 1")
        if self.method == "full":
            need(self.init == "default", "a full fine-tune has no adapter initialisation")
            need(self.loraplus_ratio == 0, "LoRA+ applies to adapters only")
        if self.method == "dora":
            # The LoRA+ grouping rule puts every DoRA magnitude vector into the high-learning-rate group.
            need(self.loraplus_ratio == 0, "DoRA is not combined with LoRA+")
        if self.init != "default":
            # Only the plain LoRA form of each initialisation was instantiated in the research step.
            need(self.method == "lora", "alternative initialisations are only used with plain LoRA")
            need(self.loraplus_ratio == 0, "alternative initialisations are not combined with LoRA+")
        return self

    # ---- conversion -----------------------------------------------------------------------
    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d):
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ConfigError(f"unknown configuration keys: {sorted(unknown)}")
        return cls(**d)

    def with_(self, **changes):
        return dataclasses.replace(self, **changes)

    def lora_kwargs(self):
        """Keyword arguments for peft.LoraConfig (EvaConfig is added by the training code)."""
        if not self.is_adapter:
            raise ConfigError(f"{self.name}: a full fine-tune has no LoraConfig")
        return {
            "r": self.rank,
            "lora_alpha": int(self.alpha) if float(self.alpha).is_integer() else self.alpha,
            "lora_dropout": self.dropout,
            "target_modules": TARGETS[self.targets],  # a string is matched with re.fullmatch
            "bias": "none",
            "task_type": "CAUSAL_LM",
            "use_rslora": self.method == "rslora",
            "use_dora": self.method == "dora",
            "init_lora_weights": INIT_LORA_WEIGHTS[self.init],
        }

    def serving_notes(self):
        """What the adapter needs before a vLLM server can load it (from the opened vLLM loader source)."""
        notes = []
        if self.method == "full":
            notes.append("full fine-tune: serve the saved model directory, there is no adapter")
        if self.method == "dora":
            notes.append("DoRA: vLLM rejects use_dora, merge into the base weights before serving")
        if self.init in ("pissa", "olora"):
            notes.append(
                f"{self.init}: base weights are rewritten during training; the adapter is saved converted "
                f"to a plain LoRA of rank {2 * self.rank}"
            )
        served_rank = 2 * self.rank if self.init in ("pissa", "olora") else self.rank
        if self.is_adapter and served_rank > 16:
            notes.append(f"rank {served_rank}: the vLLM default --max-lora-rank is 16 and must be raised")
        return notes


def diff(a, b):
    """Fields (other than the name) in which two configurations differ: {field: (a, b)}."""
    da, db = a.to_dict(), b.to_dict()
    return {k: (da[k], db[k]) for k in da if k != "name" and da[k] != db[k]}


def _eval_every(steps):
    return max(1, min(STEPS_PER_EPOCH, steps // 3 or 1))


def control(base, steps=DEFAULT_STEPS, name=None):
    """Default LoRA: rank 16, alpha 32 (scale 2.0), all seven language-model projections, no dropout."""
    batch, accum = BATCH[base]
    return RunConfig(
        name=name or f"{base}-lora-r16",
        base=base,
        batch_size=batch,
        grad_accum=accum,
        max_steps=steps,
        eval_every=_eval_every(steps),
    )


STAGE_A_EXTRAS = ("270m_full", "270m_lora_r128")


def stage_a(sizes=SIZE_LADDER, steps=DEFAULT_STEPS, extras=("270m_full",)):
    """Size ladder: the same default LoRA and the same number of optimisation steps on every size.

    Extras are the two documented recipes for the 270M model (Google: full fine-tune at 5e-5;
    Unsloth notebook: LoRA rank 128, alpha 128 at 5e-5). They are finalists, not rungs of the ladder.
    """
    unknown = set(extras) - set(STAGE_A_EXTRAS)
    if unknown:
        raise ConfigError(f"unknown Stage A extras: {sorted(unknown)}")
    arms = [control(b, steps, name=f"A-{b}-lora-r16") for b in SIZE_LADDER if b in sizes]
    if not arms:
        raise ConfigError("Stage A needs at least one size")
    if "270m" in sizes and "270m_full" in extras:
        arms.append(
            control("270m", steps).with_(name="A-270m-full-finetune", method="full", learning_rate=FULL_FINETUNE_LR)
        )
    if "270m" in sizes and "270m_lora_r128" in extras:
        arms.append(
            control("270m", steps).with_(name="A-270m-lora-r128", rank=128, alpha=128.0, learning_rate=FULL_FINETUNE_LR)
        )
    return arms


def stage_b(control_config, with_eva=False):
    """Adapter method and initialisation, one change at a time against the control, in priority order.

    Under a tight time budget the list is cut from the end, so DoRA (slowest, and it must be merged
    before vLLM can serve it) goes first.
    """
    c = control_config
    if not c.is_adapter or c.method != "lora" or c.init != "default" or c.loraplus_ratio:
        raise ConfigError("Stage B starts from a plain LoRA control")
    arms = [
        # Same rank, twice the control's scale (for rank 16: alpha 16 under rsLoRA = scale 4.0).
        c.with_(name="B-rslora-scale-x2", method="rslora", alpha=2 * c.scaling * math.sqrt(c.rank)),
        # Four times the rank at the control's scale: isolates rank from scale.
        c.with_(name="B-rslora-rank-x4", method="rslora", rank=4 * c.rank, alpha=c.scaling * math.sqrt(4 * c.rank)),
        # LoRA+: B matrices at 16 times the base learning rate, base rate halved as the PEFT docstring advises.
        c.with_(name="B-loraplus", loraplus_ratio=LORAPLUS_RATIO, learning_rate=c.learning_rate / 2),
        # PiSSA as documented by PEFT (alpha = r); it rewrites the base weights.
        c.with_(name="B-pissa", init="pissa", alpha=float(c.rank)),
    ]
    if with_eva:
        arms.append(c.with_(name="B-eva", init="eva"))
    arms.append(c.with_(name="B-dora", method="dora"))
    return arms


def stage_c_format(best):
    """Expression output (relative dates left as expressions, resolved by code) against absolute dates."""
    if best.output_format != "absolute":
        raise ConfigError("the format ablation starts from the absolute format")
    return best.with_(name="C-format-expression", output_format="expression")


def stage_c_data(best):
    """Nemotron-written plus Haiku-written training notes against Nemotron-written only, same step count."""
    if best.train_data != "nemotron":
        raise ConfigError("the data ablation starts from nemotron-only training data")
    return best.with_(name="C-data-nemotron+haiku", train_data="nemotron+haiku")


def v1_recipe(base="4b", steps=DEFAULT_STEPS):
    """The version-1 recipe (scribe/train_lora.py as repaired on 2026-11-14) expressed as a version-2 run.

    Rank 16, alpha 32, dropout 0.05, learning rate 2e-4, cosine schedule with 5% warm-up, batch 2 with
    accumulation 8, gradient checkpointing, stop token supervised, absolute format, Nemotron notes only.
    """
    return RunConfig(
        name=f"v1-recipe-{base}",
        base=base,
        dropout=0.05,
        batch_size=2,
        grad_accum=8,
        gradient_checkpointing=True,
        max_steps=steps,
        eval_every=_eval_every(steps),
        max_length=768,
    )


def grid(
    bases=SIZE_LADDER,
    methods=("lora", "rslora", "dora"),
    inits=("default", "pissa"),
    loraplus=(0.0, LORAPLUS_RATIO),
    ranks=(16,),
    formats=FORMATS,
    train_data=TRAIN_DATA,
    steps=DEFAULT_STEPS,
):
    """Every valid combination of the listed factors (invalid ones are skipped, not repaired)."""
    out = []
    for base, method, init, ratio, rank, fmt, data in itertools.product(
        bases, methods, inits, loraplus, ranks, formats, train_data
    ):
        batch, accum = BATCH[base]
        name = "-".join(
            [base, method, f"r{rank}", init, "plus" if ratio else "noplus", fmt, data.replace("+", "_")]
        )
        try:
            out.append(
                RunConfig(
                    name=name,
                    base=base,
                    method=method,
                    init=init,
                    loraplus_ratio=ratio,
                    rank=rank,
                    alpha=float(rank) if init == "pissa" else 2.0 * (math.sqrt(rank) if method == "rslora" else rank),
                    learning_rate=LORA_LR / 2 if ratio else LORA_LR,
                    output_format=fmt,
                    train_data=data,
                    batch_size=batch,
                    grad_accum=accum,
                    max_steps=steps,
                    eval_every=_eval_every(steps),
                )
            )
        except ConfigError:
            continue
    return out


def describe(c):
    if not c.is_adapter:
        return f"{c.base} full fine-tune, lr {c.learning_rate:g}, {c.output_format}, {c.train_data}"
    parts = [c.base, c.method, f"r{c.rank}", f"alpha {c.alpha:g}", f"scale {c.scaling:g}"]
    if c.init != "default":
        parts.append(f"init {c.init}")
    if c.loraplus_ratio:
        parts.append(f"LoRA+ x{c.loraplus_ratio:g}")
    if c.dropout:
        parts.append(f"dropout {c.dropout:g}")
    parts += [f"lr {c.learning_rate:g}", c.output_format, c.train_data]
    return ", ".join(parts)


if __name__ == "__main__":
    for arm in stage_a(extras=STAGE_A_EXTRAS) + stage_b(control("1b"), with_eva=True) + [v1_recipe()]:
        print(f"{arm.name:24s} {arm.config_id}  {describe(arm)}")
