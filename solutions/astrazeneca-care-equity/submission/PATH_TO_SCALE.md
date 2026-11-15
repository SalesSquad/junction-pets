# SAMA: path to scale

One slide, one table behind it. Every box is labelled **run** (executed in this project, with the
file that shows it) or **design, not deployed** (a plan, with the document it rests on). Hosted
endpoints receive SYNTHETIC text only. The design is that real patient notes stay inside a
county-controlled environment; this is designed so, and not built yet. A person confirms every extracted event and every worklist item. Thresholds are
placeholders.


## The slide

```
 INSIDE THE COUNTY (real records stay here)                                  NATIONAL
 -------------------------------------------------------------------------   --------------------------------
 [1] Finnish note ─> [2] Gemma 270M ─> [3] code counts ─> [5] person confirms   [7] THL person-level feed (TTP):
                        run: A100 vLLM,     the dates        (one click or          two dates + end reason,
                        laptop CPU           run              "needs editing")       residence, route
                        │                                     │                      design, not deployed
                        └─> [4] Nemotron second reader         v                          │
                            run on SYNTHETIC notes      [6] Pathway Clock in             v
                                                            county records       [8] quality register 3.2.1
 [9] overdue list (safety net): a nurse confirms and calls    design, not deployed     (stage, route)
     run on SYNTHETIC data / design                                │                    design, not deployed
                                                                   v
                                     [10] county statistics where the data live (NVIDIA FLARE)
                                          run in simulator; "can this county see itself?" gate
                                                                   │
 PLANNING (public aggregate data)                                  v
 [12] SAMA navigator, run locally  <──  [11] Nemotron county planner: 23 of 23 plans, numbers checked, run (cached)
```

## The boxes

| # | Box | Status | Evidence or design document |
| --- | --- | --- | --- |
| 1 | Finnish clinical note as input; other languages go to manual entry | design, not deployed (all notes so far are SYNTHETIC) | `data/roadmap/mapping-v1.json` (`pilotCard.languageScope_en`) |
| 2a | Gemma 3 270M + LoRA served by vLLM with structured outputs | run (A100, 100 SYNTHETIC notes: 100 of 100 valid JSON, p95 1.80 s, 5.74 notes a second) | `serve/smoke/smoke-guided.json`, `TRAINING.md` section 8 |
| 2b | Same adapter on a laptop CPU behind the product's `POST /api/scribe` | run (18 of 20 demo notes exact, median 4.8 s per note over HTTP) | `data/scribe/demo/http-timing.json` |
| 2c | Same adapter inside the hospital network, air-gapped, as NVIDIA Model-Free NIM with our LoRA | design, not deployed | [Model-Free NIM](https://docs.nvidia.com/nim/large-language-models/latest/deployment/model-free-nim.html), [LoRA in NIM](https://docs.nvidia.com/nim/large-language-models/latest/advanced-use-cases/finetune-lora.html), [air-gap deployment](https://docs.nvidia.com/nim/large-language-models/latest/deployment/air-gap-deployment.html) |
| 3 | Code date resolver, arm A' (Finnish lexicon), frozen and hashed | run (inside `serve/client.py`; reproduces 289/310 validation and 651/700 test exactly) | `data/scribe/v4/resolver/reproduce-v1.json`, `data/scribe/v4/resolver/freeze.json` |
| 4a | Nemotron 3.5 Super VL second reader on the hosted event endpoint | run on SYNTHETIC notes (690/700 test notes exact; the chosen pairing with Gemma 3 1B pre-filled 684/700 test notes with 4 wrong and 220/308 frozen stress notes with 3 wrong, `data/scribe/v4/eval/results-v1.json`; the earlier pairing with the 270M product adapter gave 651/700, 4 wrong; all offline and post hoc; the scribe demo applies the rule to its stored answers) | `data/scribe/nemotron/reader-v1.json`, `data/scribe/nemotron/cascade-agreement-v1.json` |
| 4b | Nemotron second reader self-hosted in a county-controlled or Finnish-hosted environment; otherwise the step is done by a person | design, not deployed | [NVFP4 model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4) |
| 5 | Person confirms every event: pre-filled for one-click confirmation, or "needs editing" | design, not deployed in any clinical system; shown in the demo | `data/roadmap/mapping-v1.json` (`pilotCard.humanReview_en`) |
| 6 | Pathway Clock fields in county records: two dates, end reason, residence, route; four optional events | design, not deployed (format and sample sizes run in simulation on SYNTHETIC people) | `submission/PATHWAY_CLOCK.md`, `data/eventlog/design-study-v1.json` |
| 7 | THL's person-level waiting-list feed (TTP) carries the clock; due by 2028 at the latest | design, not deployed: a national data flow SAMA proposes fields for | `submission/evidence-v2.json` (`thl-ttp-person-level`) |
| 8 | Cancer quality register at THL's Cancer Registry (roadmap 3.2.1) carries stage and route | design, not deployed: a national roadmap measure, not a SAMA component | `data/roadmap/mapping-v1.json` (measure 3.2.1) |
| 9 | Overdue-pathway list (safety net): code copies the written follow-up and computes the due date; a nurse confirms and calls | run on SYNTHETIC data (Satakunta replay: 16 overdue of 120 open loops; rule 60 of 60 SYNTHETIC lines); in a county: design, not deployed | `data/safetynet/safetynet-v1.json`, `submission/ZERO_EURO_2027.md` |
| 10a | County statistics computed where the data live, NVIDIA FLARE federated statistics, small cells suppressed | run in simulator on one laptop, 23 sites, SYNTHETIC: 92 of 92 cells equal the central table | `data/flare/summary.json`, `data/flare/RESULT.md` |
| 10b | "Can this county see itself?" gate and a referral-to-treatment edge at the 42-day placeholder | run in simulator on SYNTHETIC data: 15 of 23 county figures "not comparable" with the scribe as is, 1 of 23 with the code resolver; 253 of 253 FLARE cells equal the central computation | `data/flare/gate-v1.json`, `submission/PATHWAY_CLOCK.md` |
| 10c | Legal route for county-local statistics (Findata, the Secondary Use Act) | design, not deployed: one possible route, to be confirmed with THL and Findata | none in this repository |
| 11 | Nemotron county planner: three actions per area, each with owner, indicator and roadmap measure; every number checked against SAMA's tools | run on public aggregate data (23 of 23 plans; cached for the demo) | `data/planner/plans-v1.json` |
| 12 | SAMA navigator on public aggregate data (analysis, actions, optimiser, claim check) | run, locally only; no hosted deployment | `README.md` ("Run it") |
| 13 | Production licence for NIM (NVIDIA AI Enterprise) | design, not deployed | [NIM FAQ](https://forums.developer.nvidia.com/t/nvidia-nim-faq/300317) |

## What scales, and what has to be true first

- **Compute is not the bottleneck.** The scribe is a 270M-parameter model; on an A100 it served
  5.74 notes a second, and the event-log design study ran on the team's laptop CPU (its
  50,000,000-episode calibration step took 13.5 s, `runs/eventlog-fix.jsonl`).
- **The data is.** A county needs 473 / 513 / 347 complete episodes (primary care / diagnostic /
  treatment interval) to see a 20% slowdown at 80% power (SYNTHETIC simulation). At an assumed 37,000
  cases a year, 5 of 23 counties reach that within a quarter and 20 of 23 within a year.
- **Equal errors everywhere.** A county read from text while others use structured fields is flagged
  in 1.000 of simulated runs with no real slowdown, and 0.003 with the code resolver
  (`data/eventlog/design-study-v1.json`). Scaling to new counties means checking error rates per
  county and per writing style, and comparing only areas that can see themselves.
- **First real step:** Satakunta, every overdue suspected-cancer referral, lung follow-up first, a
  2027 pilot with no new capital cost (`submission/ZERO_EURO_2027.md`).
