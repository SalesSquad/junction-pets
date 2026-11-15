"""V12: original byte-bound V10+V11 real TRAIN source, no inferred labels.

Read-only restoration of independently qualified source-reported CRACI original
streams; original hashes, provenance and exact full public-mask options are
all mandatory. No source rewriting, hidden state, DEV/TEST/OOD or new physics.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import zipfile


ROOT=Path(__file__).resolve().parent.parent
V11_EVIDENCE=ROOT/"v11_learning"/"evidence.py"
V11_PACKER_BLOB="5a7138a7467f05262ad76e9faa50c6b5f46c6c62"
V11_SOURCE_SHA="ab6df4054ef6ed350b479469590a48046a0c0a68"
V11_HARNESS_SHA="b1938bee9dbca482f645b5dde3359de38e6c125e"
V11_RUN=43653579339
V11_RECEIPT_ID="craci.43653579339.1.8f1cc4094148aab9"
V11_GATE_SHA="b115fc329b50f2557e8c6074734990dbcf6d1c5046516fbbda6158c5c513eaa8"
V11_SOURCE_FILE_SHA="1f47914371c9e2d627202075db4d72fe9a2547b85d1134ee9a899809db03d578"
V11_RAW={"training.json":"c3b3b399344fa18eff7a303cf27e2a510ab9eb74111a6216df1ec11a906579df",
         "full_transitions.jsonl.gz":"0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b"}
V11_PROOFS={"receipt.json":"d4218ccf76b889e1675b53c2017e01b172a77493f37d1605ab9e72bd557fff11",
    "retention-manifest.json":"f6e4858c7d443e5f71fa5183a7a1699c1ff185d515601747a00380ae01ccad56",
    "manifest.json":"1a5239cf28c66231bc6cbc68144c63b2f90bc66b0c7a5e32a1582ea3e441278f",
    "paired-readout.json":"cd50f5def18bba6741145d27e1f07652f6d6c366a0609a04e0a060612f817e4d",
    "independent-qualification.json":"1a15574beee17d5315cd28a91ec65cf055371d924c61abe4877ba9b0224df7e8",
    "independent-positive-replay.json":"f13f8c6b344cc17679ae85c5fcb4fa2cab85bf2cce095306e3e6da9e566823df",
    "independent-clear-goal-replay.json":"52c5661e3b20183e26946457742edf710666fc1d7b7a8df7000c46fee4a90309",
    "source-integrity.json":"7d19c7aa88afdbcdaa604cd033719759bcb9b500d7cf3a9a6891bb896487c47b"}
V11_STRATEGIES=("frozen_v5","frozen_v6","frozen_v8","v10_loss_informed","v11_goal_preserving")


def require(ok, reason):
    if not ok:raise ValueError(reason)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def checked(path,expected):
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink==1,
            "V12_ORIGINAL_EVIDENCE_FILE_MISSING_OR_UNSAFE")
    b=path.read_bytes()
    require(sha(b)==expected,"V12_ORIGINAL_EVIDENCE_FILE_SHA_MISMATCH")
    return b


def blob(path):
    raw=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def load_packer(path):
    path=Path(path).resolve(strict=True)
    require(path.is_file() and not path.is_symlink() and blob(path)==V11_PACKER_BLOB,
            "V12_UNREVIEWED_EXTERNAL_V11_PACKER")
    spec=importlib.util.spec_from_file_location("v12_source_pinned_v11_evidence_packer",path)
    require(spec is not None and spec.loader is not None,"V12_V11_PACKER_IMPORT_FAILED")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_v10(archive,receipt,source_root):
    spec=importlib.util.spec_from_file_location("v12_immutable_v10_reader",V11_EVIDENCE)
    require(spec is not None and spec.loader is not None,"V12_FROZEN_V10_READER_MISSING")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    original,rows,traces,proofs=mod.load_retained_raw(Path(archive),Path(receipt),Path(source_root))
    return {"run":"v10","training":original,"rows":rows,"traces":traces,
            "sourceSha":mod.V10_SOURCE_SHA,"harnessSha":mod.V10_HARNESS_SHA,
            "trainingSha256":mod.V10_RAW["training.json"],
            "fullTransitionsSha256":mod.V10_RAW["full_transitions.jsonl.gz"]}


def load_v11(archive,receipt,packer_path):
    archive=Path(archive).resolve(strict=True)
    receipt=Path(receipt).resolve(strict=True)
    require(archive.is_dir() and not archive.is_symlink(),"V12_V11_ARCHIVE_MISSING_OR_UNSAFE")
    proof={}
    for name,checksum in V11_PROOFS.items():
        p=receipt if name=="receipt.json" else archive/name
        proof[name]=json.loads(checked(p,checksum))
    r=proof["receipt.json"]
    bind=r["binding"]
    m=proof["manifest.json"]
    qual=proof["independent-qualification.json"]
    readout=proof["paired-readout.json"]
    require(bind["sourceSha"]==m["executed_head"]==V11_SOURCE_SHA and
            bind["harnessSha"]==V11_HARNESS_SHA and bind["runId"]==V11_RECEIPT_ID and
            bind["workload"]=="rokoko-mujoco-v11-prospective" and
            r["sourceVerified"] is True and r["harnessVerified"] is True and
            r["evidenceLevel"]=="source-reported" and r["status"]=="succeeded" and
            r["jobStatus"]=="success" and r["command"]["exitCode"]==0 and
            r["evidenceUrl"]==f"https://github.com/SalesSquad/junction-pets/actions/runs/{V11_RUN}/attempts/1" and
            m["file_sha256"]["training.json"]==V11_RAW["training.json"] and
            m["file_sha256"]["full_transitions.jsonl.gz"]==V11_RAW["full_transitions.jsonl.gz"] and
            m["source_sha256"]["prospective_train.py"]==V11_SOURCE_FILE_SHA and
            m["gateSha256"]==V11_GATE_SHA and m["actual_trials"]==800 and
            m["actual_option_transitions"]==34992 and m["training_only"] is True and
            m["model_promotion_authorized"] is False and
            qual["decision"]=="valid_source_bound_five_way_train_only_evidence" and
            qual["exact_source_sha"]==V11_SOURCE_SHA and
            qual["actual_real_option_transitions"]==34992 and
            qual["independent_full_trace_public_mask_replay"] is True and
            qual["all_512_real_initial_worlds_replayed"] is True and
            qual["experiment_complete"] is True and
            qual["dev_cal_test_ood_opened"] is False and
            readout["lost_frozen_v5_goal_seed_ids"]==[] and
            readout["novel_v11_safe_goal_seed_ids"]==[] and
            readout["unsafe_v11_seed_ids"]==[] and
            readout["strategies"]["frozen_v5"]["safe_goals"]==18 and
            readout["strategies"]["v11_goal_preserving"]["safe_goals"]==18,
            "V12_V11_QUALIFIED_800_TRAIN_SOURCE_OR_NEGATIVE_SCIENCE_DRIFT")
    packer=load_packer(packer_path)
    packer.verify_archive_parts(archive,proof["retention-manifest.json"])
    reconstructed={}
    for source in proof["retention-manifest.json"]["sources"]:
        blocks=[]
        for part in source["parts"]:
            with zipfile.ZipFile(archive/part["archive"]) as z:
                require(z.namelist()==[part["entry"]],"V12_V11_ZIP_ENTRY_MISMATCH")
                blocks.append(z.read(part["entry"]))
        reconstructed[source["name"]]=b"".join(blocks)
        require(sha(reconstructed[source["name"]])==V11_RAW[source["name"]],
                "V12_REASSEMBLED_ORIGINAL_V11_SHA_CHANGED")
    training=json.loads(reconstructed["training.json"])
    full=[json.loads(line) for line in gzip.decompress(reconstructed["full_transitions.jsonl.gz"]).splitlines()]
    require(training["actual_trials"]==len(full)==800 and
            training["actual_option_transitions"]==34992 and
            training["executed_head"]==V11_SOURCE_SHA and
            len(training["all_512_public_initial_scans"])==512 and
            tuple(training["strategies"])==V11_STRATEGIES and
            training["training_only"] is True and
            training["no_dev_test_ood"] is True and
            training["model_promotion_authorized"] is False,
            "V12_V11_ORIGINAL_TRAIN_MATRIX_DRIFT")
    rows={(r["seed"],r["strategy"]):r for r in training["trials"]}
    require(len(rows)==800 and len({s for s,_ in rows})==160,
            "V12_V11_DUPLICATE_OR_MISSING_TRIAL")
    traces={}
    options=0
    for row in full:
        key=(row["seed"],row["strategy"])
        require(key in rows and key not in traces and
                len(row["transitions"])==rows[key]["full_transition_count"],
                "V12_V11_FULL_OPTION_EPISODE_DRIFT")
        for step in row["transitions"]:
            obs,nobs,mask=step["observation"],step["next_observation"],step["mask"]
            require(len(obs)==len(nobs)==18 and
                    all(isinstance(v,(float,int)) and math.isfinite(v) for v in (*obs,*nobs)) and
                    len(mask)==7 and all(v in (0,1) for v in mask) and
                    isinstance(step["action"],int) and mask[step["action"]]==1,
                    "V12_V11_NONPUBLIC_OR_UNMASKED_OPTION")
        options+=len(row["transitions"])
        traces[key]=row["transitions"]
    require(len(traces)==800 and options==34992,"V12_V11_FULL_ORIGINAL_OPTION_COUNT_DRIFT")
    return {"run":"v11","training":training,"rows":rows,"traces":traces,
            "sourceSha":V11_SOURCE_SHA,"harnessSha":V11_HARNESS_SHA,
            "trainingSha256":V11_RAW["training.json"],
            "fullTransitionsSha256":V11_RAW["full_transitions.jsonl.gz"]}
