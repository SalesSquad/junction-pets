"""Portable risk-based negative/positive contracts; never fake a hosted PASS."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("craci_feedback_v2",Path(__file__).with_name("compile.py"))
assert spec and spec.loader
fb=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

def fixture():
    def reg(version,first,baseline,candidate,novel,lost,unsafe,transitions):
        key="v10" if version=="v10" else "v11"
        return {
            "status":"succeeded",
            "source":{"repository":fb.REPO,"commit":fb.SOURCE[key]},
            "projectId":"rokoko","kind":"synthetic-test",
            "taskId":"rokoko.mujoco-prospective-train",
            "evidence":{"level":"source-reported",
                        "receiptSha256":"a"*64,
                        "ref":f"https://github.com/SalesSquad/junction-pets/actions/runs/{fb.RUN[key]}"},
            "dataset":{"split":"train","sampleCount":800,"sha256":fb.RAW_SHA[key],
                       "sampleSetSha256":"b"*64},
            "evaluation":{"kind":"train-only-prospective-physics",
                          "independentHoldout":False},
            "policySha256":None,
            "metrics":[
                {"id":"frozen-v5-safe-goals-total","value":baseline},
                {"id":f"{key}-safe-goals-total","value":candidate},
                {"id":f"{key}-novel-safe-goals-vs-frozen-v5","value":novel},
                {"id":f"{key}-lost-frozen-v5-safe-goals","value":lost},
                {"id":f"{key}-unsafe-trials","value":unsafe},
                {"id":"independently-verified-public-mask-transitions",
                 "value":transitions}
            ]
        }
    doc={
        "v10_registry":reg("v10",515000,37,26,0,11,0,38569),
        "v11_registry":reg("v11",517000,18,18,0,0,0,34992),
    }
    doc["v10_readout"]={
        "executed_head":fb.SOURCE["v10"],"dev_cal_test_ood_opened":False,
        "model_promotion_authorized":False,
        "near_seeds":list(range(515000,515128)),
        "clear_seeds":list(range(515128,515160)),
        "strategies":{"frozen_v5":{"safe_goals_all":37},
                      "v10_loss_informed":{"safe_goals_all":26}},
        "novel_v10_safe_near_goal_seeds":[],
        "lost_baseline_safe_near_goal_seeds":[515000,515001]}
    doc["v11_readout"]={
        "dev_cal_test_ood_opened":False,
        "new_model_promotion_authorized":False,
        "physical_goal250_tick_dwell_primary":True,
        "strategies":{"frozen_v5":{"safe_goals":18},
                      "v11_goal_preserving":{"safe_goals":18}},
        "novel_v11_safe_goal_seed_ids":[],
        "lost_frozen_v5_goal_seed_ids":[],
        "unsafe_v11_seed_ids":[]}
    originals={"full_transitions.jsonl.gz":fb.RAW_SHA["v11"],
               "training.json":"c"*64,"paired-readout.json":"d"*64}
    doc["v11_qualification"]={
        "experiment_complete":True,"independent_full_trace_public_mask_replay":True,
        "all_512_real_initial_worlds_replayed":True,
        "dev_cal_test_ood_opened":False,"independentHoldout":False,
        "promotion_authorized":False,"model_improvement_verified":False,
        "exact_source_sha":fb.SOURCE["v11"],"train_only_seed_start":517000,
        "selected_near_worlds":128,"selected_clear_worlds":32,
        "trials":800,"actual_real_option_transitions":34992,
        "independent_true_physics_positive_replay":{"claim_verified":True},
        "independent_true_physics_clear_goal_replay":{"claim_verified":True},
        "original_three_files_sha256":originals.copy(),
        "dataset_sha256":"b"*64,
        "novel_v11_safe_goal_seed_ids":[],
        "lost_v5_goal_seed_ids":[]}
    doc["v11_integrity"]={
        "source_head":fb.SOURCE["v11"],"promotion_authorized":False,
        "original_sha256":originals.copy(),"real_source_options":34992,
        "novel_v11_goals":[],"lost_v5_goals":[],"new_unsafe":[],
        "safe_v5_goals":18,"safe_v11_goals":18}
    doc["v11_manifest"]={
        "executed_head":fb.SOURCE["v11"],"training_only":True,
        "dev_cal_test_ood_opened":False,"model_promotion_authorized":False,
        "file_sha256":originals.copy()}
    doc["action_support"]={
        "publicObservationDimensions":18,"shieldedActionCount":7,
        "actions":[{"id":i,"name":name} for i,name in enumerate(fb.ACTION_NAMES)],
        "sources":[
            {"version":"v10","githubRun":fb.RUN["v10"],
             "sourceSha":fb.SOURCE["v10"],"originalTransitionsSha256":fb.RAW_SHA["v10"],
             "pairedTrainWorlds":160,"episodes":800,"optionEvents":38569,
             "executedPerAction":[650,2145,3982,20608,3,236,10945],
             "maskLegalPerAction":[27802,21675,21101,27797,27802,27802,38569],
             "distinctWorldsWithExecutedAction":[123,160,116,160,1,104,144],
             "distinctEpisodesWithExecutedAction":[208,365,252,641,1,104,599]},
            {"version":"v11","githubRun":fb.RUN["v11"],
             "sourceSha":fb.SOURCE["v11"],"originalTransitionsSha256":fb.RAW_SHA["v11"],
             "pairedTrainWorlds":160,"episodes":800,"optionEvents":34992,
             "executedPerAction":[297,703,4166,15303,0,251,14272],
             "maskLegalPerAction":[20998,15667,15305,20994,20998,20998,34992],
             "distinctWorldsWithExecutedAction":[123,130,113,159,0,112,155],
             "distinctEpisodesWithExecutedAction":[127,199,328,613,0,112,715]}
        ],
        "combined":{"optionEvents":73561,"sideLeftExecuted":35911,
                    "sideRightExecuted":3,"sideRightMaskLegal":48800,
                    "sideRightDistinctWorlds":1}}
    return doc

def positive(d):
    d=copy.deepcopy(d)
    r=d["v11_registry"]
    m={x["id"]:x for x in r["metrics"]}
    m["v11-safe-goals-total"]["value"]=19
    m["v11-novel-safe-goals-vs-frozen-v5"]["value"]=1
    d["v11_readout"]["strategies"]["v11_goal_preserving"]["safe_goals"]=19
    d["v11_readout"]["novel_v11_safe_goal_seed_ids"]=[517088]
    d["v11_qualification"]["novel_v11_safe_goal_seed_ids"]=[517088]
    d["v11_integrity"]["novel_v11_goals"]=[517088]
    d["v11_integrity"]["safe_v11_goals"]=19
    return d

def compile_fixture(d=None,**kwargs):
    return fb.compile_feedback(d or fixture(),{},**kwargs)

class FeedbackContracts(unittest.TestCase):
    def test_live_source_parent_pin(self):
        self.assertEqual(fb.PARENT_HEAD,"3ddc0fcf8b13df0e2dc750c02d84fdb9f2fb76ad")
        self.assertEqual(len(fb.PINNED_INPUTS),8)

    def test_canonical_data_hash_order_independent(self):
        self.assertEqual(fb.sha256(fb.canonical({"a":1,"b":2})),
                         fb.sha256(fb.canonical({"b":2,"a":1})))

    def test_git_blob_known_bytes(self):
        self.assertEqual(fb.git_blob(b"hello\n"),"ce013625030ba8dba906f756967f9e9ca394464a")

    def test_prospective_cohorts_disjoint_and_frozen_env_bounded(self):
        self.assertTrue(fb.check_next_ranges([]))
        self.assertEqual((fb.NEXT_TRAIN["pilot"]["start"],
                          fb.NEXT_TRAIN["independent_confirmation"]["start"]),
                         (518000,518512))

    def test_v11_actual_negative_trains_unsupported_right_action(self):
        out=compile_fixture()
        self.assertEqual(out["decision"],"TRAIN_MORE_FOR_UNSUPPORTED_ACTION")
        self.assertFalse(out["model_promotion_authorized"])
        self.assertEqual(out["paired_goal250"]["novel"],0)
        self.assertEqual(out["action_support"][4]["executed_events"],3)
        self.assertEqual(out["action_support"][4]["independent_train_worlds_executing"],1)
        self.assertEqual(out["action_support"][4]["legal_mask_events"],48800)

    def test_legal_is_never_counterfactual_training_label(self):
        out=compile_fixture()
        self.assertTrue(all(x["legal_not_an_unchosen_action_reward_label"]
                            for x in out["action_support"]))
        self.assertEqual(out["action_support"][6]["train_support_status"],
                         "TERMINAL_ABSTAIN_NOT_PHYSICAL_ACTION")

    def test_v10_candidate_stops_for_eleven_lost_goals(self):
        out=compile_fixture(candidate="v10")
        self.assertEqual(out["decision"],"STOP")
        self.assertIn("BASELINE_GOAL250_LOSS",out["reasons"])
        self.assertEqual(out["paired_goal250"]["lost"],11)

    def test_positive_without_raw_is_not_promotion(self):
        out=compile_fixture(positive(fixture()))
        self.assertEqual(out["decision"],"NO_PROMOTION")
        self.assertIn("NOVEL_GOAL_CLAIM_REQUIRES_ORIGINAL_RAW_RECHECK",out["reasons"])

    def test_prospective_positive_with_raw_reverification_still_only_confirmation(self):
        with patch.object(fb,"verify_original_raw",return_value={"reverified_here":True}):
            out=compile_fixture(positive(fixture()))
        self.assertEqual(out["decision"],"INDEPENDENT_TRAIN_CONFIRMATION")
        self.assertFalse(out["model_promotion_authorized"])
        self.assertFalse(out["job_dispatch_authorized"])

    def test_new_baseline_loss_stops(self):
        d=fixture()
        m={x["id"]:x for x in d["v11_registry"]["metrics"]}
        m["v11-safe-goals-total"]["value"]=17
        m["v11-lost-frozen-v5-safe-goals"]["value"]=1
        d["v11_readout"]["strategies"]["v11_goal_preserving"]["safe_goals"]=17
        d["v11_readout"]["lost_frozen_v5_goal_seed_ids"]=[517088]
        d["v11_qualification"]["lost_v5_goal_seed_ids"]=[517088]
        d["v11_integrity"]["lost_v5_goals"]=[517088]
        d["v11_integrity"]["safe_v11_goals"]=17
        out=compile_fixture(d)
        self.assertEqual(out["decision"],"STOP")

    def test_new_unsafe_stops(self):
        d=fixture()
        m={x["id"]:x for x in d["v11_registry"]["metrics"]}
        m["v11-unsafe-trials"]["value"]=1
        d["v11_readout"]["unsafe_v11_seed_ids"]=[517088]
        d["v11_integrity"]["new_unsafe"]=[517088]
        out=compile_fixture(d)
        self.assertEqual(out["decision"],"STOP")
        self.assertIn("UNSAFE_CANDIDATE_TRIAL",out["reasons"])

    def test_missing_verified_status_fails(self):
        d=fixture()
        d["v11_registry"]["status"]="failed"
        with self.assertRaisesRegex(fb.FeedbackStop,"REGISTRY_SOURCE"):
            compile_fixture(d)

    def test_wrong_source_commit_fails(self):
        d=fixture()
        d["v11_registry"]["source"]["commit"]="a"*40
        with self.assertRaisesRegex(fb.FeedbackStop,"SOURCE_TRAIN"):
            compile_fixture(d)

    def test_sealed_split_ever_opened_fails(self):
        d=fixture()
        d["v11_readout"]["dev_cal_test_ood_opened"]=True
        with self.assertRaisesRegex(fb.FeedbackStop,"GOAL250_OR_SEAL"):
            compile_fixture(d)

    def test_independent_replay_unverified_fails(self):
        d=fixture()
        d["v11_qualification"]["independent_full_trace_public_mask_replay"]=False
        with self.assertRaisesRegex(fb.FeedbackStop,"INDEPENDENT_PROOF"):
            compile_fixture(d)

    def test_duplicate_registry_metric_fails(self):
        d=fixture()
        d["v11_registry"]["metrics"].append(copy.deepcopy(d["v11_registry"]["metrics"][0]))
        with self.assertRaisesRegex(fb.FeedbackStop,"DUPLICATE_REGISTRY"):
            compile_fixture(d)

    def test_original_manifest_sha_mismatch_fails(self):
        d=fixture()
        d["v11_manifest"]["file_sha256"]["training.json"]="e"*64
        with self.assertRaisesRegex(fb.FeedbackStop,"MANIFEST_PROOF"):
            compile_fixture(d)

    def test_fake_novel_goals_without_proof_fails(self):
        d=fixture()
        m={x["id"]:x for x in d["v11_registry"]["metrics"]}
        m["v11-novel-safe-goals-vs-frozen-v5"]["value"]=1
        with self.assertRaisesRegex(fb.FeedbackStop,"NOVEL_LOST_UNSAFE"):
            compile_fixture(d)

    def test_action_support_aggregates_must_recount(self):
        d=fixture()
        d["action_support"]["combined"]["sideRightExecuted"]=23
        with self.assertRaisesRegex(fb.FeedbackStop,"COMBINED_ORIGINAL"):
            compile_fixture(d)

    def test_wrong_seven_action_abi_fails(self):
        d=fixture()
        d["action_support"]["publicObservationDimensions"]=17
        with self.assertRaisesRegex(fb.FeedbackStop,"18D_SEVEN_MASK"):
            compile_fixture(d)

    def test_unverified_ledger_fails(self):
        with self.assertRaisesRegex(fb.FeedbackStop,"UNVERIFIED"):
            compile_fixture(ledger=[{"start":518000,"end":518099,"split":"train"}])

    def test_reused_future_world_fails(self):
        with self.assertRaisesRegex(fb.FeedbackStop,"ALREADY_USED"):
            compile_fixture(ledger=[{"start":518045,"end":518059,
                                     "split":"train","verified":True}])

    def test_nonoverlapping_verified_ledger_is_allowed(self):
        out=compile_fixture(ledger=[{"start":514000,"end":514511,
                                     "split":"train","verified":True}])
        self.assertEqual(out["decision"],"TRAIN_MORE_FOR_UNSUPPORTED_ACTION")

    def test_expired_credit_cutoff_fails_closed(self):
        with self.assertRaisesRegex(fb.FeedbackStop,"EXPIRED"):
            compile_fixture(credit_cutoff="2026-11-14T21:00:00Z",
                            clock="2026-11-14T21:01:00Z")

    def test_31_minute_credit_admission_guard_exact_boundary(self):
        cutoff="2026-11-15T17:00:00Z"
        self.assertEqual(
            compile_fixture(credit_cutoff=cutoff,
                            clock="2026-11-15T16:28:59Z")["decision"],
            "TRAIN_MORE_FOR_UNSUPPORTED_ACTION")
        # At 16:29 UTC there are precisely 31 minutes remaining: STOP.
        for now in ("2026-11-15T16:29:00Z",
                    "2026-11-15T16:40:00Z",
                    "2026-11-15T16:59:59Z",
                    "2026-11-15T18:29:00+02:00"):
            with self.subTest(now=now):
                with self.assertRaisesRegex(fb.FeedbackStop,
                                            "CREDIT_WINDOW_31MIN_ADMISSION_STOP"):
                    compile_fixture(credit_cutoff=cutoff,clock=now)

    def test_current_credit_window_still_does_not_dispatch(self):
        out=compile_fixture(credit_cutoff="2026-11-15T21:00:00Z",
                            clock="2026-11-14T21:01:00Z")
        self.assertFalse(out["job_dispatch_authorized"])

    def test_real_science_stop_receipt_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"stop"
            with patch.object(fb,"source_head",return_value="a"*40), \
                 patch.object(fb,"read_pinned",return_value=(fixture(),{})):
                result=fb.main(["--mode","compile","--require-git",
                                "--expected-head","a"*40,
                                "--repo-root",tmp,"--candidate","v10",
                                "--output-dir",str(output)])
            self.assertEqual(result,2)
            self.assertEqual(json.loads((output/"feedback.json").read_text())["decision"],
                             "STOP")
            self.assertTrue((output/"manifest.json").is_file())

    def test_valid_negative_learning_does_not_exit_as_failed_science(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"learn"
            with patch.object(fb,"source_head",return_value="a"*40), \
                 patch.object(fb,"read_pinned",return_value=(fixture(),{})):
                result=fb.main(["--mode","compile","--require-git",
                                "--expected-head","a"*40,
                                "--repo-root",tmp,"--candidate","v11",
                                "--output-dir",str(output)])
            self.assertEqual(result,0)
            self.assertEqual(json.loads((output/"feedback.json").read_text())["decision"],
                             "TRAIN_MORE_FOR_UNSUPPORTED_ACTION")

    def test_utc_cutoff_requires_timezone(self):
        with self.assertRaisesRegex(fb.FeedbackStop,"UTC_CUTOFF_TIMEZONE"):
            fb.parse_utc("2026-11-14T21:00:00")

    def test_single_raw_stream_denied(self):
        with self.assertRaisesRegex(fb.FeedbackStop,"BOTH_ORIGINAL"):
            compile_fixture(raw_evidence={"v10":Path("/no/raw")})

    def test_wrong_raw_gzip_digest_denied_before_interpretation(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"raw.gz"
            with gzip.open(p,"wt") as f:f.write("{}\n")
            with self.assertRaisesRegex(fb.FeedbackStop,"HASH_MISMATCH"):
                fb.raw_support(p,"0"*64)

    def test_wilson_support_interval_not_causal_success_interval(self):
        l,u=fb.wilson(1,320)
        self.assertLess(l,1/320)
        self.assertGreater(u,1/320)
        self.assertEqual(fb.wilson(0,0),[0.,1.])

    def test_read_pinned_uses_original_git_blob_not_presentation_text(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);raw=b'{"status":"succeeded"}\n'
            (root/"test.json").write_bytes(raw)
            with patch.dict(fb.PINNED_INPUTS,
                            {"synthetic":("test.json",fb.git_blob(raw))},clear=True):
                d,p=fb.read_pinned(root)
            self.assertEqual(d["synthetic"]["status"],"succeeded")
            self.assertEqual(p["synthetic"]["file_sha256"],fb.sha256(raw))

    def test_read_pinned_rejects_edit_even_semantically_same(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);expected=b'{"a":1}\n';actual=b'{ "a": 1 }\n'
            (root/"test.json").write_bytes(actual)
            with patch.dict(fb.PINNED_INPUTS,
                            {"synthetic":("test.json",fb.git_blob(expected))},clear=True):
                with self.assertRaisesRegex(fb.FeedbackStop,"BLOB_DRIFT"):
                    fb.read_pinned(root)

if __name__=="__main__":
    unittest.main()
