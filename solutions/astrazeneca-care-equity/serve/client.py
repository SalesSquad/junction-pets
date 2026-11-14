#!/usr/bin/env python3
"""SAMA pathway scribe client. Standard library only.

One Finnish clinical-style note plus its note date goes in; proposed rows for the
pathway event log come out (source TEXT_EXTRACTED, extraction_confidence set,
verified_by_human false), together with a decision: AUTO_ACCEPT or HUMAN_REVIEW.

What this file does, in order:
  1. builds the chat messages with the same function the adapter was trained with
     (scribe/prompts.py by default, imported, never copied);
  2. calls an OpenAI-compatible /v1/chat/completions endpoint (vLLM) with greedy
     decoding, guided JSON (serve/schema.json) and token log-probabilities;
  3. validates the answer against the schema, resolves date expressions in code
     (expression format) and canonicalises with the training-time function;
  4. turns token log-probabilities into a confidence score;
  5. applies an auto-accept threshold. Without a calibrated threshold nothing is
     auto-accepted.

Synthetic training data, research artefact, not a medical device. A person must
confirm every extraction before it is used for care.

The API key is read from an environment variable and is never printed or logged.
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import http.client
import importlib.util
import json
import math
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PROMPTS = ROOT / "scribe" / "prompts.py"
SCHEMA_PATH = HERE / "schema.json"

DEFAULT_MODEL = "pathway-scribe"
FORMATS = ("absolute", "expression")
GUIDED_MODES = ("response_format", "structured_outputs", "none")
CONFIDENCE_KINDS = ("geo_mean_prob", "seq_prob", "min_prob")
DEFAULT_CONFIDENCE = "geo_mean_prob"  # exp(mean token log-probability): the score scribe/v2/risk.py calibrates
MAX_TOKENS = 384  # same cap as scribe/evaluate.py
API_KEY_ENVS = ("SCRIBE_API_KEY", "VERDA_INFERENCE_KEY")
RETRY_STATUS = {408, 425, 429, 502, 503, 504}
MISSING_LOGPROB = -9998.0  # vLLM fills a missing token log-probability with -9999.0

# Finnish month stems, identical to scribe/sample.py MONTHS (a test checks this).
MONTHS = (
    "tammi",
    "helmi",
    "maalis",
    "huhti",
    "touko",
    "kesä",
    "heinä",
    "elo",
    "syys",
    "loka",
    "marras",
    "joulu",
)

# Column order of eventlog/schema.py pathway_events (a test checks this).
EVENT_LOG_COLUMNS = (
    "episode_id",
    "event_type",
    "event_date",
    "date_precision",
    "county",
    "entry_route",
    "cancer_site",
    "age_band",
    "source",
    "extraction_confidence",
    "verified_by_human",
    "synthetic",
)


class ScribeError(Exception):
    """Configuration or contract problem on the client side."""


# --------------------------------------------------------------------------- #
# Prompts and schema
# --------------------------------------------------------------------------- #


def load_prompts(path=DEFAULT_PROMPTS):
    """Import the prompt module the adapter was trained with.

    scribe/prompts.py does `from sample import ...`, so its directory is put on
    sys.path. The module is registered under a path-specific name so two prompt
    files (v1 and a later version) can be loaded side by side.
    """
    path = pathlib.Path(path).resolve()
    if not path.is_file():
        raise ScribeError(f"prompt module not found: {path}")
    name = "sama_scribe_prompts_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    if name in sys.modules:
        return sys.modules[name]
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


# What a prompt module may provide, by role. The expression names are the ones
# scribe/v2/data_iface.py looks up in scribe/v2/data_tools.py, so the module that
# defined the training format can be passed to --prompts unchanged.
ROLE_NAMES = {
    ("messages", "absolute"): ("messages",),
    ("messages", "expression"): ("expression_messages", "messages_expression", "messages"),
    ("resolve", "expression"): ("resolve_expression", "resolve", "to_absolute"),
    ("schema", "expression"): ("EXPRESSION_SCHEMA", "expression_schema"),
}


def lookup(module, role, fmt):
    """(name, attribute) of the first attribute of `module` that plays `role` for `fmt`, or (None, None)."""
    for name in ROLE_NAMES.get((role, fmt), ()):
        if hasattr(module, name):
            return name, getattr(module, name)
    return None, None


def load_schema(fmt, path=SCHEMA_PATH):
    """Return the self-contained sub-schema for one output format."""
    if fmt not in FORMATS:
        raise ScribeError(f"unknown format {fmt!r}; expected one of {FORMATS}")
    document = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return document["$defs"][fmt]


def _type_ok(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "null":
        return value is None
    raise ScribeError(f"unsupported schema type {name!r}")


_SUPPORTED_KEYWORDS = {
    "$schema",
    "$defs",
    "$ref",
    "$comment",
    "title",
    "description",
    "x-sama",
    "type",
    "enum",
    "const",
    "pattern",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "anyOf",
    "oneOf",
    "allOf",
    # annotations: carried, not checked
    "$id",
    "definitions",
    "default",
    "examples",
    "format",
}


def validate(instance, schema, root=None, where="$"):
    """Validate against the JSON-Schema subset used by serve/schema.json.

    Returns a list of human-readable errors; an empty list means valid. An
    unknown keyword raises, so a schema edit cannot be silently ignored.
    """
    root = schema if root is None else root
    unknown = set(schema) - _SUPPORTED_KEYWORDS
    if unknown:
        raise ScribeError(f"schema keyword(s) not supported by this validator: {sorted(unknown)}")
    errors = []
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            raise ScribeError(f"only local $ref is supported, got {ref!r}")
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        errors += validate(instance, target, root, where)
    for sub in schema.get("allOf", []):
        errors += validate(instance, sub, root, where)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            passed = sum(not validate(instance, sub, root, where) for sub in schema[key])
            if passed == 0 or (key == "oneOf" and passed != 1):
                errors.append(f"{where}: matches {passed} of {len(schema[key])} {key} branches")
    if "type" in schema and not _type_ok(instance, schema["type"]):
        errors.append(f"{where}: expected {schema['type']}")
        return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{where}: {instance!r} not in enum")
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{where}: {instance!r} != const")
    if "pattern" in schema and isinstance(instance, str):
        pattern = schema["pattern"]
        # In Python, $ also matches before a trailing newline; \Z does not.
        if pattern.endswith("$") and not pattern.endswith("\\$"):
            pattern = pattern[:-1] + r"\Z"
        if not re.search(pattern, instance):
            errors.append(f"{where}: {instance!r} does not match pattern")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{where}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{where}: longer than {schema['maxLength']}")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{where}: missing {name!r}")
        extra = schema.get("additionalProperties", True)
        for name, value in instance.items():
            if name in properties:
                errors += validate(value, properties[name], root, f"{where}.{name}")
            elif extra is False:
                errors.append(f"{where}: unexpected key {name!r}")
            elif isinstance(extra, dict):
                errors += validate(value, extra, root, f"{where}.{name}")
    if isinstance(instance, list):
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{where}: more than {schema['maxItems']} items")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{where}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, value in enumerate(instance):
                errors += validate(value, schema["items"], root, f"{where}[{i}]")
    return errors


def event_keys(schema):
    """Keys of one event object in a scribe schema, other than "type"."""
    try:
        properties = schema["properties"]["events"]["items"]["properties"]
    except (KeyError, TypeError):
        return []
    return [key for key in properties if key != "type"]


def check_prompt_matches_format(messages, fmt, schema=None):
    """Refuse to pair a prompt for one output format with the schema of the other.

    The prompt has to name, in quotes, at least one event key of the schema that
    will constrain the answer ("date" or "precision" for the absolute format,
    "expression" for the expression format of serve/schema.json).
    """
    keys = event_keys(schema) if schema else []
    if not keys:
        keys = ["expression"] if fmt == "expression" else ["date", "precision"]
    text = "\n".join(str(m.get("content", "")) for m in messages)
    if not any(f'"{key}"' in text for key in keys):
        wanted = " or ".join(f'"{key}"' for key in keys)
        raise ScribeError(
            f"the prompt does not describe the {fmt} format (it names none of {wanted}). "
            "Use the prompt module the adapter was trained with (--prompts), "
            "or pass strict_prompt_check=False / --no-prompt-check to override."
        )


# --------------------------------------------------------------------------- #
# Date expressions (expression format)
# --------------------------------------------------------------------------- #

_MONTH_ALT = "|".join(MONTHS)
_RE_NUMERIC = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?")
_RE_LONG = re.compile(r"(\d{1,2})\. (" + _MONTH_ALT + r")kuuta (\d{4})")
_RE_MONTH = re.compile(r"(" + _MONTH_ALT + r")kuussa (\d{4})")
_RE_AGO = re.compile(r"([1-9]\d{0,3}) (päivää|viikkoa) sitten")


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def resolve_expression(expression, note_date):
    """Turn one Finnish date expression into (ISO date, precision).

    Covers exactly the six forms of scribe/sample.py render():
      5.3.2024             day.month.year            DAY
      5.3.                 day.month, year of note   DAY
      5. maaliskuuta 2024  long form                 DAY
      maaliskuussa 2024    month only, first day     MONTH
      12 päivää sitten     days before the note      DAY
      3 viikkoa sitten     weeks before the note     DAY
    Anything else, or an impossible calendar date, raises ValueError. The
    arithmetic is done here, in code, so the model never has to do it.
    """
    note = _as_date(note_date)
    text = expression.strip()
    m = _RE_AGO.fullmatch(text)
    if m:
        days = int(m[1]) * (7 if m[2] == "viikkoa" else 1)
        return (note - datetime.timedelta(days=days)).isoformat(), "DAY"
    m = _RE_MONTH.fullmatch(text)
    if m:
        return datetime.date(int(m[2]), MONTHS.index(m[1]) + 1, 1).isoformat(), "MONTH"
    m = _RE_LONG.fullmatch(text)
    if m:
        return datetime.date(int(m[3]), MONTHS.index(m[2]) + 1, int(m[1])).isoformat(), "DAY"
    m = _RE_NUMERIC.fullmatch(text)
    if m:
        year = int(m[3]) if m[3] else note.year
        return datetime.date(year, int(m[2]), int(m[1])).isoformat(), "DAY"
    raise ValueError(f"unsupported date expression: {expression!r}")


# --------------------------------------------------------------------------- #
# Decoding the model answer
# --------------------------------------------------------------------------- #


def strip_fences(text):
    """Same fence handling as scribe/prompts.py parse_output."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())


def resolve_object(obj, note_date):
    """Expression-format answer of serve/schema.json -> absolute form (dates resolved in code)."""
    events = []
    for event in obj["events"]:
        date, precision = resolve_expression(event["expression"], note_date)
        events.append({"type": event["type"], "date": date, "precision": precision})
    return {"entry_route": obj["entry_route"], "events": events}


def decode_output(content, fmt, note_date, canonicalise, schema, max_lookback_days=1826, resolver=None):
    """Parse, validate, resolve and canonicalise one model answer.

    resolver(obj, note_date) turns an expression-format answer into the absolute
    form; the default is resolve_object above. A training-side resolver (for
    example scribe/v2/data_tools.py) can be passed instead.

    Returns {"canonical": dict or None, "raw_object": ..., "errors": [...],
    "flags": [...]}. errors mean the answer is unusable; flags mean it parsed
    but must not be auto-accepted.
    """
    out = {"canonical": None, "raw_object": None, "errors": [], "flags": []}
    try:
        obj = json.loads(strip_fences(content))
    except (ValueError, TypeError) as exc:
        out["errors"].append(f"not_json: {exc}")
        return out
    out["raw_object"] = obj
    problems = validate(obj, schema)
    if problems:
        out["errors"].append("schema: " + "; ".join(problems[:5]))
        return out
    absolute = obj
    if fmt == "expression":
        try:
            absolute = (resolver or resolve_object)(obj, note_date)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            out["errors"].append(f"unresolved_expression: {exc}")
            return out
    try:
        canonical = canonicalise(absolute)
    except (ValueError, KeyError, TypeError) as exc:
        out["errors"].append(f"not_canonical: {exc}")
        return out
    out["canonical"] = canonical
    note = _as_date(note_date)
    seen = set()
    for event in canonical["events"]:
        day = datetime.date.fromisoformat(event["date"])
        if day > note:
            out["flags"].append("event_after_note_date")
        if (note - day).days > max_lookback_days:
            out["flags"].append("event_older_than_lookback")
        key = (event["type"], event["date"])
        if key in seen:
            out["flags"].append("duplicate_event")
        seen.add(key)
    out["flags"] = sorted(set(out["flags"]))
    return out


# --------------------------------------------------------------------------- #
# Confidence from token log-probabilities
# --------------------------------------------------------------------------- #


def _token_bytes(item):
    raw = item.get("bytes")
    if isinstance(raw, list) and raw:
        return bytes(raw)
    return str(item.get("token", "")).encode("utf-8")


def _event_byte_spans(content):
    """Byte spans of the entry_route value and of each event object, in output order."""
    decoder = json.JSONDecoder()

    def b(index):
        return len(content[:index].encode("utf-8"))

    route = None
    m = re.search(r'"entry_route"\s*:\s*', content)
    if m:
        try:
            _, end = decoder.raw_decode(content, m.end())
            route = (b(m.end()), b(end))
        except ValueError:
            route = None
    events = []
    m = re.search(r'"events"\s*:\s*\[', content)
    if m:
        i = m.end()
        while i < len(content):
            while i < len(content) and content[i] in " \t\r\n,":
                i += 1
            if i >= len(content) or content[i] != "{":
                break
            try:
                _, end = decoder.raw_decode(content, i)
            except ValueError:
                break
            events.append((b(i), b(end)))
            i = end
    return route, events


def confidence_from_logprobs(content, items):
    """Summarise the token log-probabilities of the JSON part of the answer.

    items is choices[0].logprobs.content of an OpenAI-compatible response: a
    list of {"token", "logprob", "bytes"?}. Tokens are aligned to the answer
    text by byte offsets; only tokens overlapping the span from the first '{'
    to the last '}' are scored (same rule as scribe/evaluate.py).

    Scores, all in [0, 1], higher is more confident:
      seq_prob       exp(sum of log-probabilities): probability of this exact JSON
      geo_mean_prob  exp(mean log-probability): monotone in the v1 evaluation score
      min_prob       exp(min log-probability): the weakest single token

    With guided decoding vLLM masks the logits before it computes the returned
    log-probabilities, so tokens the grammar forces score about 0 (probability
    about 1) and only real choices carry information. seq_prob is unaffected by
    how many forced tokens there are; geo_mean_prob is diluted by them. A
    threshold is only valid for the score kind and decoding mode it was
    calibrated with.

    Returns None when log-probabilities are missing or unusable.
    """
    if not isinstance(items, list) or not items:
        return None
    logprobs = []
    for item in items:
        value = item.get("logprob") if isinstance(item, dict) else None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if value <= MISSING_LOGPROB or math.isnan(value) or value > 1e-6:
            return None
        logprobs.append(min(0.0, float(value)))
    pieces = [_token_bytes(item) for item in items]
    joined = b"".join(pieces)
    text = content.encode("utf-8")
    start = text.find(b"{")
    end = text.rfind(b"}")
    offset = joined.find(text) if text else -1
    aligned = offset >= 0 and 0 <= start <= end
    spans = []
    position = 0
    for piece in pieces:
        spans.append((position, position + len(piece)))
        position += len(piece)

    def collect(lo, hi):
        lo += offset
        hi += offset
        return [lp for lp, (a, z) in zip(logprobs, spans) if z > lo and a < hi and z > a]

    route_score = None
    event_scores = None
    if aligned:
        chosen = collect(start, end + 1)
        route_span, event_spans = _event_byte_spans(content)
        if route_span:
            part = collect(*route_span)
            route_score = math.exp(sum(part)) if part else None
        event_scores = []
        for span in event_spans:
            part = collect(*span)
            event_scores.append(math.exp(sum(part)) if part else None)
    else:
        # Token text could not be aligned to the answer. Score every token that is
        # not shaped like a special token; per-event scores are unavailable.
        chosen = [
            lp
            for lp, piece in zip(logprobs, pieces)
            if not re.fullmatch(rb"<[^<>\s]+>", piece.strip())
        ]
    if not chosen:
        return None
    total = sum(chosen)
    return {
        "aligned": aligned,
        "n_tokens": len(chosen),
        "sum_logprob": total,
        "mean_logprob": total / len(chosen),
        "min_logprob": min(chosen),
        "seq_prob": math.exp(total),
        "geo_mean_prob": math.exp(total / len(chosen)),
        "min_prob": math.exp(min(chosen)),
        "route_prob": route_score,
        "event_probs_output_order": event_scores,
    }


# --------------------------------------------------------------------------- #
# Threshold and routing
# --------------------------------------------------------------------------- #


def load_threshold(path, expect):
    """Read a calibration file and check it was made for this exact setup.

    The file must carry threshold, confidence_kind, format, guided and model. A
    mismatch raises: a threshold calibrated for another score kind, output
    format, decoding mode or model says nothing about this one.
    """
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    threshold = data.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ScribeError(f"{path}: 'threshold' must be a number")
    if not 0.0 <= threshold <= 1.0:
        raise ScribeError(f"{path}: threshold {threshold} is outside [0, 1]")
    for key, wanted in expect.items():
        if data.get(key) != wanted:
            raise ScribeError(
                f"{path}: calibrated for {key}={data.get(key)!r}, but this client uses {key}={wanted!r}"
            )
    return float(threshold), data


def route_decision(decoded, confidence, finish_reason, threshold, kind, episode_id):
    """AUTO_ACCEPT only when nothing at all argues for a human look."""
    reasons = []
    if decoded["errors"]:
        reasons.append("invalid_output")
    if finish_reason != "stop":
        reasons.append(f"finish_reason_{finish_reason}")
    reasons += decoded["flags"]
    score = confidence.get(kind) if confidence else None
    if score is None:
        reasons.append("no_confidence")
    if threshold is None:
        reasons.append("no_calibrated_threshold")
    elif score is not None and score < threshold:
        reasons.append("below_threshold")
    if episode_id is None:
        reasons.append("missing_episode_id")
    return ("AUTO_ACCEPT" if not reasons else "HUMAN_REVIEW"), reasons, score


def event_rows(canonical, episode_id, extraction_confidence, context=None, synthetic=True):
    """Rows shaped like eventlog/schema.py pathway_events.

    event_date is a datetime.date (Arrow date32). county, cancer_site and
    age_band are not in a note's extraction; they come from the caller's
    structured context and stay None otherwise. extraction_confidence is the
    note-level score the auto-accept threshold was applied to, repeated on every
    row of the note, so the routing decision can be reproduced from the log.
    """
    context = context or {}
    rows = []
    for event in canonical["events"]:
        rows.append(
            {
                "episode_id": episode_id,
                "event_type": event["type"],
                "event_date": datetime.date.fromisoformat(event["date"]),
                "date_precision": event["precision"],
                "county": context.get("county"),
                "entry_route": canonical["entry_route"],
                "cancer_site": context.get("cancer_site"),
                "age_band": context.get("age_band"),
                "source": "TEXT_EXTRACTED",
                "extraction_confidence": extraction_confidence,
                "verified_by_human": False,
                "synthetic": bool(synthetic),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def read_api_key(names=API_KEY_ENVS):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _http_json(url, payload, api_key, timeout):
    """POST payload as JSON, or GET when payload is None. Returns (status, body, retry_after)."""
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as exc:
        with exc:
            body = exc.read().decode("utf-8", "replace")
            return exc.code, body, exc.headers.get("Retry-After")


class ScribeClient:
    """Calls one scribe endpoint with fixed, recorded settings."""

    def __init__(
        self,
        base_url,
        api_key=None,
        model=DEFAULT_MODEL,
        fmt="absolute",
        guided="response_format",
        prompts_path=DEFAULT_PROMPTS,
        schema_path=SCHEMA_PATH,
        threshold=None,
        confidence_kind=DEFAULT_CONFIDENCE,
        timeout=300.0,
        retries=4,
        backoff=2.0,
        max_tokens=MAX_TOKENS,
        top_logprobs=0,
        strict_prompt_check=True,
        max_lookback_days=1826,
        sleep=time.sleep,
    ):
        if not base_url:
            raise ScribeError("base_url is required")
        if guided not in GUIDED_MODES:
            raise ScribeError(f"guided must be one of {GUIDED_MODES}")
        if confidence_kind not in CONFIDENCE_KINDS:
            raise ScribeError(f"confidence_kind must be one of {CONFIDENCE_KINDS}")
        if threshold is not None and not 0.0 <= threshold <= 1.0:
            raise ScribeError("threshold must be within [0, 1]")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.fmt = fmt
        self.guided = guided
        if fmt not in FORMATS:
            raise ScribeError(f"unknown format {fmt!r}; expected one of {FORMATS}")
        self.prompts = load_prompts(prompts_path)
        self.prompts_path = str(pathlib.Path(prompts_path).resolve())
        # Messages: the function of the training-side module for this format.
        self.messages_name, self._messages = lookup(self.prompts, "messages", fmt)
        if not callable(self._messages):
            wanted = ", ".join(ROLE_NAMES[("messages", fmt)])
            raise ScribeError(f"{self.prompts_path} has none of: {wanted}")
        # Schema and date resolver: the training-side definition wins when the module
        # carries one (scribe/v2/data_tools.py); otherwise serve/schema.json and the
        # resolver in this file.
        schema_name, schema = lookup(self.prompts, "schema", fmt)
        if callable(schema):
            schema = schema()
        if isinstance(schema, dict):
            self.schema, self.schema_source = schema, f"{self.prompts_path}:{schema_name}"
        else:
            self.schema, self.schema_source = load_schema(fmt, schema_path), str(pathlib.Path(schema_path).resolve())
        resolver_name, resolver = lookup(self.prompts, "resolve", fmt)
        self.resolver = resolver if callable(resolver) else None
        self.resolver_source = f"{self.prompts_path}:{resolver_name}" if self.resolver else "serve/client.py:resolve_object"
        canonical = getattr(self.prompts, "canonicalise", None)
        if not callable(canonical):
            canonical = load_prompts(DEFAULT_PROMPTS).canonicalise
        self.canonicalise = canonical
        self.threshold = threshold
        self.confidence_kind = confidence_kind
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_tokens = max_tokens
        self.top_logprobs = top_logprobs
        self.strict_prompt_check = strict_prompt_check
        self.max_lookback_days = max_lookback_days
        self._sleep = sleep

    # What a threshold file has to agree with.
    def calibration_key(self):
        return {
            "confidence_kind": self.confidence_kind,
            "format": self.fmt,
            "guided": self.guided,
            "model": self.model,
        }

    def messages(self, row):
        messages = self._messages(row)
        if self.strict_prompt_check:
            check_prompt_matches_format(messages, self.fmt, self.schema)
        return messages

    def build_request(self, row):
        payload = {
            "model": self.model,
            "messages": self.messages(row),
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "logprobs": True,
            "top_logprobs": self.top_logprobs,
            "stream": False,
        }
        if self.guided == "response_format":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": self.schema.get("title", "pathway_scribe_" + self.fmt), "schema": self.schema},
            }
        elif self.guided == "structured_outputs":
            payload["structured_outputs"] = {"json": self.schema}
        return payload

    def call(self, payload, path="/v1/chat/completions"):
        """POST (or GET when payload is None) with retries on cold-start style failures.

        Returns {"status": "ok", "response": ..., "latency_s", "total_s", "attempts"}
        or {"status": "http_error" | "transport_error" | "bad_response", "detail", ...}.
        latency_s is the wall time of the successful attempt; total_s includes
        failed attempts and the waits between them.
        """
        url = self.base_url + path
        started = time.monotonic()
        last = {"status": "transport_error", "detail": "no attempt made"}
        attempt = 0
        for attempt in range(1, self.retries + 2):
            t0 = time.monotonic()
            retry_after = None
            try:
                code, body, retry_after = _http_json(url, payload, self.api_key, self.timeout)
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
                last = {"status": "transport_error", "detail": type(exc).__name__ + ": " + str(exc)[:200]}
            else:
                if code == 200:
                    try:
                        parsed = json.loads(body)
                    except ValueError:
                        last = {"status": "bad_response", "detail": "response body is not JSON"}
                        break
                    return {
                        "status": "ok",
                        "response": parsed,
                        "latency_s": time.monotonic() - t0,
                        "total_s": time.monotonic() - started,
                        "attempts": attempt,
                    }
                last = {"status": "http_error", "http_status": code, "detail": body[:300]}
                if code not in RETRY_STATUS:
                    break
            if attempt <= self.retries:
                wait = self.backoff * (2 ** (attempt - 1))
                if retry_after:
                    try:
                        wait = max(wait, float(retry_after))
                    except ValueError:
                        pass
                self._sleep(min(wait, 60.0))
        last.update({"latency_s": None, "total_s": time.monotonic() - started, "attempts": attempt})
        return last

    def list_models(self):
        """Model ids the endpoint serves (GET /v1/models), or raise ScribeError."""
        called = self.call(None, "/v1/models")
        if called["status"] != "ok":
            raise ScribeError(
                f"GET /v1/models failed: {called['status']} {called.get('http_status', '')} {called.get('detail', '')}".strip()
            )
        try:
            return [str(item["id"]) for item in called["response"]["data"]]
        except (KeyError, TypeError) as exc:
            raise ScribeError(f"GET /v1/models returned an unexpected body: {exc}")

    def extract(self, row, episode_id=None, context=None, synthetic=True):
        """One note in, one result out. Never raises for model or network faults."""
        if episode_id is None:
            episode_id = row.get("episode_id", row.get("id"))
        result = {
            "id": row.get("id"),
            "episode_id": episode_id,
            "status": None,
            "decision": "HUMAN_REVIEW",
            "reasons": [],
            "canonical": None,
            "rows": [],
            "raw": None,
            "finish_reason": None,
            "confidence": None,
            "score": None,
            "threshold": self.threshold,
            "errors": [],
            "latency_s": None,
            "total_s": None,
            "attempts": None,
            "usage": None,
            "settings": dict(self.calibration_key(), prompts=self.prompts_path, messages=self.messages_name,
                             schema=self.schema_source, resolver=self.resolver_source if self.fmt == "expression" else None),
            "synthetic": bool(synthetic),
        }
        called = self.call(self.build_request(row))
        for key in ("latency_s", "total_s", "attempts"):
            result[key] = called.get(key)
        if called["status"] != "ok":
            result["status"] = called["status"]
            result["errors"].append(
                f"{called['status']}: {called.get('http_status', '')} {called.get('detail', '')}".strip()
            )
            result["reasons"] = [called["status"]]
            return result
        response = called["response"]
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("content is not a string")
        except (KeyError, IndexError, TypeError) as exc:
            result["status"] = "bad_response"
            result["errors"].append(f"bad_response: {exc}")
            result["reasons"] = ["bad_response"]
            return result
        result["raw"] = content
        result["finish_reason"] = choice.get("finish_reason")
        result["usage"] = response.get("usage")
        decoded = decode_output(
            content,
            self.fmt,
            row["note_date"],
            self.canonicalise,
            self.schema,
            self.max_lookback_days,
            self.resolver,
        )
        confidence = confidence_from_logprobs(content, (choice.get("logprobs") or {}).get("content"))
        if confidence and decoded["canonical"] and confidence["event_probs_output_order"] is not None:
            confidence["event_probs"] = _reorder_event_scores(
                decoded, self.fmt, row["note_date"], confidence["event_probs_output_order"], self.resolver
            )
        decision, reasons, score = route_decision(
            decoded, confidence, result["finish_reason"], self.threshold, self.confidence_kind, episode_id
        )
        result["status"] = "ok" if not decoded["errors"] else "invalid_output"
        result["errors"] = decoded["errors"]
        result["canonical"] = decoded["canonical"]
        result["confidence"] = confidence
        result["score"] = score
        result["decision"] = decision
        result["reasons"] = reasons
        if decoded["canonical"] is not None:
            result["rows"] = event_rows(decoded["canonical"], episode_id, score, context, synthetic)
        return result


def _reorder_event_scores(decoded, fmt, note_date, scores, resolver=None):
    """Map per-event scores from output order to canonical order (date, then type).

    Best effort: returns None when the answer's events cannot be matched one to one.
    """
    try:
        raw = decoded["raw_object"]
        absolute = raw if fmt != "expression" else (resolver or resolve_object)(raw, note_date)
        events = absolute["events"]
        if len(events) != len(scores) or len(events) != len(decoded["canonical"]["events"]):
            return None
        keyed = [((event["date"], event["type"]), score) for event, score in zip(events, scores)]
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        return None
    return [score for _, score in sorted(keyed, key=lambda item: item[0])]


def run_batch(client, rows, concurrency=4, synthetic=True):
    """Extract many notes; results come back in input order.

    Keep concurrency at or below the deployment's concurrent requests per
    replica, otherwise the extra requests wait in the platform queue and their
    latency measures the queue, not the model.
    """
    rows = list(rows)
    if concurrency <= 1:
        return [client.extract(row, synthetic=synthetic) for row in rows]
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(lambda row: client.extract(row, synthetic=synthetic), rows))


def endpoint_label(base_url):
    """Host and path of the endpoint, for logs and reports (never credentials or query strings)."""
    parts = urllib.parse.urlsplit(base_url)
    return (parts.hostname or "") + (f":{parts.port}" if parts.port else "") + parts.path


def jsonable(value):
    """json.dumps default= hook for datetime.date in event rows."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if "note_text" not in row or "note_date" not in row:
                raise ScribeError(f"{path}:{number}: each line needs note_text and note_date")
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def add_endpoint_arguments(parser):
    parser.add_argument("--base-url", default=os.environ.get("SCRIBE_BASE_URL"),
                        help="endpoint base, e.g. https://containers.datacrunch.io/<deployment> (or env SCRIBE_BASE_URL)")
    parser.add_argument("--api-key-env", default=None,
                        help="name of the environment variable holding the bearer key "
                             f"(default: first set of {', '.join(API_KEY_ENVS)})")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--format", dest="fmt", choices=FORMATS, default="absolute")
    parser.add_argument("--guided", choices=GUIDED_MODES, default="response_format")
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS),
                        help="prompt module the adapter was trained with")
    parser.add_argument("--no-prompt-check", action="store_true",
                        help="skip the check that the prompt describes the chosen output format")
    parser.add_argument("--confidence", choices=CONFIDENCE_KINDS, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--threshold", type=float, default=None,
                        help="auto-accept when the score is at least this; omit to send everything to review")
    parser.add_argument("--threshold-file", default=None,
                        help="calibration JSON; must match score kind, format, guided mode and model")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=4)


def client_from_arguments(args):
    if not args.base_url:
        raise ScribeError("--base-url or SCRIBE_BASE_URL is required")
    if args.threshold is not None and args.threshold_file:
        raise ScribeError("give --threshold or --threshold-file, not both")
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else read_api_key()
    client = ScribeClient(
        args.base_url,
        api_key=api_key,
        model=args.model,
        fmt=args.fmt,
        guided=args.guided,
        prompts_path=args.prompts,
        threshold=args.threshold,
        confidence_kind=args.confidence,
        timeout=args.timeout,
        retries=args.retries,
        strict_prompt_check=not args.no_prompt_check,
    )
    if args.threshold_file:
        client.threshold, _ = load_threshold(args.threshold_file, client.calibration_key())
    return client


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    add_endpoint_arguments(parser)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--jsonl", help="batch: one JSON object per line with note_text, note_date, optional id/episode_id")
    source.add_argument("--note-file", help="single note: UTF-8 text file ('-' for stdin)")
    parser.add_argument("--note-date", help="YYYY-MM-DD, required with --note-file")
    parser.add_argument("--episode-id", help="pseudonymous episode key for --note-file")
    parser.add_argument("--not-synthetic", action="store_true",
                        help="mark rows synthetic=false (default true: all current data is synthetic)")
    parser.add_argument("--out", help="write one result per line here instead of stdout")
    args = parser.parse_args(argv)
    try:
        client = client_from_arguments(args)
        if args.jsonl:
            rows = read_jsonl(args.jsonl)
        else:
            if not args.note_date:
                raise ScribeError("--note-date is required with --note-file")
            datetime.date.fromisoformat(args.note_date)
            text = sys.stdin.read() if args.note_file == "-" else pathlib.Path(args.note_file).read_text(encoding="utf-8")
            rows = [{"note_text": text, "note_date": args.note_date, "episode_id": args.episode_id}]
    except (ScribeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    started = time.monotonic()
    results = run_batch(client, rows, args.concurrency, synthetic=not args.not_synthetic)
    wall = time.monotonic() - started
    sink = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        for result in results:
            sink.write(json.dumps(result, ensure_ascii=False, default=jsonable) + "\n")
    finally:
        if args.out:
            sink.close()
    counts = {}
    for result in results:
        counts[result["decision"]] = counts.get(result["decision"], 0) + 1
    failed = sum(r["status"] not in ("ok", "invalid_output") for r in results)
    summary = {"notes": len(results), "decisions": counts, "request_failures": failed, "wall_seconds": round(wall, 3)}
    print(json.dumps(summary), file=sys.stderr)
    try:
        sys.path.insert(0, str(HERE))
        from runlog import log

        log(
            "client_batch",
            command="serve/client.py",
            inputs={"notes": len(rows), "source": args.jsonl or "note-file", "endpoint": endpoint_label(client.base_url),
                    "settings": client.calibration_key(), "threshold": client.threshold,
                    "concurrency": args.concurrency},
            outputs=[args.out] if args.out else None,
            metrics=summary,
            status="ok" if not failed else "error",
        )
    except Exception as exc:  # the run log must never break an extraction run
        print(f"warning: run log not written: {exc}", file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
