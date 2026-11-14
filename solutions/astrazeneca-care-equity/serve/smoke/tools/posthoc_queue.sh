#!/usr/bin/env bash
# Post-hoc, validation-only runs of arms that the time-budget planner dropped from the ablation.
# train.py never loads a test split; nothing here changes the frozen selection or the official results.
# usage: posthoc_queue.sh <no start after HH:MM UTC> <hard stop HH:MM UTC> <min free MiB> <arm name> ...
set -uo pipefail
cd /root/scribe-v2
export HF_HOME=/root/scribe-v2/scribe/.hf-cache HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONDONTWRITEBYTECODE=1
PY=scribe/.gpu-venv-v2/bin/python
ART=scribe/v2/artifacts/posthoc
today=$(date -u +%F)
nostart=$(date -u -d "$today $1" +%s); hard=$(date -u -d "$today $2" +%s); minfree="$3"; shift 3
mkdir -p "$ART"
for name in "$@"; do
  now=$(date -u +%s)
  if [ "$now" -ge "$nostart" ]; then echo "SKIP $name: past the start limit $(date -u +%FT%TZ)"; continue; fi
  if pgrep -f "scribe-v3" >/dev/null 2>&1; then echo "SKIP $name: a /root/scribe-v3 job is running, yielding the GPU $(date -u +%FT%TZ)"; continue; fi
  free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
  if [ "$free" -lt "$minfree" ]; then echo "SKIP $name: only $free MiB free on the GPU $(date -u +%FT%TZ)"; continue; fi
  dir=$($PY - "$ART" "$name" <<'PYEOF'
import json, pathlib, sys
sys.path.insert(0, "scribe/v2")
import config as c
art, name = pathlib.Path(sys.argv[1]), sys.argv[2]
ctl = c.control("270m", c.DEFAULT_STEPS, name="A-270m-lora-r16")
arms = {a.name: a for a in c.stage_b(ctl)}
arms["C-format-expression"] = c.stage_c_format(ctl)
arms["C-data-nemotron+haiku"] = c.stage_c_data(ctl)
arms["A-1b-lora-r16"] = c.control("1b", c.DEFAULT_STEPS, name="A-1b-lora-r16")
arms["A-4b-lora-r16"] = c.control("4b", c.DEFAULT_STEPS, name="A-4b-lora-r16")
cfg = arms[name]
cfg.validate()
d = art / f"{cfg.name}-{cfg.config_id}"
d.mkdir(parents=True, exist_ok=True)
(d / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2))
print(d)
PYEOF
)
  [ -n "$dir" ] || { echo "FAIL $name: no config"; continue; }
  left=$(( hard - $(date -u +%s) ))
  cap=$(awk -v s="$left" 'BEGIN{m=(s-200)/60; if(m<1)m=1; printf "%.2f", m}')   # leave ~200 s for validation decoding
  echo "START $name dir=$dir free_mib=$free cap_min=$cap $(date -u +%FT%TZ)"
  timeout -s TERM "${left}s" "$PY" scribe/v2/train.py --config-json "$dir/config.json" --out "$dir" --max-minutes "$cap" >> "$dir/train.log" 2>&1
  echo "END $name exit=$? $(date -u +%FT%TZ)"
done
echo "QUEUE DONE $(date -u +%FT%TZ)"
