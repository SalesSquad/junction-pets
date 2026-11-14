#!/usr/bin/env bash
set -euo pipefail
: "${CRACI_SOURCE_ROOT:?}"
: "${CRACI_SOURCE_SHA:?}"
: "${CRACI_RECEIPT_DIR:?}"
: "${RUNNER_TEMP:?}"

test "$(git -C "$CRACI_SOURCE_ROOT" rev-parse HEAD)" = "$CRACI_SOURCE_SHA"
megasim="$CRACI_SOURCE_ROOT/solutions/rokoko-teleoperation-gym/mega"
results="$megasim/results"
report="$RUNNER_TEMP/rokoko-heldout-report"
artifacts="$CRACI_RECEIPT_DIR/artifacts/rokoko-heldout"
python="$RUNNER_TEMP/rokoko-venv/bin/python"
test -x "$python"
command -v Rscript
command -v shasum
mkdir -p "$results" "$report" "$artifacts"
pids=()
for shard in 0 1 2 3 4 5 6 7; do
  target="$results/heldout-shard-${shard}.csv"
  test ! -e "$target"
  "$python" "$megasim/experiment.py" \
    --cases 10000 --seed 910000 --shard-count 8 --shard-index "$shard" \
    --output "$target" \
    > "$artifacts/heldout-shard-${shard}.stdout.log" \
    2> "$artifacts/heldout-shard-${shard}.stderr.log" &
  pids+=("$!")
done
failures=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    echo "A MuJoCo shard failed; preserving diagnostics" >&2
    failures=1
  fi
done
test "$failures" = 0

"$python" - "$results" "$artifacts" "$CRACI_SOURCE_SHA" <<'PY'
import csv,hashlib,json,pathlib,sys
results,out,expected=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),sys.argv[3]
policies={"aligned_replay","contact_feedback","guarded_feedback","safe_abstain"}
all_ids=set()
total=0
steps=0
per_policy={x:0 for x in sorted(policies)}
for shard in range(8):
    f=results/f"heldout-shard-{shard}.csv"
    m=results/f"heldout-shard-{shard}.manifest.json"
    record=json.loads(m.read_text())
    assert record["source_commit"]==expected
    assert record["source_kind"]=="SYNTHETIC_MUJOCO"
    assert record["training"]=="NONE: four scripted controllers"
    assert record["actuation_authorized"] is False
    assert (record["total_case_plan"],record["shards"],record["local_shard"],record["seed_base"])==(10000,8,shard,910000)
    assert hashlib.sha256(f.read_bytes()).hexdigest()==record["raw_csv_sha256"]
    observed={}
    with f.open(newline="") as src:
        for row in csv.DictReader(src):
            case=int(row["case_id"])
            assert 0<=case<10000 and case%8==shard
            assert int(row["seed"])==910000+case
            assert row["policy"] in policies
            assert int(row["unsafe_deadman_target_updates"])==0
            observed.setdefault(case,set()).add(row["policy"])
            per_policy[row["policy"]]+=1
            total+=1
    assert len(observed)==1250 and all(x==policies for x in observed.values())
    assert not (set(observed)&all_ids)
    all_ids.update(observed)
    steps+=record["actual_physics_steps"]
    assert (record["actual_independent_scenarios"],record["actual_physics_episodes"],record["actual_physics_steps"])==(1250,5000,15000000)
assert all_ids==set(range(10000))
assert total==40000 and steps==120000000
assert all(n==10000 for n in per_policy.values())
proof={"status":"verified-synthetic-physics","source_sha":expected,"seed_base":910000,"worlds":10000,"shards":8,"physics_episodes":total,"solver_steps":steps,"policy_counts":per_policy,"trained_rl":False,"real_robot":False}
(out/"coverage-proof.json").write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
print(json.dumps(proof))
PY

Rscript --vanilla "$megasim/analyze.R" "$results" '^heldout-shard-[0-7][.]csv$' "$report" 20000
python3 - "$results" "$report" "$artifacts" <<'PY'
import pathlib,sys,zipfile
results,report,out=map(pathlib.Path,sys.argv[1:])
with zipfile.ZipFile(out/"rokoko-10k-worlds.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for shard in range(8):
        for suffix in (".csv",".manifest.json"):
            path=results/f"heldout-shard-{shard}{suffix}"
            archive.write(path,"results/"+path.name)
    for path in sorted(report.iterdir()):
        if path.is_file():
            archive.write(path,"analysis/"+path.name)
print("PRESERVED_FULL_SHA_BOUND_ROKOKO_ARCHIVE")
PY
printf 'Rokoko: 10000 new synthetic MuJoCo worlds, 40000 episodes, 120000000 physics steps; 20000 paired R resamples; NO trained RL or robot integration.\n'
