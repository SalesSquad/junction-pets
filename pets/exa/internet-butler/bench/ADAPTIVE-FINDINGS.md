# Adaptive red teaming of the truth table: findings (2026-11-14)

The raw output is in `bench/ADAPTIVE-EVAL.md`, which `bench/adaptive_eval.mjs` regenerates. This page records the judgments and the decisions that came out of three rounds.

## Protocol

| Round | Attacker | Size | Role |
|---|---|---|---|
| 1 | Haiku, not adaptive (7 fixed variant types per rule) | 174 forgeries + 30 true | baseline, calibration |
| 2 | Haiku, told the exact 4-row defence | 87 forgeries + 30 hard-but-true | development: the veto rows were designed from its failures |
| 3 | Haiku, told the exact 6-row defence and which attacks rows 5–6 catch | 89 forgeries + 31 hard-but-true (after adjudication) | held out |

How the runs were done:
- **Calls:** one state per passage; every judge call is recorded in `bench/cassettes/adaptive.jsonl.gz`. Re-runs replay offline: 882 replayed calls, 0 live, identical numbers.
- **Statistics:**
  - cluster bootstrap by rule, since the 3–7 passages from one rule are correlated;
  - Learn-then-Test thresholds (α = 5 % false accepts, δ = 10 %);
  - excess AURC over a perfect ranking;
  - exact McNemar test for Jev vs Luna.
- **Adjudication:** every accepted forgery in round 3 was checked by hand. 1 of 9 was a label error (fi-notice: the "only if" passage is correct law) and was relabelled as true. 1 is borderline (us-dot-refund: right content, wrong instrument name), and it is kept as a forgery.

## Results: share of forgeries accepted / share of true passages accepted

| Defence | Round 1 | Round 2 (adaptive) | Round 3 (adaptive, held out) |
|---|---|---|---|
| 4 rows, Jev | 1 % / 100 % | **47 %** / 97 % | — |
| 4 rows, Luna | 1 % / 100 % | **23 %** / 100 % | — |
| 6 rows, Jev | 0 % / 97 % | 3 % / 90 % | **9 %** / 97 % |
| 6 rows, Luna | 1 % / 67 % | 1 % / 63 % | **4–6 %** / 65 % |
| 6 rows, both must accept | — | 0 % / 60 % | **2 %** (2/89) / 63 % |
| 6 rows + code instrument veto, Luna | 1 % / 67 % | 1 % / 63 % | 4 % / 65 % |

## What we learned

1. **Non-adaptive red teaming overstates robustness.** 204/204 in round 1 became 47 % false accepts the moment the attacker knew the defence. Report adaptive numbers, or none.
2. **The blind spot was additions.** The passage states the rule correctly, then adds a false condition, exception, waiver, start point or effective date. Two veto rows (`contradicts`, `adds_terms`) cut this from 47 % to 9 % on held-out attacks, at the cost of 0–7 points of true-passage acceptance.
3. **A calibration guarantee holds only for the distribution it was calibrated on.** A Learn-then-Test threshold calibrated on naive forgeries let 28–37 % through in round 3. Calibrated on the previous adaptive round it gave 9 % (target 5 %). Re-calibrate on each newest adaptive round, and state the exchangeability assumption next to every guarantee.
4. **The two judges have different operating points.** Jev accepts 97 % of true passages and lets through 9 % of adaptive forgeries. Luna is stricter: 4–6 % false accepts, but only 65 % of true passages. Requiring both gives 2 % false accepts at 63 % true. In round 3 the difference in correctness is not significant (McNemar p = 0.38). In round 2, against the 4-row table, Luna was significantly better (p < 0.001).
5. **What still gets through is scope words and names.** "any tenancy", "including digital content", "only deadline", a misnamed rule or instrument. Identifiers go to code (`instrumentMismatch`), which caught Luna's misdated Act with no false vetoes. Scope words need a dedicated row or a quote from the legal text itself.
6. **Real-data cost.** On real Exa evidence the stricter table keeps 0 wrong answers. Coverage falls, though: Jev answers 15 of 18 errands with the subagent drafts and 13 of 18 with the API drafts. Escalations go to the full compiler (authority lane, tiers, clarifying question), which is the safe direction.

## Policy this supports

- Warrant evidence stays **legal-text-only**. Judges veto and select; they never ground.
- Fast path (`verifyClaim`): Jev's six rows plus the code vetoes. On failure, escalate; never auto-correct.
- High-stakes accept (sending a claim to an institution): require Jev and Luna to agree, record both as judgment receipts, and let the receiver replay them.
- Every new defence change gets a fresh adaptive round as its test, with the previous round as calibration.

## Round 4 (2026-11-14, same day)

**Protocol.**
- Round 3 became the development set.
- Two rows were designed from it: `same_source` (agreement) and `scope_change` (veto).
- A fresh round 4 was generated against the nine-row table (`bench/adversarial/adaptive4_*.json`). The attacker was told all rows, the code veto, and every strategy caught so far.
- Every accepted forgery in rounds 3–4 was adjudicated in `bench/adversarial/adjudication.json`: correct law (attacker label error), material, or minor. 6 "forgeries" turned out to be correct law and were relabelled. 0 accepted forgeries are left unadjudicated.

**Held-out result, round 4 (nine rows, adjudicated):**

| Defence | Forgeries accepted | Material | True passages accepted |
|---|---|---|---|
| Jev | 8/85 = 9 % (CI 4–16 %) | 3 | 33/35 |
| Luna | 7/85 = 8 % | 4 | 24/35 |
| Both must accept | 5/85 | 2 | 22/35 |

Learn-then-Test calibrated on round 3 put Jev's threshold at 0.66. At that threshold, round 4 let through 9 % of forgeries and accepted 93 % of true passages; the target was 5 %, so the miss is smaller than in earlier rounds.

**New blind spot: legal force.** Duties restated as advice or permission got through: "should", "is recommended", "are advised", "the BGB recommends". So did rights turned into duties. A tenth row, `same_force`, was designed from round 4. As a development result on round 4 it gives:
- Jev: 3/85 forgeries accepted, true accepted 32/35;
- Luna: 2/85, 24/35;
- both must accept: 1/85.

Its held-out effect needs a round 5.

**Arms race so far (forgeries accepted on the newest held-out round):**

| Round | Defence | Jev | Luna |
|---|---|---|---|
| 1, naive | 4 rows | 1 % | 1 % |
| 2, adaptive | 4 rows | 47 % | 23 % |
| 3, adaptive | 6 rows | 9 % | 4–6 % |
| 4, adaptive | 9 rows | 9 % (3 material) | 8 % (4 material) |
| 4, development | 10 rows | 4 % | 2 % |

Jev accepts 91–97 % of true passages throughout; Luna 60–69 %.

**Real-data cost (Exa evidence, verify or escalate).** Still 0 wrong answers.
- Jev answers 14/18 (subagent drafts) and 12/18 (API drafts).
- Luna answers 16/18 and 15/18.
- The escalations go to the full compiler.

**Reading of the trend.** Each new row closes the class it was designed for, and the attacker then finds the next class:
- additions → scope and source → legal force.
- The share of forgeries accepted on held-out rounds has settled at about 8–9 %, of which roughly a third to a half are material.

A judge-only defence against a white-box attacker therefore converges slowly. The durable defence is structural: GROUNDED needs a verbatim quote from an allowlisted legal text, which an attacker cannot publish. The judges' job is to keep misleading explainer pages out of the fast path, and to escalate.
