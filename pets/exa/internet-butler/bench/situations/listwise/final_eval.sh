#!/bin/zsh
# PROTOCOL amendments 2 + 3 (and 5): select on valid, then evaluate once on test. No Nemotron on Finnish rows.
# No paid calls: the tournament runs only when score_offline.py confirms the cloud-judge cache covers every
# test item, and then with --no-cloud.
# Usage (from any directory; the script cd's to its repository's root, and paths are relative to that root):
#   zsh bench/situations/listwise/final_eval.sh POLICY_DIR LK_DIR [B0_JUDGMENTS]
#   e.g. final_eval.sh runs/policy_v4 runs/list4b_kd2p   (the 2026-11-15 post-hoc v4 record)
# Reads (gitignored): bench/datasets/out/training/{valid,test}.jsonl and test.judgments.jsonl (cached cloud
# judgments), judge dirs runs/b0, runs/nemo, LK_DIR, runs/haiku_fi, runs/jev_fi. B0_JUDGMENTS defaults to the
# round-1 B0 test judgments that PROTOCOL.md names, verda/out/gemma4b-group/judgments.jsonl.
set -e
top=$(git -C "${0:A:h}" rev-parse --show-toplevel) || { echo "cannot find the repository root"; exit 2; }
cd "$top"
P=${1:?usage: final_eval.sh POLICY_DIR LK_DIR [B0_JUDGMENTS]}
LK=${2:?usage: final_eval.sh POLICY_DIR LK_DIR [B0_JUDGMENTS]}
B0=${3:-verda/out/gemma4b-group/judgments.jsonl}
P=${P%/}
L=bench/situations/listwise
D=bench/datasets/out/training
[ -f "$B0" ] || { echo "B0 judgments not found: $B0 (pass the round-1 file as the third argument)"; exit 2; }
mkdir -p "$(dirname "$P")"
lines0=$(wc -l < $D/test.judgments.jsonl)
echo "LK dir: $LK"
shasum -a 256 $L/PROTOCOL.md $L/select_policy.py $L/compare.py
python3 $L/select_policy.py --valid $D/valid.jsonl --test $D/test.jsonl --student runs/b0 \
  --teacher runs/nemo --extra lk=$LK --fi-teacher haiku=runs/haiku_fi --fi-teacher jev=runs/jev_fi \
  --out $P > $P.log 2>&1
python3 -c "
import json; r=json.load(open('$P/policy_report.json'))
for k in ('temperatures','valid_full','valid_finnish_only','cv_best','chosen','on_device','cheap_best_le50pct_calls','valid_by_lang','test_teacher_rate'): print(k, json.dumps(r[k]))"
# paired comparison with B0 (full / clean / overlap, McNemar)
for t in chosen on_device best cheap teacher; do
  echo "== $t"; python3 $L/compare.py $B0 $P/$t.judgments.jsonl | tee $P/compare_$t.txt
done
for d in runs/list4b_kd runs/list4b_kd2; do
  if [ -f $d/judgments.jsonl ]; then
    echo "== $d alone (descriptive)"; python3 $L/compare.py $B0 $d/judgments.jsonl | tee $P/compare_$(basename $d).txt
  fi
done
# tournament, cached cloud judgments only
for t in chosen on_device; do
  set +e
  python3 $L/score_offline.py $D $P/$t.judgments.jsonl > $P/score_$t.json 2>&1
  cover=$?
  set -e
  if [ "$cover" = 0 ]; then
    node --experimental-strip-types bench/situations/tournament.mjs $D/test.jsonl --student=$P/$t.judgments.jsonl --no-cloud \
      > $P/tournament_$t.log 2>&1
    python3 -c "
import json; t=open('$P/tournament_$t.log').read(); j=json.loads(t[t.index('{'):t.rindex('}')+1])
print('tournament $t', {k: v for k, v in j['all'].items() if 'student' in k})
print('  Finnish', {k: v for k, v in j['byLanguage']['Finnish'].items() if 'student' in k})"
  else
    echo "tournament $t skipped: cache incomplete"
  fi
done
lines1=$(wc -l < $D/test.judgments.jsonl)
echo "cloud cache lines before=$lines0 after=$lines1"
[ "$lines0" = "$lines1" ] || echo "WARNING: cache grew"
