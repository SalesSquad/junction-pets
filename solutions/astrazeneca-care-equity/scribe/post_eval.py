"""Checks added after review of the first evaluation. SYNTHETIC data only; research artefact,
not a medical device, not for clinical use.

Reads the stored predictions (no model is loaded here) and writes data/scribe/post-eval-v1.json:

  selective            a confidence threshold FIXED ON THE VALIDATION NOTES, then applied once to the
                       test notes and to the Haiku-written notes, with exact one-sided upper bounds on
                       the error among admitted notes. The first evaluation chose and scored its
                       thresholds on the same test notes; that is reported next to it for comparison.
  adapter_all_test     the adapter on all 500 test notes (the first evaluation scored 200).
  pathway_order_check  how many ground-truth episodes break the pathway order of DATA_COLLECTION.md
                       section 1 (eventlog/schema.py), and the scores without them.
  split_overlap        test notes whose event list also occurs in a training note with another route.
  dedup_report         what the first-row-wins de-duplication of build_dataset.py dropped.

Run: scribe/.venv/bin/python scribe/post_eval.py
"""

import collections
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from metrics import summary, wilson  # noqa: E402

DATA = ROOT / "data/scribe"
EVAL = HERE / "artifacts/mlx-eval"
LIMITS = (0.01, 0.05)


def binom_cdf(k, n, p):
    if k < 0:
        return 0.0
    if k >= n or p <= 0:
        return 1.0
    if p >= 1:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    return min(1.0, sum(math.exp(math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) + j * lp + (n - j) * lq) for j in range(k + 1)))


def upper_bound(errors, n, alpha=0.05):
    """Exact (Clopper-Pearson) one-sided upper bound on an error rate: the largest rate still
    compatible, at level alpha, with seeing this few errors in n notes."""
    if n == 0:
        return None
    if errors >= n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if binom_cdf(errors, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def notes_needed_for(limit, alpha=0.05):
    """Admitted notes without a single error needed before an error rate <= limit can be claimed
    at confidence 1 - alpha: the smallest n with 1 - alpha^(1/n) <= limit."""
    return math.ceil(math.log(alpha) / math.log(1 - limit))


def read_jsonl(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines() if x.strip()]


def is_relative(row):
    return bool({"days", "weeks"} & set(row.get("date_forms", [])))


def correct(row, pred):
    return pred == json.loads(row["target_json"])


def threshold_from(scores, outcomes, limit):
    """Lowest score t such that the notes with score >= t have an error rate <= limit and no larger
    admitted set does (ties admitted together). None when no admitted set qualifies."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    best, err = None, 0
    for pos, i in enumerate(order, 1):
        err += not outcomes[i]
        if pos < len(order) and scores[order[pos]] == scores[i]:
            continue
        if err / pos <= limit:
            best = scores[i]
    return best


def apply_threshold(rows, scores, outcomes, t):
    if t is None:
        return {"admitted": 0, "n": len(rows), "note": "no threshold qualified on the validation notes"}
    idx = [i for i, s in enumerate(scores) if s >= t]
    errors = sum(not outcomes[i] for i in idx)
    return {
        "n": len(rows),
        "admitted": len(idx),
        "coverage": wilson(len(idx), len(rows)),
        "errors_among_admitted": errors,
        "error_rate_among_admitted": errors / len(idx) if idx else None,
        "error_upper_bound_95_one_sided": upper_bound(errors, len(idx)),
        "admitted_with_relative_date": sum(is_relative(rows[i]) for i in idx),
        "notes_with_relative_date": sum(is_relative(r) for r in rows),
    }


def slim(s):
    return {k: v for k, v in s.items() if k not in ("date_errors_days", "date_error_histogram", "date_error_distribution", "outcomes", "f1_interval_note")}


def order_violations(events, order):
    """Pairs (a, b) with a before b in the pathway order but dated after it."""
    pairs = []
    for i, a in enumerate(events):
        for b in events[i + 1 :]:
            x, y = (a, b) if order[a["type"]] < order[b["type"]] else (b, a)
            if order[x["type"]] != order[y["type"]] and x["date"] > y["date"]:
                pairs.append(f"{x['type']} dated after {y['type']}")
    return pairs


def sampler_swaps():
    """Type pairs that scribe/sample.py orders one way and eventlog/schema.py the other."""
    import itertools

    from sample import TYPES

    from eventlog.schema import EVENT_TYPES

    return [[a, b] for a, b in itertools.combinations(TYPES, 2) if EVENT_TYPES.index(a) > EVENT_TYPES.index(b)]


def crossing_splits(split_rows):
    """How many ids, targets (route and events) and note texts occur in more than one of the given splits."""
    out = {}
    for name, field in (("ids", "id"), ("targets", "target_json"), ("note_texts", "note_text")):
        seen = collections.defaultdict(set)
        for split, rows in split_rows.items():
            for r in rows:
                seen[r[field]].add(split)
        out[name] = sum(len(s) > 1 for s in seen.values())
    return out


def validator_order_check(rows):
    """Run the eventlog validator (eventlog/validate.py) over ground-truth episodes, as it would see them.

    Each row's target becomes pathway_events rows: event type, date and precision from the target, entry
    route from the target. County, cancer site, age band and source are fixed placeholder values from the
    allowed enumerations; the order check does not read them. Returns what order='flag' reports and whether
    order='strict' (the mode for simulator output) would accept the file."""
    import datetime as dt

    import pyarrow as pa

    from eventlog.schema import pathway_events
    from eventlog.validate import validate

    recs = []
    for i, r in enumerate(rows):
        t = json.loads(r["target_json"])
        for e in t["events"]:
            recs.append({"episode_id": r.get("id") or str(i), "event_type": e["type"], "event_date": dt.date.fromisoformat(e["date"]),
                         "date_precision": e["precision"], "county": "HVA01", "entry_route": t["entry_route"], "cancer_site": "other",
                         "age_band": "50-54", "source": "TEXT_EXTRACTED", "extraction_confidence": None, "verified_by_human": False, "synthetic": True})
    table = pa.Table.from_pylist(recs, schema=pathway_events)
    flag = validate(table, order="flag")
    return {"episodes": len(rows), "episodes_flagged": flag.episodes_with_reversed_pair, "flagged_ids": flag.flagged_for_review,
            "reversed_neighbour_pairs": flag.reversed_by_pair, "schema_errors": flag.schema_errors, "enum_errors": flag.enum_errors,
            "strict_mode_valid": validate(table, order="strict").valid}


def ground_truth_order(split_rows):
    """Ground-truth episodes against the pathway order of DATA_COLLECTION.md section 1 (eventlog/schema.py):
    every pair of events dated against that order, and what the eventlog validator flags. split_rows maps a
    split name to its rows (each with target_json)."""
    from eventlog.schema import EVENT_TYPES, PATHWAY_ORDER

    order = {k: i for i, k in enumerate(EVENT_TYPES)}
    bad = {}
    for name, rows in split_rows.items():
        bad[name] = {}
        for i, r in enumerate(rows):
            pairs = order_violations(json.loads(r["target_json"])["events"], order)
            if pairs:
                bad[name][r.get("id") or str(i)] = pairs
    validator = {}
    for name, rows in split_rows.items():
        v = validator_order_check(rows)
        v["same_episodes_as_pair_check"] = set(v.pop("flagged_ids")) == set(bad[name])
        validator[name] = v
    return PATHWAY_ORDER, bad, validator


def validator_sentence(o):
    """One sentence on what eventlog/validate.py reports for the accepted splits, from pathway_order_check."""
    v = (o.get("eventlog_validator") or {}).get("by_split")
    if not v:
        return "The eventlog validator was not run on these episodes."
    acc = ("train", "val", "test")
    flagged, total = sum(v[k]["episodes_flagged"] for k in acc), sum(v[k]["episodes"] for k in acc)
    same = all(v[k]["same_episodes_as_pair_check"] for k in v)
    strict = [k for k in acc if not v[k]["strict_mode_valid"]]
    return (f"Run on the ground truth, `eventlog/validate.py` flags {flagged} of {total} accepted episodes"
            f"{' (the same episodes)' if same else ' (not exactly the same episodes)'}, and in its strict mode for simulator output it rejects "
            f"{'every split file' if len(strict) == len(acc) else ', '.join(strict) or 'no split file'}.")


def audit_line():
    a = json.loads((DATA / "audit-summary.json").read_text())["strata"]["True"]
    return f"{a['strict_disagreements']} of {a['sampled']}"


def write_errata(out):
    """data/scribe/dataset-v1/ERRATA.md: defects of the frozen dataset found after it was built.
    The dataset itself is not changed, because an adapter was trained and scored on it."""
    o, v, d = out["pathway_order_check"], out["split_overlap"], out["dedup_report"]
    prov_path = DATA / "provenance-v1.json"
    prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
    e, n = o["episodes_with_reversed_pair"], o["episodes"]
    L = ["# Errata for SAMA pathway scribe dataset v1", "",
         "SYNTHETIC ONLY. Written by `scribe/post_eval.py` from the dataset files; the counts are computed, not typed.",
         "The dataset is left as built: an adapter was trained and evaluated on exactly these files.", "",
         "1. **Pathway order.** The card says the event types come from `DATA_COLLECTION.md`. The sampler (`scribe/sample.py`) uses an older order, which puts "
         + "; ".join(f"`{a}` before `{b}`" for a, b in o["sampler_order_differs_on"]) + f". Against the documented order (`{o['documented_order']}`) "
         f"{o['accepted_episodes_with_reversed_pair']} of {o['accepted_episodes']} accepted episodes contain a reversed pair: {e['train']} of {n['train']} training, {e['val']} of {n['val']} validation, "
         f"{e['test']} of {n['test']} test. " + validator_sentence(o),
         f"2. **Split by route plus events.** The split hash includes the entry route, so {v['test_notes_sharing_an_event_list_with_a_training_note']} test note(s) and "
         f"{v['val_notes_sharing_an_event_list_with_a_training_note']} validation note(s) have exactly the event list of a training note with another route. "
         + ("No id, target or note text occurs in more than one split." if not any(v["crossing_splits"].values())
            else "Occurring in more than one split: " + ", ".join(f"{k} {n_}" for k, n_ in v["crossing_splits"].items()) + ".")]
    if "ids_occurring_more_than_once" in d:
        L.append(f"3. **De-duplication.** The first cached row of an id was kept whatever its verdict. Of {d['ids_occurring_more_than_once']} ids that occur more than once, "
                 f"{d['first_row_rejected_and_a_later_row_accepted']} had a rejected first row and an accepted later one (the accepted note was dropped and the id filed under rejected), "
                 f"and in {d['first_row_accepted_and_another_accepted_row_dropped']} a second accepted note was dropped.")
    else:
        L.append("3. **De-duplication.** The first cached row of an id was kept whatever its verdict; the cache is not present here, so the count was not recomputed.")
    if prov:
        c, ver, t = prov["cost"], prov["verifier"], prov["teacher"]
        L += [f"4. **Cost field.** `typesafe_cost_usd` ({c['typesafe_cost_usd_in_dataset_card']}) under \"Measured\" is {c['how']}. Price source: {c['price_source']}.",
              f"5. **Verifier version.** All {ver['calls']:,} verifier calls of the dataset build requested the alias `{ver['model_alias_requested']}` and logged only the alias, "
              f"so the version it resolved to was not captured. Same-day records elsewhere: {ver['same_day_reference']}.",
              f"6. **Teacher.** Model id `{t['model_id']}`; endpoint host `{t['endpoint_host']}` ({t.get('endpoint_host_source', 'source not stated')}); {t['endpoint']}. Version: {t['version']}. Terms: {t['terms']}."]
    L += ["", "\"Labels are exact by construction\" holds for the sampled tuple only. Whether a note states exactly those events is what the verifier estimates, "
          "and the card's audit warning (a stricter pass disagreed with " + audit_line() + " accepted notes) still stands.", ""]
    (DATA / "dataset-v1/ERRATA.md").write_text("\n".join(L))


def main():
    import pyarrow.parquet as pq

    from eventlog.schema import PATHWAY_ORDER

    ds = DATA / "dataset-v1"
    split = {s: pq.read_table(ds / f"{s}.parquet").to_pylist() for s in ("train", "val", "test")}
    haiku = read_jsonl(DATA / "haiku-test.jsonl")
    first = json.loads((DATA / "eval-v1.json").read_text())
    n200 = first["counts"]["test"]
    pred200 = {p["id"]: p for p in first["predictions"][:n200]}
    pred_h = first["predictions"][n200:]
    val_pred = read_jsonl(EVAL / "adapter-val.jsonl")
    rest_pred = read_jsonl(EVAL / "adapter-test-rest.jsonl")
    assert [p["id"] for p in val_pred] == [r["id"] for r in split["val"]], "validation predictions do not match the validation split"
    rest = {p["id"]: p for p in rest_pred}
    assert not set(rest) & set(pred200) and len(rest) + len(pred200) == len(split["test"]), "test predictions do not cover the split exactly once"

    # --- adapter on every split, one record per note
    def record(row, pred, score, raw=None):
        return {"row": row, "pred": pred, "score": score, "ok": correct(row, pred)}

    val = [record(r, p["pred"], p["score"]) for r, p in zip(split["val"], val_pred)]
    test = []
    for r in split["test"]:
        if r["id"] in pred200:
            p = pred200[r["id"]]
            test.append({**record(r, p["adapter"], p["adapter_mean_json_logprob"]), "in_first_200": True, "base_ok": correct(r, p["base"])})
        else:
            p = rest[r["id"]]
            test.append({**record(r, p["pred"], p["score"]), "in_first_200": False})
    hk = [record(r, p["adapter"], p["adapter_mean_json_logprob"]) for r, p in zip(haiku, pred_h)]
    assert [p["id"] for p in pred_h] == [r.get("id", str(i)) for i, r in enumerate(haiku)] or len(pred_h) == len(haiku)
    t200 = [x for x in test if x["in_first_200"]]

    def cols(recs):
        return [x["row"] for x in recs], [x["score"] for x in recs], [x["ok"] for x in recs]

    # --- selective prediction with a validation-fixed threshold
    selective = {
        "score": "mean log-probability of the generated JSON tokens (adapter)",
        "rule": "threshold = lowest score on the validation notes such that the notes at or above it have an error rate at or below the limit; fixed there, then applied unchanged",
        "validation_notes": len(val),
        "validation_note": "the validation notes took no gradient step; 50 of them were used to monitor validation loss during training",
        "validation_exact_match": wilson(sum(x["ok"] for x in val), len(val)),
        "notes_needed_without_error_for_claim": {str(lim): notes_needed_for(lim) for lim in LIMITS},
        "limits": {},
    }
    for lim in LIMITS:
        t = threshold_from(*cols(val)[1:], lim)
        t_test = threshold_from(*cols(t200)[1:], lim)        # what the first evaluation did: chosen on the test notes themselves
        t_haiku = threshold_from(*cols(hk)[1:], lim)
        selective["limits"][str(lim)] = {
            "threshold_from_validation": t,
            "validation": apply_threshold(*cols(val), t),
            "test_all": apply_threshold(*cols(test), t),
            "test_first_200": apply_threshold(*cols(t200), t),
            "haiku": apply_threshold(*cols(hk), t),
            "in_sample_for_comparison": {
                "note": "threshold chosen on the same notes it is scored on, as in the first evaluation; optimistic by construction",
                "test_first_200": {"threshold": t_test, **apply_threshold(*cols(t200), t_test)},
                "haiku": {"threshold": t_haiku, **apply_threshold(*cols(hk), t_haiku)},
                "haiku_threshold_applied_to_test_first_200": apply_threshold(*cols(t200), t_haiku),
                "test_threshold_applied_to_haiku": apply_threshold(*cols(hk), t_test),
            },
        }

    # --- the adapter on all test notes
    def scored(recs):
        s = summary([x["row"] for x in recs], [x["pred"] for x in recs])
        return slim(s)

    rel = [x for x in test if is_relative(x["row"])]
    absolute = [x for x in test if not is_relative(x["row"])]
    all_test = {
        "n": len(test),
        "note": "adapter only; the base model was run on the first 200 test notes only, so the paired comparison stays on those 200",
        "adapter": scored(test),
        "first_200": scored(t200),
        "other_300": scored([x for x in test if not x["in_first_200"]]),
        "with_relative_date": scored(rel),
        "absolute_dates_only": scored(absolute),
        "invalid_json": sum(x["pred"] is None for x in test),
    }

    # --- pathway order of the ground truth
    _, bad, validator = ground_truth_order({"train": split["train"], "val": split["val"], "test": split["test"], "haiku": haiku})
    pair_counts = collections.Counter(p for name in ("train", "val", "test") for pairs in bad[name].values() for p in pairs)
    clean_test = [x for x in test if x["row"]["id"] not in bad["test"]]
    clean_200 = [x for x in t200 if x["row"]["id"] not in bad["test"]]
    clean_haiku = [x for x, r in zip(hk, haiku) if r.get("id") not in bad["haiku"]]
    order_check = {
        "documented_order": PATHWAY_ORDER,
        "sampler_order_differs": "the sampler (scribe/sample.py) puts " + "; ".join(f"{a} before {b}" for a, b in sampler_swaps()) + "; the documented order has them the other way round",
        "sampler_order_differs_on": sampler_swaps(),
        "episodes_with_reversed_pair": {k: len(v) for k, v in bad.items()},
        "episodes": {"train": len(split["train"]), "val": len(split["val"]), "test": len(split["test"]), "haiku": len(haiku)},
        "accepted_episodes_with_reversed_pair": sum(len(bad[k]) for k in ("train", "val", "test")),
        "accepted_episodes": sum(len(split[k]) for k in ("train", "val", "test")),
        "reversed_pairs_by_type": dict(pair_counts),
        "test_first_200_with_reversed_pair": sum(x["row"]["id"] in bad["test"] for x in t200),
        "without_those_episodes": {
            "test_all_adapter_exact_match": wilson(sum(x["ok"] for x in clean_test), len(clean_test)),
            "test_first_200_adapter_exact_match": wilson(sum(x["ok"] for x in clean_200), len(clean_200)),
            "test_first_200_base_exact_match": wilson(sum(x["base_ok"] for x in clean_200), len(clean_200)),
            "haiku_adapter_exact_match": wilson(sum(x["ok"] for x in clean_haiku), len(clean_haiku)),
        },
        "consequence": "the adapter was trained on the training ones and is scored on the test ones",
        "eventlog_validator": {
            "how": "eventlog/validate.py run on pathway_events tables built from the ground-truth targets (placeholder county, site, age band and source; the order check does not read them)",
            "by_split": validator,
        },
    }

    # --- identical event lists across splits (the split hash includes the route)
    key = lambda r: json.dumps(json.loads(r["target_json"])["events"], sort_keys=True)
    train_keys = {key(r) for r in split["train"]}
    shared = [x for x in test if key(x["row"]) in train_keys]
    not_shared = [x for x in test if key(x["row"]) not in train_keys]
    overlap = {
        "test_notes_sharing_an_event_list_with_a_training_note": len(shared),
        "of_which_in_first_200": sum(x["in_first_200"] for x in shared),
        "of_which_single_event": sum(len(json.loads(x["row"]["target_json"])["events"]) == 1 for x in shared),
        "adapter_correct_among_them": sum(x["ok"] for x in shared),
        "test_all_adapter_exact_match_without_them": wilson(sum(x["ok"] for x in not_shared), len(not_shared)),
        "val_notes_sharing_an_event_list_with_a_training_note": sum(key(r) in train_keys for r in split["val"]),
        "cause": "the sampler (scribe/sample.py) hashes entry route plus events to choose the split, so the same events with another route can land in another split",
        "crossing_splits": crossing_splits({k: split[k] for k in ("train", "val", "test")}),
    }

    # --- de-duplication (needs the git-ignored cache)
    dedup = {"status": "cache not present; not recomputed"}
    cache = sorted((DATA / "cache").glob("*.json"))
    if cache:
        rows = [json.loads(p.read_text()) for p in cache]
        rows = [r for r in rows if "accepted" in r]
        by_id = collections.defaultdict(list)
        for r in rows:
            by_id[r["id"]].append(r)
        dup = {k: v for k, v in by_id.items() if len(v) > 1}
        dedup = {
            "status": "recomputed from data/scribe/cache",
            "cache_rows_with_a_verdict": len(rows),
            "ids_occurring_more_than_once": len(dup),
            "first_row_rejected_and_a_later_row_accepted": sum((not v[0]["accepted"]) and any(x["accepted"] for x in v[1:]) for v in dup.values()),
            "first_row_accepted_and_another_accepted_row_dropped": sum(v[0]["accepted"] and any(x["accepted"] for x in v[1:]) for v in dup.values()),
            "rule_used_for_dataset_v1": "the first cached row of an id is kept whatever its verdict",
            "consequence": "accepted notes of the first kind were dropped and their id filed under rejected; dataset-v1 is left as built because the adapter was trained and scored on it",
        }

    out = {
        "synthetic": True,
        "statement": "SYNTHETIC notes about simulated people. Research artefact; not a medical device; not for clinical use.",
        "inputs": {
            "first_evaluation": "data/scribe/eval-v1.json",
            "validation_predictions": {"file": "scribe/artifacts/mlx-eval/adapter-val.jsonl", "notes": len(val_pred)},
            "remaining_test_predictions": {"file": "scribe/artifacts/mlx-eval/adapter-test-rest.jsonl", "notes": len(rest_pred)},
            "decoding": "greedy, at most 384 new tokens, same prompt as the first evaluation",
        },
        "selective": selective,
        "adapter_all_test": all_test,
        "pathway_order_check": order_check,
        "split_overlap": overlap,
        "dedup_report": dedup,
        "predictions": {
            "val": [{"id": x["row"]["id"], "pred": x["pred"], "score": x["score"], "ok": x["ok"]} for x in val],
            "test_other_300": [{"id": x["row"]["id"], "pred": x["pred"], "score": x["score"], "ok": x["ok"]} for x in test if not x["in_first_200"]],
        },
    }
    (DATA / "post-eval-v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    write_errata(out)
    s = selective["limits"]
    print(json.dumps({
        "out": "data/scribe/post-eval-v1.json",
        "validation_exact_match": selective["validation_exact_match"]["value"],
        "test_all_exact_match": all_test["adapter"]["note_exact_match"]["value"],
        "selective": {k: {"threshold": v["threshold_from_validation"], "val": [v["validation"].get("admitted"), v["validation"].get("errors_among_admitted")],
                          "test_all": [v["test_all"].get("admitted"), v["test_all"].get("errors_among_admitted"), v["test_all"].get("error_upper_bound_95_one_sided")],
                          "haiku": [v["haiku"].get("admitted"), v["haiku"].get("errors_among_admitted"), v["haiku"].get("error_upper_bound_95_one_sided")]} for k, v in s.items()},
        "order": order_check["episodes_with_reversed_pair"], "overlap": overlap["test_notes_sharing_an_event_list_with_a_training_note"],
        "dedup": {k: v for k, v in dedup.items() if isinstance(v, int)},
    }, indent=1))


if __name__ == "__main__":
    main()
