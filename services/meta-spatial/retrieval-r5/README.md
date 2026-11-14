# Meta Lens R5: four image specialists

Four Nemotron roles produced **32 valid observations on eight development
families** using real query and gallery images. The executed campaign made
42 inference calls, including ten preserved generation/contract failures.
This is an inference and evaluation extension to R4, not a Nemotron weight
training run. It does not establish the >93% accepted-coverage target.

The earlier R4 models were actually trained; their results remain in PR #187
and `retrieval-r4`. R5 does not change their model weights, calibration rule,
historical results or production acceptance policy.

## Measured development result

Python evaluation and a separately implemented base-R summary agree exactly.
All rates below describe the same eight selected development families.

| Method | Correct first choice | Explicit proposals | Wrong proposals | Model abstentions |
| --- | ---: | ---: | ---: | ---: |
| Frozen R4 baseline | 6/8 (75%) | Not evaluated here | Not evaluated here | Not evaluated here |
| Nemotron visual | 5/8 (62.5%) | 1/8 | 0/1 | 7/8 |
| Nemotron detail | 5/8 (62.5%) | 1/8 | 0/1 | 7/8 |
| Nemotron critic | 4/8 (50%) | 3/8 | 1/3 | 5/8 |

The true product appeared in the frozen top three for only **6/8 queries**.
R4 already ranked all six first. Consequently this cohort contained no
baseline error that these three-candidate roles could repair. Visual/detail
each lost one previously correct answer; critic lost two. These are real
regressions on this pilot, while zero improvements are structurally forced
by its candidate pool. The result does not establish that a broader-pool
reranker could never help. R4 remains the comparison baseline.

OCR returned text for **3/8 queries, with 23 spans**, and no legible text for
five. These are model observations, not transcription accuracy. There are no
independent transcription labels. The detail role requested five label
closeups, one side view and one other observation; no new capture was made.

Proposal coverage above is descriptive and is not qualified acceptance.
No role demonstrated a coverage gain, and no Nemotron proposal is promoted
to a production acceptance decision. The deliberately selected eight-case
sample supports no population confidence interval or >93% coverage claim.

## Roles and inputs

| Role | Images supplied | Observation |
| --- | --- | --- |
| `ocr` | Query only | Verbatim visible text, or no legible text |
| `visual` | Query and three gallery candidates | Visible exact-variant ranking and an optional proposal |
| `detail` | Query and three gallery candidates | Distinguishing details and a useful additional capture |
| `critic` | Query and three gallery candidates | Contradictions, ranking and abstention |

These are four prompts using the same `nemotron-3.5-super-vl` backbone,
not four independent models. Their agreement is not independent evidence.
The normal runner starts all four roles concurrently. An explicit `--lanes`
subset supports repairing only missing/failed work without repeating completed
observations. No new GPU instance was provisioned.

`prepare_cases.py` pins the original R2 dataset and selected R4 report, verifies
both R4 CSVs against that report, and selects two development queries per R4
confidence quartile with eight distinct families. Selection and candidate order
do not use correctness labels. The R4 top three are shuffled before assigning
anonymous aliases. A missing true product is never injected into the pool.

Thirty unique original images were admitted by SHA256. The query is source
view 1 and each candidate is source view 0. Candidate view 1 is deliberately
not supplied: for the correct product it would be the query itself. The
additional-view role requests a new capture; no additional image was captured
in this experiment. Missing selected public ABO images are downloaded only
from the original allowlisted source and checked against the pinned dataset.

Provider prompts contain no query product ID, true family, title, catalog hint,
ranking score or correctness label. Truth lives in a separate hash-bound file
and is joined only by the offline evaluator.

## Runtime repairs observed in real calls

| Run | Calls | Valid | Result |
| --- | ---: | ---: | --- |
| `pilot-01` | 4 | 0 | All output tokens consumed by reasoning; incomplete final answers rejected |
| `pilot-02` | 4 | 0 | Reasoning disabled; field names/lengths still violated the observation contract |
| `pilot-03` | 4 | 4 | Explicit bounds and JSON schema produced one valid case for every role |
| `pilot-04` | 22 | 21 | Remaining OCR/visual/detail cases completed; critic stopped on a contradictory choice |
| `pilot-05` | 1 | 0 | A partial-properties schema union returned a ranking-only object; rejected |
| `pilot-06` | 7 | 7 | Complete-object schema alternatives completed the remaining critic cases |

The final request disables reasoning through `chat_template_kwargs`, uses a
2048-token campaign limit and constrains complete JSON objects. Local semantic
validation remains decisive: alias permutations, proposal/rank agreement,
abstention, bounded text and normalized geometry must still be valid. No failed
response was repaired by rewriting its contents or weakening the parser.

Each job has one provider attempt. Contract failures stop its role; auth/rate
failures stop further dispatch. Transport uncertainty is retained rather than
automatically retried. Deadlines stop new dispatch; an in-flight request can
continue until its separate HTTP timeout. Output directories must be new.

The existing Verda/Datacrunch credential stays in the Mac Keychain and is read
only by the calling process. Requests contain image data but no credential;
saved request receipts contain hashes rather than base64 image payloads.
Raw responses are sanitized before storage. Redirects and unregistered routes
are refused. Billing cost is unknown and is not inferred from token counts.

## Independent NVIDIA models

`nim_models.py` implements documented contracts for two separate NVIDIA routes:

| Model | Route | Purpose |
| --- | --- | --- |
| Nemotron OCR v2 | `ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2` | Dedicated image text extraction |
| Nemotron Nano 12B v2 VL | `integrate.api.nvidia.com/v1/chat/completions` | Additional visual comparison backbone |

`run_nim.py` runs one case with both models by default: at most two calls.
Explicit eight-case execution permits at most sixteen calls and four workers.
It validates original pixels before dispatch and uses only a separately
configured `NVIDIA_API_KEY`. A Datacrunch credential is never sent to NVIDIA
NIM. Missing authentication produces `BLOCKED_AUTH`, zero attempted calls and
exit code 2; it cannot be reported as a provider success.

The NIM adapters and their mocked contract/budget checks are implemented.
The actual NIM launch returned **`BLOCKED_AUTH`, exit 2, zero inference calls**:
the current executor has no configured NVIDIA NIM credential. Its plan and
receipt are recorded separately from the successful Verda observations in
`results/nim-01/`. Live OCR v2/Nano inference remains untested.

## Evaluation and replay

`evaluate.py` verifies cohort, request, response, observation and summary
bindings, reparses successful raw outputs, and keeps eight as every main
denominator. It reports failures, missing observations and explicit model
abstentions separately. It accepts explicit disjoint case/role slices and
rejects duplicate attempts unless the caller names the exact failed receipt
to exclude from the selected join. That receipt remains validated, reported
and counted in all audited calls. Valid observations cannot be excluded by
this repair mechanism.

The selected campaign is `pilot-03`, `pilot-04` and `pilot-06`. Only
`pilot-04/critic/q0002.receipt.json` is explicitly superseded. Runs 01, 02 and
05 remain audit-only records. Selection repairs technical contract failures;
it does not pick the highest-scoring answer among successful retries.

Run from a clean committed checkout with the existing Python/Pillow runtime:

```sh
python -B run_specialists.py \
  --cases /absolute/prepared/cases.json \
  --output /absolute/new-nemotron-run \
  --source-commit FULL_COMMIT \
  --max-output-tokens 2048

python -B run_nim.py \
  --cases /absolute/prepared/cases.json \
  --output /absolute/new-nim-canary \
  --source-commit FULL_COMMIT
```

For offline evaluation, supply `--cases`, `--truth`, one or more `--run-dir`
paths, `--audit-run-dir` paths, the explicit `--exclude-attempt` above,
`--selection-reason`, `--source-commit` and a new `--output` JSON path.
Copied evidence can be read without original image paths; a new inference
requires the admitted original pixels. Raw bytes and their hashes are
preserved in `results/` rather than rebasing historical receipts.

The base-R cross-check is reproducible from the retained flat input:

```sh
gzip -dc results/pilot-input.csv.gz > /absolute/frozen-pilot-input.csv
Rscript pilot_summary.R \
  --input /absolute/frozen-pilot-input.csv \
  --output /absolute/new-r-summary.csv
```

The original CRLF CSV and command logs are gzip-compressed without changing
their decompressed bytes; the manifest records both stored and original hashes.

It independently counts baseline/ranking results, proposal errors, missing
observations and paired wins/losses. It performs no model fit, threshold
selection, population significance test or qualification. Deliberate sampling
of eight development families does not support those claims.

The actual cross-check ran on R 4.6.2. Python protocol/adapter/runner tests
passed in their focused runs (17 tests), and six focused evaluator tests passed
after adding explicit failed-attempt selection. Live calls verified the
reasoning, JSON and complete-object choice repairs; a separate local JSON
schema check rejected the observed contradictory, partial and duplicate-choice
forms. These checks do not qualify the remote model's recognition accuracy.

## What must improve next

The top-three candidate recall is an upper bound for these ranking roles.
Useful development findings must next be tested with a larger frozen candidate
pool and distinct training/development families. Include predeclared diagnostic
cases whose true candidate is at R4 rank 2 or lower, and keep this hard-case
diagnostic separate from the representative evaluation. OCR needs independently
transcribed labels before character/word error or accuracy can be measured.
Additional captures must be genuinely obtained and registered; requesting
them is not evidence of using multiple views.

Any learned fusion of image scores, genuine OCR and specialist observations
must be fitted on training families, selected on development, calibrated on
separate families and evaluated on a fresh frozen holdout. This small pilot
does not replace that work. All exported observations remain
`qualification=false`, `action_authorized=false` and
`physical_identity_verified=false`.

## Primary implementation references

- [NVIDIA Super VL model card and thinking controls](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16)
- [vLLM 0.32 structured outputs](https://docs.vllm.ai/en/v0.32.0/features/structured_outputs/)
- [NVIDIA OCR API contract](https://docs.nvidia.com/nim/ingestion/image-ocr/latest/use-the-api.html)
- [NVIDIA hosted OCR prerequisites](https://docs.nvidia.com/nemo/retriever/latest/extraction/prerequisites/index.html)
- [NVIDIA Nano VL API contract](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl-infer)

The remote service reports its model identifier and deployment fingerprint;
an independently pinned model-weight revision was not available. The evidence
therefore binds actual requests/responses and client source, not an immutable
remote weight checkpoint.
