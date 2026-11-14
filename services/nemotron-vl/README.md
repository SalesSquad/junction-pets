# Nemotron 3.5 Super VL developer runtime

Dependency-free Node 22+ workflow for the existing NVIDIA companion. Nemotron performs visual observation, selects fixed tools, synthesizes evidence and checks the proposed answer. Both offline plans and execution receipts bind `pets/nvidia/pet.json` and `AGENTS.md` through the canonical `junction.nvidia` ID, current package version and SHA-256 content digests. Package guidance is not promoted to execution authority. This is a standalone public/synthetic developer adapter, not a live plugin endpoint; it does not activate a provider in production Chibi or prove bounty qualification.

```sh
node services/nemotron-vl/cli.mjs
node --test services/nemotron-vl/*.test.mjs
```

The CLI defaults to an offline plan and never reads credentials or sends a request in that mode. Its authored 960×540 worksheet visibly labels all numbers as estimates. It demonstrates the data path, not measured GPU performance or vision accuracy.

To execute, the runtime files and comparer must be tracked in a clean checkout of `SalesSquad/junction-pets`, with the exact source commit and an allowlisted origin. Configure `NVIDIA_API_KEY` through your host's existing secret mechanism; never paste it into arguments, files, logs or a PR. Then:

```sh
node services/nemotron-vl/cli.mjs --execute --source-commit <full-40-character-HEAD-SHA>
```

Execution checks the commit, worktree, tracked files and Git origin at the beginning and end. HTTPS `https://github.com/SalesSquad/junction-pets.git` and SSH `git@github.com:SalesSquad/junction-pets.git` are accepted. These are local integrity checks; receipts explicitly leave host verification unverified. A locally configured remote is not an authenticated attestation.

Trusted hosts may import `runNemotron(request, {apiKey, fetchImpl})` from `index.mjs`. The function does not read the environment. `request` contains only `question`, `images` and `benchmarkRows`; use `syntheticFixture()` for an example. Images must be bounded PNG/JPEG base64 data URLs with plausible headers and dimensions. The runtime checks signatures and declared sizes, not complete image decodability. Benchmark rows retain the existing `pets/nvidia/comparability.mjs` contract. Two distinct row IDs are required; comparisons never authenticate the supplied declarations.

Fixed read-only tools:

- `nvidia_source_card`: returns one pinned official NVIDIA card; no live browsing.
- `benchmark_compare`: invokes the existing pure comparer over supplied rows.

No arbitrary URLs are fetched, shell commands executed by tools, retries attempted, fallback models selected, new accounts created, servers started, physical devices controlled or GPU jobs launched. The only runtime network destination is the fixed NVIDIA Chat Completions endpoint; redirects are rejected. The model cannot choose a URL or tool implementation.

Limits are fixed in `LIMITS`: two images, 1 MiB each, 16,777,216 pixels per image, 2,000 question characters, 3 MB request body, 256 KiB response body, four tool-selection rounds, eight total tool calls, seven provider calls, 4,096 requested completion tokens per call, 65,536 aggregate observed reported tokens, 20-second request timeout and 90-second whole-run deadline. Token usage is validated after each response; a provider can consume tokens before an over-budget or malformed response is rejected. Input and visual token usage are not known before a call, so the aggregate budget stops subsequent calls based on observed usage and is not a strict preflight spending cap. `usageAccountingComplete` is false if any attempted call lacks valid reported usage; zero reported tokens then does not imply zero billable tokens. Costs remain unknown. There is no automatic retry. A missing key returns a failed receipt without network access.

Every provider response must return the exact requested model, one supported completion choice and valid token usage. Unknown tools, reused call IDs, invalid arguments, refusals, truncated completions, mismatched evidence and failed verification stop execution. Receipts contain request/response digests, model identity, reported usage, elapsed time and bounded tool summaries. Raw prompts, images, provider errors and chain-of-thought are excluded. Known credentials and common bearer/key forms are redacted from returned text; hosts still own input privacy and receipt handling. Model review is the same model checking its own synthesis, not an independent factual proof.

Provider facts checked 2026-11-13:

- [NVIDIA hosted model/API example](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b): exact model ID `nvidia/nemotron-3.5-super-vl-120b-a12b`, OpenAI-compatible base URL, image input, tool calling, structured output and reasoning; hosted context listed as 262K.
- [NVIDIA model card](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b/modelcard): vision temperature 0.6 / top_p 0.95 and configurable reasoning. The underlying model's up-to-1M context is deployment-dependent.

The REST body uses top-level `chat_template_kwargs`, not the Python SDK's `extra_body` wrapper. Structured outputs use the OpenAI-compatible `response_format` JSON-schema form and are validated again locally. Model capability listings establish advertised support; this exact request combination, account access, quota, latency and live provider behavior require a real authorized smoke run. No such live run has been performed by this implementation. No GPU speedup is claimed.

## Existing portfolio knowledge

For development and the next evidence workflow, read the [source-pinned knowledge reuse audit](../../docs/NVIDIA_KNOWLEDGE_REUSE.md). It records the actual DSH corpus queries, both computer inventories, existing project mechanisms and freshness gaps. Its private developer receipt is not automatically loaded into provider prompts or public plugin exports.

## Drawing observations and fixed Stoa composition

The drawing entrypoint `runDrawingObservation` reuses this exact-model bounded transport but has a separate question/source/page/region input and no benchmark requirement. It returns region-cited model interpretations or abstention after same-model review. `validateDrawingObservationResult` supports structural rechecking at the composing boundary. The fixed [Stoa→NVIDIA developer recipe](../stoa-nvidia/README.md) binds both identities and the parent request; its CLI defaults to zero-network planning. Source classifications and coordinates remain caller declarations, model review is not independent truth, and production uses existing host policy/executor/artifact seams. No live provider or sponsor-drawing qualification is implied.


## Meta task observation

The same bounded provider caller now has an explicit local NVFP4 profile, while
all existing entry points retain their hosted default. The new
`runTaskObservation` performs one grounded task interpretation without benchmark
rows or drawing-specific fields. See [the runnable Meta observation guide](../meta-spatial/OBSERVATION.md)
for the developer server, fixed profiles, strict image/track contract, evidence
limits and focused checks. It returns an advisory artifact, never a task
confirmation, identity attestation or production host grant.
