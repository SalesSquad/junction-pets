"""Offline checks for pet_voice (no network, no key). Run: python3 -m unittest services/pet-voice/test_pet_voice.py"""
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pet_voice as pv  # noqa: E402


class Profiles(unittest.TestCase):
    def test_every_pet_has_a_valid_voice_profile(self):
        voices, slugs = pv.load_voices(), pv.all_pet_slugs()
        self.assertEqual(sorted(voices), slugs)
        self.assertEqual(len(slugs), 34)
        for slug, prof in voices.items():
            self.assertIn(prof["voice"], pv.PREBUILT_VOICES, slug)
            self.assertIn(prof["language"], pv.LANGUAGE_NAMES, slug)
            self.assertTrue(prof["style"])
            p = pv.persona(slug)
            self.assertTrue(p["name"] and p["display"])
        self.assertGreaterEqual(len({p["language"] for p in voices.values()}), 10)


class Audio(unittest.TestCase):
    def test_raw_pcm_and_odd_riff_normalize_and_concat(self):
        pcm = struct.pack("<4h", 0, 1000, -1000, 0)
        wav = pv.normalize_audio(pcm, "audio/L16;codec=pcm;rate=24000")
        self.assertEqual(pv.wav_pcm(wav), (pcm, 24000, 1, 16))
        streaming = wav[:40] + struct.pack("<I", 0xFFFFFFFF) + pcm  # size unknown, as in streamed WAV
        self.assertEqual(pv.wav_pcm(pv.normalize_audio(streaming))[0], pcm)
        joined = pv.concat_wavs([wav, wav], gap=0.0)
        self.assertEqual(pv.wav_pcm(joined)[0], pcm * 2)


class Signals(unittest.TestCase):
    def test_heard_accuracy_is_language_agnostic(self):
        self.assertEqual(pv.heard_accuracy("Hei, Verda!", "hei verda"), 1.0)
        self.assertEqual(pv.heard_accuracy("こんにちは、世界", "こんにちは世界"), 1.0)
        self.assertLess(pv.heard_accuracy("Guten Morgen", "Good evening"), 0.7)
        self.assertIsNone(pv.heard_accuracy("", "x"))

    def test_rate_limit_error_parsing(self):
        body = json.dumps({"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota", "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"},
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": "GenerateRequestsPerDayPerProject"}]}]}}).encode()
        e = pv.parse_error(429, body)
        self.assertEqual((e.status, e.code, e.retry_after, e.daily), (429, "RESOURCE_EXHAUSTED", 17.0, True))

    def test_json_reply_parsing_strips_fences(self):
        resp = {"candidates": [{"content": {"parts": [{"text": "```json\n{\"heard\":\"hi\",\"heard_language\":\"en\",\"reply\":\" Hei  sinä \"}\n```"}]}}]}
        self.assertEqual(pv.parse_json_text(resp)["reply"], "Hei sinä")


class Learning(unittest.TestCase):
    def test_learn_orders_models_and_flags_weak_voice(self):
        def turn(i, voice, lang, acc, tts="m-ok", events=()):
            return {"turnId": f"r.t{i}", "inReplyTo": f"r.t{i-1}" if i else None, "status": "ok", "voice": voice, "language": lang,
                    "heardAccuracy": acc, "ttsModel": tts, "ttsVariant": "speech_metadata+voice", "ttsLatencyS": 2.0,
                    "mindModel": "mind", "mindLatencyS": 1.0, "ttsEvents": list(events), "mindEvents": []}
        run = {"turns": [turn(0, "Kore", "fi-FI", None, events=[{"model": "m-gone", "status": 404, "code": "NOT_FOUND"}]),
                         turn(1, "Puck", "it-IT", 0.5), turn(2, "Kore", "fi-FI", 0.95), turn(3, "Puck", "it-IT", 0.6),
                         turn(4, "Zephyr", "it-IT", 0.6), turn(5, "Kore", "fi-FI", 0.9)]}
        learned = pv.learn_from([run])
        self.assertEqual(learned["modelOrder"]["tts"], ["m-ok"])  # 404 model dropped
        self.assertEqual(learned["voiceLanguage"]["Kore|fi-FI"]["n"], 2)
        self.assertIn("Weak voice/language", pv.lessons_markdown(learned))
        learned["voiceLanguage"]["Zephyr|it-IT"] = {"voice": "Zephyr", "language": "it-IT", "n": 3, "mean": 0.93}
        learned["voiceLanguage"]["Puck|it-IT"] = {"voice": "Puck", "language": "it-IT", "n": 3, "mean": 0.5}
        self.assertEqual(pv.adapt_voice(learned, "Puck", "it-IT")[0], "Zephyr")
        self.assertEqual(pv.adapt_voice(learned, "Kore", "fi-FI")[0], "Kore")
        self.assertEqual(pv.model_order(learned, "tts", ["a", "m-ok"], None), ["m-ok", "a"])

    def test_models_that_ignore_the_handover_rank_lower(self):
        def turn(i, model, text, to="junction.verda", name="Verda"):
            return {"turnId": f"r.t{i}", "inReplyTo": f"r.t{i-1}" if i else None, "speaker": f"junction.p{i}", "to": to,
                    "toName": name, "mustAddressNext": True, "status": "ok", "voice": "Kore", "language": "fi-FI",
                    "heardAccuracy": 0.9 if i else None, "text": text, "ttsModel": "tts", "ttsVariant": "v", "ttsLatencyS": 1,
                    "mindModel": model, "mindLatencyS": 1 if model == "fast" else 9, "ttsEvents": [], "mindEvents": []}
        run = {"turns": [turn(0, "fast", "Hei kaikki"), turn(1, "fast", "Moi!"), turn(2, "slow", "Verda, miten menee?"),
                         turn(3, "slow", "Hei VERDA")]}
        learned = pv.learn_from([run])
        self.assertEqual(learned["modelOrder"]["mind"], ["slow"])  # fast never named the next pet -> score 0
        self.assertEqual(learned["modelStats"]["mind"]["slow"]["namedNextRate"], 1.0)
        self.assertIsNone(pv.addressed_next({**run["turns"][0], "mustAddressNext": False}, {}))

    def test_language_drift_is_judged_by_the_next_listener(self):
        base = {"status": "ok", "voice": "Kore", "ttsModel": "tts", "ttsVariant": "v", "ttsLatencyS": 1, "mindLatencyS": 1,
                "ttsEvents": [], "mindEvents": [], "text": "x", "heardAccuracy": 0.9, "mindModel": "m", "speakerSlug": "x"}
        run = {"turns": [{**base, "turnId": "r.t0", "inReplyTo": None, "language": "da-DK", "heardLanguage": ""},
                         {**base, "turnId": "r.t1", "inReplyTo": "r.t0", "language": "fi-FI", "heardLanguage": "da"},
                         {**base, "turnId": "r.t2", "inReplyTo": "r.t1", "language": "ko-KR", "heardLanguage": "Danish"}]}
        learned = pv.learn_from([run])
        self.assertEqual(learned["languageKept"]["da-DK"]["rate"], 1.0)
        self.assertEqual(learned["languageKept"]["fi-FI"]["rate"], 0.0)  # fi-FI pet answered in Danish
        self.assertEqual(pv.summarize(run["turns"])["languageKeptRate"], 0.5)
        self.assertIn("even if you heard another language", pv.turn_prompt(1, False, pv.persona("rokoko"), pv.persona("s-pankki"), "fi-FI"))

    def test_paraphrasing_voice_is_not_blamed_on_the_voice_language_pair(self):
        base = {"status": "ok", "ttsVariant": "live-recite", "ttsLatencyS": 1, "mindLatencyS": 1, "mindModel": "m",
                "ttsEvents": [], "mindEvents": [], "speakerSlug": "x", "language": "en-US", "voice": "Gacrux"}
        run = {"turns": [{**base, "turnId": "r.t0", "inReplyTo": None, "text": "Hello Modal, how do you scale jobs?",
                          "ttsModel": "live:x", "ttsSpoken": "Scaling jobs is easy with queues.", "ttsFidelity": 0.2},
                         {**base, "turnId": "r.t1", "inReplyTo": "r.t0", "text": "x", "ttsModel": "tts",
                          "heard": "Scaling jobs is easy with queues.", "heardAccuracy": 0.2}]}
        learned = pv.learn_from([run])
        self.assertEqual(learned["voiceLanguage"]["Gacrux|en-US"]["mean"], 1.0)      # the voice was clear
        self.assertEqual(learned["modelStats"]["tts"]["live:x"]["meanFidelity"], 0.2)  # the model went off-script


class Delivery(unittest.TestCase):
    def test_icloud_sync_overwrites_and_reports_failures_without_raising(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "a.txt", Path(d) / "out" / "turns" / "a.txt"
            src.write_text("new")
            dst.parent.mkdir(parents=True)
            dst.write_text("old")
            self.assertEqual(pv.sync_to_icloud([(src, dst)]), [])
            self.assertEqual(dst.read_text(), "new")
            self.assertEqual(pv.sync_to_icloud([(Path(d) / "missing", dst)], attempts=1), ["a.txt"])


if __name__ == "__main__":
    unittest.main()
