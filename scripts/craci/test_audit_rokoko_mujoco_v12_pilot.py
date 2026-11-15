"""Portable fail-closed source/physics audit tests, no private archive needed."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

SOURCE=Path(__file__).with_name("audit_rokoko_mujoco_v12_pilot.py")
spec=importlib.util.spec_from_file_location("craci_v12_original_audit",SOURCE)
assert spec and spec.loader
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

def observation(*,obstacle=.065,object_y=0.,x=0.):
    v=np.zeros(18,dtype=np.float32)
    v[0]=x;v[1]=object_y;v[6]=.09;v[7]=obstacle
    v[9]=.99;v[10:12]=1.
    v[16]=.16
    return v.tolist()

def fake_event(*,success=False,contact=2,dwell=250,action=1):
    start=observation()
    finish=observation(x=.16)
    return dict(observation=start,mask=a.public_mask(start),action=action,
                reward=1.,cost=0,done=True,contacts_cumulative=contact,
                dwell_ticks_current=dwell,dwell_ticks_cumulative=dwell,
                success_info=success,next_observation=finish)

def fake_result(*,success=False,contact=2,dwell=250,unsafe=False,abstained=False):
    return dict(success=success,unsafe=unsafe,abstained=abstained,contacts=contact,
                dwell_ticks_final=dwell,total_reward=1.,physics_steps=1000)

def scans():
    out=[]
    for seed in range(518000,518512):
        obs=observation(obstacle=.065 if seed%3 else .15)
        out.append(dict(seed=seed,world_hash=f"unique-world-{seed}",
                        observation=obs,mask=a.public_mask(obs)))
    return out

def synthetic_public_trajectory_source():
    all_scans=scans()
    selected=a.derive_public_cohort(all_scans)
    trials=[]
    for r in selected:
        for arm in a.ARMS:
            trials.append(dict(seed=r["seed"],strategy=arm,
                               world_hash=r["world_hash"],
                               full_transition_sha256=a.sha(a.canonical([r["seed"],arm]))))
    return dict(executed_head=a.SOURCE,model_sha256=a.MODEL,plan_sha256=a.PLAN,
                all_512_public_initial_scans=all_scans,
                cohort=[dict(seed=r["seed"],world_hash=r["world_hash"]) for r in selected],
                trials=trials)

class OriginalV12AuditContract(unittest.TestCase):
    def test_exact_frozen_source_and_artifact_identity(self):
        self.assertEqual(a.SOURCE,"78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f")
        self.assertEqual(a.HARNESS,"4874d15dd68d3a809aaf7d769d6b5bef85d378bd")
        self.assertEqual(a.EXPECTED_ARTIFACT_SHA,
                         "f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311")

    def test_frozen_seven_action_abi(self):
        self.assertEqual(len(a.public_mask(observation())),7)
        self.assertEqual(set(a.ARMS),
                         {"frozen_v5","v12_phase_dwell_supported_actions",
                          "v12_right_side_action4_exploration_train_only"})

    def test_deadman_forces_all_motors_masked(self):
        o=observation();o[15]=1.
        self.assertEqual(a.public_mask(o),[0,0,0,0,0,0,1])

    def test_public_mask_rejects_nonfinite_and_bad_obs_size(self):
        with self.assertRaisesRegex(AssertionError,"18D"):
            a.public_mask([0.]*17)
        v=observation();v[7]=float("nan")
        with self.assertRaisesRegex(AssertionError,"NONFINITE"):
            a.public_mask(v)

    def test_first_public_observed_40_near_8_clear_only(self):
        r=a.derive_public_cohort(scans())
        self.assertEqual(len(r),48)
        self.assertEqual(sum(abs(row["observation"][7])<.122 for row in r),40)
        self.assertEqual(sum(abs(row["observation"][7])>=.122 for row in r),8)

    def test_missing_scan_seed_fails(self):
        r=scans();r[45]["seed"]=518100
        with self.assertRaisesRegex(AssertionError,"FRESH_TRAIN_SCAN_GAP"):
            a.derive_public_cohort(r)

    def test_repeated_scan_seed_fails(self):
        r=scans();r[1]["seed"]=r[0]["seed"]
        with self.assertRaisesRegex(AssertionError,"FRESH_TRAIN_SCAN_GAP"):
            a.derive_public_cohort(r)

    def test_wrong_original_public_mask_fails(self):
        r=scans();r[1]["mask"]=[1]*7
        with self.assertRaisesRegex(AssertionError,"PUBLIC_INITIAL_MASK"):
            a.derive_public_cohort(r)

    def test_missing_near_worlds_fails(self):
        r=scans()
        for row in r:
            row["observation"][7]=.15
            row["mask"]=a.public_mask(row["observation"])
        with self.assertRaisesRegex(AssertionError,"UNDERFILLED"):
            a.derive_public_cohort(r)

    def test_valid_physical_goal250_requires_raw_last_success(self):
        e=fake_event(success=True)
        self.assertTrue(a.validate_terminal_goal250(fake_result(success=True),[e]))

    def test_fake_250tick_goal_without_real_contact_fails(self):
        e=fake_event(success=True,contact=0)
        with self.assertRaisesRegex(AssertionError,"FAKE_GOAL250"):
            a.validate_terminal_goal250(fake_result(success=True,contact=0),[e])

    def test_fake_goal_with_raw_dwell_under250_fails(self):
        e=fake_event(success=True,dwell=249)
        with self.assertRaisesRegex(AssertionError,"FAKE_GOAL250"):
            a.validate_terminal_goal250(fake_result(success=True,dwell=249),[e])

    def test_fake_goal_with_zero_physics_fails(self):
        e=fake_event(success=True)
        row=fake_result(success=True);row["physics_steps"]=0
        with self.assertRaisesRegex(AssertionError,"FAKE_GOAL250"):
            a.validate_terminal_goal250(row,[e])

    def test_fake_goal_with_out_of_goal_public_observation_fails(self):
        e=fake_event(success=True)
        e["next_observation"][0]=0.
        with self.assertRaisesRegex(AssertionError,"FAKE_GOAL250"):
            a.validate_terminal_goal250(fake_result(success=True),[e])

    def test_forged_terminal_success_info_fails(self):
        e=fake_event(success=False)
        with self.assertRaisesRegex(AssertionError,"REAL_TERMINAL_FLAG"):
            a.validate_terminal_goal250(fake_result(success=True),[e])

    def test_terminal_abstain_must_use_option_six(self):
        e=fake_event(success=False,action=1)
        with self.assertRaisesRegex(AssertionError,"ABSTAIN_REQUIRES"):
            a.validate_terminal_goal250(fake_result(abstained=True),[e])

    def test_unsafe_trial_not_safe_goal(self):
        e=fake_event(success=False)
        e["cost"]=1
        self.assertFalse(a.validate_terminal_goal250(
            fake_result(unsafe=True),[e]))

    def test_signed_public_away_displacement_recomputed(self):
        first=observation(obstacle=.065,object_y=0.)
        last=observation(obstacle=.065,object_y=-.030)
        e=dict(observation=first,next_observation=last)
        self.assertAlmostEqual(
            a.validate_signed_public_progress(
                dict(lateral_displacement=.03,away_lateral_displacement=.03),[e]),.03)

    def test_fake_abs_lateral_motion_cannot_count_as_away(self):
        first=observation(obstacle=.065,object_y=0.)
        last=observation(obstacle=.065,object_y=.030)
        with self.assertRaisesRegex(AssertionError,"FORGED_SIGNED"):
            a.validate_signed_public_progress(
                dict(lateral_displacement=.03,away_lateral_displacement=.03),
                [dict(observation=first,next_observation=last)])

    def test_original_zip_digest_drift_rejected_before_unpacking(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"altered-original.zip"
            p.write_bytes(b"not the hosted original")
            d=Path(tmp)/"unpacked";d.mkdir()
            with self.assertRaisesRegex(AssertionError,"HOSTED_ARTIFACT_SHA"):
                a.unpack(p,d)

    def test_summary_canonical_hash_order_deterministic(self):
        self.assertEqual(a.sha(a.canonical({"a":1,"b":2})),
                         a.sha(a.canonical({"b":2,"a":1})))

    def test_public_trajectory_manifest_is_exact_hash_only_48_by_3(self):
        source=synthetic_public_trajectory_source()
        index=a.build_public_trajectory_index(source)
        self.assertEqual(index["schema"],a.TRACE_SCHEMA)
        self.assertEqual((len(index["worlds"]),len(index["trajectories"])),(48,144))
        self.assertFalse(index["contains_original_18d_observations"])
        self.assertEqual(set(index["worlds"][0]),{"seed","world_hash"})
        self.assertEqual(set(index["trajectories"][0]),
                         {"seed","strategy","full_transition_sha256"})

    def test_duplicate_public_trace_pair_rejected(self):
        source=synthetic_public_trajectory_source()
        source["trials"][1]=source["trials"][0]
        with self.assertRaisesRegex(AssertionError,"TRAJECTORY_INDEX_TRIAL"):
            a.build_public_trajectory_index(source)

    def test_changed_public_trace_world_hash_rejected(self):
        source=synthetic_public_trajectory_source()
        source["cohort"][0]["world_hash"]="forged-world"
        with self.assertRaisesRegex(AssertionError,"TRAJECTORY_INDEX_COHORT"):
            a.build_public_trajectory_index(source)

    def test_public_trace_canonical_file_bytes_reject_drift(self):
        index=a.build_public_trajectory_index(synthetic_public_trajectory_source())
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"trace-index.json"
            target.write_bytes(a.canonical(index)+b"\n")
            a.check_public_trajectory_index(target,index)
            target.write_bytes(target.read_bytes()+b" ")
            with self.assertRaisesRegex(AssertionError,"PUBLIC_TRAJECTORY_INDEX"):
                a.check_public_trajectory_index(target,index)

if __name__=="__main__":
    unittest.main()
