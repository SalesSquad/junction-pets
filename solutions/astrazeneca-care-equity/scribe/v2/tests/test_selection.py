import unittest

import fakes
import config as cfgmod
import run_ablation as ra

N_VAL = 250


class Guarded(dict):
    """A run result that fails the test the moment anything reads a key that starts with 'test'."""

    def __getitem__(self, key):
        if str(key).startswith("test"):
            raise AssertionError(f"selection code read {key!r}")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if str(key).startswith("test"):
            raise AssertionError(f"selection code read {key!r}")
        return super().get(key, default)


def exact_for(cfg):
    """A made-up world: validation exact match of every configuration."""
    value = {"270m": 0.60, "1b": 0.80, "4b": 0.86}[cfg.base]
    if cfg.method == "full":
        value = 0.66
    if cfg.method == "rslora" and cfg.rank == 64:
        value += 0.06
    if cfg.loraplus_ratio:
        value += 0.008
    if cfg.method == "dora":
        value -= 0.02
    if cfg.output_format == "expression":
        value += 0.05
    if cfg.dropout:
        value -= 0.04
    return value


class Lab:
    """Fake GPU: training and evaluation advance a fake clock and return made-up results."""

    SECONDS_PER_STEP = {"270m": 0.2, "1b": 0.6, "4b": 2.5}

    def __init__(self, clock, exact=exact_for, poison=None, guarded=True):
        self.clock, self.exact, self.poison, self.guarded = clock, exact, poison, guarded
        self.calls = []
        self.ablation = None

    def train(self, cfg, max_minutes):
        per_step = self.SECONDS_PER_STEP[cfg.base] * ra.Estimator.factor(cfg.to_dict())
        self.clock.advance(per_step * cfg.max_steps + 7 + 0.1 * N_VAL)
        self.calls.append(("train", cfg.name, self.ablation.frozen))
        value = self.exact(cfg)
        result = fakes.run_result(
            cfg,
            fakes.outcomes(N_VAL, round(value * N_VAL)),
            seconds_per_step=per_step,
            poison_test=None if self.poison is None else self.poison(value),
        )
        return Guarded(result) if self.guarded else result

    def evaluate(self, system, splits, constrained, frozen_path):
        label = system["run"]["config"]["name"] if "run" in system else f"base-{system['base']}"
        base = system["run"]["config"]["base"] if "run" in system else system["base"]
        n = sum(self.ablation.s["n_test"].values()) if splits[0].startswith("test") else N_VAL
        self.clock.advance(6 + 0.1 * n)
        self.calls.append(("eval", label, tuple(splits), constrained, frozen_path, self.ablation.frozen))
        spec = {"name": label, "base": base}
        if splits[0].startswith("val"):
            # Under the constraint one more validation note is right; unconstrained through the same
            # evaluator gives the training-time result (the like-for-like baseline of review finding 3).
            constrained_on = constrained == "auto"
            exact = self.exact(cfgmod.RunConfig.from_dict(system["run"]["config"])) + (0.004 if constrained_on else 0.0)
            block = fakes.eval_result(spec, splits, N_VAL, exact, backend="native-dfa" if constrained_on else "none")
            block["splits"][splits[0]]["metrics"]["ids"] = [f"val-{i:04d}" for i in range(N_VAL)]
            return block
        exact = 0.2 if "run" not in system else self.exact(cfgmod.RunConfig.from_dict(system["run"]["config"]))
        return fakes.eval_result(spec, splits, 40, exact)


def run(budget_minutes, **kwargs):
    lab_kwargs = {k: kwargs.pop(k) for k in ("exact", "poison", "guarded") if k in kwargs}
    clock = fakes.FakeClock()
    lab = Lab(clock, **lab_kwargs)
    ablation = ra.Ablation(fakes.settings(budget_minutes, **kwargs), lab.train, lab.evaluate, clock=clock)
    lab.ablation = ablation
    return ablation.run(), lab


def view(name, base, correct, shift=0, n=N_VAL):
    ok = fakes.outcomes(n, correct, shift)
    return {"name": name, "base": base, "exact": correct / n, "n": n, "ids": list(range(n)), "outcomes": ok}


class Rules(unittest.TestCase):
    def test_size_highest_wins_when_clearly_better(self):
        got = ra.select_size([view("s", "270m", 150), view("m", "1b", 200), view("l", "4b", 215)])
        self.assertEqual((got["winner"], got["best_by_exact_match"]), ("l", "l"))

    def test_size_smaller_wins_when_close_and_not_significantly_worse(self):
        # 5 notes apart (2 points), all discordant in one direction: exact McNemar p = 0.0625 >= 0.05.
        got = ra.select_size([view("m", "1b", 200), view("l", "4b", 205)])
        self.assertEqual((got["winner"], got["best_by_exact_match"]), ("m", "l"))
        self.assertAlmostEqual(got["comparisons"][0]["exact_p"], 0.0625)

    def test_size_smaller_loses_when_significantly_worse(self):
        # 6 notes apart: p = 0.03125 < 0.05, so the gap is treated as real although it is under 3 points.
        got = ra.select_size([view("m", "1b", 200), view("l", "4b", 206)])
        self.assertEqual(got["winner"], "l")

    def test_size_tie_goes_to_the_smaller_model(self):
        self.assertEqual(ra.select_size([view("m", "1b", 200), view("l", "4b", 200)])["winner"], "m")

    def test_arm_needs_a_significant_paired_gain(self):
        control = view("control", "1b", 200)
        small, big, bigger = view("small", "1b", 203), view("big", "1b", 212), view("bigger", "1b", 220)
        worse = view("worse", "1b", 180)
        self.assertEqual(ra.select_arm(control, [small, worse])["winner"], "control")
        self.assertFalse(ra.select_arm(control, [small])["adopted"])
        self.assertEqual(ra.select_arm(control, [small, big])["winner"], "big")
        self.assertEqual(ra.select_arm(control, [big, bigger, small])["winner"], "bigger")
        self.assertEqual(ra.select_arm(control, [])["winner"], "control")

    def test_arm_with_equal_score_but_different_notes_is_not_adopted(self):
        control = view("control", "1b", 200, shift=0)
        other = view("other", "1b", 200, shift=100)
        got = ra.select_arm(control, [other])
        self.assertEqual((got["winner"], got["comparisons"][0]["exact_p"]), ("control", 1.0))

    def test_comparison_needs_the_same_notes(self):
        a, b = view("a", "1b", 200), view("b", "1b", 200)
        b["ids"] = list(range(1, N_VAL + 1))
        with self.assertRaises(ValueError):
            ra.compare(a, b)

    def test_finalist(self):
        order = list(cfgmod.SIZE_LADDER)
        winner = view("adapter-4b", "4b", 215)
        self.assertEqual(ra.select_finalist(winner, view("full-270m", "270m", 165), order)["winner"], "adapter-4b")
        self.assertEqual(ra.select_finalist(winner, view("full-270m", "270m", 211), order)["winner"], "full-270m")
        self.assertEqual(ra.select_finalist(winner, view("full-270m", "270m", 235), order)["winner"], "full-270m")
        same_size = view("adapter-270m", "270m", 215)
        self.assertEqual(ra.select_finalist(same_size, view("full-270m", "270m", 213), order)["winner"], "adapter-270m")

    def test_decoding_and_holm(self):
        self.assertEqual(ra.choose_decoding(0.80, 0.81, "native-dfa")[0], "auto")
        self.assertEqual(ra.choose_decoding(0.80, 0.80, "native-dfa")[0], "off")
        self.assertEqual(ra.choose_decoding(0.80, 0.90, "none")[0], "off")
        self.assertEqual(ra.choose_decoding(0.80, None, "native-dfa")[0], "off")
        for got, want in zip(ra.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06]):
            self.assertAlmostEqual(got, want)

    def test_ineligible_runs_are_not_candidates(self):
        cfg = cfgmod.control("1b")
        self.assertTrue(ra.eligible(fakes.run_result(cfg, fakes.outcomes(10, 8))))
        self.assertFalse(ra.eligible(fakes.run_result(cfg, fakes.outcomes(10, 8), status="time_cap")))
        self.assertFalse(ra.eligible({"status": "error", "eligible": False}))
        self.assertFalse(ra.eligible(None))


class TestDataIsolation(unittest.TestCase):
    def test_selection_never_reads_test_metrics(self):
        # Results carry poisoned test metrics and raise if any 'test*' key is read before the freeze.
        out, lab = run(100000, poison=lambda v: 1 - v)
        clean, _ = run(100000, poison=None)
        other, _ = run(100000, poison=lambda v: 0.5)
        for key in ("config", "decoding", "rationale"):
            self.assertEqual(out["selection"][key], clean["selection"][key])
            self.assertEqual(out["selection"][key], other["selection"][key])
        self.assertEqual(out["stages"]["A"]["selection"]["winner"], clean["stages"]["A"]["selection"]["winner"])

    def test_val_view_exposes_validation_only(self):
        result = fakes.run_result(cfgmod.control("1b"), fakes.outcomes(N_VAL, 200), poison_test=0.0)
        self.assertEqual(set(ra.val_view(result)), {"name", "base", "exact", "n", "ids", "outcomes"})
        self.assertEqual(ra.val_view(result)["exact"], 0.8)

    def test_test_notes_are_read_once_and_only_after_the_freeze(self):
        out, lab = run(100000)
        evals = [c for c in lab.calls if c[0] == "eval"]
        on_test = [c for c in evals if c[2][0].startswith("test")]
        on_val = [c for c in evals if not c[2][0].startswith("test")]
        self.assertTrue(on_test)
        self.assertTrue(all(c[5] for c in on_test))  # the selection was frozen at call time
        self.assertTrue(all(c[4] for c in on_test))  # and the frozen file was handed to the evaluator
        self.assertTrue(all(not c[5] and c[4] is None for c in on_val))
        self.assertEqual(len({c[1] for c in on_test}), len(on_test))  # each system exactly once
        self.assertEqual(sorted(out["test"]["systems"]), ["base_zero_shot", "selected", "v1_recipe"])
        self.assertTrue(all(not frozen for kind, _, frozen in [c for c in lab.calls if c[0] == "train"]))
        first_test = lab.calls.index(on_test[0])
        self.assertTrue(all(c[0] == "eval" and c[2][0].startswith("test") for c in lab.calls[first_test:]))

    def test_test_phase_refuses_to_run_before_the_freeze(self):
        clock = fakes.FakeClock()
        lab = Lab(clock)
        ablation = ra.Ablation(fakes.settings(100000), lab.train, lab.evaluate, clock=clock)
        lab.ablation = ablation
        with self.assertRaisesRegex(RuntimeError, "frozen"):
            ablation.test_phase({}, None, "off", {"confidences": [], "outcomes": []})
        self.assertFalse(lab.calls)


class Stages(unittest.TestCase):
    def test_full_run_follows_the_rules(self):
        out, lab = run(100000)
        self.assertEqual(out["status"], "complete")
        self.assertEqual(out["dropped"], [])
        self.assertEqual(out["stages"]["A"]["selection"]["winner"], "A-4b-lora-r16")
        self.assertEqual(out["stages"]["A"]["finalists"], ["A-270m-full-finetune"])
        self.assertEqual(out["stages"]["B"]["selection"]["winner"], "B-rslora-rank-x4")
        self.assertEqual(out["stages"]["B"]["control"], "A-4b-lora-r16")
        self.assertEqual(out["stages"]["C_format"]["selection"]["winner"], "C-format-expression")
        self.assertEqual(out["stages"]["C_data"]["selection"]["winner"], "C-format-expression")
        self.assertFalse(out["stages"]["C_data"]["selection"]["adopted"])
        chosen = out["selection"]["config"]
        self.assertEqual(
            (chosen["base"], chosen["method"], chosen["rank"], chosen["output_format"], chosen["train_data"]),
            ("4b", "rslora", 64, "expression", "nemotron"),
        )
        self.assertEqual(out["final"], dict(out["final"], run="C-format-expression", reused=True))
        self.assertEqual(out["selection"]["decoding"], "auto")  # one validation note better under the constraint
        self.assertIn("v1-recipe-4b", out["runs"])
        self.assertEqual(out["stages"]["B"]["changes"]["B-dora"], {"method": ["lora", "dora"]})
        self.assertFalse(out["budget"]["over_budget"])
        trained = [c[1] for c in lab.calls if c[0] == "train"]
        self.assertEqual(trained[:4], ["A-270m-lora-r16", "A-1b-lora-r16", "A-4b-lora-r16", "A-270m-full-finetune"])
        self.assertEqual(len(trained), len(set(trained)))

    def test_mcnemar_and_risk_control_are_reported(self):
        out, _ = run(100000)
        pairs = {(t["a"], t["b"], t["split"]) for t in out["test"]["mcnemar"]}
        self.assertEqual(len(pairs), 9)  # three pairs x (two test sets + pooled)
        self.assertIn(("selected", "v1_recipe", "test_haiku"), pairs)
        self.assertTrue(all(0 <= t["exact_p"] <= t["holm_adjusted_p"] <= 1 for t in out["test"]["mcnemar"]))
        control = out["risk_control"]
        self.assertEqual(control["calibration_n"], N_VAL)
        self.assertEqual({(r["alpha"], r["method"]) for r in control["results"]}, {(a, m) for a in (0.01, 0.05) for m in ("fixed_sequence", "bonferroni")})
        self.assertEqual(set(control["results"][0]["checks"]), {"test_nemotron", "test_haiku", "pooled"})
        strict = next(r for r in control["results"] if r["alpha"] == 0.01 and r["method"] == "fixed_sequence")
        self.assertIsNone(strict["calibration"]["threshold"])  # 250 notes cannot certify 1%: 299 are needed
        self.assertIn("too small", strict["calibration"]["reason"])

    def test_unavailable_format_and_data_are_dropped_with_the_reason(self):
        out, _ = run(
            100000,
            expression_available=(False, "scribe/v2/data_tools.py is missing expression_messages"),
            haiku_train_available=(False, "split 'train_haiku' is not available"),
        )
        reasons = {d["item"]: d["reason"] for d in out["dropped"]}
        self.assertIn("data_tools.py is missing", reasons["C-format-expression"])
        self.assertIn("train_haiku", reasons["C-data-nemotron+haiku"])
        self.assertEqual(out["selection"]["config"]["output_format"], "absolute")
        self.assertEqual(out["status"], "complete")

    def test_a_failed_first_run_does_not_stop_the_ladder(self):
        clock = fakes.FakeClock()
        lab = Lab(clock, guarded=False)

        def train(cfg, max_minutes):
            if cfg.base == "270m":
                clock.advance(5)
                return {"config": cfg.to_dict(), "config_id": cfg.config_id, "status": "error", "eligible": False, "error": "chat template drift"}
            return lab.train(cfg, max_minutes)

        ablation = ra.Ablation(fakes.settings(100000), train, lab.evaluate, clock=clock)
        lab.ablation = ablation
        out = ablation.run()
        self.assertEqual(out["status"], "complete")
        self.assertEqual(out["runs"]["A-270m-lora-r16"]["status"], "error")
        self.assertEqual(out["stages"]["A"]["selection"]["winner"], "A-4b-lora-r16")
        self.assertEqual(out["stages"]["A"]["finalists"], [])
        self.assertTrue(any("chat template drift" in note for note in out["notes"]))

    def test_no_eligible_run_is_an_error_not_a_guess(self):
        clock = fakes.FakeClock()
        lab = Lab(clock, guarded=False)

        def train(cfg, max_minutes):
            return {"config": cfg.to_dict(), "config_id": cfg.config_id, "status": "error", "eligible": False, "error": "no GPU"}

        ablation = ra.Ablation(fakes.settings(100000), train, lab.evaluate, clock=clock)
        lab.ablation = ablation
        with self.assertRaisesRegex(RuntimeError, "no eligible run"):
            ablation.run()
        self.assertIsNone(ablation.out["selection"])
        self.assertIsNone(ablation.out["test"])
        self.assertFalse([c for c in lab.calls if c[0] == "eval"])

    def test_final_run_is_reused_after_a_batch_split_change(self):
        # After an out-of-memory retry the finished run has half the batch and twice the accumulation.
        clock = fakes.FakeClock()
        lab = Lab(clock, guarded=False)

        def train(cfg, max_minutes):
            return lab.train(cfg.with_(batch_size=cfg.batch_size // 2, grad_accum=cfg.grad_accum * 2), max_minutes)

        ablation = ra.Ablation(fakes.settings(100000), train, lab.evaluate, clock=clock)
        lab.ablation = ablation
        out = ablation.run()
        self.assertTrue(out["final"]["reused"])
        self.assertNotIn("final-selected", out["runs"])

    def test_final_steps_force_a_new_final_run(self):
        out, lab = run(100000, final_steps=648)
        self.assertEqual(out["final"], {"run": "final-selected", "reused": False})
        self.assertEqual(out["runs"]["final-selected"]["config"]["max_steps"], 648)
        self.assertEqual(out["selection"]["run"], "final-selected")
        self.assertEqual(out["runs"]["v1-recipe-4b"]["config"]["max_steps"], 648)

    def test_failed_arm_is_recorded_and_ignored(self):
        def train_with_failure(lab):
            real = lab.train

            def train(cfg, max_minutes):
                result = real(cfg, max_minutes)
                if cfg.name == "B-rslora-rank-x4":
                    result = dict(result, status="error", eligible=False, error="CUDA error")
                    result.pop("val")
                return result

            return train

        clock = fakes.FakeClock()
        lab = Lab(clock, guarded=False)
        ablation = ra.Ablation(fakes.settings(100000), train_with_failure(lab), lab.evaluate, clock=clock)
        lab.ablation = ablation
        out = ablation.run()
        self.assertEqual(out["runs"]["B-rslora-rank-x4"]["status"], "error")
        self.assertNotIn("B-rslora-rank-x4", out["stages"]["B"]["arms_completed"])
        self.assertEqual(out["stages"]["B"]["selection"]["winner"], "A-4b-lora-r16")
        self.assertTrue(any("B-rslora-rank-x4" in note for note in out["notes"]))


class TimeBudget(unittest.TestCase):
    def planned(self):
        control = cfgmod.control("1b")
        return [a.name for a in cfgmod.stage_a()] + [a.name for a in cfgmod.stage_b(control)]

    def test_tight_budget_drops_later_items_and_still_finishes(self):
        out, lab = run(60)
        self.assertEqual(out["status"], "complete")
        dropped = [d["item"] for d in out["dropped"]]
        self.assertTrue(dropped)
        self.assertTrue(all(d["reason"] for d in out["dropped"]))
        self.assertIsNotNone(out["selection"])
        self.assertIn("selected", out["test"]["systems"])
        self.assertFalse(out["budget"]["over_budget"])
        self.assertLessEqual(out["budget"]["elapsed_seconds"], 60 * 60)
        # Every planned training run was either run or dropped; nothing vanished silently.
        trained = {c[1] for c in lab.calls if c[0] == "train"}
        for name in self.planned():
            self.assertTrue(name in trained or name in dropped, name)
        self.assertFalse(trained & set(dropped))

    def test_stage_b_is_cut_from_the_end(self):
        for minutes in (45, 60, 90, 120, 200):
            out, _ = run(minutes)
            stage = out["stages"]["B"]
            done = stage["arms_completed"]
            with self.subTest(minutes=minutes):
                self.assertEqual(done, stage["arms"][: len(done)])  # a prefix of the priority order

    def test_every_budget_ends_with_a_tested_selection(self):
        for minutes in (2, 10, 30, 60, 120, 240):
            out, lab = run(minutes)
            with self.subTest(minutes=minutes):
                self.assertEqual(out["status"], "complete")
                self.assertTrue(out["selection"]["frozen"])
                self.assertIn("selected", out["test"]["systems"])
                self.assertEqual(lab.calls[0][:2], ("train", "A-270m-lora-r16"))  # smallest size first, always

    def test_tiny_budget_runs_the_smallest_size_and_reports_the_rest_as_dropped(self):
        out, lab = run(2)
        trained = [c[1] for c in lab.calls if c[0] == "train"]
        self.assertEqual(trained, ["A-270m-lora-r16"])
        self.assertEqual(out["selection"]["config"]["base"], "270m")
        self.assertEqual(out["final"]["reused"], True)
        self.assertEqual(sorted(out["test"]["systems"]), ["selected"])
        dropped = {d["item"] for d in out["dropped"]}
        self.assertTrue({"A-1b-lora-r16", "A-4b-lora-r16", "B-dora", "C-format-expression", "zero-shot base on test"} <= dropped)
        self.assertEqual(out["status"], "complete")

    def test_estimator_uses_measurements_then_parameter_scaling(self):
        estimator = ra.Estimator()
        cfg = cfgmod.control("1b")
        self.assertEqual(estimator.train_seconds(cfg, N_VAL), (None, None))
        estimator.observe(fakes.run_result(cfgmod.control("270m"), fakes.outcomes(N_VAL, 200), seconds_per_step=0.2))
        seconds, basis = estimator.train_seconds(cfg, N_VAL)
        ratio = cfgmod.BASES["1b"]["parameters"] / cfgmod.BASES["270m"]["parameters"]
        self.assertAlmostEqual(seconds, ratio * (0.2 * 324 + 7 + 0.1 * N_VAL))
        self.assertIn("extrapolated from 270m", basis)
        estimator.observe(fakes.run_result(cfg, fakes.outcomes(N_VAL, 200), seconds_per_step=0.6))
        seconds, basis = estimator.train_seconds(cfg, N_VAL)
        self.assertAlmostEqual(seconds, 0.6 * 324 + 7 + 0.1 * N_VAL)
        self.assertEqual(basis, "measured")
        dora = cfg.with_(name="d", method="dora")
        self.assertAlmostEqual(estimator.train_seconds(dora, N_VAL)[0], 1.3 * 0.6 * 324 + 7 + 0.1 * N_VAL)
        estimator.observe({"status": "error"})  # ignored

    def test_budget_clock(self):
        clock = fakes.FakeClock()
        budget = ra.Budget(1, clock)
        clock.advance(45)
        self.assertEqual((budget.elapsed(), budget.remaining()), (45, 15))


class ReviewFixes(unittest.TestCase):
    """Version-2 review (runs/review-findings-v2.json), findings 0, 1, 2, 4 and 6."""

    def test_one_finished_rung_is_not_called_the_highest(self):
        got = ra.select_size([view("only", "270m", 112)])
        self.assertEqual(got["winner"], "only")
        self.assertIn("only ladder run that finished", got["rationale"])
        self.assertNotIn("highest", got["rationale"])

    def test_no_arm_ran_is_not_a_negative_test(self):
        got = ra.select_arm(view("control", "270m", 112), [])
        self.assertEqual(got["comparisons"], [])
        self.assertIn("no arm ran", got["rationale"])
        self.assertNotIn("p <", got["rationale"])

    def test_finalist_rationale_states_the_test(self):
        got = ra.select_finalist(view("lora", "270m", 112), view("full", "270m", 117), list(cfgmod.SIZE_LADDER))
        self.assertFalse(got["adopted"])
        self.assertIn("discordant", got["rationale"])
        self.assertIn("exact p =", got["rationale"])

    def test_reserve_holds_back_only_what_is_never_sacrificed(self):
        out, lab = run(60)
        measured = [p for p in out["planning"] if p["reserve_basis"].startswith("never-sacrificed")]
        self.assertTrue(measured)
        for p in measured:
            for sacrificed in ("zero_shot", "v1_recipe", "decoding_check"):
                self.assertNotIn(sacrificed, p["reserve_basis"])
        self.assertIn("reserve_rule", out["protocol"])
        # With the smaller reserve the ablation arms get the time before the baselines do.
        trained = {c[1] for c in lab.calls if c[0] == "train"}
        self.assertTrue(trained & {"B-rslora-scale-x2", "B-rslora-rank-x4", "B-loraplus"})

    def test_test_summary_has_no_in_sample_coverage_and_splits_unparsable(self):
        records = [
            {"prediction": {"entry_route": "PRIVATE", "events": []}, "stopped": True, "tokens": 20},
            {"prediction": None, "stopped": False, "tokens": 134},   # cut at the cap
            {"prediction": None, "stopped": True, "tokens": 40},     # malformed
        ]
        block = {
            "metrics": {"n": 3, "note_exact_match": {"value": 1 / 3}, "ids": ["a", "b", "c"], "outcomes": [True, False, False],
                        "confidences": [-0.1, -0.5, -0.9], "risk_coverage": {"largest_empirical_coverage": {"0.05": 0.33}}},
            "decoding": {"constraint": {"backend": "none"}, "max_new_tokens": 134, "seconds": 1.0},
            "records": records,
        }
        got = ra.test_summary(block)
        self.assertNotIn("risk_coverage", got)
        self.assertEqual(got["unparsable_by_cause"],
                         {"n": 3, "unparsable": 2, "cut_at_cap": 1, "malformed": 1, "max_new_tokens": 134})

    def test_decoding_check_uses_the_same_evaluator_for_both_arms(self):
        out, lab = run(240)
        modes = [c[3] for c in lab.calls if c[0] == "eval" and c[2][0].startswith("val")]
        self.assertEqual(sorted(modes), ["auto", "off"])
        self.assertEqual(out["selection"]["decoding"], "auto")


if __name__ == "__main__":
    unittest.main()
