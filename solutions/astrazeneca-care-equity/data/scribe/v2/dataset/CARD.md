# SAMA pathway scribe dataset v2

SYNTHETIC ONLY. Every note is invented text written by a language model from a sampled answer key.
No real patients, clinicians or patient text. A research artefact, not a medical device, and not for clinical use.

The task: read one Finnish clinical-style note and its note date, and return the entry route and the
dated cancer-pathway events as canonical JSON. Version 2 adds a second writer (Claude Haiku) to the
Nemotron notes of version 1, notes without any pathway event, notes built around two wording traps
(referral sent versus received; first contact versus physician assessment versus specialist visit), and a
second target format in which the model copies each date as printed and code does the date arithmetic.

## Files

| file | rows | nemotron-3.5-super-vl | claude-haiku-5-5 | standard | careful | no_event |
| --- | --- | --- | --- | --- | --- | --- |
| `train.parquet` | 2354 | 1716 | 638 | 2184 | 63 | 107 |
| `val.parquet` | 310 | 250 | 60 | 294 | 6 | 10 |
| `test_nemotron.parquet` | 500 | 500 | 0 | 500 | 0 | 0 |
| `test_haiku.parquet` | 200 | 0 | 200 | 147 | 20 | 33 |
| `rejected.parquet` | 2290 | 1990 | 300 | 2229 | 61 | 0 |

- `train` = version-1 train + the accepted Haiku notes that are not held out.
- `val` = version-1 val + 60 accepted Haiku notes.
- `test_nemotron` = version-1 test, the same rows in the same order.
- `test_haiku` = 200 accepted Haiku notes, held out and stratified by kind: careful 20, no_event 33, standard 147.
- `rejected` = version-1 rejected + the Haiku notes that failed a gate. Not for training.

No id occurs in two files. For a note with events the id is the SHA-256 of its answer key (route and
events), so identical ground truth cannot sit on both sides of a split. A note without events has one of
only five possible answers (a route and an empty list), so there the id also covers the dated content.
The hold-out is fixed by a hash of the id (`heldout` in the statistics file), not by file order.

## Columns

The version-1 columns keep their names, types and order: `id`, `split`, `note_text`, `note_date`, `style`,
`entry_route`, `events`, `target_json`, `date_forms`, `teacher_model`, `verifier_probabilities`, `accepted`,
`synthetic`, `distractors`. `split` holds the name of the version-2 file; every other version-1 value of a
version-1 row is unchanged. New columns:

| column | content |
| --- | --- |
| `writer` | `nemotron-3.5-super-vl` or `claude-haiku-5-5` |
| `kind` | `standard`, `careful` or `no_event` (all version-1 rows are `standard`) |
| `expression_json` | the expression target, see below |
| `focus` | what the specification was built to exercise, e.g. `referral_sent_only`, `non_cancer_lookalike` |
| `facts` | the events with the date string printed in the note (`expression`) and its form |
| `reject_stage` | `code_check` or `verifier` in `rejected.parquet`, otherwise empty |

## The expression target

`target_json` gives absolute dates, so the model has to turn `12 päivää sitten` into a calendar date.
`expression_json` holds the same events with each date as the note states it:

```
{"kind":"ABSOLUTE","date":"YYYY-MM-DD"}   3.2.2025, 3. helmikuuta 2025, and 3.2. (year of the note date)
{"kind":"MONTH","year":Y,"month":M}       helmikuussa 2025
{"kind":"DAYS_AGO","n":N}                 12 päivää sitten
{"kind":"WEEKS_AGO","n":N}                8 viikkoa sitten
```

Events are listed in the order their date strings first appear in the note, so that no date comparison is
needed to order them. `scribe/v2/data_tools.py` has the resolver (`resolve_expression(obj, note_date)`), the
prompt (`expression_messages`) and a JSON schema for constrained decoding (`EXPRESSION_SCHEMA`). A test
resolves the expression target of all 5654 rows against the note date and compares the result with
`target_json`; the build refuses to write a row that does not match. Date kinds in train, val and test: ABSOLUTE 4068, DAYS_AGO 1381, MONTH 1357, WEEKS_AGO 1249.

## How the Haiku notes were made and checked

1200 specifications (900 standard, 150 careful, 150 no_event) were sampled by code with seeds that
differ from version 1; none shares an id or an answer key with version 1 or the earlier 60-note Haiku pilot.
Twelve Claude Haiku agents wrote the notes from `WRITER_INSTRUCTIONS.md`. 1198 notes were delivered in
48 files, all valid JSON; 2 specification(s) have no note. Note text was not edited.
The writers were told to leave a note out rather than break a rule, and one reported checking its notes
with a script, so the code-check rate below describes delivered notes.

Both gates are the version-1 ones, imported unchanged from `scribe/verify.py`:

1. Code check: every planned date string is present, nothing else looks like a date, 60 to 140 words.
2. TypeSafe Jev (`jev-latest`): one Noul per event and one for the route (each at least 0.8), one for any
   unlisted event and one per non-event date (each below 0.5). A `no_event` note gets a single Noul, whether
   the note describes any dated cancer-pathway event, which must be below 0.5.

| kind | notes | code check failed | Jev rejected, of those that passed the code check | accepted |
| --- | --- | --- | --- | --- |
| all | 1198 | 0 of 1198 (0.0 %, 95 % interval 0.0 to 0.3 %) | 300 of 1198 (25.0 %, 95 % interval 22.7 to 27.6 %) | 898 of 1198 (75.0 %, 95 % interval 72.4 to 77.3 %) |
| standard | 898 | 0 of 898 (0.0 %, 95 % interval 0.0 to 0.4 %) | 239 of 898 (26.6 %, 95 % interval 23.8 to 29.6 %) | 659 of 898 (73.4 %, 95 % interval 70.4 to 76.2 %) |
| careful | 150 | 0 of 150 (0.0 %, 95 % interval 0.0 to 2.5 %) | 61 of 150 (40.7 %, 95 % interval 33.1 to 48.7 %) | 89 of 150 (59.3 %, 95 % interval 51.3 to 66.9 %) |
| no_event | 150 | 0 of 150 (0.0 %, 95 % interval 0.0 to 2.5 %) | 0 of 150 (0.0 %, 95 % interval 0.0 to 2.5 %) | 150 of 150 (100.0 %, 95 % interval 97.5 to 100.0 %) |

Intervals are Wilson 95 % intervals. Reasons for a code-check failure (a note can have several): none. Reasons for a Jev rejection (a note can have several): event below 0.8 65, route below 0.8 215, unlisted event at or above 0.5 38, distractor at or above 0.5 0.

Rejected notes by what the specification exercised: first_contact_and_physician_assessment 7 of 15, first_contact_physician_assessment_and_specialist_visit 9 of 15, physician_assessment_and_specialist_visit 5 of 15, referral_received_only 2 of 23, referral_sent_and_received 14 of 30, referral_sent_only 9 of 22, sampler_v1 239 of 898, single_first_contact 5 of 10, single_physician_assessment 7 of 10, single_specialist_visit 3 of 10. Events scored below 0.8, by type: SYMPTOM_ONSET_REPORTED 0 of 278, FIRST_CONTACT 8 of 277, PHYSICIAN_ASSESSMENT 23 of 304, REFERRAL_SENT 6 of 330, REFERRAL_RECEIVED 10 of 317, SPECIALIST_VISIT 12 of 284, DIAGNOSIS 2 of 258, MDT_DECISION 5 of 259, TREATMENT_START 1 of 262.

The single `no_event` question gave at most 0.04 for the 150 `no_event` notes. As a positive control
the same question was asked about accepted Haiku notes that do hold pathway events: 60 of 60 (100.0 %, 95 % interval 94.0 to 100.0 %) were judged to contain one, lowest probability 0.69.

TypeSafe use for this step: 1258 requests, 1410864 tokens (1300516 in, 110348 out), USD 0.059256 at USD 0.042 per million tokens; 0 failed attempt(s). Of these, 1198 requests and 1369795 tokens verified notes and 41069 tokens were the positive control. The limit was USD 3.

## Limits

- A Jev probability is a model judgment. Passing both gates does not prove that a label is right, and the
  thresholds are the version-1 ones. In version 1 a stricter second Jev pass disagreed with 43 of 60 sampled
  accepted notes, while an independent reader found 2 indefensible labels in 60 (the version-1 card and
  `data/scribe/label-audit-v1.json`). Neither audit has been run on the Haiku notes.
- The accepted Haiku notes are the ones Jev scored highly. Most rejections were a route score below 0.8, so
  train, val and `test_haiku` over-represent the ways of stating the route that Jev reads as explicit.
  `test_haiku` was filtered by the same gate as the training notes and is not an unfiltered sample of the writer.
- `test_haiku`, `val` and `train` Haiku notes come from the same 12 writer sessions (slices): notes were held out
  by a hash of their id within each kind, not by session (`assign_haiku`). A run trained on Haiku notes is
  therefore tested on notes from sessions it saw in training, which favours it. No near-duplicates were found
  (review of 2026-11-14, `runs/review-findings-v2.json` finding 8), but a session-disjoint Haiku test set, for
  example two whole slices held out, is needed before claiming that Haiku training generalises across sessions.
- The `no_event` gate asks one question. It does not check that the note names the service given as
  `entry_route`; by convention the route of a note without events is the service where the contact takes place.
- The code check would accept a date string that is printed more than once; 0 accepted Haiku note(s) do that.
- A date without a year (`3.2.`) is ABSOLUTE in the expression target, so the model still has to copy the
  year from the note date for that one form.
- The Finnish of the specifications and the notes has not been reviewed by a Finnish clinician.
- Sampled answer keys are a language-coverage design (uniform event subsets, evenly spread routes), not
  Finnish epidemiology. Two writers are still only two writers; real records will differ from both.
- Nothing here establishes how well a model trained on this data extracts events.

Exact numbers, hashes of inputs and outputs: `data/scribe/v2/dataset-stats.json`. Reproduce with
`scribe/.venv/bin/python scribe/v2/data_tools.py build`; test with
`scribe/.venv/bin/python -m unittest discover -s data/scribe/v2/tests`.
