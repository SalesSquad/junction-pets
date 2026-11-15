#!/usr/bin/env bash
set -euo pipefail
: "${CRACI_SOURCE_ROOT:?}"
: "${CRACI_SOURCE_SHA:?}"
: "${CRACI_RECEIPT_DIR:?}"
test "$(git -C "$CRACI_SOURCE_ROOT" rev-parse HEAD)" = "$CRACI_SOURCE_SHA"
command -v Rscript
command -v node
proof="$CRACI_SOURCE_ROOT/solutions/arduino-green-edge/proof"
out="$RUNNER_TEMP/arduino-proof-48"
artifacts="$CRACI_RECEIPT_DIR/artifacts/arduino-proof-48"
mkdir -p "$out" "$artifacts"
node "$proof/generate.mjs" --days=48 > "$out/synthetic-days.csv" 2> "$out/generator.log"
Rscript --vanilla "$proof/analyze.R" "$out/synthetic-days.csv" > "$out/risk-summary.csv" 2> "$out/risk-analysis.log"
Rscript --vanilla "$proof/switchback.R" plan 48 > "$out/switchback-plan.csv" 2> "$out/switchback.log"
python3 - "$out" "$CRACI_SOURCE_SHA" <<'PY'
import csv,hashlib,json,pathlib,sys
out,head=pathlib.Path(sys.argv[1]),sys.argv[2]
def read(p):
    with (out/p).open(newline="") as f:
        return list(csv.DictReader(f))
days=read("synthetic-days.csv")
summary=read("risk-summary.csv")
plan=read("switchback-plan.csv")
assert len(days)==384 and len(summary)==40 and len(plan)==96
assert all(r["evidence"]=="SYNTHETIC" and r["source_sha"]=="7aee5bd372fa32fa92306f0db9fab39bd2ca1567" for r in days)
from collections import Counter
cohorts=Counter((r["partition"],r["scenario"]) for r in days)
assert set(cohorts.values())=={48} and len(cohorts)==8
assert all(r["statistically_qualified"]=="FALSE" and r["physical_measurement"]=="FALSE" for r in summary)
assert set(r["overhead_w"] for r in summary)=={"0","4","8","12","30"}
assert all(r["evidence"]=="PLANNED_NOT_EXECUTED" for r in plan)
assert "GLOBAL_VERDICT=NOT_QUALIFIED" in (out/"risk-analysis.log").read_text()
proof={"status":"verified-synthetic-only","source_sha":head,"parent_model_sha":"7aee5bd372fa32fa92306f0db9fab39bd2ca1567","day_records":384,"strata":8,"per_stratum":48,"risk_rows":40,"switchback_planned_pairs":48,"statistically_qualified":False,"physical_measurement":False,"sha256":{p:hashlib.sha256((out/p).read_bytes()).hexdigest() for p in ["synthetic-days.csv","risk-summary.csv","switchback-plan.csv"]}}
(out/"coverage-proof.json").write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
print(json.dumps(proof))
PY
python3 - "$out" "$artifacts" <<'PY'
import pathlib,shutil,sys,zipfile
src,dst=map(pathlib.Path,sys.argv[1:])
with zipfile.ZipFile(dst/"arduino-48-day-proof.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for name in ("synthetic-days.csv","risk-summary.csv","switchback-plan.csv"):
        archive.write(src/name,name)
shutil.copy2(src/"coverage-proof.json",dst/"coverage-proof.json")
for path in src.glob("*.log"):
    shutil.copy2(path,dst/path.name)
PY
printf 'Arduino: 384 synthetic day records, 40 risk rows, 48 planned/unexecuted switchback pairs; NO energy savings or physical qualification.\n'
