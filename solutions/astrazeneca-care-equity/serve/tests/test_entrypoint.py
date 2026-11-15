"""serve/entrypoint.sh in dry-run mode: flags, key handling, adapter checks. Needs bash."""

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import support

ENTRYPOINT = support.SERVE / "entrypoint.sh"
BASH = shutil.which("bash")


@unittest.skipIf(BASH is None, "bash not available")
class Entrypoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = pathlib.Path(self.tmp.name) / "adapter"
        self.adapter.mkdir()
        self.write_config()
        (self.adapter / "adapter_model.safetensors").write_bytes(b"")

    def write_config(self, **changes):
        config = {"r": 16, "lora_alpha": 32, "target_modules": ["q_proj"], "bias": "none",
                  "base_model_name_or_path": "unsloth/gemma-3-4b-it"}
        config.update(changes)
        (self.adapter / "adapter_config.json").write_text(json.dumps(config))

    def run_entrypoint(self, **env):
        base = {"PATH": os.environ["PATH"], "SCRIBE_ADAPTER_DIR": str(self.adapter),
                "SCRIBE_BASE_LOCAL_DIR": str(pathlib.Path(self.tmp.name) / "no-base"), "SCRIBE_DRY_RUN": "1",
                "SCRIBE_GUARD_DIR": str(support.SERVE)}
        base.update(env)
        return subprocess.run([BASH, str(ENTRYPOINT)], env=base, capture_output=True, text=True, timeout=60)

    def command(self, output):
        line = [l for l in output.splitlines() if l.startswith("scribe entrypoint: command:")][0]
        return line.split("command:", 1)[1].split()

    def test_default_command(self):
        done = self.run_entrypoint(SCRIBE_API_KEY="unit-test-key")
        self.assertEqual(done.returncode, 0, done.stderr)
        args = self.command(done.stdout)
        self.assertEqual(args[:3], ["vllm", "serve", "unsloth/gemma-3-4b-it"])

        def value(flag):
            return args[args.index(flag) + 1]

        self.assertEqual(value("--host"), "0.0.0.0")
        self.assertEqual(value("--port"), "8000")
        self.assertEqual(value("--served-model-name"), "gemma-base")
        self.assertEqual(value("--dtype"), "bfloat16")
        self.assertEqual(value("--max-model-len"), "2048")
        self.assertEqual(value("--max-num-seqs"), "8")
        self.assertEqual(value("--gpu-memory-utilization"), "0.90")
        self.assertEqual(value("--max-loras"), "1")
        self.assertEqual(value("--max-lora-rank"), "16")
        self.assertEqual(value("--lora-modules"), f"pathway-scribe={self.adapter}")
        self.assertEqual(value("--disable-access-log-for-endpoints"), "/health")
        self.assertIn("--enable-lora", args)
        self.assertIn("--language-model-only", args)
        self.assertIn("--structured-outputs-config", args)
        self.assertIn("xgrammar", done.stdout)
        # Must stay off: with xgrammar 0.2.9 it makes the grammar reject compact JSON (test_xgrammar.py).
        self.assertNotIn("disable_any_whitespace", done.stdout)
        self.assertNotIn("--revision", args)
        self.assertIn("GET /health on port 8000", done.stdout)

    def test_key_is_required_and_never_printed(self):
        refused = self.run_entrypoint()
        self.assertEqual(refused.returncode, 64)
        self.assertIn("SCRIBE_API_KEY is not set", refused.stderr)
        secret = "unit-test-key-that-must-not-be-echoed"
        done = self.run_entrypoint(SCRIBE_API_KEY=secret)
        self.assertEqual(done.returncode, 0)
        self.assertNotIn(secret, done.stdout + done.stderr)
        self.assertNotIn("--api-key", done.stdout)
        self.assertIn("bearer key required", done.stdout)
        open_mode = self.run_entrypoint(SCRIBE_ALLOW_NO_KEY="1")
        self.assertEqual(open_mode.returncode, 0)
        self.assertIn("NOT required", open_mode.stdout)
        native = self.run_entrypoint(VLLM_API_KEY=secret)
        self.assertEqual(native.returncode, 0)
        self.assertNotIn(secret, native.stdout + native.stderr)

    def test_key_guards_every_path_through_the_middleware(self):
        # Review finding 14: vLLM 0.29.0 checks VLLM_API_KEY only under /v1, /v2, /inference, /cohere.
        done = self.run_entrypoint(SCRIBE_API_KEY="k")
        self.assertEqual(done.returncode, 0, done.stderr)
        args = self.command(done.stdout)
        self.assertEqual(args[args.index("--middleware") + 1], "guard.BearerGuard")
        self.assertIn("every path except /health and /ping", done.stdout)
        native = self.command(self.run_entrypoint(VLLM_API_KEY="k").stdout)
        self.assertIn("--middleware", native)
        open_mode = self.run_entrypoint(SCRIBE_ALLOW_NO_KEY="1")
        self.assertNotIn("--middleware", self.command(open_mode.stdout))
        missing = self.run_entrypoint(SCRIBE_API_KEY="k", SCRIBE_GUARD_DIR=str(pathlib.Path(self.tmp.name) / "nowhere"))
        self.assertEqual(missing.returncode, 66)
        self.assertIn("guard.py", missing.stderr)

    def test_overrides(self):
        done = self.run_entrypoint(
            SCRIBE_API_KEY="k", SCRIBE_BASE_REVISION="bf46152c47f5dd20b896357cb51abc4c03b8ee8c",
            SCRIBE_PORT="9000", SCRIBE_MAX_MODEL_LEN="4096", SCRIBE_MAX_NUM_SEQS="2", SCRIBE_TEXT_ONLY="0",
            SCRIBE_LORA_NAME="scribe-b", SCRIBE_EXTRA_ARGS="--seed 7")
        self.assertEqual(done.returncode, 0, done.stderr)
        args = self.command(done.stdout)
        self.assertEqual(args[args.index("--revision") + 1], "bf46152c47f5dd20b896357cb51abc4c03b8ee8c")
        self.assertEqual(args[args.index("--port") + 1], "9000")
        self.assertEqual(args[args.index("--max-model-len") + 1], "4096")
        self.assertEqual(args[args.index("--max-num-seqs") + 1], "2")
        self.assertEqual(args[args.index("--lora-modules") + 1], f"scribe-b={self.adapter}")
        self.assertEqual(args[-2:], ["--seed", "7"])
        self.assertNotIn("--language-model-only", args)

    def test_baked_base_model_is_used_offline(self):
        base = pathlib.Path(self.tmp.name) / "base"
        base.mkdir()
        (base / "config.json").write_text("{}")
        done = self.run_entrypoint(SCRIBE_API_KEY="k", SCRIBE_BASE_LOCAL_DIR=str(base),
                                   SCRIBE_BASE_REVISION="bf46152c47f5dd20b896357cb51abc4c03b8ee8c")
        self.assertEqual(done.returncode, 0, done.stderr)
        args = self.command(done.stdout)
        self.assertEqual(args[2], str(base))
        self.assertNotIn("--revision", args)

    def test_missing_adapter_files(self):
        (self.adapter / "adapter_model.safetensors").unlink()
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k").returncode, 66)
        (self.adapter / "adapter_model.safetensors").write_bytes(b"")
        (self.adapter / "adapter_config.json").unlink()
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k").returncode, 66)

    @unittest.skipIf(shutil.which("python3") is None, "python3 not on PATH")
    def test_adapter_config_checks(self):
        cases = {
            "rank above the limit": {"r": 32},
            "modules_to_save": {"modules_to_save": ["lm_head"]},
            "DoRA": {"use_dora": True},
            "bias": {"bias": "all"},
            "per-module ranks": {"rank_pattern": {"model.layers.0.self_attn.q_proj": 8}},
            "per-module alphas": {"alpha_pattern": {"q_proj": 16}},
            "trained on another base": {"base_model_name_or_path": "unsloth/gemma-3-1b-it"},
        }
        for name, change in cases.items():
            self.write_config(**change)
            done = self.run_entrypoint(SCRIBE_API_KEY="k")
            self.assertEqual(done.returncode, 65, name)
        self.write_config(rank_pattern={}, alpha_pattern={})  # empty patterns are what PEFT writes by default
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k").returncode, 0)
        self.write_config(r=32)
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k", SCRIBE_MAX_LORA_RANK="32").returncode, 0)
        self.write_config(base_model_name_or_path="unsloth/gemma-3-1b-it")
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k", SCRIBE_BASE_MODEL="unsloth/gemma-3-1b-it").returncode, 0)
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k", SCRIBE_SKIP_BASE_CHECK="1").returncode, 0)
        # Mirror and original share the last path part; a local copy does too.
        self.write_config(base_model_name_or_path="google/gemma-3-4b-it")
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k").returncode, 0)
        self.write_config(base_model_name_or_path="/root/models/gemma-3-4b-it/")
        self.assertEqual(self.run_entrypoint(SCRIBE_API_KEY="k").returncode, 0)
        # training-config.json written by scribe/train_lora.py is checked as well.
        self.write_config()
        (self.adapter / "training-config.json").write_text(json.dumps({"base_model": "unsloth/gemma-3-1b-it"}))
        done = self.run_entrypoint(SCRIBE_API_KEY="k")
        self.assertEqual(done.returncode, 65)
        self.assertIn("training-config.json", done.stderr)

    def test_check_only_needs_no_key(self):
        done = self.run_entrypoint(SCRIBE_CHECK_ONLY="1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("command:", done.stdout)

    def test_dockerfile_matches_entrypoint_contract(self):
        dockerfile = (support.SERVE / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG VLLM_IMAGE=docker.io/vllm/vllm-openai:v0.29.0", dockerfile)
        self.assertNotIn(":latest", dockerfile)
        self.assertIn('ENTRYPOINT ["/opt/scribe/entrypoint.sh"]', dockerfile)
        self.assertIn("COPY --from=adapter adapter_config.json adapter_model.safetensors", dockerfile)
        self.assertIn("SCRIBE_ADAPTER_DIR=/opt/scribe/adapter", dockerfile)
        self.assertIn("SCRIBE_LORA_NAME=pathway-scribe", dockerfile)
        self.assertIn("EXPOSE 8000", dockerfile)
        self.assertIn("ARG BAKE_BASE_MODEL=0", dockerfile)
        ignore = (support.SERVE / ".dockerignore").read_text(encoding="utf-8").split()
        self.assertIn("!entrypoint.sh", ignore)
        self.assertIn("!schema.json", ignore)
        self.assertIn("!guard.py", ignore)
        self.assertIn("COPY guard.py /opt/scribe/guard.py", dockerfile)


if __name__ == "__main__":
    unittest.main()
