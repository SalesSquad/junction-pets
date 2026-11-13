import contextlib
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import urllib.error

SPEC = importlib.util.spec_from_file_location("pilot", Path(__file__).with_name("pilot.py"))
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
SHA = "a" * 40
MODEL = "fixture-model-v1"
KEY = "private-test-key-never-log"
RESULT = {"route": "needs_evidence", "response": "A manifest exists; live execution remains unproven."}


def response(provider, model=MODEL):
    text = json.dumps(RESULT)
    if provider == "openai":
        return {"object": "response", "status": "completed", "id": "resp_fixture", "model": model,
                "output": [{"type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": text}]}],
                "usage": {"input_tokens": 180, "output_tokens": 30}}
    if provider == "anthropic":
        return {"type": "message", "role": "assistant", "stop_reason": "end_turn",
                "id": "msg_fixture", "model": model, "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 180, "output_tokens": 30}}
    if provider == "gemini":
        return {"modelVersion": model, "responseId": "response_fixture",
                "candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": text}]}}],
                "usageMetadata": {"promptTokenCount": 180, "candidatesTokenCount": 30}}
    return {"model": model, "answers": {
        "route": {"type": "choice", "choice": "needs_evidence", "confidence": 0.95,
                  "probabilities": {"needs_evidence": 0.95, "respond": 0.03, "review": 0.02}},
        "evidence_supports_live": {"type": "noul", "noul": 0.01}},
        "usage": {"input_tokens": 180, "output_tokens": 15}}


class NoEnvironment:
    def get(self, *args):
        raise AssertionError("plan read credentials")


class PilotTests(unittest.TestCase):
    def invoke(self, provider, value=None, model=MODEL, headers=None, source_check=None):
        observed = []
        def transport(endpoint, body, request_headers):
            observed.append((endpoint, json.loads(body), request_headers))
            return json.dumps(value if value is not None else response(provider)).encode(), headers or {"x-request-id": "req_fixture"}
        receipt = pilot.run(provider, model, SHA, True,
                            env={pilot.PROVIDERS[provider][1]: KEY}, transport=transport,
                            source_check=source_check or (lambda _: None))
        return receipt, observed

    def test_default_plan_reads_no_credentials_network_or_source(self):
        for provider in pilot.PROVIDERS:
            with self.subTest(provider=provider), patch.object(pilot, "verify_checkout", side_effect=AssertionError), patch.object(pilot, "http_post", side_effect=AssertionError):
                result = pilot.run(provider, MODEL, SHA, env=NoEnvironment())
                self.assertEqual(result["mode"], "plan-only")
                self.assertFalse(result["executed"])
                self.assertFalse(result["exactModelVerified"])

    def test_all_provider_success_shapes_and_first_party_requests(self):
        for provider in pilot.PROVIDERS:
            with self.subTest(provider=provider):
                checks = []
                result, calls = self.invoke(provider, source_check=checks.append)
                self.assertEqual(checks, [SHA, SHA])
                self.assertEqual(len(calls), 1)
                self.assertEqual(result["result"]["route"], "needs_evidence")
                self.assertEqual(result["requestedModel"], MODEL)
                self.assertEqual(result["returnedModel"], MODEL)
                self.assertTrue(result["exactModelVerified"])
                self.assertFalse(result["providerInvocationObserved"])
                self.assertFalse(result["chibiHostVerified"])
                self.assertEqual(result["qualifiedPasses"], 0)
                self.assertEqual(result["requestId"], "req_fixture")
                self.assertGreaterEqual(result["latencyMs"], 0)
                self.assertNotIn(KEY, json.dumps(result))
                endpoint, body, headers = calls[0]
                self.assertTrue(endpoint.startswith(pilot.PROVIDERS[provider][0]))
                self.assertNotIn(KEY, endpoint)
                self.assertNotIn(KEY, json.dumps(body))
                self.assertEqual(headers["Content-Type"], "application/json")
                if provider == "openai": self.assertEqual(body["max_output_tokens"], 512)
                if provider == "anthropic": self.assertEqual(body["max_tokens"], 512)
                if provider == "gemini": self.assertEqual(body["generationConfig"]["maxOutputTokens"], 512)
                if provider == "typesafe":
                    self.assertIsNone(result["result"]["response"])
                    self.assertFalse(result["outputTokenLimitEnforcedByRequest"])
                    self.assertEqual(set(body["questions"]), {"route", "evidence_supports_live"})

    def test_returned_alias_does_not_claim_exact_model(self):
        result, _ = self.invoke("typesafe", response("typesafe", "resolved-version-v2"))
        self.assertFalse(result["exactModelVerified"])
        self.assertEqual(result["returnedModel"], "resolved-version-v2")

    def test_anthropic_optional_thinking_is_accepted_without_receipt_disclosure(self):
        thinking = {"type": "thinking", "thinking": "private-reasoning-canary", "signature": "signature-canary"}
        redacted = {"type": "redacted_thinking", "data": "redacted-reasoning-canary"}
        for prefix in ([thinking], [redacted], [thinking, redacted]):
            value = response("anthropic")
            value["content"] = deepcopy(prefix) + value["content"]
            with self.subTest(types=[block["type"] for block in prefix]):
                receipt, _ = self.invoke("anthropic", value)
                self.assertEqual(receipt["result"], RESULT)
                self.assertEqual(receipt["usage"]["outputTokens"], 30)
                serialized = json.dumps(receipt)
                for canary in ("private-reasoning-canary", "signature-canary", "redacted-reasoning-canary"):
                    self.assertNotIn(canary, serialized)

    def test_anthropic_malformed_duplicate_and_effect_blocks_are_refused(self):
        thinking = {"type": "thinking", "thinking": "analysis", "signature": "signature"}
        text = response("anthropic")["content"][0]
        bad = [[thinking], [{"type": "thinking", "thinking": "analysis"}, text],
               [{"type": "thinking", "thinking": "analysis", "signature": 1}, text],
               [{"type": "redacted_thinking"}, text],
               [{"type": "redacted_thinking", "data": ""}, text],
               [{"type": "tool_use", "id": "tool", "name": "run", "input": {}}, text],
               [{"type": "unknown"}, text], [thinking, deepcopy(thinking), text],
               [text, deepcopy(text)], [None, text]]
        for content in bad:
            value = response("anthropic")
            value["content"] = deepcopy(content)
            with self.subTest(content=content), self.assertRaisesRegex(pilot.PilotError, "PROVIDER_OUTPUT_INVALID"):
                self.invoke("anthropic", value)

    def test_invalid_options_fail_before_environment_or_network(self):
        cases = [("other", MODEL, SHA, False), ("openai", "x/../../secret", SHA, False),
                 ("openai", "x?key=bad", SHA, False), ("openai", "", SHA, False),
                 ("openai", "x" * 129, SHA, False), ("openai", MODEL, "A" * 40, False),
                 ("openai", MODEL, "a" * 39, False), ("openai", MODEL, SHA, "yes")]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(pilot.PilotError):
                pilot.run(*args, env=NoEnvironment())

    def test_missing_credential_is_refused_without_transport(self):
        with patch.object(pilot, "http_post", side_effect=AssertionError), self.assertRaisesRegex(pilot.PilotError, "CREDENTIAL_UNAVAILABLE"):
            pilot.run("openai", MODEL, SHA, True, env={}, source_check=lambda _: None)

    def test_source_failure_precedes_secret_read(self):
        with self.assertRaisesRegex(pilot.PilotError, "SOURCE_HEAD_MISMATCH"):
            pilot.run("openai", MODEL, SHA, True, env=NoEnvironment(),
                      source_check=lambda _: pilot.fail("SOURCE_HEAD_MISMATCH"))

    def test_source_change_after_call_refuses_receipt(self):
        checks = []
        def check(_):
            checks.append(1)
            if len(checks) == 2: pilot.fail("SOURCE_NOT_CLEAN")
        with self.assertRaisesRegex(pilot.PilotError, "SOURCE_NOT_CLEAN"):
            self.invoke("openai", source_check=check)

    def test_wrong_provider_shapes_are_refused(self):
        for provider in pilot.PROVIDERS:
            wrong = response("typesafe" if provider != "typesafe" else "openai")
            with self.subTest(provider=provider), self.assertRaises(pilot.PilotError):
                self.invoke(provider, wrong)

    def test_jev_exact_answer_ids_types_probabilities(self):
        mutations = [
            lambda v: v["answers"].update(extra={"type": "noul", "noul": .1}),
            lambda v: v["answers"].pop("route"),
            lambda v: v["answers"]["route"].update(type="score"),
            lambda v: v["answers"]["route"].update(choice="approve"),
            lambda v: v["answers"]["route"].update(confidence=True),
            lambda v: v["answers"]["route"].update(probabilities={"needs_evidence": 1}),
            lambda v: v["answers"]["route"]["probabilities"].update(respond=0.9),
            lambda v: v["answers"]["evidence_supports_live"].update(noul=1.1),
            lambda v: v["answers"]["evidence_supports_live"].update(noul=True),
            lambda v: v["answers"]["evidence_supports_live"].update(type="choice"),
        ]
        for mutate in mutations:
            value = response("typesafe")
            mutate(value)
            with self.subTest(value=value), self.assertRaises(pilot.PilotError):
                self.invoke("typesafe", value)

    def test_generator_output_schema_is_strict(self):
        bad = [{"route": "approve", "response": "yes"}, {"route": "respond", "response": ""},
               {"route": "respond", "response": "x" * 1201}, {"route": "review", "response": "x", "tool": "run"},
               {"route": "respond", "response": None}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(pilot.PilotError):
                pilot.generated_result(json.dumps(value))

    def test_unexpected_tools_and_truncation_are_refused(self):
        value = response("openai")
        value["output"].append({"type": "function_call"})
        with self.assertRaisesRegex(pilot.PilotError, "UNEXPECTED_PROVIDER_EFFECT"):
            self.invoke("openai", value)
        for provider in ("openai", "anthropic", "gemini"):
            value = response(provider)
            if provider == "openai": value["status"] = "incomplete"
            if provider == "anthropic": value["stop_reason"] = "max_tokens"
            if provider == "gemini": value["candidates"][0]["finishReason"] = "MAX_TOKENS"
            with self.subTest(provider=provider), self.assertRaisesRegex(pilot.PilotError, "INCOMPLETE"):
                self.invoke(provider, value)

    def test_usage_and_response_bounds(self):
        for provider in pilot.PROVIDERS:
            value = response(provider)
            usage = value["usageMetadata"] if provider == "gemini" else value["usage"]
            output_key = "candidatesTokenCount" if provider == "gemini" else "output_tokens"
            for count in (True, -1, 513, "20"):
                usage[output_key] = count
                with self.subTest(provider=provider, count=count), self.assertRaises(pilot.PilotError):
                    self.invoke(provider, value)
        with self.assertRaisesRegex(pilot.PilotError, "RESPONSE_TOO_LARGE"):
            pilot.parse_response("typesafe", b"x" * (pilot.MAX_BYTES + 1))
        with self.assertRaisesRegex(pilot.PilotError, "REQUEST_TOO_LARGE"), patch.object(pilot, "FIXTURE", {"input": "x" * pilot.MAX_BYTES}):
            pilot.make_request("openai", MODEL)

    def test_malformed_duplicate_and_nonfinite_json_refused(self):
        for raw in (b"not json", b'{"a":1,"a":2}', b'{"p":NaN}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(pilot.PilotError): pilot.parse_json(raw)

    def test_secret_echo_and_provider_errors_never_leak(self):
        value = response("openai")
        value["output"][0]["content"][0]["text"] = json.dumps({"route": "respond", "response": KEY})
        with self.assertRaisesRegex(pilot.PilotError, "PROVIDER_RESPONSE_REFUSED") as error:
            self.invoke("openai", value)
        self.assertNotIn(KEY, str(error.exception))
        result, _ = self.invoke("openai", headers={"x-request-id": KEY})
        self.assertIsNone(result["requestId"])
        def broken(*_): raise RuntimeError(KEY)
        with self.assertRaisesRegex(pilot.PilotError, "TRANSPORT_FAILED") as error:
            pilot.run("openai", MODEL, SHA, True, env={"OPENAI_API_KEY": KEY}, transport=broken, source_check=lambda _: None)
        self.assertNotIn(KEY, str(error.exception))
        self.assertEqual(str(pilot.PilotError(KEY)), "INTERNAL_FAILURE")

    def test_http_error_redaction_no_retry_and_redirect_refusal(self):
        for status, code in ((401, "AUTH_REFUSED"), (402, "CREDIT_REFUSED"), (429, "RATE_LIMITED"), (500, "HTTP_STATUS_REFUSED")):
            error_body = io.BytesIO(KEY.encode())
            class BrokenOpener:
                calls = 0
                def open(self, *args, **kwargs):
                    self.calls += 1
                    raise urllib.error.HTTPError("https://example.invalid/" + KEY, status, KEY, {}, error_body)
            opener = BrokenOpener()
            with self.subTest(status=status), patch.object(pilot.urllib.request, "build_opener", return_value=opener), self.assertRaisesRegex(pilot.PilotError, code):
                pilot.http_post("https://api.openai.com/v1/responses", b"{}", {})
            self.assertEqual(opener.calls, 1)
            self.assertTrue(error_body.closed)
        with self.assertRaisesRegex(pilot.PilotError, "REDIRECT_REFUSED"):
            pilot.NoRedirect().redirect_request(None, None, 302, KEY, {}, "https://evil.invalid")

    def test_decoded_escaped_credential_echo_is_refused_in_output_and_metadata(self):
        for field in ("nested_response", "returned_model", "response_id"):
            value = response("openai")
            if field == "nested_response":
                nested = json.dumps({"route": "respond", "response": KEY}).replace("-", r"\u002d")
                value["output"][0]["content"][0]["text"] = nested
            elif field == "returned_model":
                value["model"] = KEY
            else:
                value["id"] = KEY
            # Both outer metadata and the inner generated JSON can escape secrets.
            raw = json.dumps(value).replace("-", r"\u002d").encode()
            self.assertNotIn(KEY.encode(), raw)
            def escaped_transport(*_):
                return raw, {"x-request-id": "req_fixture"}
            with self.subTest(field=field), self.assertRaisesRegex(pilot.PilotError, "PROVIDER_RESPONSE_REFUSED") as error:
                pilot.run("openai", MODEL, SHA, True, env={"OPENAI_API_KEY": KEY},
                          transport=escaped_transport, source_check=lambda _: None)
            self.assertNotIn(KEY, str(error.exception))

    def test_receipt_string_guard_checks_keys_and_rejects_unexpected_objects(self):
        for value in ({KEY: "safe"}, {"nested": ["safe", {"value": KEY}]}, {"unexpected": object()}):
            with self.subTest(shape=type(value).__name__), self.assertRaises(pilot.PilotError) as error:
                pilot.verify_receipt_strings(value, KEY)
            self.assertNotIn(KEY, str(error.exception))

    def test_checkout_requires_exact_clean_origin(self):
        def proc(value): return subprocess.CompletedProcess([], 0, value, "")
        for outputs, code in ((["b" * 40], "SOURCE_HEAD_MISMATCH"), ([SHA, "?? dirty"], "SOURCE_NOT_CLEAN"),
                              ([SHA, "", "https://github.com/other/repo.git"], "SOURCE_ORIGIN_MISMATCH")):
            with self.subTest(code=code), patch.object(pilot.subprocess, "run", side_effect=[proc(x) for x in outputs]), self.assertRaisesRegex(pilot.PilotError, code):
                pilot.verify_checkout(SHA, Path("/synthetic-source"))
        with patch.object(pilot.subprocess, "run", side_effect=[proc(SHA), proc(""), proc("git@github.com:SalesSquad/junction-pets.git")]):
            pilot.verify_checkout(SHA, Path("/synthetic-source"))

    def test_cli_requires_explicit_execute_and_redacts_invalid_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(pilot, "http_post", side_effect=AssertionError):
            self.assertEqual(pilot.main(["--provider", "openai", "--model", MODEL, "--source-commit", SHA]), 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "plan-only")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(pilot.main(["--provider", KEY]), 2)
        self.assertNotIn(KEY, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["errorCode"], "INVALID_OPTIONS")


if __name__ == "__main__":
    unittest.main()
