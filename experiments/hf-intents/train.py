#!/usr/bin/env python3
"""Bounded CPU intent-model search. The training commands never open test data."""

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time
import unicodedata

DATASETS = {"banking77": ("text", "label", 77), "massive-fi-FI": ("utt", "intent", 60)}
LANES = ("word_svm", "char_svm", "hybrid_linear", "complement_nb", "svd_mlp")
HARD_CUTOFF = dt.datetime(2026, 11, 15, 16, 40, tzinfo=dt.timezone.utc).timestamp()
PROTOCOL_VERSION = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical(value) + b"\n")
    os.replace(temporary, path)


def normalized_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def cutoff_timestamp(value):
    when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if when.tzinfo is None or when.utcoffset() != dt.timedelta(0):
        raise ValueError("cutoff must be an explicit UTC timestamp")
    return min(when.timestamp(), HARD_CUTOFF)


def require_time(cutoff, seconds, now=None):
    now = time.time() if now is None else now
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("seconds must be positive and finite")
    if cutoff <= now:
        raise ValueError("training cutoff reached")
    return min(cutoff, now + seconds)


def read_parquet(path, dataset):
    import pyarrow.parquet as pq

    text_column, label_column, expected_labels = DATASETS[dataset]
    table = pq.read_table(path, columns=[text_column, label_column])
    metadata = json.loads(table.schema.metadata[b"huggingface"])
    names = metadata["info"]["features"][label_column]["names"]
    if not isinstance(names, list) or len(names) != expected_labels or len(set(names)) != len(names):
        raise ValueError("unexpected declared label vocabulary")
    texts, labels = table[text_column].to_pylist(), table[label_column].to_pylist()
    if not texts or any(not isinstance(text, str) or not normalized_text(text) for text in texts):
        raise ValueError("empty or invalid text")
    if any(type(label) is not int or not 0 <= label < len(names) for label in labels):
        raise ValueError("invalid label")
    return texts, labels, names


def split_data(data_dir, dataset):
    """Use a fixed outer validation set; all duplicate groups stay together."""
    from sklearn.model_selection import StratifiedGroupKFold

    directory = Path(data_dir)
    texts, labels, names = read_parquet(directory / "train.parquet", dataset)
    groups = [normalized_text(text) for text in texts]
    source_hashes = {"train": digest_file(directory / "train.parquet")}
    removed = 0
    if dataset == "massive-fi-FI":
        val_texts, val_labels, val_names = read_parquet(directory / "validation.parquet", dataset)
        if names != val_names:
            raise ValueError("training/validation vocabularies differ")
        held_out = {normalized_text(text) for text in val_texts}
        keep = [i for i, group in enumerate(groups) if group not in held_out]
        removed = len(texts) - len(keep)
        texts, labels = [texts[i] for i in keep], [labels[i] for i in keep]
        validation_kind = "official-validation; exact normalized overlaps excluded from training"
        source_hashes["validation"] = digest_file(directory / "validation.parquet")
    else:
        if len(set(groups)) < 5:
            raise ValueError("insufficient normalized text groups for fixed validation split")
        splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=20261115)
        train_indices, val_indices = next(splitter.split(texts, labels, groups))
        val_texts, val_labels = [texts[i] for i in val_indices], [labels[i] for i in val_indices]
        texts, labels = [texts[i] for i in train_indices], [labels[i] for i in train_indices]
        validation_kind = "fixed first fold of stratified grouped 5-fold split, seed 20261115"
    training_groups = [normalized_text(text) for text in texts]
    if set(training_groups) & {normalized_text(text) for text in val_texts}:
        raise ValueError("normalized-text leakage across training and validation")
    if len(set(labels)) < 2 or len(set(training_groups)) < 2:
        raise ValueError("insufficient training classes/groups")
    return {
        "texts": texts, "labels": labels, "groups": training_groups,
        "validation_texts": val_texts, "validation_labels": val_labels, "label_names": names,
        "protocol": {"version": PROTOCOL_VERSION, "validation": validation_kind,
                     "normalization": "NFKC + casefold + whitespace collapse",
                     "overlapping_training_rows_removed": removed,
                     "source_sha256": source_hashes,
                     "test_data_opened": False,
                     "lane_selection": "grouped training-CV mean macro-F1 only",
                     "outer_validation_usage": "final family selection only; not candidate selection"},
    }


def configuration(dataset, lane, trial):
    seed = int.from_bytes(hashlib.sha256(f"{dataset}:{lane}:{trial}".encode()).digest()[:4], "big")
    rng = random.Random(seed)
    config = {"seed": seed, "min_df": 1 if trial == 0 else rng.choice([1, 2, 3]),
              "sublinear_tf": True if trial == 0 else rng.choice([False, True]),
              "word_max_features": 10000 if trial == 0 else rng.choice([20000, 40000, 70000]),
              "char_max_features": 10000 if trial == 0 else rng.choice([30000, 50000, 80000]),
              "word_ngram_max": 2 if trial == 0 else rng.choice([1, 2, 3]),
              "char_ngram_min": 3 if trial == 0 else rng.choice([2, 3, 4]),
              "char_ngram_max": 5 if trial == 0 else rng.choice([5, 6, 7]),
              "regularization": 1.0 if trial == 0 else 10 ** rng.uniform(-2, 1.5),
              "alpha": 0.5 if trial == 0 else 10 ** rng.uniform(-3, 1),
              "svd_components": 8 if trial == 0 else rng.choice([32, 64, 128, 256]),
              "hidden_units": 32 if trial == 0 else rng.choice([64, 128, 256]),
              "mlp_iterations": 25 if trial == 0 else rng.choice([80, 120, 180]),
              "learning_rate": 0.001 if trial == 0 else 10 ** rng.uniform(-4, -2),
              "lane": lane}
    if lane == "svd_mlp":
        # Bound the dense SVD projection itself, not merely its output dimension.
        config["word_max_features"] = min(config["word_max_features"], 20000)
        config["char_max_features"] = min(config["char_max_features"], 30000)
    if lane == "complement_nb":
        config["word_max_features"] = min(config["word_max_features"], 50000)
    return config


def model_for(config, training_rows):
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import ComplementNB
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import LinearSVC

    common = {"min_df": config["min_df"], "sublinear_tf": config["sublinear_tf"], "dtype": "float32"}
    # numpy's type object is understood by skops; dtype strings are not accepted by sklearn here.
    import numpy as np
    common["dtype"] = np.float32
    word = TfidfVectorizer(ngram_range=(1, config["word_ngram_max"]),
                          max_features=config["word_max_features"], **common)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(config["char_ngram_min"], config["char_ngram_max"]),
                          max_features=config["char_max_features"], **common)
    lane = config["lane"]
    if lane in ("word_svm", "char_svm"):
        return Pipeline([("features", word if lane == "word_svm" else char),
                         ("classifier", LinearSVC(C=config["regularization"], dual="auto", max_iter=3000,
                                                  random_state=config["seed"]))])
    if lane == "complement_nb":
        return Pipeline([("features", word), ("classifier", ComplementNB(alpha=config["alpha"]))])
    features = FeatureUnion([("word", word), ("char", char)])
    if lane == "hybrid_linear":
        return Pipeline([("features", features),
                         ("classifier", LogisticRegression(C=config["regularization"], max_iter=500,
                                                            random_state=config["seed"]))])
    components = min(config["svd_components"], max(2, training_rows // 10))
    return Pipeline([("features", features),
                     ("svd", TruncatedSVD(n_components=components, random_state=config["seed"])),
                     ("scale", StandardScaler()),
                     ("classifier", MLPClassifier(hidden_layer_sizes=(config["hidden_units"],),
                                                   alpha=config["alpha"] * 0.001,
                                                   learning_rate_init=config["learning_rate"],
                                                   max_iter=config["mlp_iterations"], early_stopping=False,
                                                   random_state=config["seed"]))])


def metric_report(truth, predictions, names):
    from sklearn.metrics import accuracy_score, classification_report, f1_score

    present = sorted(set(truth))
    return {"accuracy": float(accuracy_score(truth, predictions)),
            "macro_f1_observed": float(f1_score(truth, predictions, labels=present, average="macro", zero_division=0)),
            "macro_f1_all_labels": float(f1_score(truth, predictions, labels=list(range(len(names))), average="macro", zero_division=0)),
            "rows": len(truth), "observed_classes": present,
            "absent_classes": [i for i in range(len(names)) if i not in present],
            "per_class": classification_report(truth, predictions, labels=list(range(len(names))),
                                                target_names=names, output_dict=True, zero_division=0)}


def candidate(args):
    require_time(min(args.deadline, HARD_CUTOFF), 1)
    import numpy as np
    import skops.io as sio
    from joblib import parallel_config
    from sklearn.metrics import f1_score, make_scorer
    from sklearn.model_selection import StratifiedGroupKFold, cross_val_score

    data = json.loads(Path(args.prepared).read_text())
    config = json.loads(Path(args.config).read_text())
    model = model_for(config, len(data["texts"]))
    class_groups = collections.defaultdict(set)
    for label, group in zip(data["labels"], data["groups"]):
        class_groups[label].add(group)
    minimum = min(map(len, class_groups.values()))
    folds = min(5, len(set(data["groups"])), max(2, minimum))
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=20261115)
    splits = list(splitter.split(data["texts"], data["labels"], data["groups"]))
    for training, validation in splits:
        if {data["groups"][i] for i in training} & {data["groups"][i] for i in validation}:
            raise ValueError("CV normalized-text group leakage")
    scorer = make_scorer(f1_score, average="macro", zero_division=0)
    with parallel_config(backend="loky", inner_max_num_threads=2):
        scores = cross_val_score(model, data["texts"], data["labels"], cv=splits,
                                 scoring=scorer, n_jobs=min(4, folds), error_score="raise")
    mean = float(np.mean(scores))
    if not math.isfinite(mean):
        raise ValueError("nonfinite CV score")
    result = {"cv_macro_f1": mean, "cv_fold_scores": [float(score) for score in scores],
              "cv_folds": folds, "config": config, "new_best": mean > args.best + 1e-12}
    if result["new_best"]:
        model.fit(data["texts"], data["labels"])
        predictions = model.predict(data["validation_texts"])
        validation = metric_report(data["validation_labels"], predictions, data["label_names"])
        result.update({"validation_macro_f1": validation["macro_f1_observed"], "validation_metrics": validation})
        if config["lane"] == "svd_mlp":
            # The Adam optimizer is training-only and is not an approved skops load type.
            # We resume model search, never partial-fit this optimizer; export inference weights only.
            del model.named_steps["classifier"]._optimizer
        output = Path(args.model)
        sio.dump(model, output)
        if output.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("candidate model exceeds the 100 MiB cloud member bound")
        if sio.get_untrusted_types(file=output):
            raise ValueError("checkpoint requires unapproved serialized types")
        # Exercise the same safe loader used by final evaluation before preserving the checkpoint.
        restored = sio.load(output, trusted=[])
        if list(restored.predict(data["validation_texts"])) != list(predictions):
            raise ValueError("safe reload changed predictions")
        result["model_sha256"] = digest_file(output)
    atomic_json(args.result, result)


def validate_checkpoint(out, identity=None):
    out = Path(out)
    metadata = out / "best.json"
    model = out / "best.skops"
    if not metadata.exists() and not model.exists():
        return None
    if not metadata.is_file() or not model.is_file():
        raise ValueError("incomplete checkpoint")
    if metadata.is_symlink() and metadata.resolve().parent != model.resolve().parent:
        raise ValueError("checkpoint pointers disagree")
    value = json.loads(metadata.read_text())
    if value["model_sha256"] != digest_file(model):
        raise ValueError("checkpoint model checksum mismatch")
    if identity and any(value.get(key) != val for key, val in identity.items()):
        raise ValueError("checkpoint source identity mismatch")
    return value


def publish_checkpoint(out, model, metadata):
    """Immutable pair + atomic pointer retains the previous pair on interruption."""
    out = Path(out)
    checkpoint = out / "checkpoints" / f"trial-{metadata['trial']:06d}"
    checkpoint.mkdir(parents=True, exist_ok=False)
    os.replace(model, checkpoint / "best.skops")
    atomic_json(checkpoint / "best.json", metadata)
    for name in ("best.skops", "best.json"):
        link = out / name
        if link.exists() and not link.is_symlink():
            # Cloud archives restore a regular pair; preserve it before establishing pointers.
            restored = out / "restored"
            restored.mkdir(exist_ok=True)
            os.replace(link, restored / name)
        if not link.is_symlink():
            link.symlink_to(Path("current") / name)
    temporary = out / f".current-{os.getpid()}"
    temporary.symlink_to(checkpoint.relative_to(out), target_is_directory=True)
    os.replace(temporary, out / "current")


def history_rows(out):
    path = Path(out) / "history.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError("corrupt trial history") from error
    return rows


def append_history(out, row):
    with (Path(out) / "history.jsonl").open("a") as file:
        file.write(canonical(row).decode() + "\n")
        file.flush()
        os.fsync(file.fileno())


def run(args):
    # Deliberately before importing numpy, sklearn, pyarrow, or opening data.
    deadline = require_time(cutoff_timestamp(args.cutoff), args.seconds)
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha) or not re.fullmatch(r"[0-9]+", args.run_id):
        raise ValueError("exact source SHA and numeric GitHub run ID required")
    if not 1 <= args.max_trials <= 10000:
        raise ValueError("max-trials must be in 1..10000")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    identity = {"dataset": args.dataset, "lane": args.lane, "source_sha": args.source_sha, "run_id": args.run_id}
    best = validate_checkpoint(out, identity)
    data = split_data(args.data_dir, args.dataset)
    prepared_hash = hashlib.sha256(canonical(data)).hexdigest()
    identity["prepared_sha256"] = prepared_hash
    if best and best.get("prepared_sha256") != prepared_hash:
        raise ValueError("checkpoint training inputs/protocol changed")
    state_path = out / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if any(state.get(key) != value for key, value in identity.items()):
            raise ValueError("resume state identity mismatch")
    rows = history_rows(out)
    if any(any(row.get(key) != value for key, value in identity.items()) for row in rows):
        raise ValueError("history identity mismatch")
    # An interrupted publication can leave an immutable directory before history/state append.
    # Never overwrite that evidence or repeat its configuration after resuming.
    attempted = [int(path.name[6:]) for path in (out / "checkpoints").glob("trial-*")
                 if re.fullmatch(r"trial-[0-9]{6}", path.name)]
    trial = max([row["trial"] for row in rows] + ([best["trial"]] if best else []) + attempted + [-1]) + 1
    prepared_path = out / "prepared.json"
    atomic_json(prepared_path, data)
    while trial < args.max_trials and deadline - time.time() > 3:
        config = configuration(args.dataset, args.lane, trial)
        config_path, result_path, model_path = out / "candidate-config.json", out / "candidate-result.json", out / "candidate.skops"
        atomic_json(config_path, config)
        if result_path.exists():
            result_path.unlink()
        if model_path.exists():
            model_path.unlink()
        start = time.time()
        child_deadline = min(deadline - 1, start + 1200)
        command = [sys.executable, str(Path(__file__).resolve()), "_candidate", "--prepared", str(prepared_path),
                   "--config", str(config_path), "--result", str(result_path), "--model", str(model_path),
                   "--best", str(best["cv_macro_f1"] if best else -1), "--deadline", str(child_deadline)]
        # Training receives no publication credential. Public data/model code is the only workload here.
        env = {key: value for key, value in os.environ.items()
               if key not in {"GH_TOKEN", "GITHUB_TOKEN"} and not key.startswith("ACTIONS_")}
        log_path = out / "candidate.log"
        row = dict(identity, trial=trial, config=config, started_at=start)
        with log_path.open("w") as log:
            child = subprocess.Popen(command, stdout=log, stderr=log, env=env, start_new_session=True)
            try:
                code = child.wait(timeout=max(0.1, child_deadline - time.time()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait(timeout=5)
                code = None
        row["elapsed_seconds"] = time.time() - start
        if code == 0:
            result = json.loads(result_path.read_text())
            row.update(result, status="completed")
            if result["new_best"]:
                if result["model_sha256"] != digest_file(model_path):
                    raise ValueError("candidate checksum mismatch")
                metadata = dict(identity, trial=trial, config=config,
                                cv_macro_f1=result["cv_macro_f1"], cv_fold_scores=result["cv_fold_scores"],
                                validation_macro_f1=result["validation_macro_f1"], validation_metrics=result["validation_metrics"],
                                model_sha256=result["model_sha256"], training_rows=len(data["texts"]),
                                validation_rows=len(data["validation_texts"]), label_names=data["label_names"],
                                protocol=data["protocol"], selected_at=dt.datetime.now(dt.timezone.utc).isoformat())
                publish_checkpoint(out, model_path, metadata)
                best = validate_checkpoint(out, identity)
        else:
            row.update(status="timeout" if code is None else "failed", exit_code=code)
            # Preserve bounded diagnostics without allowing a bad candidate to replace a valid model.
            row["diagnostic_tail"] = log_path.read_text(errors="replace")[-3000:]
        append_history(out, row)
        atomic_json(state_path, dict(identity, next_trial=trial + 1))
        print(json.dumps({"trial": trial, "status": row["status"], "best_cv_macro_f1": best["cv_macro_f1"] if best else None}), flush=True)
        trial += 1
    print(json.dumps({"status": "checkpoint-ready" if best else "no-completed-model", "next_trial": trial,
                      "cutoff_reached": time.time() >= cutoff_timestamp(args.cutoff)}), flush=True)
    return 0 if best else 2


def evaluate(args):
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha) or not re.fullmatch(r"[0-9]+", args.run_id):
        raise ValueError("exact source SHA and numeric GitHub run ID required")
    output = Path(args.out)
    if not output.exists():
        require_time(dt.datetime(2026, 11, 15, 17, tzinfo=dt.timezone.utc).timestamp(), 1)
    model_path = Path(args.model)
    metadata = json.loads(model_path.with_name("best.json").read_text())
    model_digest = digest_file(model_path)
    if (metadata.get("dataset") != args.dataset or metadata.get("model_sha256") != model_digest
            or metadata.get("source_sha") != args.source_sha or metadata.get("run_id") != args.run_id):
        raise ValueError("evaluation checkpoint identity/checksum mismatch")
    binding = {"dataset": args.dataset, "lane": metadata["lane"], "source_sha": args.source_sha,
               "run_id": args.run_id, "model_sha256": model_digest,
               "test_sha256": digest_file(Path(args.data_dir) / "test.parquet")}
    if output.exists():
        receipt = json.loads(output.read_text())
        if any(receipt.get(key) != value for key, value in binding.items()):
            raise ValueError("existing evaluation receipt identity/checksum mismatch")
        for key in ("accuracy", "macro_f1_observed", "macro_f1_all_labels"):
            value = receipt.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("existing evaluation receipt has invalid metrics")
        if type(receipt.get("rows")) is not int or receipt["rows"] <= 0:
            raise ValueError("existing evaluation receipt has invalid row count")
        print(json.dumps({"status": "existing-receipt-reused", **binding}), flush=True)
        return 0
    import skops.io as sio

    if sio.get_untrusted_types(file=model_path):
        raise ValueError("unapproved serialized model types")
    model = sio.load(model_path, trusted=[])
    texts, labels, names = read_parquet(Path(args.data_dir) / "test.parquet", args.dataset)
    if metadata["label_names"] != names:
        raise ValueError("test/model label vocabulary mismatch")
    result = metric_report(labels, model.predict(texts), names)
    result.update(binding, test_usage="single held-out evaluation after validation-only family selection")
    atomic_json(args.out, result)
    print(json.dumps({key: result[key] for key in ("dataset", "accuracy", "macro_f1_observed", "rows")}), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    training = sub.add_parser("run")
    training.add_argument("--dataset", choices=DATASETS, required=True)
    training.add_argument("--lane", choices=LANES, required=True)
    for name in ("data-dir", "out", "cutoff", "source-sha", "run-id"):
        training.add_argument("--" + name, required=True)
    training.add_argument("--seconds", type=float, required=True)
    training.add_argument("--max-trials", type=int, default=10000)
    scoring = sub.add_parser("evaluate")
    scoring.add_argument("--dataset", choices=DATASETS, required=True)
    for name in ("model", "data-dir", "out", "source-sha", "run-id"):
        scoring.add_argument("--" + name, required=True)
    internal = sub.add_parser("_candidate", help=argparse.SUPPRESS)
    for name in ("prepared", "config", "result", "model"):
        internal.add_argument("--" + name, required=True)
    internal.add_argument("--best", type=float, required=True)
    internal.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        return candidate(args) if args.command == "_candidate" else (run(args) if args.command == "run" else evaluate(args))
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
