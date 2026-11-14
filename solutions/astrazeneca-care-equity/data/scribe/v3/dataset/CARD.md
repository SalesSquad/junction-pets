# SAMA pathway scribe dataset v3

SYNTHETIC ONLY. Every note is invented text written by a language model from a sampled answer key.
No real patients, clinicians or patient text. A research artefact, not a medical device, and not for clinical use.

Version 3 = version 2 plus the notes of teaching round 2: NVIDIA Nemotron 3.5 Super VL (served on Verda)
wrote one note per specification in five curricula, read each note back blind, and rewrote it once when the
code check failed or the read-back disagreed with the answer key. A note enters `train` when its kept version
passed the round-2 code check and the
judge rule below. The held-out files are the version-2 files, byte for byte, so a version-3 student is
compared with the version-2 student on the same notes.

## Files

| file | rows | of which version 2 | round 2 | byte-identical to version 2 |
| --- | --- | --- | --- | --- |
| `train.parquet` | 3860 | 2354 | 1506 | no |
| `val.parquet` | 310 | 310 | 0 | yes |
| `test_nemotron.parquet` | 500 | 500 | 0 | yes |
| `test_haiku.parquet` | 200 | 200 | 0 | yes |
| `rejected.parquet` | 2384 | 2290 | 94 | no |

- `train` = the 2354 version-2 train rows, unchanged and first, then the 1506 accepted round-2 notes.
- `val`, `test_nemotron`, `test_haiku` = copies of the version-2 files (same SHA-256).
- `rejected` = the version-2 rejected rows, then 94 round-2 notes (`reject_stage` code_check 11, verifier 83). Not for training.
- `round2.jsonl` = side file with one line per round-2 specification (1600), keyed by `id`: `round`, `curriculum`, `kind`, `focus`,
  `code_check_passed`, `readback_consistent`, `repaired`, `told_order`, `words`, `rule`, `rule_pass`, `decisions_pass`, `file`.
  The parquet files keep exactly the version-2 columns and types, so `round` and `curriculum` live here.
- `dataset-stats.json` = the counts, the SHA-256 of every file and the results of the checks.

The build (`scribe/v3/build_dataset.py`) asserts that no id of `train` occurs in `val` or a test file, that no note
text occurs on both sides or twice in `train`, that no id occurs in two files, and that every expression target
resolves to its `target_json`. For a note with events the id is the SHA-256 of its answer key.

## Columns

The same as version 2, in the same order: `id`, `split`, `note_text`, `note_date`, `style`, `entry_route`, `events`, `target_json`, `date_forms`, `teacher_model`, `verifier_probabilities`, `accepted`, `synthetic`, `distractors`, `writer`, `kind`, `expression_json`, `focus`, `facts`, `reject_stage`.
For round-2 rows `verifier_probabilities` holds the Jev answers of the gate (`event_<i>`, `unlisted`, `route` =
probability of the claimed route); `writer` and `teacher_model` are `nemotron-3.5-super-vl`; `kind` is
`standard` for the curricula hard_standard, long_multi_visit and terse.

## The gate of round 2

Rule (`data/scribe/v3/judges/policy.json`): TypeSafe Jev alone, question set v2 (code adds each
date's day offset to the question). A note passes when every event probability is at least 0.3, the
probability of an unlisted event is below 0.6 and the chosen route is the claimed one.

| curriculum | candidates | code check | read-back consistent | accepted by Jev = rule | accepted by Decisions (prefix only) | in train |
| --- | --- | --- | --- | --- | --- | --- |
| all | 1600 | 1589/1600 | 1465/1589 | 1506/1589 | 269/368 | 1506 |
| hard_standard | 480 | 479/480 | 473/479 | 468/479 | 89/111 | 468 |
| careful | 400 | 400/400 | 385/400 | 382/400 | 65/93 | 382 |
| no_event | 240 | 238/240 | 170/238 | 236/238 | 50/50 | 236 |
| long_multi_visit | 240 | 233/240 | 219/233 | 199/233 | 20/55 | 199 |
| terse | 240 | 239/240 | 218/239 | 221/239 | 45/59 | 221 |

Read-back against the rule, over the notes that passed the code check: consistent and accepted 1395, consistent and rejected 70, inconsistent and accepted 111, inconsistent and rejected 13.

## Known limits

- 111 accepted round-2 notes have a read-back that disagrees with the answer key. They are in `train`
  because the rule accepted them; `round2.jsonl` (`readback_consistent`) lets a trainer leave them out.
- The rule's thresholds were chosen on notes with 2 to 8 events. No no_event, terse or long note was in that
  benchmark, so the rule is not calibrated for those curricula. For a no_event note it reduces to the unlisted-event
  question and the route; it accepted 236 of 238 no_event notes, while the teacher's own read-back agreed with
  the empty answer for 170 of 238.
- OpenAI Decisions is not part of the rule. It was asked for the first 369 notes of a fixed hash order only.
- The round-2 code check allows 110-260 words for long_multi_visit and 25-90 for terse; version 2 used 60-140.
- 87 accepted round-2 notes begin with the literal style label (for example 'Lähetekirje'), a formatting artefact that no version-2 train note and no held-out note has (by curriculum: {'hard_standard': 2, 'careful': 10, 'no_event': 0, 'long_multi_visit': 1, 'terse': 74}). The code check and the rule do not catch it, and   `train.parquet` still holds them, unchanged, because a student run was pre-registered against this file. `round2.jsonl` (`starts_with_style_label`) lets a trainer leave them out. A student can learn a label-to-route shortcut from them; the held-out files cannot reveal that.
- The held-out files are the version-2 files: all notes have 60 to 135 words. Round-2 terse notes have 25 to 49 words and long_multi_visit notes 110 to 260, so these files cannot measure what the new curricula teach. No held-out set for terse or long notes exists yet.
- The benchmark behind the rule used clean notes that the version-2 Jev gate had already accepted, so its false-reject share is biased low and its noise_after figures are not a property of this data. See `scribe/judges/RESULTS.md`.
- No human has read these notes. The audit (`data/scribe/v3/audit/audit-v1.json`) was made by language-model readers (Claude Haiku) who saw the claimed labels:
  accepted notes (sample of 160): wrong label 2/160 (0.013; Wilson 95% 0.003 to 0.044); wrong label or route not supported 6/160 (0.037; Wilson 95% 0.017 to 0.079); clean in the strict sense 153/160 (0.956; Wilson 95% 0.912 to 0.979).
  Notes the rule rejected (sample of 80): wrong label 2/80 (0.025; Wilson 95% 0.007 to 0.087); wrong label or route not supported 8/80 (0.100; Wilson 95% 0.051 to 0.185); clean in the strict sense 68/80 (0.850; Wilson 95% 0.756 to 0.912).
  The intervals overlap: this sample does not show that the rule separates wrong-label notes from good ones, and it rejected mostly good notes. Quote the per-status rows, not the pooled row.
Generated 2026-11-14T19:10:51+00:00 from `data/scribe/v3/gate/gate-v1.json` and `dataset-stats.json`.
