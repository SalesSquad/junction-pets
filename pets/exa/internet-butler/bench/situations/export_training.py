#!/usr/bin/env python3
"""Export TimeLaw-Situations for training and evaluation, split by clause-template cluster.

Why clusters: a split by provision id leaked. The same rule text appears under several ids (cross-agency
copies in the CFR, a registry "family" that lists reg. 4A inside a reg. 4 group), so "unseen provision" test
items had their clauses in training. Provisions are therefore joined into clusters whenever they share

  - a number-masked clause wording (boilerplate that occurs in more than --boilerplate provisions is ignored
    as a join key, otherwise generic penalty wording would glue everything together),
  - the same CFR title and part, or the same UK/EU instrument,
  - a registry family (`also`),

and whole clusters go to one split: sha1(cluster) -> 15 % test, 10 % valid, 75 % train. A few UK/EU instruments
are sent to test explicitly so the test split has numeric tiers outside the US. A provision contributes at
most --cap items to valid and test, so no single rule dominates the estimate.

Labels: gold is the target clause by full text; exact duplicate clause strings are merged. Each item carries a
label tier from blind recovery by the writer's model family and by other families (`checks`): clean (the
writer and every other family asked recover the gold clause), half (unverified, or the families disagree), none.

Outputs under --out:
  train.jsonl, valid.jsonl, test.jsonl     full items (question, clauses, target, tier, cluster, provision, …)
  situations.parquet, pairs.parquet        the same as tables
  mlx-pointwise/, mlx-listwise/            chat files for MLX-LM (prompts identical to gpu/prompting.py)
  split-report.json                        sizes and a leak check (no masked clause wording is shared across splits)

Usage: python3 bench/situations/export_training.py bench/situations/situations-*.jsonl --out bench/datasets/out/training-v2
"""
import argparse, glob, hashlib, json, os, random, re, sys
from collections import Counter, defaultdict
import pyarrow as pa, pyarrow.parquet as pq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gpu"))
from prompting import QUESTION, CHOICE_QUESTION, LETTERS, choice_content, own, user_content

ap = argparse.ArgumentParser()
ap.add_argument("inputs", nargs="+"); ap.add_argument("--out", required=True)
ap.add_argument("--cap", type=int, default=12, help="most items one provision may contribute to valid or test")
ap.add_argument("--boilerplate", type=int, default=12, help="a masked wording shared by more provisions than this is not a join key")
ap.add_argument("--test-instruments", default="uksi/2015/621,32021R0782,32007R1371,ukpga/2019/4", help="UK/EU instruments held out for test")
a = ap.parse_args()
random.seed(9)
files = sorted({f for pat in a.inputs for f in glob.glob(pat)})
mask = lambda c: re.sub(r"\s+", " ", re.sub(r"[\d$£€,.]+", "#", own(c).lower())).strip()[:300]

def provision(r):
    ref = r["ref"]
    return f"{ref.get('title')}-{ref.get('section')}" if "section" in ref else (ref.get("path") or ref.get("celex") or r["gid"])
def instrument(r):
    ref = r["ref"]
    if "section" in ref:
        return f"cfr-{ref.get('title')}-{ref.get('part')}"
    if ref.get("path"):
        return "/".join(ref["path"].split("/")[:3])
    return ref.get("celex") or r["gid"]

# ---------- load, de-duplicate ----------
KEYS = ["gid", "jurisdiction", "date", "url", "lang", "question", "target", "generatorRecovers", "generator", "style", "voice", "attack", "base_message", "recovers2", "validator2", "split", "source_file", "provision", "cluster", "tier", "verified"]
items, seen = [], set()
for f in files:
    for line in open(f, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        k = (r["question"], r["gid"])
        if k in seen:
            continue
        seen.add(k)
        # merge exact duplicate clause strings, keep the target pointing at the same text
        uniq = list(dict.fromkeys(r["clauses"]))
        r["target"], r["clauses"] = uniq.index(r["clauses"][r["target"]]), uniq
        if len(uniq) < 2:
            continue
        r["source_file"], r["provision"], r["instrument"] = os.path.basename(f), provision(r), instrument(r)
        # Label tier from blind recovery of the gold clause: by the writer's own family (g) and by other model
        # families (`checks` from llm_jobs.mjs merge, plus the older single second pass `recovers2`).
        #   clean  the writer recovers it AND at least one other family was asked AND all of them recover it
        #   half   the writer recovers it but no other family was asked (unverified), or the families disagree
        #   none   nobody recovers it
        g = bool(r.get("generatorRecovers"))
        others = [bool(x) for x in (r.get("checks") or {}).values()] + ([bool(r["recovers2"])] if r.get("recovers2") is not None else [])
        r["verified"] = len(others) > 0
        r["tier"] = "clean" if g and others and all(others) else "half" if g or any(others) else "none"
        for key in KEYS:
            r.setdefault(key, None)
        items.append(r)

# ---------- clusters (union-find over provisions) ----------
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(x, y):
    parent[find(x)] = find(y)

wording = defaultdict(set)
for r in items:
    find(r["provision"])
    union(r["provision"], "inst:" + r["instrument"])
    for extra in (r.get("also") or []):
        union(r["provision"], extra.get("path") or extra.get("celex") or f"{extra.get('title')}-{extra.get('section')}")
    for c in r["clauses"]:
        wording[mask(c)].add(r["provision"])
skipped = 0
for m, provs in wording.items():
    if len(provs) > a.boilerplate:
        skipped += 1
        continue
    provs = sorted(provs)
    for p in provs[1:]:
        union(provs[0], p)
# A cluster is named after its alphabetically first member, so the name (and with it the split) does not depend
# on union order or on Python's per-process string hashing. Earlier exports named it after the union-find root,
# which changed between runs.
members = defaultdict(list)
for x in list(parent):
    members[find(x)].append(x)
canon = {root: min(ms) for root, ms in members.items()}
name = lambda prov: canon[find(prov)]
held = [x for x in a.test_instruments.split(",") if x]
def split_of(r):
    if any(r["instrument"] == h or r["provision"].startswith(h) for h in held):
        return "test"
    h = int(hashlib.sha1(name(r["provision"]).encode()).hexdigest(), 16) % 100
    return "test" if h < 15 else "valid" if h < 25 else "train"
# An explicitly held-out instrument takes its whole cluster with it.
held_clusters = {find(r["provision"]) for r in items if any(r["instrument"] == h or r["provision"].startswith(h) for h in held)}
for r in items:
    r["cluster"] = hashlib.sha1(name(r["provision"]).encode()).hexdigest()[:12]
    r["split"] = "test" if find(r["provision"]) in held_clusters else split_of(r)

# ---------- caps on valid and test ----------
kept, dropped = [], Counter()
count = Counter()
order = list(range(len(items))); random.shuffle(order)
for i in sorted(order, key=lambda i: (items[i]["attack"] is not None, random.random())):  # base messages first
    r = items[i]
    if r["split"] in ("valid", "test"):
        if count[(r["split"], r["provision"])] >= a.cap:
            dropped[r["split"]] += 1
            continue
        count[(r["split"], r["provision"])] += 1
    kept.append(r)
items = kept

# ---------- leak filter and check ----------
# The split rule ignores a few boilerplate wordings shared by many provisions (they would chain everything into
# one cluster), so those can sit on both sides of the split. A stricter key (the wording without its leading
# paragraph labels, boilerplate included) removes every valid or test item that shares a clause wording with
# train, and every valid item that shares one with test. Train is never changed by this step.
leak_key = lambda c: mask(re.sub(r"^(\(([a-z]{1,4}|\d{1,3})\)\s*)+", "", own(c).strip(), flags=re.I))
train_keys = {leak_key(c) for r in items if r["split"] == "train" for c in r["clauses"]}
dropped_by_leak = Counter()
kept = []
for r in items:
    if r["split"] in ("valid", "test") and any(leak_key(c) in train_keys for c in r["clauses"]):
        dropped_by_leak[r["split"]] += 1
        continue
    kept.append(r)
test_keys = {leak_key(c) for r in kept if r["split"] == "test" for c in r["clauses"]}
items = []
for r in kept:
    if r["split"] == "valid" and any(leak_key(c) in test_keys for c in r["clauses"]):
        dropped_by_leak["valid"] += 1
        continue
    items.append(r)
by_split = defaultdict(set)
for r in items:
    for c in r["clauses"]:
        by_split[r["split"]].add(leak_key(c))
leaks = {f"{x}&{y}": len(by_split[x] & by_split[y]) for x, y in (("train", "test"), ("train", "valid"), ("valid", "test"))}
base_leak = len({r["base_message"] or r["question"] for r in items if r["split"] == "train"} & {r["base_message"] or r["question"] for r in items if r["split"] == "test"})

# ---------- write ----------
os.makedirs(a.out, exist_ok=True)
for split in ("train", "valid", "test"):
    with open(f"{a.out}/{split}.jsonl", "w", encoding="utf-8") as f:
        for r in items:
            if r["split"] == split:
                f.write(json.dumps({k: r[k] for k in KEYS} | {"ref": r["ref"], "clauses": r["clauses"], "checks": r.get("checks") or {}}, ensure_ascii=False) + "\n")
pq.write_table(pa.Table.from_pylist([{**{k: r[k] for k in KEYS}, "ref": json.dumps(r["ref"]), "checks": json.dumps(r.get("checks") or {}), "clauses": r["clauses"], "n_clauses": len(r["clauses"])} for r in items]), f"{a.out}/situations.parquet", compression="zstd")
pairs = []
for r in items:
    for i, c in enumerate(r["clauses"]):
        pairs.append({"split": r["split"], "gid": r["gid"], "provision": r["provision"], "cluster": r["cluster"], "tier": r["tier"], "lang": r["lang"], "attack": r["attack"], "situation": r["question"], "clause_idx": i, "clause": c, "label": "yes" if c == r["clauses"][r["target"]] else "no"})
pq.write_table(pa.Table.from_pylist(pairs), f"{a.out}/pairs.parquet", compression="zstd")

counts = {}
for task in ("mlx-pointwise", "mlx-listwise"):
    os.makedirs(f"{a.out}/{task}", exist_ok=True)
    for split in ("train", "valid", "test"):
        if task == "mlx-pointwise":
            rows = [{"messages": [{"role": "user", "content": user_content(p["situation"], p["clause"])}, {"role": "assistant", "content": p["label"]}]} for p in pairs if p["split"] == split and (split != "train" or p["tier"] != "none")]
            if split == "train":  # siblings outnumber the target: repeat "yes" rows to about a third of the rows
                yes = [x for x in rows if x["messages"][1]["content"] == "yes"]; no = [x for x in rows if x["messages"][1]["content"] == "no"]
                rows = no + yes * max(1, round(len(no) / (2 * max(1, len(yes))) + 0.5))
        else:
            rows = []
            for r in items:
                if r["split"] != split or (split == "train" and r["tier"] == "none") or len(r["clauses"]) > len(LETTERS):
                    continue
                o = random.sample(range(len(r["clauses"])), len(r["clauses"])) if split == "train" else list(range(len(r["clauses"])))
                rows.append({"gid": r["gid"], "attack": r["attack"], "tier": r["tier"], "messages": [{"role": "user", "content": choice_content(r["question"], r["clauses"], o)}, {"role": "assistant", "content": LETTERS[o.index(r["target"])]}]})
        random.shuffle(rows)
        with open(f"{a.out}/{task}/{split}.jsonl", "w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        counts[f"{task}/{split}"] = len(rows)

S = lambda s: [r for r in items if r["split"] == s]
report = {
    "files": [os.path.basename(f) for f in files], "items": len(items), "pairs": len(pairs),
    "provisions": len({r["provision"] for r in items}), "clusters": len({r["cluster"] for r in items}), "boilerplate_wordings_ignored": skipped,
    "splits": {s: {"items": len(S(s)), "provisions": len({r["provision"] for r in S(s)}), "clusters": len({r["cluster"] for r in S(s)}), "tiers": dict(Counter(r["tier"] for r in S(s))), "jurisdictions": dict(Counter(r["jurisdiction"] for r in S(s))), "languages": dict(Counter(r["lang"] for r in S(s)))} for s in ("train", "valid", "test")},
    "dropped_by_cap": dict(dropped), "dropped_by_leak": dict(dropped_by_leak), "largest_test_provision_share": round(max(Counter(r["provision"] for r in S("test")).values(), default=0) / max(1, len(S("test"))), 4),
    "leak_check": {"shared_masked_wordings": leaks, "train_test_shared_base_messages": base_leak},
    "attacks": dict(Counter(r["attack"] or "none" for r in items)), "generators": dict(Counter((r["generator"] or "").split("/")[-1] for r in items)), "files_out": counts,
}
json.dump(report, open(f"{a.out}/split-report.json", "w"), indent=1)
json.dump(report, open(f"{a.out}/summary.json", "w"), indent=1)
print(json.dumps({k: report[k] for k in ("items", "provisions", "clusters", "boilerplate_wordings_ignored", "dropped_by_cap", "largest_test_provision_share", "leak_check")}, indent=1))
print(json.dumps({s: {k: v for k, v in report["splits"][s].items() if k in ("items", "provisions", "clusters", "tiers", "jurisdictions")} for s in report["splits"]}, indent=1))
assert all(v == 0 for v in leaks.values()), f"leak: masked clause wordings shared across splits: {leaks}"
