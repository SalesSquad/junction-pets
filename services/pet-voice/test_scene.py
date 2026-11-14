"""Offline checks for the scene engine (no network, no key). Run: python3 -m unittest services/pet-voice/test_scene.py"""
import json
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pet_voice as pv  # noqa: E402
import scene  # noqa: E402


def h(turn, slug, text):
    return {"turn": turn, "slug": slug, "name": pv.persona(slug)["name"], "text": text, "heardText": text}


class Bibles(unittest.TestCase):
    def test_every_pet_has_a_complete_bible_and_every_scene_is_valid(self):
        chars, slugs = scene.characters(), pv.all_pet_slugs()
        self.assertEqual(sorted(chars), slugs)
        for s, c in chars.items():
            for field in ("core", "speech", "anchors", "catchphrases", "never", "delivery", "voice_design"):
                self.assertTrue(c.get(field), f"{s}.{field}")
            self.assertTrue(all(o in chars for o in c["relationships"]), s)
            self.assertNotRegex(c["delivery"], scene.PHYSICAL, s)
        scenes = scene.load("scenes.json")["scenes"]
        on_stage = {p for sc in scenes.values() for p in sc["cast"]}
        self.assertEqual(on_stage, set(slugs))  # all 34 pets appear in some scene
        for sid, sc in scenes.items():
            self.assertIn(sc["opener"], sc["cast"], sid)
            self.assertGreaterEqual(sc["turns"], len(sc["cast"]), sid)


class Checks(unittest.TestCase):
    def test_tics_and_rules_are_caught(self):
        hist = [h(0, "google-deepmind", "Interesting. Show me the logs."), h(1, "openai-codex", "Okay, running it [sighs]")]
        p = scene.check_line("google-deepmind", "Interesting. [laughs] Again?", "calm", "en-GB", hist)
        self.assertTrue(any("catchphrase" in x for x in p))
        self.assertTrue(any("tag budget" in x for x in p))
        p = scene.check_line("openai-codex", "Give me ten minutes and one failing test.", "fast", "en-US", [])
        self.assertIn("reuses an example line", p)
        p = scene.check_line("rokoko", "Det er sjovt", "gestures wildly at the robot", "da-DK", [])
        self.assertTrue(any("body movement" in x for x in p))
        p = scene.check_line("featherless", "Let's test it now", "quick", "ja-JP", [])
        self.assertIn("not written in the language's native script", p)
        self.assertEqual(scene.check_line("aalto-university", "No joo. Kokeillaan.", "soft, slow", "fi-FI", []), [])
        p = scene.check_line("bahn-express", "Great idea, let's leverage that.", "crisp", "de-DE", [])
        self.assertIn("opens with praise or validation", p)
        self.assertIn("buzzword", p)

    def test_question_streak_and_same_opener(self):
        hist = [h(0, "rokoko", "Hvad nu?"), h(1, "aalto-university", "Miks?"), h(2, "rokoko", "Altså, hvorfor?")]
        p = scene.check_line("rokoko", "Altså, robotten danser?", "bouncy", "da-DK", hist)
        self.assertIn("too many questions in a row", p)
        self.assertIn("same opening words as your previous line", p)


class Director(unittest.TestCase):
    def test_fallback_prefers_the_called_pet_then_the_quietest(self):
        cast = ["bahn-express", "openai-codex", "rokoko"]
        counts = {"bahn-express": 2, "openai-codex": 0, "rokoko": 1}
        self.assertEqual(scene.fallback_next(cast, [h(0, "bahn-express", "Rokoko, jetzt.")], counts, random.Random(1)), "rokoko")
        self.assertEqual(scene.fallback_next(cast, [h(0, "bahn-express", "Los.")], counts, random.Random(1)), "openai-codex")

    def test_an_argument_may_run_then_a_third_voice_enters(self):
        cast = ["bahn-express", "openai-codex", "rokoko", "aalto-university"]
        hist = [h(0, "bahn-express", "Los."), h(1, "openai-codex", "Nope."), h(2, "bahn-express", "Doch.")]
        counts = {"bahn-express": 2, "openai-codex": 1, "rokoko": 0, "aalto-university": 0}
        self.assertEqual(scene.blocked(cast, hist, counts), {"bahn-express"})          # A-B-A: B may answer
        hist.append(h(3, "openai-codex", "Still no."))
        counts["openai-codex"] = 2
        self.assertEqual(scene.blocked(cast, hist, counts), {"bahn-express", "openai-codex"})  # A-B-A-B: third voice
        self.assertIn(scene.fallback_next(cast, hist, counts, random.Random(2)), ("rokoko", "aalto-university"))
        self.assertEqual(scene.blocked(cast[:2], hist, {"bahn-express": 2, "openai-codex": 2}), {"openai-codex"})
        self.assertEqual(scene.blocked(cast, hist[:2], {**counts, "bahn-express": 3}),
                         {"openai-codex", "bahn-express"})                              # solo cap while others wait

    def test_everyone_gets_a_turn_before_the_scene_ends(self):
        sc = {"cast": ["bahn-express", "openai-codex", "rokoko"], "opener": "bahn-express", "setup": "x"}
        d = scene.direct(sc, [h(0, "bahn-express", "Los.")], {"bahn-express": 1, "openai-codex": 0, "rokoko": 0}, 2, "", [], random.Random(3))
        self.assertIn(d["next"], ("openai-codex", "rokoko"))
        self.assertEqual(d["by"], "rule")


class Critic(unittest.TestCase):
    def test_hard_problem_gets_a_second_critic_round(self):
        anchor = scene.characters()["bahn-express"]["anchors"][1]
        replies = iter([({"heard": "", "heard_language": "", "line": anchor, "voice_direction": "flat, fast"}, "w", 0.1),
                        ({"verdict": "keep", "problems": [], "line": anchor, "voice_direction": "flat"}, "c", 0.1),
                        ({"verdict": "rewrite", "problems": ["anchor"], "line": "Codex. Gleis drei. Jetzt.",
                          "voice_direction": "clipped, loud"}, "c", 0.1)])
        orig = scene.gen_json
        scene.gen_json = lambda *a, **k: next(replies)
        try:
            sc = {"setup": "x", "cast": ["bahn-express", "openai-codex"], "beats": {}}
            out = scene.write_turn(sc, "bahn-express", "react", [], None, {}, "", [], True)
        finally:
            scene.gen_json = orig
        self.assertEqual(out["line"], "Codex. Gleis drei. Jetzt.")
        self.assertEqual(out["critic"]["rounds"], 2)
        self.assertEqual(out["problems"], [])


class Taste(unittest.TestCase):
    def test_ratings_become_taste_and_steer_voice(self):
        import tempfile
        import listen
        with tempfile.TemporaryDirectory() as d:
            orig_l, orig_s = listen.TASTE_FILE, scene.TASTE_FILE
            listen.TASTE_FILE = scene.TASTE_FILE = Path(d) / "taste.json"
            try:
                key = {"scenes": {"p1": {"X": {"label": "v2", "run": "a"}, "Y": {"label": "baseline", "run": "b"}}},
                       "voices": {"rokoko": {"A": "prebuilt", "B": "designed"}}}
                lines = {"p1-X-3": {"slug": "rokoko", "text": "Robotten danser."}}
                t = listen.ingest([{"id": "p1", "choice": "X", "reasons": ["hauskempi"], "lines": {"p1-X-3": "up"}, "note": "Lisää tätä"},
                                   {"id": "voice-rokoko", "choice": "A"}], key, lines)
                self.assertEqual(t["systems"]["v2"]["wins"], 1)
                self.assertEqual(t["systems"]["baseline"]["losses"], 1)
                self.assertEqual(t["pets"]["rokoko"]["liked"], ["Robotten danser."])
                self.assertEqual(scene.voice_for("rokoko"), pv.load_voices()["rokoko"]["voice"])  # prebuilt preferred
                self.assertIn("Robotten danser.", scene.system_prompt("rokoko", ["rokoko"], "da-DK", []))
            finally:
                listen.TASTE_FILE, scene.TASTE_FILE = orig_l, orig_s

    def test_stage_directions_are_removed_and_flagged(self):
        self.assertEqual(scene.clean_line("(fast) Ship it. *laughs*"), "Ship it.")
        self.assertIn("stage direction inside the spoken line", scene.check_line("openai-codex", "(fast) Ship it.", "quick", "en-US", []))


if __name__ == "__main__":
    unittest.main()
