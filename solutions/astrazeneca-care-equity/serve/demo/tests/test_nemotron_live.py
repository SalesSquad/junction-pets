"""Tests for serve/demo/nemotron_live.py (live second reader). Standard library only; the endpoint is mocked, no call
is sent and no key is real.

Run: python3 -m unittest discover -s serve/demo/tests -p 'test_nemotron_live.py'
"""

import io
import json
import pathlib
import socket
import sys
import unittest
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE.parent))

import nemotron_live as L  # noqa: E402

KEY = "dummy-key-for-tests-0000"
ENV = {"VERDA_INFERENCE_BASE_URL": "https://endpoint.invalid/v1", "VERDA_INFERENCE_KEY": KEY}
NOTE = {"id": "t1", "note_date": "2025-03-10", "note_text": "Lähete lähetettiin 12.2.2025. Hoito aloitettiin 3 viikkoa sitten."}


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(answers, seen):
    def urlopen(req, timeout):
        seen.append({"url": req.full_url, "auth": req.get_header("Authorization"), "body": json.loads(req.data), "timeout": timeout})
        a = answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return _Resp(json.dumps({"choices": [{"message": {"content": a}, "finish_reason": "stop"}], "usage": {}}).encode())
    return urlopen


class LiveReader(unittest.TestCase):
    def test_frozen_v3_request_and_code_resolved_dates(self):
        seen = []
        ans = '{"entry_route":"PUBLIC_PRIMARY","events":[{"type":"REFERRAL_SENT","date":{"kind":"ABSOLUTE","date":"2025-02-12"}},{"type":"TREATMENT_START","date":{"kind":"WEEKS_AGO","n":3}}]}'
        out = L.read_live(NOTE, env=ENV, urlopen=fake_urlopen([ans], seen))
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["prediction"], {"entry_route": "PUBLIC_PRIMARY", "events": [
            {"type": "REFERRAL_SENT", "date": "2025-02-12", "precision": "DAY"},
            {"type": "TREATMENT_START", "date": "2025-02-17", "precision": "DAY"}]})
        self.assertEqual((out["model"], out["version"], out["calls"], out["flagged"]), ("nemotron-3.5-super-vl", "v3", 1, False))
        body = seen[0]["body"]
        self.assertEqual(seen[0]["url"], "https://endpoint.invalid/v1/chat/completions")
        self.assertEqual(body["messages"], L.R.messages(NOTE, "expression"))  # the frozen prompt, unchanged
        self.assertEqual((body["model"], body["temperature"], body["max_tokens"]), (L.NC.MODEL, 0.0, L.R.MAX_TOKENS_THINKING))
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": True})
        self.assertLessEqual(seen[0]["timeout"], L.DEFAULT_TIMEOUT_S)
        self.assertNotIn(KEY, json.dumps(out))

    def test_no_key(self):
        for env in ({}, {"VERDA_INFERENCE_BASE_URL": "https://endpoint.invalid/v1"}, {"VERDA_INFERENCE_KEY": KEY}):
            out = L.read_live(NOTE, env=env, urlopen=fake_urlopen([], []))
            self.assertEqual((out["ok"], out["kind"]), (False, "no_key"))

    def test_failures_are_plain_and_never_carry_the_key(self):
        cases = [
            (urllib.error.HTTPError("https://endpoint.invalid/v1/chat/completions", 401, "Unauthorized " + KEY, {}, None), "http", "HTTP 401"),
            (urllib.error.URLError(ConnectionRefusedError("refused")), "network", "could not be reached"),
            (urllib.error.URLError(socket.timeout("timed out")), "timeout", "did not answer in time"),
            (TimeoutError(), "timeout", "did not answer in time"),
        ]
        for exc, kind, text in cases:
            out = L.read_live(NOTE, env=ENV, urlopen=fake_urlopen([exc], []))
            self.assertEqual((out["ok"], out["kind"]), (False, kind), out)
            self.assertIn(text, out["error"])
            self.assertNotIn(KEY, json.dumps(out))
            self.assertNotIn("endpoint.invalid", json.dumps(out))

    def test_bad_input(self):
        for bad in ({}, {"note_text": "x", "note_date": "2025-02-30"}, {"note_text": "", "note_date": "2025-02-03"}):
            self.assertEqual(L.read_live(bad, env=ENV, urlopen=fake_urlopen([], []))["kind"], "input")

    def test_unparsable_answer_is_an_answer_without_prediction(self):
        out = L.read_live(NOTE, env=ENV, urlopen=fake_urlopen(["not json", "still not json"], []))
        self.assertTrue(out["ok"])
        self.assertIsNone(out["prediction"])
        self.assertEqual((out["calls"], out["flagged"]), (2, True))


if __name__ == "__main__":
    unittest.main()
