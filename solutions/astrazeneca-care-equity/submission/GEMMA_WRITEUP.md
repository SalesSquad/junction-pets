# Google DeepMind "Best Use of Gemma": write-up

**Gemma reads, code counts: a 270M-parameter Finnish pathway scribe that fits inside a hospital.**

All notes in this write-up are SYNTHETIC: language models wrote them from sampled answer keys, and
other models checked the labels. Nothing here has been tested on real clinical text. A person
confirms every extracted event. Every number comes from the file named next to it, and
`submission/check_numbers.py` recomputes it.

Stress-set figures come from `data/scribe/v4/eval/results-v1.json`: 308 SYNTHETIC notes frozen and
preregistered before any system read them, each system scored once.

## The problem Gemma solves

Finland's cancer strategy measures "treatment within target times", but no county can show it: the
dates sit in Finnish referral letters and visit notes, not in a table. SAMA asks for a small
Pathway Clock (two dates and an end reason per patient) and lets a pilot county record four optional
pathway dates to find where time is lost. Clinicians will not fill in extra forms, and real notes
cannot leave the hospital network. That calls for a small open model that runs where the notes
are, and proposes the dates for a person to confirm.

## What we built

- **Model.** Gemma 3 270M instruction-tuned (`unsloth/gemma-3-270m-it`) with a LoRA adapter, rank 16,
  on the attention and MLP projections. It reads one Finnish note and the date it was written, and
  writes one JSON object: the patient's entry route and the dated pathway events.
- **Training.** 324 steps at an effective batch of 16 on 2,354 SYNTHETIC notes from two writers
  (1,716 by NVIDIA Nemotron 3.5 Super VL, 638 by Claude Haiku). Training took 176 s on one A100.
- **Serving.** vLLM with structured outputs (JSON schema): 100 of 100 outputs were valid JSON, p95
  latency 1.80 s, 5.74 notes a second at concurrency 8.
- **On a laptop, inside the product.** The same adapter runs on a CPU behind the product's own
  `POST /api/scribe` endpoint: **18 of 20** demo notes exactly right, median **4.8 s** per note over
  HTTP, on a machine that was busy with other jobs (`data/scribe/demo/http-timing.json`).

## The finding: Gemma reads well and should not do arithmetic

On notes with no relative date, the adapter gets 303 of 333 test notes exactly right. On notes that
say "N päivää/viikkoa sitten" (N days or weeks ago), it gets **2 of 367**. It finds the right event
type almost every time; it fails at subtracting the offset from the note date. A bigger Gemma does
not fix that: Gemma 3 1B gets 6 of 367.

So we split the job. **Gemma reads; code counts.** A small, frozen rule finds each relative phrase
and resolves it against the note date. Its Finnish lexicon covers number words one to six, "eilen"
(yesterday) and "viikko sitten" (a week ago); vague phrases such as "pari viikkoa sitten" (a couple
of weeks ago) go to a person instead of getting an invented date.

| C-270m-all-v2data (Gemma 3 270M + LoRA) | Gemma alone | Gemma reads, code counts |
| --- | --- | --- |
| Validation, 310 notes (selection) | 134 | 289 (93.2%) |
| Test, 700 notes (already seen, post hoc) | 305 | 651 (93.0%, Wilson 90.9-94.7) |
| Test, Nemotron-written | 210/500 | 481/500 |
| Test, Haiku-written | 95/200 | 170/200 |

The rule made 0 notes worse, in every run and split. It runs after any inference engine, in the
product's scribe client (`serve/client.py`). Its files were hashed and frozen at 21:37:24 UTC,
before any stress note existed (`data/scribe/v4/resolver/freeze.json`).

## Moving the split into Gemma itself

We retrained Gemma on this laptop with MLX to write what it read (`{kind: WEEKS_AGO, n: 3}`) and
let code compute every date, with held-out phrasings (number words seven to twelve,
"toissapäivänä") kept out of training for the stress set. Validation, the selection evidence
(`data/scribe/v4/mlx/validation-v1.json`):

| MLX arm, 310 SYNTHETIC validation notes | Exact match | Haiku-written (60) | Parse failures | Training on the laptop |
| --- | --- | --- | --- | --- |
| A: absolute dates, then the code rule A' | 293/310 | 53/60 | 0 | 733 s |
| B: expression format, code computes every date | **290/310** (93.5%) | 46/60 | 2 | 1,004 s |

- Arm B met the rule we wrote down before training: at least 0.90, within 3 points of arm A,
  McNemar not significant (p = 0.70), under 1% parse failures.
- On Haiku-written notes B trails A: 46 vs 53 of 60 on validation (exact McNemar p = 0.09, not
  significant) and 154 vs 182 of 200 on the post hoc test set (p = 8e-6). That is why the frozen
  stress set, not validation, decides the headline.
- **On the fresh stress set, frozen and hashed before any model saw it** (308 notes,
  `data/scribe/v4/eval/results-v1.json`), the preregistered success criterion for arm B is **not
  met**. On the 143 notes with a held-out phrasing, B got **11 of 143** and the lexicon rule A'
  **0 of 143** (exact McNemar p = 0.00098; +7.7 points against the 10 required), and B got 73 of 87
  (83.9%) on standard phrasings against the 0.85 required. A' does not win either: its lexicon
  leaves those phrasings out by design. The honest headline: neither 270M reader handles phrasings
  it never saw. The 1B expression arm C got 95 of 143, and Nemotron 120 of 143 (optimistic: it wrote
  the stress notes). On 29 vague phrases ("pari viikkoa sitten"), A' sends 29 of 29 to a person,
  while B invents a precise date for 17 of 29.

## Why it matters for equity

Simulation on SYNTHETIC error profiles, 1,000 runs per cell (`data/eventlog/design-study-v1.json`,
`measured_interval_extraction`, the repository study the page reads):

| Primary care / diagnostic / treatment interval | Gemma alone | Gemma reads, code counts |
| --- | --- | --- |
| Bias in a county's median interval | +17.6 / +15.6 / +12.5 days | +0.18 / +0.08 / +0.08 days |
| Power to locate a 20% slowdown (every event confirmed: 0.786 / 0.745 / 0.759) | 0.232 / 0.127 / 0.049 | 0.772 / 0.704 / 0.708 |
| County read from text, rest of country from structured fields: false flag | 1.000 | 0.003 |

With Gemma alone, a county that documents in free text would be flagged as slow in every run when
nothing is wrong. With the split, about 3 times in a thousand, the same rate as when a person
confirms every event. That is why SAMA compares a county only
when it can see itself. Extra predicted events are not modelled in this simulation.

## Gemma and Nemotron together

Nemotron 3.5 Super VL reads each note a second time. When the two readers agree, the events are
pre-filled for one-click confirmation; otherwise the note is marked "needs editing". Measured offline
with the product's 270M adapter on 700 test notes (read before, so post hoc): 651 pre-filled with 4 wrong among them, and 49 needing editing; on the 200 Haiku-written test
notes, 169 pre-filled with 0 wrong (`data/scribe/nemotron/cascade-agreement-v1.json`). Gemma stays
the reader that can run inside the hospital; the second reader is self-hosted or replaced by a
person in production. Recalibrated on validation notes only, with the 1B expression arm C as the
Gemma reader (`data/scribe/v4/eval/results-v1.json`, `cascade`): 684 of 700 test notes pre-filled
with 4 wrong (test set read before; post hoc), and 220 of 308 stress notes with 3 wrong, where C's own confidence alone would
pre-fill 308 of 308 with 85 wrong.

## What else we learned

- **Writer variety beats volume.** Adding 638 Haiku-written notes to training lifted Haiku-written
  test notes from 13.0% to 47.5% exact match. Adding 1,506 more Nemotron-written notes moved
  Nemotron-written test notes from 210 to 209 of 500 (`data/scribe/v3/student/compare-v1.json`).
- **Size was not the bottleneck.** Gemma 3 1B was no better on dates, and Gemma 3 4B ran out of
  memory twice on a shared GPU, so there is no 4B number (`TRAINING.md`).

## Responsible use

- Gemma is used under the Gemma Terms of Use. Our adapters are Model Derivatives, and the Prohibited
  Use Policy covers automated decisions in healthcare, so every extraction stays a proposal until a
  person confirms it.
- Real notes stay inside the hospital network; hosted endpoints only ever received SYNTHETIC text.
- Language scope: the scribe reads Finnish notes only. Notes in Swedish, Sámi or any other language
  go to manual entry.

## Limits

- SYNTHETIC notes, written from six date forms; model-checked labels; one seed per run.
- The 700-note test set had been read before; 93.0% is post hoc. The stress set is the clean number.
- The resolver's lexicon is small by design; spelled-out numbers above six, weekdays and month
  offsets are not resolved.
- The best adapter was trained partly on Claude Haiku-written notes. Whether that matters for
  publishing the adapter is an open licensing question; a Nemotron-only adapter (V3-270m-nemotron:
  564/700 with the resolver) exists as the alternative (`runs/diagnose/resolve-relative-v1.json`).

## Files

`TRAINING.md`, `scribe/TEACHING.md`, `runs/diagnose/diagnose-v1.json`,
`runs/diagnose/resolve-relative-v1.json`, `data/scribe/v4/resolver/reproduce-v1.json`,
`data/scribe/v4/mlx/validation-v1.json`, `data/scribe/demo/http-timing.json`,
`serve/smoke/smoke-guided.json`, `data/scribe/v2/training-figures-v1.json`.
