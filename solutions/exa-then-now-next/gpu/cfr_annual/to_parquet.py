#!/usr/bin/env python3
"""CFR-Annual, stage 3: Parquet tables (zstd) for analysis, benchmarks and training.

  sections.parquet  one row per section-year that states an amount (full text, official bulk URL, zip SHA-256)
  clauses.parquet   one row per amount-bearing clause per year (context chain, amount, series_id)
  series.parquet    one row per series (same section, same wording with numbers masked): its values by year
  changes.parquet   one row per change between consecutive editions (old -> new, edition dates)

A series is a clause whose wording stays the same while its numbers change, which is the unit a time-aware
answer must track. Partitioned files are not needed at this size; each table is a single zstd Parquet file.

Usage: python3 to_parquet.py --sections sections-focused.jsonl.gz --clauses clauses-focused.jsonl.gz --out parquet/focused
"""
import argparse, gzip, json, os
from collections import defaultdict
import pyarrow as pa, pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("--sections", required=True); ap.add_argument("--clauses", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def write(name, records):
    if not records:
        return 0
    t = pa.Table.from_pylist(records)
    pq.write_table(t, f"{a.out}/{name}.parquet", compression="zstd", compression_level=9, use_dictionary=True)
    return t.num_rows

n_sections = write("sections", list(rows(a.sections)))
clauses = list(rows(a.clauses))
n_clauses = write("clauses", clauses)

# Series: per series_id, one value per edition year (the first clause of that series in the section that year).
by = defaultdict(dict)
meta = {}
for c in clauses:
    by[c["series_id"]].setdefault(c["year"], c)
    meta.setdefault(c["series_id"], c)
series, changes = [], []
for sid, years in by.items():
    ys = sorted(years)
    vals = [years[y]["amount_text"] for y in ys]
    m = meta[sid]
    n_changes = 0
    for y_prev, y in zip(ys, ys[1:]):
        p, c = years[y_prev], years[y]
        if p["amount_value"] != c["amount_value"] or p["unit"] != c["unit"]:
            n_changes += 1
            changes.append({"series_id": sid, "title": m["title"], "part": m["part"], "section": m["section"], "subject": m["subject"],
                            "template": m["template"], "year_from": y_prev, "year_to": y, "edition_from": p["edition"], "edition_to": c["edition"],
                            "old_amount": p["amount_text"], "new_amount": c["amount_text"], "old_value": p["amount_value"], "new_value": c["amount_value"],
                            "unit": c["unit"], "gap_years": y - y_prev, "clause_to": c["clause"], "source_url_to": c["source_url"],
                            # Plausible: same unit and kind, and the amount moved by a factor between 0.5 and 3. Implausible
                            # rows are usually extraction artefacts ("$15.445" read as a decimal, a percent tier meeting a
                            # dollar tier); keep them out of gold labels.
                            "ratio": round(c["amount_value"] / p["amount_value"], 4) if p["amount_value"] else None,
                            "plausible": p["unit"] == c["unit"] and p["kind"] == c["kind"] and bool(p["amount_value"]) and 0.5 <= c["amount_value"] / p["amount_value"] <= 3})
    series.append({"series_id": sid, "title": m["title"], "part": m["part"], "section": m["section"], "subject": m["subject"], "template": m["template"],
                   "first_year": ys[0], "last_year": ys[-1], "n_years": len(ys), "n_changes": n_changes, "years": ys, "amounts": vals,
                   "unit": m["unit"], "kind": m["kind"]})
n_series = write("series", series)
n_changes = write("changes", changes)
summary = {"sections": n_sections, "clauses": n_clauses, "series": n_series, "series_that_changed": sum(1 for s in series if s["n_changes"]),
           "changes": n_changes, "plausible_changes": sum(1 for c in changes if c["plausible"]), "bytes": {f: os.path.getsize(f"{a.out}/{f}") for f in os.listdir(a.out)}}
json.dump(summary, open(f"{a.out}/summary.json", "w"), indent=1)
print(json.dumps(summary))
