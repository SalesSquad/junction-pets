import asyncio
import collections
import json
import random

import pyarrow as pa
import pyarrow.parquet as pq
from common import DATA, log, save
from generate import Pipeline
from metrics import wilson
from verify import accept


def load():
    return [json.loads(p.read_text()) for p in sorted((DATA / "cache").glob("*.json"))]


async def audit():
    raw = load()
    seen = set()
    rows = []
    for row in raw:
        if row["id"] not in seen and "accepted" in row:
            seen.add(row["id"])
            rows.append(row)
    r = random.Random(20261114)
    p = Pipeline()
    sem = asyncio.Semaphore(12)

    async def one(row):
        path = DATA / "audit" / f"{row['id']}.json"
        if path.exists():
            return json.loads(path.read_text())
        async with sem:
            probs = await p.judge(row, True)
            out = {
                "id": row["id"],
                "accepted": row["accepted"],
                "probabilities": probs,
                "strict_pass": accept(probs, True),
            }
            save(path, out)
            return out

    result = []
    for accepted in [True, False]:
        pool = [x for x in rows if x.get("accepted") == accepted and "note_text" in x]
        chosen = r.sample(pool, min(60, len(pool)))
        result.extend(await asyncio.gather(*(one(x) for x in chosen)))
    await p.client.aclose()
    save(
        DATA / "audit-summary.json",
        {
            "strata": {
                str(a): {
                    "population": sum(x["accepted"] == a for x in rows),
                    "sampled": sum(x["accepted"] == a for x in result),
                    "strict_disagreements": sum(
                        x["accepted"] == a and x["strict_pass"] != a for x in result
                    ),
                }
                for a in [True, False]
            },
            "accepted_residual_noise_proxy": wilson(
                sum(x["accepted"] and not x["strict_pass"] for x in result),
                sum(x["accepted"] for x in result),
            ),
            "limit": "Second Jev pass disagreement is a model-based proxy, not independent human label truth. Stricter thresholds and shared-model errors can bias this estimate.",
        },
    )
    log("strict_audit", metrics={"notes": len(result)})


def dedup(rows, prefer_accepted=False):
    """One row per id. dataset-v1 was built with prefer_accepted=False: the first cached row wins
    whatever its verdict, which dropped accepted notes when an earlier attempt for the same id had
    been rejected (see dataset-v1/ERRATA.md). prefer_accepted=True keeps the first accepted row of
    an id if there is one; use it for any new dataset version, never to rebuild dataset-v1."""
    chosen = {}
    for r in rows:
        if r["id"] not in chosen or (prefer_accepted and r["accepted"] and not chosen[r["id"]]["accepted"]):
            chosen[r["id"]] = r
    order = {}
    for r in rows:
        order.setdefault(r["id"], len(order))
    return sorted(chosen.values(), key=lambda r: order[r["id"]])


def card_checks(out):
    """Figures for the card that are measured on the built split files: the pathway order of the ground
    truth (scribe/post_eval.py, which also runs eventlog/validate.py) and event lists shared across splits."""
    import itertools

    from post_eval import ground_truth_order  # also puts the project root on sys.path, for eventlog
    from sample import TYPES

    from eventlog.schema import EVENT_TYPES

    splits = {s: pq.read_table(out / f"{s}.parquet").to_pylist() for s in ("train", "val", "test")}
    pathway_order, bad, validator = ground_truth_order(splits)
    # type pairs that the sampler orders one way and eventlog/schema.py the other
    swapped = [(a, b) for a, b in itertools.combinations(TYPES, 2) if EVENT_TYPES.index(a) > EVENT_TYPES.index(b)]
    pairs = collections.Counter(p for name in splits for v in bad[name].values() for p in v)
    key = lambda r: json.dumps(json.loads(r["target_json"])["events"], sort_keys=True)
    train_keys = {key(r) for r in splits["train"]}
    return {
        "pathway_order": pathway_order,
        "sampler_order_differs_on": swapped,
        "episodes": {s: len(rows) for s, rows in splits.items()},
        "reversed": {s: len(bad[s]) for s in splits},
        "pairs": dict(sorted(pairs.items())),
        "validator_flagged": {s: validator[s]["episodes_flagged"] for s in splits},
        "validator_same_episodes": all(validator[s]["same_episodes_as_pair_check"] for s in splits),
        "validator_strict_rejects": [s for s in splits if not validator[s]["strict_mode_valid"]],
        "shared_event_lists": {s: sum(key(r) in train_keys for r in splits[s]) for s in ("val", "test")},
    }


def write_card(stats, out):
    """data/scribe/dataset-v1/CARD.md from the build statistics and the split files. Every figure is read or
    computed here; `--card-only` rewrites the card without rebuilding the split files."""
    c = card_checks(out)
    n, e = c["episodes"], c["reversed"]
    bad, total = sum(e.values()), sum(n.values())
    flagged = sum(c["validator_flagged"].values())
    differs = "; ".join(f"`{a}` before `{b}`" for a, b in c["sampler_order_differs_on"]) or "no pair"
    order_text = (
        f"**Pathway order (found after the build).** The sampler (`scribe/sample.py`) uses an older type order, which puts {differs}. "
        f"`DATA_COLLECTION.md` section 1 now defines the order `{c['pathway_order']}` (`eventlog/schema.py`). "
        f"Against it, {bad} of {total} accepted episodes ({100 * bad / total:.1f}%, about one in {round(total / bad)}) contain at least one pair of events dated in reversed order: "
        f"{e['train']} of {n['train']} training, {e['val']} of {n['val']} validation, {e['test']} of {n['test']} test. Reversed pairs: "
        + "; ".join(f"{k}: {v}" for k, v in c["pairs"].items())
        + f" (an episode can have both). Run on this ground truth, `eventlog/validate.py` flags {flagged} episodes"
        f"{', the same ones' if c['validator_same_episodes'] else ', not exactly the same ones'}, and its strict mode for simulator output rejects "
        f"{'every split' if len(c['validator_strict_rejects']) == 3 else ', '.join(c['validator_strict_rejects']) or 'no split'}. "
        "The files are left as built because an adapter was trained and scored on them."
    ) if bad else (
        f"**Pathway order.** Every accepted episode follows the order `{c['pathway_order']}` of `DATA_COLLECTION.md` section 1 (`eventlog/schema.py`)."
    )
    shared = c["shared_event_lists"]
    (out / "CARD.md").write_text(
        "# SAMA pathway scribe dataset v1\n\nAUDIT WARNING: The stricter same-model audit shows substantial disagreement. This dataset is not qualified as low-noise clinical training truth; inspect the audit and obtain independent review before making extraction-quality claims.\n\nSYNTHETIC ONLY. No real patients, clinicians or patient text. Research artefact, not a medical device.\n\nGround truth is code-sampled with fixed seed 20261114, nine event types and five entry routes from DATA_COLLECTION.md. Episodes contain 1–4 events in date order within 400 days before notes in 2024–2026, six date forms and 0–2 distractors. Uniform event subsets and broadly stratified date offsets are a language coverage design, not calibrated Finnish disease epidemiology. Nemotron writes Finnish notes; code checks exact date spans and 60–140 words, then Jev checks every event, unlisted events, distractors and the explicit entry route at specified thresholds. All raw probabilities remain cached.\n\n"
        + order_text
        + "\n\nA SHA256 of route and canonical events assigns the episode to a split before generation; the builder may transfer whole episodes from test surplus to a validation deficit, recording each transfer. "
        f"Identical ground truth (route and events) never crosses splits; the same event list with another route can: {shared['test']} test and {shared['val']} validation notes have the event list of a training note. No personal names requested.\n\nMeasured counts, rates, usage and audit:\n```json\n"
        + json.dumps(stats, indent=2)
        + "\n```\n\nLimits: synthetic teacher/verifier bias; no clinical validation; the second Jev pass is a correlated, stricter model-based noise proxy, not human truth. Code date detection covers explicit Finnish formats but cannot prove absence of every possible paraphrase. Labels must be confirmed by humans before care use. Training, adapter quality and external-writer generalisation are not established by this dataset.\n\nDefects found after the build (pathway order, split by route, de-duplication, cost field, verifier version, teacher) are listed in ERRATA.md in this directory.\n"
    )
    return c


def build():
    rows = load()
    rows = [r for r in rows if "accepted" in r]
    out = DATA / "dataset-v1"
    out.mkdir(exist_ok=True)
    counts = {}
    unique = dedup(rows)        # v1 rule, kept so that dataset-v1 stays reproducible
    # Balance whole episodes only: preserve the requested held-out targets without leakage.
    reassigned = []
    split_counts = collections.Counter(r["split"] for r in unique if r["accepted"])
    if split_counts["val"] < 250 and split_counts["test"] > 500:
        n = min(250 - split_counts["val"], split_counts["test"] - 500)
        candidates = sorted(
            (r for r in unique if r["accepted"] and r["split"] == "test"),
            key=lambda r: r["id"],
        )
        for row in candidates[:n]:
            row = row.copy()
            reassigned.append({"id": row["id"], "from": "test", "to": "val"})
        moved = {r["id"] for r in reassigned}
        unique = [{**r, "split": "val"} if r["id"] in moved else r for r in unique]
    event = pa.struct(
        [("type", pa.string()), ("date", pa.string()), ("precision", pa.string())]
    )
    schema = pa.schema(
        [
            ("id", pa.string()),
            ("split", pa.string()),
            ("note_text", pa.string()),
            ("note_date", pa.string()),
            ("style", pa.string()),
            ("entry_route", pa.string()),
            ("events", pa.list_(event)),
            ("target_json", pa.string()),
            ("date_forms", pa.list_(pa.string())),
            ("teacher_model", pa.string()),
            ("verifier_probabilities", pa.map_(pa.string(), pa.float64())),
            ("accepted", pa.bool_()),
            ("synthetic", pa.bool_()),
            (
                "distractors",
                pa.list_(
                    pa.struct(
                        [
                            ("kind", pa.string()),
                            ("expression", pa.string()),
                            ("date", pa.string()),
                            ("meaning", pa.string()),
                        ]
                    )
                ),
            ),
        ]
    )
    for split in ["train", "val", "test", "rejected"]:
        selected = [
            r
            for r in unique
            if (r["accepted"] and r["split"] == split)
            or (not r["accepted"] and split == "rejected")
        ]
        packed = []
        for r in selected:
            v = {k: r.get(k) for k in schema.names}
            v["split"] = split
            v["verifier_probabilities"] = list(r["verifier_probabilities"].items())
            packed.append(v)
        pq.write_table(
            pa.Table.from_pylist(packed, schema=schema),
            out / f"{split}.parquet",
            compression="zstd",
        )
        counts[split] = len(selected)
    checked = sum(r["code_check"]["ok"] for r in rows)
    rejected = sum(
        r["code_check"]["ok"] and not accept(r["verifier_probabilities"]) for r in rows
    )
    stats = {
        "counts": counts,
        "whole_episode_split_reassignments": reassigned,
        "generated": len(rows),
        "duplicate_episode_rows_removed": len(rows) - len(unique),
        "sampler_quarantined": sum(bool(r.get("sampler_rejection")) for r in rows),
        "code_check_failure": wilson(len(rows) - checked, len(rows)),
        "verifier_rejection_given_code_pass": wilson(rejected, checked),
        "usage": json.loads((DATA / "usage.json").read_text()),
        "date_forms": dict(
            collections.Counter(
                f for r in rows if r["accepted"] for f in r["date_forms"]
            )
        ),
    }
    # Computed from tokens at the owner's stated price (USD 0.042 per million tokens); not a billed amount.
    stats["typesafe_cost_usd"] = stats["usage"]["typesafe_tokens"] * 0.042 / 1e6
    if (DATA / "audit-summary.json").exists():
        stats["audit"] = json.loads((DATA / "audit-summary.json").read_text())
    if "audit" in stats:
        strata = stats["audit"]["strata"]
        a = strata["True"]
        r = strata["False"]
        na = a["population"]
        nr = r["population"]
        audit_population = na + nr
        if a["sampled"] and r["sampled"]:
            p_bad_accepted = a["strict_disagreements"] / a["sampled"]
            pr = 1 - r["strict_disagreements"] / r["sampled"]
            bad_kept = na * p_bad_accepted
            bad_rejected = nr * pr
            good_rejected = nr * (1 - pr)
            e = (bad_kept + bad_rejected) / audit_population
            c = (
                bad_rejected / (bad_kept + bad_rejected)
                if bad_kept + bad_rejected
                else None
            )
            f = good_rejected / (audit_population * (1 - e)) if e < 1 else None
            stats["audit"]["section4_noise_formula_estimate"] = {
                "teacher_unfaithfulness_e": e,
                "catch_fraction_c": c,
                "false_rejection_f": f,
                "residual": e * (1 - c) / (e * (1 - c) + (1 - e) * (1 - f))
                if c is not None and f is not None
                else None,
                "limit": "Stratified estimates from stricter Jev judgments, not ground truth.",
            }
    save(DATA / "dataset-stats.json", stats)
    write_card(stats, out)
    log(
        "build_dataset",
        outputs=["data/scribe/dataset-v1", "data/scribe/dataset-stats.json"],
        metrics=counts,
    )
    print(json.dumps(stats))


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--audit", action="store_true")
    p.add_argument("--card-only", action="store_true", help="rewrite dataset-v1/CARD.md from dataset-stats.json and the split files; nothing else is written")
    args = p.parse_args()
    if args.card_only:
        print(json.dumps(write_card(json.loads((DATA / "dataset-stats.json").read_text()), DATA / "dataset-v1")))
    else:
        if args.audit:
            asyncio.run(audit())
        build()
