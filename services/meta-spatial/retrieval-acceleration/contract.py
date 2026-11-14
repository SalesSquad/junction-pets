"""Shared advisory-only output and strict JSON helpers."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

class ContractError(ValueError):
    """A caller-visible, stable error code and explanation."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

def advisory_fields(kind: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "kind": kind,
            "qualification": False, "action_authorized": False,
            "physical_identity_verified": False}

def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_json_key", f"Duplicate JSON key: {key}")
        result[key] = value
    return result

def strict_json_loads(raw: bytes | str):
    def invalid_constant(value):
        raise ContractError("nonfinite_json", f"Non-finite JSON constant: {value}")
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ContractError("nonfinite_json", "JSON number exceeds finite range")
        return parsed
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=invalid_constant, parse_float=finite_float)
    except ContractError:
        raise
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise ContractError("invalid_json", "Invalid UTF-8 JSON document") from exc

def strict_load_json(path: str | Path, max_bytes: int = 2_097_152):
    source = Path(path)
    if not source.is_file():
        raise ContractError("missing_file", f"Required JSON file missing: {source.name}")
    if source.stat().st_size > max_bytes:
        raise ContractError("oversize_json", f"JSON exceeds {max_bytes} bytes")
    raw = source.read_bytes()
    if len(raw) > max_bytes:
        raise ContractError("oversize_json", f"JSON exceeds {max_bytes} bytes")
    return strict_json_loads(raw)

