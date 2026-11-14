"""Synthetic isolated R5 receipts; no images, provider calls or private inputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from contract import ContractError
from reconcile import INTERFACE_COMMIT, LANES, PROVIDER, PROVIDER_URL, WORK_ID, reconcile_run

SOURCE_COMMIT = "fbf27ab1ca3905ccc1c561cc6a6e7e9f05df9a5d"
MODEL = "nemotron-3.5-super-vl"


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def write_json(path: Path, value) -> bytes:
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    path.write_bytes(raw)
    return raw


def read_json(path: Path):
    return json.loads(path.read_text())


def make_run(tmp_path: Path, case_count: int = 1, *, semantic: bool = False, lanes=LANES) -> dict:
    """Build a visibly synthetic, structurally faithful R5 fixture.

    Returns keyword arguments directly accepted by reconcile_run. These files
    carry synthetic source digests and completions, never execution evidence.
    Declared image paths do not exist: the consumer must not read image pixels.
    """
    tmp_path = Path(tmp_path).absolute()
    tmp_path.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    cases_path = tmp_path / "cases.json"
    image_root = tmp_path / "synthetic-images-not-captured"
    source_commit = INTERFACE_COMMIT if semantic else SOURCE_COMMIT
    source_sha256 = {name: digest("SYNTHETIC SOURCE: " + name) for name in (
        "prepare_cases.py", "protocol.py", "provider.py", "run_specialists.py")}
    cases = []
    for index in range(8):
        case_id = f"q{index + 1:04d}"
        images = [{"image_path": str(image_root / (case_id + "-" + name + ".jpg")),
                   "image_sha256": digest("SYNTHETIC IMAGE DIGEST: " + case_id + ":" + name),
                   "source_view_index": 1 if name == "query" else 0}
                  for name in ("query", "c01", "c02", "c03")]
        cases.append({"case_id": case_id, "split": "dev", "image_root": str(image_root),
                      "confidence_quartile": index // 2 + 1, "query": images[0],
                      "candidates": [{"alias": alias, **item} for alias, item in zip(("c01", "c02", "c03"), images[1:])]})
    manifest = {
        "schema_version": 1, "work_id": WORK_ID, "source_commit": source_commit,
        "source_hashes": {name: source_sha256[name] for name in ("prepare_cases.py", "protocol.py")},
        "input_hashes": {name: digest("SYNTHETIC INPUT: " + name) for name in ("dataset", "r4_report", "predictions", "query_metrics")},
        "input_paths": {name: str(tmp_path / ("synthetic-" + name)) for name in ("dataset", "r4_report", "predictions", "query_metrics")},
        "selection": "synthetic fixture with two development cases per confidence quartile",
        "candidate_policy": "synthetic aliases; no target metadata in cases", "cases": cases,
        "query_count": 8, "distinct_families": 8, "unique_image_files": 32,
        "downloads": [], "downloaded_bytes": 0, "query_metadata_in_prompts": False,
        "candidate_metadata_in_prompts": False, "extra_view_observed": False,
        "qualification": False, "action_authorized": False,
        "evaluation_truth_sha256": digest("SYNTHETIC TRUTH IS NEVER LOADED"),
    }
    cases_raw = write_json(cases_path, manifest)
    plan = {
        "schema_version": 1, "work_id": WORK_ID, "source_commit": source_commit,
        "source_sha256": source_sha256, "cases_sha256": digest(cases_raw),
        "provider": PROVIDER, "model": MODEL, "lanes": list(lanes),
        "max_concurrent_calls": len(lanes), "maximum_inference_calls": len(lanes) * case_count,
        "start_index": 0, "case_count": case_count, "max_output_tokens_per_call": 1024,
        "max_attempts_per_job": 1, "chat_template_kwargs": {"enable_thinking": False},
        "response_format": "json_schema", "deadline_seconds": 900,
        "started_utc": "2026-11-14T21:30:00+00:00", "new_gpu_instances": 0,
        "same_backbone_specialists_are_independent_models": False, "verified_cost_usd": None,
        "qualification": False, "action_authorized": False,
    }
    if semantic:
        plan["semantic_choice_schema"] = True
    write_json(run_dir / "plan.json", plan)
    for lane in lanes:
        folder = run_dir / lane
        folder.mkdir()
        for case in cases[:case_count]:
            case_id = case["case_id"]
            common = {"case_id": case_id, "lane": lane, "split": "dev", "qualification": False}
            synthetic_request = json.dumps({"synthetic": True, "case_id": case_id, "lane": lane}).encode()
            request_hash = digest(synthetic_request)
            request = {**common, "request_sha256": request_hash, "cases_sha256": plan["cases_sha256"],
                       "query_image_sha256": case["query"]["image_sha256"],
                       "candidate_image_sha256": [] if lane == "ocr" else [item["image_sha256"] for item in case["candidates"]],
                       "status": "prepared_not_yet_observed_complete"}
            write_json(folder / (case_id + ".request.json"), request)
            content = {"status": "no_legible_text", "spans": []} if lane == "ocr" else {
                "ranking": ["c01", "c02", "c03"], "proposed_candidate": "c01",
                "identifiability": "distinguishable", "observations": [{
                    "candidate": "c01", "matching_visible_traits": ["Synthetic trait"], "contradicting_visible_traits": []}],
                "additional_observation": {"kind": "label_closeup" if lane in ("visual", "detail") else "none",
                                           "reason": "Synthetic request for a readable label" if lane in ("visual", "detail") else ""},
            }
            observation = {**content, "schema_version": 1, "lane": lane,
                           "qualification": False, "action_authorized": False, "physical_identity_verified": False}
            observation_raw = write_json(folder / (case_id + ".observation.json"), observation)
            usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
            response = {"model": MODEL, "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}}], "usage": usage}
            response_raw = write_json(folder / (case_id + ".response.json"), response)
            receipt = {**common, "schema_version": 1, "provider": PROVIDER, "url": PROVIDER_URL,
                       "requested_model": MODEL, "request_sha256": request_hash, "request_bytes": len(synthetic_request),
                       "started_utc": "2026-11-14T21:30:00+00:00", "attempts": 1,
                       "retry_performed": False, "provider_completion_known": True, "verified_cost_usd": None,
                       "usage": usage, "elapsed_seconds": 0.2, "ended_utc": "2026-11-14T21:30:00.200000+00:00",
                       "http_status": 200, "returned_model": MODEL, "finish_reason": "stop",
                       "response_sha256": digest(response_raw), "response_bytes": len(response_raw),
                       "observation_sha256": digest(observation_raw), "status": "observed_schema_valid"}
            write_json(folder / (case_id + ".receipt.json"), receipt)
    write_json(run_dir / "summary.json", {"status": "COMPLETE", "synthetic_fixture": True})
    return {"run_dir": run_dir, "cases_path": cases_path,
            "expected_source_commit": source_commit, "expected_model": MODEL}


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="r5-reconcile-synthetic-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.args = make_run(self.root)

    def artifact(self, lane="visual", suffix="receipt.json", case_id="q0001"):
        return self.args["run_dir"] / lane / (case_id + "." + suffix)

    def reconcile(self):
        return reconcile_run(**self.args)

    def change(self, path, change):
        value = read_json(path)
        change(value)
        write_json(path, value)
        return value

    def rebind_cases(self):
        case_hash = digest(self.args["cases_path"].read_bytes())
        self.change(self.args["run_dir"] / "plan.json", lambda item: item.update(cases_sha256=case_hash))
        for lane in LANES:
            self.change(self.artifact(lane, "request.json"), lambda item: item.update(cases_sha256=case_hash))

    def rebind_response(self, lane="visual"):
        raw = self.artifact(lane, "response.json").read_bytes()
        self.change(self.artifact(lane), lambda item: item.update(response_bytes=len(raw), response_sha256=digest(raw)))

    def rebind_observation(self, lane="visual"):
        raw = self.artifact(lane, "observation.json").read_bytes()
        self.change(self.artifact(lane), lambda item: item.update(observation_sha256=digest(raw)))

    def update_completion(self, lane, change):
        path = self.artifact(lane, "response.json")
        response = read_json(path)
        content = json.loads(response["choices"][0]["message"]["content"])
        change(content)
        response["choices"][0]["message"]["content"] = json.dumps(content)
        write_json(path, response)
        self.rebind_response(lane)
        observation = {**content, "schema_version": 1, "lane": lane, "qualification": False,
                       "action_authorized": False, "physical_identity_verified": False}
        write_json(self.artifact(lane, "observation.json"), observation)
        self.rebind_observation(lane)

    def assert_code(self, code):
        with self.assertRaises(ContractError) as raised:
            self.reconcile()
        self.assertEqual(code, raised.exception.code)

    def test_complete_preserves_authority_and_deduplicates_proposals(self):
        result = self.reconcile()
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("legacy_four_lane", result["plan_variant"])
        self.assertEqual(list(LANES), result["requested_lanes"])
        self.assertEqual([], result["unrequested_lanes"])
        self.assertEqual([SOURCE_COMMIT, INTERFACE_COMMIT], result["supported_interface_commits"])
        self.assertEqual(4, result["counts"]["valid_observations"])
        self.assertEqual(4, result["counts"]["receipt_reported_attempts"])
        self.assertIsNone(result["counts"]["actual_inference_calls"])
        for key in ("qualification", "action_authorized", "physical_identity_verified"):
            self.assertIs(result[key], False)
        self.assertEqual("agreement", result["cases"][0]["agreement"]["status"])
        self.assertIsNone(result["cases"][0]["agreement"]["identity_decision"])
        self.assertEqual("no_legible_text", result["cases"][0]["ocr"]["status"])
        requests = result["additional_observation_requests"]
        self.assertEqual(1, len(requests))
        self.assertEqual(["visual", "detail"], requests[0]["requesting_lanes"])
        self.assertEqual("proposed", requests[0]["status"])
        self.assertIs(requests[0]["captured"], False)
        self.assertEqual("q0001:" + result["cases"][0]["query_image_sha256"] + ":label_closeup", requests[0]["request_key"])
        self.assertFalse((self.root / "synthetic-images-not-captured").exists())
        self.assertEqual({"reported_sum": 480, "reporting_receipts": 4, "pairs_without_reported_field": 0},
                         result["reported_usage"]["fields"]["prompt_tokens"])
        self.assertEqual(120, result["reported_usage"]["fields"]["completion_tokens"]["reported_sum"])
        self.assertEqual(600, result["reported_usage"]["fields"]["total_tokens"]["reported_sum"])

    def test_full_eight_case_run_is_bounded_and_complete(self):
        args = make_run(self.root / "full", case_count=8)
        result = reconcile_run(**args)
        self.assertEqual(32, result["counts"]["expected_pairs"])
        self.assertEqual(32, result["counts"]["valid_observations"])
        self.assertEqual(8, len(result["additional_observation_requests"]))

    def test_current_semantic_full_plan_remains_complete(self):
        args = make_run(self.root / "semantic-full", case_count=8, semantic=True)
        result = reconcile_run(**args)
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("semantic_choice_subset", result["plan_variant"])
        self.assertEqual(INTERFACE_COMMIT, result["interface_commit"])
        self.assertEqual(INTERFACE_COMMIT, result["source_bindings"]["execution_commit"])
        self.assertEqual(32, result["counts"]["expected_pairs"])
        self.assertEqual(32, result["counts"]["valid_observations"])

    def test_current_critic_only_plan_completes_requested_work_with_partial_agreement(self):
        args = make_run(self.root / "critic-only", case_count=7, semantic=True, lanes=("critic",))
        result = reconcile_run(**args)
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual(["critic"], result["requested_lanes"])
        self.assertEqual(["ocr", "visual", "detail"], result["unrequested_lanes"])
        self.assertEqual(7, result["counts"]["expected_pairs"])
        self.assertEqual(7, result["counts"]["receipt_reported_attempts"])
        self.assertEqual(0, result["counts"]["missing_or_incomplete_pairs"])
        self.assertEqual(7, result["reported_usage"]["fields"]["prompt_tokens"]["reporting_receipts"])
        for case in result["cases"]:
            self.assertEqual(["critic"], list(case["lanes"]))
            self.assertIsNone(case["ocr"])
            self.assertEqual("partial", case["agreement"]["status"])
            self.assertEqual(["visual", "detail"], case["agreement"]["missing_lanes"])
            self.assertIsNone(case["agreement"]["identity_decision"])

    def test_current_ocr_only_has_no_invented_specialist_evidence(self):
        args = make_run(self.root / "ocr-only", semantic=True, lanes=("ocr",))
        result = reconcile_run(**args)
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual([], result["additional_observation_requests"])
        self.assertEqual({}, result["cases"][0]["specialist_observations"])
        self.assertEqual("partial", result["cases"][0]["agreement"]["status"])
        self.assertEqual(["visual", "detail", "critic"], result["cases"][0]["agreement"]["missing_lanes"])

    def test_current_subset_missing_requested_receipt_is_partial(self):
        args = make_run(self.root / "missing-subset", semantic=True, lanes=("detail", "critic"))
        (args["run_dir"] / "critic/q0001.receipt.json").unlink()
        result = reconcile_run(**args)
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(2, result["counts"]["expected_pairs"])
        self.assertEqual(1, result["counts"]["valid_observations"])
        self.assertEqual(1, result["counts"]["pairs_without_reported_attempt_count"])

    def test_current_plan_rejects_invalid_lane_sets(self):
        args = make_run(self.root / "invalid-lanes", semantic=True)
        path = args["run_dir"] / "plan.json"
        original = path.read_bytes()
        for lanes in ([], ["critic", "critic"], ["critic", "detail"], ["unknown"],
                      ["visual", {"lane": "critic"}], "critic"):
            with self.subTest(lanes=lanes):
                plan = json.loads(original)
                plan["lanes"] = lanes
                write_json(path, plan)
                with self.assertRaises(ContractError) as error:
                    reconcile_run(**args)
                self.assertEqual("lane_contract", error.exception.code)

    def test_current_plan_rejects_invalid_semantic_flag_and_unknown_fields(self):
        args = make_run(self.root / "invalid-semantic", semantic=True)
        path = args["run_dir"] / "plan.json"
        original = path.read_bytes()
        for flag in (False, None, 1, "true"):
            with self.subTest(flag=flag):
                plan = json.loads(original)
                plan["semantic_choice_schema"] = flag
                write_json(path, plan)
                with self.assertRaises(ContractError) as error:
                    reconcile_run(**args)
                self.assertEqual("unsupported_plan_variant", error.exception.code)
        plan = json.loads(original)
        plan["extra_semantic_policy"] = True
        write_json(path, plan)
        with self.assertRaises(ContractError) as error:
            reconcile_run(**args)
        self.assertEqual("unexpected_fields", error.exception.code)

    def test_legacy_subset_is_rejected_without_semantic_variant_marker(self):
        args = make_run(self.root / "legacy-subset", lanes=("critic",))
        with self.assertRaises(ContractError) as error:
            reconcile_run(**args)
        self.assertEqual("lane_contract", error.exception.code)

    def test_current_subset_rejects_incorrect_call_concurrency_and_attempt_budgets(self):
        args = make_run(self.root / "subset-budget", case_count=2, semantic=True, lanes=("critic",))
        path = args["run_dir"] / "plan.json"
        original = path.read_bytes()
        for field, value in (("max_concurrent_calls", 4), ("maximum_inference_calls", 8),
                             ("max_attempts_per_job", 2), ("max_concurrent_calls", True)):
            with self.subTest(field=field, value=value):
                plan = json.loads(original)
                plan[field] = value
                write_json(path, plan)
                with self.assertRaises(ContractError) as error:
                    reconcile_run(**args)
                self.assertEqual("run_budget_mismatch", error.exception.code)

    def test_current_subset_rejects_even_empty_unrequested_lane_directory(self):
        args = make_run(self.root / "unrequested-empty", semantic=True, lanes=("critic",))
        (args["run_dir"] / "visual").mkdir()
        with self.assertRaises(ContractError) as error:
            reconcile_run(**args)
        self.assertEqual("unexpected_artifact", error.exception.code)

    def test_current_subset_rejects_artifacts_from_unrequested_lane(self):
        args = make_run(self.root / "unrequested-artifact", semantic=True, lanes=("critic",))
        folder = args["run_dir"] / "visual"
        folder.mkdir()
        (folder / "q0001.receipt.json").write_bytes(self.artifact().read_bytes())
        with self.assertRaises(ContractError) as error:
            reconcile_run(**args)
        self.assertEqual("unexpected_artifact", error.exception.code)

    def test_summary_claim_cannot_replace_missing_lane(self):
        for file in (self.args["run_dir"] / "critic").iterdir():
            file.unlink()
        write_json(self.args["run_dir"] / "summary.json", {"status": "COMPLETE", "valid_observations": 999, "qualification": True})
        result = self.reconcile()
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(3, result["counts"]["receipt_reported_attempts"])
        self.assertEqual(1, result["counts"]["pairs_without_reported_attempt_count"])
        self.assertEqual("partial", result["cases"][0]["agreement"]["status"])
        self.assertIs(result["counts"]["actual_call_count_known"], False)

    def test_missing_each_required_success_artifact_is_partial(self):
        for suffix in ("request.json", "receipt.json", "response.json", "observation.json"):
            with self.subTest(suffix=suffix):
                path = self.artifact("visual", suffix)
                raw = path.read_bytes()
                path.unlink()
                result = self.reconcile()
                self.assertEqual("PARTIAL", result["status"])
                self.assertNotIn("visual", result["cases"][0]["specialist_observations"])
                self.assertEqual(["detail"], result["additional_observation_requests"][0]["requesting_lanes"])
                path.write_bytes(raw)

    def test_recorded_preparation_failure_is_partial_without_invented_attempt(self):
        for suffix in ("request.json", "response.json", "observation.json"):
            self.artifact("critic", suffix).unlink()
        write_json(self.artifact("critic"), {"case_id": "q0001", "lane": "critic", "split": "dev", "qualification": False,
                                            "status": "preparation_or_schema_error", "error_type": "ValueError", "error": "synthetic failure"})
        result = self.reconcile()
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(1, result["counts"]["failed_pairs"])
        self.assertIsNone(result["cases"][0]["lanes"]["critic"]["receipt_reported_attempts"])

    def test_transport_failure_keeps_completion_unknown(self):
        self.artifact("critic", "response.json").unlink()
        self.artifact("critic", "observation.json").unlink()
        receipt = read_json(self.artifact("critic"))
        for key in ("http_status", "returned_model", "finish_reason", "observation_sha256"):
            receipt.pop(key)
        receipt.update(status="transport_or_timeout_completion_unknown", provider_completion_known=False,
                       response_sha256=None, response_bytes=0, usage=None, error_type="TimeoutError")
        write_json(self.artifact("critic"), receipt)
        result = self.reconcile()
        self.assertEqual("PARTIAL", result["status"])
        self.assertIs(result["cases"][0]["lanes"]["critic"]["provider_completion_known"], False)

    def test_http_error_body_is_hash_bound_failure_evidence(self):
        self.artifact("critic", "observation.json").unlink()
        self.artifact("critic", "response.json").write_bytes(b"Temporary rate limit")
        receipt = read_json(self.artifact("critic"))
        for key in ("returned_model", "finish_reason", "observation_sha256"):
            receipt.pop(key)
        receipt.update(status="rate_limited", http_status=429, usage=None, retry_after="60")
        write_json(self.artifact("critic"), receipt)
        self.rebind_response("critic")
        result = self.reconcile()
        self.assertEqual("PARTIAL", result["status"])
        self.assertEqual(1, result["counts"]["failed_pairs"])

    def test_nonzero_start_slice_uses_only_selected_cases(self):
        args = make_run(self.root / "slice", case_count=8)
        plan = read_json(args["run_dir"] / "plan.json")
        plan.update(start_index=2, case_count=2, maximum_inference_calls=8)
        write_json(args["run_dir"] / "plan.json", plan)
        for lane in LANES:
            for file in (args["run_dir"] / lane).iterdir():
                if not file.name.startswith(("q0003.", "q0004.")):
                    file.unlink()
        result = reconcile_run(**args)
        self.assertEqual(["q0003", "q0004"], [case["case_id"] for case in result["cases"]])

    def test_commit_model_request_image_and_pair_corruption_rejected(self):
        changes = [
            (self.args["run_dir"] / "plan.json", "source_commit", "0" * 40, "source_commit_mismatch"),
            (self.args["run_dir"] / "plan.json", "model", "different-model", "model_or_provider_mismatch"),
            (self.artifact(), "returned_model", "different-model", "returned_model_mismatch"),
            (self.artifact(), "request_sha256", "0" * 64, "request_hash_mismatch"),
            (self.artifact("visual", "request.json"), "query_image_sha256", "0" * 64, "image_hash_mismatch"),
            (self.artifact(), "case_id", "q0002", "pair_binding"),
            (self.artifact(), "lane", "detail", "pair_binding"),
            (self.artifact(), "attempts", 2, "attempt_budget"),
            (self.artifact(), "qualification", True, "authority_escalation"),
        ]
        for path, key, value, code in changes:
            with self.subTest(key=key, path=path.name):
                original = path.read_bytes()
                self.change(path, lambda item: item.update({key: value}))
                self.assert_code(code)
                path.write_bytes(original)

    def test_case_bytes_must_match_plan(self):
        with self.args["cases_path"].open("ab") as handle:
            handle.write(b" ")
        self.assert_code("case_hash_mismatch")

    def test_response_hash_and_byte_count_are_verified(self):
        self.artifact("visual", "response.json").write_bytes(b"{}")
        self.assert_code("response_hash_mismatch")

    def test_observation_hash_is_verified(self):
        self.change(self.artifact("visual", "observation.json"), lambda item: item["additional_observation"].update(reason="Different synthetic reason"))
        self.assert_code("observation_hash_mismatch")

    def test_rehashed_observation_cannot_diverge_from_completion(self):
        self.change(self.artifact("visual", "observation.json"), lambda item: item["additional_observation"].update(reason="Different synthetic reason"))
        self.rebind_observation()
        self.assert_code("observation_content_mismatch")

    def test_response_model_and_usage_must_match_receipt(self):
        response_path = self.artifact("visual", "response.json")
        original = response_path.read_bytes()
        self.change(response_path, lambda item: item.update(model="other")); self.rebind_response()
        self.assert_code("returned_model_mismatch")
        response_path.write_bytes(original)
        self.change(response_path, lambda item: item["usage"].update(prompt_tokens=121, total_tokens=151)); self.rebind_response()
        self.assert_code("usage_mismatch")

    def test_bad_token_counts_are_rejected(self):
        self.change(self.artifact(), lambda item: item["usage"].update(prompt_tokens=True))
        self.assert_code("invalid_integer")

    def test_missing_usage_remains_unknown_in_aggregate(self):
        for lane in LANES:
            self.change(self.artifact(lane, "response.json"), lambda item: item.update(usage=None))
            self.rebind_response(lane)
            self.change(self.artifact(lane), lambda item: item.update(usage=None))
        usage = self.reconcile()["reported_usage"]
        self.assertEqual(4, usage["pairs_without_reported_usage"])
        for field in usage["fields"].values():
            self.assertIsNone(field["reported_sum"])
            self.assertEqual(0, field["reporting_receipts"])
            self.assertEqual(4, field["pairs_without_reported_field"])

    def test_partial_usage_counts_each_field_without_filling_missing_values(self):
        self.change(self.artifact("critic", "response.json"), lambda item: item.update(usage={"completion_tokens": 7}))
        self.rebind_response("critic")
        self.change(self.artifact("critic"), lambda item: item.update(usage={"completion_tokens": 7}))
        usage = self.reconcile()["reported_usage"]
        self.assertEqual(360, usage["fields"]["prompt_tokens"]["reported_sum"])
        self.assertEqual(3, usage["fields"]["prompt_tokens"]["reporting_receipts"])
        self.assertEqual(97, usage["fields"]["completion_tokens"]["reported_sum"])
        self.assertEqual(4, usage["fields"]["completion_tokens"]["reporting_receipts"])

    def test_failed_status_cannot_contradict_http_status(self):
        self.change(self.artifact(), lambda item: item.update(status="rate_limited"))
        self.assert_code("receipt_status_mismatch")

    def test_wrong_input_types_raise_contract_error(self):
        self.change(self.artifact(), lambda item: item.update(status={"unexpected": True}))
        self.assert_code("receipt_status")

    def test_summary_still_uses_strict_json_parser(self):
        (self.args["run_dir"] / "summary.json").write_text('{"status": 1, "status": 2}')
        self.assert_code("duplicate_json_key")

    def test_incomplete_completion_cannot_count_as_observed(self):
        self.change(self.artifact("visual", "response.json"), lambda item: item["choices"][0].update(finish_reason="length"))
        self.rebind_response()
        self.assert_code("completion_status")

    def test_fenced_json_completion_matches_persisted_observation(self):
        self.change(self.artifact("visual", "response.json"), lambda item: item["choices"][0]["message"].update(
            content="```json\n" + item["choices"][0]["message"]["content"] + "\n```"))
        self.rebind_response()
        self.assertEqual("COMPLETE", self.reconcile()["status"])

    def test_proposal_disagreement_does_not_select_a_winner(self):
        self.update_completion("critic", lambda item: item.update(ranking=["c02", "c01", "c03"], proposed_candidate="c02"))
        agreement = self.reconcile()["cases"][0]["agreement"]
        self.assertEqual("disagreement", agreement["status"])
        self.assertIsNone(agreement["identity_decision"])
        self.assertEqual({"visual": "c01", "detail": "c01", "critic": "c02"}, agreement["reported_proposals"])

    def test_unanimous_abstention_remains_abstention(self):
        for lane in ("visual", "detail", "critic"):
            self.update_completion(lane, lambda item: item.update(identifiability="insufficient", proposed_candidate=None))
        result = self.reconcile()
        self.assertEqual("all_abstain", result["cases"][0]["agreement"]["status"])
        self.assertIsNone(result["cases"][0]["agreement"]["identity_decision"])

    def test_observation_authority_and_semantic_mismatch_rejected(self):
        self.change(self.artifact("visual", "observation.json"), lambda item: item.update(action_authorized=True))
        self.rebind_observation(); self.assert_code("authority_escalation")

    def test_no_hidden_truth_in_selected_case_query_or_candidate(self):
        original = self.args["cases_path"].read_bytes()
        for target in ("case", "query", "candidate"):
            with self.subTest(target=target):
                manifest = json.loads(original)
                case = manifest["cases"][0]
                destination = case if target == "case" else case["query"] if target == "query" else case["candidates"][0]
                destination["truth_candidate_alias"] = "c01"
                write_json(self.args["cases_path"], manifest); self.rebind_cases()
                self.assert_code("unexpected_fields")

    def test_duplicate_case_and_duplicate_candidate_alias_rejected(self):
        original = self.args["cases_path"].read_bytes()
        self.change(self.args["cases_path"], lambda item: item["cases"][1].update(case_id="q0001")); self.rebind_cases()
        self.assert_code("duplicate_or_invalid_case")
        self.args["cases_path"].write_bytes(original)
        self.change(self.args["cases_path"], lambda item: item["cases"][0]["candidates"][1].update(alias="c01")); self.rebind_cases()
        self.assert_code("candidate_aliases")

    def test_same_commit_source_disagreement_rejected(self):
        self.change(self.args["cases_path"], lambda item: item["source_hashes"].update(protocol_py="0" * 64))
        self.rebind_cases(); self.assert_code("source_binding")

    def test_same_commit_source_hash_mismatch_rejected(self):
        self.change(self.args["cases_path"], lambda item: item["source_hashes"].update({"protocol.py": "0" * 64}))
        self.rebind_cases(); self.assert_code("source_hash_mismatch")

    def test_earlier_preparation_commit_is_explicit_not_falsely_equal(self):
        self.change(self.args["cases_path"], lambda item: item.update(source_commit="a" * 40))
        self.change(self.args["cases_path"], lambda item: item["source_hashes"].update({"protocol.py": "0" * 64}))
        self.rebind_cases()
        result = self.reconcile()
        self.assertEqual("COMPLETE", result["status"])
        self.assertEqual("a" * 40, result["source_bindings"]["preparation_commit"])
        self.assertTrue(any("different commits" in value for value in result["limitations"]))

    def test_duplicate_json_keys_nonfinite_and_overflow_rejected(self):
        path = self.artifact("visual", "request.json")
        original = path.read_bytes()
        for raw, code in ((b'{"a": 1, "a": 2}', "duplicate_json_key"),
                          (b'{"a": NaN}', "nonfinite_json"), (b'{"a": Infinity}', "nonfinite_json"),
                          (b'{"a": 1e999}', "nonfinite_json")):
            with self.subTest(raw=raw):
                path.write_bytes(raw); self.assert_code(code)
        path.write_bytes(original)

    def test_duplicate_json_keys_in_response_or_completion_rejected(self):
        response_path = self.artifact("visual", "response.json")
        original = response_path.read_bytes()
        response_path.write_bytes(b'{"model": "a", "model": "b"}')
        self.rebind_response(); self.assert_code("duplicate_json_key")
        response_path.write_bytes(original)
        self.change(response_path, lambda item: item["choices"][0]["message"].update(content='{"ranking": [], "ranking": []}'))
        self.rebind_response(); self.assert_code("duplicate_json_key")

    def test_unsafe_image_path_and_out_of_slice_artifacts_rejected(self):
        original = self.args["cases_path"].read_bytes()
        self.change(self.args["cases_path"], lambda item: item["cases"][0]["query"].update(image_path="/outside/query.jpg"))
        self.rebind_cases(); self.assert_code("image_path_binding")
        self.args["cases_path"].write_bytes(original); self.rebind_cases()
        self.artifact("visual", "receipt.json", "q0002").write_bytes(self.artifact().read_bytes())
        self.assert_code("unexpected_artifact")

    def test_symlink_and_oversize_artifact_rejected(self):
        path = self.artifact("visual", "request.json")
        backup = self.root / "request-backup.json"
        path.rename(backup); path.symlink_to(backup)
        self.assert_code("unsafe_path")
        path.unlink(); path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
        self.assert_code("oversize_json")

    def test_unknown_directory_and_nested_file_rejected(self):
        other = self.args["run_dir"] / "unclaimed-lane"
        other.mkdir()
        with self.assertRaises(ContractError):
            self.reconcile()
        other.rmdir()
        (self.args["run_dir"] / "visual" / "nested").mkdir()
        self.assert_code("unsafe_path")

    def test_invalid_expected_source_requires_explicit_full_commit(self):
        with self.assertRaises(ContractError) as error:
            reconcile_run(**{**self.args, "expected_source_commit": "main"})
        self.assertEqual("invalid_digest", error.exception.code)


if __name__ == "__main__":
    unittest.main()
