# NVIDIA "Best Use of Nemotron": submission text

The form asks for "a short explanation identifying the model used, what it does, why it matters,
and how you improved its outputs". Part 1 is ready to paste. Part 2 is the evidence behind it.
Every number comes from the file named next to it, and `submission/check_numbers.py` recomputes
them. All notes are SYNTHETIC; the planner saw only public aggregate data.

Before submitting: the NVIDIA minimum asks for Nemotron "in the working solution". Say "in the
product" only if the planner panel (`web/planner.mjs`, cached `data/planner/plans-v1.json`) is on
the page at code freeze (`BIG_PICTURE.md` must-ship item 1); otherwise say "run on SYNTHETIC notes
and public data, shown as cached plans".

---

## Part 1. Text for the form

**Model.** NVIDIA Nemotron 3.5 Super VL (`nemotron-3.5-super-vl`), called through the
OpenAI-compatible endpoint hosted by Verda for Junction, at temperature 0, with tool calling and
`enable_thinking`.

**What it does in SAMA.** SAMA measures Finland's cancer pathway clock and turns it into action, so
that the pathway is the same wherever people live, whoever they are and however they enter care.
Nemotron does two jobs in the product and one in the data:
1. **County planner.** For each of Finland's 23 areas it drafts an action plan by calling four SAMA
   tools (county brief, budget portfolio, evidence, national roadmap measure). Each action names an
   owner, an indicator and the roadmap measure it serves, plus one line on what the evidence does not
   support. Every sentence goes through a code check that each number equals a tool output of the
   same run, then a TypeSafe faithfulness check; failed sentences are dropped, never repaired. A
   planner decides; the plans are labelled drafts.
2. **Second reader.** It reads each SYNTHETIC Finnish note after our small Gemma scribe. When the two
   agree, the pathway events are pre-filled for one-click confirmation; when they differ, the note is
   marked "needs editing". A person confirms every event either way.
3. **Teacher.** It wrote 3,222 of 3,860 SYNTHETIC Finnish notes that trained the Gemma scribe.

**Why it matters.** Finland cannot yet see whether its cancer pathways meet their target. Planners
need a plan they can check, and clinicians need fewer corrections. The planner wrote a plan for
23 of 23 areas; 255 of 299 sentences survived the checks, and 0 kept sentences carry a number that
is not in a tool output. On 700 SYNTHETIC test notes, the two-reader rule pre-fills 651 notes with 4
wrong among them (0.6%) and marks 49 as needing editing; before tonight our best rule pre-filled 263
notes with 7 errors.

**How we improved its outputs.**
- *Planner.* Prompt v1 kept 164/299 sentences, with 0 of 69 indicator lines surviving. Prompt v2
  changed only the field formats and kept 255/299 (indicator lines 67 of 69) under the same gate.
  Giving the faithfulness check only the tool output each field comes from kept 255 sentences
  against 197. 10 of 10 off-limits requests (individual treatment advice, drug doses, an invented
  county) produced no plan: the model refused 9 and a code guard blocked 1.
- *Second reader.* One change at a time on 310 validation notes, with an unchanged rerun as the
  noise floor: absolute dates with Nemotron doing the arithmetic 192/310 (61.9%); copying each date
  as written and letting code compute it 282/310 (91.0%), +29.0 points; schema validation with one
  repair retry 287/310; a code check that every date is printed in the note 290/310;
  `enable_thinking` 304/310 (98.1%), +4.5 points (15 fixed, 1 worse, p = 0.00052). The chosen
  version then read the 700 test notes once: 690/700; 199/200 on notes written by another model.
- *Vision, tested honestly.* Read from page images, 13 of 20 notes were exact against 19 of 20 from
  text; it misread ä or ö on 9 of 20 pages. Not good enough yet, so the product keeps text input.

**Limits.** All notes are SYNTHETIC and Nemotron wrote most of them, so its reader score is
optimistic. NVIDIA's model card does not name Finnish; plans are English drafts. Real patient notes
never go to a hosted endpoint: in production the second reader is self-hosted in a county-controlled
environment, or a person does that step.

### Short version, if the form field has a length limit

Model: NVIDIA Nemotron 3.5 Super VL on the Verda-hosted endpoint, with tool calling and
enable_thinking. What it does: SAMA measures Finland's cancer pathway clock and turns it into
action. Nemotron drafts each area's action plan by calling SAMA's own tools: 23 of 23 plans, 255 of
299 sentences kept after a code number check and a faithfulness check, 0 kept numbers outside the
tool outputs, 10 of 10 off-limits requests with no plan. As a second reader after our Gemma scribe,
it pre-fills 651/700 SYNTHETIC test notes for one-click confirmation (4 wrong); the rest need
editing; a person confirms every event. How we improved it: field-format prompt 164/299 to 255/299
kept sentences; copying dates and computing them in code 192/310 to 282/310; enable_thinking
304/310 (98.1%). Image input tested, not good enough yet. All notes SYNTHETIC.

---

## Part 2. Evidence

### County planner (public aggregate data; English drafts)

| | Prompt v1 | Prompt v2 (selected) |
| --- | --- | --- |
| Areas with a plan | 23 | 23 of 23 |
| Sentences kept of 299 | 164 | 255 |
| Indicator lines kept of 69 | 0 | 67 |
| Kept sentences with a number not in a tool output | 0 | 0 |
| Off-limits requests with no plan, of 10 | 10 | 10 |

- Roadmap measure ids confirmed by code against `get_roadmap_measure`: 69/69.
- Selected version: 93 Nemotron calls (516,733 prompt and 26,788 completion tokens); TypeSafe Jev
  for the gate USD 0.1344. Nemotron cost is not stated because the endpoint price is unverified.
- The selection rule (v2 only if it keeps more sentences, still 0 unmatched numbers, at least 20 of
  23 areas with 3 kept sentences, and 10 of 10 off-limits with no plan) was written before the
  comparison; there is no separate held-out set of areas.
- Source: `data/planner/plans-v1.json` (`summary`), `runs/laneB-step6.jsonl`.

### Vision input (20 SYNTHETIC notes as page images; one rotated, one photo-like)

| | From the image | From the text |
| --- | --- | --- |
| Exact match | 13/20 | 19/20 |
| Notes with a relative date | 7/10 | 10/10 |
| Mean seconds per note | 6.74 | 2.02 |

Transcription: ä or ö misread on 9 of 20 pages, a date string changed on 4 of 20. Verdict in the
file: "tested, not good enough yet". Source: `data/planner/vision/vision-6b-v1.json` (`summary`).

### Validation ladder (310 SYNTHETIC notes; 250 Nemotron-written, 60 Haiku-written)

| Version | What changed | Exact match (Wilson 95%) | Paired change against the previous version | Parse failures | Output tokens per note | Mean seconds per note |
| --- | --- | --- | --- | --- | --- | --- |
| v0 | absolute dates: Nemotron does the arithmetic | 192/310 (56.4-67.2) | | 8 | 79.7 | 0.34 |
| v1 | expression format: copy the date, code computes it | 282/310 (87.3-93.7) | +29.0 pts, 98 fixed, 8 worse, p < 1e-6 | 11 | 85.1 | 0.35 |
| v1rep | nothing (identical rerun) | 282/310 | 6 up, 6 down, p = 1.0 | 8 | 85.7 | 0.36 |
| v2 | + schema validation and one repair retry | 287/310 (89.1-95.0) | +1.6 pts, 10 fixed, 5 worse, p = 0.30 | 3 | 88.2 | 0.30 |
| v2g | + grounding check (every date printed in the note) | 290/310 (90.2-95.8) | +1.0 pts, 7 fixed, 4 worse, p = 0.55 | 2 | 93.1 | 0.30 |
| v3 | + enable_thinking | 304/310 (95.8-99.1) | +4.5 pts, 15 fixed, 1 worse, p = 0.00052 | 0 | 1105.8 | 2.54 |

Haiku-written validation notes only (60): 41, 53, 56, 56, 60 for v0, v1, v2, v2g, v3.
Notes with a relative date (166): 59, 153, 156, 156, 164. Rerunning v1 unchanged moved 12 notes.
Percentages: v0 61.9%, v1 91.0%, v2 92.6%, v2g 93.5%, v3 98.1%. Thinking costs 1,106 against
93 output tokens per note and 2.54 s per note.
Source: `data/scribe/nemotron/reader-v1.json` (`validation`, `validation_ladder*`).

### Test, selected version v3, read once (700 SYNTHETIC notes)

| Slice | Exact match (Wilson 95%) |
| --- | --- |
| All | 690/700 (97.4-99.2) |
| Haiku-written (primary slice: a writer other than Nemotron) | 199/200 (97.2-99.9) |
| Nemotron-written | 491/500 (96.6-99.1) |
| Notes with a relative date | 361/367 |

Errors: 9 wrong event types and 1 wrong date; 0 parse failures. Mean latency 2.48 s per note at
concurrency 8. Source: `data/scribe/nemotron/reader-v1.json` (`test`).

### Two-reader agreement with Gemma (rule fixed in advance, no threshold)

| | Validation | Test |
| --- | --- | --- |
| Gemma 3 270M + code resolver exact | 289/310 | 651/700 |
| Nemotron v3 exact | 304/310 | 690/700 |
| Pre-filled for one-click confirmation (both agree) | 286/310 | 651/700 |
| Wrong among pre-filled | 0 | 4 (all REFERRAL_RECEIVED read as REFERRAL_SENT, Nemotron-written notes) |
| Needs editing | 24 | 49 |
| Nemotron exact among needs editing | 18 | 43 |
| Pre-filled correctly per 100 notes | 92.3 | 92.4 |

Haiku-written test notes: 169/200 pre-filled, 0 wrong. Baseline before tonight: 263/700 in the
"no edit needed" group with 7 errors (TypeSafe Jev scores at a 5% error target). Measured offline
on stored outputs; the product cascade is not claimed here.
Source: `data/scribe/nemotron/cascade-agreement-v1.json`.

### Teacher (SYNTHETIC training data)

- Round 2: 1,600 answer keys, 4,042 requests; 1,589 notes passed the code check and 1,465 were read
  back exactly by a blind second call of the same model. The TypeSafe Jev gate accepted 1,506.
- The main run made 3,551 requests in 268.8 s on the Verda-hosted endpoint, about 13.2 requests a
  second.
- Training set v3: 3,222 Nemotron-written and 638 Haiku-written notes.
Source: `data/scribe/v3/summary-v1.json`, `runs/teacher2.jsonl`, `data/scribe/v3/dataset/train.parquet`.

### Tool calling and thinking preflight

One call with one tool returned a valid call (`resolve_relative_date`, n = 3, unit weeks). One call
with `enable_thinking` returned its reasoning in a separate field, and its answer parsed and matched
exactly. Source: `data/scribe/nemotron/preflight-v1.json`.

### Requests and cost

2,602 reader requests at concurrency 8 or less, 0 request errors. The endpoint's price is not
verified, so cost is recorded as unknown, not as zero. Source: `data/scribe/nemotron/ledger.json`,
`data/scribe/nemotron/requests.jsonl`, `runs/laneB-step4.jsonl`.

### Other NVIDIA software in SAMA (does not count toward the Nemotron minimum)

NVIDIA FLARE 2.9.1 federated statistics, simulator mode on one laptop, 23 simulated county sites on
SYNTHETIC data: 92 of 92 county-by-interval cells equal SAMA's central table within 1e-6, with the
same small cells suppressed. The "can this county see itself?" gate on top of it computed the
referral-to-treatment clock per county (253 of 253 cells equal the central computation) and labels
a county's figure "not comparable" when its dates were read badly: 15 of 23 with the scribe as is,
1 of 23 with the code resolver. Source: `data/flare/summary.json`, `data/flare/gate-v1.json`.

### Caveats (from the result files)

- The notes come from six date forms in code-controlled specifications; real notes use other
  phrasings that neither the expression format nor the grounding check covers yet.
- Validation chose the version, so validation figures are selection results; the test set was read
  once, by the selected version only.
- Temperature 0 on a batched server is not bit-deterministic; the v1 rerun measures that noise.
- The planner prompts were compared on the same 23 areas they were written for.
