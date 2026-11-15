#!/bin/sh
# After the Gemma LoRA run: choose the checkpoint on validation, score it and the untrained model on the
# verified test items, and compare every judge in one tournament. No hosted judge is called (cached judgments).
cd "$(dirname "$0")/.." || exit 1
while pgrep -f "[t]rain_mlx_choice.py --model" >/dev/null || pgrep -f "[e]val_mlx_choice.py --model" >/dev/null; do sleep 60; done
D=bench/datasets/out/training-v3
M=mlx-community/gemma-4-e2b-it-4bit
A=adapters/gemma4-e2b-choice
PY=.venv-mlx/bin/python
# The run kept two checkpoints: the best on its 200 selection items (none of them attacked) and the last one.
# Choose between them on the whole verified validation split, never on the test items.
mkdir -p $A-last && cp $A/adapter_config.json $A-last/ && cp $A/last.safetensors $A-last/adapters.safetensors
for X in $A $A-last; do
  $PY gemma/eval_mlx_choice.py --model $M --adapter $X --data $D --split valid --tier clean --out runs/$(basename $X).valid.judgments.jsonl > runs/$(basename $X).valid.eval.log 2>&1
done
CHOSEN=$(python3 - <<'PY'
import json
def acc(name):
    t = open(f"runs/{name}.valid.eval.log").read()
    return json.loads(t[t.rindex('{\n "model"'):])["accuracy"]["all"]["acc"]
a, b = acc("gemma4-e2b-choice"), acc("gemma4-e2b-choice-last")
print("adapters/gemma4-e2b-choice-last" if b >= a else "adapters/gemma4-e2b-choice")
open("runs/gemma-checkpoint-choice.json", "w").write(json.dumps({"best_on_200": a, "last": b, "split": "valid, clean tier"}))
PY
)
echo "$CHOSEN" > runs/gemma-chosen-adapter.txt
$PY gemma/eval_mlx_choice.py --model $M --adapter "$CHOSEN" --data $D --split test-indep --out runs/gemma4-e2b-choice.indep.judgments.jsonl > runs/gemma4-e2b-choice.indep.eval.log 2>&1
$PY gemma/eval_mlx_choice.py --model $M --data $D --split test-indep --out runs/gemma4-e2b-zeroshot.indep.judgments.jsonl > runs/gemma4-e2b-zeroshot.indep.eval.log 2>&1
node --experimental-strip-types bench/situations/tournament.mjs $D/test-indep.jsonl --no-cloud \
  --student=gemmaLora:runs/gemma4-e2b-choice.indep.judgments.jsonl,gemmaZero:runs/gemma4-e2b-zeroshot.indep.judgments.jsonl,jevChoice:$D/test-indep.jev-choice.judgments.jsonl,lunaChoice:$D/test-indep.luna-choice.judgments.jsonl,nemotron:$D/test-indep.nemotron.judgments.jsonl \
  "--ensemble=jevChoice+lunaChoice+nemotron;jevChoice+lunaChoice+nemotron+gemmaLora;gemmaLora+nemotron" \
  "--compare=gemmaLora,gemmaZero;gemmaLora,jevChoice;gemmaLora,lunaChoice;gemmaLora,nemotron" > runs/tournament-indep-all.log 2>&1
grep -v "^test-indep.jsonl [0-9]" runs/tournament-indep-all.log > bench/results/tournament-v3-indep-all.json
cat runs/gemma-checkpoint-choice.json; echo; cat runs/gemma-chosen-adapter.txt
grep valid_acc runs/gemma4-e2b-choice.train.log | tail -3
python3 - <<'PY'
import json
r = json.load(open("bench/results/tournament-v3-indep-all.json"))
for k in ("lexical", "gemmaZero", "gemmaLora", "jevChoice", "lunaChoice", "nemotron"):
    print(k, r["all"].get(k))
for k, v in r["all"].items():
    if k.startswith("mean("): print(k, v)
print(json.dumps(r.get("paired"))[:900]); print(json.dumps(r.get("signing"))[:1200])
PY
