"""Read-only reconciliation of the pinned R5 specialist artifact layout.

This checks supplied files, not provider execution, model weights or identity.
The R5 request file is a manifest, not a copy of the actual request payload.
No provider modules, credentials, image files or evaluation truth are loaded.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import stat
from typing import Any

from contract import ContractError, advisory_fields, sha256_bytes, strict_json_loads

LANES = ("ocr", "visual", "detail", "critic")
RANK_LANES = LANES[1:]
WORK_ID = "META-LENS-R5-NEMOTRON4-20261114"
LEGACY_INTERFACE_COMMIT = "fbf27ab1ca3905ccc1c561cc6a6e7e9f05df9a5d"
INTERFACE_COMMIT = "9a16495474f815e43729bbae87eb5d42d71d49a2"
SUPPORTED_INTERFACE_COMMITS = (LEGACY_INTERFACE_COMMIT, INTERFACE_COMMIT)
PROVIDER = "verda_nemotron"
PROVIDER_URL = "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1/chat/completions"
OBSERVATION_KINDS = ("none", "label_closeup", "side_view", "back_view",
                     "connector_closeup", "scale_reference", "other")
AUTHORITY_FIELDS = ("qualification", "action_authorized", "physical_identity_verified")
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_OBSERVATION_BYTES = 65536
MAX_TOTAL_BYTES = 80 * 1024 * 1024
MAX_ARTIFACTS = 130  # Two root files, four lanes, eight cases, four artifacts per pair.
ARTIFACT_SUFFIXES = ("request.json", "receipt.json", "response.json", "observation.json")
FAILURE_STATUSES = {
    "preparation_or_schema_error", "response_too_large", "authentication_failed",
    "access_denied", "rate_limited", "request_too_large", "provider_error",
    "transport_or_timeout_completion_unknown", "invalid_provider_response",
}


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ContractError(code, message)


def _object(value: Any, label: str) -> dict:
    _require(isinstance(value, dict), "invalid_schema", f"{label} must be an object")
    return value


def _fields(value: Any, required: set[str], optional: set[str], label: str) -> dict:
    value = _object(value, label)
    _require(required <= value.keys() and value.keys() <= required | optional,
             "unexpected_fields", f"{label} has missing or unexpected fields")
    return value


def _integer(value: Any, low: int, high: int, label: str) -> int:
    _require(type(value) is int and low <= value <= high,
             "invalid_integer", f"{label} must be an integer in {low}..{high}")
    return value


def _text(value: Any, label: str, limit: int = 256, empty: bool = False) -> str:
    _require(isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip()))
             and all(ord(c) >= 32 or c in "\n\t" for c in value),
             "invalid_text", f"{label} must be bounded text")
    return value


def _digest(value: Any, label: str, length: int = 64) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None,
             "invalid_digest", f"{label} must be a lowercase {length}-character digest")
    return value


def _authority(value: dict, required: tuple[str, ...] = ("qualification",)) -> None:
    for key in required:
        _require(key in value, "missing_authority_field", f"Missing {key}")
    for key in AUTHORITY_FIELDS:
        if key in value:
            _require(value[key] is False, "authority_escalation", f"{key} must be false")


def _finite_tree(value: Any, depth: int = 0) -> None:
    _require(depth <= 20, "json_depth", "JSON exceeds the supported nesting depth")
    if isinstance(value, float):
        _require(math.isfinite(value), "nonfinite_json", "JSON numbers must be finite")
    elif isinstance(value, dict):
        for item in value.values():
            _finite_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _finite_tree(item, depth + 1)


def _json(raw: bytes | str) -> Any:
    try:
        value = strict_json_loads(raw)
        _finite_tree(value)
        return value
    except (RecursionError, OverflowError) as exc:
        raise ContractError("invalid_json", "JSON exceeds parser bounds") from exc


def _plain_path(path: Path) -> None:
    _require(len(str(path)) <= 4096, "path_bound", "Path exceeds supported length")
    _require(not any(part == ".." for part in path.parts), "unsafe_path", "Parent traversal is not allowed")
    for candidate in (path, *path.parents):
        _require(not candidate.is_symlink(), "unsafe_path", "Symlink paths are not accepted")


class _Artifacts:
    """Bounded regular-file reads, with byte hashes and mutation detection."""
    def __init__(self, root: Path):
        self.root = root.absolute()
        _plain_path(self.root)
        _require(self.root.is_dir(), "missing_directory", "Run directory does not exist")
        self.total_bytes = 0
        self.hashes: dict[str, str] = {}
        self.snapshots: list[tuple[Path, tuple[int, ...]]] = []
        self.inventory: set[str] = set()
        self.lane_directories: set[str] = set()
        self._inventory()

    def _inventory(self) -> None:
        with os.scandir(self.root) as entries:
            for count, entry in enumerate(entries, 1):
                _require(count <= 6, "artifact_count", "Run root has too many entries")
                _require(not entry.is_symlink(), "unsafe_path", "Run artifacts cannot be symlinks")
                if entry.name in LANES:
                    _require(entry.is_dir(follow_symlinks=False), "invalid_artifact", "Lane must be a directory")
                    self.lane_directories.add(entry.name)
                    with os.scandir(entry.path) as files:
                        for file_count, item in enumerate(files, 1):
                            _require(file_count <= 32, "artifact_count", "Lane has too many artifacts")
                            _require(item.is_file(follow_symlinks=False) and not item.is_symlink(),
                                     "unsafe_path", "Lane artifacts must be regular files")
                            self.inventory.add(entry.name + "/" + item.name)
                else:
                    _require(entry.name in ("plan.json", "summary.json") and entry.is_file(follow_symlinks=False),
                             "unexpected_artifact", "Unexpected file in run directory")
                    self.inventory.add(entry.name)
        _require(len(self.inventory) <= MAX_ARTIFACTS, "artifact_count", "Too many run artifacts")

    @staticmethod
    def _snapshot(value: os.stat_result) -> tuple[int, ...]:
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns

    def read(self, path: Path, label: str, limit: int = MAX_JSON_BYTES) -> bytes:
        path = path.absolute()
        _plain_path(path)
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        except FileNotFoundError as exc:
            raise ContractError("missing_file", f"Missing {label}") from exc
        except OSError as exc:
            raise ContractError("unreadable_artifact", f"Cannot read {label}") from exc
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            _require(stat.S_ISREG(before.st_mode), "unsafe_path", "Artifacts must be regular files")
            _require(before.st_size <= limit, "oversize_json", f"{label} exceeds its byte limit")
            raw = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        _require(len(raw) <= limit, "oversize_json", f"{label} exceeds its byte limit")
        _require(self._snapshot(before) == self._snapshot(after), "artifact_changed", f"{label} changed while reading")
        self.total_bytes += len(raw)
        _require(self.total_bytes <= MAX_TOTAL_BYTES, "input_byte_budget", "Run exceeds total read-byte budget")
        self.snapshots.append((path, self._snapshot(after)))
        self.hashes[label] = sha256_bytes(raw)
        return raw

    def optional(self, relative: str, limit: int = MAX_JSON_BYTES) -> bytes | None:
        if relative not in self.inventory:
            return None
        return self.read(self.root / relative, relative, limit)

    def finish(self) -> None:
        for path, expected in self.snapshots:
            try:
                current = path.stat(follow_symlinks=False)
            except OSError as exc:
                raise ContractError("artifact_changed", "An input artifact disappeared") from exc
            _require(self._snapshot(current) == expected and stat.S_ISREG(current.st_mode),
                     "artifact_changed", "An input artifact changed during reconciliation")


def _hash_map(value: Any, required: set[str], label: str) -> dict:
    value = _object(value, label)
    _require(required <= value.keys() and len(value) <= 32, "source_binding", f"Invalid {label} entries")
    for name, digest in value.items():
        _require(re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name) is not None and name not in (".", ".."),
                 "source_binding", f"Unsafe filename in {label}")
        _digest(digest, label)
    return value


def _plan(value: Any, expected_commit: str, expected_model: str) -> dict:
    value = _object(value, "plan")
    required = {"schema_version", "work_id", "source_commit", "source_sha256", "cases_sha256",
                "provider", "model", "lanes", "max_concurrent_calls", "maximum_inference_calls",
                "start_index", "case_count", "max_output_tokens_per_call", "max_attempts_per_job",
                "chat_template_kwargs", "response_format", "deadline_seconds", "started_utc",
                "new_gpu_instances", "same_backbone_specialists_are_independent_models",
                "verified_cost_usd", "qualification", "action_authorized"}
    semantic_variant = "semantic_choice_schema" in value
    if semantic_variant:
        required.add("semantic_choice_schema")
    _fields(value, required, {"physical_identity_verified"}, "plan")
    if semantic_variant:
        _require(value["semantic_choice_schema"] is True, "unsupported_plan_variant",
                 "The semantic-choice plan variant requires semantic_choice_schema=true")
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1 and value["work_id"] == WORK_ID,
             "unsupported_contract", "Plan is not the R5 schema-v1 contract")
    _require(value["source_commit"] == expected_commit, "source_commit_mismatch", "Plan execution commit differs from the expected commit")
    _hash_map(value["source_sha256"], {"prepare_cases.py", "protocol.py", "run_specialists.py", "provider.py"}, "source_sha256")
    _digest(value["cases_sha256"], "cases_sha256")
    _require(value["model"] == expected_model and value["provider"] == PROVIDER,
             "model_or_provider_mismatch", "Plan model/provider differs from the expected R5 route")
    lanes = value["lanes"]
    _require(isinstance(lanes, list) and 1 <= len(lanes) <= 4 and
             all(isinstance(lane, str) and lane in LANES for lane in lanes),
             "lane_contract", "Plan requires a nonempty list of known R5 lanes")
    _require(len(set(lanes)) == len(lanes) and lanes == [lane for lane in LANES if lane in lanes],
             "lane_contract", "Requested lanes must be unique and in the declared R5 order")
    if not semantic_variant:
        _require(lanes == list(LANES), "lane_contract", "The legacy plan requires all four R5 lanes")
    start = _integer(value["start_index"], 0, 7, "start_index")
    count = _integer(value["case_count"], 1, 8 - start, "case_count")
    for key, wanted in (("max_concurrent_calls", len(lanes)), ("maximum_inference_calls", len(lanes) * count),
                        ("max_attempts_per_job", 1), ("new_gpu_instances", 0)):
        _require(type(value[key]) is int and value[key] == wanted, "run_budget_mismatch", f"Unexpected {key}")
    _integer(value["max_output_tokens_per_call"], 256, 2048, "max_output_tokens_per_call")
    _integer(value["deadline_seconds"], 120, 1800, "deadline_seconds")
    _require(value["chat_template_kwargs"] == {"enable_thinking": False} and
             value["chat_template_kwargs"].get("enable_thinking") is False and value["response_format"] == "json_schema",
             "request_contract", "Plan request settings differ from the pinned R5 contract")
    _require(value["same_backbone_specialists_are_independent_models"] is False and value["verified_cost_usd"] is None,
             "unsupported_claim", "R5 does not attest independent models or verified cost")
    _text(value["started_utc"], "started_utc", 64)
    _authority(value, ("qualification", "action_authorized"))
    return value


def _image(value: Any, root: Path, query: bool) -> dict:
    fields = {"image_path", "image_sha256", "source_view_index"}
    if not query:
        fields.add("alias")
    value = _fields(value, fields, set(), "case image")
    path = Path(_text(value["image_path"], "image_path", 4096))
    _require(path.is_absolute() and ".." not in path.parts and path.is_relative_to(root),
             "image_path_binding", "Image path must be inside its declared absolute root")
    _digest(value["image_sha256"], "image_sha256")
    _require(type(value["source_view_index"]) is int and value["source_view_index"] == (1 if query else 0),
             "image_view_binding", "Image view index differs from the R5 case contract")
    return value


def _cases(value: Any, plan: dict) -> list[dict]:
    value = _object(value, "cases manifest")
    required = {"schema_version", "work_id", "source_commit", "source_hashes", "input_hashes",
                "input_paths", "selection", "candidate_policy", "cases", "query_count", "distinct_families",
                "unique_image_files", "downloads", "downloaded_bytes", "query_metadata_in_prompts",
                "candidate_metadata_in_prompts", "extra_view_observed", "qualification", "action_authorized",
                "evaluation_truth_sha256"}
    _fields(value, required, {"physical_identity_verified"}, "cases manifest")
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1 and value["work_id"] == WORK_ID,
             "unsupported_contract", "Cases must use the R5 schema-v1 contract")
    _digest(value["source_commit"], "preparation source_commit", 40)
    sources = _hash_map(value["source_hashes"], {"prepare_cases.py", "protocol.py"}, "source_hashes")
    _require(set(sources) == {"prepare_cases.py", "protocol.py"}, "source_binding", "Unexpected preparation source entries")
    if value["source_commit"] == plan["source_commit"]:
        _require(all(plan["source_sha256"][name] == digest for name, digest in sources.items()),
                 "source_hash_mismatch", "Same-commit preparation and execution source digests differ")
    for name in ("dataset", "r4_report", "predictions", "query_metrics"):
        _digest(_object(value["input_hashes"], "input_hashes").get(name), "input hash")
    _digest(value["evaluation_truth_sha256"], "evaluation_truth_sha256")
    _object(value["input_paths"], "input_paths")
    _text(value["selection"], "selection", 1024)
    _text(value["candidate_policy"], "candidate_policy", 1024)
    _authority(value, ("qualification", "action_authorized"))
    for name in ("query_metadata_in_prompts", "candidate_metadata_in_prompts", "extra_view_observed"):
        _require(value[name] is False, "unsupported_claim", f"{name} must be false")
    for name in ("query_count", "distinct_families"):
        _require(type(value[name]) is int and value[name] == 8, "case_count", "Exactly eight frozen development cases are required")
    cases = value["cases"]
    _require(isinstance(cases, list) and len(cases) == 8, "case_count", "Exactly eight cases are required")
    quartiles = []
    seen: set[str] = set()
    image_paths: dict[str, str] = {}
    for case in cases:
        _fields(case, {"case_id", "split", "image_root", "confidence_quartile", "query", "candidates"}, set(), "selected case")
        case_id = case["case_id"]
        _require(isinstance(case_id, str) and re.fullmatch(r"q[0-9]{4}", case_id) is not None and case_id not in seen,
                 "duplicate_or_invalid_case", "Case IDs must be unique bounded R5 IDs")
        seen.add(case_id)
        _require(case["split"] == "dev", "split_mismatch", "Only development cases are supported")
        root = Path(_text(case["image_root"], "image_root", 4096))
        _require(root.is_absolute() and ".." not in root.parts, "image_path_binding", "Image root must be absolute without traversal")
        quartiles.append(_integer(case["confidence_quartile"], 1, 4, "confidence_quartile"))
        query = _image(case["query"], root, True)
        candidates = case["candidates"]
        _require(isinstance(candidates, list) and len(candidates) == 3, "candidate_count", "Each case requires exactly three candidates")
        for item in candidates:
            _image(item, root, False)
            _require(item["image_sha256"] != query["image_sha256"], "query_image_in_gallery", "Query bytes cannot also be a candidate image")
        aliases = [item["alias"] for item in candidates]
        _require(all(isinstance(alias, str) for alias in aliases) and set(aliases) == {"c01", "c02", "c03"},
                 "candidate_aliases", "Candidate aliases must be unique c01/c02/c03")
        for item in [query, *candidates]:
            path, digest = item["image_path"], item["image_sha256"]
            _require(path not in image_paths or image_paths[path] == digest,
                     "image_hash_mismatch", "One image path has conflicting supplied digests")
            image_paths[path] = digest
    _require(sorted(quartiles) == [1, 1, 2, 2, 3, 3, 4, 4], "quartile_binding", "Cases must contain two entries per confidence quartile")
    _require(_integer(value["unique_image_files"], 1, 32, "unique_image_files") == len(image_paths),
             "image_count_mismatch", "Declared image count differs from the case images")
    _integer(value["downloaded_bytes"], 0, 32 * 4 * 1024 * 1024, "downloaded_bytes")
    _require(isinstance(value["downloads"], list) and len(value["downloads"]) <= 32,
             "download_count", "Download declarations exceed the R5 bound")
    return cases[plan["start_index"]:plan["start_index"] + plan["case_count"]]


def _request(value: Any, case: dict, lane: str, plan: dict) -> dict:
    _fields(value, {"case_id", "lane", "split", "qualification", "request_sha256", "cases_sha256",
                    "query_image_sha256", "candidate_image_sha256", "status"},
            {"action_authorized", "physical_identity_verified"}, "request manifest")
    _pair(value, case, lane)
    _digest(value["request_sha256"], "request_sha256")
    _require(value["cases_sha256"] == plan["cases_sha256"], "case_hash_mismatch", "Request is bound to different case bytes")
    _require(value["query_image_sha256"] == case["query"]["image_sha256"], "image_hash_mismatch", "Request query digest differs from its case")
    candidates = [] if lane == "ocr" else [item["image_sha256"] for item in case["candidates"]]
    _require(value["candidate_image_sha256"] == candidates, "image_hash_mismatch", "Request candidate digest order differs from its case")
    _require(value["status"] == "prepared_not_yet_observed_complete", "request_status", "Unexpected request manifest status")
    return value


def _pair(value: dict, case: dict, lane: str) -> None:
    _require(value.get("case_id") == case["case_id"] and value.get("lane") == lane and value.get("split") == "dev",
             "pair_binding", "Artifact case/lane/split differs from its filename and case")
    _authority(value)


def _usage(value: Any, label: str) -> Any:
    if value is None:
        return None
    value = _object(value, label)
    _require(len(value) <= 24, "usage_bound", "Too many usage fields")
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        if key in value:
            _integer(value[key], 0, 1_000_000_000, key)
    if all(key in value for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
        _require(value["prompt_tokens"] + value["completion_tokens"] == value["total_tokens"],
                 "usage_mismatch", "Reported token total differs from input plus output tokens")
    return value


def _receipt(value: Any, case: dict, lane: str, plan: dict) -> dict:
    value = _object(value, "receipt")
    required = {"case_id", "lane", "split", "qualification", "status"}
    provider_fields = {"schema_version", "provider", "url", "requested_model", "request_sha256", "request_bytes",
                       "started_utc", "attempts", "retry_performed", "provider_completion_known", "verified_cost_usd",
                       "usage", "elapsed_seconds", "ended_utc", "response_sha256", "response_bytes"}
    optional = provider_fields | {"http_status", "returned_model", "finish_reason", "retry_after", "error_type", "error",
                                  "observation_sha256", "action_authorized", "physical_identity_verified"}
    _fields(value, required, optional, "receipt")
    _pair(value, case, lane)
    status = value["status"]
    _require(isinstance(status, str) and status in FAILURE_STATUSES | {"observed_schema_valid"},
             "receipt_status", "Unknown R5 receipt status")
    for key, bound in (("error_type", 100), ("error", 350)):
        if key in value:
            _text(value[key], key, bound, empty=key == "error")
    if "attempts" not in value:
        _require(status == "preparation_or_schema_error" and not (provider_fields & value.keys()),
                 "receipt_schema", "Receipt lacks the provider fields required for an attempted call")
        return value
    _require(provider_fields <= value.keys(), "receipt_schema", "Incomplete provider receipt")
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1,
             "receipt_schema", "Unsupported provider receipt schema")
    _require(value["provider"] == PROVIDER and value["url"] == PROVIDER_URL and value["requested_model"] == plan["model"],
             "model_or_provider_mismatch", "Receipt model/provider differs from the plan")
    _digest(value["request_sha256"], "request_sha256")
    _integer(value["request_bytes"], 1, 16 * 1024 * 1024, "request_bytes")
    _require(type(value["attempts"]) is int and value["attempts"] == 1 and value["retry_performed"] is False,
             "attempt_budget", "R5 allows one attempt and no implicit retry")
    _require(type(value["provider_completion_known"]) is bool and value["verified_cost_usd"] is None,
             "unsupported_claim", "Invalid completion/cost declaration")
    response_bytes = _integer(value["response_bytes"], 0, MAX_JSON_BYTES, "response_bytes")
    if response_bytes:
        _digest(value["response_sha256"], "response_sha256")
    else:
        _require(value["response_sha256"] is None, "response_hash_mismatch", "Empty R5 response must have a null digest")
    if "http_status" in value:
        _integer(value["http_status"], 100, 599, "http_status")
    error_statuses = {"authentication_failed": 401, "access_denied": 403,
                      "rate_limited": 429, "request_too_large": 413}
    if status in error_statuses:
        _require(value.get("http_status") == error_statuses[status] and value["provider_completion_known"] is True,
                 "receipt_status_mismatch", "HTTP failure status differs from its receipt declaration")
    if status == "transport_or_timeout_completion_unknown":
        _require(value["provider_completion_known"] is False, "receipt_status_mismatch", "Transport failure completion must remain unknown")
    if "returned_model" in value:
        _require(value["returned_model"] == plan["model"], "returned_model_mismatch", "Returned model differs from the explicit expected model")
    _usage(value["usage"], "receipt usage")
    if "observation_sha256" in value:
        _digest(value["observation_sha256"], "observation_sha256")
    for key in ("started_utc", "ended_utc"):
        _text(value[key], key, 64)
    elapsed = value["elapsed_seconds"]
    _require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 86400,
             "invalid_elapsed", "Elapsed time must be finite and bounded")
    if status == "observed_schema_valid":
        _require(value.get("http_status") == 200 and value["provider_completion_known"] is True and
                 value.get("returned_model") == plan["model"] and value.get("finish_reason") == "stop" and
                 "observation_sha256" in value and response_bytes > 0,
                 "receipt_status_mismatch", "Observed status lacks successful bounded completion evidence")
    return value


def _observation(value: Any, lane: str, case: dict, persisted: bool = True) -> dict:
    common = {"schema_version", "lane", *AUTHORITY_FIELDS} if persisted else set()
    fields = {"status", "spans"} if lane == "ocr" else {
        "ranking", "proposed_candidate", "identifiability", "observations", "additional_observation"}
    _fields(value, fields | common, set(), "observation")
    if persisted:
        _require(type(value["schema_version"]) is int and value["schema_version"] == 1 and value["lane"] == lane,
                 "observation_binding", "Observation schema/lane differs from its artifact")
        _authority(value, AUTHORITY_FIELDS)
    if lane == "ocr":
        spans = value["spans"]
        _require(value["status"] in ("observed", "no_legible_text") and isinstance(spans, list) and len(spans) <= 32,
                 "ocr_schema", "Invalid OCR status or span count")
        _require((value["status"] == "observed") == bool(spans), "ocr_schema", "OCR status and spans disagree")
        for span in spans:
            _fields(span, {"text_verbatim", "box_normalized"}, set(), "OCR span")
            _text(span["text_verbatim"], "OCR text")
            box = span["box_normalized"]
            if box is not None:
                _require(isinstance(box, list) and len(box) == 4 and
                         all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in box) and
                         box[0] < box[2] and box[1] < box[3], "ocr_box", "OCR box is not a normalized positive rectangle")
    else:
        aliases = {item["alias"] for item in case["candidates"]}
        ranking = value["ranking"]
        _require(isinstance(ranking, list) and len(ranking) == 3 and all(isinstance(item, str) for item in ranking)
                 and set(ranking) == aliases, "candidate_ranking", "Ranking must be a permutation of the case aliases")
        _require(value["identifiability"] in ("distinguishable", "insufficient"), "identifiability", "Unknown identifiability status")
        choice = ranking[0] if value["identifiability"] == "distinguishable" else None
        _require(value["proposed_candidate"] == choice, "proposal_mismatch", "Proposal must match identifiability and first-ranked alias")
        rows = value["observations"]
        _require(isinstance(rows, list) and len(rows) <= 3, "observation_bound", "Too many candidate observations")
        seen = set()
        for row in rows:
            _fields(row, {"candidate", "matching_visible_traits", "contradicting_visible_traits"}, set(), "candidate observation")
            candidate = row["candidate"]
            _require(isinstance(candidate, str) and candidate in aliases and candidate not in seen,
                     "observation_candidate", "Observation candidate is invalid or duplicated")
            seen.add(candidate)
            for key in ("matching_visible_traits", "contradicting_visible_traits"):
                _require(isinstance(row[key], list) and len(row[key]) <= 4, "trait_bound", "Too many visible traits")
                for trait in row[key]:
                    _text(trait, "visible trait", 160)
        extra = _fields(value["additional_observation"], {"kind", "reason"}, set(), "additional observation")
        _require(extra["kind"] in OBSERVATION_KINDS, "observation_kind", "Unsupported additional observation kind")
        _text(extra["reason"], "additional observation reason", empty=extra["kind"] == "none")
    return value


def _response(raw: bytes, receipt: dict, case: dict, lane: str, observation: dict | None) -> dict:
    _require(len(raw) == receipt["response_bytes"] and sha256_bytes(raw) == receipt["response_sha256"],
             "response_hash_mismatch", "Response bytes differ from the receipt digest or byte count")
    # HTTP error bodies and invalid-provider responses may legitimately be plain text.
    # They are hash-bound failure evidence, never parsed into a usable observation.
    parsed_completion = receipt["status"] == "observed_schema_valid" or "returned_model" in receipt
    if not parsed_completion:
        return {"validated_completion": False}
    value = _object(_json(raw), "provider response")
    _require(value.get("model") == receipt["returned_model"], "returned_model_mismatch", "Response model differs from receipt")
    usage = _usage(value.get("usage"), "response usage")
    _require(usage == receipt["usage"], "usage_mismatch", "Response usage differs from receipt")
    choices = value.get("choices")
    if receipt["status"] != "observed_schema_valid" and observation is None:
        return {"validated_completion": False}
    _require(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict),
             "completion_schema", "Exactly one completion is required")
    choice = choices[0]
    _require(choice.get("finish_reason") == receipt.get("finish_reason") == "stop",
             "completion_status", "Completion must finish with stop")
    content = _object(choice.get("message"), "completion message").get("content")
    _require(isinstance(content, str) and content.strip() and len(content.encode("utf-8")) <= MAX_OBSERVATION_BYTES,
             "completion_bound", "Completion content is missing or oversized")
    content = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", content)
    if fenced:
        content = fenced.group(1).strip()
    result = _observation(_json(content), lane, case, persisted=False)
    normalized = {**result, "schema_version": 1, "lane": lane,
                  "qualification": False, "action_authorized": False, "physical_identity_verified": False}
    if observation is not None:
        _require(normalized == observation, "observation_content_mismatch", "Persisted observation differs from actual completion content")
    return {"validated_completion": True}


def _read_pair(reader: _Artifacts, case: dict, lane: str, plan: dict) -> tuple[dict, dict | None]:
    stem = lane + "/" + case["case_id"] + "."
    raws = {suffix: reader.optional(stem + suffix, MAX_JSON_BYTES if suffix == "response.json" else MAX_OBSERVATION_BYTES)
            for suffix in ARTIFACT_SUFFIXES}
    request = _request(_json(raws["request.json"]), case, lane, plan) if raws["request.json"] is not None else None
    receipt = _receipt(_json(raws["receipt.json"]), case, lane, plan) if raws["receipt.json"] is not None else None
    observation = _observation(_json(raws["observation.json"]), lane, case) if raws["observation.json"] is not None else None
    result = {"case_id": case["case_id"], "lane": lane, "state": "missing",
              "receipt_status": receipt["status"] if receipt else None,
              "receipt_reported_attempts": receipt.get("attempts") if receipt else None,
              "provider_completion_known": receipt.get("provider_completion_known") if receipt else None,
              "reported_usage": receipt.get("usage") if receipt else None,
              "http_status": receipt.get("http_status") if receipt else None,
              "missing_artifacts": [], "validated_completion": False}
    for suffix in ("request.json", "receipt.json"):
        if raws[suffix] is None:
            result["missing_artifacts"].append(suffix)
    if receipt is not None:
        if request is not None and "request_sha256" in receipt:
            _require(request["request_sha256"] == receipt["request_sha256"], "request_hash_mismatch", "Request and receipt digests differ")
        if observation is not None:
            _require("observation_sha256" in receipt and sha256_bytes(raws["observation.json"]) == receipt["observation_sha256"],
                     "observation_hash_mismatch", "Observation digest is missing or differs from its receipt")
        if "response_bytes" in receipt:
            raw = raws["response.json"]
            if receipt["response_bytes"] > 0 and raw is None:
                result["missing_artifacts"].append("response.json")
            elif raw is not None:
                _require(receipt["response_bytes"] > 0, "response_hash_mismatch", "Unexpected response bytes for a receipt declaring no response")
                result.update(_response(raw, receipt, case, lane, observation))
        elif raws["response.json"] is not None:
            raise ContractError("unbound_response", "Response has no provider receipt digest")
        if receipt["status"] == "observed_schema_valid":
            if observation is None:
                result["missing_artifacts"].append("observation.json")
            if not result["missing_artifacts"] and result["validated_completion"]:
                result["state"] = "observed_schema_valid"
            else:
                result["state"] = "incomplete"
        else:
            result["state"] = "failed"
    else:
        result["state"] = "incomplete" if any(raw is not None for raw in raws.values()) else "missing"
    result["request_sha256"] = request["request_sha256"] if request else None
    result["observation_sha256"] = receipt.get("observation_sha256") if receipt else None
    return result, observation if result["state"] == "observed_schema_valid" else None


def _agreement(observations: dict[str, dict]) -> dict:
    available = [lane for lane in RANK_LANES if lane in observations]
    choices = {lane: observations[lane]["proposed_candidate"] for lane in available}
    if len(available) != 3:
        status = "partial"
    elif len(set(choices.values())) != 1:
        status = "disagreement"
    elif next(iter(choices.values())) is None:
        status = "all_abstain"
    else:
        status = "agreement"
    return {"status": status, "available_lanes": available,
            "missing_lanes": [lane for lane in RANK_LANES if lane not in observations],
            "reported_proposals": choices, "same_backbone_specialists_are_independent_models": False,
            "identity_decision": None, "action_authorized": False}


def _usage_summary(records: list[dict]) -> dict:
    fields = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        values = [record["reported_usage"][field] for record in records
                  if isinstance(record["reported_usage"], dict) and field in record["reported_usage"]]
        fields[field] = {"reported_sum": sum(values) if values else None,
                         "reporting_receipts": len(values), "pairs_without_reported_field": len(records) - len(values)}
    with_usage = sum(isinstance(record["reported_usage"], dict) for record in records)
    return {"basis": "Sums of supplied receipt fields; missing values are unknown, not zero actual usage.",
            "pairs_with_reported_usage": with_usage, "pairs_without_reported_usage": len(records) - with_usage,
            "fields": fields, "verified_cost_usd": None}


def _reconcile_run(run_dir, cases_path, expected_source_commit, expected_model) -> dict:
    _digest(expected_source_commit, "expected_source_commit", 40)
    _text(expected_model, "expected_model", 160)
    reader = _Artifacts(Path(run_dir))
    raw_plan = reader.optional("plan.json")
    _require(raw_plan is not None, "missing_file", "The run needs plan.json")
    plan = _plan(_json(raw_plan), expected_source_commit, expected_model)
    requested_lanes = plan["lanes"]
    _require(reader.lane_directories <= set(requested_lanes), "unexpected_artifact",
             "Run contains an unrequested lane directory")
    summary = reader.optional("summary.json")
    if summary is not None:
        _json(summary)  # Enforce bounded strict JSON, without using any summary claim.
    raw_cases = reader.read(Path(cases_path), "supplied_cases.json")
    _require(sha256_bytes(raw_cases) == plan["cases_sha256"], "case_hash_mismatch", "Supplied cases bytes differ from plan")
    manifest = _object(_json(raw_cases), "cases manifest")
    cases = _cases(manifest, plan)
    expected_names = {lane + "/" + case["case_id"] + "." + suffix
                      for case in cases for lane in requested_lanes for suffix in ARTIFACT_SUFFIXES}
    _require(reader.inventory <= expected_names | {"plan.json", "summary.json"},
             "unexpected_artifact", "Run contains duplicate, unknown, or out-of-slice case/lane artifacts")
    records = []
    case_results = []
    recommendations: dict[str, dict] = {}
    for case in cases:
        lanes = {}
        observations = {}
        for lane in requested_lanes:
            record, observation = _read_pair(reader, case, lane, plan)
            records.append(record)
            lanes[lane] = record
            if observation is not None:
                observations[lane] = observation
                if lane != "ocr":
                    extra = observation["additional_observation"]
                    if extra["kind"] != "none":
                        key = case["case_id"] + ":" + case["query"]["image_sha256"] + ":" + extra["kind"]
                        recommendation = recommendations.setdefault(key, {
                            "request_key": key, "case_id": case["case_id"],
                            "query_image_sha256": case["query"]["image_sha256"], "observation_kind": extra["kind"],
                            "status": "proposed", "captured": False, "requesting_lanes": [], "reasons": [],
                            "qualification": False, "action_authorized": False, "physical_identity_verified": False})
                        recommendation["requesting_lanes"].append(lane)
                        recommendation["reasons"].append({"lane": lane, "reason": extra["reason"],
                                                          "observation_sha256": record["observation_sha256"]})
        case_results.append({"case_id": case["case_id"], "query_image_sha256": case["query"]["image_sha256"],
                             "lanes": lanes, "ocr": observations.get("ocr"),
                             "specialist_observations": {lane: observations[lane] for lane in RANK_LANES if lane in observations},
                             "agreement": _agreement(observations)})
    reader.finish()
    valid = sum(record["state"] == "observed_schema_valid" for record in records)
    reported = [record for record in records if record["receipt_reported_attempts"] is not None]
    limits = [
        "Digests establish consistency of supplied files, not signatures or execution attestation.",
        "Source digests and commit declarations are not recomputed from a trusted source checkout.",
        "Actual request payloads are absent; matching request digests do not attest prompts or transmitted pixels.",
        "Image bytes and evaluation truth are not opened; image checks bind supplied manifest digests only.",
        "Preparation selection, family labels, image format and dimensions are declared, not independently reconstructed.",
        "Responses are the runner's sanitized persisted bytes, not original wire bytes or provider signatures.",
        "Model names and token usage are provider-reported; weights, billing, actual attempts and elapsed execution are not independently verified.",
        "Agreement is descriptive evidence from the same backbone; it grants no identity, qualification or action authority.",
        "Additional observation requests are proposals; no extra view is captured or observed by this consumer.",
        "These are development cases; reconciliation does not establish accuracy, accepted coverage or test qualification.",
        "summary.json claims are ignored; only checked per-pair artifacts determine completeness.",
        "Completeness covers only requested lanes and the declared case slice; campaigns are not joined and failed attempts are not superseded.",
    ]
    if manifest["source_commit"] != plan["source_commit"]:
        limits.append("Preparation and execution declare different commits; the exact preparation manifest is file-bound, but cross-commit source equivalence is not attested.")
    return {**advisory_fields("meta.retrieval-acceleration.r5-reconciliation"),
            "status": "COMPLETE" if valid == len(records) else "PARTIAL",
            "input_work_id": WORK_ID, "interface_commit": INTERFACE_COMMIT,
            "supported_interface_commits": list(SUPPORTED_INTERFACE_COMMITS),
            "plan_variant": "semantic_choice_subset" if "semantic_choice_schema" in plan else "legacy_four_lane",
            "requested_lanes": list(requested_lanes),
            "unrequested_lanes": [lane for lane in LANES if lane not in requested_lanes],
            "source_bindings": {"execution_commit": plan["source_commit"], "preparation_commit": manifest["source_commit"],
                                "execution_source_sha256": plan["source_sha256"], "preparation_source_sha256": manifest["source_hashes"],
                                "cases_sha256": plan["cases_sha256"], "model": plan["model"], "provider": plan["provider"],
                                "artifact_sha256": dict(sorted(reader.hashes.items()))},
            "counts": {"selected_cases": len(cases), "expected_pairs": len(records), "valid_observations": valid,
                       "failed_pairs": sum(record["state"] == "failed" for record in records),
                       "missing_or_incomplete_pairs": sum(record["state"] in ("missing", "incomplete") for record in records),
                       "receipts_reporting_attempts": len(reported), "receipt_reported_attempts": sum(record["receipt_reported_attempts"] for record in reported),
                       "pairs_without_reported_attempt_count": len(records) - len(reported),
                       "actual_call_count_known": False, "actual_inference_calls": None,
                       "verified_cost_usd": None, "bytes_read": reader.total_bytes},
            "reported_usage": _usage_summary(records),
            "cases": case_results, "additional_observation_requests": list(recommendations.values()),
            "limits": {"max_cases": 8, "max_lanes": 4, "max_artifacts": MAX_ARTIFACTS,
                       "max_json_bytes": MAX_JSON_BYTES, "max_total_bytes": MAX_TOTAL_BYTES},
            "limitations": limits}


def reconcile_run(run_dir, cases_path, expected_source_commit, expected_model) -> dict:
    """Reconcile supplied R5 artifacts without retries, inference or truth access.

    Incomplete/missing per-pair artifacts return PARTIAL. Contradictory, malformed,
    oversized, traversing or corrupted supplied evidence raises ContractError.
    Cases may have been prepared at an earlier commit than their execution plan.
    """
    try:
        return _reconcile_run(run_dir, cases_path, expected_source_commit, expected_model)
    except ContractError:
        raise
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise ContractError("invalid_input", "Artifact inputs do not match the bounded R5 contract") from exc
