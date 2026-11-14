#!/usr/bin/env bash
set -euo pipefail
test -n "$CRACI_SOURCE_ROOT" && test -n "$CRACI_SOURCE_SHA"
test -n "$CRACI_RECEIPT_DIR" && test -n "$CRACI_HARNESS_ROOT"
test -n "$CRACI_SHARD_INDEX"
[[ "$CRACI_SHARD_INDEX" =~ ^[0-7]$ ]]
test "$(git -C "$CRACI_SOURCE_ROOT" rev-parse HEAD)" = "$CRACI_SOURCE_SHA"
command -v Rscript
command -v python3
out="$RUNNER_TEMP/bahn-offline-$CRACI_SHARD_INDEX"
artifacts="$CRACI_RECEIPT_DIR/artifacts/bahn-offline-$CRACI_SHARD_INDEX"
mkdir -p "$artifacts"
PYTHONDONTWRITEBYTECODE=1 python3 "$CRACI_HARNESS_ROOT/scripts/craci/bahn-offline-sweep.py" \
  --shard "$CRACI_SHARD_INDEX" --shards 8 --seeds-per-shard 10000 --base 700000 --out "$out"
Rscript --vanilla "$CRACI_HARNESS_ROOT/scripts/craci/bahn-calibrate.R" \
  "$out/paired-seeds.csv" "$out/cluster" 3000 > "$artifacts/cluster-analysis.log"
python3 - "$out" "$artifacts" <<'PY'
from pathlib import Path
import csv, hashlib, json, sys, zipfile
src,dst=map(Path,sys.argv[1:])
records=list(csv.DictReader((src/"paired-seeds.csv").open(newline="")))
assert len(records)==10000 and len({int(r["seed"]) for r in records})==10000
proof=json.loads((src/"coverage-proof.json").read_text())
shard=proof["shard"]
assert {int(r["seed"]) for r in records}==set(range(700000+shard*10000,710000+shard*10000))
ci=list(csv.DictReader((src/"cluster"/"cluster-bootstrap.csv").open(newline="")))
assert len(ci)==3 and {x["metric"] for x in ci}=={"baseline","optimizer","paired_delta_pp"}
assert all(x["synthetic_only"]=="TRUE" and x["real_90pct_qualified"]=="FALSE" for x in ci)
proof["paired_seed_csv_sha256"]=hashlib.sha256((src/"paired-seeds.csv").read_bytes()).hexdigest()
proof["cluster_bootstrap_csv_sha256"]=hashlib.sha256((src/"cluster"/"cluster-bootstrap.csv").read_bytes()).hexdigest()
proof["observed_toy_cluster_CIs"]={x["metric"]:[float(x["ci_2_5"]),float(x["ci_97_5"])] for x in ci}
(dst/"coverage-proof.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
with zipfile.ZipFile(dst/f"bahn-10000-offline-shard-{shard}.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    z.write(src/"paired-seeds.csv","paired-seeds.csv")
    for p in sorted((src/"cluster").iterdir()):
        if p.is_file(): z.write(p,"R/"+p.name)
print(json.dumps({k:v for k,v in proof.items() if k not in ("counterexamples_first100","per_level_quotes","per_level_abstentions")},sort_keys=True))
PY
printf 'BAHN: 10000 distinct toy seeds × two policies × 40 offline requests; 8-level heuristic gate and 3000 seed-cluster bootstrap draws; no live Spread or 90pct delivery qualification.\n'
