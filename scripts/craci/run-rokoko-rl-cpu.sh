#!/usr/bin/env bash
set -euo pipefail
test -n "$CRACI_SOURCE_ROOT" && test -n "$CRACI_SOURCE_SHA"
test -n "$CRACI_HARNESS_ROOT" && test -n "$CRACI_RECEIPT_DIR"
test "$(git -C "$CRACI_SOURCE_ROOT" rev-parse HEAD)" = "$CRACI_SOURCE_SHA"
dir="$RUNNER_TEMP/rokoko-rl-fresh-cpu-13"
artifacts="$CRACI_RECEIPT_DIR/artifacts/rokoko-rl-cpu"
mkdir -p "$artifacts"
test ! -e "$dir"
"$RUNNER_TEMP/rokoko-rl-venv/bin/python" \
  "$CRACI_SOURCE_ROOT/solutions/rokoko-teleoperation-gym/learning/train.py" \
  --train-episodes 96 --cal-episodes 20 --test-episodes 30 --ood-episodes 20 \
  --max-options 20 --seed 13 --device cpu --max-seconds 480 \
  --source-commit "$CRACI_SOURCE_SHA" --out "$dir"
python3 - "$dir" "$artifacts" "$CRACI_SOURCE_SHA" <<'PY'
import hashlib,json,pathlib,sys,zipfile
src,out,sha=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),sys.argv[3]
r=json.loads((src/"receipt.json").read_text())
assert r["source_commit"]==sha and not r["source_dirty"]
assert r["train_transitions"]>=64
assert r["gradient_steps"]>0
assert r["initial_parameter_sha256"]!=r["final_parameter_sha256"]
assert r["device"]=="cpu" and not r["timed_out"]
assert r["train_episodes"]==96
for split,count in [("cal",20),("test",30),("ood",20)]:
    for method in ("dqn","heuristic","abstain"):
        assert r["summary"][split+"/"+method]["episodes"]==count
assert r["weights_sha256"]==hashlib.sha256((src/"weights.pt").read_bytes()).hexdigest()
assert set(r["quality_claim"] for _ in range(1)) <= {"PASSED_PAIRED_TEST_USEFULNESS","FAILED_OR_UNQUALIFIED"}
proof={"schema":"craci.rokoko-rl-cpu-qualification.v1",
       "source_sha":sha,"device":"cpu","train_episodes":96,
       "gradient_steps":r["gradient_steps"],"train_transitions":r["train_transitions"],
       "physics_steps":r["physics_steps"],"source_bound":True,
       "weight_changed":True,"all_heldout_splits_complete":True,
       "quality_claim":r["quality_claim"],"summary":r["summary"],
       "trained_rl":True,"hardware_safety_qualified":False,"real_robot":False}
(out/"coverage-proof.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
with zipfile.ZipFile(out/"rokoko-rl-cpu-evaluation.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(src.iterdir()):
        if path.is_file(): z.write(path,path.name)
print(json.dumps(proof,sort_keys=True))
PY
printf 'Rokoko Double-DQN trained on CPU with 96 episodes + sealed 20/30/20 paired synthetic holdouts; never equate optimizer steps with winning RL or hardware safety.\n'
