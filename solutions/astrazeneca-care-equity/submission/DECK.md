# SAMA: slide text for the PDF deck

Draft for Junction 2026, AstraZeneca "Equal Care Across Finland". Eleven slides for non-technical
judges, then a technical appendix. Each slide has the words that go on it, a short speaker note and
its sources. Rewritten on 14 November 2026, 23:00-01:30 UTC, to the story in `BIG_PICTURE.md`
(revision 2, sections 3 and 4).

Rules for whoever builds the PDF:
- Every number below comes from the file named under its slide. `submission/check_numbers.py`
  recomputes them from those files and fails if one no longer matches. External facts come from
  `submission/evidence-v2.json` (links re-opened tonight) or `data/evidence/literature-v1.json`.
- A bracketed PENDING marker naming a file marks a result another lane is still producing. Fill it from the file it
  names, or delete the line if that file has no final result at code freeze. `check_numbers.py`
  lists every marker and whether its file exists yet.
- Patient-like data are SYNTHETIC: simulated people, and notes written by language models. Say so
  on every slide that shows them.
- A person confirms every extracted event and every worklist item. Use only "pre-filled for
  one-click confirmation" and "needs editing" for the two outcomes.
- Every time threshold is a **placeholder**. Write "placeholder (OECD/EU-reported target)" next to
  any 42-day threshold.
- Language scope: the scribe reads Finnish notes only; other languages go to manual entry.

Rubric weights, for the order of the slides: Actionability 30%, Insight 25%, Data quality and
transparency 20%, Execution 15%, Clarity 10%.

---

## Slide 1. SAMA: the same cancer pathway for everyone in Finland

**On the slide**
- *Sama* is Finnish for "the same".
- **The same pathway, wherever they live, whoever they are, however they enter care.**
- SAMA measures how long the cancer pathway takes, refuses to compare an area that cannot see
  itself, and turns the clock into a nurse's list of people whose next step is overdue.
- Public data for 21 wellbeing services counties, Helsinki and Åland (23 areas). Every number has a
  source; every action names its national roadmap measure.

**Speaker note.** Decision support for county and national planners. It makes no diagnosis and no
claim about any patient. National measures and the 2026 law are not claimed for Åland, which has
its own health legislation (general knowledge, not checked tonight).

**Sources.** `submission/evidence-v2.json` (`stm-21-counties`).

---

## Slide 2. The gap, and where cures are decided

**On the slide**
- Lung cancer, men, five-year relative survival (2020-2024): **Finland 17.9%**, Sweden and Norway
  average **31.1%**.
- Finland's national lung programme: lung cancers found in time are mostly found **by chance**, on
  scans taken for something else. What happens after that scan decides who is cured.
- Stage is recorded for only **42%** of cancers nationally; the aim is at least 70%.

**Speaker note.** NORDCAN survival is the national Goal 3 indicator. "Found by chance" is from the
Filha lung programme preprint, printed page 19.

**Sources.** `web/data/app.json` (`analysis.goal3`, `nordic-survival`); `submission/evidence-v2.json`
(`filha-2026-found-by-chance`, `syopajarjestot-2026-stage-completeness`).

---

## Slide 3. Who, how and where (Insight)

**On the slide**
- **Where you live is not the main gap.** Five-year survival does not differ significantly between
  regions. By education it does: **64-65%** with lower education against **77-78%** with higher.
- **How you enter care.** In one Finnish lymphoma cohort, the median from first symptom to treatment
  was **127 days** through a public health-centre appointment and **76 days** through private or
  occupational care (48 against 39 patients, p = 0.027).
- **Who is missed.** Breast screening: **63%** against **82%** by mother tongue,
  **66%** against **85%** by education (2020-21). Cervical screening: **57%** against **73%** by
  mother tongue, **51%** against **78%** by education.
- **County averages cannot see this.** Programme attendance is lowest in the capital region,
  where many women screen privately and many people speak other languages:
  Helsinki 74.3%, West Uusimaa 76.1%, Vantaa and Kerava 76.7% (2024). Across 22 counties, attendance falls as the
  education index rises (r = -0.59), and much less without Helsinki (r = -0.35).
- **Action row.** Roadmap 1.3.1: screening participation of people whose mother tongue is not
  Finnish or Swedish should reach the level of Finnish and Swedish speakers. Matching actions:
  mailed HPV self-sampling to cervical-screening non-attenders (Finnish RCT, relative participation 1.21 (1.13-1.30));
  pre-booked appointment times in invitation letters.

**Speaker note.** County and individual figures are different kinds of data: the county pattern
"cannot see" the individual one; it does not "point the wrong way". The OECD says Helsinki's low
programme attendance is likely due to more screening outside the programme. Vantaa and Kerava,
Helsinki and West Uusimaa also have the highest foreign-background shares (288.9, 216.1 and 199.8
per 1,000, 2025). Lung cancer five-year survival by education, within each sex: men about
13% against 18%, women about 20% against 30% (never compare across sexes). The route gap is one cohort of
one cancer, 87 patients in the two route groups. The correlation is a simple Pearson r of 2024
attendance against the latest education index, not SAMA's slope index.

**Sources.** `submission/evidence-v2.json` (`oecd-2025-fi-survival-education`,
`kuitunen-2026-route-medians-groups`, `oecd-2025-fi-breast-screening-gaps`,
`filha-2026-found-by-chance`); `web/data/app.json` (`analysis.indicators.screen_breast`,
`education_index`, `foreign_background`); `data/roadmap/mapping-v1.json` (measure 1.3.1);
`data/evidence/literature-v1.json` (`virtanen-2011-selfsampling-fi`).

---

## Slide 4. A target nobody can see

**On the slide**
- The OECD/EU reports a Finnish target of **six weeks** from a suspected-cancer referral to the
  start of treatment.
- The law allows more: in specialised care, assessment within **3 weeks** of the referral, tests
  within **3 months**, treatment within **6 months**. It names no cancer-specific limit.
- THL's access statistic covers non-urgent care only, as month-end snapshots. Person-level
  delivery through THL's waiting-list feed (TTP) is due by 2028 at the latest.
- The strategy's own Goal 3 indicator, "treatment within target times", **cannot be computed from
  open data today**.

**Speaker note.** We say "the OECD/EU reports a six-week target"; we do not say it is Finnish law.
THL guidance 21/2016 may already define cancer access dates and was not read tonight. The THL page
gives 1.1.2026 in one section and 1.1.2028 in another, so we say "by 2028 at the latest".

**Sources.** `submission/evidence-v2.json` (`oecd-2025-fi-six-weeks`, `stm-hoitotakuu`,
`thl-ttp-person-level`); `web/data/app.json` (`analysis.goal3`, indicator `treatment-within-target`,
status `NOT_PUBLICLY_MEASURABLE`).

---

## Slide 5. The Pathway Clock: two dates and an end reason (Actionability)

**On the slide**
- **Minimum, for every patient with a well-founded suspicion of cancer:**
  - date of well-founded suspicion;
  - end date with end reason (treated, ruled out, other);
  - county of residence;
  - entry route (public primary care, occupational or private care, emergency, other).
- **Optional, for a pilot county that wants to locate a delay:** first contact, referral sent,
  diagnosis, treatment start (SAMA's four timestamps).
- **Carriers that already exist:** THL's person-level waiting-list feed (TTP) for the clock, and
  the cancer quality register at THL's Cancer Registry (roadmap 3.2.1, EUR 2,500,000, pages 59-60)
  for stage and route. Add the fields while 3.2.1's variable set is being fixed.
- **Thresholds are placeholders:** referral to treatment 42 days, placeholder (OECD/EU-reported
  target); the worklist flags a referral with no diagnosis by the same day-42 placeholder, with
  90 days (SAMA's navigation card) shown as a sensitivity count; imaging follow-up = the due date
  the radiologist wrote.
- How much data is enough (SYNTHETIC simulation): to see a county that is 20% slower in one interval,
  at 80% power with 69 comparisons, a county needs **473 / 513 / 347** complete episodes (primary
  care / diagnostic / treatment interval). At an assumed 37,000 cases a year, **5 of 23** counties
  could see that within a quarter and **20 of 23** within a year.

**Speaker note.** The minimum follows the mandatory points of Sweden's standardised pathways. Two
points show that a pathway was late, not where; the optional points locate it. "Well-founded
suspicion" needs a clinical definition and can be gamed. Roadmap 3.2.1's own metric: 90% data
coverage including stage, and 90% of clinical notifications automated by 2030. The full card is
`submission/PATHWAY_CLOCK.md`.

**Sources.** `submission/PATHWAY_CLOCK.md`; `data/roadmap/mapping-v1.json` (measure 3.2.1);
`data/eventlog/design-study-v1.json` (`sample_sizes`); `web/data/app.json` (`eventLog.reach`);
`submission/evidence-v2.json` (`thl-ttp-person-level`, `oecd-2025-fi-six-weeks`).

---

## Slide 6. Can this county see itself? Compare only areas that can (Data quality)

**On the slide**
- **Rule:** an area enters a comparison only when its own records cover the clock; otherwise it
  reads "cannot be assessed yet", never "slow" or "fast".
- **Why (simulation, SYNTHETIC error profiles, 1,000 runs per cell):** one county's dates read from
  free text by a small model, the rest of the country from structured fields, nothing actually
  wrong. Model alone: flagged as slow in **1.000** of runs. Gemma reads, code counts: **0.001**.
  Two counties that only *write* differently: **0.022**, and **0.001** with the fix.
- **On real data, by area:** stage is recorded for 72% in Pirkanmaa, 60% in Sisä-Suomi and 33-42%
  elsewhere. Against the 70% aim, only Pirkanmaa's area could be compared on stage today. The pilot
  is how a county learns to see itself.
- **Computed where the data live (NVIDIA FLARE, SYNTHETIC):** 23 simulated county sites;
  **92 of 92** county-by-interval cells equal SAMA's central table within 1e-6; in a finer run, the
  same 40 small cells suppressed; only totals leave a site.
- **The gate on the clock (SYNTHETIC notes read into each simulated county):** with the scribe
  as is, **15 of 23** county figures are labelled "not comparable"; with Gemma reads, code counts,
  **1 of 23**. The figure stays visible; only the label changes. FLARE computed the
  referral-to-treatment clock per county: **253 of 253** cells equal the central computation.

**Speaker note.** An equity indicator is fair only if its measurement errors are the same
everywhere. Extraction errors, or a different writing style, can manufacture a gap that does not
exist. The gate's limits (median bias above 3 days, or more than 10% of events missed) are
placeholders. Notes were assigned to simulated counties by a content-blind rule, 30-31 notes each,
so differences between counties are sampling noise of one scribe, not county effects. Extra
predicted events are not modelled in the first simulation. FLARE ran in simulator mode on one
laptop, with no network between organisations. NORDCAN already produces Nordic statistics this way,
inside each registry.

**Sources.** `runs/diagnose/interval-impact-v1.json`; `submission/evidence-v2.json`
(`syopajarjestot-2026-stage-completeness`); `data/flare/summary.json`, `data/flare/RESULT.md`;
`data/flare/gate-v1.json` (`summary`, `rule`, `flare.equivalence`, `realData`).

---

## Slide 7. Close the loop: a nurse's list of overdue pathways (Actionability)

**On the slide**
- **Legal basis since 1 June 2026:** a county may identify patients whose care does not follow
  recommendations; processing their data and contacting them must respect data protection and
  self-determination.
- **Close loops before buying speed.** In a trial of 93,326 GP chest X-rays, AI prioritisation left
  the median time to CT at **53 days** in both arms (ratio 0.97, 0.93-1.02).
- **The safety net:** every day, one county gets a list of people whose suspected-cancer pathway
  has stalled: an urgent referral with no next step after the placeholder time, or a lung scan whose
  written follow-up has not happened. Code copies the radiologist's written recommendation and
  computes the due date; vague phrases go to a person. A nurse confirms each item and calls.
- **On SYNTHETIC data, Satakunta replay as of 1 December 2025:** **120** open loops, **16**
  overdue: **10** imaging follow-ups past the date the radiologist wrote and **6** referrals with no
  diagnosis by day 42 (placeholder); **4** written recommendations wait for a person to set a date.
- **The code rule** read **60 of 60** SYNTHETIC report lines correctly:
  30 due dates, 20 vague or conditional lines sent to a person, 10 lines with no follow-up.
- Each row shows episode code, age band, entry route, contact language (fi / sv / se / other,
  interpreter flag), days overdue and the missing step. Counts first; at most 3 unnamed SYNTHETIC
  rows on screen.
- **Governance:** the county owns the list and the care. No patient data leaves the county. SAMA is
  sponsor-independent; any company role is a documented, non-promotional collaboration owned by
  the county.

**Speaker note.** Time saved by faster reading (MASAI: **44%** less screen-reading workload, detection ratio of 1.29 (1.09-1.51)) is best spent closing these loops. This is the operational form of SAMA's patient-navigation action (roadmap 1.2.3,
a named care-coordinating worker). Whether "recommendations" in the 2026 law covers the timing of
pathway steps is UNVERIFIED; confirm with STM and THL. Regulatory line: a workflow aid that copies a
written recommendation, computes a date and lets a nurse decide; device qualification under the MDR
to be confirmed with Fimea before a pilot (UNVERIFIED); EU AI Act high-risk dates 2 December 2027
and 2 August 2028 tracked. KPIs are reported by entry route, education and contact language, so the
safety net cannot reproduce the gap. The counts come from simulated people and assumed follow-up
rates; they show that the list works, not how many people are lost in Satakunta. The rule was
tested on 60 SYNTHETIC lines that the same step wrote from templates after freezing the rule.

**Sources.** `submission/evidence-v2.json` (`stm-2026-proactive-care-law`, `lungimpact-2026`,
`eu-ai-act-dates`); `data/evidence/literature-v1.json` (`masai-2025-workload`); `data/roadmap/mapping-v1.json` (measure 1.2.3);
`data/safetynet/safetynet-v1.json` (`counties` HVA06, `rule.metrics`).

---

## Slide 8. Gemma reads, code counts (Execution)

**On the slide**
- The dates are already written in referral letters and visit notes, often as "kolme viikkoa
  sitten" (three weeks ago). A small open model, **Gemma 3 270M**, reads a Finnish note and copies
  what it says; code turns the phrase into a calendar date; a person confirms.
- Gemma doing the subtraction itself: **2 of 367** test notes with a relative date right.
- Gemma reads, code counts: **289 of 310** validation notes exact; **651 of 700** test notes
  (93.0%; that test set was seen before, so this is post hoc).
- Moving the split into Gemma itself (it writes "3 weeks ago", code computes the date):
  **290 of 310** validation notes, against 293 of 310 for arm A, retrained tonight on this Mac with
  MLX to write absolute dates, plus the code rule (no significant difference, McNemar p = 0.70).
- On a fresh stress set frozen before scoring: [PENDING: data/scribe/v4/eval/results-v1.json]
- On the laptop CPU, through the product's own endpoint: **18 of 20** demo notes exact, median
  **4.8 s** per note.

**Speaker note.** SYNTHETIC notes; Finnish notes only; other languages go to manual entry. Exact
match is strict: one wrong date, type or route makes the whole note wrong. No result here has been
tested on real clinical text. The expression arm was trained on this Mac with MLX; it is weaker than
the absolute-date arm on Haiku-written validation notes (46 against 53 of 60).

**Sources.** `runs/diagnose/diagnose-v1.json` (`by_has_relative`);
`data/scribe/v4/resolver/reproduce-v1.json`; `data/scribe/v4/mlx/validation-v1.json`;
`data/scribe/demo/http-timing.json`.

---

## Slide 9. Nemotron: second reader and county planner (Execution)

**On the slide**
- **Second reader (SYNTHETIC notes).** Nemotron 3.5 Super VL copies each date as written and code
  computes it: validation exact match **192/310** with Nemotron doing the arithmetic, **282/310**
  with code doing it, **304/310** with `enable_thinking`. The chosen version then read the 700 test
  notes once: **690/700**.
- **Two readers agree, or a person edits.** With Gemma on 700 SYNTHETIC test notes: **651/700**
  pre-filled for one-click confirmation, **4** of them wrong; **49** need editing. Before tonight
  our best rule gave 263/700 with 7 errors.
- **County planner.** Nemotron drafted a plan for **23 of 23** areas by calling four SAMA tools.
  Every sentence passed a code check that each number equals a tool output, then a TypeSafe check;
  failures were dropped, never repaired. **255 of 299** sentences kept, **0** with a number not in a
  tool output; **10 of 10** off-limits requests produced no plan.
- **Vision input, tested:** **13 of 20** page images read exactly, against **19 of 20** from text:
  not good enough yet, so the product keeps text input.

**Speaker note.** Plans are English drafts for a planner, labelled "drafted by Nemotron 3.5 Super VL;
numbers checked"; a planner decides. They are "draft input on public data, not an assessment". The
default view is Satakunta. Nemotron wrote most of the reader's notes itself, so its score on them is
optimistic.

**Sources.** `data/scribe/nemotron/reader-v1.json`; `data/scribe/nemotron/cascade-agreement-v1.json`;
`data/planner/plans-v1.json` (`summary`); `data/planner/vision/vision-6b-v1.json` (`summary`).

---

## Slide 10. The zero-euro 2027 plan (Actionability)

**On the slide**
- The Cancer Organisations say no strategy money is planned for **2027**. Three actions need no
  capital spending; their cost is staff time.

| Action | Owner | Roadmap | KPI |
| --- | --- | --- | --- |
| 1. Put pre-booked appointment times back into screening invitations | County screening unit | 1.3.1 | Participation by mother tongue and education, against the 80% target |
| 2. Run the overdue-pathway list with existing care coordinators | County cancer centre | 1.2.3 | Share of follow-ups closed on time; share resolved within 14 days |
| 3. Send two dates and an end reason in THL's person-level feed | County data team with THL | 3.2.1 | Share of new suspected-cancer pathways with both dates and an end reason |

- Evidence for action 1: in Helsinki, cervical screening participation fell
  from **72%** to about **62%** when pre-booked times were removed, and recovered when they
  returned (one city).

**Speaker note.** Staff time, not euros, in each row: rewriting an invitation template and handling
rebookings; a nurse's call per overdue item, at a volume the pilot measures; mapping two existing
dates into an extract the county must deliver anyway. Effects in another county are a SCENARIO. The
full plan is `submission/ZERO_EURO_2027.md`.

**Sources.** `submission/ZERO_EURO_2027.md`; `submission/evidence-v2.json`
(`stt-2026-no-strategy-money-2027`, `yle-2025-helsinki-prebooking`); `data/roadmap/mapping-v1.json`
(measures 1.3.1, 1.2.3, 3.2.1).

---

## Slide 11. The ask: Satakunta, lung follow-up first, a 2027 pilot

**On the slide**
- **Satakunta**, every overdue suspected-cancer referral, lung follow-up first, inside roadmap 1.2.3
  and 3.5.3, at no new capital cost.
- Why Satakunta, on process grounds: Finnish-language services (the scribe reads Finnish only); not
  under the state assessment procedure; high lung burden (lung C32-C34, incl. larynx, shrunk
  mortality **1.126**, 1.045-1.21). Not the highest: Lapland (1.237) and Kymenlaakso (1.132) are
  higher.
- Pilot KPIs, each by entry route, education and contact language: share of follow-ups closed on
  time; share of new pathways with both clock dates; share of pre-filled events confirmed in one
  click.
- **We do not claim** a diagnosis, a statement about any patient, or that any county's care is
  worse. Nothing from simulated people or model-written notes is a finding about Finnish patients.
  AstraZeneca sponsors the challenge; no AstraZeneca data or product information is used and no
  medicine is recommended.

**Speaker note.** Satakunta is probably outside the national lung screening pilot (roadmap 2.3.4:
Helsinki and eight counties); this is our inference, UNVERIFIED: ask a mentor. If Satakunta is in a
randomised pilot arm, the list's evaluation design must change. Lapland comes second, once
Sámi-language outreach is designed with the Sámi Parliament. Owner decision 7: disclose every
company that supported the Filha lung programme's planning phase. All patient-like data in SAMA
are SYNTHETIC; the pilot has not been run.

**Sources.** `web/data/app.json` (`analysis.mortality.lung`, rows HVA06, HVA21, HVA10);
`data/roadmap/mapping-v1.json` (`pilotCard`, measures 1.2.3, 3.5.3, 2.3.4).

---

# Technical appendix

## A1. Data and statistics

- 23 areas, 20 indicators, cancer deaths by site 2021-2025, NORDCAN survival; **57** requests to THL
  Sotkanet, Statistics Finland and NORDCAN, each stored with its retrieval time and SHA-256.
- Exact Poisson intervals, indirect age standardisation, gamma-Poisson empirical Bayes shrinkage,
  false-discovery-rate control (`src/stats.mjs`, `src/analysis.mjs`). Small counts are suppressed,
  not ranked.
- Below the 80% screening target: colorectal in **22 of 22** counties with data, cervical in
  **20 of 23**.
- All-cancer mortality, shrunk estimate: Satakunta about **1.10 times** the national level
  (**1.097**, **1.063-1.132**); the two highest areas differ by **0.001**, so no rank is claimed. Lapland lung (C32-C34,
  incl. larynx): **1.24 times**. Regional lung mortality follows incidence, so excess mortality is
  not a count of deaths avoidable by better care.
- `gp_wait_over_7d` is measured against a legal maximum that changed from 2025; values after 2024
  are not comparable with earlier ones.
- Source: `web/data/app.json`, `data/roadmap/mapping-v1.json` (`pilotCard.snapshotEvidence`),
  `ARCHITECTURE.md`.

## A2. Scenario model and optimiser (upper-bound SCENARIO, not a headline)

- The optimiser picks **18** county actions for EUR 5.95 million of a EUR 6.0 million yearly budget.
  SCENARIO: 177.1 deaths postponed a year (38.2-351.5) over 300 parameter draws; **60.1%** of it in
  counties with above-average cancer mortality.
- Disclosure: the 84-day route prior is read from the paper's Figure 1; the text's medians differ by
  51 days (127 against 76) and its means by 75 (201 against 126).
- Check against Denmark: for a 17-day shorter interval the model implies a hazard ratio of
  **0.965**; Denmark observed **0.86** (0.73-1.01).
- Source: `web/data/app.json` (`recommendation`), `ARCHITECTURE.md`, `src/recommend.mjs`.

## A3. Roadmap mapping

| SAMA action | Fit | Measure | Pages | Roadmap owner |
| --- | --- | --- | --- | --- |
| pathway-timestamps | serves | 3.2.1 | 59-60 | STM (decree change), THL / Finnish Cancer Registry, FICAN |
| timed-pathways | named | 3.1.2 | 56-57 | FICAN with the national multidisciplinary cancer groups; counties and HUS |
| equal-fast-lane | serves | 2.5.2 | 52-53 | FICAN with the national multiprofessional cancer groups |
| navigation | serves | 1.2.3 | 32 | FICAN; counties and HUS |
| ldct-pilot | named | 2.3.4 | 46-47 | STM, Palko, screening steering group, Finnish Cancer Registry, counties, City of Helsinki |
| self-sampling | serves | 2.4.4 | 50 | Finnish Cancer Registry, counties, HUS, City of Helsinki |
| screening-reminders | serves | 1.3.1 | 33 | Counties, City of Helsinki, HUS, NGOs, Cancer Registry, THL |
| ai-mammography | named | 2.4.2 | 48-49 | STM, screening steering group |
| four-timestamps (data proposal) | serves | 4.1.1 | 77-78 | Counties, City of Helsinki, HUS, THL, national cancer groups |

- "Named": the roadmap names this action. "Serves": the action serves that measure, which does not
  name it. The `ldct-pilot` action means joining the national lung screening pilot (2.3.4), which
  started in early 2026 in Helsinki and eight counties.
- **117** Finnish quotes from the roadmap checked word for word on their page of the PDF. English
  text is the team's reading, not an official translation.
- Source: `data/roadmap/mapping-v1.json`, `data/roadmap/manifest.json`, `runs/laneC-step2.jsonl`.

## A4. Gemma scribe: training (SYNTHETIC)

- Gemma 3 270M instruction-tuned, LoRA rank 16, 324 steps at effective batch 16. CUDA: trained in
  176 s on one A100 80 GB on Verda, on 2,354 SYNTHETIC notes (1,716 by Nemotron, 638 by Claude
  Haiku). MLX on this laptop: the expression arm trained in 1,004 s.
- Mixing two writers in training lifted Haiku-written test notes from 13.0% to 47.5% exact match.
- Gemma 3 1B did not fix the dates either: 6 of 367 relative-date notes.
- Served with vLLM and structured outputs: 100 of 100 valid JSON, p95 latency 1.80 s.
- Source: `TRAINING.md`, `data/scribe/v2/training-figures-v1.json`,
  `data/scribe/v3/student/compare-v1.json`, `data/scribe/v4/mlx/validation-v1.json`,
  `serve/smoke/smoke-guided.json`, `runs/diagnose/diagnose-v1.json`.

## A5. Code date resolver and the expression arm

| C-270m-all-v2data | Before | After |
| --- | --- | --- |
| Validation (selection) | 134/310 | 289/310 (93.2%) |
| Test, pooled (already seen, post hoc) | 305/700 | 651/700 (93.0%, Wilson 90.9-94.7) |
| Test, Nemotron-written | 210/500 | 481/500 |
| Test, Haiku-written | 95/200 | 170/200 |

| MLX arms, validation (310 SYNTHETIC notes) | Exact match | Haiku-written (60) | Parse failures |
| --- | --- | --- | --- |
| A: absolute dates + code rule A' | 293/310 | 53/60 | 0 |
| B: expression format, code computes every date | 290/310 | 46/60 | 2 |

- 0 notes made worse by the resolver, in every run and split; the product port matches the analysis
  rule on 5,050 of 5,050 notes.
- Arm A' adds a small Finnish lexicon, frozen at 21:37:24 UTC before any stress note existed; vague
  phrases such as "pari viikkoa sitten" go to a person.
- Arm B met the preregistered validation rule (at least 0.90, within 3 points of A, McNemar not
  significant, under 1% parse failures). Primary comparison on the frozen stress set:
  [PENDING: data/scribe/v4/eval/results-v1.json]
- Source: `data/scribe/v4/resolver/reproduce-v1.json`, `data/scribe/v4/resolver/freeze.json`,
  `data/scribe/v4/mlx/validation-v1.json`.

## A6. What extraction errors do to the county indicator (simulation, SYNTHETIC)

| Primary care / diagnostic / treatment interval | Every event confirmed | Scribe as is | Scribe + code resolver |
| --- | --- | --- | --- |
| Bias in county median interval, 500 episodes, planted 30% slowdown | 0 / 0 / 0 days | +17.4 / +15.6 / +12.6 days | +0.17 / +0.09 / +0.06 days |
| Power to locate a 20% slowdown at 473 / 513 / 347 episodes | 0.765 / 0.770 / 0.758 | 0.234 / 0.131 / 0.080 | 0.743 / 0.742 / 0.751 |
| False flag: county from text, country from structured fields | - | 1.000 | 0.001 |
| False flag: county written like Haiku, country like Nemotron | - | 0.022 | 0.001 |

- 1,000 runs per cell. Extra predicted events are not modelled.
- Source: `runs/diagnose/interval-impact-v1.json`.

## A7. Nemotron second reader: how we improved its outputs (SYNTHETIC)

| Version (one change at a time) | Validation exact match | Paired change |
| --- | --- | --- |
| v0: absolute dates, Nemotron does the arithmetic | 192/310 (61.9%) | |
| v1: copies the date as written; code computes it | 282/310 (91.0%) | +29.0 points, 98 fixed, 8 worse, McNemar p < 1e-6 |
| v1 rerun unchanged (noise floor) | 282/310 | 12 notes moved, 6 up and 6 down |
| v2: + schema validation and one repair retry | 287/310 (92.6%) | p = 0.3, parse failures 11 to 3 |
| v2g: + every date must be printed in the note | 290/310 (93.5%) | p = 0.55 |
| v3: + enable_thinking | 304/310 (98.1%) | +4.5 points, 15 fixed, 1 worse, p = 0.00052 |

- Notes with a relative date: 59/166, then 153/166 (v1), then 164/166 (v3).
- Test, read once by v3: 690/700 (Wilson 97.4-99.2); Haiku-written 199/200; Nemotron-written
  491/500. Cost of thinking: 1,106 against 93 output tokens per note, 2.54 s against 0.30 s.
- Source: `data/scribe/nemotron/reader-v1.json`.

## A8. Two-reader agreement (SYNTHETIC)

| | Validation | Test |
| --- | --- | --- |
| Pre-filled for one-click confirmation (both readers agree) | 286/310 | 651/700 |
| Wrong among pre-filled | 0 | 4 (0.6%, Wilson 0.2-1.6) |
| Needs editing | 24 | 49 |
| Nemotron exact among needs editing | 18 | 43 |
| Pre-filled correctly, per 100 notes | 92.3 | 92.4 |

- Rule fixed in advance: agreement, no threshold. Haiku-written test notes:
  169/200 pre-filled, 0 wrong. Baseline before tonight: 263/700 with 7 errors.
- Source: `data/scribe/nemotron/cascade-agreement-v1.json`, `data/scribe/v3/summary-v1.json`.

## A9. Nemotron county planner (public aggregate data)

- Prompt v1 kept 164/299 sentences (indicator lines 0/69); prompt v2 changed only the field formats
  and kept 255/299 under the same gate. 69/69 roadmap measure ids confirmed by code. Off-limits:
  the model refused 9 of 10 itself; code blocked 1 (an invented county).
- 93 Nemotron calls in the selected version; TypeSafe Jev USD 0.1344 for the gate.
- No patient data was sent: inputs were public aggregates, model scenarios, published evidence and
  roadmap text.
- Source: `data/planner/plans-v1.json` (`summary`), `runs/laneB-step6.jsonl`.

## A10. Every number has a source

- No language model writes a number in the county brief. A TypeSafe check passed **161 of 190**
  true sentences, wrongly rejected 0, and stopped **460 of 460** deliberately corrupted ones.
- Finnish summaries: **91 of 139** generated sentences shown; the rest dropped, never repaired.
- External facts on these slides: `submission/evidence-v2.json`, every link re-opened on
  14 November 2026, 22:53-23:03 UTC.
- Source: `data/claim-check/eval-v1.json`, `data/narratives/fi-v1.json`.

## A11. Safety net, gate, and what is still running

- Safety net, all 23 simulated areas (SYNTHETIC replay): **3,081** open loops, **496** overdue;
  114 referrals still without a diagnosis at the 90-day sensitivity count. Rule
  `forward-v1`, no model. Source: `data/safetynet/safetynet-v1.json` (`national`, `rule`).
- Gate: FLARE 2.9.1 simulator, 23 sites, precision 12; edge at 42.5 days so whole days up to 42
  count as within the placeholder. Real-data side: of the published areas, only Pirkanmaa reaches
  the 70% stage aim. Source: `data/flare/gate-v1.json`.
- Still running: frozen stress set, expression arm against lexicon rule A':
  [PENDING: data/scribe/v4/eval/results-v1.json]

## A12. Compute and spend recorded in files

- One Verda A100 80 GB: 2.51 h, USD 5.98 at the list price (not the invoice), shared with the Evo 2
  run. FLARE and MLX ran on this laptop at no cost.
- Nemotron on the Verda-hosted event endpoint: 2,602 reader requests with 0 request errors; price
  not verified, recorded as unknown, not zero.
- Source: `data/scribe/v2/training-figures-v1.json`, `data/scribe/nemotron/ledger.json`.

## A13. Limits

- Notes are SYNTHETIC, written from six date forms; real notes use other phrasings. Labels were
  checked by models, not people.
- The 700-note test set had been read before; 93.0% is post hoc. The frozen stress set is the
  number to trust once it exists.
- Nemotron's model card does not name Finnish; planner plans are English drafts.
- The scribe reads Finnish only. How many notes in a county are written in another language was not
  measured.
- Evo 2 on BRCA1 is a RESEARCH appendix outside the AstraZeneca pitch (`genomics/README.md`).
