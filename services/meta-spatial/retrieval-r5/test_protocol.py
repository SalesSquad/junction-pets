import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from prepare_cases import choose_queries, safe_image_path, stable_key
from protocol import make_messages, parse_response


class ProtocolBoundaryTests(unittest.TestCase):
    def case(self, root):
        images = []
        for index, colour in enumerate(("red", "green", "blue", "yellow")):
            path = root / ("FORBIDDEN_PRODUCT_" + str(index) + ".png")
            Image.new("RGB", (16, 16), colour).save(path)
            images.append({"image_path": str(path), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        return {"case_id": "q0001", "split": "dev", "image_root": str(root),
                "query": {**images[0], "source_view_index": 1, "metadata_text": "FORBIDDEN_QUERY_TITLE"},
                "candidates": [{"alias": "c0" + str(i), **images[i], "source_view_index": 0,
                                "family_id": "FORBIDDEN_FAMILY"} for i in range(1, 4)],
                "truth_candidate_alias": "FORBIDDEN_TRUTH"}

    def test_message_allowlist_and_hash_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.case(Path(tmp))
            ocr = make_messages(case, "ocr")
            visual = make_messages(case, "visual")
            self.assertEqual(sum(x["type"] == "image_url" for x in ocr[1]["content"]), 1)
            self.assertEqual(sum(x["type"] == "image_url" for x in visual[1]["content"]), 4)
            self.assertNotIn("FORBIDDEN", json.dumps(visual))
            Path(case["query"]["image_path"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "image_hash_mismatch"):
                make_messages(case, "ocr")

    def test_no_query_pixels_as_extra_gallery_and_no_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); case = self.case(root)
            case["candidates"][0]["image_sha256"] = case["query"]["image_sha256"]
            with self.assertRaisesRegex(ValueError, "query_image_in_gallery"):
                make_messages(case, "visual")
            with self.assertRaises(ValueError): safe_image_path(root, "../escape.jpg")
            link = root / "link"; link.symlink_to(root / "missing")
            with self.assertRaises(ValueError): safe_image_path(root, "link/image.jpg")

    def test_strict_ocr_and_rank_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.case(Path(tmp))
            response = parse_response('```json\n{"status":"no_legible_text","spans":[]}\n```', "ocr", case)
            self.assertFalse(response["action_authorized"])
            with self.assertRaises(ValueError): parse_response('{"status":"observed","spans":[]}', "ocr", case)
            with self.assertRaises(ValueError): parse_response('{"status":"no_legible_text","status":"observed","spans":[]}', "ocr", case)
            with self.assertRaises(ValueError): parse_response('{"status":"observed","spans":[{"text_verbatim":"A","box_normalized":[0,0,NaN,1]}]}', "ocr", case)
            ranked = {"ranking": ["c03", "c01", "c02"], "proposed_candidate": None,
                      "identifiability": "insufficient", "observations": [],
                      "additional_observation": {"kind": "label_closeup", "reason": "Marking is not legible."}}
            self.assertIsNone(parse_response(json.dumps(ranked), "detail", case)["proposed_candidate"])
            ranked["proposed_candidate"] = "c03"
            with self.assertRaisesRegex(ValueError, "proposal_identifiability_mismatch"):
                parse_response(json.dumps(ranked), "detail", case)

    def test_selection_is_family_balanced_and_label_blind(self):
        records = {"p" + str(i): {"split": "dev", "family_id": "f" + str(i)} for i in range(32)}
        rows = [{"split": "dev", "query_id": pid, "confidence": str(i),
                 "exact_correct": "TRUE", "positive_rank": "1"} for i, pid in enumerate(records)]
        first = choose_queries(rows, records)
        for row in rows: row.update(exact_correct="FALSE", positive_rank="100")
        self.assertEqual(first, choose_queries(rows, records))
        self.assertEqual(len({r["family_id"] for r in first}), 8)
        self.assertEqual([r["confidence_quartile"] for r in first], [1, 1, 2, 2, 3, 3, 4, 4])
        ids = ["p1", "p2", "p3"]
        self.assertEqual(sorted(ids, key=lambda x: stable_key("q0001:" + x)),
                         sorted(reversed(ids), key=lambda x: stable_key("q0001:" + x)))


if __name__ == "__main__":
    unittest.main()
