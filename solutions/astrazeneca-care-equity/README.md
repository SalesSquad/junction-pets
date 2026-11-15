# SAMA: Care Equity Navigator

**Junction 2026, AstraZeneca challenge M344 "Equal Care Across Finland".** *Sama* is Finnish for
"the same": the same cancer pathway for everyone, wherever they live, whoever they are, however they
enter care.

## Quick start

SAMA is a decision-support page for Finland's cancer pathway: public data on who is missed and where, plus a pathway clock and a nurse's follow-up list that a person checks. Everything patient-like in it is SYNTHETIC, and a person confirms every extracted event.

```bash
npm test     # checks, no install and no keys needed
npm start    # then open http://127.0.0.1:4179 (default PORT in web/serve.mjs); the page uses stored outputs
```

Jury view: http://127.0.0.1:4179/?jury shows only the demo path. Optional live Gemma (laptop CPU): see `submission/DEMO_SCRIPT.md`. Optional live Nemotron ("Ask Nemotron live" button): see `submission/DEMO_SCRIPT.md`, step 7.

Links: [deck (PDF)](submission/deck/SAMA-deck.pdf) | [demo script](submission/DEMO_SCRIPT.md) | [Q&A](submission/QA.md) | [video source](submission/video/) (the rendered MP4 is kept out of git; rebuild it from that folder)

| Result | Value | Source file |
| --- | --- | --- |
| Lung cancer survival, men, relative (Finland vs Sweden-Norway mean) | 17.9% vs 31.1% | `web/data/app.json` `analysis.goal3` |
| Two-reader rule, pre-filled for one-click confirmation | 684/700 test notes, 4 wrong (post hoc); 220/308 frozen stress notes, 3 wrong | `data/scribe/v4/eval/results-v1.json` |
| Gemma 3 1B alone on the stress set | 85 of 308 notes wrong | `data/scribe/v4/eval/local-pairs-posthoc-v1.json` (post hoc) |
| FLARE vs central table; comparability | 253/253 cells equal; 15 of 23 counties not comparable with the model's own dates, 1 of 23 with the code resolver | `data/flare/gate-v1.json` |
| Safety net, Satakunta replay (SYNTHETIC) | 16 of 120 open loops overdue | `data/safetynet/safetynet-v1.json` |
| County planner drafts | 255 of 299 sentences kept | `data/planner/plans-v1.json` |

## The story

**In the public data we could read, who you are and how you enter care show clearer cancer gaps in
Finland than where you live.** We found no significant regional difference in five-year survival,
but one by education, and one by the door a patient comes in through. The regional result is not
significant, and low power is not evidence of absence, so this does not show that place is
irrelevant. Finland also has a target we found no open way to check: the OECD/EU reports six weeks
from a suspected-cancer referral to treatment, the treatment guarantee in law allows up to six
months, and we found no county that publishes the time for any cancer. SAMA is the missing
measurement and action layer:

1. **See who, how and where** on public data (the panel right after the map).
2. **Measure it only where it can be seen.** A county computes its own referral-to-treatment clock
   where its data live (NVIDIA FLARE, on SYNTHETIC data), and it is compared only when it can see
   itself.
3. **Close loops, don't count them.** The same clock becomes a nurse's daily list of people whose
   next step is overdue. A nurse confirms every item; SAMA never decides what follow-up is due.
4. **Pilot: Satakunta, lung follow-up first**, chosen on process grounds, inside the national cancer
   roadmap. The county owns the list and the care; the design keeps patient data inside the county (a design, not built yet).

Everything patient-like in SAMA is SYNTHETIC and labelled so on the page.

## The finding: who and how, not only where

| Finding | Value | Source |
| --- | --- | --- |
| Five-year relative survival by education (individual level) | lower 64% (men) and 65% (women) vs higher 77% and 78%; no significant regional difference | OECD/EU Country Cancer Profile Finland 2025, p. 20 (evidence row `oecd-2025-survival-education`) |
| Screening participation by education and mother tongue | breast 66% vs 85% by education, 63% vs 82% by mother tongue (2020-21); cervical 51% vs 78% and 57% vs 73% | same profile (rows `oecd-2025-*-screening-*`) |
| Symptom to treatment by entry route | median 127 vs 76 days, public primary-care appointment vs private or occupational care, 48 vs 39 patients, p = 0.027, one Finnish DLBCL cohort | Kuitunen J et al. 2026 (row `kuitunen-2026-route-medians`) |
| County education gradients (ecological) | all 10 slope intervals include zero | `web/data/app.json` `analysis.gradients` |
| Lowest breast-screening attendance, 2024 | the five lowest areas are all in Uusimaa: Helsinki 74.3%, West Uusimaa 76.1%, Vantaa-Kerava 76.7%, East Uusimaa 79.8%, Central Uusimaa 80.5% | `web/data/app.json` `analysis.indicators.screen_breast` |

County averages cannot show who is missed. Programme attendance is lowest in the capital region:
the OECD/EU profile says Helsinki's low participation is likely because screening outside the
programme is more frequent there, and Vantaa-Kerava, Helsinki and West Uusimaa have the highest
foreign-background shares in the snapshot (288.9, 216.1 and 199.8 per 1,000 inhabitants, 2025,
`analysis.indicators.foreign_background`). A county league table therefore measures recording and
population mix as much as access. The page labels the county gradients
ECOLOGICAL and puts the published individual-level figures beside them, then the actions that
already target the gap (roadmap measure 1.3.1, mailed HPV self-sampling).

## The two new panels (section 05 of the page, all SYNTHETIC)

**Close the loop: the county safety-net worklist** (`data/safetynet/safetynet-v1.json`, built by
`safetynet/build.py`, rendered by `web/safetynet.mjs`). A frozen code rule (`forward-v1`) copies the
follow-up date a radiologist wrote; ranges and vague phrases go to a person. On 60 SYNTHETIC report
lines it got 60 of 60 right; on 5,002 more lines rendered from the same templates with new seeds it
made 0 wrong or invented dates and missed 0 recommendations, and sent 40 dated lines to a person
instead. The rule and its test lines come from the same step, so this covers its own templates, not
real reports. Satakunta, replayed as of 2025-12-01: 120 open loops, 16 overdue; 305 of 375
referrals had a diagnosis by day 42 (a placeholder). Counts come first, then at most three unnamed
SYNTHETIC rows. The list follows the county selected on the page; Satakunta is the proposed pilot.

**Measure it only where it can be seen: the comparability gate** (`data/flare/gate-v1.json`, built
by `flare/build_gate.py`, rendered by `web/flare.mjs`). NVIDIA FLARE 2.9.1 ran on 23 simulated county
sites on this Mac; only filtered totals left each site, and FLARE equals the plain-Python central
table in 253 of 253 cells (tolerance 1e-6). Nationally 11,510 of 19,581 SYNTHETIC pathways (58.8%)
started treatment within 42 days of the referral being sent; 42 days is a placeholder for the
OECD/EU-reported target. If a county's dates were read from notes by the raw Gemma scribe, 15 of 23
counties would be "not comparable"; with the code date resolver, 1 of 23. Differences between
counties within one arm are sampling noise on 30-31 notes per county, not county effects. Beside it,
one MEASURED chip on public data asks "Can this area see its cancer stage?": stage is recorded for
42% of cancers in the whole country, 72% in Pirkanmaa, 60% in the Sisä-Suomi area and 33-42% in the
other areas, against an aim of at least 70% (Syöpäjärjestöt, 17 Jun 2026, as stored in the gate
file).

Both panels are bundled into `web/data/app.json` (`safetyNet`, `flareGate`) by `src/tracks.mjs`
with the same rules as the other tracks: a missing file leaves the panel out with the reason in
`app.trackProblems`, and a file without a field the panel reads fails the build.

## What SAMA does on public data

SAMA answers the three questions of the brief on real public data, with a source for every number:

1. **Identify the gap.** 23 areas (Finland's 21 wellbeing services counties, the City of Helsinki,
   which organises its own services, and Åland), 20 open indicators, cancer deaths by site 2021-2025,
   Nordic survival benchmarks, and the published individual-level gaps by education, mother tongue
   and entry route. National measures and the 2026 law are not claimed for Åland.
2. **Locate it on the pathway.** Detection, primary care, referral, diagnosis, treatment start,
   outcome. Where public data cannot see a stage, the tool says so and treats that as a finding.
3. **Recommend what to do.** Eight evidence-bound actions with owner, mechanism, cost assumption,
   scenario effect with a range, the indicator to monitor and what is not known; a budget optimiser
   with an explicit inequality-aversion weight; and a claim check on every sentence of the brief.

It is decision support for planners. It makes no diagnosis, no patient-level inference and no
causal claim about a county.

## What the data shows (snapshot of 14 November 2026)

| Finding | Value | Source |
| --- | --- | --- |
| Five-year lung cancer survival, men, 2020-2024 | Finland 17.9% vs Sweden-Norway mean 31.1% (gap 13.2 points) | NORDCAN |
| Cancer deaths per year, 2021-2025 mean | 13,289; strategy target 11,960 (minus 10%) | Statistics Finland |
| Same age-specific death rates on the 2035 population | 15,798 deaths a year | Statistics Finland projection |
| Colorectal screening below the 80% target | 22 of 22 counties with data | THL Sotkanet |
| Cervical screening below the 80% target | 20 of 23 areas | THL Sotkanet |
| Highest age-standardised cancer mortality | Satakunta 1.10 and Kymenlaakso 1.10 times the national level, about 59 and 46 more deaths a year | Statistics Finland |
| Lung cancer mortality (larynx, trachea and lung, C32-C34), Lapland | 1.24 times the national level | Statistics Finland |
| Symptom to treatment, public primary-care appointment vs private or occupational care | median 127 vs 76 days, 48 vs 39 patients, p = 0.027, one Finnish DLBCL cohort | Kuitunen J et al. 2026, p. 4 |
| Five-year relative survival by education (individual level) | lower 64% (men) and 65% (women) vs higher 77% and 78%; no significant regional difference | OECD/EU Country Cancer Profile Finland 2025, p. 20 |
| Screening participation by education and mother tongue | breast 66% vs 85% by education, 63% vs 82% by mother tongue (2020-21); cervical 51% vs 78% and 57% vs 73% | same profile, p. 15 |
| County education gradients (ecological) | all 10 slope intervals include zero; the five lowest breast-screening areas are all in Uusimaa | `web/data/app.json` `analysis.gradients` |
| Target from suspected-cancer referral to treatment | six weeks as reported by the OECD/EU (p. 19); the treatment guarantee in law allows up to six months for non-urgent specialised care and names no cancer-specific limit | OECD/EU 2025; STM hoitotakuu, updated 29 Oct 2026 |
| Time from referral to treatment, by county | we found none published for any cancer | (data gap) |

Goal 3 of the National Cancer Strategy 2026-2035 ("Ensuring equal and effective cancer care") is
covered by all three of its indicators: Nordic-level survival for poor-prognosis cancers, cancer
mortality minus 10%, and treatment within target times. The third cannot be computed from open
data, which is why the first recommended action is to record four pathway timestamps nationally.

All figures in this table are in `web/data/app.json` (built from `data/snapshot/public-v1.json` and
`data/evidence/literature-v1.json`; every external figure is a verified evidence row with the page it
was read from).

## The page, in order

1. **The gap** (map) and **who, how and where**: county education gradients labelled ECOLOGICAL
   with their intervals, beside the published individual-level figures and the route medians.
2. **The county pathway** and **Goal 3**. A flag that the latest year does not confirm is shown as a
   possible signal (Satakunta's referral indicator, a whole-percent value equal to the national one
   in 2025).
3. **What to do**: the headline is a process metric (share treated within the placeholder threshold;
   share of overdue referrals followed up on time), then the Satakunta pilot card, then the
   portfolio model, labelled as an upper-bound SCENARIO. Every action names its roadmap measure id
   (`src/roadmap.mjs`). After the pilot card: the safety-net worklist (`#safety-net`, follows the
   selected county) and the FLARE comparability gate (`#comparability-gate`), both SYNTHETIC.
4. **The insight** (section 06, SYNTHETIC simulation, `app.json` `insight` from
   `data/eventlog/design-study-v1.json` `measured_interval_extraction`): extraction errors manufacture
   fake county inequality. With no real difference anywhere, a county of 500 pathways whose dates are
   read from notes by the scribe as it was, against a country with structured dates, is flagged as
   slower in 1.000 of 1,000 runs; with the code date resolver in 0.003, the same as with every event
   confirmed by a person (0.003). Writing style alone (county notes like Haiku's, country like
   Nemotron's): 0.018 as is, 0.004 with the resolver.
5. **County plan draft** (section 07): a summary bundled in `app.json` `planner` (what was checked,
   prompt v1 164 against prompt v2 255 of 299 sentences kept, off-limits requests: the model refused 9
   of 10; the 10th was stopped by a county code guard added afterwards, after seeing prompt v1's
   answers to these same prompts (post hoc), the image-input test 13 of 20 against 19 of 20 from text, "tested, not good enough yet"),
   then the stored Nemotron 3.5 Super VL drafts (`data/planner/plans-v1.json`), labelled "Draft for a
   planner, drafted by Nemotron 3.5 Super VL; numbers checked". The build re-runs every stored tool
   call on the current data (`src/build.mjs` `plannerToolCheck`): 20 of 23 areas get identical tool
   outputs; HVA05, HVA06 and HVA91 do not, and their drafts carry a small caption "Drafted on an
   earlier data build" (the tool names and the method sit in a folded block below the plan).
6. **Analyst brief**, then the two SYNTHETIC tracks; the scribe section opens with the Gemma demo
   (`POST /api/scribe`; the stored CPU outputs in `data/scribe/demo/` are shown first and used when
   the route is unavailable), then "Gemma reads, code counts" (below), with the earlier versions,
   the teacher and the judges folded into one collapsed block.
7. The Evo 2 benchmark is not on this page: it is a separate research appendix (`/research.html`).

## How SAMA reads notes, checks itself and federates (below the product, never feeding it)

Two SYNTHETIC studies sit under the product on the same page (how it reads notes and how it checks
its own data), and one RESEARCH benchmark sits on a separate appendix page (`web/research.html`). None of them changes a county figure, a
recommendation or the brief (`tests/tracks.test.mjs` checks this). Each is labelled on the page and
in `app.json` as `SYNTHETIC` or `RESEARCH` and names the JSON file every figure is copied from.
`src/build.mjs` fails if a cited file lacks a field it needs, and leaves a part out, with the reason
in `app.trackProblems`, if the file is absent.

**1. The data to collect** (SYNTHETIC; `data/eventlog/design-study-v1.json`, `DATA_COLLECTION.md`).
A pathway event log in Parquet, one row per dated event, and a simulation study of how many records
make it useful. To find a county 20% slower in one interval at 80% power with 69 comparisons
controlled, a county needs 473 (primary care), 513 (diagnostic) and 347 (treatment) complete
episodes. Under an assumed 37,000 cases a year, 5 of 23 counties could detect a 20% slowdown in
every interval within a quarter and 20 within a year. Fed with the scribe's measured errors (version-2
adapter, teacher-written notes), a 500-episode county locates a planted 30% slowdown in 48.6% to
77.7% of runs, against 99.7% to 99.9% with confirmed dates, and a county whose dates come from text
while the rest of the country uses structured fields is flagged in 100% of runs when nothing is wrong.
Simulated people under stated assumptions; not Finnish patients.

**2. Pathway scribe: Gemma reads, code counts** (SYNTHETIC; `TRAINING.md`, `scribe/TEACHING.md`,
`scribe/v4/RESULTS.md`). A small Gemma model with a LoRA adapter reads a Finnish note and copies each
date phrase; code computes the date; a second reader checks; a person confirms every event. Every
note was written by a language model, and the scribe reads Finnish notes only.
- Gemma alone does the date arithmetic badly: 2/367 test notes with a relative date exactly right
  (`runs/diagnose/diagnose-v1.json`). The frozen code date resolver (`scribe/v3/resolve.py`, frozen
  21:37:24 UTC) on the same stored outputs: 289/310 validation and 651/700 test notes (post hoc; from
  134 and 305), 0 notes made worse (`data/scribe/v4/resolver/reproduce-v1.json`).
- Frozen, preregistered stress set of 308 notes with phrasings no training note used
  (`data/scribe/v4/eval/results-v1.json`): the preregistered criterion for the expression-format arm
  B is not met (11/143 on held-out phrasings against 0/143 for the lexicon rule A', p = 0.00098; B
  73/87 on standard phrasings). The 1B expression arm C got 95/143, Nemotron 120/143 (optimistic:
  it wrote these notes). Vague phrases: A' sends 29/29 to a person; B invents a precise date for
  17/29.
- Nemotron 3.5 Super VL as second reader (`data/scribe/nemotron/reader-v1.json`), one change at a
  time on validation: absolute dates 192/310, copy-the-phrase with code arithmetic 282/310, plus
  validation and grounding 290/310, plus thinking 304/310; the selected version read the test notes
  once: 690/700.
- Two readers, one person, evaluated offline on stored outputs: a note is pre-filled for one-click
  confirmation only when the code-resolved Gemma answer and Nemotron agree. Chosen on validation
  only (arm C plus agreement): 684/700 test notes pre-filled with 4 wrong (test set read before;
  post hoc), 220/308 stress notes with 3 wrong; the earlier rule
  pre-filled 263 with 7 wrong. Everything else needs editing, and a person confirms every note.
  The scribe demo applies the same rule to Nemotron's stored answers for its SYNTHETIC notes with
  the 270M product adapter (`C-270m-all-v2data`; 651/700 test notes with that adapter, post hoc):
  15 of 20 demo notes pre-filled, 0 wrong; free text and notes rewritten by code have no second
  answer and need editing. "15 of 20 pre-filled" and "18 of 20 exact" are different measures:
  pre-filled counts notes where both readers agree, exact counts notes where the 270M reader alone
  matches the answer key. By default the page calls no hosted model; the optional "Ask Nemotron
  live" button under Note 4 does (see `submission/DEMO_SCRIPT.md`).
- Version-2 ablation on one A100 (`data/scribe/v2/ablation-v1.json`): selected Gemma 3 270M LoRA r16
  (validation exact match 36.1%, n = 310); test exact match 42.0% on 500 teacher-written (Nemotron)
  notes and 13.0% on 200 notes by a different writer (Haiku). The 1B and 4B sizes and every later
  arm were dropped for time.
- After the ablation (`data/scribe/v3/student/compare-v1.json`, 700 pooled test notes): reference
  33.7%; V3-270m-nemotron, the pre-registered primary, 38.1% (other writer 13.0% to 29.0%, its
  no-event notes 0/33 to 21/33; teacher-written 42.0% to 41.8%, p 1.0); C-270m-all-v2data 43.6%
  (Holm p 8.7e-16, all of the gain on the other writer's notes; teacher-written 42.0% to 42.0%);
  V3-270m-all 39.6% (but 39.4% against 42.0% on teacher-written notes, p 0.007); Gemma 3 1B (post
  hoc) 38.6%. Every run had 324 optimisation steps, so a larger training set is seen for fewer
  epochs (1,716 notes 3.0, 2,354 notes 2.2, 3,222 notes 1.6, 3,860 notes 1.3); the data arms differ
  in epochs as well as in data. No 4B number: it ran out of GPU memory twice and a third attempt was
  stopped.
- Serving (`serve/smoke/smoke-guided.json`, `serve/smoke/smoke-plain.json`): vLLM on the A100,
  100 held-out notes at concurrency 8: valid JSON 100/100 with structured outputs and 98/100 without;
  exact match 22% both ways (half the notes are by the other writer); latency p50 1.28 s and p95
  1.80 s with structured outputs. Every note went to a person; no threshold was calibrated.
- Teaching loop (`data/scribe/v3/summary-v1.json`): the Nemotron teacher wrote notes for 1,600
  answer keys (4,042 requests); 1,589 passed the code check, 1,465 of those were read back exactly,
  and the Jev gate accepted 1,506 of 1,589. On planted errors the Jev rule caught 66/80 and rejected
  0/80 clean notes (its question set was designed after earlier results were seen); OpenAI Decisions
  caught 58/80 and rejected 11/80. A Haiku audit found 2/160 wrong labels among sampled accepted
  notes. Cascade experiment at a 5% target on 700 test notes (on the page a person still confirms
  every note): the student's own confidence would have accepted 270 notes with 28 of them wrong
  (10.4%, above the target); the Jev score 263 with 7 wrong (2.7%). More notes accepted: no, within
  noise. Lower error among them: outside test-sampling noise, but within noise once the thresholds
  are re-chosen on resampled validation notes.
- Version 1 (laptop fallback, Gemma 3 1B on MLX) stays on the page as history, marked superseded.

**3. Research appendix, separate page: Evo 2 on BRCA1** (RESEARCH; `data/genomics/brca1-evo2-v1.json`,
`genomics/README.md`). The open Evo 2 7B model scored 2,150 of 3,893 single-letter BRCA1 changes (a
partial run, 4,096 bp window instead of the published 8,192) against the laboratory assay of
Findlay et al. 2018. Headline, missense variants only: the strongest evidence level reached is
**supporting** towards loss of function and none towards normal function, with both the Tavtigian
2018 and the Pejaver 2022 thresholds; missense AUROC 0.709 (0.658 to 0.759); Evo 2 minus CADD on the
same variants -0.048 (-0.103 to 0.004). Over all types of change the AUROC is 0.822 (0.790 to 0.855)
and the level "moderate", for reference only. Research use only; nothing here classifies a variant
or informs any clinical choice.

## Run it

```bash
npm test            # statistics, real-data analysis, optimiser, evidence binding, guardrails, decision briefs, forecast integrity, roadmap, planner, page panels, safety net and gate, insight, scribe lanes, supporting tracks
npm run data        # refetch the public snapshot (THL Sotkanet, Statistics Finland, NORDCAN)
npm run build       # analysis + recommendations + supporting tracks -> web/data/app.json
npm start           # http://127.0.0.1:4179
```

Node 22 or newer; the product has no runtime dependencies. `npm run data` needs Python 3.10+
(standard library only). The claim check uses TypeSafe when `TYPESAFE_API_KEY` is set in the
server environment; without it the interface reports "not configured" and nothing is guessed.
`npm run build` reads the committed result files of the supporting tracks; re-running those studies
needs the Python environments, services and GPU described in `DATA_COLLECTION.md`, `TRAINING.md`,
`scribe/TEACHING.md` and `genomics/README.md`.

## How it works

- `pipeline/fetch_public_data.py` builds `data/snapshot/public-v1.json`. Every request URL, its
  retrieval time and the SHA-256 of the raw response are kept in the manifest.
- `src/stats.mjs`, `src/analysis.mjs`: exact Poisson intervals, indirect age standardisation,
  gamma-Poisson empirical Bayes shrinkage, false-discovery-rate control, slope index of inequality.
  Small counts are suppressed instead of ranked.
- `src/recommend.mjs`: the action library, the scenario model and the budget optimiser. Effects come
  from `data/evidence/literature-v1.json`; costs are planning assumptions the user can change. Each
  scenario number has a range from 300 parameter draws, and a stability score.
- `src/claims.mjs`, `src/claim-check.mjs`: the county brief is templated from the analysis (no
  language model writes numbers). A TypeSafe System One model answers two narrow questions per
  sentence: is it faithful to its facts and evidence, and does it overclaim? Anything short of a
  confident pass goes to a human. Measured on this product (`src/eval-claim-check.mjs`, 650 real
  calls, `jev-1.14.0`): 161 of 190 true sentences passed automatically, none was wrongly rejected,
  and all 460 deliberately corrupted sentences (flipped direction, changed number, wrong county,
  added causal claim) were stopped.
- `src/narratives.mjs`: plain-language Finnish summaries written by Claude Haiku. A sentence is
  shown only if every number in it occurs in its source claims and the TypeSafe check passes;
  failed sentences are dropped, never repaired. Of 139 generated sentences 91 are shown.
- `src/decisions.mjs`: source-scoped county decision briefs; registry context does not feed the
  optimiser. `src/forecast-integrity.mjs` admits only structurally supported forecast horizons.
- `ml/`: research forecasting against persistence, drift and ridge. The historical 14-configuration
  GPU sweep did not demonstrate an improvement beyond seed spread. Its overlap and no-winner
  export defects prevent qualification; the demo withholds its forecasts. Historical selection
  was two transformers, five baselines and one indicator with no winner. Corrected code alone
  does not establish new forecast performance.
- `src/tracks.mjs`, `web/tracks.mjs`: the three supporting tracks, copied from their result files
  with a source and a label for every figure. A test fails if a figure on those sections is typed
  into the code instead of read from data. `src/tracks.mjs` also bundles the safety-net worklist
  and the comparability gate; `web/safetynet.mjs` and `web/flare.mjs` render them
  (`tests/ship-panels.test.mjs`; `tests/flare-panel.test.mjs` runs the FLARE lane's own panel tests).
- `safetynet/` (Python standard library, pyarrow, and `eventlog/schema.py` read only): the frozen follow-up rule, the SYNTHETIC
  report lines and the worklist join. `flare/`: the NVIDIA FLARE job, its site partitions and the
  gate. Rebuild commands are in `data/safetynet/SCHEMA.md` and `flare/README.md`.
- `web/`: static demo with a self-only content security policy. The main product comes first; the
  supporting tracks follow it.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the data flows, model equations and limits,
[PROGRESS.md](PROGRESS.md) for what was verified, what is synthetic, what failed and what is open,
and [runs/RUNLOG.md](runs/RUNLOG.md) for one line per run.

## What it does not claim

- A county difference is a measured difference between populations, not proof of worse care and
  not a statement about any patient.
- "Deaths postponed" is an upper-bound scenario under stated assumptions, shown below the process
  headline. Its honest lower bound is zero.
- The route gap comes from one Finnish cohort of one cancer (87 patients in the two route groups) and
  is used as a prior. The model's 84-day central value is read from Figure 1 of the paper (means 207 vs 123 days); the paper's text gives means of 201 vs 126 and medians of 127 vs 76.
- Costs are placeholders for planning, not prices.
- The safety-net rule was measured on SYNTHETIC lines from its own templates, not on real radiology
  reports. A nurse confirms every worklist item; SAMA never decides what follow-up is due. Whether
  the 1 June 2026 law covers the timing of pathway steps is not confirmed.
- The FLARE run is a simulation (the third of the three tracks, how counties federate): 23 sites on one Mac reading partitions of one folder, no network or
  site approval. FLARE is not a legal permit, and aggregates still need a disclosure policy.
- Every 42-day threshold is a placeholder for the OECD/EU-reported six-week target; We found no
  cancer-specific limit in Finnish law.
- Nothing from simulated people or model-written notes is a finding about Finnish patients, and we
  have not tested any scribe result on real clinical text. Judges and auditors are models;
  their agreement is not ground truth.
- The genomics benchmark is research only and sits on a separate appendix page: no variant
  classification, no clinical use.
- AstraZeneca sponsors the challenge. No AstraZeneca data or product information is used, and no
  medicine is recommended.

## Changelog: decision and evidence update (15 November 2026)

Start at **One county. One next step.** Select a county to see its measured mortality
result, a separately labelled pathway question, and a proposed 30-day investigation
with an accountable owner, denominator, missing-data rule and 90-day review. The
investigation order is transparent; it is not an estimate of which action saves most
lives. General healthcare access remains a proxy for cancer pathways. County and
national observations must cover the same actual years before a signal enters this
new decision view. The existing scenario optimiser remains a separate planning tool.

The downloadable/printable brief includes source scope and limitations. National
lung/trachea registry context is **7,097 of 14,873 cases (47.7%)** without recorded
extent information in the 2019–2023 report; it is not assigned to counties, other
cancers or model parameters. Missing extent/MDT records do not establish absent care.
See [registry evidence](data/evidence/registry-context-v1.json) for the source tables.
Goal 3.1/3.2 links the proposed measurement work to timely, comparable pathways.
Precision diagnostics is a clearly unimplemented Goal 4.3 direction; BioNeMo has not
been run on this product and no molecular or clinical benefit is claimed.

**Historical forecasts are withheld from the demo.** The saved run reused 2023
validation targets in test evaluation. Colorectal screening also had no validation
winner but was exported as persistence with collapsed intervals. The original
artifacts are preserved byte-for-byte. New code enforces disjoint target years,
per-horizon training/validation/test evidence, and abstention for missing evidence.
A corrected public-data evaluation has **not** yet been executed. See
[the evaluation protocol](ml/README.md) and [historical audit](data/ml/forecast-v1-audit.json).

## Disclosure

The `engine.mjs` guardrail module and its 14 tests were written earlier in the event as milestone 1
on invented fixtures (`fixtures/regions.json`, still labelled synthetic). Everything else here was
built during Junction 2026; the supporting tracks use simulated people, model-written notes and a
public laboratory benchmark, never patient data. Built with Claude Code and Codex CLI. Runtime
services of the product are TypeSafe System One (claim check) and Claude Haiku (Finnish summaries). The
video's narration is a synthetic voice (ElevenLabs), generated from `submission/VIDEO_SCRIPT.md`.
The supporting tracks also used NVIDIA Nemotron on Verda (teacher), TypeSafe Jev and OpenAI
Decisions (judges), Claude Haiku (second writer and auditor), Gemma 3 (student) and Evo 2
(genomics). GPU work ran on Verda; the A100 that ran the version-2 scribe runs, the vLLM smoke test
and the Evo 2 scoring was deleted at 19:27 UTC after its results were copied back.
