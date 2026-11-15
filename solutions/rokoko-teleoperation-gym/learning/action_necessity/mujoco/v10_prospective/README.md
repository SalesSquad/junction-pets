# Rokoko V10 — prospective five-way TRAIN-only physics (unpromoted)

Work ID: `J26-ROKOKO-V10-FRESH-PHYSICS-20261114`.

## Preregistered experiment

- Product ancestor: V10 source-only draft `58c972e58575f022f2e97f09612f7c7fb244d4cb` (#206), stacked on reviewed V9/V8/V7. No modification to those historical policies, physics or seven-option shield.
- Use the original MuJoCo **3.3.7**, original **18-dimensional public observation**, exact original **7-bit legal mask**, maximum 60 options and true success + **250-tick dwell**. No simulator emulation, oracle, hidden state, dev, cal, test or OOD.
- Reserved new `515000–515511` **TRAIN-only** seed scan. Deterministically choose the first 128 `abs(initial_observation[7]) < .122` near-corridor and 32 clear-corridor worlds using only initial public observations, without inspecting outcomes.
- Execute **five frozen arms on every one of the identical 160 worlds**: `frozen_v5`, `frozen_v6`, `repeat_left`, `frozen_v8`, `v10_loss_informed` = 800 episodes. Each episode starts with a fresh controller, no online fit, no adaptive seed changes.
- Report *physical* safe goal/dwell counts (near/clear/all), lost frozen-V5/V6 successes, genuinely new V10 safe wins, unsafe/regression counts, 25-mm signed lateral movement and subsequent legal forward reopening, abstention and timeouts. Compare using paired seed/world hashes. A physically poor V10 is a valid scientific **NO GO**.

## Unchanged evidence and limits

- Product writes source-bound `training.json` (all 800 sparse + raw hashes), `full_transitions.jsonl.gz` (all complete original 18D+mask trajectories), `paired-readout.json` and `manifest.json` **exclusively to the fresh private `$RUNNER_TEMP/v10-prospective-private-originals` folder**, outside `CRACI_RECEIPT_DIR`. The legacy independently reviewed V7 qualifier re-verifies every full trace and complete pre-outcome selection scan *in that private folder*; an additional V10 verifier checks *all* original legal masks, each reopen and raw outcome tallies. The existing V7 positive replayer reruns all near-corridor positive TRAIN episodes against genuine MuJoCo and reproduces every frozen policy action. A complementary, disjoint V10 verifier independently re-executes **every claimed clear-corridor safe goal** with exact policy proposals, legal masks, costs, contacts, success and 250-tick dwell. Independent qualifier writes `independent-positive-replay.json`, `independent-clear-goal-replay.json` and `independent-qualification.json` **after** proof.
- Do not truncate original `training.json` when it exceeds **20 MiB**. The immutable private original may be up to the unchanged V7 qualification cap **32 MiB**. Only after full qualification, the new dedicated `scripts/craci/rokoko-mujoco-v10-retain-evidence.py` reads both original file hashes from the frozen source manifest and directly writes exact ZIP-parts plus small source-bound proof files into `CRACI_RECEIPT_DIR/artifacts/rokoko-mujoco-v10-prospective`. **No over-20-MiB original ever appears in the collector tree.** Each archive is verified by exact raw reassembly; *every small independent proof file* also has an SHA-256 pinned in the retention manifest. The original **20 MiB per file / 63 MiB total** limits stay unchanged. The originals remain untouched in private temp until ephemeral job exit. Prior V8 compact JSON was 17.52 MiB for 640 episodes; 800 episodes are projected around **22 MiB** (estimate only, not executed). A **21 MiB original-file synthetic test** passes packing, reassembly, exact SHA, corruption rejection and original retention without exposing its oversized original to the collector.
- Both model checkpoint files are copied byte-for-byte from a source-verified clean checkout into fresh private runner temp. Frozen SHA-256s: V10 `3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d`; V8 `07823dcc52ea85b64e18767e1b1af29e63e3236613598cb349610a6b4fd37dc1`; V8 training receipt `dc22f5538f19ef346d6b9965e7b28beed15e813b4b149ae5711d7dfae1771e73`.
- CRACI wrapper `scripts/craci/rokoko-mujoco-v10-prospective-qualification.py` requires `CRACI_WORKLOAD=rokoko-mujoco-v10-prospective`, pinned product/harness Git SHA, clean git, original MuJoCo/NumPy venv, independent full-trace and policy replay. Its per-run source identity is **not** provider safety attestation. No automatic deployment, merger, model promotion or billing claim.

## Integration gate (owned by sole CRACI harness integrator)

This source-only branch does **not** enable a new GitHub Actions workflow or launch CRACI. After a separate source-independent review, the existing `craci-pilot.yml` owner must explicitly register the workload in the workflow choice list **and** existing `scripts/craci/plan.mjs` finite source admission logic. The separate 4-vCPU MuJoCo job uses the two new byte-identical scripts `rokoko-mujoco-v10-prospective-qualification.py` and `rokoko-mujoco-v10-retain-evidence.py` from the harness-integrator branch, with source checkout pointing to the immutable reviewed product PR SHA. Do **not** modify the previous V7/V8 packer or global limits. Finalize the CRACI run receipt **after** the wrapper has independently qualified private originals and published only bounded exact ZIP parts. Preserve the credit hard stop, actual source SHA, harness SHA and success/failure receipt gating.

The later manual dispatch, **only if source review/integration and existing credit window approve**, would use:

```sh
gh workflow run craci-pilot.yml -R SalesSquad/junction-pets \
  --ref codex/craci-v7-feasibility-integrator-20261114 \
  -f workload=rokoko-mujoco-v10-prospective \
  -f source_sha=SOURCE_ONLY_V10_PROSPECTIVE_REVIEWED_HEAD
```

`SOURCE_ONLY_V10_PROSPECTIVE_REVIEWED_HEAD` must be replaced with the immutable reviewed **40-hex commit**, not a branch name or dynamic source. The harness's own commit is a separate immutable SHA. Source status remains unqualified until actual replays and original artifact evidence are checked.

## Verification scope

```sh
python3 -B -m unittest discover -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_prospective -p 'test_contract.py' -v
python3 -B -m unittest discover -s scripts/craci -p 'test_rokoko_mujoco_v10_prospective_qualification.py' -v
python3 -B -m unittest discover -s scripts/craci -p 'test_rokoko_mujoco_v10_retain_evidence.py' -v
```

These are *fast synthetic contract checks*, **not** proof that 800 MuJoCo episodes completed, or that V10 improved over V5/V8. No external spend or CRACI dispatch was performed as part of source authoring.
