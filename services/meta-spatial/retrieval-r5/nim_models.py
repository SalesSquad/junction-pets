"""Pure NVIDIA NIM request/response contracts; no HTTP, credentials or image edits.

Limits below are local pilot guards, not advertised NVIDIA service limits.
MIME signatures are checked; the service remains responsible for decoding.
Nano callers must supply admitted RGB images. Its documented image-count
statements differ (4 versus 5), so this adapter conservatively permits four.
"""
from __future__ import annotations

import base64
import binascii
import copy
import math

OCR_MODEL = "nvidia/nemotron-ocr-v2"
OCR_ENDPOINT = "https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2"
NANO_MODEL = "nvidia/nemotron-nano-12b-v2-vl"
NANO_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
ALLOWED_ENDPOINTS = frozenset((OCR_ENDPOINT, NANO_ENDPOINT))
SOURCE_DOCS = {
    "ocr_hosted": "https://docs.nvidia.com/nemo/retriever/latest/extraction/prerequisites/index.html",
    "ocr_contract": "https://docs.nvidia.com/nim/ingestion/image-ocr/latest/use-the-api.html",
    "nano_contract": "https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl-infer",
    "nano_model": "https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_NANO_TOTAL_IMAGE_BYTES = 16 * 1024 * 1024
MAX_NANO_IMAGES = 4
MAX_TEXT_CHARACTERS = 65536
MAX_OCR_SPANS = 4096
MIME_PREFIXES = {"image/png": "data:image/png;base64,", "image/jpeg": "data:image/jpeg;base64,"}


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _finite(value, name, *, maximum=1.0):
    _require(type(value) in (int, float), "nonfinite_or_nonnumeric:" + name)
    try:
        value = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError("nonfinite_or_nonnumeric:" + name) from error
    _require(math.isfinite(value), "nonfinite_or_nonnumeric:" + name)
    _require(0 <= value <= maximum, "out_of_range:" + name)
    return float(value)


def _image(image_bytes, mime):
    _require(type(image_bytes) is bytes, "image_bytes_required")
    _require(isinstance(mime, str) and mime in MIME_PREFIXES, "only_png_or_jpeg_supported")
    _require(0 < len(image_bytes) <= MAX_IMAGE_BYTES, "image_exceeds_local_size_bound")
    signature_ok = (image_bytes.startswith(b"\x89PNG\r\n\x1a\n") if mime == "image/png"
                    else image_bytes.startswith(b"\xff\xd8\xff"))
    _require(signature_ok, "image_mime_signature_mismatch")
    return MIME_PREFIXES[mime] + base64.b64encode(image_bytes).decode("ascii")


def build_ocr_payload(image_bytes, mime):
    """Submit one actual image unchanged; no title, label or catalog hint field."""
    return {"input": [{"type": "image_url", "url": _image(image_bytes, mime)}],
            "merge_levels": ["word"]}


def parse_ocr_response(obj):
    """Normalize a successful single-image OCR response, never an HTTP failure.

    Empty detection is a provider observation, not a ground-truth absence claim.
    Missing optional confidence/geometry stays missing/null, never invented.
    Error-shaped or malformed results raise ValueError for the caller to record
    as schema/transport failure, distinct from a valid empty OCR response.
    """
    _require(isinstance(obj, dict) and "error" not in obj and obj.get("object") != "error", "ocr_object_required")
    _require(obj.get("model") == OCR_MODEL, "unexpected_ocr_model")
    data = obj.get("data")
    _require(isinstance(data, list) and len(data) == 1, "one_ocr_image_result_required")
    item = data[0]
    _require(isinstance(item, dict) and type(item.get("index")) is int and item["index"] == 0,
             "unexpected_ocr_image_index")
    detections = item.get("text_detections")
    _require(isinstance(detections, list) and len(detections) <= MAX_OCR_SPANS,
             "bounded_ocr_detections_required")
    spans, total_text = [], 0
    for detection in detections:
        _require(isinstance(detection, dict), "ocr_detection_object_required")
        prediction = detection.get("text_prediction")
        _require(isinstance(prediction, dict) and isinstance(prediction.get("text"), str),
                 "verbatim_ocr_text_required")
        text = prediction["text"]
        total_text += len(text)
        _require(total_text <= MAX_TEXT_CHARACTERS, "ocr_text_exceeds_local_bound")
        span = {"text_verbatim": text, "box_normalized": None}
        if "confidence" in prediction:
            span["confidence"] = _finite(prediction["confidence"], "confidence")
        box = detection.get("bounding_box")
        if box is not None:
            _require(isinstance(box, dict), "ocr_box_object_required")
            points = box.get("points")
            _require(isinstance(points, list) and len(points) == 4, "four_ocr_box_points_required")
            polygon = []
            for point in points:
                _require(isinstance(point, dict), "ocr_point_object_required")
                polygon.append([_finite(point.get("x"), "box_x"), _finite(point.get("y"), "box_y")])
            xs, ys = zip(*polygon)
            bounds = [min(xs), min(ys), max(xs), max(ys)]
            _require(bounds[0] < bounds[2] and bounds[1] < bounds[3], "degenerate_ocr_box")
            span["box_normalized"] = bounds
            span["polygon_normalized"] = polygon
        spans.append(span)
    visible = any(span["text_verbatim"].strip() for span in spans)
    result = {"status": "observed" if visible else "no_legible_text",
              "provider_observation": "text_detected" if visible else "no_text_detected",
              "model": OCR_MODEL, "spans": spans,
              "action_authorized": False, "physical_identity_verified": False,
              "qualification": False}
    if "usage" in obj:
        usage = obj["usage"]
        _require(isinstance(usage, dict), "ocr_usage_object_required")
        if "images_size_mb" in usage:
            result["usage"] = {"images_size_mb": _finite(usage["images_size_mb"], "images_size_mb",
                                                        maximum=float("inf"))}
    return result


def _data_image_size(url):
    _require(isinstance(url, str), "image_data_url_required")
    mime = next((mime for mime, prefix in MIME_PREFIXES.items() if url.startswith(prefix)), None)
    _require(mime is not None, "only_bound_png_jpeg_data_urls_supported")
    encoded = url[len(MIME_PREFIXES[mime]):]
    _require(len(encoded) <= 4 * ((MAX_IMAGE_BYTES + 2) // 3), "image_exceeds_local_size_bound")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("invalid_image_base64") from error
    canonical = _image(raw, mime)
    _require(canonical == url, "noncanonical_image_data_url")
    return len(raw)


def build_nano_payload(messages, max_tokens=1024):
    """Build a bounded documented chat request from caller-owned messages.

    No response_format/JSON-schema support is assumed. The caller validates the
    returned content against its experiment protocol. External URLs are refused
    so an admitted image cannot change between hashing and provider retrieval.
    """
    _require(type(max_tokens) is int and 1 <= max_tokens <= 8192, "invalid_nano_max_tokens")
    _require(isinstance(messages, list) and 1 <= len(messages) <= 20, "bounded_messages_required")
    text_count = image_count = image_bytes = 0
    for message in messages:
        _require(isinstance(message, dict) and set(message) == {"role", "content"}, "invalid_message_fields")
        role, content = message["role"], message["content"]
        _require(role in ("system", "assistant", "user"), "unsupported_message_role")
        if isinstance(content, str):
            text_count += len(content)
        else:
            _require(role == "user" and isinstance(content, list) and 1 <= len(content) <= 32,
                     "user_content_parts_required")
            for part in content:
                _require(isinstance(part, dict), "content_part_object_required")
                if part.get("type") == "text":
                    _require(set(part) == {"type", "text"} and isinstance(part["text"], str),
                             "invalid_text_part")
                    text_count += len(part["text"])
                elif part.get("type") == "image_url":
                    _require(set(part) == {"type", "image_url"} and isinstance(part["image_url"], dict)
                             and set(part["image_url"]) == {"url"}, "invalid_image_part")
                    image_bytes += _data_image_size(part["image_url"]["url"])
                    image_count += 1
                else:
                    raise ValueError("unsupported_content_part")
        _require(text_count <= MAX_TEXT_CHARACTERS, "nano_text_exceeds_local_bound")
        _require(image_count <= MAX_NANO_IMAGES and image_bytes <= MAX_NANO_TOTAL_IMAGE_BYTES,
                 "nano_images_exceed_local_bound")
    _require(image_count >= 1, "actual_image_required_for_nano_visual_pilot")
    return {"model": NANO_MODEL, "messages": copy.deepcopy(messages), "temperature": 0,
            "max_tokens": max_tokens, "stream": False}
