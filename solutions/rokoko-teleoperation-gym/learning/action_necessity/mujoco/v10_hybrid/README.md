# Rokoko MuJoCo V10 hybrid: frozen V5 goal finisher + V8 early lateral rescue

**Status: source-verified compositional candidate / original TRAIN-only diagnosis.**
Not trained on a new world, not run in hybrid MuJoCo physics, not a goal-success
result, not a safety certificate, not a release or model-promotion decision.

## Why the switching point matters

The first V5-abstention hybrid proposal was invalid as a useful rescue: in the
original V8 CRACI full transition trace, 1,548 of the 1,556 V5 abstain actions
had original legal mask `[0,0,0,0,0,0,1]` (only abstain possible). Switching to
V8 **after** physical full-lock cannot make a previously illegal lateral option
legal. The frozen candidate instead detects an **earlier** public-mask event:

1. V5 controls normally, using the original 18-component public observation and
   original seven-bit legal-action mask only.
2. If **both forward actions are masked** but at least one of actions 3/4
   (lateral) is **still legal**, and public goal distance is over 35 mm, route
   to exact immutable V8 hierarchical policy for at most 12 options.
3. On public-mask forward reopening (or after 12 options), reset to a freshly
   instantiated original V5 controller. Allow at most 2 rescue rounds/episode.
4. Every action must still be a Python `int` in `[0,6]` and legal in the
   original mask. Malformed input, unreviewed checkpoint or illegal output
   **raises**: no hidden simulator state, oracle, illegal-action correction or
   fallback that could make qualification artificially green.

The stricter default `near-early-side-mask-rescue` additionally requires the
current public `abs(observation[7]) < .122` (the V8 original pre-registered
near-corridor threshold). `early-side-mask-rescue` omits that near gate as a
separate frozen competitor. Both were defined before the next fresh prospective
physics run. They are **not learned checkpoint weights**, just transparent
option routing on already-observable state. V5/V8 weights, control code and
physics are untouched.

## Original immutable data (the only diagnostics consulted)

| Evidence | Pinned identity |
| --- | --- |
| Product source / corrected V8 PR #192 base | `87c91de52cef5c3e745115f737abc4ab8d654a32` |
| Harness source | `251f003b56b9eea1aff79568ad351f615acaee20` |
| CRACI hosted run | `craci.43645486985.1.0627c4e23e4a1296` |
| Original hosted receipt SHA256 | `59e200ce7570157f643174b9f0d8dce8a9c47fdf99aa5080afaab8b7da337e6f` |
| Original `training.json` SHA256 | `af84ec8c6552383e29b8a8dd18ef237c8e3dfd3080729b16f445239618327965` |
| Original `full_transitions.jsonl.gz` SHA256 | `cbaeacd5a7a2a46a30e6b63afeb12614552da032b68e78a6a90fa7d75c49101a` |
| Frozen original V8 canonical weights SHA256 | `9dd1011cd267899da4b9205fb73bdd2f5a8453719b1003351a24a82a2743e0ea` |

`diagnose_train.py` requires all original byte digests, hosted source+execution
receipt, independent qualification, original 640 paired trial rows and the
full 29,923 raw transition actions. This is not self-attestation via a
newly created manifest. V8 runner, trainer, checkpoint and trainer receipt are
also bound to exact SHA256 in `hybrid_policy.py` at inference initialization.

### Frozen policy-diagnostic readout on original 513000 TRAIN worlds

All four controls used paired worlds (128 near, 32 clear). The only observed
goal completions are **original single-policy** outcomes:

| Original control | Near safe goals / 128 | Clear safe goals / 32 |
| --- | ---: | ---: |
| Frozen V5 | 9 | 20 |
| Frozen V6 | 2 | 20 |
| Repeat-left | 0 | 0 |
| V8 hierarchical | 0 | 1 |

From original V5 **public observed masks only**:

- Early hybrid gate appears on **108/119 original near V5 failures**.
- Early hybrid gate appears on **0/29 original V5 goal-finishing traces**.
- For **106 of those 108** gating worlds, *independent* original V8 rollout
  separately demonstrated at least one forward reopening after a side action.
- There are **no clear-corridor V5 traces** reaching the early gate.
- V8's sole goal completion is shared with V5; it adds **zero novel goals**.

This is **in-sample opportunity matching**, *not* a hybrid success prediction.
Switching actions changes the physics trajectory, so these 108/106/0 counts
cannot prove that V5 goals stay preserved, the rescue succeeds, or it is safe.
The original V8 result itself is disappointing in goal completion; use its
observed lateral reopening solely as the plausible auxiliary mechanism.

### Reproduce the read-only original TRACE diagnosis

After restoring and independently SHA-checking the original CRACI ZIP artifact
`14134391158` (ZIP SHA256
`8e33c0b87a8e98cf3be2d4116a8bc4eca2e45efc3707e9fc8d385566319febb8`):

```bash
python3 -m unittest discover -s solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_hybrid -p 'test_*.py' -v
python3 solutions/rokoko-teleoperation-gym/learning/action_necessity/mujoco/v10_hybrid/diagnose_train.py \
  --restored-raw /path/to/verified-original-v8-raw \
  --retained-artifacts /path/to/verified-original-v8-artifact-dir \
  --receipt /path/to/verified-hosted-craci-receipt.json
```

No copied original raw trace or credentials are committed to this candidate.

## Next: real fresh prospective MuJoCo qualification (not yet performed)

1. Freeze this PR HEAD and two modes, verify all SHA pins and source ancestry.
   The new host runner may import `policy_factory` as an immutable module; it
   must use the **unchanged** original `physics.py`/`moving_scene.xml`, seven
   legal options and source-verified V5/V8 checkpoints.
2. Pre-register a disjoint **516000+ TRAIN-only** world cohort, selected solely
   on public first-observation corridor geometry, before any outcomes. V9
   already uses 514000 and the independent V10 gradient candidate reserves
   515000. The candidate cannot inspect these future result seeds now.
3. Paired controls `frozen_v5`, `frozen_v6`, `repeat_left`,
   `v8_hierarchical`, `early-side-mask-rescue`,
   `near-early-side-mask-rescue`; same seeds, same original shield, same
   deadlines and evidence schema. Never select seeds based on results.
4. Measure genuinely **safe goal dwell >=250 ticks**, unsafe/abstain/timeout,
   near/clear, unique goals versus V5, and first lateral mask reopening.
   Report each separately; any improvement must survive independent raw
   transition replay and comparison, not agent-authored summaries.
5. Fail closed on source/physics/receipt mismatch, partial experiment or unsafe
   output. No dev/cal/test/OOD, no silent threshold tuning, no model promotion,
   no deploy or branch merge. If scientific result is still red, retain it as a
   negative learning record and design a new **versioned** candidate.

**Run / PR ownership:** this directory only. The separate V10 gradient
learner, V9, original V8 PR and adjacent harness/physics are outside scope.
