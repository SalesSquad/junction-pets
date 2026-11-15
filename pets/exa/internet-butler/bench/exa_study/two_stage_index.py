#!/usr/bin/env python3
"""Build bench/exa_study/two_stage_index.json: for each of the paired 300 situations, the CFR parts in Exa's
top 5 (rewritten query and raw message) and, for those parts, every amount-bearing section in the edition of
the event year (CFR-Annual focused tables, titles 12, 14, 16, 20, 29 and 49 only).

  .venv-mlx/bin/python bench/exa_study/two_stage_index.py [--tables <dir with clauses.parquet>]
"""
import argparse, json, os, re, statistics
from collections import defaultdict
import pyarrow.parquet as pq

ap = argparse.ArgumentParser()
ap.add_argument("--tables", default=os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Events/Junction-2026/Datasets/cfr-annual-focused"))
a = ap.parse_args()
COVERED = {"12", "14", "16", "20", "29", "49"}
rows = [json.loads(l) for l in open("bench/exa_study/rewrite_discovery_given.jsonl")]
raw = {}
for l in open("bench/exa_study/discovery.jsonl"):
    j = json.loads(l); raw[j["key"]] = j
agent = {}
for l in open("bench/exa_study/agent_discovery.jsonl"):
    j = json.loads(l); agent[j["key"]] = j
sit = {}
for l in open("bench/exa_study/all-situations.jsonl"):  # base messages only, first row wins
    x = json.loads(l)
    if not x.get("attack"):
        sit.setdefault(f"{x['gid']}|{x['question'][:80]}", x)
pat = re.compile(r"ecfr\.gov/.*?title-(\d+)(?:/.*?)?/part-(\d+[A-Za-z]?)", re.I)
def parts(urls):
    out = []
    for u in urls:
        x = pat.search(u)
        if x and (x.group(1), x.group(2)) not in out:
            out.append((x.group(1), x.group(2)))
    return out
need, items = set(), []
for r in rows:
    it = sit[r["key"]]; ref = it["ref"]; year = str(ref.get("edition", it["date"]))[:4]
    pr, ps = parts(r["urls"]), parts(raw[r["key"]]["urls"])
    for t, p in pr + ps:
        need.add((t, p, year))
    items.append({"key": r["key"], "lang": r["lang"], "question": it["question"], "date": it["date"], "query": r["query"],
                  "gold": {"title": str(ref["title"]), "part": str(ref["part"]), "section": str(ref["section"]), "year": year},
                  "rewriteParts": pr, "rawParts": ps, "rewriteSection": r["section"], "rewriteRank": r.get("rank"),
                  "agentSection": agent[r["key"]]["section"], "searchSection": raw[r["key"]]["section"]})
idx = defaultdict(dict)
for c in pq.read_table(a.tables + "/clauses.parquet", columns=["title", "year", "part", "section", "subject", "context", "clause", "kind"]).to_pylist():
    k = (str(c["title"]), str(c["part"]), str(c["year"]))
    if k not in need:
        continue
    s = idx[k].setdefault(str(c["section"]), {"section": str(c["section"]), "subject": c["subject"] or "", "n": 0, "money": 0, "sample": ""})
    s["n"] += 1; s["money"] += c["kind"] == "money"
    if not s["sample"] or (c["kind"] == "money" and "$" not in s["sample"]):
        s["sample"] = ((c["context"] + " … ") if c["context"] else "") + c["clause"]
# A covered title's part with no amount-bearing section gets an empty list, so a missing key means "title not covered".
out = {"|".join(k): sorted(idx[k].values(), key=lambda x: x["section"]) if k in idx else [] for k in need if k[0] in COVERED}
json.dump({"items": items, "parts": out, "coveredTitles": sorted(COVERED)}, open("bench/exa_study/two_stage_index.json", "w"), ensure_ascii=False)
sizes = [len(v) for v in out.values() if v]
print(json.dumps({"items": len(items), "partYearsNeeded": len(need), "inCoveredTitles": len(out), "withSections": len(sizes), "medianSections": statistics.median(sizes), "maxSections": max(sizes)}))
