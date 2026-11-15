#!/usr/bin/env python3
"""Offline scoring for the Gemma judge: no network, no paid calls.

1. student-alone accuracy: argmax P(yes) over each test situation's clauses vs the gold `target`;
2. cache coverage: whether bench/datasets/out/training/test.judgments.jsonl already holds every
   (jev|luna, situation, clause) key, so tournament.mjs would make no API calls.
Exit code 0 when coverage is complete, 3 when the tournament must NOT run.
"""
import json, sys
from collections import Counter

D = sys.argv[1]
student_file = sys.argv[2]
items = [json.loads(l) for l in open(f"{D}/test.jsonl") if l.strip()]
student = {}
for l in open(student_file):
    if l.strip():
        j = json.loads(l)
        student[j["k"]] = j["p"]
cache = set()
for l in open(f"{D}/test.judgments.jsonl"):
    if l.strip():
        cache.add(json.loads(l)["k"])

ok = 0
missing_student = 0
by_attack = Counter(); by_attack_ok = Counter()
missing_cache = 0
for it in items:
    cs = it["clauses"]
    ps = []
    for c in cs:
        k = f"student|{it['question']}|{c}"
        if k not in student:
            missing_student += 1
        ps.append(student.get(k, 0.0))
        for judge in ("jev", "luna"):
            if f"{judge}|{it['question']}|{c}" not in cache:
                missing_cache += 1
    best = max(range(len(ps)), key=lambda i: ps[i]) if ps else -1
    hit = best == it["target"]
    ok += hit
    attack = str(it.get("attack") or "none")
    by_attack[attack] += 1; by_attack_ok[attack] += hit

result = {
    "situations": len(items),
    "student_alone_accuracy": round(ok / max(1, len(items)), 4),
    "missing_student_keys": missing_student,
    "missing_cloud_cache_keys": missing_cache,
    "by_attack": {a: round(by_attack_ok[a] / by_attack[a], 3) for a in sorted(by_attack)},
}
print(json.dumps(result, indent=1))
sys.exit(0 if missing_cache == 0 else 3)
