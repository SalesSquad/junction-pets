#!/usr/bin/env python3
"""Choice groups for TimeLaw-Situations from CFR-Annual Parquet: one section in one annual edition with 2-16
distinct amount-bearing clauses. Sections whose amounts changed over the years are weighted 3:1, and at most
two editions per section are taken (spread over time), so the set is time-aware and not dominated by long tables.

Usage: python3 groups_from_parquet.py parquet/focused groups-cfr.jsonl --max 1500
"""
import argparse, json, random
from collections import defaultdict
import pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("parquet"); ap.add_argument("out"); ap.add_argument("--max", type=int, default=0, help="0 = all")
ap.add_argument("--per-section", type=int, default=3); ap.add_argument("--prefix", default="cfr")
a = ap.parse_args()
random.seed(3)

clauses = pq.read_table(f"{a.parquet}/clauses.parquet", columns=["title", "part", "section", "subject", "year", "edition", "clause_idx", "context", "clause", "source_url"]).to_pylist()
changed = {(r["title"], r["section"]) for r in pq.read_table(f"{a.parquet}/series.parquet", columns=["title", "section", "n_changes"]).to_pylist() if r["n_changes"]}

by = defaultdict(list)
for c in clauses:
    by[(c["title"], c["section"], c["year"])].append(c)
per_section = defaultdict(list)
for (t, sec, y), cs in by.items():
    cs.sort(key=lambda c: c["clause_idx"])
    distinct = {c["clause"] for c in cs}
    if 2 <= len(distinct) and len(cs) <= 16:
        per_section[(t, sec)].append((y, cs))

# Every distinct version of a section's tiers (same clause set = same version), at most --per-section of them,
# spread over time. A changed section keeps the edition right before and after each change first.
pool = []
for (t, sec), years in per_section.items():
    years.sort()
    versions, seen_sets = [], set()
    for y, cs in years:
        key = tuple(sorted({c["clause"] for c in cs}))
        if key not in seen_sets:
            seen_sets.add(key); versions.append((y, cs))
    if len(versions) > a.per_section:
        step = (len(versions) - 1) / (a.per_section - 1) if a.per_section > 1 else 0
        versions = [versions[round(i * step)] for i in range(a.per_section)]
    for y, cs in versions:
        pool.append((3 if (t, sec) in changed else 1, t, sec, y, cs))
random.shuffle(pool)
if a.max and len(pool) > a.max:
    pool.sort(key=lambda x: -x[0] * random.random())
    pool = pool[: a.max]
groups = []
for w, t, sec, y, cs in pool:
    c0 = cs[0]
    groups.append({
        "gid": f"{a.prefix}-{t}-{sec}-{y}", "jurisdiction": "US", "dataset": a.prefix, "changed": w == 3,
        "ref": {"source": "ecfr", "title": t, "part": c0["part"], "section": sec, "edition": c0["edition"]},
        "date": c0["edition"], "url": c0["source_url"], "title": f"{t} CFR {sec} {c0['subject']}".strip(),
        "clauses": [f"{c['context']} … {c['clause']}" if c["context"] else c["clause"] for c in cs],
    })
with open(a.out, "w") as f:
    for g in groups:
        f.write(json.dumps(g, ensure_ascii=False) + "\n")
print(json.dumps({"sections_with_tiers": len(per_section), "changed_sections": len(changed), "groups": len(groups), "changed_groups": sum(g["changed"] for g in groups), "titles": sorted({g["ref"]["title"] for g in groups})}))
