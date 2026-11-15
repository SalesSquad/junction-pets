#!/bin/zsh
# Spend guard for one Verda GPU job: poll the VM until the job script touches its done marker (gpu/verda/
# vm_run_list.sh touches DONE), copying run.log on every poll; then pull run.log and runs/ and shut the VM down
# through verda-agent. Hard wall-clock limit LIMIT_MIN from the guard's start: on the limit it pulls what exists
# and shuts down. The SSH key stays on this Mac; nothing is uploaded.
#
# Environment:
#   JOB            verda-agent job id (required)
#   LOCAL_JOB_DIR  local directory of this job (default: the current directory); results go to LOCAL_JOB_DIR/out/
#   SSH_CONFIG     ssh config with the VM's Host entry (default: LOCAL_JOB_DIR/ssh_config)
#   VM_HOST        Host alias in SSH_CONFIG (default: verda-vm)
#   VERDA_AGENT    verda-agent executable (default: verda-agent from PATH)
#   LIMIT_MIN      hard limit in minutes (default 75)
#   REMOTE_DIR     job directory on the VM (default /root/job); DONE_FILE (default DONE); POLL_SEC (default 60)
# Usage: JOB=gemma-judge4-... VM_HOST=gemma4-vm LOCAL_JOB_DIR=$HOME/jobs/judge4 zsh gpu/verda/guard.sh
: ${JOB:?set JOB to the verda-agent job id}
LOCAL_JOB_DIR=${LOCAL_JOB_DIR:-$PWD}
SSH_CONFIG=${SSH_CONFIG:-$LOCAL_JOB_DIR/ssh_config}
VM_HOST=${VM_HOST:-verda-vm}
VERDA_AGENT=${VERDA_AGENT:-verda-agent}
LIMIT_MIN=${LIMIT_MIN:-75}
REMOTE_DIR=${REMOTE_DIR:-/root/job}
DONE_FILE=${DONE_FILE:-DONE}
POLL_SEC=${POLL_SEC:-60}
cd "$LOCAL_JOB_DIR" || exit 1
[ -f "$SSH_CONFIG" ] || { echo "no ssh config: $SSH_CONFIG"; exit 1; }
command -v "$VERDA_AGENT" >/dev/null || { echo "verda-agent not found: $VERDA_AGENT"; exit 1; }
# functions, not a string variable such as S="ssh -F ...": zsh does not word-split an unquoted variable
S() { ssh -F "$SSH_CONFIG" "$VM_HOST" "$@"; }
C() { scp -F "$SSH_CONFIG" -q "$@"; }
t0=$(date +%s)
mkdir -p out
pull() {
  C "$VM_HOST:$REMOTE_DIR/run.log" out/ 2>/dev/null
  C -r "$VM_HOST:$REMOTE_DIR/runs" out/ 2>/dev/null
}
over() { [ $(( ($(date +%s) - t0) / 60 )) -ge $LIMIT_MIN ]; }
echo "$(date -u +%FT%TZ) guard start job=$JOB host=$VM_HOST limit=${LIMIT_MIN}min"
while true; do
  if S "test -f $REMOTE_DIR/$DONE_FILE" 2>/dev/null; then echo "$(date -u +%FT%TZ) $DONE_FILE"; pull; break; fi
  if over; then echo "$(date -u +%FT%TZ) LIMIT ${LIMIT_MIN} min reached"; pull; break; fi
  C "$VM_HOST:$REMOTE_DIR/run.log" out/run.log 2>/dev/null
  sleep $POLL_SEC
done
"$VERDA_AGENT" shutdown "$JOB" || echo "$(date -u +%FT%TZ) SHUTDOWN FAILED for $JOB: stop the VM by hand"
echo "guard exit $(date -u +%FT%TZ); pulled: $(ls out/runs 2>/dev/null | tr '\n' ' ')"
