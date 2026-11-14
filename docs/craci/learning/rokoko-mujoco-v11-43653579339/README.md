# Rokoko CRACI V11 — independent negative science, next learning cycle

WorkID `CRACI-V11-LEARNING-20261114`. This is a source-bound **TRAIN-only**
MuJoCo 3.3.7 experiment, not a product qualification or model promotion.

## Original immutable evidence

- GitHub CRACI Actions run: https://github.com/SalesSquad/junction-pets/actions/runs/43653579339
- Original GitHub artifact: `14137341587`, 5,293,908 bytes,
  SHA-256 `bbf94c662fab3ac0efab3448c9e917dcce473a2644efc82a3f4835dd85792bae`.
- Byte-identical original archived to the Mac Mini iCloud Drive under
  `Junction/CRACI/rokoko-v11-43653579339-github-artifact.zip`.
- Immutable CRACI harness commit: `b1938bee9dbca482f645b5dde3359de38e6c125e`.
- Product training source commit: `ab6df4054ef6ed350b479469590a48046a0c0a68`.
- Original unmodified `training.json` SHA-256:
  `c3b3b399344fa18eff7a303cf27e2a510ab9eb74111a6216df1ec11a906579df`.
- Original full `full_transitions.jsonl.gz` SHA-256:
  `0a38081a43426ee4774d09d22886202aaf56d59f6b925a0a75cb2f2da14c848b`.
- Original `paired-readout.json` SHA-256:
  `cd50f5def18bba6741145d27e1f07652f6d6c366a0609a04e0a060612f817e4d`.

The adjacent JSON documents are **byte-for-byte copies** of the hosted receipt,
source-integrity, lossless-part retention plan, original manifest, paired
readout and hosted independent physics-qualification reports. The large
original trajectories are retained in the original artifact and iCloud, not
silently reduced to the sparse retained documentation.

Replay retained original evidence without dispatching a simulator, provider,
or a new paid job (requires Python 3 and NumPy):

```bash
python3 scripts/craci/rokoko-mujoco-v11-independent-audit.py \
  /path/to/originally-unzipped-CRACI-artifact \
  /path/to/original-artifact-14137341587.zip
```

This checks receipt/manifest/ZIP SHA binding, reconstructs all original ZIP
parts, independently recalculates the 512 public starts, all 800 paired
episodes and every 18D observation/7-action legal mask, reconciles sparse
and full trajectories, real terminal contact/goal250 dwell outcomes and exact
novel/lost/unsafe seed lists. The hosted qualification separately reports
fresh MuJoCo physics replay. The offline audit **does not independently rerun
MuJoCo** or provide provider attestation.

## Physical goal-first result

| Frozen strategy | Safe goals / 160 | Near / 128 | Clear / 32 | Unsafe |
| --- | ---: | ---: | ---: | ---: |
| V5 baseline | 18 | 6 | 12 | 0 |
| V6 baseline | 14 | 2 | 12 | 0 |
| V8 | 0 | 0 | 0 | 1 |
| V10 loss-informed | 9 | 3 | 6 | 1 |
| V11 goal-preserving | 18 | 6 | 12 | 0 |

- **Real execution:** 800 paired episodes on 160 selected public-start worlds,
  34,992 actual executed shielded option transitions.
- **New goal250 dwell wins versus V5: 0.** Lost V5 goal wins: 0. V11 unsafe: 0.
- V11 changed action sequences on **62 of 160** same-seed worlds, so the
  negative result is not just a completely unused intervention.
- V11 reopened forward movement in 108/128 near worlds versus V5 60/128,
  **diagnostic proxy only**; this produced no new valid terminal successes.
- Independent raw paired bootstrap 95% descriptive interval for safe-goal
  rate delta: `[0, 0]`; exploratory exact McNemar p = 1.0.
- **Science decision: `NO_PROMOTION_NEGATIVE_TRAIN`**. The physical task is
  sustained goal contact for at least 250 MuJoCo ticks, not merely clearing a
  corridor, opening forward movement or achieving one-step goal proximity.

## Cross-version diagnostic and learning hypothesis

An independent count of the original **V10 plus V11 executed** trajectories
found 73,561 total option transitions:

| Option | Actually executed | Legal in public mask |
| --- | ---: | ---: |
| `SIDE_LEFT` / 3 | 35,911 | not used as a success estimate |
| `SIDE_RIGHT` / 4 | **3** | **48,800** |

These are transition-level counts, not independent worlds; legal does **not**
imply right-sided action succeeds or is safe. Three examples cannot support
credible right-side action-conditioned dynamics. An honest learned controller
must mark option 4 **UNTRAINED**, even where the public shield allows it.
The machine-readable exact per-action executed/legal and distinct-world counts
are in `action-support-v10-v11.json`; all three right-side executions came from
only one V10 frozen-V6 world, and V11 provided none.

The next version is an *action-conditioned, uncertainty-aware, phase-aware
contact-to-dwell controller*: infer moving-obstacle trend only from past and
current public 18D observations; fit transitions only for **actions actually
executed** in original TRAIN traces; compose 2–3 of the seven legal options;
preserve V5 on unsupported regions. No private simulator state, invented
unchosen-action labels, eighth action, hidden DEV/CAL/TEST/OOD access or
unverified positive counterfactuals.

**Fresh, predeclared proposal, not an approved result:** public-only 518000+
scans; 48-world/144-episode pilot with strict unsafe, V5-regression and
zero-novel physical-goal stops; only if a new safe physical goal appears,
repeat one frozen candidate on a disjoint 160-world/320-episode TRAIN
confirmation. Separate right-side exploration is needed before offering
option 4 as a trained rescue. New CRACI dispatch requires current source,
credit-window checks, independent review, evidence retention and hard stop.

No merge, hardware release, production deployment or model promotion is
authorized by this document. Provider-specific actual financial cost is
unknown; sealed holdout evaluation is not available.
