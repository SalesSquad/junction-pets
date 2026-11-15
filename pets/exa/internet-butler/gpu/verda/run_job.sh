#!/bin/zsh
# One Verda GPU round end to end, from this Mac (the SSH key never leaves it):
#  1) every POLL_SEC seconds, at most POLL_TRIES times, submit one job through verda-agent when a preferred GPU type
#     is in stock; stop at once on any provider answer that is not a clean "not available" (outcome unknown means:
#     never reuse the job id, run `verda-agent doctor`);
#  2) wait for the VM's IP and SSH; 3) upload INPUTS (paths relative to LOCAL_JOB_DIR) to REMOTE_DIR and start
#     RUN_SCRIPT there detached; 4) spend guard: pull REMOTE_DIR/run.log and REMOTE_DIR/runs when DONE_FILE appears
#     or LIMIT_MIN after launch, then shut the VM down through verda-agent.
# Usage (example: the round-4 LK3 job):
#   LOCAL_JOB_DIR=~/jobs/lk3 SPEC_BASE=~/jobs/spec.json SSH_KEY=~/.ssh/id_verda AGENT=claude-gemma-judge \
#   JOB_PREFIX=gemma-judge4-20261115 RUN_SCRIPT=vm_run_list.sh \
#   INPUTS="train.jsonl valid.jsonl test.jsonl train.nemo.jsonl train.fi_aug.jsonl train_list.py prune inputs.sha256 vm_run_list.sh" \
#   zsh gpu/verda/run_job.sh
# SPEC_BASE is a verda-agent job spec (ssh_key_id, os_volume_gib, source_commit, input_sha256, ...); instance_type,
# location and image are filled in per try. Writes LOCAL_JOB_DIR/{spec.json, ssh_config, known_hosts, job.txt, out/}.
setopt pipefail
: ${LOCAL_JOB_DIR:?} ${SPEC_BASE:?} ${SSH_KEY:?} ${AGENT:?} ${JOB_PREFIX:?} ${RUN_SCRIPT:?} ${INPUTS:?}
VA=${VERDA_AGENT:-verda-agent}; V=${VERDA:-verda}
POLL_TRIES=${POLL_TRIES:-40}; POLL_SEC=${POLL_SEC:-180}; LIMIT_MIN=${LIMIT_MIN:-100}
REMOTE_DIR=${REMOTE_DIR:-/root/job}; DONE_FILE=${DONE_FILE:-DONE}; VM_HOST=${VM_HOST:-verda-job-vm}
# preferred types, best first, as "type:image"; CC types need the CC image
PREF=${PREF:-"1RTXPRO6000.30V.CC:24.04.cuda13.4.cc 1RTXPRO6000.30V:24.04.cuda12.9 1A100.22V:24.04.cuda12.9 1H100.80S.30V:24.04.cuda12.9 1L40S.20V:24.04.cuda12.9 1RTX6000ADA.10V:24.04.cuda12.9"}
cd "$LOCAL_JOB_DIR" || exit 2
log() { echo "$(date -u +%FT%TZ) $*"; }
S() { ssh -F ssh_config "$VM_HOST" "$@"; }   # a function, never a string variable: zsh does not word-split "$S"
JOB=""; IID=""
for n in $(seq 1 $POLL_TRIES); do
  pick=$($V --agent availability 2>/dev/null | PREF="$PREF" python3 -c "
import json, os, sys
d = json.load(sys.stdin)
for item in os.environ['PREF'].split():
    t, img = item.split(':', 1)
    for x in d:
        if t in (x.get('instance_types') or []):
            print(t, x['location_code'], img); raise SystemExit
")
  if [ -n "$pick" ]; then
    t=${pick%% *}; rest=${pick#* }; loc=${rest%% *}; img=${rest#* }
    T="$t" L="$loc" I="$img" B="$SPEC_BASE" python3 -c "
import json, os
s = json.load(open(os.environ['B'])); s.update(instance_type=os.environ['T'], location=os.environ['L'], image=os.environ['I'])
json.dump(s, open('spec.json', 'w'), indent=1)"
    JOB=$JOB_PREFIX-p$n
    out=$($VA submit --job-id "$JOB" --agent "$AGENT" --spec spec.json 2>&1)
    log "try=$n $t $loc $img $out"
    case "$out" in
      *not-available*) JOB="" ;;
      *'"instance_id"'*) IID=$(echo "$out" | python3 -c "import sys, json; print(json.load(sys.stdin)['job']['instance_id'])"); break ;;
      *) log "STOP: ambiguous submit outcome for $JOB (run: $VA doctor)"; exit 2 ;;
    esac
  else
    log "try=$n no preferred GPU in stock"
  fi
  sleep $POLL_SEC
done
[ -n "$IID" ] || { log "gave up after $POLL_TRIES tries"; exit 1; }
log "submitted $JOB instance $IID"
echo "$JOB $IID" > job.txt
IP=""
for i in $(seq 1 40); do
  IP=$($V --agent vm list 2>/dev/null | IID="$IID" python3 -c "
import json, os, sys
d = json.load(sys.stdin); d = d.get('data', d) if isinstance(d, dict) else d
for x in d:
    if x.get('id') == os.environ['IID'] and x.get('ip'):
        print(x['ip']); break")
  [ -n "$IP" ] && break; sleep 15
done
[ -n "$IP" ] || { log "no IP; shutting down"; $VA shutdown "$JOB"; exit 3; }
cat > ssh_config <<EOF
Host $VM_HOST
  HostName $IP
  User root
  IdentityFile $SSH_KEY
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile $LOCAL_JOB_DIR/known_hosts
  ConnectTimeout 10
  ServerAliveInterval 30
EOF
for i in $(seq 1 40); do S true 2>/dev/null && break; sleep 15; done
S "mkdir -p $REMOTE_DIR" && scp -F ssh_config -q -r ${=INPUTS} "$VM_HOST:$REMOTE_DIR/" \
  && S "cd $REMOTE_DIR && chmod +x $RUN_SCRIPT && (nohup setsid ./$RUN_SCRIPT > /dev/null 2>&1 < /dev/null &); sleep 3; head -3 run.log" \
  || { log "launch failed; shutting down"; $VA shutdown "$JOB"; exit 4; }
log "launched on $IP"
t0=$(date +%s); mkdir -p out
pull() { scp -F ssh_config -q "$VM_HOST:$REMOTE_DIR/run.log" out/ 2>/dev/null; scp -F ssh_config -q -r "$VM_HOST:$REMOTE_DIR/runs" out/ 2>/dev/null; }
while true; do
  if S "test -f $REMOTE_DIR/$DONE_FILE" 2>/dev/null; then log "DONE"; pull; break; fi
  if [ $(( ($(date +%s) - t0) / 60 )) -ge $LIMIT_MIN ]; then log "LIMIT $LIMIT_MIN min"; pull; break; fi
  scp -F ssh_config -q "$VM_HOST:$REMOTE_DIR/run.log" out/run.log 2>/dev/null
  sleep 60
done
$VA shutdown "$JOB" || log "WARNING: shutdown of $JOB failed; run $VA doctor"
log "shutdown requested for $JOB; pulled: $(ls out/runs 2>/dev/null | tr '\n' ' ')"
