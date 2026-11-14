"""Staged ablation under a wall-clock budget. Every choice is made on validation notes; the test
notes are read once, after the selection has been frozen.

    python scribe/v2/run_ablation.py --time-budget-min 60

Stage A   size ladder: the same default LoRA, absolute format, Nemotron notes, the same number of
          optimisation steps on every size (270M, 1B, 4B). The documented full fine-tune of the 270M
          model runs alongside as a finalist.
Stage B   adapter method and initialisation on the chosen size, one change at a time against the
          Stage A run of that size (rsLoRA at twice the scale, rsLoRA at four times the rank, LoRA+,
          PiSSA, optionally EVA, DoRA).
Stage C   on the chosen method: expression output against absolute dates, then Nemotron+Haiku training
          notes against Nemotron only. The second starts from the winner of the first, so the selected
          configuration has always been trained and validated as a whole.
Final     one final run of the selected configuration (an identical finished run is reused), a check
          of schema-constrained decoding on validation, the version-1 recipe, then the selection is
          frozen and three systems are evaluated once on test_nemotron and test_haiku: the base model
          zero-shot, the version-1 recipe and the selected configuration. Exact McNemar tests between
          them; risk-control thresholds from validation, checked on test.

Selection rules (fixed here, before any run):
  size     highest validation note-level exact match; a smaller size is taken instead when it is
           within 3 points and not significantly worse on the paired validation notes (exact McNemar
           p >= 0.05).
  arm      a change replaces the control only if it is better on the paired validation notes with
           exact McNemar p < 0.05; among several such arms the highest exact match wins. Otherwise the
           control stays. p-values are not adjusted for the number of arms.
  decoding schema-constrained decoding is used only if its validation exact match is strictly higher.

Time budget. Items claim the budget in this order: Stage A sizes from small to large, Stage A extras,
Stage B arms in listed order, Stage C format, Stage C data. An item runs only if its estimated
duration fits in what is left after reserving the final phase; otherwise it is dropped and recorded,
and later items never pre-empt earlier ones. Estimates come from runs already measured in the same
session (scaled by parameter count for a size not yet measured); the smallest size always runs first
and without a cap, because nothing is measured before it and without it there is no result at all. Inside the final phase the order of sacrifice is: the
constrained-decoding check, then the version-1 recipe, then the zero-shot base model. The selected
configuration is always trained and tested. Everything dropped is listed in the output.

Outputs: data/scribe/v2/ablation-v1.json and scribe/v2/RESULTS.md (rendered from that JSON).
"""

from __future__ import annotations

import argparse
import pathlib
import socket
import subprocess
import sys
import time

import _paths
import config as cfgmod
import data_iface
import formats
import report
import risk
from core import ABLATION_JSON, ARTIFACTS, RESULTS_MD, load_json, log, save_json, utc_now, versions
from metrics import mcnemar

MARGIN = 0.03
LEVEL = 0.05
RESERVE_FRACTION_UNMEASURED = 0.4  # share of the budget held back for the final phase until then
# Planning multipliers on the measured seconds per step of a plain LoRA run of the same size. They
# decide what is attempted, nothing else; reported durations are always measured.
PLANNING_FACTORS = {"dora": 1.3, "gradient_checkpointing": 1.5, "small_batch": 1.5, "zero_shot_generation": 2.0}


# ---- selection: pure functions on validation views -------------------------------------------------


def eligible(result):
    return bool(result) and result.get("status") == "ok" and bool(result.get("eligible")) and "val" in result


def recipe_of(result):
    """Recipe id of a finished run (its batch split may differ from the plan after an OOM retry)."""
    try:
        return cfgmod.RunConfig.from_dict(result["config"]).recipe_id
    except (KeyError, TypeError, cfgmod.ConfigError):
        return None


def val_view(result):
    """The only part of a run that selection is allowed to see: its validation outcomes."""
    m = result["val"]["metrics"]
    return {
        "name": result["config"]["name"],
        "base": result["config"]["base"],
        "exact": m["note_exact_match"]["value"],
        "n": m["n"],
        "ids": list(m["ids"]),
        "outcomes": [bool(x) for x in m["outcomes"]],
    }


def compare(a, b):
    """Paired exact McNemar test between two validation views."""
    if a["ids"] != b["ids"]:
        raise ValueError(f"{a['name']} and {b['name']} were validated on different notes")
    a_only = sum(x and not y for x, y in zip(a["outcomes"], b["outcomes"]))
    b_only = sum(y and not x for x, y in zip(a["outcomes"], b["outcomes"]))
    return {
        "a": a["name"],
        "b": b["name"],
        "a_exact": a["exact"],
        "b_exact": b["exact"],
        "a_only_correct": a_only,
        "b_only_correct": b_only,
        "exact_p": mcnemar(a_only, b_only),
    }


def select_size(views, margin=MARGIN, level=LEVEL):
    """views: validation views of the ladder runs, smallest size first."""
    if not views:
        raise ValueError("no eligible size")
    best = max(views, key=lambda v: v["exact"])  # max keeps the first (smallest) on ties
    comparisons, chosen = [], best
    for v in views:
        if v is best:
            break
        test = compare(v, best)
        comparisons.append(test)
        if best["exact"] - v["exact"] <= margin and test["exact_p"] >= level:
            chosen = v
            break
    if len(views) == 1:
        # One finished rung is not a comparison; do not call it "the highest" (review finding 0).
        why = f"{best['name']} is the only ladder run that finished ({best['exact']:.3f}); no size was compared"
    elif chosen is best:
        why = f"{best['name']} has the highest validation exact match among the {len(views)} ladder runs ({best['exact']:.3f})"
    else:
        why = (f"{chosen['name']} ({chosen['exact']:.3f}) is within {margin:.2f} of {best['name']} ({best['exact']:.3f}) "
               f"and not significantly worse (p >= {level}); the smaller size is taken")
    return {"winner": chosen["name"], "best_by_exact_match": best["name"], "comparisons": comparisons, "rationale": why}


def select_arm(control, arms, level=LEVEL):
    """Keep the control unless an arm is significantly better on the paired validation notes."""
    if not arms:
        # Nothing ran, so nothing was tested (review finding 1).
        return {"winner": control["name"], "adopted": False, "comparisons": [],
                "rationale": "no arm ran (all dropped for time or unavailable); the control stays by default"}
    comparisons = [compare(arm, control) for arm in arms]
    better = [
        (arm, test)
        for arm, test in zip(arms, comparisons)
        if arm["exact"] > control["exact"] and test["exact_p"] < level
    ]
    if not better:
        why = (f"no arm beat {control['name']} with p < {level} on the paired validation notes "
               f"({len(arms)} arm(s) compared); the control stays")
        return {"winner": control["name"], "adopted": False, "comparisons": comparisons, "rationale": why}
    arm, test = max(better, key=lambda t: t[0]["exact"])
    why = (
        f"{arm['name']} ({arm['exact']:.3f}) beats {control['name']} ({control['exact']:.3f}) "
        f"with p = {test['exact_p']:.4f}"
    )
    return {"winner": arm["name"], "adopted": True, "comparisons": comparisons, "rationale": why}


def select_finalist(winner, finalist, size_order, margin=MARGIN, level=LEVEL):
    """A finalist (e.g. the 270M full fine-tune) replaces the adapter winner only on these terms."""
    test = compare(finalist, winner)
    smaller = size_order.index(finalist["base"]) < size_order.index(winner["base"])
    if finalist["exact"] > winner["exact"] and test["exact_p"] < level:
        take, why = True, f"{finalist['name']} is significantly better than {winner['name']} (p = {test['exact_p']:.4f})"
    elif smaller and winner["exact"] - finalist["exact"] <= margin and test["exact_p"] >= level:
        take, why = True, (
            f"{finalist['name']} is a smaller model within {margin:.2f} of {winner['name']} and not significantly worse"
        )
    else:
        take, why = False, (
            f"{finalist['name']} does not displace {winner['name']}: {finalist['exact']:.3f} vs {winner['exact']:.3f}, "
            f"{test['a_only_correct']} vs {test['b_only_correct']} discordant notes, exact p = {test['exact_p']:.3f}; "
            f"the incumbent is kept unless the finalist is better with p < {level}"
        )
    return {"winner": finalist["name"] if take else winner["name"], "adopted": take, "comparisons": [test], "rationale": why}


def choose_decoding(free_exact, constrained_exact, backend):
    if constrained_exact is None or backend in (None, "none"):
        return "off", "constrained decoding was not available or not evaluated; unconstrained decoding is used"
    if constrained_exact > free_exact:
        return "auto", f"constrained decoding ({backend}) is higher on validation: {constrained_exact:.3f} vs {free_exact:.3f}"
    return "off", f"constrained decoding ({backend}) is not higher on validation: {constrained_exact:.3f} vs {free_exact:.3f}"


def holm(pvalues):
    """Holm-adjusted p-values, in the input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


# ---- time budget -------------------------------------------------------------------------------------


class Budget:
    def __init__(self, minutes, clock=time.monotonic):
        self.total = minutes * 60.0
        self.clock = clock
        self.start = clock()

    def elapsed(self):
        return self.clock() - self.start

    def remaining(self):
        return self.total - self.elapsed()


class Estimator:
    """Durations predicted from runs measured in this session; None until something is measured."""

    def __init__(self):
        self.step = {}  # base -> seconds per optimisation step of a plain LoRA run
        self.fixed = {}  # base -> encode + load + validation-loss seconds
        self.note = {}  # base -> generation seconds per note

    @staticmethod
    def factor(cfg):
        f = 1.0
        if cfg["method"] == "dora":
            f *= PLANNING_FACTORS["dora"]
        if cfg["gradient_checkpointing"]:
            f *= PLANNING_FACTORS["gradient_checkpointing"]
        if cfg["batch_size"] < 8:
            f *= PLANNING_FACTORS["small_batch"]
        return f

    def observe(self, result):
        if not result or result.get("status") not in ("ok", "time_cap") or "train" not in result:
            return
        cfg, base = result["config"], result["config"]["base"]
        per_step = result["train"].get("seconds_per_step")
        if per_step:
            self.step[base] = per_step / self.factor(cfg)
        s = result.get("seconds", {})
        self.fixed[base] = s.get("encode", 0) + s.get("load", 0) + s.get("eval_loss", 0)
        per_note = result["val"]["decoding"].get("seconds_per_note") if "val" in result else None
        if per_note:
            self.note[base] = per_note

    def _value(self, table, base):
        if base in table:
            return table[base], "measured"
        if not table:
            return None, None
        params = cfgmod.BASES[base]["parameters"]
        ref = min(table, key=lambda b: abs(cfgmod.BASES[b]["parameters"] - params))
        scaled = table[ref] * params / cfgmod.BASES[ref]["parameters"]
        return scaled, f"extrapolated from {ref} by parameter count"

    def train_seconds(self, cfg, n_val):
        cfg = cfg.to_dict() if hasattr(cfg, "to_dict") else cfg
        step, b1 = self._value(self.step, cfg["base"])
        fixed, _ = self._value(self.fixed, cfg["base"])
        note, _ = self._value(self.note, cfg["base"])
        if step is None or fixed is None or note is None:
            return None, None
        return step * self.factor(cfg) * cfg["max_steps"] + fixed + note * n_val, b1

    def eval_seconds(self, base, n_notes, slow=1.0):
        fixed, b1 = self._value(self.fixed, base)
        note, _ = self._value(self.note, base)
        if fixed is None or note is None:
            return None, None
        return fixed + note * n_notes * slow, b1


# ---- the staged run ----------------------------------------------------------------------------------


def run_summary(result):
    """What the ablation file keeps of one run (the full result stays in the run directory)."""
    out = {k: result.get(k) for k in ("config", "config_id", "description", "status", "eligible", "error", "smoke")}
    out["serving_notes"] = result.get("serving_notes")
    out["loss_path"] = (result.get("loss_path") or {}).get("path")
    out["adapter"] = result.get("adapter")
    if "train" in result:
        t = result["train"]
        out["train"] = {
            k: t.get(k)
            for k in (
                "global_step",
                "planned_steps",
                "time_cap_hit",
                "train_seconds",
                "seconds_per_step",
                "approx_tokens_per_second",
                "calibration_first_20_steps",
                "peak_gpu_memory_bytes",
                "final_eval_loss",
                "eval_loss_curve",
            )
        }
    if "val" in result:
        m = result["val"]["metrics"]
        out["val"] = {
            k: m.get(k)
            for k in (
                "n",
                "note_exact_match",
                "event_f1",
                "event_precision",
                "event_recall",
                "route_accuracy",
                "invalid_output",
                "stopped",
                "by_writer",
                "by_kind",
                "outcomes",
            )
        }
        out["val"]["by_split"] = result["val"].get("by_split")
        out["val"]["decoding"] = result["val"].get("decoding")
    out["seconds"] = result.get("seconds")
    out["artifacts"] = result.get("artifacts")
    out["oom_retries"] = result.get("oom_retries")
    out["reused"] = result.get("reused", False)
    return out


class Ablation:
    """The stages, with training and evaluation injected so that the logic is testable without a GPU.

    train_fn(config, max_minutes) -> run result (as written by train.py)
    eval_fn(system, splits, constrained, frozen_path) -> evaluation result (as written by evaluate.py)
    """

    def __init__(self, settings, train_fn, eval_fn, clock=time.monotonic, save_fn=None):
        self.s = settings
        self.train_fn = train_fn
        self.eval_fn = eval_fn
        self.save_fn = save_fn
        self.budget = Budget(settings["budget_minutes"], clock)
        self.estimator = Estimator()
        self.results = {}  # name -> full run result
        self.frozen = False
        self.out = {
            "schema": "scribe-v2-ablation-v1",
            "synthetic": True,
            "status": "in_progress",
            "started_utc": utc_now(),
            "host": socket.gethostname(),
            "versions": versions(),
            "bases": {k: {"repo": v["repo"], "revision": v["revision"]} for k, v in cfgmod.BASES.items()},
            "licence": "ungated Unsloth mirrors of Gemma 3, used under the Gemma Terms of Use "
                       "(https://ai.google.dev/gemma/terms) and the Gemma Prohibited Use Policy "
                       "(https://ai.google.dev/gemma/prohibited_use_policy)",
            "budget": {"minutes": settings["budget_minutes"]},
            "protocol": {
                "steps": settings["steps"],
                "effective_batch": 16,
                "seed": cfgmod.SEED,
                "selection_metric": "note-level exact match on the validation notes (all available writers pooled)",
                "size_rule": f"highest; smaller size if within {MARGIN} and McNemar p >= {LEVEL}",
                "arm_rule": f"replace the control only if better with McNemar p < {LEVEL} (unadjusted)",
                "decoding_rule": "constrained only if strictly higher validation exact match",
                "budget_claim_order": "A sizes small to large, A extras, B arms in listed order, C format, C data",
                "final_phase_sacrifice_order": "constrained-decoding check, version-1 recipe, zero-shot base",
                "reserve_rule": "while arms are planned, only the never-sacrificed part of the final phase is reserved "
                                "(test of the selected configuration, plus its final run if it must be retrained)",
                "planning_factors": PLANNING_FACTORS,
                "risk": {"alphas": list(risk.ALPHAS), "delta": risk.DELTA, "primary_method": "fixed_sequence"},
            },
            "data": settings.get("data", {}),
            "runs": {},
            "stages": {},
            "dropped": [],
            "planning": [],
            "selection": None,
            "final": None,
            "test": None,
            "risk_control": None,
            "notes": list(settings.get("notes", [])),
        }

    # ---- bookkeeping ----
    def save(self):
        self.out["budget"]["elapsed_seconds"] = self.budget.elapsed()
        if self.save_fn:
            self.save_fn(self.out)

    def drop(self, stage, item, reason, estimate=None, basis=None):
        self.out["dropped"].append(
            {"stage": stage, "item": item, "reason": reason, "estimate_seconds": estimate, "estimate_basis": basis}
        )
        self.save()

    def n_test(self):
        return sum(self.s["n_test"].values())

    def record(self, result):
        name = result["config"]["name"]
        self.results[name] = result
        self.out["runs"][name] = run_summary(result)
        self.estimator.observe(result)
        self.save()

    # ---- estimates ----
    def final_phase(self, base, final_needed=True, v1=True, decoding=True, zero_shot=True):
        """Estimated seconds of the final phase if `base` is selected; None before any measurement."""
        parts = {}
        test, _ = self.estimator.eval_seconds(base, self.n_test())
        if test is None:
            return None, {}
        parts["test_selected"] = test
        if final_needed:
            parts["final_run"], _ = self.estimator.train_seconds(self.candidate(base), self.s["n_val"])
        if decoding:
            parts["decoding_check"], _ = self.estimator.eval_seconds(base, self.s["n_val"])
        if zero_shot:
            parts["zero_shot"], _ = self.estimator.eval_seconds(
                base, self.n_test(), PLANNING_FACTORS["zero_shot_generation"]
            )
        if v1:
            v1_cfg = cfgmod.v1_recipe(self.v1_base(base), self.s["steps"])
            train, _ = self.estimator.train_seconds(v1_cfg, self.s["n_val"])
            test_v1, _ = self.estimator.eval_seconds(v1_cfg.base, self.n_test())
            parts["v1_recipe"] = (train or 0) + (test_v1 or 0)
        parts = {k: v for k, v in parts.items() if v is not None}
        return sum(parts.values()), parts

    def candidate(self, base):
        return cfgmod.control(base, self.s["steps"])

    def v1_base(self, selected_base):
        """Version 1 trained the 4B model: use that size once it has been measured in this session,
        otherwise the selected size (a recipe comparison at equal size)."""
        wanted = self.s["v1_base"]
        return wanted if wanted in self.estimator.step else selected_base

    def reserve(self, base):
        """Seconds held back while ablation arms are planned: only what is never sacrificed, i.e. the test
        of the selected configuration (and its final run when it must be retrained). The decoding check,
        the version-1 recipe and the zero-shot base are sacrificed first and run only on time that is left
        (review finding 2: reserving them dropped every Stage B/C arm, and the zero-shot base was then
        dropped anyway)."""
        # The final run costs nothing when the selected configuration was already trained identically.
        retrain = bool(self.s["final_steps"] or self.s["retrain_final"])
        estimate, parts = self.final_phase(base, final_needed=retrain, v1=False, decoding=False, zero_shot=False)
        if estimate is None:
            return RESERVE_FRACTION_UNMEASURED * self.budget.total, "share of the budget (nothing measured yet)"
        return estimate, "never-sacrificed final phase: " + ", ".join(f"{k} {v:.0f}s" for k, v in parts.items())

    # ---- running one optional item ----
    def attempt(self, stage, cfg, reserve_base):
        estimate, basis = self.estimator.train_seconds(cfg, self.s["n_val"])
        reserve, reserve_basis = self.reserve(reserve_base)
        left = self.budget.remaining() - reserve
        plan = {
            "stage": stage,
            "item": cfg.name,
            "estimate_seconds": estimate,
            "estimate_basis": basis,
            "reserve_seconds": reserve,
            "reserve_basis": reserve_basis,
            "seconds_left_after_reserve": left,
        }
        self.out["planning"].append(plan)
        if not self.estimator.step:
            # Nothing has been measured yet (first run, or every run so far failed): this run always
            # happens and is never cut short, otherwise there would be no result and no estimate at all.
            cap = 0.0
        elif estimate is None or estimate > left:
            reason = (
                "no estimate is available"
                if estimate is None
                else f"estimated {estimate:.0f}s ({basis}) does not fit in {left:.0f}s left after reserving "
                f"{reserve:.0f}s for the final phase"
            )
            self.drop(stage, cfg.name, reason, estimate, basis)
            return None
        else:
            cap = left
        plan["training_cap_minutes"] = cap / 60
        result = self.train_fn(cfg, cap / 60)
        self.record(result)
        if not eligible(result):
            self.out["notes"].append(
                f"{cfg.name}: status {result.get('status')!r}; not eligible for selection ({result.get('error') or 'incomplete'})"
            )
        return result

    # ---- stages ----
    def stage_a(self):
        arms = cfgmod.stage_a(self.s["sizes"], self.s["steps"], self.s["extras"])
        ladder = [a for a in arms if a.method == "lora" and a.rank == 16]
        extras = [a for a in arms if a not in ladder]
        done = []
        for cfg in ladder + extras:
            largest = max([cfgmod.SIZE_LADDER.index(r["config"]["base"]) for r in done] + [cfgmod.SIZE_LADDER.index(cfg.base)])
            result = self.attempt("A", cfg, cfgmod.SIZE_LADDER[largest])
            if result:
                done.append(result)
        views = [val_view(self.results[c.name]) for c in ladder if eligible(self.results.get(c.name))]
        if not views:
            raise RuntimeError("Stage A produced no eligible run; nothing can be selected")
        selection = select_size(views)
        finalists = [c.name for c in extras if eligible(self.results.get(c.name))]
        self.out["stages"]["A"] = {
            "arms": [c.name for c in ladder + extras],
            "ladder": [c.name for c in ladder],
            "finalists": finalists,
            "selection": selection,
        }
        self.save()
        return next(c for c in ladder if c.name == selection["winner"]), finalists

    def one_factor_stage(self, key, control_cfg, arms):
        control = val_view(self.results[control_cfg.name])
        ran = []
        for cfg in arms:
            if self.attempt(key, cfg, control_cfg.base) and eligible(self.results[cfg.name]):
                ran.append(cfg)
        selection = select_arm(control, [val_view(self.results[c.name]) for c in ran])
        self.out["stages"][key] = {
            "control": control_cfg.name,
            "arms": [c.name for c in arms],
            "arms_completed": [c.name for c in ran],
            "changes": {c.name: {k: list(v) for k, v in cfgmod.diff(control_cfg, c).items()} for c in arms},
            "selection": selection,
        }
        self.save()
        return next((c for c in ran if c.name == selection["winner"]), control_cfg)

    def stage_c(self, best):
        ok, why = self.s["expression_available"]
        if ok:
            best = self.one_factor_stage("C_format", best, [cfgmod.stage_c_format(best)])
        else:
            self.drop("C_format", "C-format-expression", f"expression format unavailable: {why}")
        ok, why = self.s["haiku_train_available"]
        if ok:
            arm = cfgmod.stage_c_data(best)
            if best.output_format == "expression":
                arm = arm.with_(name="C-data-nemotron+haiku-expression")
            best = self.one_factor_stage("C_data", best, [arm])
        else:
            self.drop("C_data", "C-data-nemotron+haiku", f"Haiku-written training notes unavailable: {why}")
        return best

    def finalists(self, best, names):
        for name in names:
            winner, finalist = val_view(self.results[best.name]), val_view(self.results[name])
            selection = select_finalist(winner, finalist, list(cfgmod.SIZE_LADDER))
            self.out["stages"].setdefault("finalists", []).append(selection)
            if selection["adopted"]:
                best = cfgmod.RunConfig.from_dict(self.results[name]["config"])
        self.save()
        return best

    # ---- final phase ----
    def final_run(self, best):
        final_cfg = best.with_(name="final-selected", max_steps=self.s["final_steps"] or best.max_steps)
        twin = next(
            (
                r
                for r in self.results.values()
                if eligible(r) and recipe_of(r) == final_cfg.recipe_id and (r.get("artifacts") or {}).get("saved")
            ),
            None,
        )
        if twin and not self.s["retrain_final"]:
            self.out["final"] = {
                "run": twin["config"]["name"],
                "reused": True,
                "note": "the selected configuration was already trained with identical settings and seed; that run is the final run",
            }
            self.save()
            return twin
        result = self.train_fn(final_cfg, 0.0)  # the final run has no time cap
        self.record(result)
        if not eligible(result):
            raise RuntimeError(f"the final run failed: {result.get('error') or result.get('status')}")
        self.out["final"] = {"run": final_cfg.name, "reused": False}
        self.save()
        return result

    def decoding_check(self, final):
        base = final["config"]["base"]
        estimate, basis = self.estimator.eval_seconds(base, self.s["n_val"])
        need, _ = self.estimator.eval_seconds(base, self.n_test())
        free = final["val"]["metrics"]
        if estimate is None or estimate + (need or 0) > self.budget.remaining():
            self.drop("final", "constrained-decoding check", "does not fit in the remaining budget", estimate, basis)
            return "off", {"chosen": "off", "rationale": "the check was dropped for time"}, free
        got = self.eval_fn({"run": final}, self.s["val_splits"], "auto", None)
        merged = merge_splits(got, self.s["val_splits"])
        # Like-for-like baseline (review finding 3): the unconstrained arm goes through the same evaluator,
        # split layout and token cap as the constrained arm, not through train.py's in-process generation.
        if estimate + (need or 0) + estimate <= self.budget.remaining():
            same_path = merge_splits(self.eval_fn({"run": final}, self.s["val_splits"], "off", None), self.s["val_splits"])
            if same_path["ids"] == merged["ids"] and same_path["exact"] is not None:
                free = {"note_exact_match": {"value": same_path["exact"]}, "ids": same_path["ids"],
                        "outcomes": same_path["outcomes"], "confidences": same_path["confidences"],
                        "source": "evaluate.py, unconstrained, same splits and cap as the constrained arm"}
        backend = merged["backend"]
        mode, why = choose_decoding(free["note_exact_match"]["value"], merged["exact"], backend)
        info = {
            "chosen": mode,
            "rationale": why,
            "backend": backend,
            "backend_detail": merged["detail"],
            "validation_exact_match_unconstrained": free["note_exact_match"]["value"],
            "validation_exact_match_constrained": merged["exact"],
            "paired_test": compare(
                {"name": "constrained", "exact": merged["exact"], "ids": merged["ids"], "outcomes": merged["outcomes"]},
                {"name": "unconstrained", "exact": free["note_exact_match"]["value"], "ids": list(free["ids"]), "outcomes": list(free["outcomes"])},
            )
            if merged["ids"] == list(free["ids"])
            else None,
        }
        return mode, info, (merged if mode == "auto" else free)

    def v1_run(self, selected_base):
        cfg = None
        for base in dict.fromkeys([self.v1_base(selected_base), selected_base]):
            candidate = cfgmod.v1_recipe(base, self.s["final_steps"] or self.s["steps"])
            estimate, basis = self.estimator.train_seconds(candidate, self.s["n_val"])
            tests = sum(
                x or 0
                for x in (
                    self.estimator.eval_seconds(selected_base, self.n_test())[0],
                    self.estimator.eval_seconds(base, self.n_test())[0],
                )
            )
            left = self.budget.remaining() - tests
            if estimate is not None and estimate <= left:
                cfg = candidate
                break
            self.drop(
                "final",
                candidate.name,
                f"estimated {estimate and round(estimate)}s does not fit in {left:.0f}s left after the test evaluations",
                estimate,
                basis,
            )
        if cfg is None:
            return None
        if cfg.base != self.s["v1_base"]:
            self.out["notes"].append(
                f"the version-1 recipe was run on {cfg.base}, not on {self.s['v1_base']} as in version 1 "
                "(that size was not measured in this session or did not fit the budget)"
            )
        result = self.train_fn(cfg, max(1.0, left / 60))
        self.record(result)
        if not eligible(result) or not (result.get("artifacts") or {}).get("saved"):
            self.out["notes"].append(f"{cfg.name}: status {result.get('status')!r}; excluded from the test comparison")
            return None
        return result

    def freeze(self, final, decoding, decoding_info, rationale):
        selection = {
            "frozen": True,
            "frozen_utc": utc_now(),
            "config": final["config"],
            "config_id": final["config_id"],
            "description": final.get("description"),
            "run": final["config"]["name"],
            "decoding": decoding,
            "decoding_check": decoding_info,
            "rationale": rationale,
            "validation_exact_match": final["val"]["metrics"]["note_exact_match"],
            "serving_notes": final.get("serving_notes"),
        }
        self.out["selection"] = selection
        self.frozen = True
        self.save()
        return selection

    def test_phase(self, final, v1, decoding, calibration):
        if not self.frozen:
            raise RuntimeError("test data may not be touched before the selection is frozen")
        splits = self.s["test_splits"]
        systems = {"selected": {"run": final}}
        base = final["config"]["base"]
        estimate, basis = self.estimator.eval_seconds(base, self.n_test(), PLANNING_FACTORS["zero_shot_generation"])
        selected_first, _ = self.estimator.eval_seconds(base, self.n_test())
        if estimate is not None and estimate + (selected_first or 0) <= self.budget.remaining():
            systems["base_zero_shot"] = {"base": base, "max_new_tokens": final.get("max_new_tokens")}
        else:
            self.drop("final", "zero-shot base on test", "does not fit in the remaining budget", estimate, basis)
        if v1:
            systems["v1_recipe"] = {"run": v1}
        evaluated = {}
        for label, system in systems.items():
            got = self.eval_fn(system, splits, decoding, self.s["frozen_path"])
            evaluated[label] = {
                "system": got.get("system"),
                "splits": {name: test_summary(block) for name, block in got["splits"].items()},
                "pooled": merge_splits(got, splits),
            }
        tests = []
        for a, b in (("selected", "base_zero_shot"), ("selected", "v1_recipe"), ("v1_recipe", "base_zero_shot")):
            if a not in evaluated or b not in evaluated:
                continue
            for name in list(splits) + ["pooled"]:
                va, vb = (
                    (evaluated[x]["pooled"] if name == "pooled" else evaluated[x]["splits"][name]) for x in (a, b)
                )
                test = compare(
                    {"name": a, "exact": va["exact"], "ids": va["ids"], "outcomes": va["outcomes"]},
                    {"name": b, "exact": vb["exact"], "ids": vb["ids"], "outcomes": vb["outcomes"]},
                )
                tests.append(dict(test, split=name))
        for test, adjusted in zip(tests, holm([t["exact_p"] for t in tests])):
            test["holm_adjusted_p"] = adjusted
        self.out["test"] = {"decoding": decoding, "systems": evaluated, "mcnemar": tests}
        selected = evaluated["selected"]
        checks = {
            name: ([c for c in block["confidences"]], [not o for o in block["outcomes"]])
            for name, block in list(selected["splits"].items()) + [("pooled", selected["pooled"])]
        }
        control = risk.calibrate_and_check(
            calibration["confidences"], [not o for o in calibration["outcomes"]], checks
        )
        control["calibration_split"] = "validation notes of the selected system under the frozen decoding"
        control["caveat"] = (
            "the validation notes were also used to select the configuration, so they are not a fresh "
            "calibration sample; the fixed_sequence result is the pre-registered one, and picking whichever "
            "of the two methods accepts more after seeing both weakens the guarantee to 1 - 2*delta"
        )
        self.out["risk_control"] = control
        self.save()

    def run(self):
        size_cfg, finalists = self.stage_a()
        best = self.one_factor_stage("B", size_cfg, cfgmod.stage_b(size_cfg, self.s["with_eva"]))
        best = self.stage_c(best)
        best = self.finalists(best, finalists)
        rationale = [f"Stage {k}: " + s["selection"]["rationale"] for k, s in self.out["stages"].items() if k != "finalists"]
        rationale += [s["rationale"] for s in self.out["stages"].get("finalists", [])]
        final = self.final_run(best)
        decoding, decoding_info, calibration_view = self.decoding_check(final)
        calibration = {
            "confidences": list(calibration_view["confidences"]),
            "outcomes": list(calibration_view["outcomes"]),
        }
        v1 = self.v1_run(final["config"]["base"])
        self.freeze(final, decoding, decoding_info, rationale)
        self.test_phase(final, v1, decoding, calibration)
        self.out["status"] = "complete"
        self.out["finished_utc"] = utc_now()
        self.out["budget"]["over_budget"] = self.budget.remaining() < 0
        self.save()
        return self.out


def test_summary(block):
    m = block["metrics"]
    keep = (
        "n",
        "note_exact_match",
        "event_f1",
        "event_precision",
        "event_recall",
        "route_accuracy",
        "invalid_output",
        "distractor_extraction",
        "stopped",
        "parse_modes",
        "by_writer",
        "by_kind",
        "by_date_form",
    )
    # No risk_coverage here: evaluate.score picks that threshold on the same notes it reports on, which is
    # an in-sample figure; the held-out check is risk_control (review finding 6).
    out = {k: m.get(k) for k in keep}
    out["unparsable_by_cause"] = unparsable_by_cause(block)
    out.update(
        exact=m["note_exact_match"]["value"],
        ids=list(m["ids"]),
        outcomes=list(m["outcomes"]),
        confidences=list(m["confidences"]),
        constraint=block["decoding"]["constraint"],
        seconds=block["decoding"].get("seconds"),
    )
    return out


def unparsable_by_cause(block):
    """Unparsable answers split into 'cut at the generation cap' (never stopped, used every allowed new
    token) and 'malformed' (the model stopped, the text is not a valid answer). Review finding 4."""
    records = block.get("records")
    if records is None:
        return None
    cap = (block.get("decoding") or {}).get("max_new_tokens")
    bad = [r for r in records if r.get("prediction") is None]
    cut = [r for r in bad if not r.get("stopped") and cap is not None and (r.get("tokens") or 0) >= cap]
    return {"n": len(records), "unparsable": len(bad), "cut_at_cap": len(cut), "malformed": len(bad) - len(cut),
            "max_new_tokens": cap}


def merge_splits(evaluation, splits):
    """Pool the per-split outcomes of one evaluation (ids, outcomes, confidences, exact match)."""
    ids, outcomes, confidences, backends, details = [], [], [], set(), []
    for name in splits:
        block = evaluation["splits"][name]
        m = block["metrics"]
        ids += list(m["ids"])
        outcomes += [bool(x) for x in m["outcomes"]]
        confidences += list(m["confidences"])
        backends.add(block["decoding"]["constraint"]["backend"])
        details.append(block["decoding"]["constraint"].get("detail", ""))
    return {
        "n": len(ids),
        "exact": sum(outcomes) / len(outcomes) if outcomes else None,
        "ids": ids,
        "outcomes": outcomes,
        "confidences": confidences,
        "backend": backends.pop() if len(backends) == 1 else "mixed",
        "detail": "; ".join(sorted(set(d for d in details if d))),
    }


# ---- real training and evaluation (subprocesses) ------------------------------------------------------


class Runner:
    def __init__(self, artifacts, extra_train=(), extra_eval=(), resume=False, python=sys.executable, expected_val=None):
        self.expected_val = expected_val  # validation splits of this session; a resumed run must match them
        self.artifacts = pathlib.Path(artifacts)
        self.extra_train = list(extra_train)
        self.extra_eval = list(extra_eval)
        self.resume = resume
        self.python = python

    def _call(self, cmd, log_path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"\n$ {' '.join(cmd)}\n")
            f.flush()
            return subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode

    def train(self, cfg, max_minutes):
        tries, retries = 0, []
        while True:
            out_dir = self.artifacts / f"{cfg.name}-{cfg.config_id}"
            result_path = out_dir / "result.json"
            if self.resume and result_path.exists():
                previous = load_json(result_path)
                same_notes = self.expected_val is None or (previous.get("data") or {}).get("val") == self.expected_val
                if recipe_of(previous) == cfg.recipe_id and eligible(previous) and same_notes:
                    previous["reused"] = True
                    return previous
            out_dir.mkdir(parents=True, exist_ok=True)
            if result_path.exists():
                result_path.unlink()
            save_json(out_dir / "config.json", cfg.to_dict())
            cmd = [
                self.python,
                str(_paths.V2 / "train.py"),
                "--config-json",
                str(out_dir / "config.json"),
                "--out",
                str(out_dir),
                "--max-minutes",
                f"{max_minutes:.2f}",
            ] + self.extra_train
            code = self._call(cmd, out_dir / "train.log")
            if result_path.exists():
                result = load_json(result_path)
            else:
                result = {
                    "config": cfg.to_dict(),
                    "config_id": cfg.config_id,
                    "status": "error",
                    "eligible": False,
                    "error": f"train.py exited with code {code} and wrote no result; see {out_dir / 'train.log'}",
                }
            result["oom_retries"] = retries
            if result.get("status") == "oom" and cfg.batch_size > 1 and tries < 2:
                tries += 1
                retries.append({"batch_size": cfg.batch_size, "grad_accum": cfg.grad_accum})
                cfg = cfg.with_(batch_size=cfg.batch_size // 2, grad_accum=cfg.grad_accum * 2)  # same effective batch
                continue
            return result

    def evaluate(self, system, splits, constrained_mode, frozen_path):
        if "run" in system:
            run_dir = pathlib.Path(system["run"]["artifacts"]["saved"]["path"]).parent
            spec, label = f"run:{run_dir}", system["run"]["config"]["name"]
        else:
            spec, label = f"base:{system['base']}", f"base-{system['base']}"
        out = self.artifacts / "evaluations" / f"{label}--{'+'.join(splits)}--{constrained_mode}.json"
        cmd = [
            self.python,
            str(_paths.V2 / "evaluate.py"),
            "--system",
            spec,
            "--splits",
            ",".join(splits),
            "--constrained",
            constrained_mode,
            "--out",
            str(out),
        ] + self.extra_eval
        if frozen_path:
            cmd += ["--selection-frozen", str(frozen_path)]
        if system.get("max_new_tokens"):  # the zero-shot base gets the same generation cap as the selected run
            cmd += ["--max-new-tokens", str(system["max_new_tokens"])]
        code = self._call(cmd, self.artifacts / "evaluations" / "evaluate.log")
        if code != 0 or not out.exists():
            raise RuntimeError(f"evaluate.py failed with code {code}; see {self.artifacts / 'evaluations' / 'evaluate.log'}")
        return load_json(out)


def preflight(sizes):
    """What data and formats exist right now; nothing here needs a GPU."""
    data, notes = {}, []
    val_sets, val_sources = data_iface.heldout_rows("val")
    test_sets, test_sources = data_iface.heldout_rows("test")
    data["val"], data["test"] = val_sources, test_sources
    if not val_sets:
        raise RuntimeError("no validation split is available")
    if not test_sets:
        raise RuntimeError("no test split is available")
    train_rows, train_sources = data_iface.training_rows("nemotron")
    data["train"] = dict(train_sources)
    heldout = [r for rows in list(val_sets.values()) + list(test_sets.values()) for r in rows]
    data_iface.assert_disjoint(train_rows, heldout, "validation and test")
    try:
        haiku_rows, haiku_sources = data_iface.load_split("train_haiku")
        data_iface.assert_disjoint(haiku_rows, heldout, "validation and test")
        data["train"]["train_haiku"] = {"rows": len(haiku_rows), "source": haiku_sources}
        haiku = (True, "")
    except data_iface.SplitUnavailable as e:
        haiku = (False, str(e))
    for name in data_iface.TEST_SPLITS:
        if name not in test_sets:
            notes.append(f"{name} is not available and is not evaluated")
    return {
        "data": data,
        "notes": notes,
        "n_val": sum(len(r) for r in val_sets.values()),
        "n_test": {k: len(v) for k, v in test_sets.items()},
        "val_splits": list(val_sets),
        "test_splits": list(test_sets),
        "expression_available": formats.available("expression", train_rows[:200]),
        "haiku_train_available": haiku,
    }


def main():
    p = argparse.ArgumentParser(description="Staged scribe ablation under a wall-clock budget (never selects on test).")
    p.add_argument("--time-budget-min", type=float, required=True)
    p.add_argument("--steps", type=int, default=cfgmod.DEFAULT_STEPS, help="optimisation steps of every ablation run")
    p.add_argument("--final-steps", type=int, default=0, help="steps of the final run (default: same as --steps)")
    p.add_argument("--retrain-final", action="store_true", help="train the final run even if an identical run exists")
    p.add_argument("--sizes", default=",".join(cfgmod.SIZE_LADDER))
    p.add_argument("--stage-a-extras", default="270m_full", help="comma-separated: 270m_full,270m_lora_r128 or empty")
    p.add_argument("--with-eva", action="store_true", help="add the EVA initialisation arm to Stage B")
    p.add_argument("--v1-base", default="4b", help="size for the version-1 recipe (falls back to the selected size)")
    p.add_argument("--out", default=str(ABLATION_JSON))
    p.add_argument("--results-md", default=str(RESULTS_MD))
    p.add_argument("--artifacts", default=str(ARTIFACTS))
    p.add_argument("--resume", action="store_true", help="reuse finished runs found in the artifacts directory")
    p.add_argument("--plan", action="store_true", help="print the planned arms and data availability, then exit")
    p.add_argument("--smoke-tokenizer", default=None, help="wiring test on CPU with tiny random models")
    p.add_argument("--limit-train", type=int, default=0)
    p.add_argument("--limit-val", type=int, default=0)
    p.add_argument("--limit-test", type=int, default=0)
    args = p.parse_args()

    sizes = tuple(s for s in args.sizes.split(",") if s)
    extras = tuple(s for s in args.stage_a_extras.split(",") if s)
    found = preflight(sizes)
    settings = dict(
        found,
        budget_minutes=args.time_budget_min,
        steps=args.steps,
        final_steps=args.final_steps,
        retrain_final=args.retrain_final,
        sizes=sizes,
        extras=extras,
        with_eva=args.with_eva,
        v1_base=args.v1_base,
        frozen_path=str(pathlib.Path(args.artifacts) / "selection-frozen.json"),
    )
    if args.limit_val:
        settings["n_val"] = sum(min(info["rows"], args.limit_val) for info in settings["data"]["val"].values())
    if args.limit_test:
        settings["n_test"] = {k: min(v, args.limit_test) for k, v in settings["n_test"].items()}
    if args.plan:
        arms = cfgmod.stage_a(sizes, args.steps, extras)
        print("Stage A:", *[f"  {a.name}: {cfgmod.describe(a)}" for a in arms], sep="\n")
        print("Stage B (on the chosen size):", *[f"  {a.name}: {cfgmod.describe(a)}" for a in cfgmod.stage_b(arms[0], args.with_eva)], sep="\n")
        print("Stage C: expression format", settings["expression_available"], "| Haiku training notes", settings["haiku_train_available"])
        print("Data:", settings["data"])
        return

    smoke = bool(args.smoke_tokenizer)
    if smoke and pathlib.Path(args.out).resolve() == ABLATION_JSON.resolve():
        p.error("a wiring test must not write the real result file; pass --out, --results-md and --artifacts elsewhere")
    extra_train, extra_eval = [], []
    if smoke:
        # Batch 2 with accumulation 8 keeps the effective batch of 16, so the recipe (and with it the
        # reuse of finished runs) is the same as on a GPU; only the split differs, as after an OOM retry.
        extra_train += ["--smoke-tokenizer", args.smoke_tokenizer, "--batch-size", "2", "--grad-accum", "8", "--eval-batch-size", "2"]
        extra_eval += ["--smoke-tokenizer", args.smoke_tokenizer, "--batch-size", "2"]
    if args.limit_train:
        extra_train += ["--limit-train", str(args.limit_train)]
    if args.limit_val:
        extra_train += ["--limit-val", str(args.limit_val)]
    runner = Runner(args.artifacts, extra_train, extra_eval, args.resume, expected_val=settings["data"]["val"])
    limit_val, limit_test = args.limit_val, args.limit_test

    def eval_fn(system, splits, constrained_mode, frozen_path):
        limit = limit_test if any(s.startswith("test") for s in splits) else limit_val
        runner.extra_eval = extra_eval + (["--limit", str(limit)] if limit else [])
        return runner.evaluate(system, splits, constrained_mode, frozen_path)

    out_path, md_path = pathlib.Path(args.out), pathlib.Path(args.results_md)

    def save_fn(out):
        out["smoke"] = smoke
        if out.get("selection") and out["selection"].get("frozen"):
            save_json(settings["frozen_path"], out["selection"])
        save_json(out_path, out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(report.render(out))

    frozen = pathlib.Path(settings["frozen_path"])
    if frozen.exists():
        frozen.unlink()  # a selection frozen by an earlier session must not unlock the test notes for this one
    ablation = Ablation(settings, runner.train, eval_fn, save_fn=save_fn)
    if not smoke:
        log("v2_ablation_start", command=" ".join(sys.argv), inputs={k: settings[k] for k in ("budget_minutes", "steps", "sizes", "extras")})
    try:
        out = ablation.run()
    except Exception as e:
        ablation.out["status"] = "failed"
        ablation.out["error"] = f"{type(e).__name__}: {e}"
        ablation.out["finished_utc"] = utc_now()
        ablation.save()
        if not smoke:
            log("v2_ablation", command=" ".join(sys.argv), outputs=[str(out_path)], metrics={"error": str(e)[:300]}, status="error")
        raise
    if not smoke:
        selected = out["test"]["systems"]["selected"]["pooled"]
        log(
            "v2_ablation",
            command=" ".join(sys.argv),
            outputs=[str(out_path), str(md_path)],
            metrics={
                "selected": out["selection"]["description"],
                "test_exact_match_pooled": selected["exact"],
                "test_n_pooled": selected["n"],
                "runs": len(out["runs"]),
                "dropped": len(out["dropped"]),
                "elapsed_seconds": out["budget"]["elapsed_seconds"],
            },
        )
    print(f"wrote {out_path} and {md_path}")


if __name__ == "__main__":
    main()
