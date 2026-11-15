"""serve/convert_mlx_adapter.py: MLX LoRA layout -> PEFT layout, values untouched."""

import contextlib
import io
import json
import os
import pathlib
import shutil
import struct
import subprocess
import tempfile
import unittest

import support
import convert_mlx_adapter as conv

REAL = support.ROOT / "scribe" / "artifacts" / "adapter-v1"


def f32(values):
    return struct.pack(f"<{len(values)}f", *values)


def matrix(raw, rows, cols):
    flat = struct.unpack(f"<{rows * cols}f", raw)
    return [list(flat[r * cols : (r + 1) * cols]) for r in range(rows)]


class Convert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = pathlib.Path(self.tmp.name) / "mlx"
        self.out = pathlib.Path(self.tmp.name) / "peft"
        self.src.mkdir()
        # in = 3, rank = 2, out = 4
        self.a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]                  # (3, 2)
        self.b = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]  # (2, 4)
        self.tensors = {
            "model.layers.0.self_attn.q_proj.lora_a": ("F32", [3, 2], f32(self.a)),
            "model.layers.0.self_attn.q_proj.lora_b": ("F32", [2, 4], f32(self.b)),
            "model.layers.1.mlp.down_proj.lora_a": ("F32", [3, 2], f32([x + 0.5 for x in self.a])),
            "model.layers.1.mlp.down_proj.lora_b": ("F32", [2, 4], f32([x + 0.5 for x in self.b])),
        }
        self.write()

    def write(self, **config):
        conv.write_safetensors(self.src / "adapters.safetensors", self.tensors)
        base = {"fine_tune_type": "lora", "model": "mlx-community/gemma-3-1b-it-bf16",
                "lora_parameters": {"rank": 2, "scale": 2.0, "dropout": 0.05, "keys": ["self_attn.q_proj", "mlp.down_proj"]}}
        base.update(config)
        (self.src / "adapter_config.json").write_text(json.dumps(base))

    def test_round_trip_of_the_file_format(self):
        tensors, metadata = conv.read_safetensors(self.src / "adapters.safetensors")
        self.assertEqual(tensors, self.tensors)
        self.assertIsNone(metadata)

    def test_transposed_values_and_keys(self):
        record = conv.convert(self.src, self.out, "unsloth/gemma-3-1b-it")
        tensors, metadata = conv.read_safetensors(self.out / "adapter_model.safetensors")
        self.assertEqual(metadata, {"format": "pt"})
        self.assertEqual(sorted(tensors), [
            "base_model.model.model.layers.0.self_attn.q_proj.lora_A.weight",
            "base_model.model.model.layers.0.self_attn.q_proj.lora_B.weight",
            "base_model.model.model.layers.1.mlp.down_proj.lora_A.weight",
            "base_model.model.model.layers.1.mlp.down_proj.lora_B.weight",
        ])
        dtype, shape, raw = tensors["base_model.model.model.layers.0.self_attn.q_proj.lora_A.weight"]
        self.assertEqual((dtype, shape), ("F32", [2, 3]))
        a = matrix(f32(self.a), 3, 2)
        big_a = matrix(raw, 2, 3)
        self.assertTrue(all(big_a[i][j] == a[j][i] for i in range(2) for j in range(3)))
        dtype, shape, raw = tensors["base_model.model.model.layers.0.self_attn.q_proj.lora_B.weight"]
        self.assertEqual((dtype, shape), ("F32", [4, 2]))
        b = matrix(f32(self.b), 2, 4)
        big_b = matrix(raw, 4, 2)
        self.assertTrue(all(big_b[i][j] == b[j][i] for i in range(4) for j in range(2)))
        # The update itself: scale * (x @ a) @ b  ==  (alpha / r) * B (A x)
        x = [0.5, -1.0, 2.0]
        config = json.loads((self.out / "adapter_config.json").read_text())
        xa = [sum(x[i] * a[i][k] for i in range(3)) for k in range(2)]
        mlx = [2.0 * sum(xa[k] * b[k][o] for k in range(2)) for o in range(4)]
        ax = [sum(big_a[k][i] * x[i] for i in range(3)) for k in range(2)]
        peft = [config["lora_alpha"] / config["r"] * sum(big_b[o][k] * ax[k] for k in range(2)) for o in range(4)]
        self.assertEqual(mlx, peft)
        self.assertEqual((record["modules"], record["tensors"]), (2, 4))

    def test_peft_config(self):
        conv.convert(self.src, self.out, "unsloth/gemma-3-1b-it")
        config = json.loads((self.out / "adapter_config.json").read_text())
        self.assertEqual(config["peft_type"], "LORA")
        self.assertEqual(config["task_type"], "CAUSAL_LM")
        self.assertEqual((config["r"], config["lora_alpha"]), (2, 4))  # alpha = scale * rank
        self.assertEqual(config["target_modules"], ["down_proj", "q_proj"])
        self.assertEqual(config["base_model_name_or_path"], "unsloth/gemma-3-1b-it")
        # What vLLM v0.29.0 refuses must be absent.
        self.assertEqual(config["bias"], "none")
        self.assertIsNone(config["modules_to_save"])
        self.assertIs(config["use_dora"], False)
        self.assertIs(config["use_rslora"], False)
        training = json.loads((self.out / "training-config.json").read_text())
        self.assertEqual(training["base_model"], "unsloth/gemma-3-1b-it")
        self.assertEqual(training["converted_from_mlx"]["source_base_model"], "mlx-community/gemma-3-1b-it-bf16")

    def test_sixteen_bit_values_are_moved_not_interpreted(self):
        raw = bytes(range(12))  # (3, 2) of 2-byte units
        out = conv.transpose(raw, 3, 2, 2)
        self.assertEqual(out, bytes([0, 1, 4, 5, 8, 9, 2, 3, 6, 7, 10, 11]))

    def test_refusals(self):
        del self.tensors["model.layers.1.mlp.down_proj.lora_b"]
        self.write()
        with self.assertRaises(ValueError):
            conv.convert(self.src, self.out, "unsloth/gemma-3-1b-it")
        self.setUp()
        self.write(fine_tune_type="dora")
        with self.assertRaises(ValueError):
            conv.convert(self.src, self.out, "unsloth/gemma-3-1b-it")
        self.write(lora_parameters={"rank": 3, "scale": 2.0})
        with self.assertRaises(ValueError):
            conv.convert(self.src, self.out, "unsloth/gemma-3-1b-it")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(conv.main([str(self.src / "nope"), str(self.out), "--base-model", "x"]), 1)

    @unittest.skipIf(shutil.which("bash") is None, "bash not available")
    def test_entrypoint_accepts_the_converted_adapter(self):
        conv.convert(self.src, self.out, "unsloth/gemma-3-1b-it")
        env = {"PATH": os.environ["PATH"], "SCRIBE_ADAPTER_DIR": str(self.out), "SCRIBE_CHECK_ONLY": "1",
               "SCRIBE_MAX_LORA_RANK": "16"}
        entrypoint = str(support.SERVE / "entrypoint.sh")
        ok = subprocess.run(["bash", entrypoint], env=dict(env, SCRIBE_BASE_MODEL="unsloth/gemma-3-1b-it"),
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        if shutil.which("python3"):
            wrong = subprocess.run(["bash", entrypoint], env=env, capture_output=True, text=True)
            self.assertEqual(wrong.returncode, 65)  # default base is the 4B model
            self.assertIn("gemma-3-1b-it", wrong.stderr)

    @unittest.skipUnless((REAL / "adapters.safetensors").exists(), "version-1 MLX adapter not on this machine")
    def test_real_version_1_adapter(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(conv.main([str(REAL), str(self.out), "--base-model", "unsloth/gemma-3-1b-it"]), 0)
        source, _ = conv.read_safetensors(REAL / "adapters.safetensors")
        target, _ = conv.read_safetensors(self.out / "adapter_model.safetensors")
        self.assertEqual((len(source), len(target)), (364, 364))
        config = json.loads((self.out / "adapter_config.json").read_text())
        self.assertEqual((config["r"], config["lora_alpha"]), (16, 32))
        self.assertEqual(config["target_modules"],
                         ["down_proj", "gate_proj", "k_proj", "o_proj", "q_proj", "up_proj", "v_proj"])
        for name, (dtype, shape, raw) in source.items():
            module, kind = name.rsplit(".", 1)
            twin = "base_model.model." + module + (".lora_A.weight" if kind == "lora_a" else ".lora_B.weight")
            self.assertEqual(target[twin][1], shape[::-1], name)
            self.assertEqual(target[twin][2], conv.transpose(raw, shape[0], shape[1], conv.ITEM_BYTES[dtype]), name)
            self.assertEqual(conv.transpose(target[twin][2], shape[1], shape[0], conv.ITEM_BYTES[dtype]), raw, name)


if __name__ == "__main__":
    unittest.main()
