#!/usr/bin/env python3
"""Six new public HB numerical ML corrections, with unknown-rejection training.

Development-only: known labels 12/15 from TRAIN physical scenes5/9, unknown
class detector trained from subsets of CAL physical scene10. For each of six
disjoint 8-frame DEV folds, reserve 28 calibration frame groups to fit unknown
rejectors, 12 different groups to select a risk-constrained candidate, and
open 8 DEV frame groups only after six candidate stages have frozen. The six
DEV folds are from a previously studied SAME physical scene; no blind
new-scene, device, camera, product/identity, or deployment claim.

Never read feature values from exposed scene8/11 test rows, NEVER make product
permission decisions with this model. Python+scikit-learn CPU only; no GPU,
LLM, network, API, secrets, or private photos.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import pickle
import subprocess

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

SOURCE_CSV_SHA = "2540595932867db80e1313dc011640b901c53b16a4f3f897b9d13e32d0c57363"
SOURCE_FILE = "fixtures/lens-hb-cc0-vision-20261114/public-hb-object-features.csv"
KNOWN = ("12", "15")
METHODS = (
    "color_balanced_linear",
    "vision_pca16_linear",
    "vision_prototype_novelty",
    "learned_unknown_logistic",
    "learned_unknown_forest",
    "dual_unknown_consensus",
)
WORK_ID = "CHIBI-LENS-SIX-UNKNOWN-ML-20261115"


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def dataset(path: Path):
    if not path.is_file() or path.is_symlink() or sha_file(path) != SOURCE_CSV_SHA:
        raise RuntimeError("Exact approved public HB source CSV bytes required")
    records = []
    with path.open(newline="", encoding="utf8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        color = [f"c{i:02}" for i in range(48)]
        vision = [f"v{i:03}" for i in range(768)]
        if len(fields) != 828 or not set(color + vision).issubset(fields):
            raise RuntimeError("Source HB feature schema changed")
        for row in reader:
            split = row["split"]
            # Reject unseen/old TEST rows before reading any of their features.
            if split not in ("train", "cal"):
                continue
            scene = int(row["scene_id"])
            label = row["label"]
            if row["source"] != "bop-hb-val-primesense-public-cc0" or \
               row["license"] != "CC0-1.0" or \
               row["modality"] != "REAL_RGB_MASKED":
                raise RuntimeError("Unlicensed source or invalid modality")
            if split == "train":
                if scene not in (5, 9) or label not in KNOWN:
                    raise RuntimeError("Unreviewed training identity or scene")
            else:
                if scene != 10 or label not in (*KNOWN, "UNKNOWN"):
                    raise RuntimeError("Unreviewed development labels/scenes")
            data = np.array([float(row[k]) for k in color + vision], dtype=np.float64)
            if not np.isfinite(data).all() or (data[:48] < 0).any() or (data[:48] > 1).any():
                raise RuntimeError("Invalid public numeric features")
            if not 0.999 < np.linalg.norm(data[48:]) < 1.001:
                raise RuntimeError("Unexpected revision-2 Vision embedding")
            records.append((split, scene, int(row["frame_id"]), label, data))
    train = [r for r in records if r[0] == "train"]
    cal = [r for r in records if r[0] == "cal"]
    if len(train) != 186 or len(cal) != 234 or \
       len(set(r[2] for r in cal)) != 48:
        raise RuntimeError("Original HB train/cal observation groups changed")
    return train, cal


def features(model, rows):
    x = np.stack([r[4] for r in rows])
    c = model["scaler"].transform(x[:, :48])
    v = model["pca"].transform(x[:, 48:])
    color_p = model["color"].predict_proba(c)[:, 1]
    vision_p = model["vision"].predict_proba(v)[:, 1]
    # Original known models only, no unknown labels used for these fits.
    sim = x[:, 48:] @ model["centroids"].T
    max_sim = sim.max(axis=1)
    diff_sim = np.abs(sim[:, 1] - sim[:, 0])
    c_conf = np.maximum(color_p, 1 - color_p)
    v_conf = np.maximum(vision_p, 1 - vision_p)
    meta = np.column_stack([
        c_conf, v_conf, max_sim, diff_sim, np.abs(color_p - vision_p),
        np.abs(vision_p - .5),
    ])
    if not np.isfinite(meta).all():
        raise RuntimeError("Invalid source-bound recognition/novelty features")
    return dict(color_p=color_p, vision_p=vision_p, max_sim=max_sim,
                meta=meta, known_guess=np.where(vision_p >= .5, "15", "12"),
                color_guess=np.where(color_p >= .5, "15", "12"))


def fit_known(train, seed):
    x = np.stack([r[4] for r in train])
    y = np.array([r[3] for r in train])
    scaler = StandardScaler().fit(x[:, :48])
    pca = PCA(n_components=16, svd_solver="full").fit(x[:, 48:])
    color = LogisticRegression(C=.65, max_iter=500, solver="liblinear",
                               class_weight="balanced", random_state=seed)
    vision = LogisticRegression(C=.35, max_iter=500, solver="liblinear",
                                class_weight="balanced", random_state=seed)
    color.fit(scaler.transform(x[:, :48]), y)
    vision.fit(pca.transform(x[:, 48:]), y)
    means = []
    for label in KNOWN:
        v = x[y == label, 48:].mean(axis=0)
        norm = np.linalg.norm(v)
        if norm <= 0:
            raise RuntimeError("Zero known-class centroid")
        means.append(v / norm)
    return dict(scaler=scaler, pca=pca, color=color, vision=vision,
                centroids=np.stack(means), train_sim_quantile=None)


def fit_unknown(model, fit_rows, seed):
    z = features(model, fit_rows)["meta"]
    y = np.array([1 if r[3] in KNOWN else 0 for r in fit_rows])
    if len(set(y)) != 2 or len(fit_rows) < 50:
        raise RuntimeError("Insufficient disjoint known/unknown fit groups")
    standardizer = StandardScaler().fit(z)
    clf = LogisticRegression(C=.3, max_iter=500, solver="liblinear",
                             class_weight="balanced", random_state=seed)
    clf.fit(standardizer.transform(z), y)
    forest = RandomForestClassifier(n_estimators=56, max_depth=4,
                                    min_samples_leaf=4, n_jobs=1,
                                    class_weight="balanced",
                                    random_state=seed+17)
    forest.fit(z, y)
    return standardizer, clf, forest


def stage_score(stage, inputs, trained):
    p_c = inputs["color_p"]
    p_v = inputs["vision_p"]
    v_conf = np.maximum(p_v, 1 - p_v)
    c_conf = np.maximum(p_c, 1 - p_c)
    sim = np.clip((inputs["max_sim"] + 1) / 2, 0, 1)
    linear = trained["unknown_logit"].predict_proba(
        trained["unknown_scaler"].transform(inputs["meta"]))[:, 1]
    forest = trained["unknown_forest"].predict_proba(inputs["meta"])[:, 1]
    if stage == 0:
        score = c_conf
        guess = inputs["color_guess"]
    elif stage == 1:
        score = v_conf
        guess = inputs["known_guess"]
    elif stage == 2:
        score = v_conf * sim
        guess = inputs["known_guess"]
    elif stage == 3:
        score = v_conf * linear
        guess = inputs["known_guess"]
    elif stage == 4:
        score = v_conf * forest
        guess = inputs["known_guess"]
    elif stage == 5:
        agree = (inputs["known_guess"] == inputs["color_guess"]).astype(float)
        score = v_conf * np.minimum(linear, forest) * agree * sim
        guess = inputs["known_guess"]
    else:
        raise ValueError("Six preregistered model corrections only")
    if not np.isfinite(score).all() or (score < 0).any() or (score > 1.001).any():
        raise RuntimeError("Invalid candidate safety score")
    return score, guess


def metrics(rows, score, guess, threshold):
    truth = np.array([r[3] for r in rows])
    if len(score) != len(rows) or len(guess) != len(rows):
        raise RuntimeError("Incorrect prediction shapes")
    admitted = score >= threshold
    right = admitted & (truth != "UNKNOWN") & (guess == truth)
    wrong = admitted & ~right
    return dict(n=len(rows), correctKnown=int(right.sum()),
                wrongAccepted=int(wrong.sum()),
                unknownAccepted=int((wrong & (truth == "UNKNOWN")).sum()),
                accepted=int(admitted.sum()),
                knownCount=int((truth != "UNKNOWN").sum()),
                unknownCount=int((truth == "UNKNOWN").sum()),
                threshold=float(threshold))


def calibrate(rows, score, guess, wrong_budget):
    if wrong_budget < 0:
        raise ValueError("No threshold may increase source risk")
    # Fixed source-independent grid; no DEV labels available here.
    thresholds = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75,
                  0.80, 0.85, 0.90, 0.95, 0.975, 0.99,
                  0.995, 0.999, 1.01)
    best = None
    budget = min(int(.05*len(rows)), wrong_budget)
    for t in thresholds:
        m = metrics(rows, score, guess, t)
        if m["wrongAccepted"] > budget:
            continue
        key = (m["correctKnown"], -m["wrongAccepted"], t)
        if best is None or key > best[0]:
            best = (key, m)
    if best is None:
        raise RuntimeError("Risk budget missing the abstain fallback")
    return best[1]


def evaluate(source_root: Path, expected_head: str, fold: int, output: Path) -> dict:
    if fold not in range(6) or len(expected_head) != 40 or \
       any(c not in "0123456789abcdef" for c in expected_head):
        raise RuntimeError("Full source HEAD/fold admission required")
    head = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True, timeout=20).stdout.strip()
    if head != expected_head:
        raise RuntimeError("Source checkout SHA changed")
    train, cal = dataset(source_root / SOURCE_FILE)
    groups = sorted({r[2] for r in cal})
    # PR205 used original simple group slices. This uses new fixed permutation,
    # yet these are already-exposed same-scene DEVELOPMENT labels.
    rng = np.random.default_rng(2026111500)
    shuffled = rng.permutation(groups).tolist()
    dev = set(shuffled[fold*8:(fold+1)*8])
    remain = [x for x in shuffled if x not in dev]
    fit_groups = set(remain[:28])
    safe_groups = set(remain[28:])
    if len(dev) != 8 or len(fit_groups) != 28 or len(safe_groups) != 12 or \
       (dev & fit_groups) or (dev & safe_groups) or (fit_groups & safe_groups):
        raise RuntimeError("Frame group leakage")
    fit_rows = [r for r in cal if r[2] in fit_groups]
    safety_rows = [r for r in cal if r[2] in safe_groups]
    dev_rows = [r for r in cal if r[2] in dev]
    if not fit_rows or not safety_rows or not dev_rows:
        raise RuntimeError("Empty independent model development partition")
    known = fit_known(train, seed=202611151 + fold)
    u_scaler, u_logit, u_forest = fit_unknown(known, fit_rows, seed=202611151 + fold)
    fitted = dict(known=known, unknown_scaler=u_scaler,
                  unknown_logit=u_logit, unknown_forest=u_forest)
    safety_in = features(known, safety_rows)
    # DEV features are not selected on until after all six correction stages.
    champion = dict(stage=-1, method="abstain_all", threshold=1.01,
                    correctKnown=0, wrongAccepted=0)
    trace = []
    for stage, name in enumerate(METHODS):
        scores, guesses = stage_score(stage, safety_in, fitted)
        candidate = calibrate(safety_rows, scores, guesses, champion["wrongAccepted"])
        updated = (candidate["correctKnown"] > champion["correctKnown"] and
                   candidate["wrongAccepted"] <= champion["wrongAccepted"])
        if updated:
            champion = dict(stage=stage, method=name, **candidate)
        if champion["wrongAccepted"] != 0:
            raise RuntimeError("Unknown-risk feedback accepted worse-than-baseline wrongs")
        trace.append(dict(stage=stage+1, method=name, candidateCal=candidate,
                          changedChampion=bool(updated),
                          resultingChampion=champion["method"],
                          resultingWrongBudget=champion["wrongAccepted"]))
    dev_inputs = features(known, dev_rows)
    if champion["stage"] == -1:
        dev_result = dict(n=len(dev_rows), correctKnown=0, wrongAccepted=0,
                          unknownAccepted=0, accepted=0,
                          knownCount=sum(r[3] in KNOWN for r in dev_rows),
                          unknownCount=sum(r[3] == "UNKNOWN" for r in dev_rows),
                          threshold=1.01)
    else:
        scores, guesses = stage_score(champion["stage"], dev_inputs, fitted)
        dev_result = metrics(dev_rows, scores, guesses, champion["threshold"])
    report = dict(
        schema="junction.chibi-lens.six-new-ood-ml.v1", workId=WORK_ID,
        exactSourceHEAD=head, approvedPublicSourceCSVsha256=SOURCE_CSV_SHA,
        fold=fold, trainPhysicalScenes=[5,9], developmentPhysicalScene=10,
        excludedPreviouslySeenPhysicalScenes=[8,11],
        trainingKnownRows=len(train), unknownTrainingRows=len(fit_rows),
        safetyCalibrationRows=len(safety_rows), developmentRows=len(dev_rows),
        fitFrameGroups=len(fit_groups), calibrationFrameGroups=len(safe_groups),
        devFrameGroups=sorted(dev),
        sourceTrust="CC0-1.0 numerical features only, self-reported source metadata",
        modelsFitted=4,
        sixDistinctLearningMethods=list(METHODS),
        sixSequentialFeedbackStages=trace,
        selectedDevelopmentChampion=champion,
        internalDevelopmentOnly=dev_result,
        productFieldQualification=False, modelPromoted=False,
        privateImagesUploaded=False, realDeviceIdentityVerified=False,
        providerAttestationAvailable=False, actualProviderBillEur=None,
        limitations=[
            "Same physical scene10 previously exposed in older research, not independent field testing",
            "Train-only known class12/15 source scenes5+9, source cal scene10 unknowns used for development model fitting",
            "No raw images or full-frame object detection, only GT-derived ROI public numerical features",
            "Six new semantic models, NOT six independent camera domains or real Meta glasses approval",
        ],
    )
    if output.exists():
        raise RuntimeError("Refuse overwrite existing source-bound output")
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    with (output / "trained-models.pkl").open("xb") as f:
        # Python pickle is research-only, never load from untrusted sources.
        pickle.dump({"sourceHEAD":head,"champion":champion,
                     "known":known, "unknown_scaler":u_scaler,
                     "unknown_logit":u_logit,"unknown_forest":u_forest},
                    f, protocol=4)
    report["weightsSHA256"] = sha_file(output / "trained-models.pkl")
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root",type=Path,required=True)
    ap.add_argument("--expected-head",required=True)
    ap.add_argument("--fold",type=int,choices=range(6),required=True)
    ap.add_argument("--out",type=Path,required=True)
    a = ap.parse_args()
    r = evaluate(a.source_root,a.expected_head,a.fold,a.out)
    print(json.dumps({"fold":a.fold,"MLfits":r["modelsFitted"],"stages":6,
                      "champion":r["selectedDevelopmentChampion"]["method"],
                      "devRight":r["internalDevelopmentOnly"]["correctKnown"],
                      "devWrong":r["internalDevelopmentOnly"]["wrongAccepted"],
                      "fieldQualified":False},sort_keys=True))


if __name__ == "__main__":
    main()
