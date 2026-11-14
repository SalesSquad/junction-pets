import re
import unittest

import fakes  # noqa: F401
import config as c


class Grid(unittest.TestCase):
    def test_stage_a_is_a_size_ladder_with_equal_steps(self):
        arms = c.stage_a()
        ladder = [a for a in arms if a.method == "lora"]
        self.assertEqual([a.base for a in ladder], ["270m", "1b", "4b"])
        self.assertEqual({a.max_steps for a in arms}, {324})
        self.assertEqual({a.effective_batch for a in arms}, {16})
        self.assertEqual({a.output_format for a in arms}, {"absolute"})
        self.assertEqual({a.train_data for a in arms}, {"nemotron"})
        for a in ladder[1:]:
            self.assertLessEqual(set(c.diff(ladder[0], a)), {"base", "batch_size", "grad_accum"})
        full = [a for a in arms if a.method == "full"]
        self.assertEqual(len(full), 1)
        self.assertEqual((full[0].base, full[0].learning_rate), ("270m", 5e-5))
        self.assertIsNone(full[0].scaling)

    def test_stage_a_respects_sizes_and_extras(self):
        self.assertEqual([a.name for a in c.stage_a(sizes=("1b",), extras=())], ["A-1b-lora-r16"])
        self.assertEqual(len(c.stage_a(extras=c.STAGE_A_EXTRAS)), 5)
        with self.assertRaises(c.ConfigError):
            c.stage_a(extras=("nonsense",))

    def test_stage_b_changes_one_thing_at_a_time(self):
        control = c.control("1b")
        arms = {a.name: a for a in c.stage_b(control, with_eva=True)}
        self.assertEqual(
            list(arms), ["B-rslora-scale-x2", "B-rslora-rank-x4", "B-loraplus", "B-pissa", "B-eva", "B-dora"]
        )
        allowed = {
            "B-rslora-scale-x2": {"method", "alpha"},
            "B-rslora-rank-x4": {"method", "rank", "alpha"},
            "B-loraplus": {"loraplus_ratio", "learning_rate"},
            "B-pissa": {"init", "alpha"},
            "B-eva": {"init"},
            "B-dora": {"method"},
        }
        for name, arm in arms.items():
            self.assertEqual(set(c.diff(control, arm)), allowed[name], name)
        self.assertEqual(control.scaling, 2.0)
        self.assertEqual(arms["B-rslora-scale-x2"].scaling, 4.0)
        self.assertEqual((arms["B-rslora-rank-x4"].rank, arms["B-rslora-rank-x4"].scaling), (64, 2.0))
        self.assertEqual(arms["B-loraplus"].learning_rate, 1e-4)
        self.assertEqual(arms["B-pissa"].scaling, 1.0)
        self.assertEqual(list(arms)[-1], "B-dora")  # the first arm to be cut under a tight budget
        self.assertNotIn("B-eva", [a.name for a in c.stage_b(control)])

    def test_stage_c_and_v1(self):
        best = c.control("1b")
        self.assertEqual(c.diff(best, c.stage_c_format(best)), {"output_format": ("absolute", "expression")})
        self.assertEqual(c.diff(best, c.stage_c_data(best)), {"train_data": ("nemotron", "nemotron+haiku")})
        v1 = c.v1_recipe()
        self.assertEqual((v1.base, v1.rank, v1.alpha, v1.dropout), ("4b", 16, 32.0, 0.05))
        self.assertEqual((v1.batch_size, v1.grad_accum, v1.gradient_checkpointing), (2, 8, True))
        self.assertTrue(v1.supervise_stop_token)

    def test_invalid_combinations_are_refused(self):
        base = c.control("1b")
        for change in (
            dict(method="dora", loraplus_ratio=16.0),
            dict(method="full", init="pissa"),
            dict(method="full", loraplus_ratio=16.0),
            dict(method="rslora", init="pissa"),
            dict(init="eva", loraplus_ratio=16.0),
            dict(loraplus_ratio=0.5),
            dict(base="27b"),
            dict(output_format="yaml"),
            dict(train_data="haiku"),
            dict(rank=0),
        ):
            with self.assertRaises(c.ConfigError, msg=str(change)):
                base.with_(**change)

    def test_full_grid(self):
        grid = c.grid()
        # 3 sizes x 2 formats x 2 data settings x valid (method, init, LoRA+) combinations:
        # lora: default/pissa without LoRA+ and default with LoRA+ = 3; rslora: 2; dora: 1.
        self.assertEqual(len(grid), 3 * 2 * 2 * 6)
        self.assertEqual(len({g.config_id for g in grid}), len(grid))
        self.assertEqual(len({g.name for g in grid}), len(grid))
        self.assertFalse([g for g in grid if g.method == "dora" and g.loraplus_ratio])
        self.assertTrue(all(g.scaling in (1.0, 2.0) for g in grid))

    def test_round_trip_and_ids(self):
        a = c.control("4b")
        self.assertEqual(c.RunConfig.from_dict(a.to_dict()), a)
        self.assertEqual(a.config_id, a.with_(name="another name").config_id)
        self.assertNotEqual(a.config_id, a.with_(seed=1).config_id)
        with self.assertRaises(c.ConfigError):
            c.RunConfig.from_dict(dict(a.to_dict(), typo=1))
        self.assertEqual(a.warmup_steps, 17)  # ceil(0.05 * 324)
        halved = a.with_(batch_size=a.batch_size // 2, grad_accum=a.grad_accum * 2)  # what an OOM retry does
        self.assertNotEqual(a.config_id, halved.config_id)
        self.assertEqual(a.recipe_id, halved.recipe_id)
        self.assertNotEqual(a.recipe_id, a.with_(batch_size=a.batch_size // 2).recipe_id)
        self.assertNotEqual(a.recipe_id, a.with_(rank=8).recipe_id)

    def test_lora_kwargs(self):
        kw = c.control("1b").lora_kwargs()
        self.assertIsInstance(kw["target_modules"], str)  # a string is matched as a regular expression
        self.assertEqual((kw["r"], kw["lora_alpha"], kw["use_rslora"], kw["use_dora"]), (16, 32.0, False, False))
        self.assertIs(kw["init_lora_weights"], True)
        arms = {a.name: a for a in c.stage_b(c.control("1b"), with_eva=True)}
        self.assertTrue(arms["B-rslora-rank-x4"].lora_kwargs()["use_rslora"])
        self.assertTrue(arms["B-dora"].lora_kwargs()["use_dora"])
        self.assertEqual(arms["B-pissa"].lora_kwargs()["init_lora_weights"], "pissa_niter_4")
        self.assertEqual(arms["B-eva"].lora_kwargs()["init_lora_weights"], "eva")
        self.assertNotIn("modules_to_save", kw)
        with self.assertRaises(c.ConfigError):
            c.stage_a()[-1].lora_kwargs()

    def test_targets_stay_out_of_the_vision_tower(self):
        language = [
            "model.language_model.layers.1.self_attn.q_proj",
            "model.language_model.layers.33.mlp.down_proj",
            "model.layers.0.self_attn.o_proj",
            "base_model.model.model.layers.17.mlp.gate_proj",
        ]
        vision = [
            "model.vision_tower.encoder.layers.0.self_attn.q_proj",
            "model.vision_tower.vision_model.encoder.layers.3.self_attn.v_proj",
            "model.multi_modal_projector.mm_input_projection",
            "lm_head",
        ]
        pattern = c.TARGETS["attn_mlp"]
        self.assertTrue(all(re.fullmatch(pattern, n) for n in language))
        self.assertFalse(any(re.fullmatch(pattern, n) for n in vision))
        self.assertFalse(re.fullmatch(c.TARGETS["attn"], language[1]))
        self.assertTrue(re.fullmatch(c.TARGETS["mlp"], language[1]))

    def test_serving_notes(self):
        arms = {a.name: a for a in c.stage_b(c.control("1b"))}
        self.assertEqual(c.control("1b").serving_notes(), [])
        self.assertTrue(any("merge" in n for n in arms["B-dora"].serving_notes()))
        self.assertTrue(any("rank 64" in n for n in arms["B-rslora-rank-x4"].serving_notes()))
        self.assertTrue(any("rank 32" in n for n in arms["B-pissa"].serving_notes()))


if __name__ == "__main__":
    unittest.main()
