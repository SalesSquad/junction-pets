# Vague-time gate (post hoc)

**POST HOC: designed after the stress results were seen.** SYNTHETIC notes only. Research artefact, not a medical device. A person confirms every extracted event; the gate only moves a note from 'pre-filled for one-click confirmation' to 'needs editing'. Every number below is read from `data/scribe/vague/results-v1.json` (written by `scribe/vague/score.py` from stored outputs; no model was run).

## What it is

`scribe/vague/rule.py` (fi-vague-time-v1, sha256 `80dae7ab2b0e3cb5...`, frozen 2026-11-15T00:39:24Z in `data/scribe/vague/freeze-v1.json` before it read any note) lists vague or approximate Finnish time expressions explicitly: vague quantities ('pari viikkoa'), approximations ('noin kaksi viikkoa', 'reilu viikko'), ranges ('2-3 viikkoa'), weeks/months/years without a day ('viime viikolla', 'viime kuussa'), parts of a period ('maaliskuun alussa'), seasons, holidays, 'around' words and 'the date is not known'. Standard library; tests: `python3 -m unittest discover -s scribe/vague/tests`.

Comparison detector: the needs-person list of the frozen resolver arm A' (`scribe/v3/lexicon.py`, frozen 2026-11-14T21:37:24Z, before the stress set). Caveat: the stress set's vague family (`scribe/stress/phrases.py`: 'pari viikkoa sitten', 'muutama päivä sitten', 'kuukausi sitten', 'pari kuukautta sitten', 'viime kuussa') was written by the same project with the same notion of vague, so this detector is not independent of it.

## Flags

| set | post hoc rule | frozen A' detector | either |
| --- | --- | --- | --- |
| validation, notes flagged (all false by construction) | 1/310 (0.3%, 95% CI 0.1-1.8) | 0/310 (0.0%, 95% CI 0.0-1.2) | 1/310 (0.3%, 95% CI 0.1-1.8) |
| test, notes flagged (all false by construction) | 1/700 (0.1%, 95% CI 0.0-0.8) | 0/700 (0.0%, 95% CI 0.0-0.5) | 1/700 (0.1%, 95% CI 0.0-0.8) |
| stress, vague notes caught | 23/29 (79.3%, 95% CI 61.6-90.1) | 29/29 (100.0%, 95% CI 88.3-100.0) | 29/29 (100.0%, 95% CI 88.3-100.0) |
| stress, false flags (notes without a vague fact) | 2/279 (0.7%, 95% CI 0.2-2.6) | 0/279 (0.0%, 95% CI 0.0-1.4) | 2/279 (0.7%, 95% CI 0.2-2.6) |

Validation and test notes hold no vague fact by construction (`data/scribe/v2/WRITER_INSTRUCTIONS.md` section 3.3 forbids any other time reference and a code check rejects notes that hold one). The rule's flags there: ['viime aikoina'] (validation); ['muistelee'] (test). On stress it flags ['viime päivinä']; ['viime aikoina'] in notes without a vague fact. All four sit in sentences about how the patient feels, not on a pathway date ('viime aikoina' and 'viime päivinä' are vague time words; 'muistelee', 'recalls', is a hedge the rule lists because recalled dates are often approximate). Each costs one pre-filled note, never an error.

The rule misses every stress note whose vague phrase is 'kuukausi sitten' (6 notes): the rule treats 'a month ago' as an exact calendar shift, the stress set as a 25-35 day window. This is a difference of definition. Changing the rule now would fit it to the stress set, so v1 stays as frozen.

## Effect on the readers (stored outputs)

| policy | set | pre-filled for one-click confirmation | error among pre-filled |
| --- | --- | --- | --- |
| two-reader cascade (Gemma 3 1B + Nemotron agree), no gate | test 700 | 684/700 (97.7%, 95% CI 96.3-98.6) | 4/684 (0.6%, 95% CI 0.2-1.5) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), + post hoc rule | test 700 | 683/700 (97.6%, 95% CI 96.2-98.5) | 4/683 (0.6%, 95% CI 0.2-1.5) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), + frozen A' detector | test 700 | 684/700 (97.7%, 95% CI 96.3-98.6) | 4/684 (0.6%, 95% CI 0.2-1.5) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), + either | test 700 | 683/700 (97.6%, 95% CI 96.2-98.5) | 4/683 (0.6%, 95% CI 0.2-1.5) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), no gate | stress 308 | 220/308 (71.4%, 95% CI 66.1-76.2) | 3/220 (1.4%, 95% CI 0.5-3.9) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), + post hoc rule | stress 308 | 218/308 (70.8%, 95% CI 65.5-75.6) | 2/218 (0.9%, 95% CI 0.2-3.3) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), + frozen A' detector | stress 308 | 219/308 (71.1%, 95% CI 65.8-75.9) | 2/219 (0.9%, 95% CI 0.2-3.3) |
| two-reader cascade (Gemma 3 1B + Nemotron agree), + either | stress 308 | 218/308 (70.8%, 95% CI 65.5-75.6) | 2/218 (0.9%, 95% CI 0.2-3.3) |
| Gemma 3 1B alone, no gate | test 700 | 700/700 (100.0%, 95% CI 99.5-100.0) | 16/700 (2.3%, 95% CI 1.4-3.7) |
| Gemma 3 1B alone, + post hoc rule | test 700 | 699/700 (99.9%, 95% CI 99.2-100.0) | 16/699 (2.3%, 95% CI 1.4-3.7) |
| Gemma 3 1B alone, + frozen A' detector | test 700 | 700/700 (100.0%, 95% CI 99.5-100.0) | 16/700 (2.3%, 95% CI 1.4-3.7) |
| Gemma 3 1B alone, + either | test 700 | 699/700 (99.9%, 95% CI 99.2-100.0) | 16/699 (2.3%, 95% CI 1.4-3.7) |
| Gemma 3 1B alone, no gate | stress 308 | 308/308 (100.0%, 95% CI 98.8-100.0) | 85/308 (27.6%, 95% CI 22.9-32.8) |
| Gemma 3 1B alone, + post hoc rule | stress 308 | 283/308 (91.9%, 95% CI 88.3-94.4) | 61/283 (21.6%, 95% CI 17.2-26.7) |
| Gemma 3 1B alone, + frozen A' detector | stress 308 | 279/308 (90.6%, 95% CI 86.8-93.4) | 56/279 (20.1%, 95% CI 15.8-25.2) |
| Gemma 3 1B alone, + either | stress 308 | 277/308 (89.9%, 95% CI 86.1-92.8) | 55/277 (19.9%, 95% CI 15.6-24.9) |

Vague facts on the stress set (29 facts in 29 notes) that reach a person:

- Gemma 3 1B alone: no gate 0/29 (0.0%, 95% CI 0.0-11.7) (stored: 11 precise days and 18 months invented without a flag); + post hoc rule 23/29 (79.3%, 95% CI 61.6-90.1); + frozen A' detector 29/29 (100.0%, 95% CI 88.3-100.0); + either 29/29 (100.0%, 95% CI 88.3-100.0).
- Two-reader cascade: no gate 28/29 (96.5%, 95% CI 82.8-99.4) (the two readers already disagree on most vague notes); + post hoc rule 29/29 (100.0%, 95% CI 88.3-100.0); + frozen A' detector 29/29 (100.0%, 95% CI 88.3-100.0).
- Stored Nemotron v3 alone, for reference: flags 3/29 vague facts for a person and leaves the vague event out in 25/29.

## Reading

- On the two-reader cascade the gate changes little: it removes the one vague note the readers agreed on, which was wrong. The test set loses 1 pre-filled note to the post hoc rule.
- On Gemma 3 1B alone (the offline, on-device path) the gate matters: without it every vague fact is dated without a flag.
- The stress vague family has five phrase types. Most of the rule's lexicon (seasons, holidays, approximations, ranges) is tested only by unit tests on constructed strings.
- Our no-gate numbers reproduce the stored results-v1.json cascade and exact-match counts: True.
