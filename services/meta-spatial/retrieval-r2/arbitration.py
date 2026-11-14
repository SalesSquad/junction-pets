#!/usr/bin/env python3
"""Predeclared cache-only late fusion / disagreement study. No model training.

Model spaces remain separate: only candidate ranks or already comparable
SigLIP image/text cosine scores are combined. ask_new_view is an offline
recommendation, never an executed camera action or evidence of calls saved.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from retrieval import (absent_family_scores, confidence, family_max,
                       file_sha256, retrieval_metrics,
                       upper_false_accept_bound, validate_dataset, write_json)

SIGLIP = {"id": "google/siglip2-base-patch16-224", "revision": "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2", "weights": "612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b", "dimension": 768}
DINO = {"id": "facebook/dinov2-small", "revision": "ed25f3a31f01632728cabb09d1542f84ab7b0056", "weights": "ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1", "dimension": 384}
PROTOCOL = {
    "id": "META-LENS-TRAIN-20261114-R2-ARBITRATION-1",
    "selection_after_test_inspection_allowed": False,
    "trained_parameters": 0,
    "rrf_k": 60,
    "rrf_components": ["DINO_image_image", "SigLIP_image_image", "SigLIP_image_text"],
    "rrf_weights": [1, 1, 1],
    "agreement": "DINO_top1 == dev_selected_SigLIP_hybrid_top1 == RRF_top1; exact product, not family",
    "methods": ["frozen_siglip_hybrid", "frozen_dino", "fixed_rrf", "fixed_rrf_agreement"],
    "absent_family_risk_targets": [0.01, 0.05],
    "calibration_coverage_targets": [0.10, 0.25, 0.50, 0.75],
    "threshold_selection_partition": "cal",
    "siglip_hybrid_weight_selection_partition": "dev",
    "evaluation_partitions": ["test", "ood"],
    "present_error_scope": "ALL query rows plus any error within each family",
    "absent_error_scope": "ANY acceptance across all query variants within each absent family",
    "capture_outcome": "SIMULATED_RECOMMENDATION_ONLY",
    "actual_new_view_observed": False,
    "counterfactual_quality_gain_measured": False,
}


def rrf(score_matrices, k=60):
    if k != 60 or len(score_matrices) != 3:
        raise ValueError("predeclared_three_component_rrf60_required")
    shape = np.asarray(score_matrices[0]).shape
    if len(shape) != 2 or shape[0] != shape[1]:
        raise ValueError("square_candidate_scores_required")
    fused = np.zeros(shape, dtype=np.float32)
    valid = None
    for raw in score_matrices:
        scores = np.asarray(raw)
        if scores.shape != shape or np.isnan(scores).any() or np.isposinf(scores).any():
            raise ValueError("invalid_component_scores")
        this_valid = np.isfinite(scores)
        if valid is not None and not np.array_equal(valid, this_valid):
            raise ValueError("candidate_masks_must_match")
        valid = this_valid
        order = np.argsort(-scores, axis=1, kind="stable")
        ranks = np.empty_like(order)
        np.put_along_axis(ranks, order, np.arange(shape[1])[None,:] + 1, axis=1)
        fused += np.where(valid, 1.0 / (k + ranks), 0.0).astype(np.float32)
    fused[~valid] = -np.inf
    return fused


def assemble(dino, siglip_ii, siglip_it, weight):
    if weight not in (0.0,0.25,0.5,0.75,1.0):
        raise ValueError("unexpected_dev_hybrid_weight")
    # Avoid 0 * -inf during absent-family replay at the endpoint weights.
    if weight == 0:
        hybrid = siglip_ii.copy()
    elif weight == 1:
        hybrid = siglip_it.copy()
    else:
        hybrid = weight*siglip_it + (1-weight)*siglip_ii
    fused = rrf([dino, siglip_ii, siglip_it])
    agree = (dino.argmax(1) == hybrid.argmax(1)) & (fused.argmax(1) == dino.argmax(1))
    yes = np.ones(len(dino), dtype=bool)
    return {"frozen_siglip_hybrid": (hybrid, yes), "frozen_dino": (dino, yes), "fixed_rrf": (fused, yes), "fixed_rrf_agreement": (fused, agree)}


def summarize(scores, allowed, absent_scores, absent_allowed, families, policy):
    values, top = confidence(scores)
    absent_values, _ = confidence(absent_scores)
    threshold = policy["threshold"]
    accepted = np.zeros(len(values), dtype=bool) if threshold is None else allowed & (values >= threshold)
    absent_accepted = np.zeros(len(values), dtype=bool) if threshold is None else absent_allowed & (absent_values >= threshold)
    correct = top == np.arange(len(values))
    wrong = accepted & ~correct
    family_wrong = family_max(wrong, families) > 0
    family_absent = family_max(absent_accepted, families) > 0
    n = len(family_wrong)
    return {"queries": len(values), "families": n, "accepted": int(accepted.sum()), "coverage": float(accepted.mean()), "accepted_precision": float(np.sum(accepted & correct)/accepted.sum()) if accepted.any() else None, "wrong_present_accepted": int(wrong.sum()), "present_families_with_any_error": int(family_wrong.sum()), "present_family_error_upper95": upper_false_accept_bound(int(family_wrong.sum()),n), "absent_query_false_accepts": int(absent_accepted.sum()), "absent_family_false_accepts": int(family_absent.sum()), "absent_family_false_accept_rate": float(family_absent.mean()), "absent_family_upper95": upper_false_accept_bound(int(family_absent.sum()),n), "ask_new_view_fraction": float(1-accepted.mean()), "ask_due_to_disagreement": int(np.sum(~allowed)), "ask_due_to_threshold_or_unsupported_calibration": int(np.sum(allowed & ~accepted)), "ask_new_view_is_simulated_recommendation": True, "actual_capture_performed": False, "calls_saved_measured": False, "conditional_accepted_error_certified": False, "bound_method": "any_error_within_family; exact_zero_event_binomial_else_one_sided_Wilson95", "bound_assumption": "independent_connected_families; source_correlations_remain"}


def calibrate(scores, allowed, absent_scores, absent_allowed, families, risk_target):
    values, top = confidence(scores)
    negative, _ = confidence(absent_scores)
    correct = top == np.arange(len(values))
    candidates = np.unique(np.concatenate((values, negative)))
    candidates = np.concatenate((candidates, [np.nextafter(np.float32(candidates.max()),np.float32(np.inf))]))
    n = len(set(families))
    best = None
    for threshold in candidates:
        accepted = allowed & (values >= threshold)
        absent = absent_allowed & (negative >= threshold)
        absent_events = int(np.sum(family_max(absent,families)>0))
        upper = upper_false_accept_bound(absent_events,n)
        if upper <= risk_target and not np.any(accepted & ~correct):
            coverage = float(accepted.mean())
            if best is None or coverage > best["calibration_coverage"]:
                best = {"threshold": float(threshold), "calibration_coverage": coverage, "status": "cal_selected", "calibration_absent_family_upper95": upper}
    if best is None:
        best = {"threshold": None, "calibration_coverage": 0.0, "status": "always_ask_insufficient_calibration"}
    return {**best, "partition": "cal", "absent_family_false_accept_rate_target": risk_target, "zero_observed_present_errors_required": True, "conditional_accepted_error_certified": False}


def coverage_policy(scores, allowed, target):
    """Select on CAL only; report actual test coverage, never retune it."""
    values, _ = confidence(scores)
    best = {"threshold": None, "calibration_coverage": 0.0}
    for threshold in np.unique(values):
        coverage = float(np.mean(allowed & (values >= threshold)))
        if coverage <= target and coverage > best["calibration_coverage"]:
            best = {"threshold": float(threshold), "calibration_coverage": coverage}
    return {**best, "partition": "cal", "target_coverage": target, "maximum_gate_coverage": float(allowed.mean()), "risk_constraint_enforced": False, "test_coverage_exactly_matched": False}


def typed_decision(scores, allowed, product_ids, policy):
    vector = np.asarray(scores,dtype=np.float32).reshape(1,-1)
    if len(product_ids) != vector.shape[1] or not isinstance(allowed,(bool,np.bool_)):
        raise ValueError("invalid_decision_input")
    value, top = confidence(vector)
    threshold = policy.get("threshold")
    if threshold is not None and (isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not np.isfinite(threshold)):
        raise ValueError("invalid_policy_threshold")
    accepted = allowed and threshold is not None and float(value[0]) >= threshold
    return {"schema_version":1, "kind":"meta.retrieval.recommendation", "decision":"candidate" if accepted else "ask_new_view", "candidate_product_id":product_ids[int(top[0])] if accepted else None, "reason":"accepted_by_predeclared_gate_and_threshold" if accepted else "model_disagreement" if not allowed else "insufficient_calibrated_confidence", "confidence_score":float(value[0]), "confidence_is_probability":False, "physical_identity_verified":False, "identity_verified":False, "action_authorized":False, "actual_device_action":False, "evidence_domain":"offline_public_catalog_retrieval", "new_view_outcome":"NOT_OBSERVED"}


def read_cache(path, receipt, keys, n, dimension):
    if receipt["feature_sha256"] != file_sha256(path):
        raise ValueError("cache_digest_mismatch")
    with np.load(path,allow_pickle=False) as f:
        arrays = {key:np.asarray(f[key],dtype=np.float32) for key in keys}
    for value in arrays.values():
        if value.shape != (n,dimension) or not np.isfinite(value).all() or not np.allclose(np.linalg.norm(value,axis=1),1,atol=0.001):
            raise ValueError("cache_shape_or_normalization_mismatch")
    return arrays


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data",required=True,type=Path)
    p.add_argument("--siglip-features",required=True,type=Path)
    p.add_argument("--siglip-run",required=True,type=Path)
    p.add_argument("--dino-run",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--max-seconds",type=int,default=900)
    a=p.parse_args()
    if not 30 <= a.max_seconds <= 1800:
        p.error("bounded CPU experiment required")
    if a.output.exists() and any(a.output.iterdir()):
        p.error("preserve previous output; select new directory")
    a.output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    write_json(a.output/"preregistration.json",{**PROTOCOL,"script_sha256":file_sha256(__file__),"model_pins":{"siglip":SIGLIP,"dino":DINO}})
    dataset_sha=file_sha256(a.data/"dataset.json")
    if (a.data/"dataset.sha256").read_text().strip()!=dataset_sha:
        raise ValueError("dataset_seal_mismatch")
    data=json.loads((a.data/"dataset.json").read_text())
    integrity=validate_dataset(data)
    records=data["records"]
    order=[r["product_id"] for r in records]
    sr=json.loads(a.siglip_features.with_suffix(".json").read_text())
    dr=json.loads((a.dino_run/"report.json").read_text())
    run=json.loads((a.siglip_run/"report.json").read_text())
    selection=run["selection"]
    if sr["dataset_sha256"]!=dataset_sha or dr["dataset_sha256"]!=dataset_sha or run["dataset_sha256"]!=dataset_sha or sr["product_order"]!=order or dr["product_order"]!=order:
        raise ValueError("cache_dataset_or_order_mismatch")
    if sr["model_id"]!=SIGLIP["id"] or sr["model_revision"]!=SIGLIP["revision"] or sr["model_weights_sha256"]!=SIGLIP["weights"] or not sr.get("image_inference_executed") or not sr.get("encoder_frozen"):
        raise ValueError("siglip_model_pin_mismatch")
    if dr["model_id"]!=DINO["id"] or dr["model_revision"]!=DINO["revision"] or dr["model_weight_sha256"]!=DINO["weights"] or dr["status"]!="COMPLETED" or dr["kind"]!="ACTUAL_FROZEN_META_DINOV2_BASELINE" or not dr.get("encoder_frozen"):
        raise ValueError("dino_model_pin_mismatch")
    if run["status"]!="COMPLETED" or run["feature_receipt"]["feature_sha256"]!=sr["feature_sha256"] or selection["partition"]!="dev" or selection["test_or_ood_used_for_selection"] is not False:
        raise ValueError("invalid_siglip_dev_selection_binding")
    weight=selection["frozen_hybrid_image_text_weight"]
    siglip=read_cache(a.siglip_features,sr,("query","gallery","text"),len(records),SIGLIP["dimension"])
    dino=read_cache(a.dino_run/"features.npz",dr,("query","gallery"),len(records),DINO["dimension"])
    families={}

    def prepare_partition(split):
        if time.monotonic()-started>a.max_seconds:
            raise RuntimeError("arbitration_deadline_exceeded")
        idx=np.asarray([i for i,r in enumerate(records) if r["split"]==split])
        families[split]=[records[i]["family_id"] for i in idx]
        # Never multiply DINO vectors with SigLIP vectors.
        component=[dino["query"][idx]@dino["gallery"][idx].T,
                   siglip["query"][idx]@siglip["gallery"][idx].T,
                   siglip["query"][idx]@siglip["text"][idx].T]
        normal=assemble(*component,weight)
        absent=assemble(*(absent_family_scores(s,families[split]) for s in component),weight)
        return normal,absent

    prepared={"cal":prepare_partition("cal")}
    policies={}
    # No test/OOD metric is used for choosing a method, gate, weight or threshold.
    cal_normal,cal_absent=prepared["cal"]
    for method in PROTOCOL["methods"]:
        scores,allowed=cal_normal[method]
        absent_scores,absent_allowed=cal_absent[method]
        policies[method]={"risk":{str(target):calibrate(scores,allowed,absent_scores,absent_allowed,families["cal"],target) for target in PROTOCOL["absent_family_risk_targets"]},"coverage":{str(target):coverage_policy(scores,allowed,target) for target in PROTOCOL["calibration_coverage_targets"]}}
    write_json(a.output/"calibration.json",policies)
    # Freeze the thresholds before constructing any heldout score matrices.
    for split in ("test","ood"):
        prepared[split]=prepare_partition(split)
    results={}
    for split in ("cal","test","ood"):
        normal,absent=prepared[split]
        results[split]={}
        for method in PROTOCOL["methods"]:
            if time.monotonic()-started>a.max_seconds:
                raise RuntimeError("arbitration_deadline_exceeded")
            scores,allowed=normal[method]
            absent_scores,absent_allowed=absent[method]
            by_mode={mode:{target:summarize(scores,allowed,absent_scores,absent_allowed,families[split],policy) for target,policy in policies[method][mode].items()} for mode in ("risk","coverage")}
            results[split][method]={"retrieval_before_gate":retrieval_metrics(scores,families[split]),"policies":by_mode}
    report={"schema_version":1,"status":"COMPLETED","work_id":PROTOCOL["id"],"evidence_mode":"ACTUAL_CACHE_REPLAY_WITH_SIMULATED_NEW_VIEW_RECOMMENDATIONS","protocol":PROTOCOL,"script_sha256":file_sha256(__file__),"dependency_sha256":file_sha256(Path(__file__).with_name("retrieval.py")),"dataset_sha256":dataset_sha,"integrity":integrity,"model_pins":{"siglip":SIGLIP,"dino":DINO},"cache_sha256":{"siglip":sr["feature_sha256"],"dino":dr["feature_sha256"]},"dev_selected_siglip_hybrid_weight":weight,"calibration":policies,"results":results,"wall_seconds":time.monotonic()-started,"parameters_trained":0,"gpu_calls":0,"hosted_api_calls":0,"actual_new_view_observed":False,"calls_saved_measured":False,"physical_identity_verified":False,"action_authorized":False,"deployment_authorized":False,"limitations":["Risk thresholds and coverage thresholds are separate predeclared comparison tracks; coverage-track policies do not enforce a risk limit.","Coverage targets are matched only on calibration where attainable; actual test/OOD coverage is reported and never retuned.","One percent target concerns absent-family any-accept events, not conditional error among accepted candidates.","Foundation model overlap with public ABO is unknown; campaign split independence does not establish pretraining decontamination.","Disagreement may reflect correlated model errors; agreement is not truth or physical identity.","New-view recommendations have no observed second-view outcome; no benefit, latency or saved calls of active sensing is established.","The selected SigLIP hybrid comes from its prior dev-only selection; no winner is selected using this test/OOD report."]}
    write_json(a.output/"report.json",report)
    print(json.dumps({"stage":"ARBITRATION_COMPLETED","report":str(a.output/"report.json"),"actual_new_view_observed":False}),flush=True)


if __name__=="__main__":
    main()
