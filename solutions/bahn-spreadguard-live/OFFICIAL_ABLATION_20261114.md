# Bahn Express Spread — official unranked practice evidence (2026-11-14)

**Work ID:** `BAHN-SPREAD-97-20261114`

**Scope:** private `SalesSquad/junction-pets`, stacked draft PR #161 against
PR #128. Baseline source `5a0cb61c6083ce13c465b46b9958c90e066e142e`;
experimental source `e992cbab5910c331f02a7bd0a7b16b29ae5e9188`.
Execution: authorized MacBook Pro, official pinned `spread==0.1.0`,
level-8 sponsor service. All world IDs below refer to completed,
**unranked practice** runs. No `--board` and no `--final` was used.
Credentials were loaded from the owner's local Keychain at execution; they
are not included here. `world.score()`, not rounded terminal progress, is
the source of record.

## Sponsor objective and experimental hypotheses

- Official goal: maximize **gross margin in EUR**, conditional on
  **at least 90% on-time service in each scored world**.
- Internal stretch goal: 97% on time. It is **not a sponsor rule**.
- Discovery is the reviewed baseline: quote 132% of list, booking/slack and
  fee-budget gates, no extra next-day buffer.
- Admission is an isolated overlay: 132% of list and +240-minute next-day
  quote buffer, without driver invitations.
- Margin candidate: 139% of list and +240-minute next-day quote buffer,
  using the same official driver/fee rules as Discovery. These parameters
  were chosen after observing seed `01`, so it was **not blind**; `02`–`05`
  are matched holdouts, not proof of future world performance.
- Standalone 139% price and rescue variants are ablations, not recommended
  default policies.

## Matched level-8 sponsor worlds

All first-stage seeds are `bahn-proof-20261114-<suffix>`. Each cell in the
time columns is exact sponsor on-time delivered / won orders, with percent
rounded for display. Margin is exact cents converted to EUR.

| Suffix | Discovery world | Discovery on time | Discovery margin |
| --- | --- | ---: | ---: |
| 01 | `wfd82e24c841c3593a65f` | 311/322 (96.58%) | €6,771.29 |
| 02 | `w54c8a1a172532efca12a` | 269/292 (92.12%) | €4,827.80 |
| 03 | `w879c323f06867d4df463` | 293/308 (95.13%) | €6,114.93 |
| 04 | `wc15cfcc5d2e50eb4b98b` | 244/260 (93.85%) | €5,149.64 |
| 05 | `w33a8290e0983ed92a89c` | 277/283 (97.88%) | €7,285.48 |
| **Total** | | **1,394/1,465 (95.15%)** | **€30,149.14** |

| Suffix | Admission 132% +240m world | Admission on time | Admission margin |
| --- | --- | ---: | ---: |
| 01 | `w98d49e062eb905b299d2` | 302/310 (97.42%) | €6,772.59 |
| 02 | `we8346427a920c10738ea` | 263/281 (93.59%) | €5,071.06 |
| 03 | `wa40ec787a37efd9f027e` | 272/287 (94.77%) | €5,742.60 |
| 04 | `wadc089fdd0745049c128` | 241/249 (96.79%) | €5,206.09 |
| 05 | `wc289756d3a28ad5cc409` | 277/280 (98.93%) | €7,329.56 |
| **Total** | | **1,355/1,407 (96.30%)** | **€30,121.90** |

| Suffix | Margin 139% +240m world | On time | Margin |
| --- | --- | ---: | ---: |
| 01 | `w5f5406d5e1a2a60926d5` | 319/333 (95.80%) | €7,936.97 |
| 02 | `wf78478fad516f52764fc` | 287/312 (91.99%) | €5,390.93 |
| 03 | `w1543ca74476dee7c3ab9` | 323/339 (95.28%) | €6,659.68 |
| 04 | `w109698471181fb40d3b5` | 238/251 (94.82%) | €5,896.03 |
| 05 | `w447a429f45391dccab58` | 329/335 (98.21%) | €9,178.04 |
| **Total** | | **1,496/1,570 (95.29%)** | **€35,061.65** |

All 15 worlds above returned `ranked: true` from `world.score()`:
this denotes **score eligibility**, not a leaderboard run.

## Frozen-policy blind holdouts (five additional seeds)

After freezing 139% / +240m and the source SHA above, we predeclared
`bahn-blind-20261114-06` through `bahn-blind-20261114-10` and ran
Discovery and the combo once per seed, with no retuning between seeds.
All 10 additional worlds completed and returned `ranked: true` (eligible).

| Seed | Discovery world | Discovery on time | Discovery margin | Combo world | Combo on time | Combo margin |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| 06 | `wbd587c0d71b1b91b35de` | 245/251 (97.61%) | €5,310.66 | `wb783afee5f2c95100b1b` | 250/261 (95.79%) | €5,726.44 |
| 07 | `w284a5f35d24d96970c73` | 181/185 (97.84%) | €5,254.28 | `w5341331c1a5bf6e6a0cf` | 177/182 (97.25%) | €5,504.39 |
| 08 | `w9579bb3ff0c73c382b7d` | 252/265 (95.09%) | €6,235.47 | `w19e0f5713c8094fb8949` | 297/311 (95.50%) | €8,046.28 |
| 09 | `wde2ebb587d26ce52184c` | 259/266 (97.37%) | €6,283.07 | `w237db37afdc864c01127` | 260/270 (96.30%) | €6,881.57 |
| 10 | `w5906c55475ffecad80e0` | 136/137 (99.27%) | €4,223.13 | `wf7d8c2b7c38b0e541cef` | 116/117 (99.15%) | €4,289.50 |
| **Total** | | **1,073/1,104 (97.19%)** | **€27,306.61** | | **1,100/1,141 (96.41%)** | **€30,448.18** |

**Blind result:** the combo gained **€3,141.57 (+11.505%)** versus
Discovery; every individual seed gained gross margin and all stayed
above 90% on time. The combo's aggregate on-time percentage was lower
by 0.79 percentage points in this sample. Across the complete ten
matched seeds, baseline achieved **2,467/2,569 (96.03%)** and
**€57,455.75**, while the combo achieved **2,596/2,711 (95.76%)** and
**€65,509.83**. The resulting gross-margin improvement was
**€8,054.08 (+14.018%)**, with 10/10 positive per-seed margin deltas
and 10/10 combo worlds sponsor-eligible. This is meaningful evidence for
the sponsor's margin-first goal, **not evidence of 97% reliability**.

R analysis on Mac, using 20,000 paired bootstrap resamples of worlds
with seed `97141114`, gave a descriptive 95% percentile interval
**+8.70% to +19.57%** for the ten-world gross-margin improvement
and **+4.32% to +20.87%** for the blind five alone. These intervals
assume the tested seeds adequately represent future worlds; they
do not account for the initial seed-based parameter selection, a
changing competitor mix or system-wide correlated failures.
The blind-five exact one-sided sign-test p-value is 0.03125
(exploratory; no claims of pre-registered hypothesis testing).

## Conclusions and caveats

1. **Best observed sponsor-scoring candidate:** 139% quote price plus
   240-minute next-day admission buffer. Compared with Discovery, this
   delivered **+€4,912.51 (+16.294%)** margin and 105 more won orders,
   while keeping all five sponsor worlds above 90%. Overall on time is
   95.2866%, not 97%.
2. **Best observed service candidate:** 132% price plus 240-minute buffer.
   Compared with Discovery, this increased aggregate on-time share by
   1.1506 percentage points, with **−€27.24 (−0.09%)** total margin,
   but achieved >97% in only two of five worlds and did not meet the
   internal 97% aggregate target.
3. **Capacity/selection confounding:** On seed 01, the 132% admission run
   removed 16 baseline order IDs and gained five different IDs. Only one
   of the 16 removed was approximately late according to the reveal
   event data; denominator changes and system-level capacity effects
   matter. Do not claim the new admission gate accurately predicts
   which particular orders would be late.
4. **Eligibility tail risk:** The margin candidate's seed 02 on-time
   share was only 91.99%, less than 2 percentage points above the
   minimum. A different final seed could fail the gate. Ten eligible
   worlds improve confidence but do not establish a high-confidence
   guarantee of eligibility on an unseen final world.
5. **Rescue intervention failed:** Seed 01 Discovery was 96.58% and
   €6,771.29, `rescue full` was 96.57% and €6,483.91 after 2,107
   invitations, and `rescue fees` was 96.58% and €6,736.58.
   Do not enable full rescue in competition.
6. **Price-only ablation:** 139% price without additional time buffer
   on seed 01 delivered 94.77%, €7,714.31 and 344 orders. Adding the
   buffer improved that paired same-seed candidate to 95.80% and
   €7,936.97, while still below the 97% stretch goal.

The first Claude Fable 5.2 read-only review warned against excessive
invitations, fee erosion and selection effects. A subsequent request
to re-review the margin candidate failed with **usage credits exhausted**;
no second Fable endorsement is claimed. An independent read-only
quantitative review recommended fresh paired holdouts before promotion.

### Reproduce safely

```bash
# On the authorized Mac with the official SDK installed and credentials
# supplied by the existing approved local Keychain mechanism:
SPREAD_ADMISSION_PRICE_PCT=139 \
SPREAD_ADMISSION_EXTRA_SLACK=240 \
python admission_experiment.py --level 8 --seed bahn-proof-20261114-01
# Do not add --board or --final for an incidental rehearsal.
```

**Decision:** the frozen 139% +240m candidate **passes the requested
five-blind-holdout gate** and is the best observed option for the
sponsor's margin-first final, conditional on a preflight confirming the
official rule/clock, final permissions, source SHA and live environment.
Keep Discovery as a fallback if the sponsor changes conditions; do not
change parameters on intuition after these tests. The owner must
separately authorize an actual final submission; a successful practice
world is not an entry.

Official sponsor kit:
[rules](https://spread.bahnexpress.com/kit/RULES.md),
[handbook](https://spread.bahnexpress.com/kit/HANDBOOK.md),
[API](https://spread.bahnexpress.com/kit/API.md).
