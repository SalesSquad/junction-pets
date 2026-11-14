#!/usr/bin/env bash
set -euo pipefail
test -n "${CRACI_SOURCE_ROOT:-}" && test -n "${CRACI_SOURCE_SHA:-}"
test -n "${CRACI_HARNESS_ROOT:-}" && test -n "${CRACI_RECEIPT_DIR:-}"
case "${CRACI_LEARNER_SEED:-}" in 17|43) ;; *) echo "Unregistered ablation learner" >&2; exit 2;; esac
test "$(git -C "$CRACI_SOURCE_ROOT" rev-parse HEAD)" = "$CRACI_SOURCE_SHA"
test "$CRACI_SOURCE_SHA" = "59479b42b177c1829a2e6678adfff1fb68aef09c"
cutoff_epoch="$(date -u -d "$CRACI_WINDOW_END" +%s)"
remaining="$((cutoff_epoch - $(date -u +%s) - 90))"
test "$remaining" -gt 0
train="$RUNNER_TEMP/rokoko-ablation-train-$CRACI_LEARNER_SEED"
evaldir="$RUNNER_TEMP/rokoko-ablation-eval-$CRACI_LEARNER_SEED"
artifacts="$CRACI_RECEIPT_DIR/artifacts/rokoko-rl-ablations"
mkdir -p "$artifacts"
test ! -e "$train" && test ! -e "$evaldir"
timeout --signal=TERM --kill-after=10 "$remaining" \
  "$RUNNER_TEMP/rokoko-rl-venv/bin/python" \
  "$CRACI_SOURCE_ROOT/solutions/rokoko-teleoperation-gym/learning/train.py" \
  --train-episodes 1000 --cal-episodes 0 --test-episodes 0 --ood-episodes 0 \
  --max-options 60 --seed "$CRACI_LEARNER_SEED" --device cpu --max-seconds 650 \
  --source-commit "$CRACI_SOURCE_SHA" --out "$train"
remaining="$((cutoff_epoch - $(date -u +%s) - 90))"
test "$remaining" -gt 0
timeout --signal=TERM --kill-after=10 "$remaining" \
  "$RUNNER_TEMP/rokoko-rl-venv/bin/python" \
  "$CRACI_HARNESS_ROOT/scripts/craci/rokoko-rl-ablations.py" \
  --source-root "$CRACI_SOURCE_ROOT" --trained "$train" --out "$evaldir" \
  --learner-seed "$CRACI_LEARNER_SEED" --test 300 --ood 200 --max-seconds 850
python3 - "$train" "$evaldir" "$artifacts" "$CRACI_SOURCE_SHA" "$CRACI_LEARNER_SEED" <<'PY'
import hashlib,json,pathlib,sys,zipfile
train,evaldir,out,sha,seed=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),pathlib.Path(sys.argv[3]),sys.argv[4],int(sys.argv[5])
r=json.loads((train/"receipt.json").read_text())
proof=json.loads((evaldir/"report.json").read_text())
assert r["source_commit"]==sha and proof["source_commit"]==sha
assert r["initial_parameter_sha256"]!=r["final_parameter_sha256"]
assert proof["initial_sha256"]==r["initial_parameter_sha256"]
assert proof["trained_sha256"]==r["final_parameter_sha256"]
assert r["gradient_steps"]>0 and r["train_episodes"]==1000
assert not r["timed_out"] and r["device"]=="cpu"
assert proof["learner_seed"]==seed and proof["shared_worlds_paired"]
assert proof["worlds_test"]==300 and proof["worlds_ood"]==200
assert proof["test_seed_range"]==[321000,321299]
assert proof["ood_seed_range"]==[421000,421199]
assert set(proof["methods"])=={"trained_q","untrained_q","push_medium","heuristic","masked_random","abstain"}
assert all(all(proof["results"][split][method]["episodes"]==count for method in proof["methods"]) for split,count in [("fresh_test",300),("fresh_ood",200)])
(out/"coverage-proof.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
with zipfile.ZipFile(out/"rokoko-rl-ablations-cpu-evidence.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in (train/"receipt.json",train/"frozen-config.json",evaldir/"report.json",evaldir/"episodes.csv"):
        z.write(path,path.name if path.parent==evaldir else "trainer-"+path.name)
print(json.dumps({"schema":proof["schema"],"learner_seed":seed,"source_sha":sha,"trained_weight_changed":True,"quality_claim":proof["quality_claim"],"fresh_test":proof["results"]["fresh_test"],"fresh_ood":proof["results"]["fresh_ood"]},sort_keys=True))
PY
