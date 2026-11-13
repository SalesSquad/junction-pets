# Fictional robot episode metadata review

`reviewEpisode(jsonText)` from `episode-review.mjs` is a pure, bounded check of
**invented metadata declarations**. It never reads footage, calls Qualia, records
a person or robot, runs a model, authenticates consent, establishes dataset
rights, verifies success/safety, or controls a device. This is our local source
contract, not a Qualia product/API schema. All example identities, frames,
timestamps, outcome labels and consent statements are fictional.

## Closed input

Accept one primitive JSON string, maximum **32,768 UTF-8 bytes**. Ordinary
`JSON.parse` semantics apply: duplicate object members take their last value.
This is not a canonical/signature parser. Every object has exactly its listed
keys; missing keys, extras, invalid types, duplicate annotation/evidence IDs or
values outside the accepted domains throw `TypeError`. Numbers are safe
integers without negative zero; no coercions or inferred defaults are used.

A fictional ID is `fictional-` followed by 1–64 lowercase letters, digits or
hyphens, starting with a letter/digit. These labels do not identify real people.

| Required root field | Domain |
| --- | --- |
| `schemaVersion`, `kind` | Exactly `1`, `"fictional-robot-episode"` |
| `episodeId`, `recordingId` | Fictional IDs |
| `durationMs` | Integer 1–3,600,000; declared episode duration, not a measured recording |
| `expectedFrameCount` | Integer 1–128 |
| `frames` | 0–128 objects, exactly `{index, timestampMs, frameId}` |
| `consent` | `null` (no declaration) or exactly `{state, recordingId, purpose}` |
| `annotations` | 0–32 objects with the six fields below |

Frame fields are `index` (integer 0–127 or null), `timestampMs` (integer
0–3,600,000 or null) and `frameId` (fictional ID or null). Explicit null means
unknown and always produces a finding. Timestamp and index zero are meaningful,
not missing. Frames must be supplied in contiguous index order beginning at
zero; count must equal `expectedFrameCount`. Non-null frame IDs must be unique.
Known timestamps must increase strictly in the supplied order and fall within
`[0, durationMs]`. Unknown timestamps remain findings; comparison resumes at
the next known time against the prior known time. No frame rate, synchronization
or image-content completeness is inferred.

Consent fields: `state` is `granted`, `unknown`, `withdrawn` or null;
`recordingId` is a fictional ID or null; `purpose` is `annotation-review`,
`training` or null. Only the **declaration** `granted` for the exact recording
and `annotation-review` is consistent. Unknown/missing/withdrawn consent or
another/unknown scope requires review. Even consistency never grants data use,
proves current lawful consent, validates revocation, or authorizes training.

Every annotation has exactly:

| Field | Domain |
| --- | --- |
| `id` | Unique fictional ID |
| `fromFrame`, `toFrame` | Integers 0–127; inclusive interval |
| `label` | `attempt`, `success`, `failure` or `unknown` |
| `source` | `operator` or `model`; a declaration, not verified provenance |
| `evidenceFrameIds` | 0–8 unique fictional frame IDs |

Annotation intervals must be ordered and their endpoints must name supplied
frames at the corresponding contiguous indices and stay below the expected
count. Success/failure labels need at least one evidence reference; every
reference must name a supplied frame within the annotation interval. A linked
frame ID does **not** prove what an image contains or that a task succeeded.
Empty annotations are accepted: this check does not require a label for every
frame or claim annotation/dataset coverage. Duplicate frame IDs are a finding;
the first supplied position is used for subsequent references while the overall
result remains `needs-review`.

## Output and ordering

Return exactly `{schemaVersion:1, kind:"fictional-episode-review", episodeId,
status, findings, summary, boundary}`. `status` is `consistent-declarations`
only with no findings, otherwise `needs-review`. Neither is a readiness,
deployment, permission, recording-quality or model-performance qualification.

`summary` contains `{frames, expectedFrames, annotations, consentDeclaration}`;
the final value is `missing` for null consent, `unknown` for null consent state,
or the declared state. `boundary` is always exactly `{synthetic:true,
recordingInspected:false, consentVerified:false, outcomeVerified:false,
deviceActionAuthorized:false}`.

Findings have exactly `{code, field}`, in deterministic order: count, supplied
frames, consent, supplied annotations/references. Codes and field locations:

- `frame-count-mismatch`: `frames`.
- `unknown-frame-index`, `frame-sequence-mismatch`: `frames[i].index`.
- `unknown-timestamp`, `timestamp-outside-episode`, `nonmonotonic-timestamp`:
  `frames[i].timestampMs` (outside precedes monotonic when both occur).
- `unknown-frame-id`, `duplicate-frame-id`: `frames[i].frameId`.
- `missing-consent-declaration`: `consent`; `consent-withdrawn` or
  `consent-unknown`: `consent.state`; `consent-recording-mismatch`:
  `consent.recordingId`; `consent-purpose-mismatch`: `consent.purpose`.
- `reversed-annotation-interval`, `annotation-frame-out-of-range`:
  `annotations[i]`.
- `outcome-without-evidence-reference`, `unknown-evidence-frame`,
  `evidence-outside-annotation`: `annotations[i].evidenceFrameIds`.

## Example and verification

`examples/fictional-episode.json` yields three frames, one annotation and no
findings, while every execution/consent/outcome authority flag stays false.
Run `node --test tests/pet-qualia.test.mjs` from the repository root. Twelve
source tests cover timing/sequence/identity gaps, missing/null/zero, consent
scope and withdrawal, annotation provenance/references, malformed input,
bounded collections and ordinary JSON behavior. They are distinct from the
six unchanged authored model evals; no model, camera or robot has been invoked.
