# CRACI science-to-learning controller (TRAIN-only, advisory)

**WorkID:** `J26-CRACI-SELF-IMPROVING-LOOP-20261114`  
**Scope:** private `SalesSquad/junction-pets`; this folder only.

This is the missing link between *a large physics run* and *a materially better
next development iteration*. It consumes **original byte-verified real MuJoCo
TRAIN artifacts**, computes paired same-world goal regret and mask compliance,
and produces the next candidate's **immutable learning/curriculum proposal**.
It has **no network calls, CRACI dispatch, billing, background service, model
training, credential access, release or automatic model promotion**.

It **complements**, rather than replacing, existing CRACI `adaptive-core.mjs`
(credit-aware advisory job selection), `provider-proof.mjs` (provider evidence),
the bounded CRACI V7/V8 evidence collectors and the existing hourly CRACI R
guardian. A fresh owner/reviewer-approved CRACI source workload runs physics;
this tool only closes the *observe → diagnose → propose → independent review →
new TRAIN remeasurement* feedback loop.

## Executed original evidence: V8 negative result

Frozen source PR [#192](https://github.com/SalesSquad/junction-pets/pull/192),
executed source `87c91de52cef5c3e745115f737abc4ab8d654a32`; harness PR
[#186](https://github.com/SalesSquad/junction-pets/pull/186) executed commit
`251f003b56b9eea1aff79568ad351f615acaee20`; original real
[CRACI #43645486985](https://github.com/SalesSquad/junction-pets/actions/runs/43645486985),
archive [#14134391158](https://github.com/SalesSquad/junction-pets/actions/runs/43645486985/artifacts/14134391158).
The source-reported successful execution was independently replay-qualified
for **TRAIN data ingestion**, not for policy superiority or deployment.

The sample input `v8-qualified-pins.json` freezes all **seven exact original
file SHA-256 values**. The controller refuses a mismatched receipt/run URL,
unpaired world hash, unverified public-observation cohort selection, partial
full transition count, unsupported action mask, replay or
inconsistent independent readout.

Verified original paired data from the 640 real MuJoCo 3.3.7 episodes:

| Strategy | Safe goals, total/160 | Safe near goals/128 | Newly unsafe |
| --- | ---: | ---: | ---: |
| Frozen V5 | 29 | 9 | 0 |
| Frozen V6 | 22 | 2 | 0 |
| repeat_left | 0 | 0 | 0 |
| V8 learned | 1 | 0 | 0 |

V8 lost **28 of V5's same-world successes**, gained **zero** new ones and
achieved safe reopening after a side action in **108/128 near worlds** but
converted **0** into a safe near goal. The resulting decision is
`NO_GO_LOST_FROZEN_GOALS`, not “learning success”. All 29,923 original full
option transitions passed the seven-action legality and 18D public-observation
shape recheck. It cannot prove the actual dynamics were simulated faithfully;
the prior independent MuJoCo replay is retained as separate original evidence.

The output identifies nine **original observed, frozen-control-won** hard
TRAIN worlds where V8 did not win. The next candidate may upweight the actual
observed teacher actions in those worlds. **Do not synthesize counterfactual
labels** from losing pairs. This leads to the separately reviewed, frozen
[V10 candidate PR #206](https://github.com/SalesSquad/junction-pets/pull/206),
model `candidate-weights.json` SHA256
`3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d`.

The generated advisory freezes **fresh TRAIN scan seed IDs 515000–515511**
(seed-scan digest in output), with **128 near + 32 clear worlds selected only
after public initial observation** and five paired strategies (up to 800
episodes). This is a *requested future experiment*, not newly executed CRACI
physics. An additional evidence qualification and independent source review
remain mandatory before admission; dev/cal/test/OOD stay closed.

## Reproduce from original retained bytes

Restore the authentic original archive to directories of your choice. Pin its
file SHA256 against the seven values in `v8-qualified-pins.json`. For example,
let `RETAINED` be the original artifact extraction directory and `RESTORED` be
the SHA-verified, losslessly reassembled raw file directory:

```sh
node scripts/craci/learning_controller/cli.mjs \
  --pins scripts/craci/learning_controller/v8-qualified-pins.json \
  --training "$RESTORED/training.json" \
  --transitions "$RESTORED/full_transitions.jsonl.gz" \
  --manifest "$RETAINED/manifest.json" \
  --qualification "$RETAINED/independent-qualification.json" \
  --replay "$RETAINED/independent-positive-replay.json" \
  --readout "$RETAINED/paired-readout.json" \
  --receipt "$RECEIPT" \
  --candidate-commit 58c972e58575f022f2e97f09612f7c7fb244d4cb \
  --candidate-weights 3a926fdd80bc5bfe069ba4ab50792aaed760d81480eb68a80b6e087beec71f3d \
  --out NEW-EVIDENCE-CYCLE.json
```

`--out` **must not exist**; output uses exclusive creation to preserve earlier
negative decisions. Pass both `--prior PREVIOUS.json --prior-sha256
REVIEWED_EXACT_FILE_SHA256` on a subsequent, genuinely new source-qualified
result. The CLI rejects repeated source/byte identities, rejects modified
previous reports, increments the future TRAIN scan by 512, and binds the
previous cycle hash. **An independently reviewed prior SHA must be supplied**;
this process cannot certify that the person supplying it is the reviewer.

Run the small source/unit check:

```sh
node --test scripts/craci/learning_controller/core.test.mjs
```

`examples/v8-real-science-cycle.json` is a *reproducible derived report*
from original retained evidence, not a newly executed simulation or an
independent reviewer signature. The complete original artifacts remain in the
owning CRACI archive; source data are not duplicated into this repository.

## Stop and acceptance policy

1. **No evidence, no lesson.** Refuse changed/missing raw SHA, incomplete
   source-reported receipt, masked-action violation, mismatched control-world
   pairing, inconsistent third-party readout or TRAIN/OOD provenance violation.
2. **No goal preservation, no promotion.** Exact frozen-V5 same-world wins
   must be retained, newly unsafe episodes must not increase, and at least one
   genuinely new paired safe goal must appear before *even proposing*
   additional independent scientific review.
3. **No train leakage or fabricated cohorts.** New seeds are disjoint from
   original source worlds; the future scan is fixed before knowing its
   observations or outcomes. Re-derive every accepted cohort from the
   source's complete ascending public-observation scan (original threshold
   0.122, first 128 near and 32 clear), including the original world hashes.
   The future 800-row summary may exceed CRACI's capture limit: a reviewed
   lossless chunk packer and exact reassembly/complete-row check are required;
   incomplete/truncated capture must stop, never silently omit bad worlds.
   Use only observed public state and the original seven-action masks at
   inference.
4. **No self-attestation.** Source-reported CRACI plus independent source
   replay does not equal provider-certified billing or holdout certification.
   `dispatchAuthorized` and `modelPromotionAuthorized` always remain false.
5. **No perpetual spending.** Existing `adaptive-core` + the authorized CRACI
   operator/guardian own budgets, concurrency, credit-window cutoff and
   shutdown. This controller never launches a job or changes that policy.

The only useful success metric of this controller is whether future reviewed,
same-world TRAIN remeasurement improves safe goal completion **without** losing
the baseline's existing successes. Offline imitation loss remains diagnostic.
