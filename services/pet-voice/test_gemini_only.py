"""Offline checks for --gemini-only (no network, no key). Run: python3 -m pytest -q services/pet-voice/test_gemini_only.py"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tempfile  # noqa: E402
os.environ.setdefault("SSVOICE_HOME", tempfile.mkdtemp(prefix="ssvoice-test-"))  # never the real quota ledger
os.environ["SSVOICE_CACHE"] = "0"                                               # nor the real audio cache
import pet_voice as pv  # noqa: E402
import scene  # noqa: E402


class GeminiOnly(unittest.TestCase):
    def setUp(self):
        self.saved = (dict(pv.GEMINI_ONLY), os.environ.get("PET_VOICE_GEMINI_ONLY"), set(pv.EXHAUSTED), pv.gemini.call, pv.gemini.live_speak,
                      pv.oa.post)
        pv.GEMINI_ONLY["on"] = False
        os.environ.pop("PET_VOICE_GEMINI_ONLY", None)
        pv.EXHAUSTED.clear()

        def no_network(*a, **k):
            raise AssertionError("network call attempted")
        pv.oa.post = no_network

    def tearDown(self):
        on, env, ex, pv.gemini.call, pv.gemini.live_speak, pv.oa.post = self.saved
        pv.GEMINI_ONLY["on"] = on["on"]
        os.environ.pop("PET_VOICE_GEMINI_ONLY", None)
        if env is not None:
            os.environ["PET_VOICE_GEMINI_ONLY"] = env
        pv.EXHAUSTED.clear(); pv.EXHAUSTED.update(ex)

    def test_default_orders_keep_openai_last_and_gemini_only_removes_it(self):
        for kind, defaults in (("tts", pv.DEFAULT_TTS_MODELS), ("mind", pv.DEFAULT_MIND_MODELS)):
            normal = pv.model_order({}, kind, defaults, None)
            self.assertTrue(any(m.startswith("openai:") for m in normal), kind)
            pv.set_gemini_only()
            only = pv.model_order({"modelOrder": {kind: ["openai:x"] + defaults}}, kind, defaults, None)
            self.assertFalse(any(m.startswith("openai:") for m in only), kind)
            self.assertEqual(only, [m for m in normal if not m.startswith("openai:")])
            self.assertEqual(pv.model_order({}, kind, defaults, ["openai:a", "gemini-x"]), ["gemini-x"])
            pv.GEMINI_ONLY["on"] = False
            os.environ.pop("PET_VOICE_GEMINI_ONLY")

    def test_env_switch_and_scene_writers(self):
        self.assertTrue(any(m.startswith("openai:") for m in scene.writer_order()))
        os.environ["PET_VOICE_GEMINI_ONLY"] = "1"
        self.assertTrue(pv.gemini_only())
        self.assertEqual(scene.writer_order(), [m for m in scene.WRITERS if not m.startswith(("openai:", "openai-shared:"))])

    def test_cli_flag_before_and_after_subcommand(self):
        for argv in (["--gemini-only", "status"], ["status", "--gemini-only"]):
            pv.GEMINI_ONLY["on"] = False
            os.environ.pop("PET_VOICE_GEMINI_ONLY", None)
            ap_fn = pv.cmd_status
            pv.cmd_status = lambda args: 0
            try:
                # status is wired via set_defaults(fn=cmd_status) at parse time, so patch happens before main() builds it
                self.assertEqual(pv.main(argv), 0)
            finally:
                pv.cmd_status = ap_fn
            self.assertTrue(pv.gemini_only(), argv)

    def test_speak_fails_clearly_when_gemini_is_exhausted_and_never_tries_openai(self):
        pv.set_gemini_only()

        def quota(model, body, key, log, **kw):
            raise pv.ProviderError(429, "RESOURCE_EXHAUSTED", "per day", daily=True)

        def live_down(*a, **k):
            raise pv.ProviderError(0, "TIMEOUT", "down")
        pv.gemini.call, pv.gemini.live_speak = quota, live_down
        log = []
        with self.assertRaises(pv.ProviderError) as cm:
            pv.speak("hei", "Kore", "warm", "k", ["gemini-a-tts", "live:g", "openai:gpt-4o-mini-tts"], log)
        self.assertEqual(cm.exception.code, "GEMINI_ONLY_EXHAUSTED")
        self.assertIn("--gemini-only", cm.exception.message)
        self.assertFalse(any(e["model"].startswith("openai:") for e in log))

    def test_think_fails_clearly_and_scene_writer_too(self):
        pv.set_gemini_only()

        def quota(model, body, key, log, **kw):
            raise pv.ProviderError(429, "RESOURCE_EXHAUSTED", "per day", daily=True)
        pv.gemini.call = quota
        with self.assertRaises(pv.ProviderError) as cm:
            pv.think("sys", "prompt", None, "k", ["gemini-3.5-flash", "openai:gpt-5.4-mini"], [])
        self.assertEqual(cm.exception.code, "GEMINI_ONLY_EXHAUSTED")
        with self.assertRaises(pv.ProviderError) as cm:
            scene.gen_json("sys", [{"text": "hi"}], {"type": "OBJECT"}, "k", [])
        self.assertEqual(cm.exception.code, "GEMINI_ONLY_EXHAUSTED")

    def test_openai_post_is_blocked_even_if_called_directly(self):
        pv.oa.post = self.saved[5]
        pv.set_gemini_only()
        with self.assertRaises(pv.ProviderError) as cm:
            pv.openai_post("audio/speech", payload={})
        self.assertEqual(cm.exception.code, "GEMINI_ONLY")

    def test_without_the_flag_openai_is_still_the_last_resort(self):
        called = []
        pv.openai_speak_saved = pv.oa.speak
        pv.oa.speak = lambda *a, **k: called.append(1) or pv.pcm_to_wav(b"\0\0" * 10)

        def quota(model, body, key, log, **kw):
            raise pv.ProviderError(429, "RESOURCE_EXHAUSTED", "per day", daily=True)
        pv.gemini.call = quota
        try:
            out = pv.speak("hei", "Kore", "warm", "k", ["gemini-a-tts", "openai:gpt-4o-mini-tts"], [])
        finally:
            pv.oa.speak = pv.openai_speak_saved
        self.assertEqual(out["model"], "openai:gpt-4o-mini-tts")
        self.assertEqual(called, [1])


if __name__ == "__main__":
    unittest.main()
