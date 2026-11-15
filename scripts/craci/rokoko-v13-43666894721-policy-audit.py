#!/usr/bin/env python3
"""Verify one retained V13 artifact and replay policy decisions, not physics."""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

import numpy as np

ARCHIVE_SHA = "45ff6ba157771a2a56c6139ec124a30f0fc0f26674fe97f00dd5d4c996e404e2"
SOURCE_SHA = "faec266d6d3a44af3a564f46e0778209c1dc3af1"
HARNESS_SHA = "5ce3ac346c1ad7c399bf84e2cd678fba041d9fd0"
HARNESS_FILES = {
    "rokoko-mujoco-v13-original-qualification.py": "2244cb268427c10824c72838f233a789128da11d6f008ba69b656d44247b22fe",
    "rokoko-mujoco-v13-original-retain-evidence.py": "0982f41c30d385c77709520910b5982fb9c8e4ee86b1b46049d1bc6bcb46d563",
    "rokoko-mujoco-v7-feasibility-qualification.py": "41737892c3a0c3dda165d3ec230015d8ac168ba6eb03bf2bc94495d0a412568d",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "AUDIT_SOURCE_MISSING")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "harness", "source", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    archive = Path(args.archive).resolve(strict=True)
    root = Path(args.harness).resolve(strict=True)
    source = Path(args.source).resolve(strict=True)
    output = Path(args.output)
    require(np.__version__ == "2.3.4", "AUDIT_NUMPY_VERSION_MISMATCH")
    require(sha(archive) == ARCHIVE_SHA, "AUDIT_OUTER_ARCHIVE_SHA_MISMATCH")
    for name, expected in HARNESS_FILES.items():
        require(sha(root / "scripts/craci" / name) == expected, "AUDIT_HARNESS_FILE_SHA_MISMATCH")

    h = load(root / "scripts/craci/rokoko-mujoco-v13-original-qualification.py", "v13_archive_h")
    packer = load(root / "scripts/craci/rokoko-mujoco-v13-original-retain-evidence.py", "v13_archive_p")
    v7 = load(root / "scripts/craci/rokoko-mujoco-v7-feasibility-qualification.py", "v13_archive_v7")
    h.git_head_clean(source, SOURCE_SHA, product=True)
    policy = h.load_module(source / h.PRODUCT / "policy.py", "v13_audit_original_policy")
    protocol = h.load_module(source / h.PRODUCT / "protocol.py", "v13_audit_original_protocol")
    plan = protocol.load_plan(source / h.PRODUCT / "v13-plan.json")
    survey = h.verify_preflight(source / h.PRODUCT / "v13-world-survey.json")
    h.PLAN_SHA = h.REVIEWED_PLAN_SHA

    temp_root = "/private/tmp" if Path("/private/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="v13-original-audit-", dir=temp_root) as temp:
        temp = Path(temp)
        extracted = temp / "artifact"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as outer:
            entries = outer.infolist()
            require(len(entries) <= 128 and len({i.filename for i in entries}) == len(entries),
                    "AUDIT_OUTER_ARCHIVE_DUPLICATE_OR_OVERSIZED")
            for info in entries:
                name = PurePosixPath(info.filename)
                require(not name.is_absolute() and ".." not in name.parts and
                        not stat.S_ISLNK(info.external_attr >> 16) and info.file_size < 20 * 1024 * 1024,
                        "AUDIT_UNSAFE_ARCHIVE_ENTRY")
            outer.extractall(extracted)

        outer_manifest = json.loads((extracted / "manifest.json").read_text())
        require(outer_manifest["complete"] is True and not outer_manifest["rejected"],
                "AUDIT_OUTER_MANIFEST_INCOMPLETE")
        for item in outer_manifest["files"]:
            path = extracted / item["path"]
            require(path.stat().st_size == item["bytes"] and sha(path) == item["sha256"],
                    "AUDIT_OUTER_MANIFEST_FILE_MISMATCH")
        receipt = json.loads((extracted / "receipt.json").read_text())
        require(receipt["status"] == "failed" and receipt["stageOutcome"] == "failure" and
                receipt["binding"]["sourceSha"] == SOURCE_SHA and
                receipt["binding"]["harnessSha"] == HARNESS_SHA,
                "AUDIT_WRONG_RUN_OR_RECEIPT_STATUS")

        collector = extracted / "artifacts/rokoko-mujoco-v13-original"
        retention = json.loads((collector / "retention-manifest.json").read_text())
        require(retention["status"] == "COMPLETE_TRAIN_ONLY" and
                retention["exact_source_sha"] == SOURCE_SHA, "AUDIT_RETENTION_STATUS_MISMATCH")
        packer.verify_reassembled(collector, retention)
        private = temp / "private"
        private.mkdir()
        for item in retention["sources"]:
            target = private / item["name"]
            with target.open("xb") as dest:
                for part in item["parts"]:
                    with zipfile.ZipFile(collector / part["archive"]) as archive_part:
                        dest.write(archive_part.read(part["entry"]))
            require(sha(target) == item["original_sha256"] == retention["original_sha256"][item["name"]],
                    "AUDIT_REASSEMBLED_SOURCE_MISMATCH")
        for name in ("manifest.json", "paired-readout.json", "independent-qualification.json"):
            shutil.copyfile(collector / name, private / name)

        training, original_manifest, readout, rows = h.verify_full_originals(
            private, SOURCE_SHA, protocol, plan, v7, survey)
        packer.validate_original_rows(training, training["trials"], private)
        qualification = json.loads((private / "independent-qualification.json").read_text())
        hosted_replay = qualification["full_192_real_episode_physics_replay"]
        require(qualification["actual_trials"] == 192 and
                hosted_replay["exact_real_full_options_replayed"] == training["actual_option_transitions"] == 4798 and
                qualification["new_model_promotion_authorized"] is False,
                "AUDIT_HOSTED_REPLAY_RECEIPT_MISMATCH")

        staged = h.stage_frozen_models(source, temp / "frozen")
        factories, _, _, _, _ = h.original_factories(source, staged, policy)
        seen, instances = set(), []
        counts, goals, near, unsafe = (collections.Counter(), collections.defaultdict(list),
                                       collections.Counter(), collections.Counter())
        options = 0
        with gzip.open(private / "full_transitions.jsonl.gz", "rt", encoding="utf8") as stream:
            for line in stream:
                doc = json.loads(line)
                key = (doc["seed"], doc["strategy"])
                require(key in rows and key not in seen, "AUDIT_DUPLICATE_OR_UNKNOWN_EPISODE")
                seen.add(key)
                row, trace = rows[key], doc["transitions"]
                controller = factories[doc["strategy"]]()
                for transition in trace:
                    action = controller(np.asarray(transition["observation"], dtype=np.float32),
                                        np.asarray(transition["mask"], dtype=int))
                    require(type(action) is int and action == transition["action"] and
                            transition["mask"][action] == 1, "AUDIT_POLICY_ACTION_MISMATCH")
                    options += 1
                if doc["strategy"] in h.ARMS[2:]:
                    modes = controller.mode_history
                    require(modes == row["source_policy_mode_history"], "AUDIT_POLICY_MODE_MISMATCH")
                    instances.extend(h.source_bound_burst_right4_instances(doc["seed"], doc["strategy"], trace, modes))
                counts[doc["strategy"]] += 1
                unsafe[doc["strategy"]] += int(row["unsafe"])
                if h.safe_goal(row):
                    goals[doc["strategy"]].append(doc["seed"])
                    near[doc["strategy"]] += int(row["observed_corridor"])

        require(len(seen) == 192 and options == 4798 and
                instances == training["observed_exploration_action4_instances"] ==
                hosted_replay["untrained_right4_actual_legal_instances"] and len(instances) == 149,
                "AUDIT_OPTION_OR_BURST_INSTANCE_MISMATCH")
        require(h.independent_science_gate(rows, instances) == qualification["science_gate"] and
                all(counts[arm] == 48 and unsafe[arm] == 0 for arm in h.ARMS) and
                all(sorted(goals[arm]) == sorted(goals[h.ARMS[0]]) for arm in h.ARMS),
                "AUDIT_PAIRED_GOAL_OR_SAFETY_MISMATCH")
        result = {
            "run": 43666894721, "artifact_sha256": sha(archive),
            "source_sha": SOURCE_SHA, "harness_sha": HARNESS_SHA,
            "original_sha256": original_manifest["file_sha256"],
            "episodes": len(seen), "options": options,
            "safe_goals": {arm: len(goals[arm]) for arm in h.ARMS},
            "safe_near_goals": {arm: near[arm] for arm in h.ARMS},
            "unsafe": {arm: unsafe[arm] for arm in h.ARMS},
            "novel_goals": readout["novelSafeGoalsByStrategy"],
            "active_burst_right4": len(instances),
            "burst_right4_by_arm": dict(collections.Counter(x["strategy"] for x in instances)),
            "science_gate": qualification["science_gate"], "workflow_status": receipt["status"],
            "source_verified": receipt["sourceVerified"], "harness_verified": receipt["harnessVerified"],
            "hosted_full_physics_replay_reported": True, "offhost_policy_replay_checked": True,
            "offhost_physics_replay_performed": False,
            "provider_attestation_verified": receipt["providerAttestationVerified"],
            "actual_billing": receipt["cost"]["actual"], "model_promotion_authorized": False,
        }
        with output.open("x", encoding="utf8") as stream:
            json.dump(result, stream, sort_keys=True, indent=2)
            stream.write("\n")
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
