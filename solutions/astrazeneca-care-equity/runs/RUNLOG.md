# Run log

Append-only. One line per major run on 14 November 2026 (UTC): what ran, where, its cost where a
file records one, and the result file. Machine-readable entries are in `runs/*.jsonl` (one JSON object
per line with `ts`, `step`, `host`, `command`, `inputs`, `outputs`, `metrics`, `cost_usd`, `status`).
Numbers here are copied from those entries or from the named result files; "not priced" means no
file records a price. The first six rows were written by the first integrator and are kept as they
were; their cost was not recorded in a JSON file.

Hosts: "MacBook Pro" is the local machine (it also calls the remote services); `az-equity-a100-20261114`
is the Verda A100 used for the version-2 scribe runs, the vLLM smoke test and Evo 2 (created 16:56,
deleted with its disk at 19:27; list price times wall time USD 5.98, not the invoice,
`data/scribe/v2/training-figures-v1.json` `machine_cost`).

| UTC | step | where | cost | result |
| --- | --- | --- | --- | --- |
| 14:25 | public data snapshot (57 requests) | MacBook Pro | not recorded | `data/snapshot/public-v1.json`, sha256 9a68651c… |
| 14:50 | forecaster, 5 seeds | Verda V100 spot | not recorded | transformer ties persistence; baselines chosen for 7 of 8 |
| 15:00 | claim-check evaluation, 650 calls | TypeSafe jev-1.14.0 | not recorded | 161/190 true passed, 460/460 corrupted stopped (`data/claim-check/eval-v1.json`) |
| 15:16 | open-weight summary writer (Qwen3-32B-AWQ, vLLM) | Verda A100 spot | not recorded | failed at start-up, machine reclaimed; nothing used |
| 15:24 | forecaster sweep, 14 configs x 3 seeds | Verda V100 spot | not recorded | no config beats best baseline beyond seed spread |
| 15:35 | Finnish summaries, 139 sentences | Claude Haiku + TypeSafe | not recorded | 91 shown, 48 dropped (`data/narratives/fi-v1.json`) |
| 15:48-18:54 | event-log design study, several runs (`runs/eventlog.jsonl`) | MacBook Pro | 0 | `data/eventlog/design-study-v1.json` |
| 15:50-16:06 | scribe version-1 notes: Nemotron teacher (4,500 requests) + TypeSafe verifier (7,194 requests) (`runs/scribe.jsonl`) | MacBook Pro → Verda endpoint, TypeSafe | TypeSafe USD 0.2876; Nemotron not priced | `data/scribe/dataset-stats.json` |
| 16:33, 17:02 | planned version-1 GPU training on `az-equity-gpu-20261114`: host unreachable (`runs/train.jsonl`) | Verda GPU | not priced | none: the planned run did not happen |
| 16:49 | Claude Haiku writes the version-1 test notes of a second writer (`runs/train.jsonl`) | MacBook Pro → Anthropic API | USD 0.070736 | `data/scribe/haiku-test.jsonl` |
| 16:59-17:11 | scribe version-1 laptop fallback, Gemma 3 1B LoRA on MLX (`runs/train.jsonl`) | MacBook Pro | 0 | `data/scribe/eval-v1.json` (history) |
| 17:00-18:17 | version-2 data: Haiku second writer and TypeSafe verification (`runs/v2-data.jsonl`) | MacBook Pro → Anthropic, TypeSafe | Haiku pilot USD 0.049846 reported (rest not recorded); TypeSafe USD 0.0593 | `data/scribe/v2/dataset/` |
| 17:11-17:27 | Evo 2 7B scoring of BRCA1, stopped at its time budget after 2,150 of 3,893 variants | `az-equity-a100-20261114` | within the A100 total | `data/genomics/brca1-evo2-v1.json` |
| 18:23-18:58 | version-2 ablation, 35-minute budget (34.6 min used) | `az-equity-a100-20261114` | within the A100 total | `data/scribe/v2/ablation-v1.json` |
| 18:31-19:10 | judge benchmark with planted errors (`runs/judges.jsonl`) | MacBook Pro → TypeSafe, OpenAI | TypeSafe USD 0.0689; OpenAI 1,038,484 tokens | `data/scribe/v3/judges/benchmark-v1.json` |
| 18:34-18:45 | teacher round 2, 1,600 specifications (`runs/teacher2.jsonl`) | MacBook Pro → Verda endpoint | Nemotron 4,042 requests, not priced | `data/scribe/v3/teacher/stats.json` |
| 18:50-18:58 | Jev gate on 1,589 round-2 notes (`runs/gate-v3.jsonl`) | MacBook Pro → TypeSafe | TypeSafe USD 0.1024 | `data/scribe/v3/gate/gate-v1.json` |
| 19:04 | vLLM smoke test, 100 notes, plain then structured outputs (log lines reconstructed in `runs/training-md.jsonl`) | `az-equity-a100-20261114` | within the A100 total | `serve/smoke/smoke-plain.json`, `serve/smoke/smoke-guided.json` |
| 19:04-19:12 | Haiku audit of 240 sampled round-2 notes (`runs/audit-v3.jsonl`) | MacBook Pro → Anthropic API | not priced (usage not recorded) | `data/scribe/v3/audit/audit-v1.json` |
| up to 19:27 | post-ablation students (1B, data arms), comparisons pre-registered at 19:08:08; 4B ran out of memory twice, third attempt stopped (`data/scribe/v3/student/RUNS.md`) | `az-equity-a100-20261114` | within the A100 total | `data/scribe/v3/student/compare-v1.json` |
| 19:13-19:41 | fix workflow: genomics reanalysis, event-log measured extraction, version-1 scribe regeneration (`runs/genomics-fix.jsonl`, `runs/eventlog-fix.jsonl`, `runs/scribe-v1-fix.jsonl`); done flag 19:58 | MacBook Pro | 0 | `data/genomics/brca1-evo2-v1.json`, `data/eventlog/design-study-v1.json`, `data/scribe/eval-v1.json` |
| 19:38-19:46 | cascade: Jev on 1,007 notes, Decisions on 186 (`runs/cascade-v3.jsonl`) | MacBook Pro → TypeSafe, OpenAI | TypeSafe USD 0.0574; OpenAI 245,314 tokens | `data/scribe/v3/cascade/cascade-v1.json`, `data/scribe/v3/summary-v1.json` |
| 18:58-20:24 | `TRAINING.md`, training figures and version-2 review fixes (`runs/training-md.jsonl`) | MacBook Pro | 0 | `TRAINING.md`, `data/scribe/v2/training-figures-v1.json` |
| 20:30-20:53 | product integration of the three tracks, build, 72 node tests, server check (`runs/integrate-tracks-v3.jsonl`) | MacBook Pro | 0 | `web/data/app.json` |
| 22:54-23:06 | ship wave, page: who/how/where panel, process headline, Satakunta pilot card, Nemotron planner and Gemma demo on the page, Evo 2 moved to `/research.html`; `npm test` 101/101 (`runs/ship-page.jsonl`) | MacBook Pro | 0 (local) | `web/data/app.json`, `web/research.html` |
| 22:55-23:08 | ship wave, safety net: rule `forward-v1` frozen, 60 SYNTHETIC report lines 60/60, second check on 5,002 lines (0 wrong or invented dates, 40 dated lines sent to a person), worklist join; Satakunta 120 open loops, 16 overdue (`runs/ship-safetynet.jsonl`) | MacBook Pro | 0 (local) | `data/safetynet/safetynet-v1.json` |
| 22:57-23:05 | ship wave, FLARE gate: NVIDIA FLARE 2.9.1 simulator, 23 SYNTHETIC county sites, 179.63 s; 253/253 cells equal the central table; not comparable 15/23 (raw scribe) and 1/23 (code resolver) (`runs/ship-flare.jsonl`) | MacBook Pro | 0 (local) | `data/flare/gate-v1.json` |
| 22:53-23:09 | ship wave, deck: submission drafts rewritten; `submission/check_numbers.py` 250 facts, 0 failures, 1 pending placeholder (`runs/ship-deck.jsonl`) | MacBook Pro | 0 (local; public pages re-opened) | `submission/` |
| 23:10-23:20 | ship wave, integration: safety net and gate bundled into `app.json` (`safetyNet`, `flareGate`) and mounted in section 05; `npm test` 113/113; own server on port 4185 checked with curl and the browser pane, then stopped (`runs/ship-integrate.jsonl`) | MacBook Pro | 0 (local) | `web/data/app.json` |

Runs of Lanes A, B and C between 20:53 and 22:50 UTC (MLX training, Nemotron reader and planner,
scribe demo) are logged in `runs/laneA-*.jsonl`, `runs/laneB-*.jsonl` and `runs/laneC-*.jsonl` and are
not summarised in this table.

Totals recorded in files: TypeSafe USD 0.5758 over the three scribe ledgers
(`data/scribe/v2/training-figures-v1.json` `api_spend`); OpenAI 1,283,798 tokens over 876 requests,
USD 0.1284 at the list rate (`data/scribe/v3/judges/usage-openai.json`, `data/scribe/v3/summary-v1.json`);
Haiku USD 0.070736 and USD 0.049846 recorded, the rest not recorded; Nemotron 8,542 requests, not
priced. No total project cost exists.
