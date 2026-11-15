#!/usr/bin/env python3
"""Per-ROW overlap flags for valid and test (replaces the gid-level *_overlap_gids.json of PROTOCOL.md rule 4, which
compare.py collapsed to gids and so marked 393 test rows instead of the 358 the definition flags).

Definition (unchanged from the 2026-11-14 producer): tokset(x) = set of lowercased \\w+ tokens of a clause's own text
(the part after the last " … "). A row is overlap when the token set of its gold clause equals, or has Jaccard >= 0.8
with, the token set of some TRAIN clause (any option of any train group). Exact search with a size + prefix filter on
a fixed rare-first token order, so the result does not depend on the hash seed.
Writes bench/situations/listwise/{valid,test}_overlap_questions.json (the questions of overlap rows; questions are
unique per split). Run from the repository root.
"""
import collections, json, math, re
D = "bench/datasets/out/training"
THR = 0.8
own = lambda c: c.split(" … ")[-1]
tokset = lambda s: frozenset(re.findall(r"\w+", s.lower()))
load = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
train = load(f"{D}/train.jsonl")
sets = list({tokset(own(c)) for r in train for c in r["clauses"]})
df = collections.Counter(w for u in sets for w in u)
order = lambda t: sorted(t, key=lambda w: (df.get(w, 0), w))
plen = lambda n: n - math.ceil(THR * n) + 1 if n else 0
index = collections.defaultdict(list)
for j, u in enumerate(sets):
    for w in order(u)[: plen(len(u))]:
        index[w].append(j)
exact = set(sets)


def best(t):
    if t in exact:
        return 1.0
    cands = set()
    for w in order(t)[: plen(len(t))]:
        cands.update(index.get(w, ()))
    return max((len(t & sets[j]) / max(1, len(t | sets[j])) for j in cands), default=0.0)


for split in ("valid", "test"):
    rows = load(f"{D}/{split}.jsonl")
    assert len({r["question"] for r in rows}) == len(rows), "questions must be unique per split"
    flagged = [r["question"] for r in rows if best(tokset(own(r["clauses"][r["target"]]))) >= THR]
    json.dump(flagged, open(f"bench/situations/listwise/{split}_overlap_questions.json", "w"), ensure_ascii=False)
    print(json.dumps({"split": split, "rows": len(rows), "overlap_rows": len(flagged), "clean_rows": len(rows) - len(flagged)}))
