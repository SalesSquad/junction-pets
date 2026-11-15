#!/usr/bin/env bash
# One source-pinned, pre-registered challenge. No physical robot or RL claim.
set -euo pipefail

test "$(git -C "$CRACI_SOURCE_ROOT" rev-parse HEAD)" = "$CRACI_SOURCE_SHA"
task="$CRACI_SOURCE_ROOT/solutions/rokoko-teleoperation-gym/learning/action_necessity"
artifacts="$CRACI_RECEIPT_DIR/artifacts"
mkdir -p "$artifacts"

# Development-only diagnostic is separate from the untouched qualification sets.
python3 "$task/run.py" --split dev --episodes 200 \
  --source-commit "$CRACI_SOURCE_SHA" --output "$artifacts/rokoko-action-development.json"

# Train only on 121000...121199. The algorithm/hyperparameters and code are
# pinned before either locked test/OOD split is read.
python3 "$task/imitation.py" --train-episodes 200 --epochs 3 \
  --eval-split test --eval-episodes 300 \
  --output "$artifacts/rokoko-imitation-locked-test.json"
python3 "$task/imitation.py" --train-episodes 200 --epochs 3 \
  --eval-split ood --eval-episodes 200 \
  --output "$artifacts/rokoko-imitation-locked-ood.json"

python3 - "$artifacts" <<'ROKOKO_SCORE'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1]); read = lambda name: json.loads((root/name).read_text())
test = read('rokoko-imitation-locked-test.json')
ood = read('rokoko-imitation-locked-ood.json')
assert test['weights_sha256'] == ood['weights_sha256'], 'Two splits used different fitted models'
assert test['training'] == ood['training'], 'Training changed between locked splits'
assert test['validation']['split'] == 'test' and test['validation']['episodes'] == 300
assert ood['validation']['split'] == 'ood' and ood['validation']['episodes'] == 200
test_pass = test['validation']['learned_action_necessity_demo']
ood_safe = ood['validation']['learned']['unsafe'] <= ood['validation']['constant']['unsafe']
result = {
    'schema': 'craci.rokoko.locked-imitation-qualification.v1',
    'scope': 'SYNTHETIC_2D_KINEMATICS_BEHAVIOR_CLONING_NOT_RL_OR_MUJOCO',
    'method': 'train fixed 200 synthetic teacher episodes, 3 epochs, then untouched heldout test/OOD',
    'same_frozen_model_sha256': test['weights_sha256'],
    'test': {k: test['validation'][k] for k in ('learned','teacher','constant','fitted_minus_constant')},
    'ood': {k: ood['validation'][k] for k in ('learned','teacher','constant','fitted_minus_constant')},
    'test_accepts_predeclared_15pp_ci_and_safety': test_pass,
    'ood_unsafe_not_higher_than_constant': ood_safe,
    'qualification_passed': bool(test_pass and ood_safe),
    'limits': 'Never infer MuJoCo, reinforcement-learning or physical robot safety from this benchmark.',
}
with (root/'rokoko-locked-verdict.json').open('x') as stream:
    json.dump(result, stream, sort_keys=True, indent=2)
print(json.dumps(result, sort_keys=True))
if not (test_pass and ood_safe):
    raise SystemExit('Predeclared locked qualification failed; preserve source-bound negative evidence')
ROKOKO_SCORE
