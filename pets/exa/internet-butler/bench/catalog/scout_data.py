#!/usr/bin/env python3
"""Scout: data facts for the semantic catalog (read only, no embedding).

Usage: .venv-catalog/bin/python bench/catalog/scout_data.py
Writes bench/catalog/out/scout_data.json and prints it.
"""
import collections
import json
import os
import resource
import statistics

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.environ.get(
    "CFR_DATA",
    "/Users/mikaelervamaa/Library/Mobile Documents/com~apple~CloudDocs/Events/Junction-2026/Datasets/cfr-annual-focused",
)
OUT = os.path.join(ROOT, "bench", "catalog", "out", "scout_data.json")


def js_slice(s: str, n: int) -> str:
    """JavaScript String.prototype.slice(0, n) counts UTF-16 code units."""
    return s.encode("utf-16-le")[: 2 * n].decode("utf-16-le", errors="ignore")


facts = {}

# ---- clauses.parquet -------------------------------------------------------------------------
t = pq.read_table(f"{DATA}/clauses.parquet", columns=["title", "year", "edition", "part", "section", "kind"])
facts["clauses_rows"] = t.num_rows
title = t["title"].to_pylist()
year = t["year"].to_pylist()
section = t["section"].to_pylist()
part = t["part"].to_pylist()
edition = t["edition"].to_pylist()
kind = t["kind"].to_pylist()
del t

newest = {}
for ti, y in zip(title, year):
    if y > newest.get(ti, 0):
        newest[ti] = y
all_secs = collections.defaultdict(set)
new_secs = collections.defaultdict(set)
all_parts = collections.defaultdict(set)
new_parts = collections.defaultdict(set)
sec_years = collections.defaultdict(set)
new_edition = {}
new_rows = collections.Counter()
for ti, y, s, p, e in zip(title, year, section, part, edition):
    all_secs[ti].add(s)
    all_parts[ti].add(p)
    sec_years[(ti, s)].add(y)
    if y == newest[ti]:
        new_secs[ti].add(s)
        new_parts[ti].add(p)
        new_edition[ti] = e
        new_rows[ti] += 1
facts["clauses"] = {
    "titles": sorted(newest),
    "year_range": [min(year), max(year)],
    "newest_edition_per_title": {str(k): {"year": newest[k], "edition": new_edition[k]} for k in sorted(newest)},
    "distinct_title_section_newest_per_title": {str(k): len(new_secs[k]) for k in sorted(newest)},
    "distinct_title_section_newest_total": sum(len(v) for v in new_secs.values()),
    "clause_rows_newest_per_title": {str(k): new_rows[k] for k in sorted(newest)},
    "clause_rows_newest_total": sum(new_rows.values()),
    "distinct_title_section_all_years_per_title": {str(k): len(all_secs[k]) for k in sorted(newest)},
    "distinct_title_section_all_years_total": sum(len(v) for v in all_secs.values()),
    "distinct_title_part_newest_total": sum(len(v) for v in new_parts.values()),
    "distinct_title_part_all_years_total": sum(len(v) for v in all_parts.values()),
    "distinct_title_section_year_total": sum(len(v) for v in sec_years.values()),
    "kind_counts": dict(collections.Counter(kind).most_common()),
}
clause_secs_all = {(ti, s) for ti, ss in all_secs.items() for s in ss}
clause_secs_new = {(ti, s) for ti, ss in new_secs.items() for s in ss}
del title, year, section, part, edition, kind

# ---- text lengths (words) on a strided sample, to size "short documents" ---------------------
t = pq.read_table(f"{DATA}/clauses.parquet", columns=["subject", "context", "clause"])
n = t.num_rows
idx = list(range(0, n, 97))
samp = t.take(idx)
del t


def words(col):
    w = sorted(len((x or "").split()) for x in samp[col].to_pylist())
    return {"median": w[len(w) // 2], "p90": w[int(len(w) * 0.9)], "p99": w[int(len(w) * 0.99)], "max": w[-1]}


facts["clause_word_lengths_sample"] = {"n": len(idx), "subject": words("subject"), "context": words("context"), "clause": words("clause")}
del samp

# ---- sections.parquet (keys only; never read the text column) --------------------------------
t = pq.read_table(f"{DATA}/sections.parquet", columns=["title", "year", "section"])
facts["sections_rows"] = t.num_rows
st, sy, ss = t["title"].to_pylist(), t["year"].to_pylist(), t["section"].to_pylist()
del t
s_new = {}
for ti, y in zip(st, sy):
    if y > s_new.get(ti, 0):
        s_new[ti] = y
facts["sections"] = {
    "newest_year_per_title": {str(k): s_new[k] for k in sorted(s_new)},
    "distinct_title_section_newest_total": len({(ti, s) for ti, y, s in zip(st, sy, ss) if y == s_new[ti]}),
    "distinct_title_section_all_years_total": len(set(zip(st, ss))),
}
section_years = set(zip(st, ss, sy))
del st, sy, ss

# ---- benchmark items --------------------------------------------------------------------------
keys = {}
with open(os.path.join(ROOT, "bench/exa_study/discovery.jsonl")) as f:
    for line in f:
        if line.strip():
            j = json.loads(line)
            keys[j["key"]] = j
items = {}
rows_matched = 0
with open(os.path.join(ROOT, "bench/exa_study/all-situations.jsonl")) as f:
    for line in f:
        if not line.strip():
            continue
        it = json.loads(line)
        if it.get("attack"):
            continue
        k = f'{it["gid"]}|{js_slice(it["question"], 80)}'
        if k in keys:
            rows_matched += 1
            items.setdefault(k, it)
bench = {
    "discovery_rows": len(keys),
    "matched_unique_keys": len(items),
    "matched_rows_in_all_situations": rows_matched,
    "unmatched_keys": len(set(keys) - set(items)),
}
by_lang = collections.Counter(it["lang"] for it in items.values())
bench["per_language"] = dict(by_lang.most_common())
bench["per_jurisdiction"] = dict(collections.Counter(it["jurisdiction"] for it in items.values()).most_common())
bench["per_source"] = dict(collections.Counter(it["ref"]["source"] for it in items.values()).most_common())
us = [it for it in items.values() if it["ref"]["source"] == "ecfr"]
ed_years = collections.Counter(int(str(it["ref"].get("edition") or it["date"])[:4]) for it in us)
bench["us_edition_years"] = {str(k): ed_years[k] for k in sorted(ed_years)}
bench["us_edition_year_min_max_median"] = [min(ed_years), max(ed_years), int(statistics.median(sorted(ed_years.elements())))]
bench["us_per_title"] = dict(sorted(collections.Counter(str(it["ref"]["title"]) for it in us).items()))
bench["us_distinct_provisions"] = len({it["provision"] for it in us})
bench["non_us_dates"] = sorted({it["date"][:4] for it in items.values() if it["ref"]["source"] != "ecfr"})
bench["question_words_median_per_language"] = {
    lang: int(statistics.median(len(it["question"].split()) for it in items.values() if it["lang"] == lang)) for lang in by_lang
}
# Coverage of the gold provisions by candidate catalogs.
gold = [(int(it["ref"]["title"]), str(it["ref"]["section"]), int(str(it["ref"].get("edition") or it["date"])[:4])) for it in us]
bench["us_gold_in_clauses_any_year"] = sum((t_, s_) in clause_secs_all for t_, s_, _ in gold)
bench["us_gold_in_clauses_newest_edition"] = sum((t_, s_) in clause_secs_new for t_, s_, _ in gold)
bench["us_gold_in_clauses_same_year"] = sum(y_ in sec_years.get((t_, s_), ()) for t_, s_, y_ in gold)
bench["us_gold_in_sections_same_year"] = sum((t_, s_, y_) in section_years for t_, s_, y_ in gold)
bench["us_gold_in_newest_by_language"] = {
    lang: f'{sum((int(it["ref"]["title"]), str(it["ref"]["section"])) in clause_secs_new for it in us if it["lang"] == lang)}/{sum(it["lang"] == lang for it in us)}'
    for lang in by_lang
}
# The Exa arm on the same rows, for the comparison table.
bench["exa_section_hits_by_language"] = {
    lang: f'{sum(keys[k]["section"] for k, it in items.items() if it["lang"] == lang)}/{by_lang[lang]}' for lang in by_lang
}
facts["benchmark"] = bench
facts["peak_rss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(facts, f, indent=1)
print(json.dumps(facts, indent=1))
