#!/usr/bin/env python3
"""V11 original-source integrity precheck; NOT a physics replay certificate.

The existing CRACI independent MuJoCo replay/packaging admission is still
required. This precheck prevents an incomplete, cherry-picked, shortened or
mask-illegal original stream from being falsely promoted as complete evidence.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

from prospective_train import (ARMS, SCHEMA, derive_cohort, readout,
                               policy, require, sha, load_plan)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                                     ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def check_originals(root, expected_head):
    root=Path(root).resolve(strict=True)
    load_plan()
    require(len(expected_head)==40 and all(c in "0123456789abcdef" for c in expected_head),
            "V11_QUALIFICATION_EXPECTED_FULL_SOURCE_HEAD_REQUIRED")
    manifest=json.loads((root/"manifest.json").read_bytes())
    require(manifest["schema"]==SCHEMA+".manifest" and
            manifest["executed_head"]==expected_head and
            manifest["gateSha256"]==policy.GATE_SHA256 and
            manifest["training_only"] is True and
            manifest["model_promotion_authorized"] is False and
            manifest["actual_trials"]==800 and
            manifest["new_qualification_performed"] is False and
            set(manifest["file_sha256"])=={"training.json","full_transitions.jsonl.gz","paired-readout.json"},
            "V11_QUALIFICATION_MANIFEST_OR_PROMOTION_DRIFT")
    for name,checksum in manifest["file_sha256"].items():
        file=root/name
        require(file.is_file() and not file.is_symlink() and file.stat().st_nlink==1 and
                sha(file)==checksum,"V11_QUALIFICATION_ORIGINAL_FILE_HASH_DRIFT")
    training=json.loads((root/"training.json").read_bytes())
    require(training["schema"]==SCHEMA+".training" and
            training["executed_head"]==expected_head and
            training["training_only"] is True and
            training["no_dev_test_ood"] is True and
            training["model_promotion_authorized"] is False and
            training["candidate_source_gate_sha256"]==policy.GATE_SHA256 and
            training["actual_trials"]==800 and
            training["strategies"]==list(ARMS) and
            len(training["trials"])==800,
            "V11_QUALIFICATION_ORIGINAL_TRAINING_INVALID")
    cohort=derive_cohort(training["all_512_public_initial_scans"])
    require(training["cohort"]==cohort,"V11_QUALIFICATION_PUBLIC_COHORT_TAMPERED")
    bykey={(r["seed"],r["strategy"]):r for r in training["trials"]}
    require(len(bykey)==800 and set(bykey)=={(r["seed"],arm) for r in cohort for arm in ARMS},
            "V11_QUALIFICATION_MISSING_DUPLICATE_OR_CHANGED_PAIRED_ARM")
    for world in cohort:
        for arm in ARMS:
            row=bykey[world["seed"],arm]
            require(row["world_hash"]==world["world_hash"] and
                    row["observed_corridor"]==world["observed_corridor"],
                    "V11_QUALIFICATION_PAIRED_WORLD_OR_NEAR_CLEAR_CHANGED")
    total=0
    seen=set()
    with gzip.open(root/"full_transitions.jsonl.gz","rt",encoding="utf8") as handle:
        for line in handle:
            require(len(line)<2_000_000,"V11_QUALIFICATION_OVERSIZED_OR_BROKEN_OPTION_TRACE")
            data=json.loads(line)
            key=(data["seed"],data["strategy"])
            require(key in bykey and key not in seen and
                    len(data["transitions"])==bykey[key]["full_transition_count"] and
                    digest(data["transitions"])==bykey[key]["full_transition_sha256"],
                    "V11_QUALIFICATION_INCOMPLETE_OR_ALTERED_ORIGINAL_OPTION_TRACE")
            seen.add(key)
            for step in data["transitions"]:
                obs,mask=policy.validate_public_inputs(step["observation"],step["mask"])
                policy.validate_public_inputs(step["next_observation"],step["mask"])
                policy.checked_action(step["action"],mask)
            last=data["transitions"][-1]
            # The original V8/V7 independent verifier must additionally
            # re-run MuJoCo, 250-tick contact/dwell physics and costs. This is
            # only a source-consistency precheck against original bytes.
            source_goal=bool(last["success_info"] and
                             last["dwell_ticks_current"]>=250 and last["cost"]==0)
            require(source_goal==bool(bykey[key]["success"]),
                    "V11_QUALIFICATION_TERMINAL_250TICK_GOAL_CONTRADICTION")
            total+=len(data["transitions"])
    require(seen==set(bykey) and total==training["actual_option_transitions"]==
            manifest["actual_option_transitions"],
            "V11_QUALIFICATION_TRUNCATED_ORIGINAL_STREAM")
    source_readout=json.loads((root/"paired-readout.json").read_bytes())
    calculated=readout(training["trials"],cohort)
    require(source_readout==calculated,"V11_QUALIFICATION_SOURCE_SCIENCE_READOUT_DRIFT")
    return {"schema":SCHEMA+".source-integrity-readout",
            "source_head":expected_head,"trials":800,"real_source_options":total,
            "original_sha256":manifest["file_sha256"],
            "safe_v5_goals":calculated["strategies"]["frozen_v5"]["safe_goals"],
            "safe_v11_goals":calculated["strategies"]["v11_goal_preserving"]["safe_goals"],
            "lost_v5_goals":calculated["lost_frozen_v5_goal_seed_ids"],
            "novel_v11_goals":calculated["novel_v11_safe_goal_seed_ids"],
            "new_unsafe":calculated["unsafe_v11_seed_ids"],
            "science_precheck":calculated["source_only_preliminary_training_gate"],
            "independent_physics_replay_complete":False,
            "promotion_authorized":False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original-dir",type=Path,required=True)
    ap.add_argument("--expected-head",required=True)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    result=check_originals(args.original_dir,args.expected_head)
    require(not args.out.exists(),"V11_QUALIFICATION_NO_ORIGINAL_OVERWRITE")
    with args.out.open("x",encoding="utf8") as target:
        json.dump(result,target,sort_keys=True,indent=2);target.write("\n")
    print(json.dumps({"science_precheck":result["science_precheck"],
                      "trials":result["trials"],"original_options":result["real_source_options"],
                      "independent_physics_replay_complete":False,
                      "promotion_authorized":False},sort_keys=True))


if __name__=="__main__":main()
