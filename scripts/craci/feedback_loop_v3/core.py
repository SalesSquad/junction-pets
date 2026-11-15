#!/usr/bin/env python3
"""CRACI V12 original-hosted ZIP -> deterministic, advisory TRAIN-only V13 decision.

This is *not* an experiment executor or a causal effect estimator. Its inputs
are immutable CRACI evidence and its output cannot authorize spend/promotion.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import PurePosixPath, Path
import zipfile

ARTIFACT_SHA = "f2bed411c74bd99a4a622bd3ed1853a2542313ede8acc219b9f1d57c08729311"
ARTIFACT_ID = 14139070947
RUN_ID = 43657058944
SOURCE = "78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
HARNESS = "4874d15dd68d3a809aaf7d769d6b5bef85d378bd"
MODEL = "82cfa42ba2240aff6d00ec3e2b15c06d78386d3c0682986a23e478977f2dbf9e"
PLAN = "8074f8f8978e2e55bdf201eeb9713888e44befe1d93856da44c1830bb86cfc48"
OLD_V10_RAW = "739c30a13ecacdecd404774fc9dadd887944f32df5cef14cfd2758a639460419"
ARMS = ("frozen_v5", "v12_phase_dwell_supported_actions",
        "v12_right_side_action4_exploration_train_only")
PILOT = "artifacts/rokoko-mujoco-v12-pilot/"
MAX_ZIP_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNCOMPRESSED_TOTAL = 63 * 1024 * 1024
MAX_ORIGINAL_JSONL_BYTES = 32 * 1024 * 1024
FUTURE_START = 519024  # Seeds 518512..519023 reserved for optional V12 follow-up.
FUTURE_END = 519535  # ContactEnv.reset TRAIN upper bound is below 520000.


class EvidenceRejected(ValueError):
    """Fails closed if evidence, source, physics, or split isolation disagrees."""


def need(ok: object, code: str) -> None:
    if not ok:
        raise EvidenceRejected(code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def read_json(data: bytes, code: str) -> object:
    try:
        return json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceRejected(code) from error


def safe_zip(data: bytes, *, max_members: int = 64) -> dict[str, bytes]:
    need(len(data) <= MAX_ZIP_BYTES, "ZIP_TOO_LARGE")
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            need(0 < len(infos) <= max_members, "ZIP_ENTRY_COUNT")
            members: dict[str, bytes] = {}
            claimed_total = 0
            for info in infos:
                path = PurePosixPath(info.filename)
                need(not path.is_absolute() and info.filename == path.as_posix() and
                     ".." not in path.parts and "." not in path.parts and
                     "\\" not in info.filename and not info.is_dir() and
                     not ((info.external_attr >> 16) & 0o170000) == 0o120000 and
                     info.filename not in members, "UNSAFE_OR_DUPLICATE_ZIP_MEMBER")
                need(0 <= info.file_size <= MAX_FILE_BYTES, "UNBOUNDED_ZIP_MEMBER")
                claimed_total += info.file_size
                need(claimed_total <= MAX_UNCOMPRESSED_TOTAL, "ZIP_UNCOMPRESSED_LIMIT")
                body = archive.read(info)
                need(len(body) == info.file_size, "ZIP_MEMBER_SIZE_DRIFT")
                members[info.filename] = body
            return members
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as error:
        raise EvidenceRejected("ZIP_CORRUPTED") from error


def public_mask(obs: list[float]) -> list[int]:
    """Independent 18D public shield check, double-precision with fixed margins."""
    need(len(obs) == 18 and all(type(x) in (float, int) and math.isfinite(x) for x in obs),
         "PUBLIC_18D_NONFINITE")
    allowed = [1] * 7
    if obs[15] or not obs[10] or not obs[11] or obs[8] > .1 or obs[9] < .8:
        return [0] * 6 + [1]
    ox, oy = obs[:2]
    bx, by = obs[6:8]
    dx, dy = .16 - ox, -oy
    t = max(0.0, min(1.0, ((bx-ox)*dx+(by-oy)*dy)/max(dx*dx+dy*dy, 1e-12)))
    distance = math.hypot(ox+t*dx-bx, oy+t*dy-by)
    if distance < .060:
        allowed[:5] = [0] * 5
    if math.hypot(obs[2]-ox, obs[3]-oy) < .029:
        allowed[2] = 0
    if distance < .060:
        scale = max(math.hypot(dx, dy), 1e-9)
        ux, uy = dx/scale, dy/scale
        lx, ly = -uy, ux
        for action in (0, 3, 4):
            forward = -.041 if action == 0 else -.024
            lateral = 0.0 if action == 0 else (.019 if action == 3 else -.019)
            target = (ox + forward*ux + lateral*lx,
                      oy + forward*uy + lateral*ly)
            allowed[action] = int(math.hypot(target[0]-bx, target[1]-by) > .055)
    return allowed


def read_original_hosted(archive_path: Path) -> dict:
    """Verify every byte from the original hosted artifact before parsing results."""
    data = Path(archive_path).read_bytes()
    need(sha(data) == ARTIFACT_SHA, "HOSTED_ZIP_SHA_DRIFT")
    outer = safe_zip(data)
    need("receipt.json" in outer and "manifest.json" in outer, "MISSING_HOSTED_WRAPPER")
    receipt = read_json(outer["receipt.json"], "BAD_RECEIPT_JSON")
    wrapper = read_json(outer["manifest.json"], "BAD_WRAPPER_JSON")
    need(receipt["status"] == "succeeded" and receipt["jobStatus"] == "success" and
         receipt["stageOutcome"] == "success" and receipt["command"]["exitCode"] == 0 and
         receipt["sourceVerified"] is True and receipt["harnessVerified"] is True and
         receipt["providerAttestationVerified"] is False and
         receipt["binding"]["sourceSha"] == SOURCE and
         receipt["binding"]["harnessSha"] == HARNESS and
         receipt["binding"]["repository"] == "SalesSquad/junction-pets" and
         receipt["runId"] == "craci.43657058944.1.93edebd476b31661" and
         receipt["manifest"]["sha256"] == sha(outer["manifest.json"]) and
         wrapper["complete"] is True, "HOSTED_SOURCE_OR_RECEIPT_INVALID")
    expected = set()
    for info in wrapper["files"]:
        path = info["path"]
        need(path not in expected and path in outer, "MISSING_WRAPPED_FILE")
        need(len(outer[path]) == info["bytes"] and sha(outer[path]) == info["sha256"],
             "WRAPPED_FILE_HASH_DRIFT")
        expected.add(path)
    need(set(outer) == expected | {"manifest.json", "receipt.json",
          "registry/runs/craci.43657058944.1.93edebd476b31661.json"},
         "UNEXPECTED_HOSTED_ARCHIVE_MEMBER")

    retention = read_json(outer[PILOT+"retention-manifest.json"], "BAD_RETENTION")
    manifest = read_json(outer[PILOT+"manifest.json"], "BAD_PRODUCT_MANIFEST")
    qual = read_json(outer[PILOT+"independent-qualification.json"], "BAD_QUALIFICATION")
    readout = read_json(outer[PILOT+"paired-readout.json"], "BAD_READOUT")
    old_feedback = read_json(outer["artifacts/rokoko-feedback-v2/feedback.json"], "BAD_V2_FEEDBACK")
    need(retention["status"] == "COMPLETE_TRAIN_ONLY" and
         retention["exact_source_sha"] == manifest["executed_head"] == SOURCE and
         qual["harness_head"] == HARNESS and
         manifest["model_sha256"] == qual["model_sha256"] == MODEL and
         manifest["plan_sha256"] == qual["plan_sha256"] == PLAN and
         manifest["training_only"] is qual["full_144_real_episode_physics_replay"]["training_only"] is True and
         manifest["dev_cal_test_ood_opened"] is qual["dev_cal_test_ood_opened"] is False and
         manifest["actual_trials"] == qual["actual_trials"] == 144 and
         manifest["actual_option_transitions"] == qual["actual_option_transitions"] == 4228 and
         qual["new_model_promotion_authorized"] is False and
         qual["experiment_complete"] is True and
         qual["full_144_real_episode_physics_replay"]["claim_verified"] is True and
         readout["scienceDecision"] == "STOP" and
         readout["hardStopNoFurtherPhysics"] is True and
         readout["modelPromotionAuthorized"] is False and
         old_feedback["source_runs"]["v10"]["raw_sha256"] == OLD_V10_RAW and
         old_feedback["model_promotion_authorized"] is False and
         old_feedback["job_dispatch_authorized"] is False,
         "PRODUCT_SOURCE_SPLIT_OR_V10_GUARD_DRIFT")

    originals = {}
    for original in retention["sources"]:
        chunks = []
        for part in original["parts"]:
            zip_path = PILOT + part["archive"]
            packed = outer[zip_path]
            need(len(packed) == part["archive_bytes"] and
                 sha(packed) == part["archive_sha256"], "INNER_ARCHIVE_SHA_DRIFT")
            files = safe_zip(packed, max_members=1)
            need(list(files) == [part["entry"]], "INNER_ARCHIVE_ENTRY_CHANGED")
            raw = files[part["entry"]]
            need(len(raw) == part["raw_bytes"] and sha(raw) == part["raw_sha256"],
                 "INNER_CHUNK_SHA_DRIFT")
            chunks.append(raw)
        name = original["name"]
        need(name not in originals, "DUPLICATE_ORIGINAL")
        whole = b"".join(chunks)
        need(len(whole) == original["original_bytes"] and
             sha(whole) == original["original_sha256"] == retention["original_sha256"][name] ==
             manifest["file_sha256"][name] == qual["original_sha256"][name],
             "LOSSLESS_ORIGINAL_SHA_DRIFT")
        originals[name] = whole
    need(set(originals) == {"training.json", "full_transitions.jsonl.gz"} and
         sha(outer[PILOT+"paired-readout.json"]) == manifest["file_sha256"]["paired-readout.json"],
         "ORIGINAL_SOURCE_INCOMPLETE")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(originals["full_transitions.jsonl.gz"])) as gz:
            uncompressed = gz.read(MAX_ORIGINAL_JSONL_BYTES + 1)
    except (OSError, EOFError) as error:
        raise EvidenceRejected("ORIGINAL_GZIP_CORRUPTED") from error
    need(len(uncompressed) <= MAX_ORIGINAL_JSONL_BYTES, "UNBOUNDED_ORIGINAL_GZIP")
    rows = [read_json(line, "BAD_TRANSITION_LINE") for line in uncompressed.splitlines()]
    training = read_json(originals["training.json"], "BAD_ORIGINAL_TRAINING")
    need(training["executed_head"] == SOURCE and
         training["actual_physics_engine"] == "mujoco-3.3.7" and
         training["model_sha256"] == MODEL and training["plan_sha256"] == PLAN and
         training["training_only"] is True and training["no_dev_test_ood"] is True and
         training["model_promotion_authorized"] is False and
         training["actual_trials"] == 144 and
         training["actual_option_transitions"] == 4228 and
         training["strategies"] == list(ARMS), "TRAIN_ORIGINAL_SOURCE_DRIFT")
    return {"receipt": receipt, "training": training, "transitions": rows,
            "readout": readout, "qualification": qual, "old_feedback": old_feedback,
            "original_sha256": {name: sha(contents) for name, contents in originals.items()}}


def validate_historical_safety(feedback: dict) -> None:
    """V10 historical safety evidence is a regression gate, not new V12 proof."""
    pair = feedback["paired_goal250"]
    need(feedback["source_runs"]["v10"]["raw_sha256"] == OLD_V10_RAW and
         pair["paired_worlds"] == 160 and
         pair["baseline_safe_goals"] == pair["candidate_safe_goals"] == 18 and
         pair["lost"] == pair["novel"] == pair["unsafe"] == 0 and
         feedback["verified_independent_holdout"] is False and
         feedback["sealed_splits_unopened"] is True and
         feedback["model_promotion_authorized"] is False and
         feedback["job_dispatch_authorized"] is False,
         "HISTORICAL_V10_V11_SAFETY_REGRESSION")


def verify_raw(bundle: dict) -> dict:
    """Independent original options, real paired outcomes, and provenance."""
    training = bundle["training"]
    qualification = bundle["qualification"]
    readout = bundle["readout"]
    need(training["training_only"] is True and training["no_dev_test_ood"] is True and
         training["model_promotion_authorized"] is False and
         readout["devCalTestOodOpened"] is False and
         qualification["new_model_promotion_authorized"] is False,
         "FORBIDDEN_SPLIT_OR_PROMOTION")
    validate_historical_safety(bundle["old_feedback"])
    scans = training["all_512_public_initial_scans"]
    need(len(scans) == 512 and [r["seed"] for r in scans] == list(range(518000, 518512)),
         "FRESH_TRAIN_SCAN_CHANGED")
    near, clear = [], []
    for row in scans:
        need(len(row["world_hash"]) == 64 and
             row["mask"] == public_mask(row["observation"]), "PUBLIC_SCAN_MASK_DRIFT")
        if abs(row["observation"][7]) < .122 and len(near) < 40:
            near.append(row)
        elif abs(row["observation"][7]) >= .122 and len(clear) < 8:
            clear.append(row)
    selected = sorted([*near, *clear], key=lambda r: r["seed"])
    by_seed = {r["seed"]: r for r in selected}
    cohort = training["cohort"]
    need(len(selected) == len(cohort) == 48 and
         [r["seed"] for r in cohort] == [r["seed"] for r in selected],
         "COHORT_CHANGED_OR_UNBALANCED")
    for row in cohort:
        scan = by_seed[row["seed"]]
        need(row["world_hash"] == scan["world_hash"] and
             row["initial_mask"] == scan["mask"] and
             row["observed_corridor"] == (abs(scan["observation"][7]) < .122) and
             abs(row["initial_public_obstacle_y"] - scan["observation"][7]) < 1e-8,
             "COHORT_PUBLIC_WORLD_DRIFT")

    trials: dict[tuple[int, str], dict] = {}
    for row in training["trials"]:
        key = (row["seed"], row["strategy"])
        need(key not in trials and key[0] in by_seed and key[1] in ARMS and
             row["world_hash"] == by_seed[key[0]]["world_hash"] and
             all(type(row[name]) is bool for name in ("success", "unsafe", "abstained")),
             "UNPAIRED_TRIAL_OR_WORLD_DRIFT")
        trials[key] = row
    need(len(trials) == 144 and set(trials) ==
         {(row["seed"], arm) for row in selected for arm in ARMS},
         "ACTUAL_144_PAIRED_GRID_CHANGED")

    seen: set[tuple[int, str]] = set()
    total_options = 0
    executed = Counter()
    action_worlds = defaultdict(set)
    action_episodes = defaultdict(set)
    goals = defaultdict(set)
    witnesses = defaultdict(list)
    minimum_failed_candidate_distance = float("inf")
    for record in bundle["transitions"]:
        key = (record["seed"], record["strategy"])
        need(key in trials and key not in seen, "UNEXPECTED_OR_DUPLICATED_TRACE")
        seen.add(key)
        row = trials[key]
        events = record["transitions"]
        n = len(events)
        sparse = sorted(set(range(min(12, n))) | set(range(max(0, n-8), n)) |
                        set(range(0, n, 5)))
        need(1 <= n <= 60 and row["full_transition_count"] == row["option_steps"] == n and
             row["full_transition_sha256"] == sha(canonical(events)) and
             row["sparse_transition_indices"] == sparse and
             row["transitions"] == [events[i] for i in sparse],
             "FULL_OPTION_OR_SPARSE_SHA_MISMATCH")
        prev_contacts, prev_dwell = 0, 0
        for index, event in enumerate(events):
            obs, nxt = event["observation"], event["next_observation"]
            action = event["action"]
            need(len(obs) == len(nxt) == 18 and
                 type(action) is int and 0 <= action <= 6 and
                 event["mask"] == public_mask(obs) and event["mask"][action] == 1 and
                 type(event["cost"]) is int and event["cost"] in (0, 1) and
                 type(event["success_info"]) is bool and
                 event["done"] is (index == n-1) and
                 type(event["contacts_cumulative"]) is int and
                 event["contacts_cumulative"] >= prev_contacts and
                 type(event["dwell_ticks_cumulative"]) is int and
                 event["dwell_ticks_cumulative"] >= prev_dwell,
                 "PHYSICAL_OPTION_MASK_CONTACT_DWELL_CHANGED")
            if index:
                need(all(abs(a-b) < 1e-5 for a,b in
                         zip(events[index-1]["next_observation"], obs)),
                     "PUBLIC_OBSERVATION_CHAIN_BROKEN")
            prev_contacts = event["contacts_cumulative"]
            prev_dwell = event["dwell_ticks_cumulative"]
            executed[action] += 1
            action_worlds[action].add(record["seed"])
            action_episodes[action].add(key)
            total_options += 1

            observed = {"seed": record["seed"], "world_hash": row["world_hash"],
                        "strategy": record["strategy"], "option": index+1,
                        "action": action, "mask_legal": event["mask"][action],
                        "before_object_xy": obs[:2], "after_object_xy": nxt[:2],
                        "transition_sha256": sha(canonical(event))}
            if record["strategy"] == ARMS[1] and not row["success"]:
                distance = math.hypot(nxt[0]-nxt[16], nxt[1]-nxt[17])
                minimum_failed_candidate_distance = min(minimum_failed_candidate_distance, distance)
                if (index >= 17 and obs[10] == 0 and action == 6 and
                        not any(w["seed"] == record["seed"] for w in witnesses["post_option17_live_false_release"])):
                    witnesses["post_option17_live_false_release"].append({**observed,
                        "observed_live_flag": obs[10], "dwell_ticks": event["dwell_ticks_cumulative"]})
                if (row["abstained"] and index == n-1 and index < 20 and
                        obs[10] != 0 and action == 6):
                    witnesses["early_abstain_with_live_true"].append({**observed,
                        "observed_live_flag": obs[10], "contacts": event["contacts_cumulative"]})
            if record["strategy"] == ARMS[2] and action == 4:
                witnesses["real_right4_exploration"].append({**observed,
                    "observed_live_flag": obs[10]})

        last = events[-1]
        need(row["success"] is last["success_info"] and
             row["contacts"] == last["contacts_cumulative"] and
             row["dwell_ticks_final"] == last["dwell_ticks_current"] and
             row["unsafe"] is any(e["cost"] for e in events) and
             abs(row["total_reward"] - sum(e["reward"] for e in events)) < 1e-4,
             "TERMINAL_GOAL_SAFETY_OR_REWARD_CHANGED")
        if row["success"] and not row["unsafe"] and not row["abstained"]:
            distance = math.hypot(last["next_observation"][0]-last["next_observation"][16],
                                  last["next_observation"][1]-last["next_observation"][17])
            need(last["dwell_ticks_cumulative"] >= 250 and
                 last["contacts_cumulative"] > 0 and distance < .025 and
                 last["action"] != 6 and row["physics_steps"] > 0,
                 "FAKE_GOAL250_WITHOUT_REAL_CONTACT_DWELL")
            goals[record["strategy"]].add(record["seed"])

    need(seen == set(trials) and total_options == 4228 and
         total_options == qualification["full_144_real_episode_physics_replay"]["exact_real_full_options_replayed"] and
         executed[4] == 31 == qualification["full_144_real_episode_physics_replay"]["untrained_right4_actual_legal_executions"] and
         len(action_worlds[4]) == len(action_episodes[4]) == 31,
         "REAL_OPTION_COUNT_OR_ACTION4_SUPPORT_DRIFT")
    baseline, candidate, exploration = (goals[arm] for arm in ARMS)
    lost = sorted(baseline-candidate)
    novel = sorted(candidate-baseline)
    unsafe = sorted(seed for (seed,arm),row in trials.items()
                    if arm == ARMS[1] and row["unsafe"])
    exploratory_unsafe = sorted(seed for (seed,arm),row in trials.items()
                                if arm == ARMS[2] and row["unsafe"])
    need(len(baseline) == len(candidate) == len(exploration) == 12 and
         len(novel) == len(lost) == len(unsafe) == len(exploratory_unsafe) == 0 and
         baseline == candidate == exploration and
         len(baseline) == readout["frozenV5SafeGoals"] and
         len(candidate) == readout["candidateSafeGoals"] and
         novel == readout["candidateNovelSafeGoalWorldSeeds"] and
         lost == readout["candidateLostV5GoalWorldSeeds"] and
         unsafe == readout["candidateUnsafeWorldSeeds"] and
         exploratory_unsafe == readout["explorationOnlyUnsafeWorldSeeds"] and
         readout["scienceDecision"] == "STOP" and
         readout["devCalTestOodOpened"] is False and
         readout["independentPhysicsReplayQualified"] is False,
         "STOP_GOAL250_OR_SAFETY_REGRESSION")

    # Near-vs-clear is a *public initial observation* tag, not a sealed split.
    near_goal = len([seed for seed in baseline if abs(by_seed[seed]["observation"][7]) < .122])
    clear_goal = len(baseline)-near_goal
    need(near_goal == 5 and clear_goal == 7 and
         qualification["full_144_real_episode_physics_replay"]["real_safe_near_goal_trajectories_replayed"] == 15 and
         qualification["full_144_real_episode_physics_replay"]["real_safe_clear_goal_trajectories_replayed"] == 21,
         "OBSERVED_NEAR_CLEAR_GOAL_DRIFT")

    # Choose one original failure witness per failure class to avoid false
    # independent samples: these are observation-tied hypotheses, not effects.
    for seed in sorted(by_seed):
        row = trials[(seed, ARMS[1])]
        if row["observed_corridor"] and not row["success"]:
            witness = {"seed":seed,"world_hash":row["world_hash"],"strategy":ARMS[1],
                       "option":row["option_steps"],"action":row["transitions"][-1]["action"],
                       "mask_legal":row["transitions"][-1]["mask"][row["transitions"][-1]["action"]],
                       "transition_sha256":sha(canonical(row["transitions"][-1])),
                       "observed_corridor":True,"contacts":row["contacts"],
                       "dwell_ticks_final":row["dwell_ticks_final"]}
            witnesses["near_corridor_without_goal_dwell"].append(witness)
    # Full-stream options must be used when validating witness hashes. Sparse
    # stage-funnel rows above merely locate the original-world failure class.
    return {
        "fresh_train_scans":len(scans),"near_worlds":len(near),"clear_worlds":len(clear),
        "paired_worlds":len(by_seed),"real_episodes":len(trials),"full_real_options":total_options,
        "baseline_goal250":len(baseline),"candidate_goal250":len(candidate),
        "exploration_goal250":len(exploration),"goal_worlds":sorted(baseline),
        "candidate_novel":novel,"candidate_lost":lost,"candidate_unsafe":unsafe,
        "exploration_unsafe":exploratory_unsafe,"near_goal_worlds":near_goal,
        "clear_goal_worlds":clear_goal,"right4_executed":executed[4],
        "right4_distinct_worlds":len(action_worlds[4]),
        "right4_world_ids":sorted(action_worlds[4]),
        "executed_options_per_action":[executed[i] for i in range(7)],
        "candidate_failed_min_object_goal_distance_m":round(minimum_failed_candidate_distance,6),
        "candidate_early_abstained_worlds":sum(trials[(seed,ARMS[1])]["abstained"] for seed in by_seed),
        "witnesses":{name:sorted(values,key=lambda v:(v["seed"],v["option"]))[:6]
                     for name,values in sorted(witnesses.items())},
    }


def compile_decision(bundle: dict) -> dict:
    findings = verify_raw(bundle)
    need(FUTURE_START == 519024 and FUTURE_END == 519535 and FUTURE_END < 520000 and
         FUTURE_END - FUTURE_START + 1 == 512, "FUTURE_TRAIN_SEED_RANGE_INVALID")
    witness = findings["witnesses"]
    hypothesis = [
        ("pre_release_reachability", "Test shield-legal actions *before* the observed post-option17 live flag drop; a live=False observation is a failure symptom, not a proven cause.",
         "post_option17_live_false_release"),
        ("early_abstain_recovery", "Prospectively branch the last shield-legal physical alternatives before observed early abstain with live=True; a legal mask alone does not imply a safe positive reward.",
         "early_abstain_with_live_true"),
        ("right4_counterfactual_reachability", "Test actual action4 rightward transitions on new TRAIN worlds where the public mask permits them; prior 31 executions prove support, not gain.",
         "real_right4_exploration"),
        ("near_corridor_contact_lateral_reopen_dwell", "Compare contact, lateral clearance, forward reopen and sustained 250-tick goal dwell on blocked near corridors without proxy-goal credit.",
         "near_corridor_without_goal_dwell"),
    ]
    ranked = []
    for rank,(key,prediction,group) in enumerate(hypothesis,1):
        evidence = witness.get(group, [])
        need(len(evidence) > 0,"MISSING_CAUSAL_WITNESS_"+key)
        ranked.append({"rank":rank,"id":key,"type":"falsifiable_observational_hypothesis",
                       "hypothesis":prediction,"witness_class":group,
                       "observed_train_witnesses":evidence[:3],
                       "counterfactual_effect_observed":False,
                       "requires_new_real_physics_intervention":True})
    return {
        "schema":"junction.craci.v13.feedback-source-bound-decision.v1",
        "work_id":"CRACI-FEEDBACK-LEARNING-V3-20261115",
        "decision":"SCIENCE_STOP_NO_PROMOTION",
        "science":{"status":"STOP","reason":"ZERO_NOVEL_SAFE_PHYSICAL_GOAL250",
                   "baseline_goal250":findings["baseline_goal250"],
                   "candidate_goal250":findings["candidate_goal250"],
                   "exploratory_right4_goal250":findings["exploration_goal250"],
                   "novel":findings["candidate_novel"],"lost":findings["candidate_lost"],
                   "unsafe":findings["candidate_unsafe"]},
        "evidence":{
            "hosted_run_id":RUN_ID,"hosted_artifact_id":ARTIFACT_ID,
            "hosted_artifact_zip_sha256":ARTIFACT_SHA,
            "source_sha":SOURCE,"harness_sha":HARNESS,
            "model_sha256":MODEL,"plan_sha256":PLAN,
            "original_raw_sha256":bundle["original_sha256"],
            "run_id":bundle["receipt"]["runId"],
            "actual_physics":"MuJoCo 3.3.7, original train-only, no rerun",
            "actual_episodes":findings["real_episodes"],
            "actual_options":findings["full_real_options"],
            "paired_worlds":findings["paired_worlds"],
            "near_goal_worlds":findings["near_goal_worlds"],
            "clear_goal_worlds":findings["clear_goal_worlds"],
            "right4_legal_actual_executions":findings["right4_executed"],
            "right4_distinct_worlds":findings["right4_distinct_worlds"],
            "right4_world_ids":findings["right4_world_ids"],
            "candidate_early_abstained_worlds":findings["candidate_early_abstained_worlds"],
            "candidate_failed_min_goal_distance_m":findings["candidate_failed_min_object_goal_distance_m"],
            "no_dev_cal_test_ood_opened":True,
            "signed_provider_attestation":False,
            "actual_spend_eur":None,
            "github_artifact_expires_at_utc":"unknown_not_independently_verified",
        },
        "next_training_decision":{
            "type":"ADVISORY_V13_COUNTERFACTUAL_REACHABILITY_WITNESS_PLAN",
            "ranked_hypotheses":ranked,
            "frozen_new_train_cohort":{
                "first_seed":FUTURE_START,"last_seed_inclusive":FUTURE_END,
                "scan_worlds":512,"first_public_near":128,"first_public_clear":32,
                "chosen_distinct_worlds":160,
                "selection":"first_by_seed_with_abs_public_initial_obstacle_y_lt_0.122_for_near",
                "reserved_earlier_train_seeds":"518000..519023",
                "forbidden_seeds":"seed>=520000 and DEV/CAL/TEST/OOD",
                "original_contact_env_guard_unchanged":True,
            },
            "prospective_arena":{"arms":["frozen_v5","v13_unpromoted_counterfactual_witness"],
                                 "paired_real_episodes_if_approved":320,
                                 "frozen_before_new_world_open":True},
            "acceptance_requirements":[
                "independent original MuJoCo physics, not mask-legal pseudo-outcomes",
                "zero unsafe, zero lost frozen V5 true contact+dwell250 goal worlds",
                "at least one novel shield-legal physical goal250 near world, otherwise STOP",
                "paired initial public worlds with per-step immutable world/action/transition SHA",
                "report pre-release reachability and right4 support without post-selected fixed 95% CI",
                "no DEV/CAL/TEST/OOD, no changed original safety masks or contact physics",
                "independent source review and explicit fresh credit/budget admission required",
            ],
            "pre_admission_hard_stop_utc":"2026-11-15T17:00:00Z",
            "no_dispatch_authorization":True,
            "model_promotion_authorized":False,
            "source_only_no_paid_run":True,
        },
        "limitations":[
            "Observational traces do not establish causal effect of proposed action changes",
            "V12 original train-only worlds are not independent DEV/CAL/TEST/OOD holdout evidence",
            "V10/V11 historical guard is source-reported in V2 feedback, not revalidated raw in V3",
            "GitHub collector receipt is source-reported, not signed CRACI provider billing/provenance",
            "No fresh 519024+ physics was executed, no model trained or deployed",
        ],
        "dispatch_authorized":False,
        "model_promotion_authorized":False,
        "provider_billed_eur":None,
    }
