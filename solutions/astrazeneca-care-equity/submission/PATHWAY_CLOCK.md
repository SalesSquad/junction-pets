# The Pathway Clock: the card

One card for THL, FICAN and a county data team. It names the smallest set of fields that measures
Finland's cancer-pathway target, the two national data carriers that already exist, and the rule
that an area is compared only when it can see itself. Every threshold on it is a **placeholder**.
Every number comes from the file named next to it; `submission/check_numbers.py` recomputes them.
Patient-like data behind it are SYNTHETIC.

## The minimum, for every patient with a well-founded suspicion of cancer

| Field | Values | Why it is in the minimum |
| --- | --- | --- |
| Date of well-founded suspicion | date | Starts the clock. The OECD/EU reports a target of **six weeks** from a suspected-cancer referral to treatment |
| End date | date | Stops the clock |
| End reason | treated, ruled out, other | A pathway that ends in "ruled out" is a finished pathway, not a missing one |
| County of residence | one of 23 areas | Reports by where people live, not where they were treated |
| Entry route | public primary care, occupational or private care, emergency, other | Median symptom to treatment was **127 days** through a public health-centre appointment and **76 days** through private or occupational care in one Finnish cohort |

The minimum follows the mandatory points of Sweden's standardised cancer pathways (research and
panel source in `BIG_PICTURE.md`, not re-opened tonight). Two dates show that a pathway was late,
not where.

## Optional events, for a pilot county that wants to locate a delay

First contact, referral sent, diagnosis, treatment start: SAMA's four timestamps. In SAMA's
SYNTHETIC event log the clock starts when the referral is **sent** (`REFERRAL_SENT`). The scribe
pre-fills these from Finnish notes and a person confirms each one; notes in other languages go to
manual entry.

How much data is enough (SYNTHETIC simulation): to see a county that is 20% slower in one interval,
at 80% power with 69 comparisons, a county needs **473 / 513 / 347** complete episodes (primary
care / diagnostic / treatment interval). At an assumed 37,000 cases a year, **5 of 23** counties
could see that within a quarter and **20 of 23** within a year.

## Carriers that already exist

| Carrier | What it carries | Status |
| --- | --- | --- |
| THL's person-level waiting-list feed (TTP) | The clock: suspicion date, end date and reason, residence, route | Today THL's statistic covers non-urgent care only, as month-end snapshots. Person-level delivery is due by 2028 at the latest (the page says 1.1.2026 in one section and 1.1.2028 in another) |
| Cancer quality register at THL's Cancer Registry, roadmap 3.2.1 (EUR 2,500,000, pages 59-60) | Stage and route; optional events | Decree updated in 2026-2028; roadmap metric: 90% data coverage including stage, 90% of clinical notifications automated by 2030. Ask: add the clock fields while the variable set is being fixed |

## Placeholder thresholds (one table)

| Clock | Threshold | Source of the number |
| --- | --- | --- |
| Referral to treatment | 42 days | **Placeholder (OECD/EU-reported target).** The law allows assessment within **3 weeks**, tests within **3 months** and treatment within **6 months**, with no cancer-specific limit |
| Referral to diagnosis (worklist trigger) | 42 days, with 90 days as a sensitivity count | The same OECD/EU-reported placeholder; 90 days is SAMA's `navigation` card (`src/recommend.mjs`), shown only as a count (`data/safetynet/safetynet-v1.json` `thresholds`) |
| Imaging follow-up | The due date the radiologist wrote | Copied, never decided by SAMA |

Cancer-specific access times are to be set under roadmap measure 3.1.2 (p. 57); quality targets and
indicators under 3.1.4 (p. 58). SAMA's thresholds stay placeholders until they are set.

## The gate: can this county see itself?

- An area enters a comparison only when its own records cover the clock. Otherwise it reads
  "cannot be assessed yet", never "slow" or "fast".
- Why: in a simulation on SYNTHETIC error profiles, a county whose dates are read from free text
  while the rest of the country uses structured fields is flagged as slow in **1.000** of runs with
  nothing wrong, and in **0.003** with "Gemma reads, code counts"
  (`data/eventlog/design-study-v1.json`).
- On real data the gate applies to areas, because stage completeness is published by area only:
  72% in Pirkanmaa, 60% in Sisä-Suomi and 33-42% elsewhere, against an aim of 70%.
- Computed where the data live: NVIDIA FLARE federated statistics on 23 simulated county sites
  reproduced **92 of 92** county-by-interval cells of SAMA's central table within 1e-6, with the
  same small cells suppressed (`data/flare/summary.json`, SYNTHETIC).
- The gate run with a referral-to-treatment edge at 42.5 days (whole days up to the 42-day
  placeholder count as within), SYNTHETIC notes read into each simulated county: with the scribe as
  is, **15 of 23** county figures are labelled "not comparable"; with Gemma reads, code counts,
  **1 of 23**. The figure stays visible; only the label changes. FLARE computed it per county:
  **253 of 253** cells equal the central computation. The gate's limits are placeholders:
  median bias above 3 days, or more than 10% of events missed (`data/flare/gate-v1.json`).

## Sources

`submission/evidence-v2.json` (`oecd-2025-fi-six-weeks`, `stm-hoitotakuu`, `thl-ttp-person-level`,
`kuitunen-2026-route-medians-groups`, `syopajarjestot-2026-stage-completeness`);
`data/roadmap/mapping-v1.json` (measure 3.2.1); `data/eventlog/design-study-v1.json`
(`sample_sizes`); `web/data/app.json` (`eventLog.reach`); `runs/diagnose/interval-impact-v1.json`;
`data/flare/summary.json`; `data/flare/gate-v1.json`; `data/safetynet/safetynet-v1.json`.
