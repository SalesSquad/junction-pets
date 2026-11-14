"""Data export for the MLX arms of NVIDIA_OPTIONS.md step 3. SYNTHETIC notes only.

  roundtrip   resolve_expression(expression_target(row)) == label on every train and val row
  augment     rewrite the relative-date phrase of about a third of the train notes that have one into a Finnish
              number word 1-6, "eilen", "päivä sitten" or "viikko sitten" (code only, train only); the held-out
              families (number words 7-12, "toissapäivänä") are never produced
  chat        mlx_lm chat JSONL per arm: absolute (version-1 prompt and target) and expression-aug

Reads only data/scribe/v2/dataset/{train,val}.parquet. Writes data/scribe/v4/mlx/.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys

import m2common as C

import data_tools as DT  # scribe/v2
from prompts import canonicalise, messages as absolute_messages  # scribe (version 1)

AUG_SEED = "sama-mlx2-augment-20261114"
AUG_SHARE = 1 / 3
# Train phrasings: what the A' lexicon (scribe/v3/lexicon.py) also covers. (offset in days, phrase, expression).
NUMBER_WORDS_TRAIN = {2: "kaksi", 3: "kolme", 4: "neljä", 5: "viisi", 6: "kuusi"}
NUMBER_WORDS_HELDOUT = {7: "seitsemän", 8: "kahdeksan", 9: "yhdeksän", 10: "kymmenen", 11: "yksitoista", 12: "kaksitoista"}
HELDOUT_ADVERBS = {"toissapäivänä": 2}


def train_options():
    """Every phrasing the augmentation may write, grouped by day offset (distinct offsets per note)."""
    opts = {1: [("eilen", {"kind": "DAYS_AGO", "n": 1}),
                ("päivä sitten", {"kind": "DAYS_AGO", "n": 1}),
                ("yksi päivä sitten", {"kind": "DAYS_AGO", "n": 1})],
            7: [("viikko sitten", {"kind": "WEEKS_AGO", "n": 1}),
                ("yksi viikko sitten", {"kind": "WEEKS_AGO", "n": 1})]}
    for n, w in NUMBER_WORDS_TRAIN.items():
        opts[n] = [(f"{w} päivää sitten", {"kind": "DAYS_AGO", "n": n})]
        opts[7 * n] = [(f"{w} viikkoa sitten", {"kind": "WEEKS_AGO", "n": n})]
    return dict(sorted(opts.items()))


# Weights inside an offset: "eilen" is the everyday word, the "yksi ..." forms are rare in Finnish.
OPTION_WEIGHTS = {"eilen": 3, "päivä sitten": 2, "yksi päivä sitten": 1, "viikko sitten": 3, "yksi viikko sitten": 1}


def heldout_phrasings():
    words = [f"{w} {unit} sitten" for w in NUMBER_WORDS_HELDOUT.values() for unit in ("päivää", "viikkoa")]
    return {
        "number_words_7_12": NUMBER_WORDS_HELDOUT,
        "adverbs": HELDOUT_ADVERBS,
        "phrases": words + list(HELDOUT_ADVERBS),
        "tokens": list(NUMBER_WORDS_HELDOUT.values()) + list(HELDOUT_ADVERBS),
    }


_HELDOUT_RE = re.compile(r"(?<!\w)(" + "|".join(heldout_phrasings()["tokens"]) + r")(?!\w)", re.IGNORECASE)


def label(row):
    return json.loads(row["target_json"])


# ---- round trip ---------------------------------------------------------------------------------------------------

def roundtrip_rows(rows):
    """[(id, ok, error)] for resolve_expression(expression_target(row)) == label, and to_expression agreement."""
    out = []
    for r in rows:
        try:
            target = DT.expression_target(r)
            resolved = DT.resolve_expression(json.loads(target), r["note_date"])
            ok = resolved == canonicalise(label(r))
            err = "" if ok else "resolved target differs from the label"
            if ok and r.get("facts") is not None:
                rebuilt = DT._compact(DT.to_expression(r))
                if rebuilt != target:
                    ok, err = False, "stored expression_json differs from to_expression(row)"
        except Exception as e:  # noqa: BLE001 - every failure counts
            ok, err = False, f"{type(e).__name__}: {e}"
        out.append((r["id"], ok, err))
    return out


# ---- augmentation -------------------------------------------------------------------------------------------------

def _capitalise_at(text, start, phrase):
    """Capitalise a phrase that starts a sentence (start of the note or after . ! ? or a line break)."""
    pre = text[:start].rstrip(" \t")
    if not pre or pre.endswith("\n") or pre[-1] in ".!?":
        return phrase[0].upper() + phrase[1:]
    return phrase


def candidates(row):
    """Relative facts of a row grouped by printed phrase, or None when the row cannot be rewritten safely.

    Safe: every relative phrase is a digit phrase printed exactly once (version-1 date_pattern boundaries), and no
    distractor prints the same string.
    """
    facts = row.get("facts") or []
    rel = [f for f in facts if f["form"] in ("days", "weeks")]
    if not rel:
        return None
    groups = collections.OrderedDict()
    for f in rel:
        groups.setdefault(f["expression"], []).append(f)
    distractor_strings = {d["expression"] for d in row.get("distractors") or []}
    for phrase in groups:
        if phrase in distractor_strings:
            return None
        if len(re.findall(DT.date_pattern(phrase), row["note_text"])) != 1:
            return None
    return groups


def augment_row(row, rng):
    """Rewrite every relative phrase of one row. Returns (new_row, record). Offsets keep the original order."""
    groups = candidates(row)
    lowered = row["note_text"].lower()
    # Leave out a phrasing the note already contains anywhere, so every rewritten phrase occurs exactly once.
    opts = {}
    for off, choices in train_options().items():
        keep = [c for c in choices if not re.search(DT.date_pattern(c[0]), lowered)]
        if keep:
            opts[off] = keep
    note = DT._as_date(row["note_date"])
    phrases = sorted(groups, key=lambda p: (note - DT._as_date(groups[p][0]["date"])).days)  # newest first
    offsets = sorted(rng.sample(list(opts), len(phrases)))
    text = row["note_text"]
    mapping = {}
    for phrase, off in zip(phrases, offsets):
        choices = opts[off]
        new, expr = rng.choices(choices, weights=[OPTION_WEIGHTS.get(c[0], 1) for c in choices])[0]
        m = re.search(DT.date_pattern(phrase), text)
        new_text = _capitalise_at(text, m.start(), new)
        text = text[: m.start()] + new_text + text[m.end():]
        mapping[phrase] = {"to": new_text, "expression": expr, "offset_days": off}
    new_facts = []
    for f in row["facts"]:
        f = dict(f)
        if f["expression"] in mapping:
            mp = mapping[f["expression"]]
            f.update(expression=mp["to"], date=DT.resolve_date(mp["expression"], note)[0], precision="DAY",
                     form="aug_" + ("weeks_word" if mp["expression"]["kind"] == "WEEKS_AGO" else
                                    "yesterday" if mp["to"].lower() == "eilen" else "days_word"))
        new_facts.append(f)
    truth = {"entry_route": row["entry_route"],
             "events": [{"type": f["type"], "date": f["date"], "precision": f["precision"]} for f in new_facts]}
    # Expression target: events in the order their phrases appear in the new text (ties keep canonical order).
    canonical = sorted(new_facts, key=lambda f: (f["date"], f["type"]))
    keyed = []
    for i, f in enumerate(canonical):
        hits = list(re.finditer(DT.date_pattern(f["expression"]), text))
        if not hits:
            raise ValueError(f"{row['id']}: rewritten phrase {f['expression']!r} not found")
        if f["form"].startswith("aug_") and len(re.findall(DT.date_pattern(f["expression"].lower()), text.lower())) != 1:
            raise ValueError(f"{row['id']}: rewritten phrase {f['expression']!r} is not unique")
        hit = hits[0]
        if f["form"].startswith("aug_"):
            expr = next(mp["expression"] for mp in mapping.values() if mp["to"] == f["expression"])
        else:
            expr = DT.parse_expression(f["expression"], row["note_date"])
        keyed.append((hit.start(), i, {"type": f["type"], "date": expr}))
    target = {"entry_route": row["entry_route"], "events": [e for _, _, e in sorted(keyed, key=lambda k: k[:2])]}
    new = dict(row)
    new.update(note_text=text, facts=new_facts, target_json=DT._compact(canonicalise(truth)),
               expression_json=DT._compact(target), events=truth["events"],
               date_forms=sorted({f["form"] for f in new_facts}), augmented=True)
    # Round trip of the rewritten row: code resolution of the new target must equal the new label.
    if DT.resolve_expression(target, row["note_date"]) != canonicalise(truth):
        raise ValueError(f"{row['id']}: augmented round trip failed")
    if _HELDOUT_RE.search(" ".join(mp["to"] for mp in mapping.values())):
        raise ValueError(f"{row['id']}: augmentation produced a held-out phrasing")
    record = {"id": row["id"], "writer": row["writer"],
              "rewrites": [{"from": p, **mapping[p]} for p in phrases]}
    return new, record


def augment(rows):
    rng = random.Random(AUG_SEED)
    eligible = [r for r in rows if candidates(r)]
    with_rel = [r for r in rows if any(f["form"] in ("days", "weeks") for f in r.get("facts") or [])]
    k = round(AUG_SHARE * len(with_rel))
    chosen = set(r["id"] for r in rng.sample(eligible, min(k, len(eligible))))
    out, records = [], []
    for r in rows:
        if r["id"] in chosen:
            new, rec = augment_row(r, rng)
            out.append(new)
            records.append(rec)
        else:
            out.append(r)
    stats = {
        "train_rows": len(rows),
        "rows_with_relative_fact": len(with_rel),
        "eligible_rows": len(eligible),
        "target_share": AUG_SHARE,
        "rewritten_rows": len(records),
        "rewritten_phrases": sum(len(r["rewrites"]) for r in records),
        "phrase_counts": dict(collections.Counter(
            re.sub(r"^\w", lambda m: m.group().lower(), w["to"]) for r in records for w in r["rewrites"]).most_common()),
        "rewritten_by_writer": dict(collections.Counter(r["writer"] for r in records)),
    }
    return out, records, stats


def heldout_occurrences(rows):
    c = collections.Counter()
    for r in rows:
        for m in _HELDOUT_RE.finditer(r["note_text"]):
            c[m.group(1).lower()] += 1
    return dict(c)


# ---- chat JSONL ---------------------------------------------------------------------------------------------------

def chat_absolute(row):
    return {"messages": absolute_messages(row) + [{"role": "assistant", "content": row["target_json"]}]}


def chat_expression(row):
    return {"messages": DT.expression_messages(row) + [{"role": "assistant", "content": DT.expression_target(row)}]}


def write_jsonl(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return {"path": C.rel(path), "rows": len(items), "sha256": C.sha256_file(path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.parse_args(argv)
    train, val = C.load_split("train"), C.load_split("val")
    # 1. round trip on every train and val row, before anything else
    rt = {name: roundtrip_rows(rows) for name, rows in (("train", train), ("val", val))}
    failures = {k: [(i, e) for i, ok, e in v if not ok] for k, v in rt.items()}
    rt_out = {"rule": "resolve_expression(json.loads(expression_target(row)), note_date) == canonical label, and "
                      "stored expression_json == to_expression(row)",
              "synthetic": True,
              "counts": {k: {"rows": len(v), "ok": sum(ok for _, ok, _ in v)} for k, v in rt.items()},
              "failures": {k: v[:20] for k, v in failures.items()}}
    C.save_json(C.OUT / "roundtrip-v1.json", rt_out)
    C.log("roundtrip", "scribe/.venv/bin/python scribe/mlx2/export.py",
          inputs={"train": C.rel(C.DATASET / "train.parquet"), "val": C.rel(C.DATASET / "val.parquet")},
          outputs={"file": C.rel(C.OUT / "roundtrip-v1.json")}, metrics=rt_out["counts"],
          status="ok" if not any(failures.values()) else "failed")
    print(json.dumps(rt_out["counts"]))
    if any(failures.values()):
        print("round trip failed; fix the targets first", failures, file=sys.stderr)
        return 1
    # 2. augmentation on train only
    aug_train, records, stats = augment(train)
    held = heldout_phrasings()
    held_doc = {
        "synthetic": True,
        "rule": "Held out of every training note for the step 5 stress set: never written by scribe/mlx2/export.py.",
        **held,
        "train_phrasings": {str(k): [p for p, _ in v] for k, v in train_options().items()},
        "heldout_token_occurrences": {"train_original": heldout_occurrences(train),
                                      "train_augmented": heldout_occurrences(aug_train),
                                      "val": heldout_occurrences(val)},
        "note": "Occurrences are whole-word matches of a held-out number word or adverb anywhere in the note text "
                "(any context, not only dates); the augmentation adds none.",
    }
    C.save_json(C.OUT / "heldout-phrasings.json", held_doc)
    C.save_json(C.OUT / "augmentation-v1.json", {"synthetic": True, "seed": AUG_SEED, **stats, "rows": records})
    # 3. chat JSONL
    files = {
        "absolute/train": write_jsonl(C.OUT / "chat/absolute/train.jsonl", [chat_absolute(r) for r in train]),
        "absolute/valid": write_jsonl(C.OUT / "chat/absolute/valid.jsonl", [chat_absolute(r) for r in val]),
        "expression-aug/train": write_jsonl(C.OUT / "chat/expression-aug/train.jsonl", [chat_expression(r) for r in aug_train]),
        "expression-aug/valid": write_jsonl(C.OUT / "chat/expression-aug/valid.jsonl", [chat_expression(r) for r in val]),
    }
    C.save_json(C.OUT / "export-v1.json", {"synthetic": True, "created": C.now(), "files": files,
                                           "augmentation": stats, "heldout": C.rel(C.OUT / "heldout-phrasings.json")})
    C.log("export", "scribe/.venv/bin/python scribe/mlx2/export.py",
          inputs={"train": C.rel(C.DATASET / "train.parquet"), "val": C.rel(C.DATASET / "val.parquet")},
          outputs={k: v["path"] for k, v in files.items()},
          metrics={k: v for k, v in stats.items() if k != "phrase_counts"} | {"heldout_added": held_doc["heldout_token_occurrences"]})
    print(json.dumps(stats, ensure_ascii=False))
    print(json.dumps(held_doc["heldout_token_occurrences"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
