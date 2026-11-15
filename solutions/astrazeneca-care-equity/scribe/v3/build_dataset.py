"""Dataset v3 = dataset v2 + the round-2 Nemotron notes accepted by the gate.

  scribe/.venv/bin/python scribe/v3/build_dataset.py

train.parquet         every row of the version-2 train file, unchanged and in the same order, followed by the
                      round-2 notes the rule accepted (data/scribe/v3/gate/judged.jsonl, pass == true)
val.parquet           byte-identical copy of version 2
test_nemotron.parquet byte-identical copy of version 2
test_haiku.parquet    byte-identical copy of version 2
rejected.parquet      version-2 rejected rows, unchanged, followed by the round-2 notes that failed the code
                      check (reject_stage code_check) or the rule (reject_stage verifier). Not for training.
round2.jsonl          side file keyed by id: round, curriculum and the gate flags of every round-2 note
                      (the parquet schema of version 2 is kept exactly, so it has no such columns)
CARD.md, ../dataset-stats.json is written as data/scribe/v3/dataset/dataset-stats.json

The build stops (AssertionError) when an id of train occurs in val or a test file, when a note text occurs
on both sides, or when a row's expression target does not resolve to its absolute target.
All text is SYNTHETIC. Nothing here is for clinical use.
"""

import collections
import json
import shutil
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "v2"))

from common import starts_with_style_label, CANDIDATES, CURRICULA, DATASET_V2, DATASET_V3, GATE, POLICY, ROOT, log, now, read_jsonl, save_json, sha256_file, write_jsonl  # noqa: E402

import data_tools  # noqa: E402  (version 2, read only)

COPIED = ("val", "test_nemotron", "test_haiku")
HELDOUT = COPIED
FILES = ("train", "val", "test_nemotron", "test_haiku", "rejected")


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def to_row(c, split, accepted, reject_stage, probabilities):
    """A round-2 candidate in the exact version-2 columns."""
    events = [dict(type=e["type"], date=e["date"], precision=e["precision"]) for e in c["events"]]
    target = compact(dict(entry_route=c["entry_route"], events=events))
    assert target == c["target_json"], f"target_json differs from the events: {c['id']}"
    resolved = data_tools.resolve_expression(json.loads(c["expression_json"]), c["note_date"])
    assert compact(resolved) == compact(json.loads(c["target_json"])) or resolved == data_tools.canonicalise(
        json.loads(c["target_json"])
    ), f"expression target does not resolve to the absolute target: {c['id']}"
    return dict(
        id=c["id"],
        split=split,
        note_text=c["note_text"],
        note_date=c["note_date"],
        style=c["style"],
        entry_route=c["entry_route"],
        events=events,
        target_json=c["target_json"],
        date_forms=list(c["date_forms"]),
        teacher_model=c["teacher_model"],
        verifier_probabilities=list(probabilities.items()),
        accepted=accepted,
        synthetic=True,
        distractors=[{k: d[k] for k in ("kind", "expression", "date", "meaning")} for d in c["distractors"]],
        writer=c["writer"],
        kind=c["kind"],
        expression_json=c["expression_json"],
        focus=c["focus"],
        facts=[{k: f[k] for k in ("type", "date", "precision", "expression", "form", "meaning")} for f in c["facts"]],
        reject_stage=reject_stage,
    )


def counts(rows, meta):
    out = dict(
        rows=len(rows),
        by_writer=dict(collections.Counter(r["writer"] for r in rows)),
        by_kind=dict(collections.Counter(r["kind"] for r in rows)),
        round2_rows=sum(r["id"] in meta for r in rows),
        round2_by_curriculum={c: sum(meta.get(r["id"], {}).get("curriculum") == c for r in rows) for c in CURRICULA},
    )
    return out


def check_disjoint(tables):
    """Ids and note texts of train against every held-out file; returns the counts that were asserted to be 0."""
    train_ids = set(tables["train"].column("id").to_pylist())
    train_txt = set(tables["train"].column("note_text").to_pylist())
    assert len(train_ids) == tables["train"].num_rows, "duplicate id inside train"
    res = {}
    for name in HELDOUT:
        ids = set(tables[name].column("id").to_pylist())
        txt = set(tables[name].column("note_text").to_pylist())
        res[name] = dict(ids_shared_with_train=len(train_ids & ids), note_texts_shared_with_train=len(train_txt & txt))
        assert not train_ids & ids, f"id of train occurs in {name}"
        assert not train_txt & txt, f"note text of train occurs in {name}"
    dup = tables["train"].num_rows - len(train_txt)
    assert dup == 0, f"{dup} duplicated note texts inside train"
    all_ids = collections.Counter(i for n in FILES for i in tables[n].column("id").to_pylist())
    twice = sum(v > 1 for v in all_ids.values())
    assert twice == 0, f"{twice} ids occur in two files"
    return dict(heldout=res, duplicate_note_texts_in_train=dup, ids_in_two_files=twice)


def main():
    cands = read_jsonl(CANDIDATES)
    by_id = {c["id"]: c for c in cands}
    judged = {r["id"]: r for r in read_jsonl(GATE / "judged.jsonl")}
    DATASET_V3.mkdir(parents=True, exist_ok=True)

    v2 = {n: pq.read_table(DATASET_V2 / f"{n}.parquet") for n in FILES}
    schema = v2["train"].schema
    assert all(v2[n].schema.equals(schema) for n in FILES)

    accepted, rejected, not_judged, meta = [], [], [], {}
    for c in cands:
        j = judged.get(c["id"])
        m = dict(
            id=c["id"],
            round=2,
            curriculum=c["curriculum"],
            kind=c["kind"],
            focus=c["focus"],
            code_check_passed=c["code_check"]["passed"],
            readback_consistent=c["readback"]["consistent"],
            repaired=c["repaired"],
            told_order=c["told_order"],
            words=c["words"],
            starts_with_style_label=starts_with_style_label(c["note_text"]),
            rule=j["rule"] if j else None,
            rule_pass=j["pass"] if j else None,
            decisions_pass=(j["judge_pass"].get("decisions") if j and "decisions" in j["judges"] and not j["judges"]["decisions"].get("error") else None),
        )
        probs = dict((j["judges"].get("jev") or {}).get("probabilities") or {}) if j else {}
        if not c["code_check"]["passed"]:
            rejected.append(to_row(c, "rejected", False, "code_check", {}))
            m["file"] = "rejected"
        elif j is None or j["pass"] is None:
            not_judged.append(c["id"])
            m["file"] = None  # passed the code check but the rule's judge gave no answer: in neither file
        elif j["pass"]:
            accepted.append(to_row(c, "train", True, None, probs))
            m["file"] = "train"
        else:
            rejected.append(to_row(c, "rejected", False, "verifier", probs))
            m["file"] = "rejected"
        meta[c["id"]] = m

    new_train = pa.Table.from_pylist(accepted, schema=schema)
    new_rej = pa.Table.from_pylist(rejected, schema=schema)
    tables = dict(v2)
    tables["train"] = pa.concat_tables([v2["train"], new_train])
    tables["rejected"] = pa.concat_tables([v2["rejected"], new_rej])
    assert tables["train"].schema.equals(schema) and tables["rejected"].schema.equals(schema)
    n2 = v2["train"].num_rows
    assert tables["train"].slice(0, n2).equals(v2["train"]), "version-2 train rows changed"
    assert tables["rejected"].slice(0, v2["rejected"].num_rows).equals(v2["rejected"]), "version-2 rejected rows changed"
    disjoint = check_disjoint(tables)

    pq.write_table(tables["train"], DATASET_V3 / "train.parquet")
    pq.write_table(tables["rejected"], DATASET_V3 / "rejected.parquet")
    for n in COPIED:
        shutil.copyfile(DATASET_V2 / f"{n}.parquet", DATASET_V3 / f"{n}.parquet")
        assert sha256_file(DATASET_V3 / f"{n}.parquet") == sha256_file(DATASET_V2 / f"{n}.parquet")
    write_jsonl(DATASET_V3 / "round2.jsonl", [meta[c["id"]] for c in cands])

    # read back what was written and check it again
    written = {n: pq.read_table(DATASET_V3 / f"{n}.parquet") for n in FILES}
    assert all(written[n].schema.equals(schema) for n in FILES), "a written file has another schema than version 2"
    assert written["train"].slice(0, n2).equals(v2["train"])
    disjoint_written = check_disjoint(written)
    assert disjoint_written == disjoint
    mismatch = 0
    for r in written["train"].to_pylist() + written["val"].to_pylist() + written["test_nemotron"].to_pylist() + written["test_haiku"].to_pylist():
        resolved = data_tools.resolve_expression(json.loads(r["expression_json"]), r["note_date"])
        mismatch += resolved != data_tools.canonicalise(json.loads(r["target_json"]))
    assert mismatch == 0, f"{mismatch} expression targets do not resolve to target_json"

    files = {}
    for n in FILES:
        rows = written[n].to_pylist()
        files[n] = dict(
            file=f"{n}.parquet",
            sha256=sha256_file(DATASET_V3 / f"{n}.parquet"),
            v2_sha256=sha256_file(DATASET_V2 / f"{n}.parquet"),
            byte_identical_to_v2=sha256_file(DATASET_V3 / f"{n}.parquet") == sha256_file(DATASET_V2 / f"{n}.parquet"),
            v2_rows=v2[n].num_rows,
            **counts(rows, meta),
        )
    acc_meta = [m for m in meta.values() if m["file"] == "train"]
    rej_meta = [m for m in meta.values() if m["file"] == "rejected"]
    stats = dict(
        schemaVersion="scribe-dataset-v3-stats",
        generated=now(),
        synthetic=True,
        sources=dict(
            v2_dataset=str(DATASET_V2.relative_to(ROOT)),
            candidates=str(CANDIDATES.relative_to(ROOT)),
            candidates_sha256=sha256_file(CANDIDATES),
            judged="data/scribe/v3/gate/judged.jsonl",
            judged_sha256=sha256_file(GATE / "judged.jsonl"),
            policy_sha256=sha256_file(POLICY),
        ),
        columns=[f.name for f in schema],
        schema_equal_to_v2={n: written[n].schema.equals(schema) for n in FILES},
        files=files,
        round2=dict(
            candidates=len(cands),
            added_to_train=len(accepted),
            added_to_rejected=len(rejected),
            rejected_by_stage=dict(collections.Counter(r["reject_stage"] for r in rejected)),
            passed_code_check_but_not_judged=len(not_judged),
            added_to_train_by_curriculum={c: sum(m["curriculum"] == c for m in acc_meta) for c in CURRICULA},
            added_to_rejected_by_curriculum={c: sum(m["curriculum"] == c for m in rej_meta) for c in CURRICULA},
            candidates_by_curriculum={c: sum(x["curriculum"] == c for x in cands) for c in CURRICULA},
            added_to_train_by_kind=dict(collections.Counter(m["kind"] for m in acc_meta)),
            added_to_train_readback_consistent=sum(m["readback_consistent"] is True for m in acc_meta),
            added_to_train_readback_inconsistent=sum(m["readback_consistent"] is False for m in acc_meta),
            added_to_train_starts_with_style_label=sum(bool(m["starts_with_style_label"]) for m in acc_meta),
            added_to_train_starts_with_style_label_by_curriculum={c: sum(bool(m["starts_with_style_label"]) and m["curriculum"] == c for m in acc_meta) for c in CURRICULA},
            added_to_train_repaired=sum(bool(m["repaired"]) for m in acc_meta),
            side_file="round2.jsonl",
            side_file_rows=len(meta),
        ),
        checks=dict(
            v2_train_rows_unchanged_and_first=True,
            v2_rejected_rows_unchanged_and_first=True,
            train_rows=written["train"].num_rows,
            train_rows_from_v2=n2,
            train_rows_from_round2=written["train"].num_rows - n2,
            expression_targets_not_resolving_to_target_json=mismatch,
            **disjoint,
        ),
    )
    save_json(DATASET_V3 / "dataset-stats.json", stats)
    log(
        "build_dataset",
        inputs=[str(DATASET_V2.relative_to(ROOT)), str(CANDIDATES.relative_to(ROOT)), "data/scribe/v3/gate/judged.jsonl"],
        outputs=[str((DATASET_V3 / f).relative_to(ROOT)) for f in [f"{n}.parquet" for n in FILES] + ["round2.jsonl", "dataset-stats.json"]],
        metrics=dict(files={n: files[n]["rows"] for n in FILES}, round2=stats["round2"], checks=stats["checks"]),
        cost_usd=0,
        status="ok",
    )
    print(json.dumps(dict(files={n: files[n]["rows"] for n in FILES}, round2=stats["round2"], checks=stats["checks"]), indent=1))


if __name__ == "__main__":
    main()
