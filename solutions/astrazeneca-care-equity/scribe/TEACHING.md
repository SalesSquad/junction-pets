# How a large teacher, two judges and independent auditors teach a small Gemma model

All text in this project is SYNTHETIC. Language models wrote every note from sampled answer keys. The labels are
model-written too. Nothing here has been validated clinically and nothing is for clinical use.

Every number below is copied from a JSON file. The source is given in brackets. `data/scribe/v3/summary-v1.json`
(written by `scribe/v3/summarise.py`) holds the same numbers in one flat file.

## 1. The loop

```
 answer key (code samples route + dated events)
        |
        v
 [TEACHER: Nemotron 3.5 Super VL on Verda] --writes--> Finnish note
        |                                                  |
        |   code check (dates present, nothing extra)      |
        |   blind read-back (teacher reads note, no key)   |
        |   one repair if either fails                     |
        v                                                  v
 [JUDGE 1: TypeSafe Jev]   [JUDGE 2: OpenAI Decisions]   (gate: Jev only)
        |                         (measured, not in the rule)
        v
 accepted notes --> train.parquet --> [STUDENT: Gemma 3 LoRA "pathway scribe"]
        |
        +--> sample --> [AUDITORS: Claude Haiku, saw the claims] --> label-error shares
        |
        +--> at inference: student answer + Jev/Decisions check --> keep, or send to a person  (cascade: NOT measured)
```

Why different model families: a model reads its own writing too kindly. The teacher writes. A second family
(Jev, a small TypeSafe model) judges. A third (OpenAI Decisions) judges again. A fourth (Haiku) audits. The
student is a Gemma model. Code does all date arithmetic, because no model did it reliably.

## 2. Round 2 teaching protocol

Write, code check, blind read-back, one repair. 1,600 specifications in five curricula, all completed
[data/scribe/v3/teacher/stats.json `specifications`]. The teacher used 4,042 of a cap of 5,500 requests
[data/scribe/v3/teacher/ledger.json]. Wall time was 325.9 s [stats.json `wall_seconds.total`].

| step | first attempt | kept note |
|---|---|---|
| code check passed | 1486/1600 (0.9287) | 1589/1600 (0.9931) |
| read-back equals the key | 1311/1486 (0.8822) | 1465/1589 (0.922) |
| both | 1311/1600 (0.8194) | 1465/1600 (0.9156) |

[stats.json `overall`.] A repair was tried for 289 notes and worked for 154 (0.5329).
Hardest curriculum: no_event, clean after repair 170/238 (0.7143), mostly because the reader finds an extra event
[stats.json `per_curriculum.no_event`].

Honest deviations: 172 specifications used four calls, not three. 90 long notes were regenerated because the teacher
told the visits in time order. 77 requests of one aborted pilot were lost unrecorded. The word limits differ by
curriculum (long 110-260, terse 25-90). Round 1 is not a like-for-like comparison.

## 3. Judge benchmark with planted errors

Code plants one error in a note's claimed answer: a shifted date, a swapped type, a removed or added event, a swapped
route. The note stays. A good judge fails the corrupted pair and passes the clean pair. 300 notes, 600 pairs, six kinds
[data/scribe/v3/judges/benchmark-v1.json `design`]. Thresholds were fixed on a calibration half; numbers below are the report half.

Pairs both judges answered (80 corrupted, 80 clean) [benchmark-v1.json `report.rules`]:

| rule | corrupted caught | clean rejected |
|---|---|---|
| Jev alone (v1 questions) | 60/80 | 1/80 |
| Decisions alone | 58/80 | 11/80 |
| both must pass | 65/80 | 12/80 |
| either passes | 53/80 | 0/80 |
| Jev with day offsets (v2) | 66/80 | 0/80 |

On all 300 report pairs, Jev v1 caught 110/150 and rejected 8/150 clean. Jev v2 caught 126/150 and rejected 2/150
[`report.jev_alone_all_report_pairs`, `report.jev_hint_alone_all_report_pairs`].

Do the judges make the same mistakes? Mostly yes on corrupted pairs. Cohen's kappa is 0.690 overall, 0.613 on
corrupted pairs and -0.023 on clean pairs. 15 of 80 corrupted pairs were missed by both [`report.agreement`]. Both
miss swapped types and removed events: Jev v2 caught 14/25 and 15/25 [`caught_by_kind`]. Decisions caught 1/14 removals.
Neither judge does date arithmetic well; Jev answered below 0.5 on 28/50 "weeks ago" facts until code added the day
offset (v2 cut that to 1/50) [`diagnostics_calibration_half`].

Two caveats that change how to read this:

- The v2 question set was designed after seeing the v1 results of both halves. Only the v1 row is an untouched estimate.
- The clean pairs came from notes the version-2 Jev gate had already accepted. The clean-rejected shares are therefore
  biased low. Do not read them as a property of the round-2 data.

Decisions was run on only 320 of 600 pairs because of its 500,000-token allowance, and never with the v2 questions.

## 4. Label noise

`noise_after = e(1-c) / (e(1-c) + (1-e)(1-f))` with c = share of errors caught and f = share of clean notes rejected
(DATA_COLLECTION.md section 4). For Jev v2 on 300 pairs, noise goes from 0.05, 0.10, 0.20 to 0.0085, 0.0177, 0.0390
[benchmark-v1.json `report.jev_hint_alone_all_report_pairs.noise_after`]. This is a planted-error result with a biased f.
It is not the noise of the round-2 data. The audit below is the measurement of that.

## 5. Gate and audit

The gate is Jev v2 alone: every event at least 0.3, unlisted event below 0.6, route equal to the claim. It accepted
1,506 of 1,589 notes that passed the code check (0.9478) [data/scribe/v3/gate/gate-v1.json `overall.rule`]. The gate
barely overlaps the read-back flag: of 124 read-back-inconsistent notes it rejected 13
[`overall.readback_vs_rule`]. It was never calibrated for no_event, terse or long notes and accepted 236 of 238 no_event notes.

Dataset v3 train has 3,860 rows: 2,354 from version 2, then 1,506 round-2 notes. The held-out files are the version-2
files byte for byte [data/scribe/v3/dataset/dataset-stats.json].

Audit: Claude Haiku read 240 notes with the claimed labels visible (160 accepted, 80 rejected). It is a language model,
not a human. 0 of 1,153 verdicts were discarded for a quote missing from the note [data/scribe/v3/audit/audit-v1.json].

| group | wrong label | wrong label or route not supported | strict clean |
|---|---|---|---|
| accepted (160 of 1,506) | 2/160 (0.0125) | 6/160 (0.0375) | 153/160 (0.9563) |
| rejected by the rule (80 of 83) | 2/80 (0.025) | 8/80 (0.10) | 68/80 (0.85) |

The intervals overlap [`by_status`]. This sample does not show that the gate removes wrong labels, and it rejected
mostly good notes (strict clean 68/80). Do not quote the pooled row; the two groups were sampled at different rates.

## 6. What round 2 did to the student

The comparison was pre-registered before any of these runs had a result [data/scribe/v3/student/preregistration.json].
The reference is the frozen version-2 selection (Gemma 3 270M, LoRA r16, 1,716 Nemotron round-1 notes). Every run used
the same 324 optimisation steps [each run's result.json `train.global_step`], so a run with more training rows made fewer
passes over each note. Read the data arms with that in mind. Note-level exact match on the held-out files
[data/scribe/v3/student/compare-v1.json, written by scribe/v3/compare_students.py; training rows from result.json
`data.train_tokens.examples`]:

| run | training rows | Nemotron-written (500) | Haiku-written (200) | pooled (700) | pooled exact McNemar p vs reference |
|---|---|---|---|---|---|
| reference A-270m-lora-r16 | 1,716 | 210 (0.42) | 26 (0.13) | 236 (0.3371) | |
| V3-270m-nemotron, primary: + round-2 notes the Jev gate accepted | 3,222 | 209 (0.418) | 58 (0.29) | 267 (0.3814) | 0.00054 (Holm 0.00054) |
| V3-270m-all: + round-2 notes + version-2 Haiku notes | 3,860 | 197 (0.394) | 80 (0.40) | 277 (0.3957) | 9.8e-06 (Holm 2.0e-05) |
| C-270m-all-v2data: version-2 data + version-2 Haiku notes | 2,354 | 210 (0.42) | 95 (0.475) | 305 (0.4357) | 2.9e-16 (Holm 8.7e-16) |
| S-1b-lora-r16: Gemma 3 1B, post hoc size ladder | 1,716 | 216 (0.432) | 54 (0.27) | 270 (0.3857) | 8.2e-06 (outside the Holm family) |

- The round-2 notes changed nothing on Nemotron-written notes (209 vs 210, p = 1.0) and helped on Haiku-written notes
  (58 vs 26, p = 4.2e-05). On the 33 Haiku-written no_event notes the primary went from 0 to 21 correct [`by_kind.no_event`].
- The largest pooled gain came from adding the version-2 Haiku training notes (C-270m-all-v2data), all of it on
  Haiku-written test notes (95 vs 26; Nemotron-written 210 vs 210). Those test notes have the same writer as the added notes.
- With both additions (V3-270m-all) the student lost on Nemotron-written notes (197 vs 210, p = 0.0072). It also had the most
  rows for the same 324 steps; whether that or the data mix caused the loss was not tested.
- The 1B run was evaluated on test because it beat the reference on validation (the pre-registered rule); it is post hoc.
- There is no 4B number: it ran out of GPU memory twice and a third attempt was stopped by the coordinator to protect the
  pre-registered runs [data/scribe/v3/student/S-4b-lora-r16/*.log].
- The held-out files could not show the new curricula anyway: all their notes have 60 to 135 words, while round-2 terse
  notes have 25 to 49 and long notes 110 to 260. A held-out set for those is still needed.

## 7. Cascade at inference

The student proposes events and a person confirms them. A note may skip the person only if the error among skipped notes
stays at a target. The student is V3-270m-nemotron, chosen on validation exact match only: C-270m-all-v2data was highest
(134/310), but it and the pre-registered primary (124/310) lie within each other's Wilson intervals, and the rule then
prefers the primary [data/scribe/v3/cascade/cascade-v1.json `student`]. Jev re-read the 1,007 notes whose answer parsed
(3 did not parse and always go to a person). Decisions re-read 93 validation and 93 test notes chosen by a hash of the id.
Judge score = the lowest event probability x (1 - the unlisted-event probability), and 0 when the judge picks another
route. Thresholds were set on the 310 validation notes only (asserted in code) and applied to the 700 test notes. They are
empirical, not guarantees.

| target, signal | pre-filled for one-click confirmation (700 test notes) | error among pre-filled | of them on Haiku-written notes |
|---|---|---|---|
| 5%, student confidence | 270 (0.3857) | 28/270 (0.1037) | 21/61 wrong |
| 5%, Jev score | 263 (0.3757) | 7/263 (0.0266) | 3/55 wrong |
| 5%, student + Jev (logistic) | 276 (0.3943) | 12/276 (0.0435) | 8/65 wrong |
| 10%, student confidence | 287 (0.41) | 36/287 (0.1254) | 28/73 wrong |
| 10%, Jev score | 309 (0.4414) | 43/309 (0.1392) | 30/87 wrong |
| 10%, student + Jev (logistic) | 315 (0.45) | 48/315 (0.1524) | 34/92 wrong |

[cascade-v1.json `test.all_notes`.]

- More notes pre-filled for one-click confirmation? At 5%, no: the differences are within noise (Jev -1.0 points, paired bootstrap -3.1 to +1.1).
  At 10%, Jev adds 3.1 points and student + Jev 4.0. That is outside test-sampling noise but within noise once the
  thresholds are re-chosen on resampled validation notes (-2.4 to +6.7 and -0.9 to +6.0 points) [`pipeline_bootstrap`].
- What the judge changed is the error. The student's own 5% threshold gave 0.1037 on test and 21/61 wrong on Haiku-written
  notes; with Jev it was 0.0266. That reduction is outside test-sampling noise (-11.0 to -4.5 points) but within noise once
  the thresholds are re-chosen (-10.8 to +1.5). At 10% every signal's test error was above the target.
- Ranking over all coverages (area under the risk-coverage curve, lower is better): student 0.2689, Jev 0.2545, student +
  Jev 0.2529, best possible 0.2514. Jev minus student is -0.0144 (paired bootstrap -0.0210 to -0.0083).
- Decisions let fewer notes be pre-filled for one-click confirmation than the student on its subset (5%: 23/93 vs 41/93), and adding it to student +
  Jev did not add coverage (5%: 33/93 vs 41/93; 10%: 43/93 vs 44/93) [`test.decisions_subset`].
- Jev cost USD 0.057 per 1,000 notes with latency p50 0.198 s and p95 0.355 s; Decisions USD 0.1319 at the list rate,
  0.254 s and 0.735 s [`judges`]. This step used 1,367,355 TypeSafe tokens (USD 0.0574) and 245,314 OpenAI tokens.
- Full tables: data/scribe/v3/cascade/RESULTS.md.

## 8. Cost per 1,000 notes

| step | cost | source |
|---|---|---|
| Jev judge, v2 questions | USD 0.0618 in the benchmark; USD 0.0646 in the gate (1,538 tokens per note at USD 0.042 per million) | benchmark-v1.json `cost`, gate-v1.json `tokens.jev` |
| Decisions judge | USD 0.1442 at the list rate of USD 0.10 per million input tokens (output not charged) | benchmark-v1.json `cost.decisions`; the Decisions guide, opened 2026-11-14 |
| Nemotron teacher | not computed: 3,650 calls in kept candidates for 1,600 notes, no Verda price was read | teacher/stats.json |
| Haiku audit | not computed: token use was not recorded | |

Totals spent: TypeSafe USD 0.1715 over 2,737 requests; OpenAI 1,038,484 tokens over 690 requests
[judges/usage-typesafe.json, judges/usage-openai.json]. The gate step read its OpenAI allowance as additive to the
judges step, so the total exceeds 600,000 if that limit was meant cumulatively.

## 9. What failed

- 87 accepted round-2 training notes start with the literal style label (74 are terse). No version-2 or held-out note does.
  The code check and the gate miss it. train.parquet is unchanged because a student run is pre-registered against it;
  `round2.jsonl` now has a `starts_with_style_label` flag so a trainer can drop them
  [dataset-stats.json `round2.added_to_train_starts_with_style_label`].
- The gate rejected 83 notes, 34 of them long_multi_visit (233 passed the code check, 199 were accepted), and the audit found most of the audited rejects clean.
- The rule is not calibrated for no_event, terse or long notes.
- 111 accepted notes are read-back-inconsistent and stay in train, flagged in `round2.jsonl`.
- The cascade and the student comparison did not happen.
- 76 identical benchmark requests (50 Jev, 26 Decisions) were paid twice before a per-request lock was added.

## 10. Limits

Synthetic text written by models. Labels come from the sampler but the notes were written by a model and checked only
by other models. No human read the notes. No clinical validation. The audit is a language-model audit. Planted errors are
six mechanical kinds in equal shares, which real teacher errors need not match.
