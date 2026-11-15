"""Bounded provider calls. Host credentials never enter prompts or receipts."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


@dataclass(frozen=True)
class Route:
    name: str
    url: str
    model: str


NEMOTRON = Route("verda_nemotron", "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1/chat/completions", "nemotron-3.5-super-vl")
NIM_NANO = Route("nvidia_nim_nano", "https://integrate.api.nvidia.com/v1/chat/completions", "nvidia/nemotron-nano-12b-v2-vl")
NIM_OCR = Route("nvidia_nim_ocr", "https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2", "nvidia/nemotron-ocr-v2")
ALLOWED_ROUTES = (NEMOTRON, NIM_NANO, NIM_OCR)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_nemotron_key():
    """Use the existing approved MBP Keychain item in this process only."""
    if sys.platform != "darwin":
        raise RuntimeError("existing_mbp_keychain_route_required")
    lib = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    find = lib.SecKeychainFindGenericPassword
    find.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p,
                     ctypes.c_uint32, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
                     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
    find.restype = ctypes.c_int32
    lib.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    service, account = b"verda-nemotron-inference", getpass.getuser().encode()
    length, data = ctypes.c_uint32(), ctypes.c_void_p()
    status = find(None, len(service), service, len(account), account,
                  ctypes.byref(length), ctypes.byref(data), None)
    if status:
        raise RuntimeError("keychain_access_unavailable:" + str(status))
    try:
        key = ctypes.string_at(data, length.value).decode()
    finally:
        lib.SecKeychainItemFreeContent(None, data)
    if not key or "\n" in key or "\r" in key:
        raise RuntimeError("invalid_credential")
    return key


def load_nim_key():
    """A Datacrunch credential is deliberately never tried at NVIDIA NIM."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("nvidia_nim_credential_not_configured")
    if not key.startswith("nvapi-") or "\n" in key or "\r" in key:
        raise RuntimeError("nvidia_nim_credential_format_unverified")
    return key


def redact(text, key):
    text = text.replace(key, "[REDACTED]") if key else text
    return re.sub(r"(?:dc_|nvapi-|sk-)[A-Za-z0-9_-]{20,}", "[REDACTED]", text)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(route, payload, key, *, timeout=120):
    if route not in ALLOWED_ROUTES:
        raise ValueError("unapproved_provider_route")
    if route != NEMOTRON and not key.startswith("nvapi-"):
        raise ValueError("separate_nvidia_nim_credential_required")
    if not 1 <= timeout <= 180:
        raise ValueError("bounded_timeout_required")
    body = canonical(payload)
    if len(body) > 16 * 1024 * 1024:
        raise ValueError("bounded_request_required")
    started = time.monotonic()
    receipt = {"schema_version": 1, "provider": route.name, "url": route.url,
               "requested_model": route.model, "request_sha256": sha256(body),
               "request_bytes": len(body), "started_utc": datetime.now(timezone.utc).isoformat(),
               "attempts": 1, "retry_performed": False, "provider_completion_known": False,
               "verified_cost_usd": None, "usage": None, "qualification": False}
    response_object = None
    raw = b""
    request = urllib.request.Request(route.url, body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(request, timeout=timeout) as response:
            receipt["http_status"] = response.status
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            receipt["status"] = "response_too_large"
            raw = b""
        else:
            safe_text = redact(raw.decode("utf-8"), key)
            response_object = json.loads(safe_text,
                parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite_provider_json")))
            raw = safe_text.encode()
            if not isinstance(response_object, dict):
                raise ValueError("provider_response_object_required")
            receipt["status"] = "response_received"
            receipt["provider_completion_known"] = True
            receipt["returned_model"] = response_object.get("model")
            receipt["usage"] = response_object.get("usage")
            choices = response_object.get("choices") or []
            if choices:
                receipt["finish_reason"] = choices[0].get("finish_reason")
    except urllib.error.HTTPError as error:
        receipt["http_status"] = error.code
        receipt["status"] = {401: "authentication_failed", 403: "access_denied", 429: "rate_limited",
                             413: "request_too_large"}.get(error.code, "provider_error")
        receipt["retry_after"] = error.headers.get("Retry-After")
        raw = redact(error.read(4096).decode("utf-8", errors="replace"), key).encode()
        receipt["provider_completion_known"] = True
    except (TimeoutError, urllib.error.URLError) as error:
        receipt["status"] = "transport_or_timeout_completion_unknown"
        receipt["error_type"] = type(error).__name__
    except (ValueError, UnicodeError, KeyError, TypeError) as error:
        receipt["status"] = "invalid_provider_response"
        receipt["error_type"] = type(error).__name__
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        receipt["ended_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["response_sha256"] = sha256(raw) if raw else None
        receipt["response_bytes"] = len(raw)
    return receipt, response_object, raw


def completion_text(response):
    if not isinstance(response, dict):
        raise ValueError("no_provider_completion")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("one_completion_required")
    if choices[0].get("finish_reason") != "stop":
        raise ValueError("incomplete_provider_completion")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty_provider_completion")
    return content
