#!/usr/bin/env python3
"""R3: fixed train/dev-only visual adapter experiment on verified R2 caches.

Primary preservation=0 and cosine-preservation=.05 ablation stay separate.
The selected primary may be epoch0 identity. No fresh calibration/test data,
images, model download, hosted API, service, or deployment is used here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import time
from pathlib import Path

import numpy as np

from visual_adapter import (epoch_batches, make_torch_adapter,
                            mine_visual_hard_negatives, project_features,
                            select_with_identity, symmetric_visual_loss)

R2_RETRIEVAL_SHA256 = "ef0103867c05d920a587dae858e6d25fc62f748ae294851bff48c3d19417e813"
MODEL_ID = "google/siglip2-base-patch16-224"
MODEL_REVISION = "75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2"
MODEL_WEIGHTS_SHA256 = "612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b"
PROTOCOL = {
    "schema_version": 1,
    "work_id": "META-LENS-ADAPTER-R3-20261114",
    "kind": "train_dev_only_shared_visual_residual",
    "model_id": MODEL_ID,
    "model_revision": MODEL_REVISION,
    "model_weights_sha256": MODEL_WEIGHTS_SHA256,
    "dimension": 768, "rank": 64, "trainable_parameters": 98304,
    "seeds": [17,31,53], "epochs": 12, "batch_size": 128,
    "temperature": 0.07, "learning_rate": 0.001,
    "weight_decay": 0.0001, "gradient_clip": 1.0,
    "recipes": [{"name":"primary", "preservation":0.0}, {"name":"cosine_preservation_ablation", "preservation":0.05}],
    "preservation_definition": "mean across two anchor views of (1 - cosine(projected, frozen)); not coordinate-averaged MSE",
    "positive_pair": "same product, distinct source-image SHA256 query/gallery",
    "negative_policy": "same-family nonpositive products masked; never promoted to positives",
    "mining": "train-only mean of both frozen image-image similarity directions; top4 other-family candidates",
    "anchors": "each train row exactly once per epoch; at most floor(batch/2) anchors; additional candidates are never loss query rows",
    "loss": "symmetric image-image contrastive CE over anchors only plus recipe's optional cosine preservation",
    "epoch_selection": "dev alternate-view-to-gallery Recall@1, then MRR; identity wins exact ties; no minimum gain threshold",
    "seed_selection": "same dev ordering; earliest fixed seed wins nonidentity ties",
    "confirmation_candidate": "primary recipe selection only; ablation never substitutes automatically",
    "epoch0_identity_eligible": True,
    "encoder_finetuned": False,
    "fresh_cal_test_evaluated": False,
    "r2_test_ood_used_for_selection": False,
    "deployment_authorized": False,
}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()


def load_r2_helpers():
    path = Path(__file__).resolve().parent.parent / "retrieval-r2" / "retrieval.py"
    if not path.is_file() or sha_bytes(path.read_bytes()) != R2_RETRIEVAL_SHA256:
        raise ValueError("missing_or_changed_frozen_sibling_r2_retrieval")
    spec = importlib.util.spec_from_file_location("meta_r2_retrieval_frozen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def deadline_check(deadline):
    if time.monotonic() > deadline:
        raise RuntimeError("r3_experiment_deadline_exceeded")


def load_train_dev(data_root, feature_path, helpers):
    dataset_path = data_root / "dataset.json"
    dataset_sha = helpers.file_sha256(dataset_path)
    if (data_root / "dataset.sha256").read_text().strip() != dataset_sha:
        raise ValueError("r2_dataset_seal_mismatch")
    manifest = json.loads(dataset_path.read_text())
    helpers.validate_dataset(manifest)
    records = manifest["records"]
    receipt = json.loads(feature_path.with_suffix(".json").read_text())
    feature_sha = helpers.file_sha256(feature_path)
    if receipt.get("dataset_sha256") != dataset_sha or receipt.get("feature_sha256") != feature_sha or receipt.get("product_order") != [r["product_id"] for r in records]:
        raise ValueError("r2_feature_dataset_or_order_mismatch")
    if receipt.get("model_id") != MODEL_ID or receipt.get("model_revision") != MODEL_REVISION or receipt.get("model_weights_sha256") != MODEL_WEIGHTS_SHA256 or receipt.get("encoder_frozen") is not True or receipt.get("image_inference_executed") is not True:
        raise ValueError("r2_frozen_pixel_feature_provenance_mismatch")
    indices = {s:np.asarray([i for i,r in enumerate(records) if r["split"]==s],dtype=np.int64) for s in ("train","dev")}
    if any(len(v)<20 for v in indices.values()):
        raise ValueError("insufficient_train_or_dev")
    views = {}
    with np.load(feature_path,allow_pickle=False) as archive:
        # Read only visual arrays. Text features never enter the R3 loss.
        for key in ("query","gallery"):
            array = archive[key]
            if array.dtype != np.float32 or array.shape != (len(records),768) or not np.isfinite(array).all() or not np.allclose(np.linalg.norm(array,axis=1),1,atol=0.001):
                raise ValueError("r2_visual_cache_shape_dtype_or_normalization_mismatch")
            for split,idx in indices.items():
                views.setdefault(split,{})[key] = helpers.normalize(array[idx])
            del array
    selected_records = {s:[records[i] for i in idx] for s,idx in indices.items()}
    families = {s:[r["family_id"] for r in selected_records[s]] for s in indices}
    if set(families["train"]) & set(families["dev"]):
        raise ValueError("train_dev_family_overlap")
    if len(set(families["train"]))<2:
        raise ValueError("two_train_families_required")
    for subset in selected_records.values():
        if any(r["views"][0]["sha256"]==r["views"][1]["sha256"] for r in subset):
            raise ValueError("same_image_positive_pair_rejected")
    binding = {"dataset_sha256":dataset_sha,"feature_sha256":feature_sha,"feature_receipt_sha256":helpers.file_sha256(feature_path.with_suffix(".json")),"train_product_ids_sha256":sha_bytes(canonical([r["product_id"] for r in selected_records["train"]])),"dev_product_ids_sha256":sha_bytes(canonical([r["product_id"] for r in selected_records["dev"]])),"consumed_partitions":["train","dev"],"consumed_counts":{s:len(v) for s,v in selected_records.items()},"consumed_family_counts":{s:len(set(v)) for s,v in families.items()},"source_manifest_contains_historical_r2_partitions":True,"historical_test_ood_scores_computed":False,"fresh_cal_test_loaded":False}
    return views,families,binding


def evaluate_dev(views, families, weights, helpers):
    q=project_features(views["query"],weights)
    g=project_features(views["gallery"],weights)
    return helpers.retrieval_metrics(q@g.T,families)


def train_candidate(recipe, seed, views, families, hard, baseline, output, helpers, device, deadline):
    import torch
    from safetensors.numpy import save_file
    model=make_torch_adapter(768,64,seed,device)
    if sum(p.numel() for p in model.parameters()) != 98304:
        raise RuntimeError("unexpected_trainable_parameter_count")
    initial={name:value.detach().cpu().numpy().copy() for name,value in model.state_dict().items()}
    optimizer=torch.optim.AdamW(model.parameters(),lr=0.001,weight_decay=0.0001)
    query=torch.tensor(views["train"]["query"],device=device,dtype=torch.float32)
    gallery=torch.tensor(views["train"]["gallery"],device=device,dtype=torch.float32)
    best={**baseline,"recipe":recipe["name"],"preservation":recipe["preservation"]}
    best_weights=None
    history=[]
    max_gradient=0.0
    steps=0
    started=time.monotonic()
    for epoch in range(1,13):
        deadline_check(deadline)
        model.train()
        coverage=np.zeros(len(query),dtype=np.int64)
        loss_sum=contrast_sum=cosine_sum=0.0
        anchors_seen=candidate_rows=0
        epoch_steps=0
        for batch in epoch_batches(families["train"],hard,128,seed,epoch-1):
            deadline_check(deadline)
            coverage[batch.anchors]+=1
            loss,parts=symmetric_visual_loss(model,query,gallery,batch,0.07,recipe["preservation"])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            gradient=float(torch.nn.utils.clip_grad_norm_(model.parameters(),1.0).detach().cpu())
            if not np.isfinite(gradient):
                raise RuntimeError("nonfinite_training_gradient")
            max_gradient=max(max_gradient,gradient)
            optimizer.step()
            n=len(batch.anchors)
            anchors_seen+=n
            candidate_rows+=len(batch.candidates)
            loss_sum+=float(loss.detach().cpu())*n
            contrast_sum+=parts["contrastive"]*n
            cosine_sum+=parts["cosine_preservation"]*n
            steps+=1
            epoch_steps+=1
        if anchors_seen!=len(query) or not np.all(coverage==1):
            raise RuntimeError("one_anchor_per_epoch_invariant_broken")
        model.eval()
        weights={k:v.detach().cpu().numpy().astype(np.float32,copy=True) for k,v in model.state_dict().items()}
        if not all(np.isfinite(v).all() for v in weights.values()):
            raise RuntimeError("nonfinite_adapter_weights")
        dev=evaluate_dev(views["dev"],families["dev"],weights,helpers)
        candidate={"kind":"adapter","recipe":recipe["name"],"preservation":recipe["preservation"],"seed":seed,"epoch":epoch,"dev":dev,"checkpoint":None,"checkpoint_sha256":None}
        selected=select_with_identity({**baseline,"recipe":recipe["name"],"preservation":recipe["preservation"]},[best,candidate])
        if selected is candidate:
            best=dict(candidate)
            best_weights=weights
        elif selected["kind"]=="identity":
            best=selected
            best_weights=None
        row={"epoch":epoch,"loss":loss_sum/anchors_seen,"contrastive_loss":contrast_sum/anchors_seen,"cosine_preservation":cosine_sum/anchors_seen,"anchors_seen":anchors_seen,"unique_anchors":int(np.sum(coverage>0)),"minimum_anchor_count":int(coverage.min()),"maximum_anchor_count":int(coverage.max()),"candidate_rows_including_reuse":candidate_rows,"optimizer_steps":epoch_steps,"dev":dev,"selected_epoch_so_far":best["epoch"],"selected_kind_so_far":best["kind"]}
        history.append(row)
        print(json.dumps({"stage":"r3_training","recipe":recipe["name"],"seed":seed,**row}),flush=True)
    final={k:v.detach().cpu().numpy().astype(np.float32,copy=True) for k,v in model.state_dict().items()}
    final_relative=f"checkpoints/{recipe['name']}-seed-{seed}-final.safetensors"
    save_file(final,str(output/final_relative))
    if best_weights is not None:
        relative=f"checkpoints/{recipe['name']}-seed-{seed}.safetensors"
        save_file(best_weights,str(output/relative))
        best["checkpoint"]=relative
        best["checkpoint_sha256"]=helpers.file_sha256(output/relative)
    update_norm=float(np.sqrt(sum(float(np.sum((final[k]-initial[k])**2,dtype=np.float64)) for k in final)))
    report={"recipe":recipe["name"],"preservation":recipe["preservation"],"seed":seed,"trainable_parameters":98304,"epoch0":baseline,"history":history,"selection":best,"optimizer_steps":steps,"max_observed_gradient_norm":max_gradient,"final_parameter_update_l2":update_norm,"final_b_l2":float(np.linalg.norm(final["b"])),"gradient_observed":bool(max_gradient>0),"parameter_update_observed":bool(update_norm>0),"selected_checkpoint_trained":best["kind"]=="adapter","final_checkpoint":final_relative,"final_checkpoint_sha256":helpers.file_sha256(output/final_relative),"seconds":time.monotonic()-started,"no_text_or_teacher_used":True}
    helpers.write_json(output/f"history-{recipe['name']}-seed-{seed}.json",report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--features",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--device",default="cuda:0")
    parser.add_argument("--max-seconds",type=int,default=1800)
    args=parser.parse_args()
    if not 60<=args.max_seconds<=7200:
        parser.error("bounded runtime required")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("preserve previous run; output must be new or empty")
    helpers=load_r2_helpers()
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"checkpoints").mkdir(exist_ok=True)
    started=time.monotonic()
    deadline=started+args.max_seconds
    protocol_sha=sha_bytes(canonical(PROTOCOL))
    source_hashes={name:helpers.file_sha256(Path(__file__).with_name(name)) for name in ("visual_adapter.py","train_visual.py","test_visual_adapter.py")}
    source_hashes["../retrieval-r2/retrieval.py"]=R2_RETRIEVAL_SHA256
    helpers.write_json(args.output/"protocol.json",PROTOCOL)
    views,families,binding=load_train_dev(args.data,args.features,helpers)
    import torch
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("requested_cuda_unavailable")
    if args.device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    runtime={"python":platform.python_version(),"numpy":np.__version__,"torch":torch.__version__,"safetensors":importlib.metadata.version("safetensors"),"cuda_runtime":torch.version.cuda,"device":args.device,"gpu":torch.cuda.get_device_name(torch.device(args.device)) if args.device.startswith("cuda") else None,"training_dtype":"float32","deterministic_bitwise_reproducibility_claimed":False}
    helpers.write_json(args.output/"run-start.json",{"protocol_sha256":protocol_sha,"source_hashes":source_hashes,"input_binding":binding,"runtime":runtime,"max_seconds":args.max_seconds,"started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())})
    dev=evaluate_dev(views["dev"],families["dev"],None,helpers)
    baseline={"kind":"identity","seed":None,"epoch":0,"dev":dev,"checkpoint":None,"checkpoint_sha256":None}
    helpers.write_json(args.output/"epoch0.json",baseline)
    deadline_check(deadline)
    hard=mine_visual_hard_negatives(views["train"]["query"],views["train"]["gallery"],families["train"],4)
    hard_receipt={"source_partition":"train","local_rows":len(hard),"k":hard.shape[1],"sha256":sha_bytes(hard.astype("<i8").tobytes()),"source_train_product_ids_sha256":binding["train_product_ids_sha256"],"no_dev_or_test_mining":True}
    helpers.write_json(args.output/"hard-negatives.json",hard_receipt)
    reports=[]
    selections={}
    for recipe in PROTOCOL["recipes"]:
        runs=[train_candidate(recipe,seed,views,families,hard,baseline,args.output,helpers,args.device,deadline) for seed in PROTOCOL["seeds"]]
        reports.extend(runs)
        identity={**baseline,"recipe":recipe["name"],"preservation":recipe["preservation"]}
        selections[recipe["name"]]=select_with_identity(identity,[run["selection"] for run in runs])
    selection={"schema_version":1,"kind":"meta.visual_adapter.r3.selection","work_id":PROTOCOL["work_id"],"dataset_sha256":binding["dataset_sha256"],"feature_sha256":binding["feature_sha256"],"protocol_sha256":protocol_sha,"source_hashes":source_hashes,"primary":selections["primary"],"ablation":selections["cosine_preservation_ablation"],"confirmation_candidate":dict(selections["primary"]),"selection_partition":"dev","fresh_cal_test_evaluated":False,"r2_test_ood_used_for_selection":False,"physical_identity_verified":False,"action_authorized":False,"deployment_authorized":False}
    helpers.write_json(args.output/"selection.json",selection)
    helpers.write_json(args.output/"report.json",{"schema_version":1,"status":"COMPLETED_TRAIN_DEV_ONLY","work_id":PROTOCOL["work_id"],"protocol":PROTOCOL,"protocol_sha256":protocol_sha,"source_hashes":source_hashes,"input_binding":binding,"runtime":runtime,"epoch0":baseline,"hard_negative_receipt":hard_receipt,"candidates":reports,"selection":selection,"wall_seconds":time.monotonic()-started,"peak_torch_gpu_bytes":torch.cuda.max_memory_allocated() if args.device.startswith("cuda") else None,"gpu_or_provider_cost_usd":None,"cost_owner":"root_provider_receipt","fresh_cal_test_evaluated":False,"promotion_qualified":False,"deployment_authorized":False,"limitations":["Existing R2 train/dev is reused; this is development evidence, not an independent confirmation.","Known R2 test/OOD outcomes motivated a new objective; they are not scored or used to choose R3 checkpoints.","No new image encoder weights or model backbones are trained; only the shared residual projection is learned.","Primary and preservation ablation remain separate; only primary is automatically selected for prospective confirmation.","Dev superiority can be selection noise; no minimum gain or significance claim is imposed.","Catalog-image retrieval does not establish live glasses, physical identity, OCR, user learning or spatial registration quality.","Foundation encoder pretraining overlap with public ABO remains unknown."]})
    print(json.dumps({"stage":"R3_TRAIN_DEV_COMPLETED","selection":str(args.output/"selection.json"),"primary_kind":selection["primary"]["kind"],"primary_epoch":selection["primary"]["epoch"],"fresh_cal_test_evaluated":False}),flush=True)


if __name__=="__main__":
    main()
