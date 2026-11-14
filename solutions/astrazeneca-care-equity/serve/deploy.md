# Deploying the pathway scribe on Verda serverless containers

**Nothing in sections 2 to 8 has been executed.** No image was pushed, no deployment was
created, no GPU was used, no money was spent. The commands are written to be pasted in order.
Each one says where its flags come from. Where a value could not be confirmed without creating
something, it is marked **UNVERIFIED** and section 10 lists it again.

What was executed is listed in section 9.

The adapter is trained on synthetic text. It is a research artefact, not a medical device.
Gemma 3 and every adapter or merged model derived from it are used under the
[Gemma Terms of Use](https://ai.google.dev/gemma/terms) and the
[Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy), which names
automated decisions in healthcare. The client's `AUTO_ACCEPT` decision is a setting for synthetic
demonstration notes only; it must never drive an automated decision about a real patient.

## 0. What you need

- Docker with buildx (checked here: Docker 29.8.2, buildx 0.37.2).
- The Verda CLI, logged in (checked here: 1.10.0).
- Registry credentials for `vccr.io` saved in the CLI. `verda --agent registry show -o json`
  reported them configured on 2026-11-14, **expiring 2026-11-20**. After that date create new
  ones in the console and run `verda registry configure`.
- An inference API key for calling the endpoint: `VERDA_INFERENCE_KEY` in
  `~/.config/verda-inference/env`. It is a different credential from the CLI login.

```bash
cd solutions/astrazeneca-care-equity          # project root; every path below is relative to it
set -a; . ~/.config/verda-inference/env; set +a   # loads VERDA_INFERENCE_KEY; prints nothing
NAME=sama-scribe-gemma                        # deployment name = URL slug, cannot be changed later
TAG=v1                                        # ':latest' is rejected by the CLI
```

## 1. Put the adapter in PEFT layout

vLLM serves PEFT adapters: a directory with `adapter_config.json` and
`adapter_model.safetensors`. Choose the case that applies.

**Case A: the version-1 adapter that exists today.** It was trained with mlx-lm on a Mac on
Gemma 3 1B (`scribe/artifacts/adapter-v1/adapters.safetensors`), which vLLM cannot read.
Convert it (local, free, about a second; this command has been run, see section 9):

```bash
python3 serve/convert_mlx_adapter.py scribe/artifacts/adapter-v1 serve/build/adapter-v1-peft \
  --base-model unsloth/gemma-3-1b-it
ADAPTER_DIR=serve/build/adapter-v1-peft
BASE_MODEL=unsloth/gemma-3-1b-it
BASE_REVISION=5b11413a10db4e486ef16a20101fd028f8f2499c
```

**Case B: an adapter trained with PEFT on a CUDA machine.** No conversion. The base model
must be the one the adapter was trained on. The version-2 selection (`A-270m-lora-r16`, the
adapter the vLLM smoke run served, `serve/smoke/README.md`) was copied back to
`scribe/v2/artifacts/adapter-selected/` (git-ignored):

```bash
ADAPTER_DIR=scribe/v2/artifacts/adapter-selected
BASE_MODEL=unsloth/gemma-3-270m-it
BASE_REVISION=23cf460f6bb16954176b3ddcc8d4f250501458a9
```

The later students are in `scribe/v3/artifacts/<run>/adapter/` (270M runs: the same base and
revision; `S-1b-lora-r16`: `unsloth/gemma-3-1b-it` at `5b11413a10db4e486ef16a20101fd028f8f2499c`).
`TRAINING.md` section 6 names the recipe it recommends. A 4B adapter (`unsloth/gemma-3-4b-it`,
`bf46152c47f5dd20b896357cb51abc4c03b8ee8c`) was never trained.

Both base models are the ungated Unsloth mirrors (Hugging Face reports `gated: false`; the
Google originals are gated). The Gemma licence applies to both. The revisions are the commits
Hugging Face listed on 2026-11-14.

An adapter that vLLM cannot serve stops the image build with a plain message: rank above 16,
DoRA, `modules_to_save`, adapter bias, per-module ranks (`rank_pattern`, which EVA
initialisation in `scribe/v2` can produce), or a base model that differs from `BASE_MODEL`.
For a per-module-rank adapter, merge it into the base weights and serve the merged model
(not built here).

## 2. Build the image

```bash
docker buildx build --platform linux/amd64 \
  -f serve/Dockerfile \
  --build-context adapter="$ADAPTER_DIR" \
  --build-arg BASE_MODEL="$BASE_MODEL" \
  --build-arg BASE_REVISION="$BASE_REVISION" \
  -t "$NAME:$TAG" --load serve/
```

- Base image: `docker.io/vllm/vllm-openai:v0.29.0`, the tag Verda's vLLM tutorial names as
  tested. Docker Hub lists its linux/amd64 variant at 8,674,178,554 bytes compressed, so the
  first build downloads about 8.7 GB.
- `--platform linux/amd64`: **UNVERIFIED** that Verda's GPU nodes are x86-64 (their docs do not
  say; the vLLM image also exists for arm64). On an Apple-silicon Mac the two small `RUN` steps
  run under emulation.
- The base model is not in the image. Add `--build-arg BAKE_BASE_MODEL=1` to bake it in
  (adds 2.0 GB for Gemma 3 1B or 8.6 GB for Gemma 3 4B; no Hugging Face call at start).

Check the image without a GPU (prints the vLLM command and exits; nothing is served):

```bash
docker run --rm --platform linux/amd64 -e SCRIBE_API_KEY=local-check -e SCRIBE_DRY_RUN=1 "$NAME:$TAG"
```

## 3. Push to the Verda registry

```bash
verda --agent registry show -o json 2>/dev/null        # read-only: registry_configured must be true
verda --agent registry push "$NAME:$TAG" -o json       # uploads the image, about 8.7 GB the first time
verda --agent registry tags "$NAME" -o json            # read-only: the tag must be listed
PROJECT_ID=$(verda --agent registry show -o json 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["project_id"])')
IMAGE="vccr.io/$PROJECT_ID/$NAME:$TAG"
echo "$IMAGE"
```

`verda --agent registry ls -o json` answered `registry_repo_not_found` (404) on 2026-11-14.
That may only mean the project registry is still empty, but a push has **not** been proven to
work with the saved credentials. If the push fails, recreate the credentials in the console.

## 4. Three things the CLI cannot do (console, once)

The CLI 1.10.0 has no command for any of these; the public API has
(`POST /v1/container-registry-credentials`, `POST /v1/secrets`, `GET /v1/serverless-compute-resources`).

1. **Registry credentials object for pulling the private image.** In the console create
   registry credentials of type Verda for `vccr.io`, and note the name you give it:
   ```bash
   REGISTRY_CREDS=vccr-sama        # the name you chose in the console
   ```
2. **The compute name.** Open *Containers → New deployment* and read the exact name of the
   GPU type you want (do not create anything there).
   ```bash
   COMPUTE=L40S                    # UNVERIFIED spelling; the existing deployments use "H100"
   ```
3. **Optional, only for variant B in section 5: a secret** holding the bearer key the container
   itself should demand.
   ```bash
   KEY_SECRET=sama-scribe-key      # the secret's name, not its value
   ```

## 5. Create the deployment (scale to zero)

Every flag is from `verda container create --help` (CLI 1.10.0).

**Variant A, recommended first: the platform key only.** Verda's gateway already requires
`Authorization: Bearer <inference key>` on every call. The container adds no second key.

```bash
verda --agent container create \
  --name "$NAME" \
  --image "$IMAGE" \
  --registry-creds "$REGISTRY_CREDS" \
  --compute "$COMPUTE" --compute-size 1 \
  --port 8000 --healthcheck-path /health --healthcheck-port 8000 \
  --env SCRIBE_ALLOW_NO_KEY=1 \
  --min-replicas 0 --max-replicas 1 \
  --concurrency 8 \
  --scale-down-delay 5m \
  --request-ttl 15m \
  --yes -o json
```

**Variant B: the container also checks a key.** The same command with
`--env-secret SCRIBE_API_KEY="$KEY_SECRET"` in place of `--env SCRIBE_ALLOW_NO_KEY=1`.
With a key set, the entrypoint loads `serve/guard.py` (`--middleware guard.BearerGuard`), which
requires the key on every path except `/health` and `/ping`. Without that middleware vLLM 0.29.0
would check the key only under `/v1`, `/v2`, `/inference` and `/cohere`, leaving `POST /invocations`
(which runs generation), `/tokenize`, `/metrics`, `/docs` and others open. The guard was tested
with a fake ASGI app, not inside a live vLLM (**UNVERIFIED** there). Variant B also works only
if the gateway forwards the `Authorization` header unchanged and the secret holds the same value
as the inference key; whether the header is forwarded is **UNVERIFIED**, and if it is not, every
call ends in `401`. Try A first. In variant A nothing in the container checks a key, so the
platform gateway is the only protection: do not expose the container's port any other way.

What the flags do:

| flag | why |
| --- | --- |
| `--min-replicas 0` | scale to zero: no replica, and no compute charge, while nothing is asked |
| `--max-replicas 1` | caps the bill at one GPU |
| `--concurrency 8` | equals `SCRIBE_MAX_NUM_SEQS` in `serve/entrypoint.sh`; keep the two equal |
| `--scale-down-delay 5m` | the CLI default; the replica stays (and is billed) five minutes after the last request |
| `--request-ttl 15m` | a queued request lives this long; the CLI default of 5m can be shorter than a first cold start |
| `--port 8000`, `/health` | vLLM listens on 8000; `/health` needs no key and answers 200 once the model is loaded |

Nothing else needs to be set: the image's entrypoint starts vLLM with the adapter as model
`pathway-scribe`, the base model as `gemma-base`, `HF_HOME=/data/hf` (the deployment's
500 GiB scratch disk, kept across scale-to-zero), 2,048 tokens of context and at most 8
sequences at once.

Add `--spot` for the interruptible price (about half). Not advised for a demo.

## 6. Test

```bash
BASE_URL=$(verda --agent container describe "$NAME" -o json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["endpoint_base_url"].rstrip("/"))')
echo "$BASE_URL"                                     # https://containers.datacrunch.io/sama-scribe-gemma

verda --agent container replicas "$NAME" -o json     # read-only: watch the replica start
```

The first request after idle starts a replica: image pull, then (first time only) the base
model download into `/data/hf`, then loading. Verda publishes no cold-start time, and none
was measured. A request waits in the queue for up to the request TTL.

```bash
curl -sS --max-time 900 "$BASE_URL/v1/models" -H "Authorization: Bearer $VERDA_INFERENCE_KEY"
```

The answer must list `gemma-base` and `pathway-scribe`. Then one synthetic note through the
client (prints the extraction, the confidence and the decision):

```bash
head -n 1 serve/fixtures/heldout-v1.jsonl > /tmp/one-note.jsonl
python3 serve/client.py --base-url "$BASE_URL" --jsonl /tmp/one-note.jsonl --timeout 900
```

And the smoke test: 50 held-out synthetic notes, exact match and latency percentiles, exit
status 0 only if the floors are met:

```bash
python3 serve/smoke_test.py --base-url "$BASE_URL" --concurrency 8 --timeout 900 \
  --out serve/smoke-report.json
echo "exit status: $?"
```

Both tools read the key from `SCRIBE_API_KEY` or, failing that, `VERDA_INFERENCE_KEY`. They
never print it. If the smoke test's exact match is near zero while `/v1/models` is fine, read
the *What can differ from training* list in `serve/README.md` before blaming the adapter.

## 7. Pause, resume, or just let it idle

```bash
verda --agent container scale "$NAME" --min-replicas 0 --yes --wait -o json   # idle at zero (already the case)
verda --agent container pause "$NAME" -o json                                  # stop serving entirely
verda --agent container resume "$NAME" -o json                                 # serve again
```

To hold one replica warm for a demo, and release it afterwards:

```bash
verda --agent container scale "$NAME" --min-replicas 1 --yes --wait -o json   # billed every minute from now
verda --agent container scale "$NAME" --min-replicas 0 --yes --wait -o json   # back to pay-per-use
```

## 8. Delete

```bash
verda --agent container delete "$NAME" --yes -o json           # the deployment (irreversible)
verda --agent registry delete "$NAME:$TAG" --yes -o json       # the pushed image (irreversible)
docker rmi "$NAME:$TAG"                                # the local image
```

Then remove the registry credentials object and the secret in the console if nothing else
uses them.

## Price, and what is billed when idle

Per GPU-hour, serverless, on-demand, in USD. Read on 2026-11-14 from
`verda --agent instance-types --gpu -o json` (`serverless_price`) and from
verda.com/serverless-containers.

| GPU | memory | on-demand | spot | on the public price list |
| --- | --- | --- | --- | --- |
| L40S | 48 GB | 2.22 | 1.11 | yes |
| RTX PRO 6000 | 96 GB | 3.12 | not read | yes |
| H100 | 80 GB | 5.765 | not read | yes |
| RTX 6000 Ada | 48 GB | 1.767 | 0.8833 | no, CLI catalogue only |
| A100 40GB | 40 GB | 1.869 | 0.9345 | no, CLI catalogue only |

**Use L40S at 2.22 USD per hour**: it is the cheapest GPU that both sources list for
serverless containers, and both Gemma 3 1B (2.0 GB of weights) and Gemma 3 4B (8.6 GB) fit
in 48 GB. The RTX 6000 Ada would be cheaper at 1.767 USD per hour if the console offers it
for containers; that is **UNVERIFIED**. Verda's tutorial also mentions a "General Compute
(24 GB VRAM)" type; its price was not found.

Billing, as Verda states it:

- You pay for every minute in which a replica did any work, including the time it spends
  starting and stopping. Charges appear in 10-minute blocks. One 10-minute block of one L40S
  replica is 2.22 × 10 / 60 = 0.37 USD.
- With `--min-replicas 0` there is no charge while idle ("No idle charges").
- With `--min-replicas 1` or more, those replicas are billed all the time.
- A replica stays up for the scale-down delay (5 minutes here) after the last request, and
  that time is billed.
- **Not stated by Verda and not verified:** what a paused deployment costs, whether the
  500 GiB scratch disk is charged while the deployment is idle or paused, and what registry
  storage costs for the pushed image.

## 9. What has been executed

Details with timestamps are in `runs/v2-serve.jsonl`; the spot prices of RTX PRO 6000 and H100 in
the price table were never read (an earlier version of this file showed half the on-demand price
there, review finding 22).

- **On the project's A100, outside this container (2026-11-14):** vLLM 0.29.0 and xgrammar 0.2.9
  in a venv, started through `serve/entrypoint.sh` (before `guard.py` existed) by
  `serve/smoke/tools/start_server.sh`, bound to 127.0.0.1, serving `unsloth/gemma-3-270m-it` at
  `23cf460f6bb16954176b3ddcc8d4f250501458a9` with the version-2 adapter as `pathway-scribe`. The
  smoke test ran 100 held-out synthetic notes with and without structured outputs: valid JSON 100
  and 98 of 100, exact match 0.22, p95 latency 1.80 s and 1.99 s (`serve/smoke/`, see its README).
  This exercised Gemma 3 LoRA loading, `--language-model-only`, the fixed xgrammar backend and
  log-probabilities under guided decoding. It did not exercise this image, Verda, the gateway or
  a cold start.

Local or read-only:

- Read-only Verda commands: `--help` pages, `container list`, `container describe` of one
  existing paused deployment, `registry show`, `registry ls`, `instance-types`.
- Docker Hub, Hugging Face, Verda docs and the vLLM v0.29.0 source and docs were read for the
  tag, digests, sizes, flags and behaviours quoted here.
- `docker build --check` on `serve/Dockerfile`: no warnings. A full build of the same
  Dockerfile on a small stand-in base image (`redis:7.2`, already on this machine) with a dummy
  adapter: built, the entrypoint dry run printed the vLLM command inside the container, a
  missing weights file failed the build. The real 8.7 GB base image was not pulled.
- `serve/convert_mlx_adapter.py` on the version-1 adapter: 182 modules, 364 tensors, every
  transposed matrix bit-identical to the source. The converted adapter was then loaded with
  PEFT 0.21.3 on the local Gemma 3 1B weights and compared with the answers the MLX run had
  stored; see `serve/README.md` for the count.
- `serve/schema.json` compiled with xgrammar 0.2.9 (the engine vLLM uses; v0.29.0 pins
  `>=0.2.1,<1.0.0`): all 4,456 dataset targets are accepted in both formats and all malformed
  test answers are rejected.
- Unit tests: `python3 -m unittest discover -s serve/tests`, against a fake HTTP server.

## 10. Open points to settle at first deployment

1. Compute name string for L40S, and whether a cheaper type is offered (section 4).
2. Name and creation of the registry credentials object; whether the saved `vccr.io`
   credentials can push (section 3).
3. CPU architecture of the GPU nodes (section 2).
4. Whether the gateway forwards `Authorization` to the container (section 5, variant B).
5. Cold-start time, and whether `--request-ttl 15m` is enough for the very first start.
6. vLLM v0.29.0 has run once on the project's A100 (section 9), which observed Gemma 3 LoRA
   loading (270M), `--language-model-only`, the fixed `xgrammar` backend and log-probabilities
   under guided decoding. Still not observed: this image, `guard.py` inside vLLM, and CUDA 13.0 on
   Verda's serverless nodes (the A100 machine reported driver 580.178.04, `runs/v2-gpu.jsonl`).
7. Cost of a paused deployment, of its scratch disk, and of registry storage.
