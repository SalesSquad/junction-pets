# ops/verda_job.py: one batch job on a short-lived Verda Cloud machine

`ops/verda_job.py` (Python 3.10+, standard library only) rents a machine, copies a directory to
it, runs one command detached, streams the log, brings the artifacts back and deletes the
machine with its volumes. It replaces the hand-run sequence used three times on 2026-11-14
(rows "Verda V100 spot", "Verda V100 spot" and "Verda A100 spot" in `runs/RUNLOG.md`).

What went wrong by hand that day, and what the tool does about it:

| Seen in | Problem | In the tool |
| --- | --- | --- |
| `runs/RUNLOG.md`, 15:16 row | spot machine reclaimed, nothing usable | reported as `spot_reclaimed`, exit 74, machine and volumes deleted |
| `runs/train.jsonl`, step `gpu_unreachable` | ssh timed out, ping lost | `unreachable` after 6 failed polls in a row, exit 77, machine deleted |
| `.codex-logs/BLOCKER.txt` | ssh host key changed mid-run | own `known_hosts` per run, a changed key is never accepted, exit 77 |
| `.codex-logs/llm-last.txt` | "The machine was left running." | deletion in a `finally` block and on SIGINT/SIGTERM/SIGHUP |

Nothing here is for clinical use; the tool only moves files and runs a command.

## Status: what has been executed and what has not

Executed on 2026-11-14 with verda CLI 1.10.0:

- 36 unit tests against a fake `verda`, `ssh` and `rsync`: all pass (50.272 s, run after the version-2 review fixes; 27 tests and 84.142 s before them).
- Three real `--dry-run`s; the last one is pasted below. Each ran two read-only
  `verda cost estimate` calls and nothing else.
- Read-only checks of real JSON shapes: `vm list`, `vm describe`, `cost estimate`,
  `instance-types`, `vm availability`, `images`, and the error shape for HTTP 400, HTTP 404 and
  a client timeout.
- The ssh option set (with `~` in the key path) against a closed loopback port, and the rsync
  flags on a local copy, with the local OpenSSH 10.5p1 and openrsync: both accepted. No ssh or
  rsync connection to a Verda machine was made.

Not executed, so not verified against the real service:

- `verda vm create` and `verda vm delete` have never been called by this tool or while writing
  it. The JSON that `vm create` prints, the body of the HTTP 503 answer, the exact status
  string of a reclaimed spot machine and the effect of `--with-volumes` are modelled in the
  fake from the CLI help and the task brief. The tool is written to tolerate other shapes
  (see "Create outcomes"), but the first real run should be watched, and `sweep` run after it.
- `--wait=false` on `vm create` is taken from the help text (`--wait` is a boolean flag,
  default true); it has not been sent to the API.

## Use

Run from the solution directory (`solutions/astrazeneca-care-equity`). Discover the values
first; instance types, locations and image slugs change and differ per type. All read-only:

```bash
verda --agent instance-types --gpu -o json              # type name, price_per_hour, spot_price (the type field is `instance_type` or `name`;
                                                        # no run log records which: read it from the output)
verda --agent vm availability --kind gpu --spot -o json # what is in stock now, with location
verda --agent images --type <instance_type> -o json     # field image_type is the --image value
verda --agent ssh-key list -o json                      # field id is the --ssh-key-id value
```

Then dry-run, read the estimate and the commands, and run it for real by removing `--dry-run`:

```bash
python3 ops/verda_job.py run --dry-run \
  --candidate 1V100.4V@FIN-01:spot \
  --candidate 1V100.4V@FIN-01:on-demand \
  --image 24.04.cuda12.9-v100 \
  --ssh-key-id SSH_KEY_ID \
  --ssh-key-path '~/.ssh/id_verda_junction_20261113' \
  --hostname-prefix sama-scribe \
  --copy scribe:scribe \
  --copy data/scribe/dataset-v1:data/scribe/dataset-v1 \
  --exclude .venv --exclude .gpu-venv --exclude .hf-cache --exclude artifacts \
  --exclude __pycache__ --exclude .ruff_cache \
  --remote-dir /root/sama \
  --command 'bash scribe/run_gpu.sh --allow-fallback' \
  --artifact data/scribe/adapter-v1 --artifact data/scribe/eval-v1.json --artifact runs/scribe.jsonl \
  --artifact-exclude checkpoints \
  --max-minutes 90 --budget-usd 3
```

Afterwards, and any time in doubt:

```bash
python3 ops/verda_job.py sweep                 # lists; deletes nothing
python3 ops/verda_job.py sweep --delete-mine   # deletes machines recorded in ops/.state/
```

Main flags of `run` (`python3 ops/verda_job.py run --help` lists all, including the timing knobs):

| Flag | Meaning |
| --- | --- |
| `--candidate TYPE@LOCATION:spot\|on-demand[,image=SLUG][,usd=PRICE]` | repeat; tried in the order given. `image=` overrides `--image` for that candidate, `usd=` states the hourly price instead of looking it up |
| `--kind gpu\|cpu`, `--image`, `--os-volume-gb` (50) | passed to `vm create` as `--kind`, `--os`, `--os-volume-size` |
| `--ssh-key-id`, `--ssh-key-path`, `--ssh-user` (root) | key registered at Verda and the matching private key file |
| `--hostname-prefix` | hostname is `<prefix>-<MMDD-HHMMSS>-<6 hex>-c<n>` |
| `--copy LOCAL_DIR[:SUBDIR]`, `--exclude` | repeat; contents go to `<remote-dir>/<SUBDIR>/` |
| `--remote-dir` (`/root/job`), `--command` or `--command-file` | where and what to run |
| `--artifact PATH`, `--artifact-exclude`, `--artifacts-dir` | repeat; fetched into `ops/artifacts/<run-id>/` by default, `job.log` always |
| `--max-minutes`, `--budget-usd` | both required; caps for the whole run |
| `--dry-run`, `--offline`, `--keep` | see below |
| `--run-log` | default `runs/v2-ops.jsonl` |

## What `run` does, in order

1. **Cost estimate first.** For each candidate it asks
   `verda --agent cost estimate --type T --os-volume N [--spot] -o json` and reads
   `total.hourly`, which includes the OS volume. It prints the price, what the maximum
   wall-clock time would cost and how long the budget lasts. Without a price for every
   candidate a real run refuses to start (exit 2), because the budget cap could not be enforced.
2. **State file** `ops/.state/<run-id>.json` is written before the first create. Each hostname
   is recorded before its create call and each instance id the moment it is known.
3. **Candidates in order.** `vm list`, then `vm create ... --wait=false`. The first machine that
   reaches `status=running` with an ip and answers on ssh is used.
4. **Copy and start.** `mkdir`, `rsync -az` per `--copy`, then a launcher `run.sh` is installed
   and started with `nohup`, all three streams redirected, so the ssh call returns at once.
   The command writes to `~/.verda_job/<run-id>/job.log`; its exit code goes to `exit_code`
   (written to a temporary name and renamed).
5. **Poll** every 20 s over ssh: exit code, whether the process is alive, new log bytes (the
   last 20 new lines are printed). `vm describe` every third poll and after every failed poll.
6. **Fetch** `job.log` and every `--artifact` with rsync, then sha256 each file.
7. **Delete, always.** `verda --agent vm delete <id> --with-volumes --yes --wait ...`, followed
   by a `vm describe` that must answer NOT_FOUND. Up to three attempts.
8. **Run log.** One JSON line appended to `--run-log`.

### Create outcomes

| `vm create` result | Treated as |
| --- | --- |
| success with an id in the output | machine created |
| HTTP 503, or "not enough resources" / "no capacity" in the message | candidate failed, next one; no machine exists |
| other 4xx, `VALIDATION_ERROR`, `MISSING_REQUIRED_FLAGS` | candidate failed, next one |
| `AUTH_ERROR` (not a timeout), `INSUFFICIENT_BALANCE` | whole run stops, exit 70 |
| client timeout, a 5xx other than capacity, success without an id | unknown: the machine may exist. `vm list` is searched for the exact hostname for up to 45 s; found means the machine is used (no second create), not found means next candidate, and the hostname is checked again at cleanup |
| machine becomes `discontinued` (or errors, or disappears) before it is usable | that machine is deleted with its volumes, then the next candidate |
| ssh never answers within 420 s, or the host key changes | same |

### Exit codes

The exit code of the remote command is passed through when the command fails. The tool's own
codes are 70 and above; `metrics.outcome` in the run log says which case it was.

| Exit | Outcome | Meaning |
| --- | --- | --- |
| 0 | `ok` | command exited 0 and every artifact was fetched |
| 1..255 | `remote_failed` | the remote command's own exit code |
| 2 | (usage) | bad arguments, or no price for a candidate |
| 70 | `no_candidate` | no candidate produced a usable machine |
| 71 | `setup_failed` | copy or start failed on a machine that was up |
| 72 | `time_cap` | `--max-minutes` reached |
| 73 | `budget_cap` | `--budget-usd` reached |
| 74 | `spot_reclaimed` | spot machine taken back mid-run; printed in a banner; the command did not fail |
| 75 | `artifact_missing` | command exited 0 but an artifact could not be fetched |
| 76 | (any) | a machine of this run could not be confirmed deleted; overrides every other code |
| 77 | `machine_lost`, `unreachable`, `host_key_changed`, `job_vanished` | the machine or the job went away |
| 78 | `internal_error` | bug in the tool; cleanup still ran |
| 79 | (any) | a create was never confirmed either way, a delete was accepted but no `vm describe` confirmed it, or a machine stayed `discontinued`; the state file is kept, run `sweep`. Overrides every code except 76; the job's own outcome stays in `metrics.outcome` |
| 130, 143, 129 | `signal_SIGINT`, `signal_SIGTERM`, `signal_SIGHUP` | interrupted; cleanup still ran |

After a time cap, budget cap or failed command the tool still fetches `job.log` and whatever
artifacts exist, as long as the machine answers. After a reclaim there is nothing to fetch.
If a reclaimed machine still reports `discontinued` after the delete attempts, that is not
counted as a leak, but the exit code is 79 and its state file is kept so `sweep` checks it
again. Before 2026-11-14 evening (review finding 17 of `runs/review-findings-v2.json`) such
cases, an unconfirmed create and an unconfirmed delete exited 0; they now exit 79 with run-log
status `needs_sweep`.

### Caps and the cost figure

- Time: one deadline for the whole run, counted from the start of the tool, covering
  provisioning attempts as well. Setup steps get a timeout that ends at the deadline.
- Budget: `sum over machines of (seconds from the create call to confirmed deletion) / 3600 x
  hourly price incl. OS volume`. Machines of failed candidates count. The run stops when this
  plus a teardown reserve (`--teardown-reserve-seconds`, default 120 s at the current hourly
  price) reaches the budget.
- The figure in the run log (`cost_usd`) is this estimate, not an invoice. Verda's own billing
  granularity was not checked. Fetching artifacts after a command has finished is bounded by
  `--fetch-timeout-seconds` (900), not by the caps.

### Signals

SIGINT, SIGTERM and SIGHUP are recorded by the handler, which also stops the child process in
flight. The main flow raises once at its next checkpoint and goes to cleanup. During cleanup
further signals are reported and ignored, and the delete call runs in its own session so a
Ctrl-C on the terminal cannot kill it. If the signal arrives while `vm create` is in flight,
cleanup looks the recorded hostname up and deletes the machine if it was created. SIGKILL and
power loss cannot be handled; the state file stays and `sweep` picks it up.

The handler itself writes nothing buffered (one unbuffered write to stderr that may fail). All
terminal output goes through one helper that never raises: if stdout or stderr stops accepting
writes (the reader of a pipe such as `tee` or `head` exited, the terminal was closed, an ssh
session dropped), the rest of the run is written to `ops/.state/<run-id>.log`, and the cleanup,
the state file and the run-log line are unaffected (`metrics.output_redirected_to` names the
file). In the `finally` block the cleanup runs first in its own `try`, each hostname lookup and
each delete in its own `try`, and the state file and run-log line are written before any banner.
Until review finding 12 this was not so: a closed pipe or terminal made the first message of the
`finally` block raise, the machine was not deleted and no run-log line was written.

### `--dry-run`, `--offline`, `--keep`

- `--dry-run` prints every command a real run would execute, with `<instance-id>` and `<ip>`
  as placeholders, and creates, copies and deletes nothing. It does run the read-only price
  lookup so the estimate is real. Add `--offline` to skip that too.
- `--keep` skips the final deletion and prints the instance id, ip, hourly price and the exact
  delete command in a banner. The state file stays with status `kept`. Machines of failed
  candidates are still deleted.

## What gets deleted, and what never does

- `run` deletes only instance ids in its own state file. An id gets there in two ways: from
  the output of the create call, or by finding the exact hostname this run generated (it
  contains six random hex digits and is recorded before the call) on a machine whose id was
  not in `vm list` just before the call. An id read from the create output is only trusted
  once `vm describe` reports this run's hostname for it.
- Every delete, in `run` and in `sweep`, describes the id first. If describe reports a
  different hostname, the id is disowned and never deleted, and the hostname is looked up again
  to find this run's real machine. If an id that was only ever read from create output cannot be
  described, it is not deleted either; it stays on record (exit 76) for `sweep`.
- A create answered with HTTP 503 or a capacity message is not taken as proof that no machine
  exists (the answer may come from a gateway in front of the API). The tool looks the exact
  hostname up for `--refusal-lookup-seconds` (15) before the next candidate, uses the machine if
  it is there, and looks again at cleanup; `sweep` looks such entries up as well. Other 4xx
  refusals answered by the API itself (validation, missing flags, auth, balance) are trusted.
- `verda vm delete` is always called with one explicit id, `--with-volumes` and `--yes`. The
  tool has no code path that passes `--all`, `--hostname` or `--status`.
- Spot machines are created with `--os-volume-on-spot-discontinue delete_permanently`, so a
  reclaim does not leave a billed volume behind.
- After a delete the tool asks `volume describe` for the volume ids it saw on the machine and
  records the answer in the run log (`volumes_after_delete`). It warns but does not delete
  volumes itself.

## `sweep`

Lists every state file in `ops/.state/`, whether the owning process is still alive, and for
each recorded id what `vm describe` says now. For a create that never settled it looks the
recorded hostname up, under the same rule as `run` (exact hostname, id absent before the create
call). Without `--delete-mine` it deletes nothing, state files included. With `--delete-mine`
it deletes those machines with their volumes and removes state files that have nothing left; a run that is still active is skipped unless `--include-active` is
given. A state file written on another host counts as active, because this host cannot tell
whether that run is alive. Exit 0 when nothing of this tool exists any more, 1 when something still does, 3 when
something could not be checked.

A state file exists only while there is something to look at: an active run, `--keep`, a
failed deletion, or a create whose outcome was never confirmed. A clean run removes its own.

## Run-log line

One line per run, same schema as the other `runs/*.jsonl` files:

- `ts`, `step` (`verda_job` or `verda_job_dry_run`), `host`, `command`, `command_sha256`, `status`
  (`ok`, `needs_sweep` or `error`)
- `command` is a redacted preview: values that look like tokens (`dc_`, `hf_`, `sk-`, `nvapi-`,
  `verda_s3_`, `Bearer ...`) are replaced by `[REDACTED]`; `command_sha256` identifies the exact
  text. The dry run prints the launcher with the same masking. The masking is a safety net, not a
  licence: **never put a secret in `--command` or `--command-file`.** The launcher `run.sh` on
  the machine holds the command verbatim. Put secrets in an environment file on the machine (copy
  it with `--copy` from a directory outside the repository, and `source` it in the command).
- `inputs`: run id, candidates, images, copies, caps
- `metrics`: `outcome`, `exit_code`, `remote_exit_code`, `instance_type`, `location`, `spot`,
  `hourly_usd`, `seconds` (lifetime of the machine that ran the job), `wall_seconds`,
  `cost_estimate_usd`, `attempts` (one entry per candidate)
- `outputs.machines`: every machine created, with id, seconds, cost, `deleted`, `delete_calls`
- `outputs.artifacts`: path, bytes and sha256 per file, or `missing` with the reason
- `cost_usd`: the estimate described above

## Tests

```bash
python3 -m unittest discover -s ops/tests
```

`ops/tests/fakes/` holds a fake `verda`, `ssh` and `rsync`; the test puts them first on PATH.
The fake ssh runs the remote command locally in a temporary directory, so the detached start,
the log and exit-code files, polling and artifact fetching run for real. No test opens a
network connection. Every test also checks that each `verda` call is `--agent ... -o json`,
that no delete carries `--all`, `--hostname` or `--status`, that only ids created in that test
are deleted, and that a machine with the same hostname prefix that the tool did not create
survives.

Scripted cases (36 tests): first candidate 503 and the second succeeds; create times out but
the machine exists (no second create); create times out and no machine appears; create
succeeds without an id; machine discontinued while waiting (with and without a second
candidate); remote command fails and its exit code is passed through; shell syntax error in
the command; artifact missing; budget cap; time cap; spot reclaimed mid-run; on-demand
machine lost; SIGTERM and SIGINT during the run; SIGTERM while `vm create` is in flight;
repeated signals during cleanup; delete failing once; delete failing every time; `--keep`
followed by `sweep` and `sweep --delete-mine`; `sweep` against a live run; `--dry-run` and
`--dry-run --offline`; missing price; candidate options; refused create. Added after the
version-2 review: stdout and stderr piped and the reader closed, then SIGINT; only stdout piped
and closed, no signal; a terminal (pty) that goes away mid-run; a 503 although the machine was
created; a 503 with no machine; create output naming a foreign id that cannot be described; a
delete accepted but never confirmed (exit 79); `sweep` against another host's state file; a
token in `--command` kept out of the run log. Eight of these nine fail against the tool as it was
before the fixes; the plain 503 case passed before as well. In each case with a
machine the delete call is asserted to happen exactly once per created id, with
`--with-volumes`.

The fake's error output copies the shape seen from the real CLI (JSON on stderr with
`error.code`, `error.message`, `error.details.status`; exit 4 for an API error, 5 for not
found, 3 for an auth error). Its success output for create and delete, and the text of the
503 body, are assumptions.

## The real dry-run

Run at 2026-11-14 17:17:27 UTC from the solution directory, with the command shown under
"Use". Instance type, location and image come from `instance-types`, `vm availability` and
`images` a few minutes earlier: `1V100.4V` at FIN-01 was the only GPU type under 1 USD/h
listed in stock, spot and on-demand. That is what was available, not a statement that a V100
with 16 GB suits Gemma training; `scribe/README.md` asks for a bf16-capable GPU and that was
not checked here. `SSH_KEY_ID` is a placeholder. An earlier dry-run with the type from the
CLI's own help example (`1V100.6V`) showed that this type is not in the catalog; that run is
in `runs/v2-ops.jsonl` too.

Output, unedited:

```text
[17:17:27Z] $ verda --agent --timeout 60s cost estimate --type 1V100.4V --os-volume 50 --spot -o json
[17:17:29Z] $ verda --agent --timeout 60s cost estimate --type 1V100.4V --os-volume 50 -o json

COST ESTIMATE (nothing has been created yet)
  caps: max wall-clock 90 min, budget 3.00 USD, OS volume 50 GiB, teardown reserve 120 s
   #  candidate                           USD/hour  cost of max wall-clock  budget lasts  binding cap
   1  1V100.4V@FIN-01:spot                  0.1357              0.2035 USD    1326.5 min  time
   2  1V100.4V@FIN-01:on-demand             0.2577              0.3866 USD     698.5 min  time
  planned ceiling for this run: 0.3866 USD = min(budget, hours x hourly price incl. volume of the dearest candidate); candidates are tried in the order given

DRY RUN: nothing is created, copied or deleted. Commands a real run executes, in order.

ssh options of every ssh and rsync command below, shown there as $SSH:
  SSH="ssh -i ~/.ssh/id_verda_junction_20261113 -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=ops/.state/20261114T171727Z-a5134b.known_hosts -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o LogLevel=ERROR"

State file (written before the first create): ops/.state/20261114T171727Z-a5134b.json
Run log line appended to: runs/v2-ops.jsonl

1. Provision: candidates in order, stop at the first machine that answers on SSH.

   candidate 1: 1V100.4V@FIN-01:spot
  $ verda --agent --timeout 60s vm list -o json
      # ids that exist before the create; the new hostname must not be among them
  $ verda --agent --timeout 60s vm create --kind gpu --instance-type 1V100.4V --location FIN-01 --os 24.04.cuda12.9-v100 --hostname sama-scribe-1114-171727-a5134b-c1 --description 'verda_job 20261114T171727Z-a5134b' --ssh-key SSH_KEY_ID --os-volume-size 50 --is-spot --os-volume-on-spot-discontinue delete_permanently --wait=false -o json
      # HTTP 503 / not enough resources -> next candidate; client timeout -> look the hostname up in `vm list` before anything else
  $ verda --agent --timeout 60s vm describe '<instance-id>' -o json
      # every 5 s until status=running with an ip (max 900 s); 'discontinued' -> delete this machine, next candidate
  $ $SSH 'root@<ip>' true
      # until it answers (max 420 s)
  $ verda --agent --timeout 60s vm delete '<instance-id>' --with-volumes --yes --wait --wait-timeout 300s -o json
      # only if this candidate failed after its machine was created

   candidate 2: 1V100.4V@FIN-01:on-demand
  $ verda --agent --timeout 60s vm list -o json
      # ids that exist before the create; the new hostname must not be among them
  $ verda --agent --timeout 60s vm create --kind gpu --instance-type 1V100.4V --location FIN-01 --os 24.04.cuda12.9-v100 --hostname sama-scribe-1114-171727-a5134b-c2 --description 'verda_job 20261114T171727Z-a5134b' --ssh-key SSH_KEY_ID --os-volume-size 50 --wait=false -o json
      # HTTP 503 / not enough resources -> next candidate; client timeout -> look the hostname up in `vm list` before anything else
  $ verda --agent --timeout 60s vm describe '<instance-id>' -o json
      # every 5 s until status=running with an ip (max 900 s); 'discontinued' -> delete this machine, next candidate
  $ $SSH 'root@<ip>' true
      # until it answers (max 420 s)
  $ verda --agent --timeout 60s vm delete '<instance-id>' --with-volumes --yes --wait --wait-timeout 300s -o json
      # only if this candidate failed after its machine was created

2. Copy and start (detached: nohup, log file, exit-code file).
  $ $SSH 'root@<ip>' 'cd "$HOME" && mkdir -p -- /root/sama/scribe /root/sama/data/scribe/dataset-v1 && J="$HOME/.verda_job/20261114T171727Z-a5134b" && mkdir -p "$J"'
  $ rsync -az -e "$SSH" --exclude .venv --exclude .gpu-venv --exclude .hf-cache --exclude artifacts --exclude __pycache__ --exclude .ruff_cache scribe/ 'root@<ip>:/root/sama/scribe/'
  $ rsync -az -e "$SSH" --exclude .venv --exclude .gpu-venv --exclude .hf-cache --exclude artifacts --exclude __pycache__ --exclude .ruff_cache data/scribe/dataset-v1/ 'root@<ip>:/root/sama/data/scribe/dataset-v1/'
  $ $SSH 'root@<ip>' 'J="$HOME/.verda_job/20261114T171727Z-a5134b" && mkdir -p "$J" && cat > "$J/run.sh" && chmod 700 "$J/run.sh"'
      # stdin: the launcher script printed below
  $ $SSH 'root@<ip>' 'J="$HOME/.verda_job/20261114T171727Z-a5134b" && cd "$J" && { nohup bash "$J/run.sh" > /dev/null 2>&1 < /dev/null & echo $! > "$J/pid"; } && echo STARTED'

   launcher script (run.sh):
   | #!/usr/bin/env bash
   | # Generated by ops/verda_job.py for run 20261114T171727Z-a5134b.
   | J="$(cd "$(dirname "$0")" && pwd)"
   | cat > "$J/cmd.sh" <<'VERDA_JOB_EOF_a5134b'
   | bash scribe/run_gpu.sh --allow-fallback
   | VERDA_JOB_EOF_a5134b
   | if ! { cd "$HOME" && cd -- /root/sama; }; then
   |   echo "verda_job: cannot cd to /root/sama" > "$J/job.log"; echo 97 > "$J/exit_code"; exit 97
   | fi
   | bash "$J/cmd.sh" > "$J/job.log" 2>&1 < /dev/null
   | rc=$?
   | echo "$rc" > "$J/exit_code.tmp" && mv "$J/exit_code.tmp" "$J/exit_code"
   | exit "$rc"

3. Poll every 20 s, print new log lines; `vm describe` every 3 polls and after every failed poll.
  $ $SSH 'root@<ip>' 'J="$HOME/.verda_job/20261114T171727Z-a5134b"; if [ -f "$J/exit_code" ]; then echo "EXIT=$(cat "$J/exit_code")"; else echo "EXIT="; fi; if kill -0 "$(cat "$J/pid" 2>/dev/null)" 2>/dev/null; then echo "ALIVE=1"; else echo "ALIVE=0"; fi; S=$(( $(wc -c < "$J/job.log" 2>/dev/null || echo 0) )); echo "SIZE=$S"; echo "----"; if [ "$S" -gt 0 ]; then tail -c +1 "$J/job.log" | head -c $((S-0)) | tail -n 20; fi'
      # the byte offset (0 here) advances with the log
  $ verda --agent --timeout 60s vm describe '<instance-id>' -o json
      # discontinued or not found -> spot_reclaimed (exit 74) for spot, machine_lost (exit 77) otherwise

4. Fetch artifacts (also after a failed command or a time/budget cap, when the machine still answers).
  $ rsync -az -e "$SSH" --exclude checkpoints 'root@<ip>:.verda_job/20261114T171727Z-a5134b/job.log' ops/artifacts/20261114T171727Z-a5134b/
  $ rsync -az -e "$SSH" --exclude checkpoints 'root@<ip>:/root/sama/data/scribe/adapter-v1' ops/artifacts/20261114T171727Z-a5134b/
  $ rsync -az -e "$SSH" --exclude checkpoints 'root@<ip>:/root/sama/data/scribe/eval-v1.json' ops/artifacts/20261114T171727Z-a5134b/
  $ rsync -az -e "$SSH" --exclude checkpoints 'root@<ip>:/root/sama/runs/scribe.jsonl' ops/artifacts/20261114T171727Z-a5134b/

5. Always: finally block, SIGINT/SIGTERM/SIGHUP, time cap, budget cap, spot reclaim.
  $ verda --agent --timeout 60s vm delete '<instance-id>' --with-volumes --yes --wait --wait-timeout 300s -o json
      # only ids recorded in this run's state file
  $ verda --agent --timeout 60s vm describe '<instance-id>' -o json
      # confirmation: expect NOT_FOUND

DRY RUN complete: 0 machines created, 0 deleted.
```

No state file and no artifacts directory were created, and `sweep` afterwards reported no
state files.
