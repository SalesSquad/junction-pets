# CRACI Feedback Loop v2 — from original TRAIN outcomes to a next experiment

WorkID `CRACI-CLOSED-LOOP-20261114`. This is an offline deterministic
**evidence compiler**. It does not execute CRACI, train on invented actions,
open a held-out split, promote a model, spend credits, change the original
MuJoCo 3.3.7 seven-option shield, or edit any existing workflow.

## Pinned, independently reviewed history

The compiler is stacked on exact Junction integrator source
`3ddc0fcf8b13df0e2dc750c02d84fdb9f2fb76ad` (#186).
All eight inputs (two V10/V11 registry records, paired readouts, V11 source
integrity, original manifest, independent qualification and full original
action-support aggregate) are pinned by original **Git blob SHA-1**.
The compiler recomputes those Git object digests from bytes before reading
JSON. It also cross-checks exact physics source SHA, receipt/run IDs,
original gzip SHA256, `train` split, evidence provenance, 160-world paired
goal counts, **250 consecutive MuJoCo goal-dwell ticks**, independently replayed
positive/public-mask outcomes, source and original artifact digests, V5
baseline, novel/lost/unsafe goal lists and seven-action support counters.

Historical training sources:

| Source | Original run | Original full transitions SHA256 | Goal250 outcome |
| --- | --- | --- | --- |
| V10 | `43649224059` | `739c30a13ecacdecd404774fc9dadd887944f32df5cef14cfd2758a639460419` | 26 candidate vs V5 37; **0 novel, 11 lost** |
| V11 | `43653579339` | `0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b` | 18 candidate vs V5 18; **0 novel, 0 lost, 0 unsafe** |

The source-pinned independent action-support audit counted **73,561
actually executed** 18D public-observation/7-mask option transitions across
320 distinct TRAIN worlds. SIDE_RIGHT action4 was executed only **three
times in one distinct world** (V10); the mask allowed it 48,800 times.
This identifies *insufficient executed-action coverage*, not 48,800 safe
training examples or positive counterfactual action labels. Per-action
descriptive Wilson intervals concern world **execution coverage**, not
success probabilities or causal benefits.

## CLI

From a **clean checkout of the exact new feedback-compiler Git HEAD**
descended from the immutable parent above:

```bash
python3 scripts/craci/feedback_loop_v2/compile.py \
  --mode compile --require-git --expected-head EXACT_NEW_40_HEX_HEAD \
  --repo-root . --output-dir /new/empty/craci-feedback \
  --candidate v11
```

Optional original compressed evidence inputs, both together:

```bash
  --v10-raw-gz /path/to/restored-v10-full_transitions.jsonl.gz \
  --v11-raw-gz /path/to/restored-v11-full_transitions.jsonl.gz
```

These must match the **original** pinned SHA256 values above. The compiler
then streams and recounts every actual executed action, mask-legal action,
episode and distinct world, rejecting mismatches. This is a second local
aggregate recount, **not a new MuJoCo physics replay**, provider attestation
or held-out evaluation. Without them it explicitly reports that its evidence
comes from previously independently reviewed source artifacts.

Optional guards:

- `--used-seed-ledger ledger.json` containing verified train-range objects,
  e.g. `[{"start":518000,"end":518050,"split":"train","verified":true}]`.
  Any overlap with a proposed fresh seed cohort causes **STOP**.
- `--credit-cutoff-utc 2026-11-15T17:00:00Z`, optionally
  `--at-utc 2026-11-14T20:00:00Z` for deterministic repro. An elapsed
  cutoff causes STOP. Passing a cutoff never authorizes dispatch.
- `--candidate v10` deliberately produces STOP because it lost eleven
  frozen-V5 goal250 wins.

The compiler writes two exclusively created files into an **empty directory**:

- `feedback.json` — actual decision, independently checkable input
  provenance, goal250 paired outcome, per-action distinct executed-world
  support with uncertainty and risk reasons, next training-only plan.
- `manifest.json` — SHA256 of byte-exact feedback and Git blob hashes for
  the eight original evidence inputs.

Valid input with a negative scientific finding returns exit 0 and decision
`TRAIN_MORE_FOR_UNSUPPORTED_ACTION` or `NO_PROMOTION`; source/proof
integrity, reused cohort, expired cutoff, unsafe action, or lost V5 goals
cause `STOP` and nonzero exit. Verified novel goal250 wins with no losses or
unsafe and both exact originals locally recounted may recommend
`INDEPENDENT_TRAIN_CONFIRMATION`, **never promotion**.

## Preregistered next cohorts (advisory only)

| Stage | Fresh public TRAIN seed scan | Worlds and paired episodes |
| --- | --- | --- |
| Pilot | `518000..518511` | First 40 near and 8 clear observed worlds; three arms; **144 episodes** |
| Independent TRAIN confirmation | `518512..519023` | First 128 near and 32 clear; two frozen arms; **320 episodes** |

The next source owner must independently preregister actions and policy,
protect **all** frozen V5 successes and immediate unsafe stops, apply the
unchanged 7-mask and public-observation 18D ABI, and reconfirm cohort
availability and time/credit authorization at dispatch. The compiler
never reserves the seeds or dispatches the job. No DEV, calibration, TEST
or OOD data becomes available through this plan. The original `ContactEnv`
seed maximum is exclusive 520000, so both proposed ranges remain valid.

If one valid source or original digest changes, require an explicit new
source and independent review rather than repinning to make a red run green.
The financial cost of the historical hosted runs is **unknown**.

## Reproducible local verification

```bash
python3 -m unittest discover -s scripts/craci/feedback_loop_v2 -p test_contract.py -v
python3 -m compileall -q scripts/craci/feedback_loop_v2
```

Tests cover positive and negative decisions, missing or unverified source,
duplicate registry metric, fake novel goal, loss, unsafe, sealed-split
opening, legal-mask pseudo-label, raw hash mismatch, single missing original,
reused/overlapping or unverified world ranges and credit cutoff. They are
synthetic **contract** tests; they do not claim to have rerun actual MuJoCo.
