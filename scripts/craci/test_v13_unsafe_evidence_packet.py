"""Portable synthetic negative checks of the V13 original unsafe packet."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"docs/craci/learning/rokoko-mujoco-v13-43660619725/verify_original.py"
spec=importlib.util.spec_from_file_location("source_bound_v13_unsafe",SOURCE)
assert spec and spec.loader
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def observation():
    o=[0.]*18
    o[2]=-.06;o[6]=.09;o[7]=.14
    o[9]=.99;o[10]=1.;o[11]=1.;o[16]=.16
    return o


def event(*,cost=0,done=False,action=2):
    o=observation()
    return dict(observation=o,next_observation=o.copy(),mask=v.public_mask(o),
                action=action,reward=.0,cost=cost,done=done,success_info=False,
                contacts_cumulative=0,dwell_ticks_cumulative=0,dwell_ticks_current=0)


def fixture():
    sizes=[5]+[6]*5+[18]+[19]*3+[20]*6+[21]*6+[38]
    assert len(sizes)==23 and sum(sizes)==394
    worlds={518003:"a"*64,518006:"b"*64}
    full=[];journal=[]
    for branch_id,n in enumerate(sizes):
        seed=518003 if branch_id<6 else 518006
        index=branch_id if branch_id<6 else branch_id-6
        name=f"v13-seen-train-{seed}-{index:02d}"
        prefix=5 if branch_id<6 else 18
        events=[event(cost=1 if branch_id==22 and i==37 else 0,
                      done=(branch_id==22 and i==37)) for i in range(n)]
        full.append(dict(branch_id=branch_id,seed=seed,source_prefix=prefix,
                         actions=[2]*n,transitions=events))
        for i,e in enumerate(events):
            journal.append(dict(branchId=name,seed=seed,
                                sourceWorldHash=worlds[seed],
                                forkOptionIndexZeroBased=prefix,
                                optionIndexZeroBased=i,
                                phase="ORIGINAL_PREFIX" if i<prefix else "COUNTERFACTUAL",
                                transition=e,transitionSha256=v.sha(v.canonical(e)),
                                sourceOnlyUnattestedExecution=True,
                                physicsQualificationPending=True))
    return full,journal,worlds


def validate(full,journal,worlds):
    synthetic=v.sha(v.canonical(full[-1]["transitions"][-1]))
    with patch.object(v,"UNSAFE_HASH",synthetic):
        return v.validate_branches_and_journal(full,journal,worlds)


class V13SafetyNegativeContract(unittest.TestCase):
    def test_original_frozen_sha_pins(self):
        self.assertEqual(v.ZIP_SHA,"cbbd78d255121102c39708ee2771f88c962e33e831ebce2b2c1c5d58769495b0")
        self.assertEqual(v.SOURCE,"0751d78b93855bf70820b03b0a543e123d218baf")
        self.assertEqual(v.HARNESS,"dc6d745c5facb56eed85016830dfe8f19b25032f")

    def test_real_seven_option_mask_size(self):
        self.assertEqual(v.public_mask(observation()),[1]*7)

    def test_deadman_only_allows_abstain(self):
        o=observation();o[15]=1.
        self.assertEqual(v.public_mask(o),[0,0,0,0,0,0,1])

    def test_bad_17d_or_nonfinite_observation_fails(self):
        with self.assertRaisesRegex(AssertionError,"PUBLIC_18D"):
            v.public_mask([0.]*17)
        o=observation();o[7]=float("nan")
        with self.assertRaisesRegex(AssertionError,"NONFINITE"):
            v.public_mask(o)

    def test_unmasked_synthetic_23_branches_394_original_options(self):
        full,journal,worlds=fixture()
        branches,unsafe=validate(full,journal,worlds)
        self.assertEqual((len(branches),sum(b["original_option_count"] for b in branches)),(23,394))
        self.assertEqual(unsafe["option_index_zero_based"],37)
        self.assertEqual(unsafe["action"],2)
        self.assertEqual(set(branches[-1]),{
            "branch_id","branch_name","seed","source_world_hash","source_prefix",
            "original_option_count","full_transitions_sha256","option_transition_sha256"})

    def test_second_unsafe_event_fails(self):
        f,j,w=fixture();f[0]["transitions"][0]["cost"]=1
        j[0]["transitionSha256"]=v.sha(v.canonical(j[0]["transition"]))
        with self.assertRaisesRegex(AssertionError,"EXACT_SOLE_PHYSICS_UNSAFE"):
            validate(f,j,w)

    def test_removed_original_unsafe_event_fails(self):
        f,j,w=fixture();f[-1]["transitions"][-1]["cost"]=0
        j[-1]["transitionSha256"]=v.sha(v.canonical(j[-1]["transition"]))
        with self.assertRaisesRegex(AssertionError,"EXACT_SOLE_PHYSICS_UNSAFE"):
            validate(f,j,w)

    def test_forged_unsafe_action_fails(self):
        f,j,w=fixture();f[-1]["transitions"][-1]["action"]=3
        f[-1]["actions"][-1]=3
        j[-1]["transitionSha256"]=v.sha(v.canonical(j[-1]["transition"]))
        with self.assertRaisesRegex(AssertionError,"EXACT_SOLE_PHYSICS_UNSAFE"):
            validate(f,j,w)

    def test_mask_denied_executed_option_fails(self):
        f,j,w=fixture()
        f[-1]["transitions"][-1]["mask"][2]=0
        j[-1]["transitionSha256"]=v.sha(v.canonical(j[-1]["transition"]))
        with self.assertRaisesRegex(AssertionError,"PUBLIC_ACTION_MASK"):
            validate(f,j,w)

    def test_nonfinite_source_observation_rejected(self):
        f,j,w=fixture();f[0]["transitions"][0]["observation"][8]=float("inf")
        with self.assertRaisesRegex(AssertionError,"PUBLIC_ACTION_MASK_OR_STATE"):
            validate(f,j,w)

    def test_journal_raw_transition_hash_tamper_fails(self):
        f,j,w=fixture();j[1]["transitionSha256"]="0"*64
        with self.assertRaisesRegex(AssertionError,"ORIGINAL_394_JOURNAL_HASH"):
            validate(f,j,w)

    def test_journal_phase_source_prefix_tamper_fails(self):
        f,j,w=fixture();j[1]["phase"]="COUNTERFACTUAL"
        with self.assertRaisesRegex(AssertionError,"ORIGINAL_394_JOURNAL_HASH"):
            validate(f,j,w)

    def test_journal_duplicate_option_index_fails(self):
        f,j,w=fixture();j[1]["optionIndexZeroBased"]=0
        with self.assertRaisesRegex(AssertionError,"ORIGINAL_394_JOURNAL_HASH"):
            validate(f,j,w)

    def test_wrong_source_world_hash_fails(self):
        f,j,w=fixture();j[0]["sourceWorldHash"]="c"*64
        with self.assertRaisesRegex(AssertionError,"ORIGINAL_BRANCH_JOURNAL_MAPPING"):
            validate(f,j,w)

    def test_fake_source_seed_outside_v12_frozen_cohort_fails(self):
        f,j,w=fixture();f[0]["seed"]=518511
        with self.assertRaisesRegex(AssertionError,"ORIGINAL_BRANCH_JOURNAL_MAPPING"):
            validate(f,j,w)

    def test_removed_branch_fails(self):
        f,j,w=fixture();f.pop()
        with self.assertRaisesRegex(AssertionError,"INCOMPLETE_OR_FORGED"):
            validate(f,j,w)

    def test_forged_goal_success_on_partial_branch_fails(self):
        f,j,w=fixture();f[0]["transitions"][0]["success_info"]=True
        j[0]["transitionSha256"]=v.sha(v.canonical(j[0]["transition"]))
        with self.assertRaisesRegex(AssertionError,"ORIGINAL_394_TRANSITIONS"):
            validate(f,j,w)

    def test_canonical_json_digest_order_stable(self):
        self.assertEqual(v.sha(v.canonical({"a":1,"b":2})),v.sha(v.canonical({"b":2,"a":1})))

    def test_previously_seen_zip_byte_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"modified.zip"
            path.write_bytes(b"not the original")
            with self.assertRaisesRegex(AssertionError,"HOSTED_ZIP_SHA"):
                v.original_bytes(path)

    def test_manifest_one_byte_tamper_fails(self):
        result={"status":"INCOMPLETE_STOP","unsafe":True}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"index.json"
            path.write_bytes(v.canonical(result)+b"\n")
            v.check_manifest(path,result)
            path.write_bytes(path.read_bytes()+b" ")
            with self.assertRaisesRegex(AssertionError,"PINNED_UNSAFE_HASH_ONLY"):
                v.check_manifest(path,result)

    def test_efficacy_claim_mode_never_promotable_for_original(self):
        self.assertEqual(v.classify_original_claim("INCOMPLETE_STOP","safety-negative"),
                         "STOP_UNSAFE")
        with self.assertRaisesRegex(AssertionError,"CANNOT_QUALIFY_EFFICACY"):
            v.classify_original_claim("INCOMPLETE_STOP","efficacy")
        with self.assertRaisesRegex(AssertionError,"UNEXPECTED_ORIGINAL_STATUS"):
            v.classify_original_claim("COMPLETE","safety-negative")

if __name__=="__main__":
    unittest.main()
