"""Contract checks use genuine tiny PNG bytes and synthetic provider responses."""
import base64
import copy
import struct
import unittest
import zlib

from nim_models import (MAX_IMAGE_BYTES, NANO_MODEL, OCR_MODEL,
                        build_nano_payload, build_ocr_payload, parse_ocr_response)


def rgb_png():
    def chunk(kind, payload):
        data = kind + payload
        return struct.pack(">I", len(payload)) + data + struct.pack(">I", zlib.crc32(data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


class NimContracts(unittest.TestCase):
    def response(self):
        return {"model": OCR_MODEL, "data": [{"index": 0, "text_detections": [{
            "text_prediction": {"text": "  SKU-01/O  ", "confidence": 0.91},
            "bounding_box": {"points": [{"x": 0.1, "y": 0.2}, {"x": 0.8, "y": 0.2},
                                         {"x": 0.8, "y": 0.4}, {"x": 0.1, "y": 0.4}]}}]}]}

    def messages(self, count=1):
        url = build_ocr_payload(rgb_png(), "image/png")["input"][0]["url"]
        return [{"role": "system", "content": "/no_think"},
                {"role": "user", "content": [{"type": "text", "text": "Compare visible evidence."}]
                 + [{"type": "image_url", "image_url": {"url": url}} for _ in range(count)]}]

    def test_image_bytes_are_preserved_and_mime_bound(self):
        source = rgb_png()
        payload = build_ocr_payload(source, "image/png")
        self.assertEqual(base64.b64decode(payload["input"][0]["url"].split(",", 1)[1]), source)
        self.assertEqual(payload["merge_levels"], ["word"])
        for raw, mime in ((source, "image/jpeg"), (source, "image/webp"), (b"", "image/png"),
                          ("not bytes", "image/png"), (b"x" * (MAX_IMAGE_BYTES + 1), "image/png")):
            with self.subTest(mime=mime), self.assertRaises(ValueError):
                build_ocr_payload(raw, mime)

    def test_ocr_preserves_text_and_geometry_without_authority(self):
        source = self.response(); preserved = copy.deepcopy(source)
        parsed = parse_ocr_response(source)
        self.assertEqual(source, preserved)
        self.assertEqual(parsed["status"], "observed")
        self.assertEqual(parsed["spans"][0]["text_verbatim"], "  SKU-01/O  ")
        self.assertEqual(parsed["spans"][0]["box_normalized"], [0.1, 0.2, 0.8, 0.4])
        self.assertFalse(parsed["action_authorized"])
        self.assertFalse(parsed["qualification"])

    def test_wellformed_empty_is_distinct_from_failure(self):
        empty = {"model": OCR_MODEL, "data": [{"index": 0, "text_detections": []}]}
        parsed = parse_ocr_response(empty)
        self.assertEqual(parsed["status"], "no_legible_text")
        self.assertEqual(parsed["provider_observation"], "no_text_detected")
        for obj in ({"error": "503"}, {}, {"model": OCR_MODEL, "data": []},
                    {"model": "wrong", "data": empty["data"]}):
            with self.assertRaises(ValueError): parse_ocr_response(obj)
        no_optional = self.response()
        detection = no_optional["data"][0]["text_detections"][0]
        detection.pop("bounding_box"); detection["text_prediction"].pop("confidence")
        span = parse_ocr_response(no_optional)["spans"][0]
        self.assertIsNone(span["box_normalized"])
        self.assertNotIn("confidence", span)

    def test_nonfinite_or_out_of_range_provider_values_fail(self):
        for bad in (float("nan"), float("inf"), -0.1, 1.1, True, "0.9", 10 ** 400):
            obj = self.response(); obj["data"][0]["text_detections"][0]["text_prediction"]["confidence"] = bad
            with self.subTest(value=bad), self.assertRaises(ValueError): parse_ocr_response(obj)
        obj = self.response(); obj["data"][0]["text_detections"][0]["bounding_box"]["points"][0]["x"] = float("nan")
        with self.assertRaises(ValueError): parse_ocr_response(obj)

    def test_nano_documents_four_images_and_copies_input(self):
        messages = self.messages(4)
        payload = build_nano_payload(messages)
        self.assertEqual(payload["model"], NANO_MODEL)
        self.assertEqual(payload["messages"], messages)
        messages[0]["content"] = "mutated caller"
        self.assertEqual(payload["messages"][0]["content"], "/no_think")
        self.assertNotIn("response_format", payload)
        with self.assertRaises(ValueError): build_nano_payload(self.messages(5))
        with self.assertRaises(ValueError): build_nano_payload(self.messages(), max_tokens=True)
        with self.assertRaises(ValueError): build_nano_payload(self.messages(), max_tokens=8193)

    def test_nano_refuses_unbound_urls_and_malformed_content(self):
        for url in ("https://example.com/unbound.png", "data:image/png;base64,invalid!",
                    "data:image/jpeg;base64," + base64.b64encode(rgb_png()).decode()):
            messages = self.messages(); messages[1]["content"][1]["image_url"]["url"] = url
            with self.subTest(url=url[:40]), self.assertRaises(ValueError): build_nano_payload(messages)
        with self.assertRaises(ValueError): build_nano_payload([{"role": "user", "content": "No image"}])
        messages = self.messages(); messages[1]["role"] = "assistant"
        with self.assertRaises(ValueError): build_nano_payload(messages)


if __name__ == "__main__":
    unittest.main()
