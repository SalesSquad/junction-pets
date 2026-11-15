"""V13 retained original-MuJoCo evidence -> cautious V14 TRAIN-only proposal.

No scheduler, network, credentials, new physics or model promotion. A failed
V13 diagnostic yields a source-bound STOP and safety counterexample, never a
partial training dataset. A complete diagnostic is still *seen TRAIN*, not an
independent efficacy evaluation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import tempfile
import zipfile

WORK_ID = "CRACI-V13-TO-V14-LEARNING-20261115"
SCHEMA = "junction.craci.v14.evidence-adaptive-learning.v1"
ORIGINAL_V13_PRODUCT = "0751d78b93855bf70820b03b0a543e123d218baf"
ORIGINAL_V12_PRODUCT = "78f1b9de566dedf9ba3800ebee60fffa8ed0cc4f"
ORIGINAL_V12_FULL_SHA = "7e8d7c80cb8d035d904338e1a544662181a93933cc5c324458f7195c56f90b91"
V13_PREREGISTERED_PROSPECTIVE_PLAN_SHA = "2b2b617bbd08b41052ccea5d2e8efe4c40007a17b32b3c3e8e238ca749bd5a53"
V13_PREREGISTERED_FRESH_ALL512_SHA = "2ef554fa4c828332d83671c49ea2c014829d85ccad9bb30bb6699cdd35d00478"
V13_PACKER_BLOB = "661161cd15e3be8d20dcf2ed40a1700b2075322d"
V3_MASK_BLOB = "826dd74ca9c6651238912b58cde65a7ac1647c3c"
V12_INDEX_SHA = "24460b2ed49635b33db66233dd854f84593e6f65484cde229ee17ec483dd0245"
V13_COLLECTOR = "artifacts/rokoko-mujoco-v13-causal/"
PACKER_PATH = "scripts/craci/rokoko-mujoco-v13-retain-evidence.py"
PUBLIC_MASK_PATH = "scripts/craci/feedback_loop_v3/core.py"
V12_INDEX_PATH = "docs/craci/learning/rokoko-mujoco-v12-43657058944/trajectory-sha256.json"
KNOWN_UNSAFE_ARTIFACT_SHA = "cbbd78d255121102c39708ee2771f88c962e33e831ebce2b2c1c5d58769495b0"
HASH40 = re.compile(r"^[0-9a-f]{40}$")
HASH64 = re.compile(r"^[0-9a-f]{64}$")
MAX_OUTER_BYTES = 64 * 1024 * 1024
MAX_RAW_BYTES = 63 * 1024 * 1024
MAX_LINE = 2 * 1024 * 1024
MAX_OPTIONS = 60
MAX_BRANCHES = 720
MAX_EVENTS = MAX_BRANCHES * MAX_OPTIONS
MAX_GZIP_EXPANDED = 256 * 1024 * 1024
PRACTICAL_PROGRESS_METERS = .001


class EvidenceRejected(ValueError):
    """Source provenance or scientific claim failed; never emit GO."""


def need(condition, code):
    if not condition:
        raise EvidenceRejected(code)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha_obj(obj):
    return digest(canonical(obj))


def checked_json(raw, code):
    try:
        return json.loads(raw.decode("utf8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceRejected(code) from exc


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def trusted_module(repo_root, relative_path, expected_blob, label):
    path = Path(repo_root) / relative_path
    need(path.is_file() and not path.is_symlink(), "V14_PINNED_REPO_SOURCE_NOT_REGULAR")
    need(git_blob(path.read_bytes()) == expected_blob,
         "V14_PINNED_V13_RETAINER_OR_MASK_SOURCE_BLOB_DRIFT")
    spec = importlib.util.spec_from_file_location(label, path)
    need(spec is not None and spec.loader is not None, "V14_SOURCE_IMPORT_INVALID")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def original_index(repo_root, index_path=None):
    # A detached harness checkout may stage this already SHA-audited public
    # index at an external read-only path. The SHA is frozen either way.
    path = Path(index_path) if index_path is not None else Path(repo_root) / V12_INDEX_PATH
    need(path.is_file() and not path.is_symlink() and path.stat().st_size < 128*1024 and
         digest(path.read_bytes()) == V12_INDEX_SHA,
         "V14_ORIGINAL_V12_48_WORLD_HASH_INDEX_MISSING_OR_DRIFT")
    index = checked_json(path.read_bytes(), "V14_BAD_V12_HASH_INDEX")
    need(index["executed_product_head"] == ORIGINAL_V12_PRODUCT and
         index["hosted_run"] == 43657058944 and
         index["train_only"] is True and len(index["worlds"]) == 48 and
         len(index["trajectories"]) == 144,
         "V14_V12_INDEX_SOURCE_OR_COHORT_UNQUALIFIED")
    worlds = {w["seed"]: w["world_hash"] for w in index["worlds"]}
    need(len(worlds) == 48 and len(set(worlds.values())) == 48 and
         all(type(s) is int and 518000 <= s < 518512 and
             type(h) is str and HASH64.fullmatch(h) for s,h in worlds.items()),
         "V14_V12_ORIGINAL_WORLD_HASH_SET_INVALID")
    return worlds


def _unzip_bounded(raw, safe_zip):
    need(len(raw) <= MAX_OUTER_BYTES, "V14_OUTER_HOSTED_ZIP_TOO_LARGE")
    try:
        return safe_zip(raw)
    except Exception as exc:
        raise EvidenceRejected("V14_OUTER_HOSTED_ZIP_INVALID_OR_UNBOUNDED") from exc


def _receipt_guard(outer, expected_harness_sha, expected_run, status):
    need("receipt.json" in outer and "manifest.json" in outer,
         "V14_HOSTED_WRAPPER_AND_RECEIPT_MISSING")
    receipt = checked_json(outer["receipt.json"], "V14_BAD_HOSTED_RECEIPT")
    wrapper = checked_json(outer["manifest.json"], "V14_BAD_HOSTED_WRAPPER")
    binding = receipt.get("binding", {})
    need(receipt.get("sourceVerified") is True and
         receipt.get("harnessVerified") is True and
         binding.get("sourceSha") == ORIGINAL_V13_PRODUCT and
         binding.get("harnessSha") == expected_harness_sha and
         binding.get("repository") == "SalesSquad/junction-pets" and
         binding.get("workload") == "rokoko-mujoco-v13-causal" and
         receipt.get("runId", "").startswith(f"craci.{expected_run}.") and
         receipt.get("command", {}).get("binding") == binding,
         "V14_UNBOUND_HOSTED_RUN_OR_SOURCE_REPORTED_RECEIPT")
    if status == "COMPLETE_TRAIN_DIAGNOSTIC_ONLY":
        need(receipt.get("status") == "succeeded" and
             receipt.get("jobStatus") == "success" and
             receipt.get("command", {}).get("exitCode") == 0,
             "V14_COMPLETE_WITHOUT_SUCCESSFUL_SOURCE_BOUND_HOSTED_RUN")
    else:
        need(status == "INCOMPLETE_STOP" and
             receipt.get("command", {}).get("exitCode") != 0,
             "V14_FALSE_INCOMPLETE_OR_HOSTED_EXIT_NOT_STOPPED")
    if "manifest" in receipt and "sha256" in receipt["manifest"]:
        need(receipt["manifest"]["sha256"] == digest(outer["manifest.json"]),
             "V14_HOSTED_WRAPPER_MANIFEST_SHA_DRIFT")
    listed = wrapper.get("files", [])
    need(type(listed) is list and len(listed) > 0, "V14_HOSTED_MANIFEST_FILE_SET_MISSING")
    expected = set()
    for item in listed:
        name = item["path"]
        need(name not in expected and name in outer and
             len(outer[name]) == item["bytes"] and
             digest(outer[name]) == item["sha256"],
             "V14_HOSTED_WRAPPER_CONTENT_HASH_MISMATCH")
        expected.add(name)
    registry = f"registry/runs/{receipt['runId']}.json"
    need(set(outer) == expected | {"receipt.json", "manifest.json", registry},
         "V14_UNEXPECTED_OR_OMITTED_HOSTED_WRAPPER_MEMBER")
    return receipt


def _reconstruct(outer, retention, private, complete):
    sources = ("training.json", "full_transitions.jsonl.gz", "option_journal.jsonl.gz") if complete \
       else ("partial_training.json", "full_transitions.jsonl.gz", "option_journal.jsonl.gz")
    proof_names = ("manifest.json", "diagnostic-readout.json", "independent-qualification.json") \
       if complete else ("early_stop.json",)
    need(set(retention["proof_sha256"]) == set(proof_names) and
         {s["name"] for s in retention["sources"]} == set(sources) and
         len(retention["sources"]) == 3,
         "V14_RETENTION_PROOF_SOURCE_SET_CHANGED")
    for name in proof_names:
        data = outer[V13_COLLECTOR+name]
        need(digest(data) == retention["proof_sha256"][name],
             "V14_HOSTED_RETENTION_PROOF_SHA_DRIFT")
        (private/name).write_bytes(data)
    for source in retention["sources"]:
        name = source["name"]
        parts = source["parts"]
        need(0 < len(parts) <= 64, "V14_UNBOUNDED_ORIGINAL_PART_COUNT")
        assembled = bytearray()
        for part in parts:
            archive = part["archive"]
            need(type(archive) is str and Path(archive).name == archive and
                 archive.endswith(".zip"), "V14_RETENTION_PART_TRAVERSAL")
            raw = outer[V13_COLLECTOR+archive]
            need(len(raw) == part["archive_bytes"] and
                 digest(raw) == part["archive_sha256"] and
                 len(raw) < 20*1024*1024,
                 "V14_PRIVATE_PART_ZIP_SHA_OR_SIZE_CHANGED")
            with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
                need(zipped.namelist() == [part["entry"]] and
                     zipped.infolist()[0].file_size <= 6*1024*1024,
                     "V14_PRIVATE_PART_UNEXPECTED_MEMBERS")
                chunk = zipped.read(part["entry"])
            need(len(chunk) == part["raw_bytes"] and
                 len(chunk) <= 6*1024*1024 and digest(chunk) == part["raw_sha256"],
                 "V14_PRIVATE_PART_RAW_SHA_OR_SIZE_CHANGED")
            assembled.extend(chunk)
            need(len(assembled) <= MAX_RAW_BYTES, "V14_PRIVATE_RAW_TOTAL_OVERFLOW")
        need(len(assembled) == source["original_bytes"] and
             digest(assembled) == source["original_sha256"] ==
             retention["original_sha256"][name],
             "V14_PRIVATE_REASSEMBLED_ORIGINAL_SHA_DRIFT")
        (private/name).write_bytes(assembled)
    return sources


def _jsonl_gzip(raw, max_rows, label):
    import gzip
    need(len(raw) <= MAX_RAW_BYTES, "V14_GZIP_UNBOUNDED_RAW")
    rows = []
    total = 0
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        while line := stream.readline(MAX_LINE+1):
            total += len(line)
            need(len(line) <= MAX_LINE and len(rows) < max_rows,
                 "V14_"+label+"_UNBOUNDED_LINE_OR_RECORDS")
            need(total <= MAX_GZIP_EXPANDED,"V14_"+label+"_EXPANDED_GZIP_LIMIT")
            rows.append(checked_json(line,"V14_"+label+"_NOT_JSON"))
    return rows


def load_verified_hosted(zip_path, expected_zip_sha, expected_harness_sha,
                         expected_run, repo_root, index_path=None):
    """Verify source-reported hosted wrapper, V13 unchanged original packer.

    The externally provided ZIP SHA + complete original retained SHA evidence
    are mandatory. This cannot make a signed provider billing claim.
    """
    need(type(expected_zip_sha) is str and HASH64.fullmatch(expected_zip_sha) and
         type(expected_harness_sha) is str and HASH40.fullmatch(expected_harness_sha) and
         type(expected_run) is int and expected_run > 0,
         "V14_EXTERNAL_IMMUTABLE_RUN_SHA_PINS_REQUIRED")
    archive = Path(zip_path)
    need(archive.is_file() and not archive.is_symlink() and
         0 < archive.stat().st_size <= MAX_OUTER_BYTES,
         "V14_HOSTED_ARTIFACT_MISSING_OR_UNSAFE")
    raw = archive.read_bytes()
    need(digest(raw) == expected_zip_sha, "V14_HOSTED_ARTIFACT_SHA_MISMATCH")
    packer = trusted_module(repo_root, PACKER_PATH, V13_PACKER_BLOB,
                            "v14_pinned_v13_lossless_retainer")
    v3 = trusted_module(repo_root, PUBLIC_MASK_PATH, V3_MASK_BLOB,
                        "v14_pinned_independent_public_mask")
    worlds = original_index(repo_root,index_path)
    outer = _unzip_bounded(raw,v3.safe_zip)
    need(V13_COLLECTOR+"retention-manifest.json" in outer,
         "V14_RETENTION_SOURCE_MISSING")
    retention = checked_json(outer[V13_COLLECTOR+"retention-manifest.json"],
                             "V14_RETENTION_MANIFEST_INVALID")
    status = retention.get("status")
    need(status in ("COMPLETE_TRAIN_DIAGNOSTIC_ONLY","INCOMPLETE_STOP") and
         retention.get("schema") == packer.SCHEMA and
         retention.get("exact_source_sha") == ORIGINAL_V13_PRODUCT,
         "V14_V13_RETAINED_SOURCE_STATUS_OR_SHA_CHANGED")
    receipt = _receipt_guard(outer,expected_harness_sha,expected_run,status)
    with tempfile.TemporaryDirectory(prefix="craci-v14-verify-") as temp:
        collector = Path(temp)/"collector"
        collector.mkdir()
        for name,data in outer.items():
            if name.startswith(V13_COLLECTOR):
                leaf = name[len(V13_COLLECTOR):]
                need(leaf and Path(leaf).name == leaf,
                     "V14_PRIVATE_COLLECTOR_UNEXPECTED_NESTED_MEMBER")
                (collector/leaf).write_bytes(data)
        packer.verify_reassembled(collector,retention)
        original = Path(temp)/"private"
        original.mkdir()
        sources = _reconstruct(outer,retention,original,status=="COMPLETE_TRAIN_DIAGNOSTIC_ONLY")
        packer.verify_original_evidence(original,status=="COMPLETE_TRAIN_DIAGNOSTIC_ONLY")
        training = checked_json((original/sources[0]).read_bytes(),"V14_TRAINING_BAD_JSON")
        branches = _jsonl_gzip((original/sources[1]).read_bytes(),MAX_BRANCHES,"BRANCHES")
        events = _jsonl_gzip((original/sources[2]).read_bytes(),MAX_EVENTS,"OPTION_JOURNAL")
        proofs = {name:checked_json((original/name).read_bytes(),"V14_BAD_PROOF") for name in
                  (("manifest.json","diagnostic-readout.json","independent-qualification.json")
                   if status=="COMPLETE_TRAIN_DIAGNOSTIC_ONLY" else ("early_stop.json",))}
    need(training.get("executed_head") == ORIGINAL_V13_PRODUCT and
         training.get("harness_head") == expected_harness_sha and
         training.get("source_v12_head") == ORIGINAL_V12_PRODUCT and
         training.get("source_v12_original_sha256") == ORIGINAL_V12_FULL_SHA and
         training.get("training_only") is True and
         training.get("model_promotion_authorized") is False and
         training.get("dev_cal_test_ood_opened") is False,
         "V14_ORIGINAL_SOURCE_TRAINING_OR_SEALED_SPLIT_DRIFT")
    return {"status":status,"receipt":receipt,"outerZipSha256":expected_zip_sha,
            "receiptRawSha256":digest(outer["receipt.json"]),
            "v13ProductHead":ORIGINAL_V13_PRODUCT,"v13HarnessHead":expected_harness_sha,
            "hostedRun":expected_run,"retention":retention,"training":training,
            "proofs":proofs,"branches":branches,"events":events,
            "worlds":worlds,"publicMask":v3.public_mask}


def _validate_rows(bundle):
    """Recheck pairability, action legality, exact journals and witness labels."""
    training,branches,events = bundle["training"],bundle["branches"],bundle["events"]
    failed = training["sourceFailureDiagnosis"]["v5FailedWorlds"]
    wins = training["sourceFailureDiagnosis"]["v5WinningWorlds"]
    need(len(failed)==36 and len(wins)==12 and set(failed).isdisjoint(wins) and
         set(failed)|set(wins)==set(bundle["worlds"]),
         "V14_SOURCE_ONLY_SEEN_48_WORLD_SELECTION_DRIFT")
    need(len(branches)==training["recorded_branches"] and
         len(events)==training["durably_journaled_all_executed_option_events"],
         "V14_RETAINED_OPTION_BRANCH_COUNTS_MISSING")
    grouped_events=defaultdict(list)
    for event in events:
        grouped_events[event["branchId"]].append(event)
    ordinal=Counter();seen_branch_ids=set();grouped=defaultdict(list)
    firsts={}; safety=[]
    for idx,raw in enumerate(branches):
        seed=raw["seed"];fork=raw["source_prefix"]
        need(raw["branch_id"]==idx and seed in failed and
             type(fork) is int and 0<=fork<MAX_OPTIONS,
             "V14_RETAINED_BRANCH_NOT_ONE_OF_36_FAILED_SEEN_TRAIN")
        branch_id=f"v13-seen-train-{seed}-{ordinal[seed]:02d}"
        ordinal[seed]+=1
        need(branch_id not in seen_branch_ids,"V14_REPLAY_BRANCH_ID_DUPLICATED")
        seen_branch_ids.add(branch_id)
        steps=raw["transitions"]
        need(len(steps)==len(raw["actions"]) and 0<len(steps)<=MAX_OPTIONS and
             [t["action"] for t in steps]==raw["actions"] and
             0<=fork<=len(steps),"V14_RETAINED_ACTIONS_AND_FORK_DRIFT")
        need(len(grouped_events[branch_id])==len(steps),
             "V14_COMPLETE_BRANCH_AND_DURABLE_OPTION_JOURNAL_MISMATCH")
        for i,t in enumerate(steps):
            ev=grouped_events[branch_id][i]
            obs,nxt=t["observation"],t["next_observation"]
            need(len(obs)==len(nxt)==18 and all(type(x) in (int,float) and math.isfinite(x)
                 for x in (*obs,*nxt)) and len(t["mask"])==7 and
                 t["mask"]==bundle["publicMask"](obs) and
                 type(t["action"]) is int and 0<=t["action"]<7 and
                 t["mask"][t["action"]]==1 and
                 (obs[10]!=0 or t["action"]==6) and
                 type(t["cost"]) is int and t["cost"] in (0,1) and
                 type(t["done"]) is bool and type(t["success_info"]) is bool,
                 "V14_ORIGINAL_SEVEN_SHIELD_OR_PUBLIC18D_ILLEGAL")
            need(ev["optionIndexZeroBased"]==i and ev["seed"]==seed and
                 ev["branchId"]==branch_id and
                 ev["sourceWorldHash"]==bundle["worlds"][seed] and
                 ev["phase"]==("ORIGINAL_PREFIX" if i<fork else "COUNTERFACTUAL") and
                 ev["transition"]==t and ev["transitionSha256"]==sha_obj(t) and
                 ev["physicsQualificationPending"] is True,
                 "V14_DURABLE_ORIGINAL_STEP_JOURNAL_CONTENT_OR_SOURCE_CHANGED")
            if i:
                need(steps[i-1]["next_observation"]==obs,
                     "V14_ORIGINAL_REAL_PUBLIC_STATE_CHAIN_BROKEN")
            if t["cost"]:
                safety.append({"seed":seed,"branchId":branch_id,
                  "branchIdGlobalZeroBased":idx,"optionIndexZeroBased":i,
                  "action":t["action"],"originalMask7":t["mask"],
                  "publicObservationSha256":sha_obj(obs),
                  "transitionSha256":sha_obj(t),
                  "contactsCumulative":t["contacts_cumulative"],
                  "originalActionMaskLegal":True,"cost":t["cost"],
                  "done":t["done"],"unsafeMechanism":
                      "UNKNOWN_NOT_IN_RETAINED_PUBLIC_ORIGINAL_OPTION_TRACE",
                  "originalPhysicsPossibleCausesNotIndividuallyProven":
                    ["impulse_above_original_0.006", "obstacle_contact",
                     "body_out_of_original_bounds"]})
        grouped[seed].append({"branchId":branch_id,"raw":raw,
                              "sha256":sha_obj(steps),"unsafe":any(t["cost"] for t in steps),
                              "goal250":bool(steps[-1]["success_info"] and
                                  steps[-1]["done"] and steps[-1]["dwell_ticks_current"]>=250 and
                                  steps[-1]["contacts_cumulative"]>0 and
                                  not any(t["cost"] for t in steps))})
        if len(steps)>fork:
            t=steps[fork]
            key=(seed,t["action"])
            if key in firsts:
                need(firsts[key]["transition"]==t and firsts[key]["fork"]==fork,
                     "V14_PAIRED_FORK_SAME_ACTION_NONDETERMINISTIC_PHYSICS")
            else:
                firsts[key]={"seed":seed,"action":t["action"],"fork":fork,
                    "transition":t,"worldHash":bundle["worlds"][seed],
                    "branchId":branch_id,"branchTraceSha256":sha_obj(steps)}
    extra=set(grouped_events)-seen_branch_ids
    need(seen_branch_ids<=set(grouped_events) and
         len(events)>=sum(len(b["transitions"]) for b in branches),
         "V14_DURABLE_JOURNAL_UNKNOWN_OR_MISSING_BRANCH")
    # Any journaled *partial* final branch is valid only in incomplete STOP;
    # it cannot become a training row, nor silently disappear.
    if bundle["status"]=="COMPLETE_TRAIN_DIAGNOSTIC_ONLY":
        need(len(events)==sum(len(b["transitions"]) for b in branches),
             "V14_COMPLETE_STILL_HAS_UNQUALIFIED_PARTIAL_OPTIONS")
        need(not extra,"V14_COMPLETE_HAS_UNQUALIFIED_PARTIAL_BRANCH")
    else:
        need(len(extra)<=1,"V14_INCOMPLETE_MULTIPLE_MISSING_COMPLETED_BRANCHES")
        for branch_id in extra:
            partial=grouped_events[branch_id]
            need(all(e["seed"] in failed and
                     e["branchId"]==branch_id and
                     e["optionIndexZeroBased"]==i and
                     e["sourceWorldHash"]==bundle["worlds"][e["seed"]] and
                     e["transitionSha256"]==sha_obj(e["transition"]) and
                     len(e["transition"]["observation"])==18 and
                     len(e["transition"]["mask"])==7 and
                     e["transition"]["mask"]==bundle["publicMask"](
                         e["transition"]["observation"]) and
                     e["transition"]["mask"][e["transition"]["action"]]==1
                     for i,e in enumerate(partial)),
                 "V14_UNQUALIFIED_PARTIAL_OPTION_JOURNAL_MISMATCH")
            for e in partial:
                t=e["transition"]
                if t["cost"]:
                    safety.append({"seed":e["seed"],"branchId":branch_id,
                        "branchIdGlobalZeroBased":None,
                        "optionIndexZeroBased":e["optionIndexZeroBased"],
                        "action":t["action"],"originalMask7":t["mask"],
                        "publicObservationSha256":sha_obj(t["observation"]),
                        "transitionSha256":sha_obj(t),
                        "contactsCumulative":t["contacts_cumulative"],
                        "originalActionMaskLegal":bool(t["mask"][t["action"]]),
                        "cost":t["cost"],"done":t["done"],
                        "unsafeMechanism":"UNKNOWN_NOT_IN_RETAINED_PUBLIC_ORIGINAL_OPTION_TRACE",
                        "originalPhysicsPossibleCausesNotIndividuallyProven":
                            ["impulse_above_original_0.006", "obstacle_contact",
                             "body_out_of_original_bounds"]})
    return {"grouped":grouped,"firsts":firsts,"safety":safety,
            "completedBranches":len(branches),"completedOptions":sum(len(b["transitions"]) for b in branches),
            "journaledOptions":len(events),"failed":failed,"wins":wins}


def _beta_jeffreys_counts(wins,losses,ties):
    """Posterior Beta(0.5,0.5) and conservative 95% Cantelli lower bound.

    One matched WORLD yields at most one sign, no correlated branch inflation.
    A tie is reported and excluded from the Bernoulli sign posterior.
    """
    a=wins+.5;b=losses+.5
    mean=a/(a+b)
    variance=a*b/((a+b)**2*(a+b+1))
    bound=max(0.,mean-math.sqrt(19*variance))  # one-sided Cantelli >=95%
    return {"pairedWorldWins":wins,"pairedWorldLosses":losses,
            "pairedWorldTies":ties,"distinctInformativeWorlds":wins+losses,
            "jeffreysPosteriorBeta":[a,b],"posteriorMean":mean,
            "conservativePosteriorOneSided95Lower":bound,
            "probabilityBoundMethod":"Cantelli on exact Beta posterior variance; ties omitted"}


def _compile_complete(bundle,validated):
    training= bundle["training"]
    worlds=sorted(validated["grouped"])
    results=training["worldResults"]
    readout=bundle["proofs"]["diagnostic-readout.json"]
    qualified=bundle["proofs"]["independent-qualification.json"]
    need(training["status"]=="COMPLETE_TRAIN_DIAGNOSTIC_ONLY" and
         training["allWorldsComplete"] is True and training["hardStopReason"] is None and
         len(worlds)==len(results)==36 and
         [r["seed"] for r in results]==worlds and
         readout["world_results"]==results and
         readout["status"]=="COMPLETE_TRAIN_DIAGNOSTIC_ONLY" and
         qualified["all_36_seen_train_failure_worlds_physically_replayed"] is True and
         qualified["all_raw_branches_independently_replayed"]==len(bundle["branches"]) and
         qualified["all_raw_original_physics_option_steps_replayed"]==validated["completedOptions"] and
         qualified["any_unsafe_actual_cost"] is False and
         not validated["safety"],
         "V14_NEITHER_36_WORLD_COMPLETE_NOR_INDEPENDENT_ORIGINAL_PHYSICS_QUALIFIED")
    witnessed=[]
    for result in results:
        branches=validated["grouped"][result["seed"]]
        need(len(branches)==result["executedBudgetBranches"] and
             result["status"] in ("WITNESS","NONE_REACHABLE_WITHIN_FINITE_BUDGET"),
             "V14_MISSING_SEEN_WORLD_OR_UNREGISTERED_OUTCOME")
        wins=[b for b in branches if b["goal250"]]
        if result["status"]=="WITNESS":
            need(len(wins)==1 and wins[0]["sha256"]==result["actual250TickWitnessTraceSha256"],
                 "V14_WITNESS_NOT_TRUE_PHYSICAL_250TICK_TRACE")
            witnessed.append((result["seed"],wins[0]))
        else:
            need(not wins and result["actual250TickWitnessTraceSha256"] is None,
                 "V14_UNACKNOWLEDGED_REAL_WITNESS_GOAL")
    firsts=validated["firsts"]
    by_seed=defaultdict(dict)
    for (seed,action), row in firsts.items():
        by_seed[seed][action]=row
    all_pairs=[]
    for seed,actions in sorted(by_seed.items()):
        values=list(actions.values())
        if not values:continue
        obs=values[0]["transition"]["observation"]
        mask=values[0]["transition"]["mask"]
        fork=values[0]["fork"]
        need(all(v["transition"]["observation"]==obs and
                 v["transition"]["mask"]==mask and v["fork"]==fork for v in values),
             "V14_FIRST_ACTION_NOT_SAME_ORIGINAL_PUBLIC_FORK")
        for i,a in enumerate(sorted(actions)):
            for b in sorted(actions)[i+1:]:
                ta,tb=actions[a]["transition"],actions[b]["transition"]
                progress=lambda step:math.hypot(step["observation"][16]-step["observation"][0],
                          step["observation"][17]-step["observation"][1])-math.hypot(
                          step["next_observation"][16]-step["next_observation"][0],
                          step["next_observation"][17]-step["next_observation"][1])
                all_pairs.append({"seed":seed,"actionA":a,"actionB":b,
                                  "signedPublicOneOptionGoalProgressAminusB":progress(ta)-progress(tb),
                                  "sameOriginalPublicFork":True})
    witness_by_action=defaultdict(set)
    for seed,branch in witnessed:
        fork=branch["raw"]["source_prefix"]
        need(len(branch["raw"]["transitions"])>fork,
             "V14_WITNESS_WITHOUT_ANY_COUNTERFACTUAL_ACTION")
        witness_by_action[branch["raw"]["transitions"][fork]["action"]].add(seed)
    counts=Counter(row["action"] for row in firsts.values())
    candidate_rows=[]
    for action in range(6):  # never proposal ABSTAIN as a new motor primitive
        support=counts[action]
        pair_worlds=defaultdict(list)
        for row in all_pairs:
            if row["actionA"]==action:
                pair_worlds[row["seed"]].append(row["signedPublicOneOptionGoalProgressAminusB"])
            if row["actionB"]==action:
                pair_worlds[row["seed"]].append(-row["signedPublicOneOptionGoalProgressAminusB"])
        # One *distinct world*, one posterior sign, no pseudoreplication from
        # many alternatives or repeated same-seed beam branches.
        def median(numbers):
            values=sorted(numbers);n=len(values)
            return values[n//2] if n%2 else .5*(values[n//2-1]+values[n//2])
        world_effects={seed:median(values) for seed,values in pair_worlds.items()}
        wins=sum(g>PRACTICAL_PROGRESS_METERS for g in world_effects.values())
        losses=sum(g<-PRACTICAL_PROGRESS_METERS for g in world_effects.values())
        ties=len(world_effects)-wins-losses
        posterior=_beta_jeffreys_counts(wins,losses,ties)
        candidate_rows.append({"action":action,"originalMaskedLegalDistinctWorldsExecuted":support,
           "actualSafe250WitnessWorlds":sorted(witness_by_action[action]),
           "actualSafe250WitnessWorldCount":len(witness_by_action[action]),
           "matchedWithinForkDistinctWorldCount":len(world_effects),**posterior})
    eligible=[c for c in candidate_rows if
        c["actualSafe250WitnessWorldCount"]>=2 and
        c["originalMaskedLegalDistinctWorldsExecuted"]>=3 and
        c["matchedWithinForkDistinctWorldCount"]>=3 and
        c["posteriorMean"]>.5]
    eligible.sort(key=lambda c:(-c["actualSafe250WitnessWorldCount"],
                                -c["conservativePosteriorOneSided95Lower"],
                                -c["matchedWithinForkDistinctWorldCount"],c["action"]))
    proposal=None
    if eligible:
        chosen=eligible[0]
        proposal={"schema":SCHEMA+".single-prospective-train-policy-proposal",
          "id":f"v14-public-live-before-v5-abstain-action{chosen['action']}",
          "selectedOriginalOption":chosen["action"],"fallback":"frozen V5 unchanged",
          "onlyIf":"public live==true and held==false and V5 would early ABSTAIN; action mask allows selected option; no sealed state",
          "safety":"original 18D/7 shield unchanged, never override live false or any unsafe", 
          "onlyTrainingHypothesis":True,"sourceWitnessSeenTrainSeeds":chosen["actualSafe250WitnessWorlds"],
          "sourceObservedPairedUncertainty":chosen,
          "prospectiveActual250TickGainClaimed":False,"promotionAuthorized":False,
          "requiresNewDisjointPairedRealMuJoCoTrain":True,
          "requiresIndependentSourcePinnedOriginalPhysicsReplay":True,
          "stopOnFirstUnsafeOrLostFrozenV5Goal":True}
    rows=[]
    for (_,action),row in sorted(firsts.items()):
        t=row["transition"]
        rows.append({"seed":row["seed"],"originalWorldHash":row["worldHash"],
           "action":action,"forkOptionIndexZeroBased":row["fork"],
           "publicObservation18D":t["observation"],"originalMask7":t["mask"],
           "publicNextObservation18D":t["next_observation"],
           "actualCost":t["cost"],"actualContactsCumulative":t["contacts_cumulative"],
           "sourceBranchId":row["branchId"],"sourceBranchFullTraceSha256":row["branchTraceSha256"],
           "actualOneOptionTransitionSha256":sha_obj(t),"unbiasedEfficacyEvidence":False})
    return {"rows":rows,"candidate":proposal,"witnessed":witnessed,
            "actionEvidence":candidate_rows,"matchedPairs":all_pairs}


def compile_from_verified(bundle):
    """Pure decision compiler over a *previously* source-verified bundle."""
    stats=_validate_rows(bundle)
    failed=bundle["status"]!="COMPLETE_TRAIN_DIAGNOSTIC_ONLY"
    if failed:
        need(bundle["status"]=="INCOMPLETE_STOP" and
             bundle["training"]["status"]=="INCOMPLETE_STOP" and
             bundle["proofs"]["early_stop.json"]["status"]=="INCOMPLETE_STOP",
             "V14_FALSE_COMPLETE_OR_PARTIAL_STOP")
        reason=bundle["proofs"]["early_stop.json"]["reason"]
        need(reason=="V13_REAL_PHYSICS_UNSAFE" or
             reason.startswith("V13_SOURCE_OR_PHYSICS_EXCEPTION_") or
             reason=="V13_FINITE_DEADLINE" or
             reason.startswith("V13_INDEPENDENT_PHYSICS_NOT_QUALIFIED_"),
             "V14_UNREGISTERED_PARTIAL_STOP_REASON")
        science="HARD_STOP_UNSAFE_INCOMPLETE" if reason=="V13_REAL_PHYSICS_UNSAFE" \
                else "HARD_STOP_UNQUALIFIED_INCOMPLETE"
        # The 394 known events came from *two* seen worlds and many repeated
        # prefixes. Do not compute Bernoulli safety rates over option events.
        first=stats["safety"][0] if stats["safety"] else None
        if reason=="V13_REAL_PHYSICS_UNSAFE":
            need(len(stats["safety"])==1 and first["cost"]==1 and first["done"] is True and
                 bundle["events"][-1]["transitionSha256"]==first["transitionSha256"],
                 "V14_HARD_STOP_MUST_KEEP_FIRST_AND_FINAL_REAL_UNSAFE_OPTION")
        # Original known hosted negative hard stop is a SOURCE CHECK, not a
        # synthetic substitute. A different tuple under that exact ZIP is bad.
        if bundle["outerZipSha256"]==KNOWN_UNSAFE_ARTIFACT_SHA:
            need(bundle["hostedRun"]==43660619725 and reason=="V13_REAL_PHYSICS_UNSAFE" and
                 first is not None and
                 (first["seed"],first["branchIdGlobalZeroBased"],
                  first["optionIndexZeroBased"],first["action"],
                  first["contactsCumulative"])==(518006,22,37,2,2013) and
                 first["transitionSha256"]==
                  "4702034192e3877e42278a1b297e9b8c787955fbe2a30e411dd06fd9a7fee4ba",
                 "V14_ORIGINAL_FIRST_UNSAFE_TUPLE_DRIFT")
        return _package(bundle,stats,None,[],science,first,reason)
    complete=_compile_complete(bundle,stats)
    return _package(bundle,stats,complete,complete["rows"],
                    "SEEN_TRAIN_WITNESS_NEEDS_PROSPECTIVE" if complete["candidate"] else
                    "SCIENCE_STOP_NO_CAUSAL_ACTION_POLICY_SUPPORT",None,None)


def _package(bundle,stats,complete,rows,decision,unsafe_counterexample,stop_reason):
    # source lineage is recomputable from immutable input evidence; no time,
    # random selections, model parameters, or paid job trigger is included.
    lineage={"v13SourceHead":bundle["v13ProductHead"],
             "v13HarnessHead":bundle["v13HarnessHead"],
             "hostedRun":bundle["hostedRun"],
             "hostedArtifactSha256":bundle["outerZipSha256"],
             "hostedReceiptSha256":bundle["receiptRawSha256"],
             "originalV12Head":ORIGINAL_V12_PRODUCT,
             "originalV12FullSha256":ORIGINAL_V12_FULL_SHA,
             "retainedOriginalSha256":bundle["retention"]["original_sha256"],
             "originalV12WorldIndexSha256":V12_INDEX_SHA}
    lineage_hash=sha_obj(lineage)
    rows_bytes=b"".join(canonical(row)+b"\n" for row in rows)
    manifest={"schema":SCHEMA+".dataset-manifest","workId":WORK_ID,
       "sourceLineage":lineage,"sourceLineageSha256":lineage_hash,
       "status":"COMPLETE_SEEN_TRAIN_ONLY_NOT_EFFICACY" if complete else
                "UNQUALIFIED_PARTIAL_NO_TRAINING_DATA",
       "sourceReportedRecordedBranches":stats["completedBranches"],
       "sourceReportedDistinctSeenWorlds":len(stats["grouped"]),
       "sourceReportedCompleteOptionTransitions":stats["completedOptions"],
       "sourceReportedDurableOptionEvents":stats["journaledOptions"],
       "independentSafetyRateEstimable":False,
       "independentlyOriginalPhysicsReplayedAllBranches":complete is not None,
       "worldDisjointFuturePhysicsRequired":True,
       "fullOriginal7MaskPreserved":True,"noDevCalTestOodOpened":True,
       "noModelPromotion":True,"noAutomatedPaidDispatch":True,
       "trainingRowsFilename":"training_rows.jsonl" if complete else None,
       "trainingRowsCount":len(rows),"trainingRowsSha256":digest(rows_bytes) if complete else None,
       "unsafeOriginalTransitionCounterexample":unsafe_counterexample,
       "noTrainingFromIncompleteUnsafe":True}
    candidate=complete["candidate"] if complete else None
    readout={"schema":SCHEMA+".next-training-decision","workId":WORK_ID,
       "decision":decision,"sourceLineageSha256":lineage_hash,
       "originalActualPhysicsGoal250":"all original criteria retained",
       "originalSourceRunStatus":bundle["status"],
       "sourceStopReason":stop_reason,
       "seenTrainV5WinsFrozen":len(stats["wins"]),
       "seenTrainV5Failures":len(stats["failed"]),
       "seenTrainPhysicallyExecutedDistinctWorlds":len(stats["grouped"]),
       "seenTrainDiagnosticWitnessWorldCount":len(complete["witnessed"]) if complete else None,
       "seenTrainDiagnosticWitnessWorldSeeds":sorted(s for s,_ in complete["witnessed"]) if complete else None,
       "actionEvidenceWithDistinctWorldPairedBayesianUncertainty":
                 complete["actionEvidence"] if complete else None,
       "matchedRealOriginalPublicForkPairsCorrelated":len(complete["matchedPairs"]) if complete else None,
       "nextSingleV14PolicyProposal":candidate,
       "previouslyPreregisteredV13FutureTrainPlanSha256":V13_PREREGISTERED_PROSPECTIVE_PLAN_SHA,
       "nextTrainFrozenPublicSeedScanInclusive":[519024,519535] if candidate else None,
       "nextTrainAll512PublicSeedSha256":V13_PREREGISTERED_FRESH_ALL512_SHA if candidate else None,
       "futureSourceSeedCeilingExclusive":520000,
       "candidateScienceStatus":"HYPOTHESIS_ONLY_NO_PROSPECTIVE_GAIN" if candidate else "STOP",
       "noIndependentOptionLevelSafetyRateOrEfficacyClaim":True,
       "requiresIndependentDisjointRealPhysicsAndOriginalMaskAudit":True,
       "modelPromotionAuthorized":False,"automaticPaidDispatchAuthorized":False,
       "deployAuthorized":False,"releaseAuthorized":False,
       "safetyCounterexample":unsafe_counterexample}
    return {"decision":readout,"manifest":manifest,"rowsBytes":rows_bytes}
