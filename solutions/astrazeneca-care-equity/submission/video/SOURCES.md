# SAMA video: where every number on screen comes from

`SAMA-video.mp4` (1920x1080, 119 s). Paths are relative to `solutions/astrazeneca-care-equity/`.
All patient-like content (worklist rows, the referral note, FLARE sites) is SYNTHETIC and is labelled
SYNTHETIC on screen. Numbers were checked against these files at 2026-11-15 ~01:20 UTC. If one of
the files changes before submission, re-check the matching line here and re-render.

The spoken numbers are the same as in `submission/VIDEO_SCRIPT.md` ("Where each spoken number comes
from"). This file also covers the numbers that appear only on screen.

## 0:00-0:19 The gap

| On screen | Value | File and key |
| --- | --- | --- |
| Lung cancer, men, five-year relative survival, Finland | 17.9% | `web/data/app.json` → `analysis.goal3.indicators[id=nordic-survival].rows[site=lung, sex=male].finland` |
| Sweden-Norway average | 31.1% | same row, `.benchmark` (mean of `sweden` 31.3 and `norway` 30.8) |
| "13.2 percentage points behind" | 13.2 | same row, `.gap` (-13.2) |
| Period label | NORDCAN 2020-2024 | same row, `.period` |
| Line chart, 1980-84 to 2020-24 | Finland 9.4 ... 17.9; benchmark 8.4 ... 31.1 | same row, `.history[].finland` and `.history[].benchmark` (axis ticks 10/20/30 are scale only) |
| "SAMA maps all 23 areas" | 23 | `web/data/app.json` → `analysis.regions` (23 entries) |
| "Curable cases are mostly found by chance ..." (paraphrase), programme 2026-2035, May 2026 | - | `submission/evidence-v2.json` → `filha-2026-found-by-chance` |
| Product screenshots (start page, area map) | numbers inside the captures | `submission/shots/01-hero-1440.png`, `02-gap-map-1440.png` (captured from the running page, which reads `web/data/app.json`); cropped by `tools/crops.sh` |

## 0:19-0:43 Who, how and where

| On screen | Value | File and key |
| --- | --- | --- |
| Five-year survival by education, men lower / higher | 64% / 77% | `submission/evidence-v2.json` → `oecd-2025-fi-survival-education.values.lower_men`, `.higher_men` |
| Women lower / higher | 65% / 78% | same row, `.lower_women`, `.higher_women` |
| "Survival does not differ significantly between regions" | - | same row, `.fragment` |
| First symptom to treatment, median, public health centre / occupational or private | 127 days / 76 days | `submission/evidence-v2.json` → `kuitunen-2026-route-medians-groups.values.median_public`, `.median_fast` |
| "48 against 39 patients · p = 0.027" | 48, 39, 0.027 | same row, `.n_public`, `.n_fast`, `.p` |

## 0:43-1:12 Measure it where it can be seen

| On screen | Value | File and key |
| --- | --- | --- |
| Target reported by the OECD/EU (labelled "Reported, not law") | 6 weeks | `submission/evidence-v2.json` → `oecd-2025-fi-six-weeks.values.weeks` |
| Finnish law, treatment guarantee | up to 6 months | `submission/evidence-v2.json` → `stm-hoitotakuu.values.treatment_months` |
| Bar lengths | 6 of 26 weeks | drawn to scale: six months is about 26 weeks (stated in the on-screen source line) |
| Stage recorded, nationally | 42% | `submission/evidence-v2.json` → `syopajarjestot-2026-stage-completeness.values.national` |
| "aim: at least 70%" | 70% | same row, `.values.aim` |
| "Two dates and an end reason" | 2 | `submission/ZERO_EURO_2027.md` (action 3); clock definition in `data/flare/gate-v1.json` → `clock` |
| SYNTHETIC: 23 county sites, NVIDIA FLARE | 23; FLARE 2.9.1 | `data/flare/gate-v1.json` → `flare.sites`, `flare.nvflare` |
| Tiles 01-23 | order HVA01 ... HVA21, HVA90, HVA91 | `data/flare/gate-v1.json` → `counties[]` |
| "15 of 23 not comparable if the dates come from the model alone" (hatched tiles 01, 03, 04, 05, 07, 08, 09, 13, 14, 15, 16, 17, 21, 22, 23) | 15 of 23 | `data/flare/gate-v1.json` → `summary.raw.not_comparable`, `.of`, `.not_comparable_counties` |
| "1 of 23 not comparable when Gemma reads the note and code counts the days" (tile 04 = HVA04) | 1 of 23 | `data/flare/gate-v1.json` → `summary.resolver.not_comparable`, `.not_comparable_counties` |
| FLARE output equals the central table | 253 of 253 cells | `data/flare/gate-v1.json` → `flare.equivalence.cells`, `.cells_ok` |
| "thresholds are placeholders" | - | `data/flare/gate-v1.json` → `rule.label` |

## 1:12-1:35 Close the loop

| On screen | Value | File and key |
| --- | --- | --- |
| Law change in force | 1 June 2026 | `submission/evidence-v2.json` → `stm-2026-proactive-care-law.values.in_force` |
| Trial of GP chest X-rays | 93,326 | `submission/evidence-v2.json` → `lungimpact-2026.values.xrays` |
| Median wait for CT, both arms | 53 days | same row, `.median_days_ai`, `.median_days_usual` |
| SYNTHETIC worklist, Satakunta (pilot county) | HVA06 | `data/safetynet/safetynet-v1.json` → `pilotRegionId` |
| Replay date | 1 Dec 2025 | same file, `asOf` |
| Open loops / overdue | 120 / 16 | same file, `counties[regionId=HVA06].counts.open_loops`, `.counts.overdue` |
| Row 1: SYNTHETIC-SN-20261115-HVA06-0128, imaging follow-up, 154 days overdue, recommendation text | 154 | same county, `examples[0]` (`days_overdue`, `recommendation_copied`, `status`) |
| Row 2: SYNTHETIC-20261114-2025-HVA06-310, suspected-cancer referral, 118 days overdue, day 42 | 118; 42 | `examples[1]`; 42 days is the PLACEHOLDER in `thresholds[0].days` |
| Row 3: SYNTHETIC-SN-20261115-HVA06-0152, conditional recommendation, "Needs editing" | - | `examples[2]` |
| SYNTHETIC note (demo-04): written 2.3.2024; dates toukokuussa 2023, 29.6.2023, 25 viikkoa sitten, 18.11.2023 | - | `data/scribe/demo/demo-outputs.json` → `results.demo-04.note` (`note_date`, `note_text`) and `.highlights` |
| Proposed event, MDT decision, counted by code | 9.9.2023 (25 weeks before 2.3.2024) | same entry, `.resolved.events[type=MDT_DECISION].date`, `.date_resolution.changes[0]`; `.highlights[2].days_before_note` = 175 |
| Gemma's own date (struck through) | 8.10.2023 | same entry, `.model.parsed.events[2].date` |
| "Pre-filled for one-click confirmation"; Gemma and the stored Nemotron reading agree | - | same entry, `.review`, `.review_reason` ("both readers agree exactly"), `.second_reader` |
| "Gemma 3 270M ran offline on a CPU" | 270M; CPU | same entry, `.provenance.base_model.repo`, `.provenance.decoding.device` |
| Two readers (Gemma 3 1B and Nemotron) agreed: 684 of 700 SYNTHETIC test notes pre-filled, 4 of those wrong | 684, 700, 4 | `data/scribe/v4/eval/results-v1.json` → `cascade.chosen` (`gemma: C`, `signal: agreement`), `cascade.configurations[gemma=C, signal=agreement].test.prefilled_for_one_click_confirmation.k/n` and `.error_among_prefilled.k`; `systems.C` = Gemma 3 1B |

## 1:35-1:55 The plan and the ask

| On screen | Value | File and key |
| --- | --- | --- |
| County plans drafted by Nemotron 3.5 Super VL | 23 of 23 | `data/planner/plans-v1.json` → `summary.countiesRun`, `summary.counties`; `model` |
| Drafted sentences kept after the checks | 255 of 299 | same, `summary.keptSentences`, `summary.sentences` |
| Kept sentences with a number not found in a tool output | 0 | same, `summary.keptSentencesWithUnmatchedNumber` |
| Planner screenshot (Satakunta draft) | numbers inside the capture | `submission/shots/11-planner-nemotron-1440.png` (page section 07, reads `data/planner/plans-v1.json`) |
| Our ask: Satakunta, a 2027 worklist pilot; lung follow-up first; the county owns the list; a nurse confirms and calls | 2027 | `data/roadmap/mapping-v1.json` → `pilotCard.county`, `pilotCard.ask_en`, `pilotCard.choice` ("default, owner may change") |
| "No new money: the cost is staff time"; "No patient data leaves the county" | - | `submission/ZERO_EURO_2027.md` (lines 6 and 39) |

## 1:55-1:59 End card

No numbers besides "Junction 2026". Text: "Patient-like data shown are SYNTHETIC."

## Not from a JSON file

- Chapter numbers 01-05, the progress line and axis ticks are layout, not data.
- "Junction 2026" and the challenge name are event names.
- Citation years in source lines (OECD/EU 2025, Cancer Medicine 2026, Filha May 2026) come from
  the `citation` fields of the evidence rows named above.
- Count-up animations (17.9, 31.1, 42, 120, 16) pass through intermediate values for about one
  second before they settle on the sourced value; a paused frame mid-count is not a data value.
