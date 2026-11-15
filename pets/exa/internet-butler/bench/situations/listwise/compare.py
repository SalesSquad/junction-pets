#!/usr/bin/env python3
"""Paired comparison of two student judgment files on test (PROTOCOL rule 4).

Reports accuracy on all items, on the clean subset (gold clause without a near-duplicate in train) and on
the overlap subset, the discordant counts, and the two-sided exact McNemar p-value.
Usage (from the repository root): python3 bench/situations/listwise/compare.py BASE.jsonl NEW.jsonl
"""
import json, math, sys
D = 'bench/datasets/out/training'
own = lambda c: c.split(' … ')[-1]
test = [json.loads(l) for l in open(f'{D}/test.jsonl') if l.strip()]
# per-ROW overlap (bench/situations/listwise/overlap_rows.py): one test question per overlapping row; questions are unique per row
_ovl = json.load(open('bench/situations/listwise/test_overlap_questions.json', encoding='utf-8'))
ov = set(_ovl)
assert len(ov) == len(_ovl) and ov <= {r['question'] for r in test}, 'overlap file must hold unique test questions'


def load(p):
    d = {}
    for l in open(p, encoding='utf-8'):
        j = json.loads(l); d[j['k']] = j['p']
    return d


def correct(src):
    out = []
    for r in test:
        ps = [src[f"student|{r['question']}|{c}"] for c in r['clauses']]
        gold = {i for i, c in enumerate(r['clauses']) if own(c) == own(r['clauses'][r['target']])}
        out.append(max(range(len(ps)), key=lambda i: ps[i]) in gold)
    return out


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


A, B = correct(load(sys.argv[1])), correct(load(sys.argv[2]))
res = {}
for name, sel in (('all', lambda r: True), ('clean', lambda r: r['question'] not in ov), ('overlap', lambda r: r['question'] in ov)):
    idx = [i for i, r in enumerate(test) if sel(r)]
    a = sum(A[i] for i in idx); b = sum(B[i] for i in idx)
    only_base = sum(A[i] and not B[i] for i in idx); only_new = sum(B[i] and not A[i] for i in idx)
    res[name] = {'n': len(idx), 'base': round(a / len(idx), 4), 'new': round(b / len(idx), 4),
                 'only_base_right': only_base, 'only_new_right': only_new, 'mcnemar_p': float(f'{mcnemar(only_base, only_new):.2g}')}
print(json.dumps(res, indent=1))
