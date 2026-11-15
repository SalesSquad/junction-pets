import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evaluate import ROOT, evaluate, file_hash
from protocol import LANES, WORK_ID, parse_response


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def cohort(root):
    cases, truths = [], []
    for i in range(8):
        case_id, query = "q" + str(i + 1).zfill(4), "product" + str(i)
        true_alias = None if i == 7 else ("c01" if i % 2 == 0 else "c02")
        gallery, candidates = [], []
        for rank, alias in enumerate(("c01", "c02", "c03"), 1):
            pid = query if alias == true_alias else "wrong" + str(i) + alias
            gallery.append({"alias": alias, "source_view_index": 0,
                            "image_sha256": digest(case_id + alias), "image_path": "/no-image-access/" + alias})
            candidates.append({"alias": alias, "candidate_id": pid, "candidate_family": "g" + pid,
                               "r4_rank": rank, "rank_score": float(4 - rank), "exact_correct": alias == true_alias})
        cases.append({"case_id": case_id, "split": "dev", "confidence_quartile": i // 2 + 1,
                      "image_root": "/no-image-access", "query": {"image_path": "/no-image-access/query",
                      "image_sha256": digest(case_id), "source_view_index": 1}, "candidates": gallery})
        truths.append({"case_id": case_id, "split": "dev", "query_id": query, "query_family": "family" + str(i),
                       "truth_candidate_alias": true_alias, "baseline_correct": true_alias == "c01",
                       "baseline_candidate_id": candidates[0]["candidate_id"], "baseline_rank_score": 3.0,
                       "candidates": candidates})
    truth_path, cases_path = root / "truth.json", root / "cases.json"
    inputs = {name: digest(name) for name in ("dataset", "r4_report", "predictions", "query_metrics")}
    write(truth_path, {"work_id": WORK_ID, "input_hashes": inputs, "cases": truths})
    write(cases_path, {"work_id": WORK_ID, "input_hashes": inputs,
                      "evaluation_truth_sha256": file_hash(truth_path), "cases": cases})
    return cases_path, truth_path, cases


def rank_result(abstain=False, rank_first="c01"):
    ranking = [rank_first] + [c for c in ("c01", "c02", "c03") if c != rank_first]
    return {"ranking": ranking, "proposed_candidate": None if abstain else rank_first,
            "identifiability": "insufficient" if abstain else "distinguishable", "observations": [],
            "additional_observation": {"kind": "label_closeup" if abstain else "none",
                                       "reason": "Marking unreadable" if abstain else ""}}


def run_fixture(root, cases_path, cases, attempts, *, count=8, lanes=LANES):
    root.mkdir()
    plan = {"schema_version": 1, "work_id": WORK_ID, "cases_sha256": file_hash(cases_path),
            "source_commit": "a" * 40, "source_sha256": {"protocol.py": file_hash(ROOT / "protocol.py")},
            "provider": "synthetic-local-fixture", "model": "fixture-model", "lanes": list(lanes),
            "start_index": 0, "case_count": count, "maximum_inference_calls": len(lanes) * count}
    write(root / "plan.json", plan)
    by_lane = {lane: [] for lane in lanes}
    for lane, case_index, result in attempts:
        case = cases[case_index]; case_id = case["case_id"]
        folder = root / lane
        request = {"case_id": case_id, "lane": lane, "cases_sha256": file_hash(cases_path),
                   "request_sha256": digest(lane + case_id), "query_image_sha256": case["query"]["image_sha256"],
                   "candidate_image_sha256": [] if lane == "ocr" else [c["image_sha256"] for c in case["candidates"]]}
        write(folder / (case_id + ".request.json"), request)
        failed = result is None
        raw = {"model": "fixture-model", "choices": [{"finish_reason": "length" if failed else "stop",
                                                       "message": {"content": "" if failed else json.dumps(result)}}]}
        response_path = folder / (case_id + ".response.json"); write(response_path, raw)
        receipt = {"case_id": case_id, "lane": lane, "split": "dev", "qualification": False,
                   "request_sha256": request["request_sha256"], "http_status": 200,
                   "requested_model": "fixture-model", "returned_model": "fixture-model",
                   "provider_completion_known": True, "finish_reason": "length" if failed else "stop",
                   "response_sha256": file_hash(response_path), "response_bytes": response_path.stat().st_size,
                   "status": "preparation_or_schema_error" if failed else "observed_schema_valid"}
        if not failed:
            observation_path = folder / (case_id + ".observation.json")
            write(observation_path, parse_response(json.dumps(result), lane, case))
            receipt["observation_sha256"] = file_hash(observation_path)
        write(folder / (case_id + ".receipt.json"), receipt)
        by_lane[lane].append(receipt)
    summary = {**plan, "lanes": [{"lane": lane, "records": records} for lane, records in by_lane.items()],
               "attempted_cases": len(attempts), "valid_observations": sum(a[2] is not None for a in attempts),
               "status": "PARTIAL_OR_FAILED"}
    write(root / "summary.json", summary)
    return root


class EvaluationTests(unittest.TestCase):
    def test_failed_and_missing_queries_stay_in_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp, tp, cases = cohort(root)
            run = run_fixture(root / "run", cp, cases, [
                ("visual", 0, rank_result()), ("visual", 1, rank_result()),
                ("visual", 2, rank_result(abstain=True)), ("visual", 3, None),
                ("ocr", 0, {"status": "observed", "spans": [{"text_verbatim": "A", "box_normalized": None}]}),
                ("ocr", 1, {"status": "no_legible_text", "spans": []})])
            report = evaluate(cp, tp, [run]); visual = report["lanes"]["visual"]
            self.assertEqual(report["baseline_r4_rank1"]["numerator"], 4)
            self.assertEqual(report["candidate_recall_at_3_ranking_ceiling"]["numerator"], 7)
            self.assertEqual(visual["rank1_correct_all_queries"], {"numerator": 2, "denominator": 8, "rate": 0.25})
            self.assertEqual(visual["wrong_proposals"], 1)
            self.assertEqual(visual["model_abstentions"], 1)
            self.assertEqual(visual["operational_missing_or_failed"], 5)
            self.assertEqual(visual["total_no_proposal"], 6)
            self.assertEqual(report["lanes"]["ocr"]["observed_text_cases"], 1)
            self.assertIsNone(report["lanes"]["ocr"]["ocr_accuracy"])
            self.assertFalse(report["qualification"])

    def test_duplicate_successful_attempts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp, tp, cases = cohort(root)
            one = run_fixture(root / "one", cp, cases, [("visual", 0, rank_result())])
            two = run_fixture(root / "two", cp, cases, [("visual", 0, rank_result(rank_first="c02"))])
            with self.assertRaisesRegex(ValueError, "duplicate_selected_lane_case_attempt"):
                evaluate(cp, tp, [one, two])

    def test_failed_canary_is_explicitly_audited_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp, tp, cases = cohort(root)
            canary = run_fixture(root / "canary", cp, cases, [(lane, 0, None) for lane in LANES], count=1)
            selected = run_fixture(root / "selected", cp, cases, [("visual", 0, rank_result())])
            report = evaluate(cp, tp, [selected], [canary], "Generation setting repaired after empty canary.")
            self.assertEqual(report["all_audited_attempts"], 5)
            self.assertEqual(report["lanes"]["visual"]["attempted_cases"], 1)
            self.assertEqual(report["audit_only_runs"][0]["valid_observations"], 0)

    def test_tampered_observation_and_cases_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp, tp, cases = cohort(root)
            run = run_fixture(root / "run", cp, cases, [("visual", 0, rank_result())])
            op = run / "visual/q0001.observation.json"; original = op.read_bytes()
            op.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "observation_hash_mismatch"):
                evaluate(cp, tp, [run])
            op.write_bytes(original)
            changed = json.loads(cp.read_text()); changed["cases"][0]["image_root"] = "/changed"
            write(cp, changed)
            with self.assertRaisesRegex(ValueError, "run_case_binding_mismatch"):
                evaluate(cp, tp, [run])

    def test_explicit_failed_attempt_exclusion_and_critic_only_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp, tp, cases = cohort(root)
            first = run_fixture(root / "first", cp, cases, [("critic", 1, None)])
            resumed = run_fixture(root / "resumed", cp, cases, [("critic", 1, rank_result())], lanes=("critic",))
            failed = first / "critic/q0002.receipt.json"
            with self.assertRaisesRegex(ValueError, "duplicate_selected_lane_case_attempt"):
                evaluate(cp, tp, [first, resumed])
            report = evaluate(cp, tp, [first, resumed], selection_reason="Repair invalid critic proposal.", exclude_attempts=[failed])
            self.assertEqual(report["all_audited_attempts"], 2)
            self.assertEqual(report["selected_runs"][0]["attempts"], 1)
            self.assertEqual(report["lanes"]["critic"]["attempted_cases"], 1)
            self.assertEqual(report["lanes"]["critic"]["valid_observations"], 1)
            self.assertEqual(len(report["excluded_failed_attempts"]), 1)
            self.assertEqual(report["excluded_failed_attempts"][0]["receipt_sha256"], file_hash(failed))
            with self.assertRaisesRegex(ValueError, "cannot_exclude_valid_observation"):
                evaluate(cp, tp, [resumed], exclude_attempts=[resumed / "critic/q0002.receipt.json"])
            with self.assertRaisesRegex(ValueError, "excluded_attempt_not_found"):
                evaluate(cp, tp, [resumed], exclude_attempts=[root / "not-present.receipt.json"])

    def test_inconsistent_truth_is_rejected_even_with_updated_truth_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cp, tp, cases = cohort(root)
            run = run_fixture(root / "run", cp, cases, [])
            changed = json.loads(tp.read_text()); changed["cases"][0]["baseline_correct"] = False; write(tp, changed)
            document = json.loads(cp.read_text()); document["evaluation_truth_sha256"] = file_hash(tp); write(cp, document)
            with self.assertRaisesRegex(ValueError, "baseline_correctness_mismatch"):
                evaluate(cp, tp, [run])


if __name__ == "__main__":
    unittest.main()
