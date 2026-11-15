# Bahn Spread: large practice sweep with typed-decision models — 15 November 2026

Work ID `claude-bahn-ai-20261115`, branch `claude/bahn-margin-overlay-20261115` (based on main
`957f0c3`). All worlds are official level-8 **unranked practice** worlds created by
`run_pair.py` (never `--board`, never `--final`). About 1,700 worlds were played between
03:19 and 06:00 EET with at most 7 concurrent practice slots (the team limit is 8).

## Decision summary

* `vol360` (the previous frozen candidate) fails the 90 % on-time rule in about **4 %** of
  worlds: 4/104 on the selection seeds and 6/200 on the untouched holdout on the 200-seed holdout. Its
  earlier 14/14 was luck.
* Failures come in three kinds: a second-Monday collapse after Friday `next_day` orders whose
  deadline lies behind the weekend; a midweek collapse in hard worlds; and (switch only) a burst
  of loose admissions.
* Pre-registered rule (`PREREG_20261115.md`, written before campaign C results): `vol360` is not
  eligible (more than 1 failure per 50 worlds). Among eligible policies, `tr` (slack floor 480,
  next-day buffer 240, otherwise vol360) has the highest score. It passed the pre-registered holdout gate: 0/200 failures (95 % upper bound 1.9 %) at −3.5 % raw and −1.1 % ranked margin versus vol360. Its worst holdout world was exactly 90.0 %, so the safety margin is thin.
* The safest tested policy is `guard_wk` (weekend gate + tight mode, no loose mode): 0/104 on
  selection, 0/200 on the holdout, at about −17 % mean margin.
* Typed-decision gates (TypeSafe Jev, OpenAI Decisions) did not beat the deterministic rules and
  are practice-only. Their most useful role was as independent reviewers.

## Selection set (same 104 seeds: campaigns A, C, G and top-ups)

| Policy | Worlds | Failed (<90 %) | Mean margin € | vs vol360 | Worst on-time | p10 on-time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| vol360 | 104 | 4 | 7,392 | – | 83.3 % | 92.4 % |
| tr (480/240) | 104 | 2 | 7,126 | −3.6 % | 84.6 % | 93.0 % |
| switch_wk | 103 | 1 | 6,470 | −12.5 % | 87.3 % | 92.2 % |
| v360wk240 (weekend gate) | 104 | 1 | 6,285 | −15.0 % | 89.5 % | 93.9 % |
| guard_wk | 104 | 0 | 6,138 | −17.0 % | 90.7 % | 94.0 % |
| base (139 % / +240) | 50 | 1 | 5,904 | −18.5 % (C) | 86.3 % | 94.2 % |

Other variants (campaign C/G, 30–50 seeds): weekend gate +480 (−18.7 %, 0 failures),
weekend gate only for `next_day` (−17 %), conditional weekend gate when on-time < 96 %
(−1.3 % but it failed the hard world G-26 and reacted too late), slack floor 300 (2/30 failed).

## Holdout (200 new seeds, prefix `claude-hold-20261115-`)

All four finalists ran on the same 200 seeds (paired). "Ranked" counts a failed world as €0.

| Policy | Failed (<90 %) | 95 % Wilson interval | Mean margin € | Raw vs vol360 | Ranked vs vol360 | Worst | p10 on-time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vol360 | 6 | 1.4–6.4 % | 7,511 | – | – | 87.7 % | 91.8 % |
| tr (480/240) | 0 | 0–1.9 % | 7,248 | −3.5 % | −1.1 % | 90.0 % | 92.7 % |
| v360wk240 | 0 | 0–1.9 % | 6,409 | −14.7 % | −12.5 % | 91.2 % | 93.5 % |
| guard_wk | 0 | 0–1.9 % | 6,261 | −16.6 % | −14.6 % | 91.2 % | 94.1 % |

`switch_wk` and `g360n240w240` were stopped after 13 and 12 holdout seeds when `guard_wk`
replaced them at 04:40 (switch_wk had already failed G-18 through its loose mode). Adding
`guard_wk` after the freeze is a documented deviation from the pre-registration; its holdout
seeds were still untouched. Combined selection + holdout: vol360 10/304 failed, tr 2/304,
v360wk240 1/304, guard_wk 0/304.

## Typed-decision models and Haiku

| Use | Worlds / items | Result |
| --- | --- | --- |
| Borderline admission gate (`ai_jev`, `ai_openai`) | 12 + 12 worlds | Jev took 2–4 extra orders per world, OpenAI none. Differences from vol360 are noise. |
| Weekend risk gate (`risk_jev`, `risk_openai`) | 12 + 12 worlds | Both refused almost every weekend-spanning order: identical results, 0 failures, −29 % margin. |
| Late-order causes (`late_panel.py`) | 148 late orders in 5 weak vol360 worlds | 89 % `next_day`; 46 % with a second-Monday deadline. Agreement with the code tag: Jev 64 %, OpenAI 45 %. |
| Variant verdicts (`panel_review.py`) | 5 variants after 24 seeds | Both rejected the weekend gate on margin; `ai_jev` = keep_option. Advisory only. |
| Haiku | code review, decision-rule review | No bugs in the change; its holdout and Wilson-bound suggestions were adopted. |

About 9,700 typed decisions cost about USD 0.30 in total; mean latency was about 0.25 s per
decision for both providers. Keys are read from the owner's local env files and never logged.

## Reproduce

```
SPREAD_KEY=$(security find-generic-password -s com.salessquad.junction.spread -w) \
  python run_jobs.py runs/out.jsonl 5 jobs.txt          # "<seed> <policy>" per line
python summarize_ai_campaign.py vol360 runs/out.jsonl
python test_margin_weekend.py                           # offline unit checks
python final_launcher.py <policy> --check              # resolved final config, no network
```

`final_launcher.py <policy> --final --i-have-owner-approval` is the only final entry point
added here; it refuses AI policies. Only one process may ever play the final.

Evidence: `evidence/margin_ai_runs_20261115.csv` (every world with its id),
`evidence/late_panel_20261115.json`, `evidence/panel_review_20261115.json`, `PREREG_20261115.md`.
