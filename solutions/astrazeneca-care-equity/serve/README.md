# Serving the pathway scribe

Everything needed to run the Gemma "pathway scribe" adapter behind an HTTP endpoint and to turn
its answers into proposed rows for the pathway event log. Built for a Verda serverless
container, **not deployed**: no image has been built or pushed and no Verda deployment exists.
vLLM itself has run once: on 2026-11-14 vLLM 0.29.0 served the version-2 270M adapter on the
project's A100 for a 100-note smoke test (`serve/smoke/`, section "What has been tested").

The scribe reads one Finnish clinical-style note and its note date, and returns the entry route
and the dated cancer-pathway events (`DATA_COLLECTION.md`, section 4).

**Read this first.** Every note the adapter has seen is synthetic, written by a language model.
A second model that read 60 sampled notes in full judged 2 of their labels wrong, both an
ambiguous event type (`data/scribe/label-audit-v1.json`). The adapter is a research artefact. It is not a medical
device and nothing here is for clinical use. Each extraction is a proposal: a person has to
confirm it before it counts.

**Licence.** The base model is Gemma 3 (the ungated Unsloth mirrors `unsloth/gemma-3-270m-it`,
`-1b-it`, `-4b-it` of Google's weights). Gemma and every adapter or merged model derived from it
are used under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms) and the
[Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy), which names
automated decisions in healthcare. `AUTO_ACCEPT` below is a research setting for synthetic
notes: it must never drive an automated decision about a real patient.

## Data flow

```
note text + note date
        │
        ▼
serve/client.py ── builds the chat messages with the training-time function (scribe/prompts.py)
        │           greedy decoding, max 384 tokens, guided JSON, token log-probabilities
        ▼
POST /v1/chat/completions ──► vLLM in the container (serve/Dockerfile, serve/entrypoint.sh)
        │                      base model "gemma-base" + LoRA adapter "pathway-scribe"
        │                      answer forced to fit serve/schema.json by the xgrammar engine
        ▼
serve/client.py ── checks the answer against the schema again
        │           expression format: turns "3 viikkoa sitten" into a date, in code
        │           canonical form (scribe/prompts.py canonicalise), calendar and plausibility checks
        │           confidence from the token log-probabilities
        │           auto-accept threshold
        ▼
decision AUTO_ACCEPT or HUMAN_REVIEW
+ rows shaped like eventlog/schema.py pathway_events:
  source = TEXT_EXTRACTED, extraction_confidence = the score, verified_by_human = false
```

The client never writes to the event log. It returns the rows and the decision; in the
synthetic demonstration the caller stores auto-accepted rows as they are (still with
`verified_by_human = false`) and shows the rest to a reviewer, who sets
`verified_by_human`. `county`, `cancer_site` and `age_band` are not in a note's extraction;
the caller passes them in from structured fields, otherwise they stay empty.

## Files

| file | what it is |
| --- | --- |
| `Dockerfile` | thin layer on `vllm/vllm-openai:v0.29.0`; copies one adapter directory in; base model fetched at start or baked in with `--build-arg BAKE_BASE_MODEL=1` |
| `entrypoint.sh` | checks the adapter, takes the bearer key from `SCRIBE_API_KEY`, starts `vllm serve` with limits for one small GPU on `SCRIBE_HOST` (default `0.0.0.0`) and `SCRIBE_PORT` (8000); `/health` is the health endpoint |
| `guard.py` | ASGI middleware loaded with `--middleware` whenever a key is set: requires the bearer key on every path except `/health` and `/ping`. vLLM 0.29.0 alone checks the key only under `/v1`, `/v2`, `/inference` and `/cohere`, so `POST /invocations` (which runs generation), `/tokenize`, `/metrics`, `/docs` and others would be open (review finding 14). Tested with a fake ASGI app, not inside a live vLLM |
| `schema.json` | JSON Schema of the answer, for guided decoding: `$defs.absolute` and `$defs.expression` |
| `client.py` | the client and batch runner (standard library only) |
| `smoke_test.py` | sends held-out notes, reports exact match and latency percentiles, exits non-zero below a floor |
| `selective.py` | chooses an auto-accept threshold with a stated error bound (Learn-then-Test) |
| `convert_mlx_adapter.py` | turns the mlx-lm adapter that exists today into the PEFT layout vLLM needs |
| `deploy.md` | build, push, create, test, pause and delete commands for Verda, with prices; not executed |
| `fixtures/heldout-v1.jsonl` | 50 synthetic test-split notes with labels, for the smoke test |
| `smoke/` | the executed vLLM smoke run of 2026-11-14 on the A100: results, server log, the 100 notes and the scripts; see `smoke/README.md` |
| `tests/` | unit tests against a fake HTTP server, plus fixtures; `tests/check_converted_adapter.py` is the manual PEFT-versus-MLX comparison |
| `evidence/converted-adapter-vs-mlx.json` | the 19 answers of that comparison, side by side |
| `runlog.py` | appends to `runs/v2-serve.jsonl` |

## The two answer formats

**absolute** (what `dataset-v1` trains): the model writes ISO dates itself.

```json
{"entry_route":"SCREENING","events":[{"type":"SPECIALIST_VISIT","date":"2024-01-11","precision":"DAY"}]}
```

**expression**: the model copies the date wording from the note and the code does the
arithmetic against the note date.

```json
{"entry_route":"SCREENING","events":[{"type":"SPECIALIST_VISIT","expression":"41 viikkoa sitten"}]}
```

Why the second format exists: in the only evaluation so far (`data/scribe/eval-v1.json`,
Gemma 3 1B, 200 test notes) the adapter got 91.1% of notes exactly right in the group that
file calls "absolute dates only" (n = 90) and 0.0% in the group "with relative date"
(0 of 110), where a date is written like "41 viikkoa sitten". That small model did not manage
the date arithmetic; six fixed patterns in code do.

`client.resolve_expression` covers the six forms the generator writes (`5.3.2024`, `5.3.`,
`5. maaliskuuta 2024`, `maaliskuussa 2024`, `12 päivää sitten`, `3 viikkoa sitten`) and
nothing else: "eilen" or "viime viikolla" are rejected, not guessed. Tests check it against the
generator's own parser on all 11,254 date expressions of the dataset.

No expression-format adapter exists yet. When one is trained, pass the module that defined its
training format with `--prompts`. If that module offers `expression_messages`,
`EXPRESSION_SCHEMA` and `resolve_expression` (the names `scribe/v2/data_iface.py` looks up in
`scribe/v2/data_tools.py`), the client uses the module's prompt, schema and date resolver in
place of its own, so training and serving cannot drift apart. The client refuses to pair a
prompt that describes one format with the schema of the other.

## Use

```bash
# one note
python3 serve/client.py --base-url "$BASE_URL" --note-file note.txt --note-date 2025-03-20 \
  --episode-id ep-0001

# a batch: one JSON object per line with note_text, note_date and episode_id (or id)
python3 serve/client.py --base-url "$BASE_URL" --jsonl notes.jsonl --concurrency 8 \
  --threshold-file threshold.json --out results.jsonl

# smoke test against a running endpoint
python3 serve/smoke_test.py --base-url "$BASE_URL" --concurrency 8
```

The bearer key is read from the environment variable `SCRIBE_API_KEY`, or failing that
`VERDA_INFERENCE_KEY`. It is never taken from the command line, printed or logged.

From Python:

```python
import sys; sys.path.insert(0, "serve")
import client
scribe = client.ScribeClient(base_url, api_key=key, threshold=None)
result = scribe.extract({"note_text": text, "note_date": "2025-03-20"}, episode_id="ep-0001",
                        context={"county": "HVA05", "cancer_site": "lung", "age_band": "60-64"})
result["decision"], result["reasons"], result["rows"]
```

## Confidence and the auto-accept threshold

The endpoint returns the log-probability of every token it wrote. The client keeps the tokens
of the JSON part and offers three scores between 0 and 1:

| score | meaning |
| --- | --- |
| `geo_mean_prob` (default) | exp of the mean token log-probability. The same quantity `scribe/v2/risk.py` calibrates and `scribe/evaluate.py` ranks by |
| `seq_prob` | exp of the sum: the probability of this exact answer |
| `min_prob` | the least certain single token |

It also reports a probability per event and for the route, for a reviewer's screen.

A note is auto-accepted only if all of these hold: the answer is valid, generation ended by
itself, no event is dated after the note or more than five years before it, no event is
repeated, a score exists, an episode key exists, and the score is at least the threshold.
**Without a threshold every note goes to human review.** That is the default, because no
threshold has been calibrated for a served adapter.

Getting a threshold: run the client on calibration notes that were not used for training,
mark each result right or wrong against its label, and run

```bash
python3 serve/selective.py calibration.jsonl --alpha 0.05 --delta 0.1 --grid-start 0.99 \
  --confidence-kind geo_mean_prob --format absolute --guided response_format \
  --model pathway-scribe --calibration-set "what these notes are" --out threshold.json
```

It tests thresholds from the strictest downwards with an exact binomial test and stops at the
first failure. If it certifies a threshold, then with probability at least 1 − delta the error
rate among auto-accepted notes is at most alpha, for notes like the calibration notes. At
least 45 accepted notes with no error are needed before anything can be certified at
alpha 0.05 and delta 0.1. The threshold file records the score kind, format, decoding mode and
model, and the client refuses a file made for a different combination.

What that bound is not: "wrong" means different from a machine-written label, and the notes are
synthetic. It says nothing about real Finnish clinical notes.

`scribe/v2/risk.py` holds the project's calibration code for the offline evaluation. A
threshold found there was measured on answers decoded inside Python, not on this endpoint, so
check it on endpoint answers before using it here.

## What has been tested, and how

Run the tests (standard library; 114 tests, 6 skipped without xgrammar):

```bash
python3 -m unittest discover -s serve/tests
```

With the grammar engine as well:

```bash
uv venv --python 3.12 serve/.venv && uv pip install --python serve/.venv/bin/python xgrammar
serve/.venv/bin/python -m unittest discover -s serve/tests
```

- **Messages.** For all 50 held-out notes the request carries exactly
  `scribe/prompts.py messages(row)`.
- **Schema.** All 4,456 canonical targets of `dataset-v1` validate, as do their expression
  forms; 23 malformed absolute answers and 18 malformed expressions are rejected. The same
  cases were put through xgrammar 0.2.9, the engine vLLM uses: same verdicts, with one
  intended difference (the grammar also fixes the key order).
- **Dates.** The resolver equals the generator's parser on every dataset expression, and every
  expression answer decodes to its absolute label.
- **Routing, confidence, rows, retries, exit codes.** Against a fake HTTP server that speaks
  the response shape of vLLM v0.29.0. The fake server runs no model: these tests show the
  plumbing is right, not that Gemma is.
- **Container.** `docker build --check` passes; the Dockerfile builds on a small stand-in base
  image and the entrypoint prints the expected command inside the container. The real image
  was not built.
- **Adapter conversion.** The converted version-1 adapter was loaded with PEFT on the local
  Gemma 3 1B weights and decoded greedily on 19 held-out notes: 16 answers are identical,
  character for character, to the answers the MLX run stored. The other 3 have the same route
  and event types and differ only in dates written as "N days/weeks ago", which both runs get
  wrong.

- **vLLM on a GPU (executed once, 2026-11-14).** vLLM 0.29.0 with xgrammar 0.2.9 served
  `unsloth/gemma-3-270m-it` at revision `23cf460f6bb16954176b3ddcc8d4f250501458a9` with the
  version-2 adapter `A-270m-lora-r16-5bc648b1983f` as `pathway-scribe`, bound to 127.0.0.1 on
  the project's A100 (`smoke/vllm.log`: non-default args include `language_model_only` and
  `enable_lora`). `smoke_test.py` sent 100 held-out synthetic notes (50 Nemotron-written, 50
  Haiku-written) at concurrency 8, once with structured outputs and once without
  (`smoke/smoke-guided.json`, `smoke/smoke-plain.json`): valid JSON 100 and 98 of 100, exact
  match 0.22 both ways, p95 latency 1.80 s and 1.99 s. So Gemma 3 LoRA loading,
  `--language-model-only`, the fixed xgrammar backend and log-probabilities under guided decoding
  were all exercised there. The served verdict equals the offline evaluation's on all 100 notes
  (`data/scribe/v2/training-figures-v1.json`, `serving_parity`).

`entrypoint.sh` started that server (through `smoke/tools/start_server.sh`, on the bare machine,
not in a container), before `guard.py` and `--middleware` were added.

**Not tested:** the container image (never built), `guard.py` inside a live vLLM, any Verda
serverless deployment, cold start, and anything on real notes.

## What can differ from training

If the smoke test shows low exact match on a healthy endpoint, check these first.

1. **Chat template.** Training renders the messages with the tokenizer's chat template; vLLM
   does the same on the server. Not compared token by token.
2. **Guided decoding changes what the model may write.** The grammar removes invalid
   continuations, which can also push the model onto a valid but worse path. Compare
   `--guided response_format` with `--guided none`.
3. **Whitespace.** The adapter writes compact JSON. vLLM's `disable_any_whitespace` option
   sounds like the right setting and is the wrong one: with xgrammar 0.2.9 it makes the
   grammar demand `", "` and `": "` and reject compact JSON. The entrypoint leaves it off
   (`tests/test_xgrammar.py` guards this).
4. **Log-probabilities under guided decoding.** vLLM applies the grammar mask before it
   computes the log-probabilities it returns (read in the v0.29.0 source), so forced tokens
   score close to 1. A threshold calibrated without guided decoding does not carry over.
5. **Context length.** The server accepts 2,048 tokens for prompt plus answer
   (`SCRIBE_MAX_MODEL_LEN`). A longer note gets an HTTP error and goes to review.
6. **Non-ASCII.** The grammar accepts `ä` as a raw character, not as `ä`.
7. **Schema detail.** `serve/schema.json` allows up to 9 events (one per event type);
   `scribe/v2/formats.py` allows 8. The date pattern and the enumerations are identical.

One thing outside this directory that a reader of the rows should know:
`eventlog/schema.py` orders the pathway as DIAGNOSIS, MDT_DECISION, SPECIALIST_VISIT, while
`scribe/sample.py` generates SPECIALIST_VISIT before DIAGNOSIS. The client does not check
event order for that reason.

## Limits

- Synthetic training and test data; labels written by a model. No clinical validation.
- Trained adapters: version 1 (MLX, Gemma 3 1B; 41.0% of 200 test notes exactly right,
  `data/scribe/eval-v1.json`) and the version-2 selection (PEFT, Gemma 3 270M; 42.0% of 500
  Nemotron-written and 13.0% of 200 Haiku-written test notes, `scribe/v2/RESULTS.md`). Later
  270M and 1B students are compared in `TRAINING.md`. Their adapters are git-ignored under
  `scribe/v2/artifacts/` and `scribe/v3/artifacts/`. Treat every output as a draft.
- The expression format is defined and tested here, but no adapter has been trained for it.
- Only the six generator date forms are resolved.
- Never send real patient text to an endpoint outside the organisation that is responsible for
  it. The design in `DATA_COLLECTION.md` assumes the model runs inside the hospital network;
  a Verda container is for the hackathon demonstration with synthetic notes.
