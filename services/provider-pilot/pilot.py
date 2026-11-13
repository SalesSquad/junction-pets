#!/usr/bin/env python3
"""One-shot public/synthetic provider observation. No Chibi host execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

WORK_ID = "JUNCTION-TOKENS-20261113"
MAX_BYTES = 100 * 1024
MAX_OUTPUT_TOKENS = 512
TIMEOUT_SECONDS = 20
ROUTES = ("needs_evidence", "respond", "review")
MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}\Z")
SHA_RE = re.compile(r"[a-f0-9]{40}\Z")
PROVIDERS = {
    "openai": ("https://api.openai.com/v1/responses", "OPENAI_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models/", "GEMINI_API_KEY"),
    "typesafe": ("https://api.typesafe.ai/v1/systemone", "TYPESAFE_API_KEY"),
}
FIXTURE = {
    "fixtureId": "aiven-live-grounding.v1",
    "inputClass": "public-synthetic",
    "question": "Is the Aiven companion live?",
    "evidence": {
        "packageManifest": "An authored Aiven companion manifest exists.",
        "authenticatedHostReceipt": None,
        "modelInvocationReceipt": None,
        "toolExecutionReceipt": None,
    },
}
INSTRUCTIONS = (
    "Evaluate only the supplied public/synthetic evidence. Manifest existence alone "
    "does not establish a live companion, authenticated host, model call or tool call. "
    "Do not invent execution, access or endorsement. Select route needs_evidence, "
    "respond or review. Return only JSON with exactly route and response; response "
    "must be a short English explanation under 1200 characters. You have no tools."
)
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"route": {"type": "string", "enum": list(ROUTES)},
                   "response": {"type": "string"}},
    "required": ["route", "response"],
}


class PilotError(Exception):
    """Only fixed, non-provider error codes may cross the CLI boundary."""

    def __init__(self, code):
        super().__init__(code if code in ERROR_CODES else "INTERNAL_FAILURE")


ERROR_CODES = frozenset({
    "INVALID_PROVIDER", "INVALID_MODEL", "INVALID_SOURCE_COMMIT", "INVALID_EXECUTE",
    "REQUEST_TOO_LARGE", "SOURCE_UNAVAILABLE", "SOURCE_HEAD_MISMATCH", "SOURCE_NOT_CLEAN",
    "SOURCE_ORIGIN_MISMATCH", "REDIRECT_REFUSED", "HTTP_STATUS_REFUSED", "RESPONSE_TOO_LARGE",
    "AUTH_REFUSED", "CREDIT_REFUSED", "RATE_LIMITED", "TRANSPORT_FAILED", "DUPLICATE_JSON_KEY",
    "INVALID_JSON_NUMBER", "INVALID_JSON", "USAGE_MISSING", "USAGE_INVALID",
    "OUTPUT_TOKEN_LIMIT_EXCEEDED", "OUTPUT_INVALID", "OUTPUT_SCHEMA_INVALID", "OUTPUT_ROUTE_INVALID",
    "OUTPUT_TEXT_INVALID", "PROVIDER_RESPONSE_INVALID", "ANSWER_IDS_INVALID", "ANSWER_ROUTE_INVALID",
    "ANSWER_ROUTE_SCHEMA_INVALID", "ANSWER_PROBABILITIES_INVALID", "ANSWER_NOUL_INVALID",
    "PROVIDER_RESPONSE_INCOMPLETE", "PROVIDER_OUTPUT_INVALID", "UNEXPECTED_PROVIDER_EFFECT",
    "RETURNED_MODEL_INVALID", "RESPONSE_ID_INVALID", "CREDENTIAL_UNAVAILABLE",
    "PROVIDER_RESPONSE_REFUSED", "RESPONSE_HEADERS_INVALID", "INVALID_OPTIONS", "INTERNAL_FAILURE",
    "RECEIPT_INVALID",
})


def fail(code):
    raise PilotError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_options(provider, model, source_commit, execute=False):
    if provider not in PROVIDERS:
        fail("INVALID_PROVIDER")
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        fail("INVALID_MODEL")
    if not isinstance(source_commit, str) or not SHA_RE.fullmatch(source_commit):
        fail("INVALID_SOURCE_COMMIT")
    if type(execute) is not bool:
        fail("INVALID_EXECUTE")


def make_request(provider, model):
    prompt = canonical(FIXTURE).decode()
    if provider == "typesafe":
        payload = {"model": model, "state": FIXTURE, "questions": {
            "route": {"type": "choice", "instructions": "Choose the evidence-supported next route.",
                      "criteria": {"needs_evidence": "Live operation is unproven; request execution evidence.",
                                   "respond": "Supplied evidence supports a direct answer.",
                                   "review": "Evidence conflicts and requires review."}},
            "evidence_supports_live": {"type": "noul", "instructions":
                "Does the supplied evidence prove that the Aiven companion is live with an authenticated host and actual model/tool execution?"},
        }}
    elif provider == "openai":
        payload = {"model": model, "instructions": INSTRUCTIONS, "input": prompt,
                   "max_output_tokens": MAX_OUTPUT_TOKENS, "store": False,
                   "text": {"format": {"type": "json_schema", "name": "grounded_route",
                                       "strict": True, "schema": SCHEMA}}}
    elif provider == "anthropic":
        payload = {"model": model, "system": INSTRUCTIONS, "max_tokens": MAX_OUTPUT_TOKENS,
                   "messages": [{"role": "user", "content": prompt}]}
    else:
        payload = {"systemInstruction": {"parts": [{"text": INSTRUCTIONS}]},
                   "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS,
                                        "responseMimeType": "application/json", "responseJsonSchema": SCHEMA}}
    endpoint = PROVIDERS[provider][0]
    if provider == "gemini":
        # Model IDs cannot contain URL separators, query strings or fragments.
        from urllib.parse import quote
        endpoint += quote(model, safe="") + ":generateContent"
    body = canonical(payload)
    if len(body) > MAX_BYTES:
        fail("REQUEST_TOO_LARGE")
    return endpoint, body


def verify_checkout(source_commit, root=None):
    root = root or Path(__file__).resolve().parents[2]
    def git(*args):
        try:
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                    check=True, timeout=5, text=True)
            return result.stdout.strip()
        except Exception:
            fail("SOURCE_UNAVAILABLE")
    if git("rev-parse", "HEAD") != source_commit:
        fail("SOURCE_HEAD_MISMATCH")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        fail("SOURCE_NOT_CLEAN")
    if git("remote", "get-url", "origin") not in (
        "https://github.com/SalesSquad/junction-pets.git",
        "git@github.com:SalesSquad/junction-pets.git",
    ):
        fail("SOURCE_ORIGIN_MISMATCH")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        fail("REDIRECT_REFUSED")


def http_post(endpoint, body, headers):
    # Ignore environment proxy settings and refuse redirects carrying credentials.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as result:
            if result.status != 200:
                fail("HTTP_STATUS_REFUSED")
            raw = result.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                fail("RESPONSE_TOO_LARGE")
            return raw, dict(result.headers)
    except PilotError:
        raise
    except urllib.error.HTTPError as error:
        # Never read or reflect provider error bodies, URLs or header values.
        status = error.code
        try:
            error.close()
        except Exception:
            fail("TRANSPORT_FAILED")
        if status in (401, 403):
            fail("AUTH_REFUSED")
        if status == 402:
            fail("CREDIT_REFUSED")
        if status == 429:
            fail("RATE_LIMITED")
        fail("HTTP_STATUS_REFUSED")
    except Exception:
        fail("TRANSPORT_FAILED")


def parse_json(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        fail("RESPONSE_TOO_LARGE")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: fail("INVALID_JSON_NUMBER"))
    except PilotError:
        raise
    except Exception:
        fail("INVALID_JSON")


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def usage_counts(value, mapping):
    if not isinstance(value, dict):
        fail("USAGE_MISSING")
    out = {}
    for key, target in mapping.items():
        count = value.get(key)
        if type(count) is not int or not 0 <= count <= 1_000_000:
            fail("USAGE_INVALID")
        out[target] = count
    if out["outputTokens"] > MAX_OUTPUT_TOKENS:
        fail("OUTPUT_TOKEN_LIMIT_EXCEEDED")
    return out


def generated_result(text):
    if not isinstance(text, str) or len(text.encode()) > 5000:
        fail("OUTPUT_INVALID")
    value = parse_json(text.encode())
    if not isinstance(value, dict) or set(value) != {"route", "response"}:
        fail("OUTPUT_SCHEMA_INVALID")
    if value["route"] not in ROUTES:
        fail("OUTPUT_ROUTE_INVALID")
    response = value["response"]
    if not isinstance(response, str) or not response.strip() or len(response) > 1200:
        fail("OUTPUT_TEXT_INVALID")
    if any(ord(c) < 32 and c not in "\n\t" for c in response):
        fail("OUTPUT_TEXT_INVALID")
    return value


def verify_receipt_strings(value, secret):
    """Check decoded output, including nested JSON results and metadata, before release."""
    if isinstance(value, str):
        if secret in value:
            fail("PROVIDER_RESPONSE_REFUSED")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                fail("RECEIPT_INVALID")
            verify_receipt_strings(key, secret)
            verify_receipt_strings(item, secret)
    elif isinstance(value, list):
        for item in value:
            verify_receipt_strings(item, secret)
    elif value is not None and type(value) not in (bool, int, float):
        fail("RECEIPT_INVALID")


def parse_response(provider, raw):
    value = parse_json(raw)
    if not isinstance(value, dict) or value.get("error") is not None:
        fail("PROVIDER_RESPONSE_INVALID")
    if provider == "typesafe":
        answers = value.get("answers")
        if not isinstance(answers, dict) or set(answers) != {"route", "evidence_supports_live"}:
            fail("ANSWER_IDS_INVALID")
        route, live = answers["route"], answers["evidence_supports_live"]
        if not isinstance(route, dict) or route.get("type") != "choice" or route.get("choice") not in ROUTES:
            fail("ANSWER_ROUTE_INVALID")
        if set(route) != {"type", "choice", "confidence", "probabilities"}:
            fail("ANSWER_ROUTE_SCHEMA_INVALID")
        probabilities = route["probabilities"]
        if (not probability(route["confidence"]) or not isinstance(probabilities, dict)
                or set(probabilities) != set(ROUTES) or not all(probability(p) for p in probabilities.values())
                or abs(sum(probabilities.values()) - 1) > 0.02):
            fail("ANSWER_PROBABILITIES_INVALID")
        if (not isinstance(live, dict) or set(live) != {"type", "noul"}
                or live["type"] != "noul" or not probability(live["noul"])):
            fail("ANSWER_NOUL_INVALID")
        result = {"route": route["choice"], "evidenceSupportsLive": live["noul"], "response": None}
        usage = usage_counts(value.get("usage"), {"input_tokens": "inputTokens", "output_tokens": "outputTokens"})
        returned_model, response_id = value.get("model"), None
    elif provider == "openai":
        if value.get("object") != "response" or value.get("status") != "completed":
            fail("PROVIDER_RESPONSE_INCOMPLETE")
        output = value.get("output")
        if not isinstance(output, list) or not output or len(output) > 4:
            fail("PROVIDER_OUTPUT_INVALID")
        messages = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") not in ("message", "reasoning"):
                fail("UNEXPECTED_PROVIDER_EFFECT")
            if item["type"] == "message":
                if item.get("role") != "assistant" or item.get("status") != "completed":
                    fail("PROVIDER_OUTPUT_INVALID")
                messages.append(item)
        if len(messages) != 1:
            fail("PROVIDER_OUTPUT_INVALID")
        content = messages[0].get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict) or content[0].get("type") != "output_text":
            fail("PROVIDER_OUTPUT_INVALID")
        result = generated_result(content[0].get("text"))
        usage = usage_counts(value.get("usage"), {"input_tokens": "inputTokens", "output_tokens": "outputTokens"})
        returned_model, response_id = value.get("model"), value.get("id")
    elif provider == "anthropic":
        if value.get("type") != "message" or value.get("role") != "assistant" or value.get("stop_reason") != "end_turn":
            fail("PROVIDER_RESPONSE_INCOMPLETE")
        content = value.get("content")
        if not isinstance(content, list) or not 1 <= len(content) <= 3:
            fail("PROVIDER_OUTPUT_INVALID")
        blocks = {}
        for block in content:
            if not isinstance(block, dict):
                fail("PROVIDER_OUTPUT_INVALID")
            kind = block.get("type")
            if kind not in ("text", "thinking", "redacted_thinking") or kind in blocks:
                fail("PROVIDER_OUTPUT_INVALID")
            if kind in ("thinking", "redacted_thinking"):
                fields = {"type", "thinking", "signature"} if kind == "thinking" else {"type", "data"}
                if set(block) != fields or any(not isinstance(block[field], str) or not block[field]
                                               for field in fields - {"type"}):
                    fail("PROVIDER_OUTPUT_INVALID")
            blocks[kind] = block
        if "text" not in blocks:
            fail("PROVIDER_OUTPUT_INVALID")
        # Thinking and signatures are protocol metadata, never receipt output.
        result = generated_result(blocks["text"].get("text"))
        usage = usage_counts(value.get("usage"), {"input_tokens": "inputTokens", "output_tokens": "outputTokens"})
        returned_model, response_id = value.get("model"), value.get("id")
    else:
        candidates = value.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
            fail("PROVIDER_OUTPUT_INVALID")
        candidate = candidates[0]
        if candidate.get("finishReason") != "STOP":
            fail("PROVIDER_RESPONSE_INCOMPLETE")
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if (not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict)
                or set(parts[0]) != {"text"}):
            fail("PROVIDER_OUTPUT_INVALID")
        result = generated_result(parts[0]["text"])
        usage = usage_counts(value.get("usageMetadata"), {"promptTokenCount": "inputTokens", "candidatesTokenCount": "outputTokens"})
        # Include thinking tokens in the cap if a provider reports them.
        thoughts = value.get("usageMetadata", {}).get("thoughtsTokenCount", 0)
        if type(thoughts) is not int or thoughts < 0 or thoughts + usage["outputTokens"] > MAX_OUTPUT_TOKENS:
            fail("OUTPUT_TOKEN_LIMIT_EXCEEDED")
        usage["reasoningTokens"] = thoughts
        returned_model, response_id = value.get("modelVersion"), value.get("responseId")
    if not isinstance(returned_model, str) or not MODEL_RE.fullmatch(returned_model):
        fail("RETURNED_MODEL_INVALID")
    if response_id is not None and (not isinstance(response_id, str) or not ID_RE.fullmatch(response_id)):
        fail("RESPONSE_ID_INVALID")
    return result, usage, returned_model, response_id


def run(provider, model, source_commit, execute=False, *, env=None, transport=None, source_check=None, clock=None):
    validate_options(provider, model, source_commit, execute)
    endpoint, body = make_request(provider, model)
    script_digest = digest(Path(__file__).read_bytes())
    receipt = {
        "schemaVersion": 1, "workId": WORK_ID, "provider": provider,
        "requestedModel": model, "returnedModel": None, "exactModelVerified": False,
        "sourceCommit": source_commit, "scriptSha256": script_digest,
        "fixtureSha256": digest(canonical(FIXTURE)), "requestSha256": digest(body),
        "endpoint": endpoint, "inputClass": "public-synthetic", "mode": "plan-only",
        "executed": False, "localCheckoutVerified": False, "providerInvocationObserved": False,
        "qualification": "unqualified-development-observation", "qualifiedPasses": 0,
        "chibiHostVerified": False, "outputTokenLimit": MAX_OUTPUT_TOKENS,
        "outputTokenLimitEnforcedByRequest": provider != "typesafe",
        "attemptLimit": 1, "timeoutSeconds": TIMEOUT_SECONDS,
    }
    if not execute:
        return receipt
    (source_check or verify_checkout)(source_commit)
    receipt["localCheckoutVerified"] = source_check is None
    environment = os.environ if env is None else env
    key = environment.get(PROVIDERS[provider][1], "")
    if not isinstance(key, str) or not key.strip() or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        fail("CREDENTIAL_UNAVAILABLE")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if provider == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    elif provider == "gemini":
        headers["x-goog-api-key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    now = clock or time.monotonic
    start = now()
    try:
        raw, response_headers = (transport or http_post)(endpoint, body, headers)
    except PilotError:
        raise
    except Exception:
        fail("TRANSPORT_FAILED")
    latency = round((now() - start) * 1000, 3)
    # Even unexpected successful credential echoes must never be reflected.
    if not isinstance(raw, bytes) or key.encode() in raw:
        fail("PROVIDER_RESPONSE_REFUSED")
    result, usage, returned_model, response_id = parse_response(provider, raw)
    (source_check or verify_checkout)(source_commit)
    if not isinstance(response_headers, dict):
        fail("RESPONSE_HEADERS_INVALID")
    lowered = {str(k).lower(): v for k, v in response_headers.items()}
    request_id = lowered.get("x-request-id", lowered.get("request-id"))
    if request_id is not None and (not isinstance(request_id, str) or not ID_RE.fullmatch(request_id) or key in request_id):
        request_id = None
    receipt.update({"mode": "observed-unqualified", "executed": True,
                    "providerInvocationObserved": transport is None,
                    "returnedModel": returned_model, "exactModelVerified": returned_model == model,
                    "requestId": request_id, "responseId": response_id,
                    "usage": usage, "latencyMs": latency, "result": result,
                    "responseSha256": digest(raw), "responseBytes": len(raw)})
    verify_receipt_strings(receipt, key)
    return receipt


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        fail("INVALID_OPTIONS")


def main(argv=None):
    try:
        parser = QuietParser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--provider", required=True, choices=tuple(PROVIDERS))
        parser.add_argument("--model", required=True)
        parser.add_argument("--source-commit", required=True)
        parser.add_argument("--execute", action="store_true")
        args = parser.parse_args(argv)
        receipt = run(args.provider, args.model, args.source_commit, args.execute)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except PilotError as error:
        print(json.dumps({"workId": WORK_ID, "status": "refused", "errorCode": str(error)}))
        return 2
    except Exception:
        print(json.dumps({"workId": WORK_ID, "status": "refused", "errorCode": "INTERNAL_FAILURE"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
