#!/usr/bin/env python3
"""Date-blind study, step 1: dated fill-in questions from the CFR-Annual change tables (no language model).

Each question names a US regulation section, a date (the "revised as of" date of an annual edition, 2017 or
later so the eCFR versioner can confirm it) and one clause with its amount blanked. Gold is the amount in
that edition; the trap is the amount in the latest edition of the same series. Only plausible changes are used,
at most --per-section per section, spread over titles.

Usage: python3 bench/exa_study/build_questions.py --data "<iCloud>/Events/Junction-2026/Datasets" --n 1500 --out bench/exa_study/questions.jsonl
"""
import argparse, json, random, re
from collections import defaultdict
import pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True); ap.add_argument("--n", type=int, default=1500); ap.add_argument("--out", required=True)
ap.add_argument("--per-section", type=int, default=3); ap.add_argument("--min-year", type=int, default=2017)
a = ap.parse_args()
random.seed(17)

rows = []
for name in ("cfr-annual-focused", "cfr-annual-cmp"):
    changes = pq.read_table(f"{a.data}/{name}/changes.parquet").to_pylist()
    series = {s["series_id"]: s for s in pq.read_table(f"{a.data}/{name}/series.parquet").to_pylist()}
    for c in changes:
        s = series[c["series_id"]]
        latest = s["amounts"][-1]
        if not c.get("plausible") or c["year_from"] < a.min_year or c["unit"] != "USD":
            continue
        if c["old_amount"] == latest or c["new_amount"] not in c["clause_to"]:
            continue
        clause = c["clause_to"].replace(c["new_amount"], "____", 1)
        if "$" in clause.replace("____", "") and len(re.findall(r"\$\s?\d", clause)) > 3:
            continue  # tables of many amounts make a poor single question
        i = clause.index("____")
        lo, hi = max(0, i - 260), min(len(clause), i + 160)
        excerpt = ("… " if lo else "") + clause[lo:hi].strip() + (" …" if hi < len(clause) else "")
        rows.append({
            "id": f"{c['title']}-{c['section']}-{c['year_from']}-{c['series_id'][:6]}", "dataset": name, "title": c["title"], "part": c["part"], "section": c["section"], "subject": c["subject"],
            "date": c["edition_from"], "gold": c["old_amount"], "next": c["new_amount"], "latest": latest, "latest_year": s["last_year"], "template": c["template"],
            "question": f"Under {c['title']} CFR § {c['section']} ({c['subject'].rstrip('.')}), as in force on {c['edition_from']}, what dollar amount fills the blank in this clause? \"{excerpt}\" Answer with the amount that applied on {c['edition_from']}.",
        })

by_section = defaultdict(list)
for r in rows:
    by_section[(r["title"], r["section"])].append(r)
picked = []
for k, rs in by_section.items():
    random.shuffle(rs)
    picked += rs[: a.per_section]
random.shuffle(picked)
picked = picked[: a.n]
with open(a.out, "w", encoding="utf-8") as f:
    for r in picked:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
titles = defaultdict(int)
for r in picked:
    titles[r["title"]] += 1
print(json.dumps({"candidates": len(rows), "sections": len(by_section), "written": len(picked), "by_title": dict(sorted(titles.items())), "years": sorted({r["date"][:4] for r in picked})}))
