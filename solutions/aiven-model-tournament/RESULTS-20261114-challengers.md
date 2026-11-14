# Aiven companion — five challengers, two judges, repair loop — 14 November 2026

30 unread cases written by five challenger companions (6 each: MariaDB, Valio Aimo, Espoo, S-Pankki, AstraZeneca) from their own project needs: `cases-*.json`. 2 repeats. Judges: opus and sonnet. Runner `challenge.mjs` and lint at `4bf948a`. 2026-11-14T19:07Z – 19:21Z, 0 errors. Unqualified developer measurement through the Claude CLI; not the Aiven AI gateway, not a Chibi host run.

| Model / arm | Consensus pass (both judges) [95 % CI] | opus pass | sonnet pass | Mean score (opus) [95 % CI] | Proposal when expected | Cost (USD) |
|---|---|---|---|---|---|---|
| haiku / all modules | 57 % [44–68] | 72 % | 65 % | 0.911 [0.865–0.950] | 57/60 | 3.20 |
| **haiku / all modules + lint repair** | **62 % [49–73]** | 72 % | 75 % | 0.917 [0.867–0.958] | **60/60** | 3.41 |
| sonnet / routed modules | 64 % [51–75] | 78 % | 67 % | 0.929 [0.875–0.975] | 59/60 | 5.86 |

Every arm: schema-valid 60/60, no execution 60/60, no secret echo 60/60.

## Findings

- **The repair loop does what it is built for.** It repaired 16 of 60 answers and cut lint issues per answer from 0.48 to 0.10. Proposal discipline reached 60/60, for about 6 % extra cost.
- **The quality gain from repair is small and not statistically significant** (consensus pass +5 pp with overlapping intervals). Lint fixes the hard rules; the remaining failures are content (domain specifics), which lint cannot see.
- **Haiku with repair is on par with Sonnet routed** (62 % vs 64 %, overlapping intervals) at 58 % of the cost. Best value: Haiku + all modules + repair.
- **The judges agree on 77–83 % of answers.** About one answer in five depends on the judge, so rubric ambiguity is the main noise source, not the model.
- **Per challenger (haiku + repair):** Valio Aimo 83 %, S-Pankki 67 % (up from 42 % without repair), Espoo 58 %, AstraZeneca 50 %, MariaDB 50 %. Health and domain-heavy cases remain hardest.
- **The intervals are still about ±12 pp with 60 answers per arm.** Separating changes of 5 pp needs several hundred answers per arm.
