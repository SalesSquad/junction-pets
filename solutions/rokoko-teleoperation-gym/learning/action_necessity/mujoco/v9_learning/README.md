# V9 adaptive learning — TRAIN evidence, no automatic promotion

This folder converts *independently qualified, SHA-pinned* V7 MuJoCo option
traces into a chronological stage graph and trains a stage-progress-weighted,
seven-action shield-masked imitation candidate. It also freezes the next
prospective TRAIN-only cohort **514000–514511**. It does **not** run new CRACI
physics, access dev/cal/test/OOD, dispatch cloud compute or promote any model.

It is stacked on the reviewed V8 product HEAD `6dcb577ada4314d7776025ace12d4684a136fc39`.
It only imports the byte-exact V8 trainer verifier (Git blob
`53a730b71197b18de5b3f4e03b2e870f07f9cdb0`) and does not edit or weaken
V7/V8/physics/harness code. Original immutable V7 CRACI receipt run ID:
`craci.43640728389.1.ebec06d6f3461523`. Original V7 manifest/raw/receipt
must match constants anchored in the inherited V8 verifier; a new manifest that
hashes forged bytes is **not** an authority.

```bash
python -m unittest discover \
  -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v9_learning \
  -p 'test_*.py'

python solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v9_learning/run.py \
  --v7-restored /evidence/v7-restored \
  --v7-retained /evidence/v7-retained \
  --v7-artifact-zip /evidence/craci-v7-retained.zip \
  --output-dir /evidence/new-v9-offline-run
```

Outputs are four files: `stage-readout.json`, `candidate-weights.json`,
`v9-next-train-plan.json`, `manifest.json`. Outputs must be a new directory,
never overwritten. They have reproducible SHA-256s and evidence lineage, but
their *own* manifest is only a local output inventory, never proof of CRACI
execution. The stage grader independently checks full raw transitions, per-row
canonical hashes, shield legality, chronological contact → 25mm signed lateral
→ immediate side-option forward-mask reopening → 250-tick safe goal dwell.
Absolute safe goals and incomplete paths are reported separately. Frozen V5/V6
are paired on each identical world rather than compared across seed cohorts.

The learner uses only public-observation, mask, and action-history features;
contact, success, seed and hidden simulator state are **labels only**. Fit and
diagnostic split on world seed to prevent cross-strategy leakage. The
discounted imitation weights reflect *observed milestone-action associations*,
not unobserved causal advantage. Both rare V7 safe-goal TRAIN worlds are kept in
fit (never in the held TRAIN diagnostic) so the goal-stage head learns actual
terminal behavior. Thus **goal-stage generalization remains unmeasured**. Other
TRAIN worlds have disjoint diagnostics. Stage heads with insufficient fit or
worse TRAIN-only diagnostic loss are marked blocked. Physics improvement is unknown.

Future V8 ingestion uses `--v8-verified`, but is deliberately fail-closed while
`V8_EVIDENCE_LOCK` is `None`. To unlock, separately independently replay the
entire completed 640-episode MuJoCo cohort and code-review fixed V8 run ID,
source/harness SHA, receipt, qualification, and exact raw/summary SHA-256s.
Never pass hashes as CLI trust flags. Then V9 can train on both immutable TRAIN
cohorts, report within-cohort paired outcomes, and select its next focus from
verified V8 evidence without modifying the frozen V8 experiment.

The preregistered next 160-world, 800-episode plan includes frozen V5/V6,
`repeat_left`, frozen V8, and the unpromoted V9 candidate, all paired by world.
It remains **a proposal**, not authorization to run unqualified candidate
physics or spend additional CRACI credits.
