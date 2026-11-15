# Progress

## Demo fixes after the first wave (15 November 2026, 01:20-01:55 UTC)

Owner `deliv-polish` (log `runs/deliv-polish.jsonl`). No git, no model run, no hosted call. Page fixes
from the demo QA findings, all read from the same JSON files as before:

- Start page: the survival tile reads "17.9% vs 31.1%" with "13.2 percentage points below
  Sweden–Norway" under it; provenance line "Public data snapshot, 14 Nov 2026 · 57 source requests".
- Ranking chart: round ticks (0.90 / 1.00 / 1.10), dashed line labelled "national = 1.00", ratios
  to 3 decimals. County pathway and Goal 3: one MEASURED chip per block, plain cancer-site names,
  "About 59 more cancer deaths a year than national rates predict for its age structure (estimate
  58.7; interval 37.9 to 79.9)".
- Tables no longer break inside words (`overflow-wrap: break-word` for cells; long codes keep
  `anywhere`); safety-net headers "Age", "Language"; "(fewer than 5 at the 90-day sensitivity
  threshold)"; build command and reason codes removed from the panel.
- Comparability gate: the two arms are "The model's own dates" and "Gemma reads, code counts"
  (`flare/flare.test.mjs` label assertions updated to match); plain event names; the histogram
  detail moved into the folded table.
- Planner: the plan comes right under the county list; the amber warnings became one small caption
  ("Drafted on an earlier data build; 1 sentence withheld by the check ..."); the method, prompt v1/v2
  and the tool re-check are in a folded block below the plan. The drafts were not re-run (no model
  calls in this step).
- Pilot card: "We chose Satakunta because ..." and "not under the state assessment procedure"
  (Finnish Government, 16 June 2026). First-action card: "Minimum for every county ... Optional for
  a pilot county ...".
- Gemma demo: opens on Note 4 (pre-filled, both readers agree); "MDT decision"; the raw model output
  is folded below the verdict; on phones each event is a label/value card; the not-run reason reads
  "Nemotron, the second reader, never read this rewritten note, so a person edits it".
- Scribe results (section 10): three plain numbers first (stress 280 / 223 / 88 / 85 of 308; new
  phrasings 120 / 95 / 0 / 11 of 143; two readers 684 of 700 pre-filled with 4 wrong), then one line
  labelled POST HOC for the vague-phrase gate (`data/scribe/vague/results-v1.json` via
  `src/tracks.mjs` `buildVague`), then the method and every table folded. p below 0.001 reads
  "< 0.001".
- `web/serve.mjs` reloads the demo files when they change on disk (no stale verdicts after a rebuild).
- Re-shot `submission/shots/` (39 files, 390 px at device scale 1: 15 MB instead of 30 MB), re-cropped
  `submission/deck/img/demo04-*.png` and the video frames (`submission/video/tools/crops.sh` offsets),
  re-printed `submission/deck/SAMA-deck.pdf` and re-rendered `submission/video/SAMA-video.mp4`.

## NVIDIA lanes integrated (15 November 2026, from 00:00 UTC)

Written by the lane integrator (log `runs/integrate-lanes.jsonl`). Nothing was committed or pushed. No
model, MLX or torch process was started by this step; no hosted endpoint was called.

**Added to the page** (the ship-wave panels, mount points, imports and section order are unchanged;
the new section is inserted between them):

| Section | What | Data in `app.json` | Source file |
| --- | --- | --- | --- |
| 06 `#insight` | Extraction errors manufacture fake county inequality (SYNTHETIC simulation) | `insight` | `data/eventlog/design-study-v1.json` (`measured_interval_extraction`, `findings`) |
| 07 `#plan` | Planner summary above the drafts: checks, prompt v1 against v2, off-limits, image-input test, and a re-run of every stored tool call on the current build | `planner` (`toolCheck` from `src/build.mjs`) | `data/planner/plans-v1.json`, `data/planner/vision/vision-6b-v1.json`, `data/planner/raw-v2/` |
| 10 `#scribe` | "Gemma reads, code counts": Gemma alone, the frozen resolver, the preregistered stress result, the system table, vague phrases, the two-reader cascade, the Nemotron reader ladder; the earlier versions folded into one block | `scribe.gemmaAlone`, `scribe.resolver`, `scribe.evaluation`, `scribe.reader` | `runs/diagnose/diagnose-v1.json`, `data/scribe/v4/resolver/reproduce-v1.json`, `data/scribe/v4/eval/results-v1.json`, `data/scribe/nemotron/reader-v1.json` |

Roadmap measure ids on every action, the Satakunta pilot card, the safety-net worklist, the FLARE
comparability gate and the Gemma demo route were already on the page from the ship wave and were
kept as they were.

**What ran (lane results, read from their files).**
- Gemma alone: 2/367 test notes with a relative date exactly right. Frozen code resolver on the same
  outputs: 289/310 validation, 651/700 test (post hoc), 0 notes made worse.
- Stress set: 308 SYNTHETIC notes, frozen and preregistered at 21:57:19 UTC. Preregistered criterion
  for the expression arm B **not met** (11/143 against 0/143 for the lexicon rule A', p = 0.00098; B
  73/87 on standard phrasings). Arm C (Gemma 3 1B, expression format) 95/143; Nemotron 120/143
  (optimistic: it wrote the notes). Vague phrases: A' 29/29 to a person; B invents a date for 17/29.
- Two-reader cascade, chosen on validation only (arm C plus agreement): 684/700 test notes pre-filled
  for one-click confirmation with 4 wrong (test set read before; post hoc); 220/308 stress notes with 3 wrong. A person confirms every
  note.
- Nemotron reader ladder on validation: 192, 282, 287, 290, 304 of 310; test once: 690/700.
- County planner: 255 of 299 sentences kept, 0 kept sentences with an unmatched number, 10/10
  off-limits requests with no plan (the model refused 9; the 10th is stopped by a county guard
  added after seeing prompt v1's answers to these same prompts, post hoc; without it, 9 of 10); image input 13/20 against 19/20 from text, "tested, not good
  enough yet". Re-running the stored tool calls on this build: 20 of 23 areas identical; HVA05,
  HVA06 (county brief) and HVA91 changed, and the page says "read with care" for them.
- Insight: no real difference, county read from notes against a structured country: flagged in
  1.000 of 1,000 runs as is, 0.003 with the resolver (0.003 with every event confirmed).

**Failed or not done.**
- The preregistered success criterion for arm B failed; the deck and write-up say so.
- The live CPU route `POST /api/scribe` was not run by this step: the Mac had 16.1 of 17.4 GB swap in
  use at 00:13 UTC, so the route was checked with `"mode":"precomputed"` only. Lane C measured the live
  route earlier (median 4.84 s per note under load, `data/scribe/demo/http-timing.json`).
- The agreement rule is now applied in the scribe demo (`serve/demo/engine.py` `apply_second_reader`,
  `web/serve.mjs`) from Nemotron's stored answers only: 15 of 20 demo notes pre-filled, 0 wrong; free
  text and the 3 notes rewritten by code need editing. It is not wired into `scribe/v3/cascade.py`, and
  no hosted model is called from the page.
- The planner drafts were not re-drafted on the current build; three areas' tool outputs changed.
- `submission/VERDA_DISCORD.md` keeps `[SUMMARY LINK]` for the owner, who decides where to publish.

**Synthetic.** Every note, every scribe figure, the insight, the safety net and the gate's clock are
SYNTHETIC. The planner read public aggregate data only.

**Unverified.** Nothing here was tested on real clinical notes. The Nemotron price on the event
endpoint is not known (cost recorded as null). The 700 test notes were read before tonight. The stress
set was written by Nemotron, so Nemotron's own score on it is optimistic.

## Ship wave 23:00-02:00 UTC (14-15 November 2026)

Written 23:20 UTC by the ship-integrate step (Lane C; log `runs/ship-integrate.jsonl`). Nothing was
committed or pushed. No model, MLX or torch process was started by this step.

**On the page now, in order** (`web/index.html`; section order is pinned by `tests/tracks.test.mjs`):

| Section | Panel | Data | Added by |
| --- | --- | --- | --- |
| 01 | Map and ranking (real data) | `web/data/app.json` `analysis` | earlier |
| 02 | Who, how and where: ECOLOGICAL county gradients beside the published individual-level figures and the route medians | `analysis.gradients`, evidence rows in `data/evidence/literature-v1.json` | ship-page, 23:02 |
| 05 | Process headline, Satakunta pilot card | `app.json` `roadmap` | ship-page, 23:02 |
| 05 `#safety-net` | **Close the loop: county safety-net worklist** (SYNTHETIC; follows the selected county, Satakunta is the pilot) | `app.json` `safetyNet`, bundled from `data/safetynet/safetynet-v1.json` | mounted by this step |
| 05 `#comparability-gate` | **Measure it only where it can be seen: FLARE comparability gate** (SYNTHETIC clock and gate; MEASURED public stage chip) | `app.json` `flareGate`, bundled from `data/flare/gate-v1.json` | mounted by this step |
| 06 | Nemotron county plan draft | `data/planner/plans-v1.json` (fetched) | ship-page, 23:02 |
| 09 | Gemma scribe demo (stored output first; "Run live" calls `POST /api/scribe`) | `data/scribe/demo/` | ship-page, 23:02 |
| footer | Evo 2 benchmark moved to `/research.html` | `data/genomics/brca1-evo2-v1.json` | ship-page, 23:02 |

**What this step changed.**
- `src/tracks.mjs`: `buildSafetyNet` and `buildFlareGate` with the same rules as the other tracks: an
  absent file leaves the panel out with the reason in `app.trackProblems`; a file without a field its
  panel reads fails the build. Extra guards: both files must be marked SYNTHETIC, at most three
  example rows per county, every numeric worklist threshold labelled PLACEHOLDER, the 42-day clock
  labelled a placeholder, every county an area of the public snapshot.
- `web/app.mjs` imports `web/safetynet.mjs` and `web/flare.mjs` (both unchanged, owned by their lanes)
  and fills the two mount points from `app.json`; a missing bundle or a failed render shows its reason.
- `web/index.html`: two nav links ("Close the loop", "Comparability gate"), section 05 intro.
  `web/styles.css`: panel layout. `src/build.mjs`: build summary names both panels.
- Tests: `tests/ship-panels.test.mjs` (7 tests) and `tests/flare-panel.test.mjs` (runs the FLARE lane's
  5 panel tests inside `npm test`); the stale-`app.json` check now covers both bundles.

**Checks run.** `node src/build.mjs`: 23 regions, 36 evidence rows, `safetyNet` and `flareGate`
present, `trackProblems` empty. `npm test`: 113 of 113 pass (101 before this step). `node --check`: 9
web modules and `src/build.mjs`, `src/tracks.mjs`, `src/claims.mjs`, `src/recommend.mjs`, all OK.
Own server `node web/serve.mjs` on port 4185 with `SAMA_SCRIBE_LIVE=0` (4179 was held by another
process, left alone): `/`, the modules and `/data/app.json` returned 200, and the served `app.json`
was byte-identical to the file; server stopped. Browser pane: no console errors; Satakunta tiles 120
open loops, 16 overdue, 30 of 50 imaging follow-ups done by the due date, 305 of 375 referrals with a
diagnosis by day 42 (placeholder); 23 gate rows; no horizontal page scroll at 375 px; tab closed.
Not tested: the live Gemma route.

**Headline numbers of the two panels** (all SYNTHETIC unless marked):
- Safety net (`data/safetynet/safetynet-v1.json`): rule `forward-v1` 60 of 60 on 60 lines; second
  check on 5,002 lines: 0 wrong or invented dates, 0 missed recommendations, 40 dated lines sent to a
  person; national 3,081 open loops, 496 overdue; Satakunta 120 and 16, replay date 2025-12-01.
- Gate (`data/flare/gate-v1.json`): NVIDIA FLARE 2.9.1, 23 simulated sites, 253 of 253 cells equal to
  the central table; 11,510 of 19,581 pathways (58.8%) within the 42-day placeholder; not comparable
  15 of 23 with the raw scribe, 1 of 23 with the code resolver; MEASURED stage chip (Syöpäjärjestöt,
  17 Jun 2026): country 42%, Pirkanmaa 72%, Sisä-Suomi 60%, other areas 33-42%, aim 70%.

**Rule for the first-wave integrator (02:00-03:15 UTC).** Keep these panels as they are: the section
order, the `#safety-net` and `#comparability-gate` mount points, the imports in `web/app.mjs`, the
`safetyNet` and `flareGate` keys of `app.json`, and `tests/ship-panels.test.mjs` and
`tests/flare-panel.test.mjs`. Only add the Lane A evaluation results
(`data/scribe/v4/eval/results-v1.json`, not present at 23:20 UTC) to the scribe section, then run
`node src/build.mjs` and `npm test` once on the final source. If the safety-net or FLARE lane rebuilds
its JSON, rebuild `app.json`: the stale check in `tests/tracks.test.mjs` fails until you do.

**Open after this step.**
- The live `POST /api/scribe` path was not exercised (memory rule).
- The stored Nemotron draft for Satakunta still says the county is "clearly worse" at referral; the
  page shows a "Read with care" note under it (`data/planner/plans-v1.json` belongs to Lane B).
- The safety-net file's legal line says a county may identify such patients "and contact them"; the
  deck lane reports that the re-opened STM page puts contacting only in a separate data-protection
  paragraph and writes "identify" (`runs/ship-deck.jsonl`). The wording belongs to the safety-net lane.
- Within one gate arm, county differences are sampling noise on 30-31 notes per county; the gate
  panel says so. The worklist's imaging completion is the same assumed 70% on time in every county.

**Stage:** working demo on real public data, with three supporting tracks. **Owner:** `astrazeneca`.
**PR:** SalesSquad/junction-pets#113. **Branch:** `codex/j26-astra-equity-m1-20261114`.
Last updated 14 November 2026, 20:53 UTC. Nothing in this update was committed or pushed.

Labels used below: **real** = public aggregate data or published literature; **SYNTHETIC** = simulated
people or notes written by language models; **RESEARCH** = a public laboratory benchmark, research use
only. Every figure names its source file.

## Verified: the product (real data)

| What | Evidence | Where it ran |
| --- | --- | --- |
| Public snapshot: 23 counties, 20 indicators, cancer deaths by site, NORDCAN survival; 57 requests with SHA-256 | `data/snapshot/public-v1.json`; expected deaths sum to observed nationally within 0.1% (`tests/navigator.test.mjs`) | MacBook Pro |
| Analysis, recommendations, optimiser, evidence binding, brief, guardrails | `npm test`: 72 of 72 node tests pass (last run 20:53 UTC, `runs/integrate-tracks-v3.jsonl`) | MacBook Pro, Node 26 |
| Goal 3 wording and indicators | read from the strategy PDF (Figure 1, section 3) | fican.fi |
| Claim check on the real service | 650 calls to TypeSafe `jev-1.14.0`: 161 of 190 true sentences auto-passed, 29 to human review, 0 wrongly rejected; 460 of 460 corrupted sentences stopped | `data/claim-check/eval-v1.json` |
| Finnish plain-language summaries | Claude Haiku wrote 139 sentences for 23 counties; 91 passed the number match and the TypeSafe check and are shown, 48 were dropped | `data/narratives/fi-v1.json` |
| Early-warning forecaster and sweep | no transformer beats the best baseline by more than the seed spread; a baseline is shipped for 6 of 8 indicators | `ml/artifacts/metrics.json`, `ml/artifacts/gpu-sweep/SWEEP_REPORT.md` |
| Build | `npm run build` writes `web/data/app.json` (sha256 in `runs/integrate-tracks-v3.jsonl`) with all three tracks and an empty `trackProblems` | MacBook Pro |
| Served page | `node web/serve.mjs` on port 4180 (4179 was already held by an earlier server of this project, left running): `/` and `/data/app.json` return 200; the existing server on 4179 also returns 200 and the same `app.json` bytes | MacBook Pro |
| Layout | at 375 px the page has no horizontal scroll (document width 375 px), no console errors, sections in order: product first, early warning, then the three tracks, then evidence; checked once in the built-in browser | MacBook Pro |

## Verified: the supporting tracks (bundled, tested, labelled)

`tests/tracks.test.mjs` (22 of the 72 node tests) binds every bundled figure to its file, checks that
a missing required field fails the build and an absent file is reported, that each data number on the
page sits under its `SYNTHETIC` or `RESEARCH` chip, and that no figure in those sections is typed into
the code (a deliberately typed figure made that test fail; it was then removed).

| Track | Headline | Source |
| --- | --- | --- |
| Data collection (SYNTHETIC) | a county needs 473 / 513 / 347 complete episodes (primary care / diagnostic / treatment) to detect a 20% slowdown at 80% power with 69 comparisons; 5 of 23 counties could detect it within a quarter, 20 within a year | `data/eventlog/design-study-v1.json` |
| Data collection, with the scribe's measured errors (SYNTHETIC) | a 500-episode county locates a planted 30% slowdown in 48.6% to 77.7% of runs (version-2 adapter, teacher-written notes) instead of 99.7% to 99.9%; extracting only one county's dates flags it in 100% of runs with no slowdown | `data/eventlog/design-study-v1.json` `measured_text_extraction` |
| Scribe, version-2 ablation (SYNTHETIC) | Gemma 3 270M LoRA r16 selected (validation 36.1%, n = 310); test exact match 42.0% (500 Nemotron-written notes) and 13.0% (200 Haiku-written) | `data/scribe/v2/ablation-v1.json` |
| Scribe, after the ablation (SYNTHETIC) | pooled exact match on 700 test notes: reference 33.7%, V3-270m-nemotron 38.1%, C-270m-all-v2data 43.6%, V3-270m-all 39.6%, 1B 38.6% (post hoc); no 4B number | `data/scribe/v3/student/compare-v1.json` |
| Scribe, serving (SYNTHETIC) | vLLM, 100 notes: valid JSON 100/100 (structured) and 98/100 (plain), exact 22% both, p50 1.28 s, p95 1.80 s at concurrency 8 | `serve/smoke/smoke-guided.json`, `serve/smoke/smoke-plain.json` |
| Teaching loop (SYNTHETIC) | gate accepted 1,506 of 1,589; Jev rule caught 66/80 planted errors, rejected 0/80 clean; cascade at 5%: student 28/270 wrong among notes that skipped review, Jev 7/263 | `data/scribe/v3/summary-v1.json` |
| Evo 2 on BRCA1 (RESEARCH) | missense only: strongest level "supporting" towards loss of function, none towards normal function; missense AUROC 0.709 (0.658 to 0.759); partial run, 2,150 of 3,893 variants | `data/genomics/brca1-evo2-v1.json` |

Python suites of the tracks were run by their owners, not by this update (from their run logs):
event log 35 tests OK (`runs/eventlog-fix.jsonl`); genomics 39 OK (`runs/genomics-fix.jsonl`);
scribe version 1 26 OK (`runs/scribe-v1-fix.jsonl`); scribe v3 29 OK (`runs/cascade-v3.jsonl`);
scribe v2 100, data v2 20, serve 114, ops 36 OK (`runs/training-md.jsonl`).

## Synthetic, by design

- Every scribe note was written by a language model (Nemotron as teacher, Claude Haiku as second
  writer) from a sampled answer key; labels were checked by models (TypeSafe Jev, OpenAI Decisions,
  Claude Haiku), not by people. No figure says the scribe works on real clinical text.
- The event-log study simulates people under assumed case counts, routes and step distributions;
  its sample sizes must be re-measured once real event data exist.
- Judge and auditor agreement is not ground truth.

## Tried and failed, or not included

- The planned version-1 GPU training: the first GPU machine stopped answering and later presented a
  different host key; a laptop fallback ran instead (`runs/train.jsonl`). Version 1 is kept on the
  page as superseded history.
- Version-2 ablation: the 1B and 4B sizes and every LoRA-variant, format and data arm were dropped
  for time (`data/scribe/v2/ablation-v1.json` `dropped`).
- 4B student: out of GPU memory twice; a third attempt was stopped to protect the pre-registered
  runs. No 4B number (`data/scribe/v3/student/RUNS.md`).
- V3-270m-all lost on Nemotron-written notes (39.4% against 42.0%, p 0.007), with the most rows for
  the same 324 steps; the cause was not tested (`data/scribe/v3/student/compare-v1.json`).
- Cascade: at the 5% target the student's own threshold gave 10.4% error on test; at the 10% target
  every signal's test error was above 10%. A judge did not let measurably more notes be pre-filled for
  one-click confirmation at 5% (a person confirms every note either way) (`data/scribe/v3/summary-v1.json` `cascade.verdict`).
- Evo 2: partial run (time budget) with a 4,096 bp window instead of 8,192 (memory cap); the window
  was chosen after an interim look (`data/genomics/brca1-evo2-v1.json`).
- An open-weight summary writer (Qwen3-32B-AWQ on vLLM) failed at start-up; nothing from it is used
  (`data/narratives/raw-open/RUN.json`).
- 76 identical judge-benchmark requests (50 Jev, 26 Decisions) were paid twice before a lock was
  added (`data/scribe/v3/judges/benchmark-v1.json` `design.paid_requests`).

## Not verified

- Dark mode, a screen-reader pass and the print stylesheet.
- Numeric national target times for cancer treatment (THL guidance 21/2016): not read at source.
- Health-content review by an oncologist or epidemiologist. No AstraZeneca mentor input is included.
- The claim-check pass rate moves by one or two sentences between runs near the 0.8 threshold.
- No hosted deployment. The demo runs locally only.
- The vLLM guard (`serve/guard.py`) was tested only against a fake app, not inside a live vLLM
  (`TRAINING.md`).

## Open

1. A Haiku-written test set whose writer sessions are disjoint from the training notes, and a held-out
   set for the new curricula (terse and long notes): the current test files cannot show either.
2. Re-run the scribe comparisons with matched epochs, and a 4B run on a card with room for it.
3. Finish the Evo 2 benchmark (1,743 variants left) at the published 8,192 bp window; this needs a
   new GPU, since the A100 was deleted at 19:27 UTC.
4. Documents owned by other workers that are now stale: `DATA_COLLECTION.md` section 4 still lists
   the round-2 student as "not yet measured" (the result is in `compare-v1.json`); `scribe/TEACHING.md`
   sections 1, 8 and 9 still say the cascade and the student comparison did not happen and give
   older spend totals; `TRAINING.md` points to `scribe/TEACHING.md` for the cascade instead of
   `data/scribe/v3/cascade/cascade-v1.json`.
5. From before: mentor review of the action library and costs; county incidence by site and stage
   from the Finnish Cancer Registry; THL target times; a hosted demo once publication is decided.

## Spend recorded in files

- Verda A100 `az-equity-a100-20261114`: list price times wall time USD 5.98 (16:56 to 19:27 UTC),
  not the invoice (`data/scribe/v2/training-figures-v1.json` `machine_cost`). The first GPU machine
  (`az-equity-gpu-20261114`) and the earlier spot V100 and A100 are not priced here.
- TypeSafe: USD 0.5758 over the three scribe ledgers (`training-figures-v1.json` `api_spend`).
- OpenAI Decisions: 1,283,798 tokens over 876 requests, USD 0.1284 at the list rate
  (`data/scribe/v3/judges/usage-openai.json`, `data/scribe/v3/summary-v1.json`).
- Claude Haiku: USD 0.070736 (version-1 test notes) and USD 0.049846 (version-2 writer pilot)
  recorded; the rest of the version-2 writing and the round-2 audit were not recorded.
- Nemotron teacher: 4,500 + 4,042 requests, not priced.
- No total project cost exists.
