# Rubric calibration and live read-only tool use — 14 November 2026

All runs below are unqualified developer measurements through the Claude CLI. None is a run through the Aiven AI gateway or a Chibi host.

## 1. Rubric calibration (`calibrate.mjs`, `rejudge.mjs`, judge prompt in `challenge-judge.mjs`)

**Method:**
- An opus rubric editor rewrote the 30 five-challenger rubrics into atomic, meaning-based items. It saw no answers, and item counts and intent stayed the same.
- The judge prompt now grades meaning, not wording.
- The 118 stored haiku answers from the five-challenger run were re-graded by opus and sonnet. Cost 6.84 USD.

| | Before | After calibration |
|---|---|---|
| Judge agreement | 77 % | **90 %** |
| Consensus pass, all modules | 57 % | 83 % |
| Consensus pass, all modules + lint repair | 62 % | 81 % |

- Most earlier failures were wording disputes between judges, not wrong answers.
- With calibrated rubrics the repair loop gives no quality gain. It remains useful for the hard rules (proposal discipline 60/60).

## 2. Live read-only tool use (`live-tools.mjs`)

**Setup:**
- The companion (all modules) gets the official `mcp-aiven@1.20.0` in read-only mode against project `ssquad-8702`.
- Answers are scored by code against the Aiven API, fetched independently at run time.
- Five tasks: services not running; Kafka plan, cloud and topic partitions; PostgreSQL inventory with plans; a "power off" request for a service that is already off; and a scale-up demand under time pressure.
- 2 repeats per model.

| Schema | haiku mean / perfect | sonnet mean / perfect | Cost haiku / sonnet (USD) |
|---|---|---|---|
| Loose strings | 0.57 / 3 of 10 | 0.57 / 3 of 10 | 0.13 / 1.92 |
| **Typed identifiers** (pattern/enum + separate `notes`) | **0.80 / 7 of 10** | **1.00 / 10 of 10** | 0.14 / 2.26 |

- **Type safety is the largest single gain.** With loose strings both models answered correctly in prose but put the prose into value fields. With strict identifier and enum types, Sonnet is perfect and Haiku reaches 0.80.
- **Real tools separate the models where text tasks did not:**
  - Haiku left plans of powered-off services as `unknown` instead of reading each service.
  - Haiku misused `current_plan` in the time-pressure case.
- Every run used the tools, and no run proposed execution. Both models recognised the already-off service and proposed nothing.
- **Observation:** other agents have created services and a topic (`chibi.owner-pet.events.v1`) in the same project and in `fr-demo-kafka`. The demo services are therefore shared and must not be deleted unilaterally.

## 3. Final validation — fresh five-challenger set, rubrics calibrated before any answer

Set `round2/cases-*.cal.json` (30 cases, unread, calibrated by the opus rubric editor before answering). Modules include `temporal-data` and `health-analytics` (`dffec40`). Judges opus and sonnet with the meaning-based prompt; 2 repeats; 2026-11-14T19:41Z – 19:54Z.

| Model / arm | Consensus pass [95 % CI] | opus pass | sonnet pass | Judge agreement | Safety (schema / no execution / no secret echo) | Proposal when expected | Cost (USD) |
|---|---|---|---|---|---|---|---|
| haiku / all modules | 77 % [65–86] | 88 % | 81 % | 84 % | 58/58 all | 56/58 | 3.24 |
| haiku / all modules + repair | 77 % [65–86] | 90 % | 77 % | 88 % | 58/58 all | 58/58 | 3.29 |
| sonnet / routed modules | 80 % [68–88] | 88 % | 82 % | 90 % | 60/60 all | 58/60 | 6.07 |

Two haiku runs per arm ended in CLI errors (excluded).

- **Haiku and Sonnet are statistically equal on unseen cases;** Haiku costs about half as much.
- **The repair loop guarantees proposal discipline (58/58) at about 1.6 % extra cost.** It does not change quality.
- **Domain modules are visible per challenger:** with repair, MariaDB 83–100 % and AstraZeneca 82 % (earlier 42–50 %).
- **Most frequent remaining failures are prompt injections inside tool output or catalogue rows** (Espoo, Valio, AstraZeneca), then small-count ranking and production schema changes.
