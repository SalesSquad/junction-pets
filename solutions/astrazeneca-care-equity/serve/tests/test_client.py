"""serve/client.py against a fake vLLM server: messages, request shape, confidence, routing, rows."""

import contextlib
import datetime
import io
import json
import math
import os
import pathlib
import socket
import tempfile
import unittest

import support
import client
import prompts as v1_prompts
from fake_vllm import API_KEY, FakeVLLM, logprob_items

ROWS = support.heldout()


def gold_answers(total_logprob=-0.01, fmt="absolute"):
    answers = {}
    for row in ROWS:
        content = row["target_json"] if fmt == "absolute" else support.compact(support.expression_json(row))
        answers[support.user_content(row)] = {"content": content, "total_logprob": total_logprob}
    return answers


def make_client(server, **kwargs):
    kwargs.setdefault("api_key", API_KEY)
    kwargs.setdefault("retries", 2)
    kwargs.setdefault("backoff", 0.0)
    kwargs.setdefault("sleep", lambda seconds: None)
    # The scripted answers spread one total log-probability over the tokens, so seq_prob is the
    # score these tests can state exactly. The client's own default is checked separately.
    kwargs.setdefault("confidence_kind", "seq_prob")
    return client.ScribeClient(server.base_url, **kwargs)


class Messages(unittest.TestCase):
    def test_messages_are_exactly_the_training_prompt(self):
        with FakeVLLM(gold_answers()) as server:
            c = make_client(server)
            for row in ROWS:
                self.assertEqual(c.build_request(row)["messages"], v1_prompts.messages(row))
            c.extract(ROWS[0])
            sent = server.requests[0]["payload"]
        self.assertEqual(sent["messages"], v1_prompts.messages(ROWS[0]))
        self.assertEqual([m["role"] for m in sent["messages"]], ["system", "user"])
        self.assertEqual(sent["messages"][1]["content"], f"Note date: {ROWS[0]['note_date']}\n{ROWS[0]['note_text']}")

    def test_request_shape_and_guided_json(self):
        schema = client.load_schema("absolute")
        with FakeVLLM(gold_answers()) as server:
            make_client(server).extract(ROWS[0])
            make_client(server, guided="structured_outputs").extract(ROWS[0])
            make_client(server, guided="none").extract(ROWS[0])
            first, second, third = (r["payload"] for r in server.requests)
            header = server.requests[0]
        self.assertEqual(first["model"], "pathway-scribe")
        self.assertEqual(first["temperature"], 0)
        self.assertEqual(first["max_tokens"], 384)
        self.assertIs(first["logprobs"], True)
        self.assertIs(first["stream"], False)
        self.assertEqual(first["response_format"],
                         {"type": "json_schema", "json_schema": {"name": "pathway_scribe_absolute", "schema": schema}})
        self.assertNotIn("structured_outputs", first)
        self.assertEqual(second["structured_outputs"], {"json": schema})
        self.assertNotIn("response_format", second)
        self.assertNotIn("response_format", third)
        self.assertNotIn("structured_outputs", third)
        for removed in ("guided_json", "guided_regex", "guided_choice", "guided_decoding_backend"):
            self.assertNotIn(removed, first)  # removed from vLLM in v0.12.0
        self.assertEqual(header["authorization"], "Bearer " + API_KEY)
        self.assertEqual(header["content_type"], "application/json")

    def test_key_never_appears_in_the_result(self):
        with FakeVLLM(gold_answers()) as server:
            result = make_client(server).extract(ROWS[0])
        self.assertNotIn(API_KEY, json.dumps(result, default=client.jsonable))

    def test_expression_format_needs_an_expression_prompt(self):
        with FakeVLLM(gold_answers()) as server:
            with self.assertRaises(client.ScribeError):
                make_client(server, fmt="expression").build_request(ROWS[0])
            with self.assertRaises(client.ScribeError):
                make_client(server, prompts_path=support.EXPRESSION_PROMPTS).build_request(ROWS[0])
            ok = make_client(server, fmt="expression", prompts_path=support.EXPRESSION_PROMPTS).build_request(ROWS[0])
        self.assertEqual(ok["response_format"]["json_schema"]["name"], "pathway_scribe_expression")
        self.assertEqual(ok["messages"][1], v1_prompts.messages(ROWS[0])[1])

    def test_missing_prompt_module(self):
        with self.assertRaises(client.ScribeError):
            client.load_prompts(support.TESTS / "no_such_prompts.py")

    def test_absolute_format_needs_a_messages_function(self):
        with FakeVLLM({}) as server:
            with self.assertRaises(client.ScribeError):
                make_client(server, prompts_path=support.TESTS / "fixtures" / "data_tools_like.py")

    def test_training_side_module_supplies_prompt_schema_and_resolver(self):
        """A module shaped like scribe/v2/data_tools.py wins over serve/schema.json."""
        import importlib.util

        path = support.TESTS / "fixtures" / "data_tools_like.py"
        spec = importlib.util.spec_from_file_location("data_tools_like_oracle", path)
        oracle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oracle)
        row = ROWS[0]
        answer = {"entry_route": json.loads(row["target_json"])["entry_route"],
                  "events": [{"type": f["type"], "when": f["expression"]} for f in row["facts"]]}
        with FakeVLLM({support.user_content(row): {"content": support.compact(answer), "total_logprob": math.log(0.9)}}) as server:
            c = make_client(server, fmt="expression", prompts_path=path, threshold=0.5)
            result = c.extract(row)
            sent = server.requests[0]["payload"]
        self.assertEqual(sent["messages"], oracle.expression_messages(row))
        self.assertEqual(sent["response_format"]["json_schema"]["schema"], oracle.EXPRESSION_SCHEMA)
        self.assertEqual(sent["response_format"]["json_schema"]["name"], "pathway_scribe_expression")
        self.assertEqual(result["canonical"], json.loads(row["target_json"]))
        self.assertEqual(result["decision"], "AUTO_ACCEPT")
        self.assertTrue(result["settings"]["schema"].endswith("data_tools_like.py:EXPRESSION_SCHEMA"))
        self.assertTrue(result["settings"]["resolver"].endswith("data_tools_like.py:resolve_expression"))
        self.assertEqual(result["settings"]["messages"], "expression_messages")
        self.assertEqual(len(result["confidence"]["event_probs"]), len(result["rows"]))
        # An answer in serve's own expression shape does not fit the training-side schema.
        own = support.compact(support.expression_json(row))
        with FakeVLLM({support.user_content(row): {"content": own}}) as server:
            wrong = make_client(server, fmt="expression", prompts_path=path).extract(row)
        self.assertEqual(wrong["status"], "invalid_output")

    def test_default_confidence_is_the_geometric_mean_token_probability(self):
        self.assertEqual(client.DEFAULT_CONFIDENCE, "geo_mean_prob")
        row = ROWS[0]
        spec = {"content": row["target_json"], "total_logprob": math.log(0.5)}
        with FakeVLLM({support.user_content(row): spec}) as server:
            result = client.ScribeClient(server.base_url, api_key=API_KEY, threshold=0.9).extract(row)
        self.assertEqual(result["settings"]["confidence_kind"], "geo_mean_prob")
        self.assertAlmostEqual(result["score"], 0.5 ** (1 / result["confidence"]["n_tokens"]))
        self.assertAlmostEqual(result["score"], math.exp(result["confidence"]["mean_logprob"]))
        self.assertEqual(result["decision"], "AUTO_ACCEPT")


class Confidence(unittest.TestCase):
    CONTENT = '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","date":"2024-03-05","precision":"DAY"},{"type":"FIRST_CONTACT","date":"2024-01-01","precision":"DAY"}]}'

    def test_scores_from_known_log_probabilities(self):
        items = logprob_items(self.CONTENT, token_logprobs=None, total_logprob=math.log(0.8))
        conf = client.confidence_from_logprobs(self.CONTENT, items)
        self.assertTrue(conf["aligned"])
        self.assertEqual(conf["n_tokens"], len(items) - 1)  # the end-of-turn token is not scored
        self.assertAlmostEqual(conf["seq_prob"], 0.8, places=12)
        self.assertAlmostEqual(conf["geo_mean_prob"], 0.8 ** (1 / conf["n_tokens"]), places=12)
        self.assertAlmostEqual(conf["min_prob"], 0.8 ** (1 / conf["n_tokens"]), places=12)

    def test_one_weak_token_sets_min_and_lands_in_its_event(self):
        n = len(logprob_items(self.CONTENT)) - 1
        weak = self.CONTENT.index("2024-03-05") // 3  # pseudo-tokens are 3 characters long
        logprobs = [0.0] * n
        logprobs[weak] = math.log(0.25)
        conf = client.confidence_from_logprobs(self.CONTENT, logprob_items(self.CONTENT, token_logprobs=logprobs))
        self.assertAlmostEqual(conf["seq_prob"], 0.25)
        self.assertAlmostEqual(conf["min_prob"], 0.25)
        self.assertAlmostEqual(conf["route_prob"], 1.0)
        self.assertAlmostEqual(conf["event_probs_output_order"][0], 0.25)
        self.assertAlmostEqual(conf["event_probs_output_order"][1], 1.0)

    def test_fences_and_trailing_tokens_are_outside_the_scored_span(self):
        text = "```json\n" + self.CONTENT + "\n```"
        n = len(logprob_items(text)) - 1
        inside = [i for i in range(n) if i * 3 + 3 > text.index("{") and i * 3 <= text.rindex("}")]
        logprobs = [math.log(0.5)] * n
        for i in inside:
            logprobs[i] = 0.0
        conf = client.confidence_from_logprobs(text, logprob_items(text, token_logprobs=logprobs))
        self.assertEqual(conf["n_tokens"], len(inside))
        self.assertAlmostEqual(conf["seq_prob"], 1.0)

    def test_non_ascii_tokens_align_by_bytes(self):
        text = '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","expression":"12 päivää sitten"}]}'
        n = len(logprob_items(text)) - 1
        logprobs = [0.0] * n
        logprobs[text.index("päivää") // 3] = math.log(0.5)
        conf = client.confidence_from_logprobs(text, logprob_items(text, token_logprobs=logprobs))
        self.assertTrue(conf["aligned"])
        self.assertAlmostEqual(conf["event_probs_output_order"][0], 0.5)
        self.assertAlmostEqual(conf["route_prob"], 1.0)

    def test_tokens_without_bytes_and_unaligned_fallback(self):
        items = [{"token": t, "logprob": -0.1} for t in ["{", '"a"', ":", "1", "}"]]
        conf = client.confidence_from_logprobs('{"a":1}', items)
        self.assertTrue(conf["aligned"])
        self.assertAlmostEqual(conf["sum_logprob"], -0.5)
        odd = [{"token": "token_id:5", "logprob": -0.2}, {"token": "<end_of_turn>", "logprob": -3.0}]
        conf = client.confidence_from_logprobs('{"a":1}', odd)
        self.assertFalse(conf["aligned"])
        self.assertAlmostEqual(conf["sum_logprob"], -0.2)
        self.assertIsNone(conf["event_probs_output_order"])

    def test_missing_or_impossible_log_probabilities_give_no_confidence(self):
        good = logprob_items('{"a":1}')
        self.assertIsNone(client.confidence_from_logprobs('{"a":1}', None))
        self.assertIsNone(client.confidence_from_logprobs('{"a":1}', []))
        for bad in (-9999.0, None, float("nan"), 0.5, True):
            items = [dict(i) for i in good]
            items[0]["logprob"] = bad
            self.assertIsNone(client.confidence_from_logprobs('{"a":1}', items), bad)


class Routing(unittest.TestCase):
    def one(self, spec, row=None, **kwargs):
        row = row or ROWS[0]
        with FakeVLLM({support.user_content(row): spec}) as server:
            result = make_client(server, **kwargs).extract(row)
            return result, server

    def test_confident_and_correct_is_auto_accepted(self):
        row = ROWS[0]
        result, _ = self.one({"content": row["target_json"], "total_logprob": math.log(0.97)}, threshold=0.9)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["decision"], "AUTO_ACCEPT")
        self.assertEqual(result["reasons"], [])
        self.assertAlmostEqual(result["score"], 0.97)
        self.assertEqual(result["canonical"], json.loads(row["target_json"]))
        self.assertEqual(result["finish_reason"], "stop")

    def test_no_threshold_means_review(self):
        result, _ = self.one({"content": ROWS[0]["target_json"], "total_logprob": math.log(0.999)})
        self.assertEqual(result["decision"], "HUMAN_REVIEW")
        self.assertEqual(result["reasons"], ["no_calibrated_threshold"])
        self.assertEqual(len(result["rows"]), len(json.loads(ROWS[0]["target_json"])["events"]))

    def test_below_threshold_means_review(self):
        result, _ = self.one({"content": ROWS[0]["target_json"], "total_logprob": math.log(0.6)}, threshold=0.9)
        self.assertEqual(result["decision"], "HUMAN_REVIEW")
        self.assertEqual(result["reasons"], ["below_threshold"])

    def test_threshold_is_inclusive(self):
        result, _ = self.one({"content": '{"entry_route":"PRIVATE","events":[]}',
                              "token_logprobs": [0.0] * 13}, threshold=1.0)
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["decision"], "AUTO_ACCEPT")

    def test_score_kinds_route_differently(self):
        spec = {"content": ROWS[0]["target_json"], "total_logprob": math.log(0.5)}
        seq, _ = self.one(spec, threshold=0.9, confidence_kind="seq_prob")
        geo, _ = self.one(spec, threshold=0.9, confidence_kind="geo_mean_prob")
        self.assertEqual(seq["decision"], "HUMAN_REVIEW")
        self.assertEqual(geo["decision"], "AUTO_ACCEPT")
        self.assertEqual(geo["settings"]["confidence_kind"], "geo_mean_prob")

    def test_invalid_output_is_never_accepted(self):
        for content in ["Potilas on", '{"entry_route":"PRIVATE"}',
                        '{"entry_route":"PRIVATE","events":[{"type":"BIOPSY","date":"2024-01-01","precision":"DAY"}]}',
                        '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","date":"2024-02-30","precision":"DAY"}]}']:
            result, _ = self.one({"content": content, "total_logprob": 0.0}, threshold=0.5)
            self.assertEqual(result["status"], "invalid_output", content)
            self.assertEqual(result["decision"], "HUMAN_REVIEW")
            self.assertIn("invalid_output", result["reasons"])
            self.assertEqual(result["rows"], [])
            self.assertIsNone(result["canonical"])
            self.assertTrue(result["errors"])

    def test_truncated_answer_is_reviewed(self):
        result, _ = self.one({"content": ROWS[0]["target_json"], "total_logprob": 0.0, "finish_reason": "length"}, threshold=0.5)
        self.assertEqual(result["decision"], "HUMAN_REVIEW")
        self.assertEqual(result["reasons"], ["finish_reason_length"])

    def test_event_after_note_date_is_reviewed(self):
        row = dict(ROWS[0])
        content = '{"entry_route":"PRIVATE","events":[{"type":"SPECIALIST_VISIT","date":"2031-01-14","precision":"DAY"}]}'
        result, _ = self.one({"content": content, "total_logprob": 0.0}, row=row, threshold=0.5)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reasons"], ["event_after_note_date"])
        self.assertEqual(result["decision"], "HUMAN_REVIEW")

    def test_no_log_probabilities_means_review(self):
        result, _ = self.one({"content": ROWS[0]["target_json"], "logprobs": False}, threshold=0.0)
        self.assertEqual(result["reasons"], ["no_confidence"])
        self.assertIsNone(result["score"])
        self.assertIsNone(result["rows"][0]["extraction_confidence"])
        items = logprob_items(ROWS[0]["target_json"])
        items[2]["logprob"] = -9999.0
        result, _ = self.one({"content": ROWS[0]["target_json"], "items": items}, threshold=0.0)
        self.assertEqual(result["reasons"], ["no_confidence"])

    def test_missing_episode_id_blocks_auto_accept(self):
        row = {"note_text": ROWS[0]["note_text"], "note_date": ROWS[0]["note_date"]}
        result, _ = self.one({"content": ROWS[0]["target_json"], "total_logprob": 0.0}, row=row, threshold=0.5)
        self.assertEqual(result["reasons"], ["missing_episode_id"])
        self.assertEqual(result["decision"], "HUMAN_REVIEW")

    def test_cold_start_is_retried(self):
        row = ROWS[0]
        with FakeVLLM({support.user_content(row): {"content": row["target_json"]}}, fail_first=2) as server:
            slept = []
            result = make_client(server, retries=3, backoff=0.5, sleep=slept.append).extract(row)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(slept, [0.5, 1.0])
        self.assertGreaterEqual(result["total_s"], result["latency_s"])

    def test_retries_run_out(self):
        row = ROWS[0]
        with FakeVLLM({support.user_content(row): {"content": row["target_json"]}}, fail_first=10) as server:
            result = make_client(server, retries=2).extract(row)
        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["decision"], "HUMAN_REVIEW")
        self.assertEqual(result["reasons"], ["http_error"])
        self.assertEqual(result["rows"], [])
        self.assertIsNone(result["latency_s"])

    def test_wrong_key_is_not_retried(self):
        row = ROWS[0]
        with FakeVLLM({support.user_content(row): {"content": row["target_json"]}}) as server:
            result = make_client(server, api_key="wrong").extract(row)
            self.assertEqual(server.requests, [])
        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["attempts"], 1)
        self.assertIn("401", result["errors"][0])
        self.assertNotIn("wrong", json.dumps(result, default=client.jsonable))

    def test_unknown_model_and_unexpected_body(self):
        row = ROWS[0]
        with FakeVLLM({support.user_content(row): {"content": row["target_json"]}}) as server:
            result = make_client(server, model="not-served").extract(row)
        self.assertEqual((result["status"], result["attempts"]), ("http_error", 1))
        result, _ = self.one({"body": {"choices": []}})
        self.assertEqual(result["status"], "bad_response")
        result, _ = self.one({"body": {"choices": [{"message": {"content": None}}]}})
        self.assertEqual(result["status"], "bad_response")

    def test_nothing_listening(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        c = client.ScribeClient(f"http://127.0.0.1:{port}", retries=1, backoff=0.0, sleep=lambda s: None, timeout=2)
        result = c.extract(ROWS[0])
        self.assertEqual(result["status"], "transport_error")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["decision"], "HUMAN_REVIEW")
        with self.assertRaises(client.ScribeError):
            c.list_models()

    def test_list_models(self):
        with FakeVLLM({}) as server:
            self.assertEqual(make_client(server).list_models(), ["gemma-base", "pathway-scribe"])
            with self.assertRaises(client.ScribeError):
                make_client(server, api_key="wrong").list_models()

    def test_expression_format_end_to_end(self):
        with FakeVLLM(gold_answers(math.log(0.95), "expression")) as server:
            c = make_client(server, fmt="expression", prompts_path=support.EXPRESSION_PROMPTS, threshold=0.9)
            results = client.run_batch(c, ROWS, concurrency=4)
            sent = server.requests[0]["payload"]
        self.assertEqual(sent["response_format"]["json_schema"]["schema"], client.load_schema("expression"))
        for row, result in zip(ROWS, results):
            self.assertEqual(result["canonical"], json.loads(row["target_json"]), row["id"])
            self.assertEqual(result["decision"], "AUTO_ACCEPT")
            self.assertEqual(len(result["confidence"]["event_probs"]), len(result["rows"]))

    def test_batch_keeps_input_order(self):
        with FakeVLLM(gold_answers()) as server:
            results = client.run_batch(make_client(server), ROWS, concurrency=8)
            self.assertEqual(len(server.requests), len(ROWS))
        self.assertEqual([r["id"] for r in results], [row["id"] for row in ROWS])
        self.assertTrue(all(r["canonical"] == json.loads(row["target_json"]) for r, row in zip(results, ROWS)))

    def test_per_event_scores_follow_canonical_order(self):
        content = '{"entry_route":"PRIVATE","events":[{"type":"DIAGNOSIS","date":"2024-03-05","precision":"DAY"},{"type":"FIRST_CONTACT","date":"2024-01-01","precision":"DAY"}]}'
        n = len(logprob_items(content)) - 1
        logprobs = [0.0] * n
        logprobs[content.index("2024-03-05") // 3] = math.log(0.25)
        row = {"id": "x", "note_text": "t", "note_date": "2024-06-01"}
        result, _ = self.one({"content": content, "token_logprobs": logprobs}, row=row)
        self.assertEqual([e["type"] for e in result["canonical"]["events"]], ["FIRST_CONTACT", "DIAGNOSIS"])
        self.assertAlmostEqual(result["confidence"]["event_probs"][0], 1.0)
        self.assertAlmostEqual(result["confidence"]["event_probs"][1], 0.25)


class ThresholdFile(unittest.TestCase):
    def write(self, **fields):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(fields, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    KEY = {"confidence_kind": "seq_prob", "format": "absolute", "guided": "response_format", "model": "pathway-scribe"}

    def test_key_is_what_the_client_reports(self):
        with FakeVLLM({}) as server:
            self.assertEqual(make_client(server).calibration_key(), self.KEY)

    def test_matching_file_loads(self):
        value, data = client.load_threshold(self.write(threshold=0.93, alpha=0.05, **self.KEY), self.KEY)
        self.assertEqual(value, 0.93)
        self.assertEqual(data["alpha"], 0.05)

    def test_mismatch_is_refused(self):
        for key, other in [("confidence_kind", "geo_mean_prob"), ("format", "expression"),
                           ("guided", "none"), ("model", "gemma-base")]:
            with self.assertRaises(client.ScribeError, msg=key):
                client.load_threshold(self.write(threshold=0.93, **dict(self.KEY, **{key: other})), self.KEY)
        with self.assertRaises(client.ScribeError):
            client.load_threshold(self.write(threshold=0.93), self.KEY)

    def test_bad_threshold_values_are_refused(self):
        for bad in (None, "0.9", 1.5, -0.1, True):
            with self.assertRaises(client.ScribeError, msg=repr(bad)):
                client.load_threshold(self.write(threshold=bad, **self.KEY), self.KEY)
        with FakeVLLM({}) as server:
            with self.assertRaises(client.ScribeError):
                make_client(server, threshold=1.2)


class EventRows(unittest.TestCase):
    def test_rows_fit_the_event_log_contract(self):
        contract = support.eventlog_contract()
        self.assertEqual(list(client.EVENT_LOG_COLUMNS), contract["columns"])
        row = ROWS[0]
        with FakeVLLM({support.user_content(row): {"content": row["target_json"], "total_logprob": math.log(0.9)}}) as server:
            result = make_client(server, threshold=0.5).extract(
                row, episode_id="ep-0001", context={"county": "HVA05", "cancer_site": "lung", "age_band": "60-64"})
        target = json.loads(row["target_json"])
        self.assertEqual(len(result["rows"]), len(target["events"]))
        for out, event in zip(result["rows"], target["events"]):
            self.assertEqual(list(out), contract["columns"])
            self.assertEqual(out["episode_id"], "ep-0001")
            self.assertEqual(out["event_type"], event["type"])
            self.assertIn(out["event_type"], contract["EVENT_TYPES"])
            self.assertEqual(out["event_date"], datetime.date.fromisoformat(event["date"]))
            self.assertIsInstance(out["event_date"], datetime.date)
            self.assertEqual(out["date_precision"], event["precision"])
            self.assertEqual(out["entry_route"], target["entry_route"])
            self.assertEqual(out["source"], "TEXT_EXTRACTED")
            self.assertIn(out["source"], contract["SOURCES"])
            self.assertIs(out["verified_by_human"], False)
            self.assertIs(out["synthetic"], True)
            self.assertAlmostEqual(out["extraction_confidence"], 0.9)
            self.assertTrue(0.0 <= out["extraction_confidence"] <= 1.0)
            self.assertEqual((out["county"], out["cancer_site"], out["age_band"]), ("HVA05", "lung", "60-64"))
        json.dumps(result, default=client.jsonable)

    def test_context_defaults_to_none_and_falls_back_to_row_id(self):
        row = ROWS[1]
        with FakeVLLM({support.user_content(row): {"content": row["target_json"]}}) as server:
            result = make_client(server).extract(row)
        self.assertEqual(result["rows"][0]["episode_id"], row["id"])
        self.assertIsNone(result["rows"][0]["county"])
        self.assertIsNone(result["rows"][0]["cancer_site"])
        self.assertIsNone(result["rows"][0]["age_band"])

    def test_rows_load_into_the_arrow_schema_when_pyarrow_is_present(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            self.skipTest("pyarrow not installed in this interpreter")
        import importlib.util

        spec = importlib.util.spec_from_file_location("eventlog_schema_for_test", support.ROOT / "eventlog" / "schema.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = client.event_rows(json.loads(ROWS[0]["target_json"]), "ep-1", 0.9,
                                 {"county": "HVA05", "cancer_site": "lung", "age_band": "60-64"})
        table = module.events_table(rows)
        self.assertEqual(table.num_rows, len(rows))
        self.assertEqual(table.schema, module.pathway_events)


class CommandLine(unittest.TestCase):
    def test_batch_cli_writes_results(self):
        with FakeVLLM(gold_answers(math.log(0.95))) as server, tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "results.jsonl")
            os.environ["SERVE_TEST_KEY"] = API_KEY
            self.addCleanup(os.environ.pop, "SERVE_TEST_KEY", None)
            # The run log is redirected so a unit test never writes runs/v2-serve.jsonl.
            import runlog
            original = runlog.PATH
            runlog.PATH = pathlib.Path(tmp) / "log.jsonl"
            self.addCleanup(setattr, runlog, "PATH", original)
            with contextlib.redirect_stderr(io.StringIO()):
                code = client.main(["--base-url", server.base_url, "--api-key-env", "SERVE_TEST_KEY",
                                    "--jsonl", str(support.HELDOUT), "--threshold", "0.9", "--out", out,
                                    "--retries", "0"])
            self.assertEqual(code, 0)
            lines = [json.loads(line) for line in pathlib.Path(out).read_text(encoding="utf-8").splitlines()]
            logged = [json.loads(line) for line in runlog.PATH.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), len(ROWS))
        self.assertTrue(all(line["decision"] == "AUTO_ACCEPT" for line in lines))
        self.assertEqual(lines[0]["rows"][0]["source"], "TEXT_EXTRACTED")
        self.assertEqual(lines[0]["settings"]["confidence_kind"], "geo_mean_prob")
        self.assertEqual(logged[0]["step"], "client_batch")
        self.assertNotIn(API_KEY, json.dumps(logged))

    def test_cli_argument_errors_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(client.main(["--base-url", "http://127.0.0.1:9", "--note-file", "/nonexistent"]), 2)
            self.assertEqual(client.main(["--base-url", "http://127.0.0.1:9", "--jsonl", str(support.HELDOUT),
                                          "--threshold", "0.5", "--threshold-file", "x.json"]), 2)
        self.assertIn("--note-date is required", err.getvalue())
        self.assertIn("not both", err.getvalue())


if __name__ == "__main__":
    unittest.main()
