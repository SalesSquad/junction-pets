# Task observation: SAM 3.1 → Nemotron → advisory Resume card

This is a runnable developer integration for Chibi Continuity. It adds a bounded
image/track interpretation to the existing packing journey. The private Chibi
host remains the authority for identity, consent, evidence and durable task
commands; this loopback development server does not impersonate that host.

## Run the complete synthetic journey

From the repository root, with Node 22 or later:

```sh
node services/meta-spatial/observation-server.mjs
```

Open `http://127.0.0.1:8787`. Confirm camera and microphone, interrupt, resume,
then select **Use synthetic sample** and **Analyze this moment**. The card shows
the original illustrative scene, three candidate boxes and an advisory question.
Confirmations still require the existing visible checkbox/button flow.

Synthetic pixels, rectangular example masks and deterministic model responses
are explicitly labelled. This is an actual source/API/UI integration, not an
actual SAM inference, Nemotron inference, camera capture or physical identity
measurement. Images and proposals stay in page memory; the existing local task
journal stores only its existing commands.

## Real model profiles

```sh
# Existing approved hosted key supplied by the trusted launcher; never put it in the UI.
node services/meta-spatial/observation-server.mjs --mode hosted

# Existing local vLLM server, same host or an already authorized loopback tunnel.
node services/meta-spatial/observation-server.mjs --mode local
```

Hosted mode reads only `NVIDIA_API_KEY` when explicitly selected and uses the
existing fixed `https://integrate.api.nvidia.com/v1/chat/completions` endpoint and
`nvidia/nemotron-3.5-super-vl-120b-a12b` model. Local mode uses only
`http://127.0.0.1:18765/v1/chat/completions`, alias `nemotron-3.5-super-vl`, one image,
at most 640×640 pixels / 512 KiB, a 256-token answer and thinking disabled. It
does not forward a hosted API key. A returned alias does not attest checkpoint
bytes: the receipt identifies the **requested** NVFP4 revision and explicitly
marks weight attestation unverified.

The server starts no GPU, downloads no checkpoint and creates no remote service.
There are at most 20 interpretation attempts per process, one in-flight request,
fixed destinations, no redirects, bounded JSON/image/response sizes, CSRF and
exact-origin checks. Restarting a process is not a way to bypass provider quotas.
Real hosted/local mode must use the owner's existing authorized account, data
and capacity. This source delivery does not attest their current availability.

## SAM worker and portable handoff

The separate [Agents SAM worker PR122](https://github.com/SalesSquad/agents/pull/122),
source `53c0b4ba00886f3707a47051eefb65e8f5708d61`, owns
`cloud-services/verda/experiments/meta-sam31/`. Its CLI accepts bounded relative
frame paths with byte hashes, sizes and RFC3339 timestamps. It uses the pinned
official multiplex predictor and publishes only the final frame of the supplied
causal prefix. It does not use later frames to qualify an earlier live claim.

The common [JSON schema](observation.schema.json) is copied by digest into that
worker. Its SHA-256 is
`74c24c9da840a8cf6cd59df8a8dc3732e0e22023a89ea67164418e2b33927091`.
Expected checkpoint: `facebook/sam3.1@daa63191845a41281374e725f4c9e51c7a824460`,
`sam3.1_multiplex.pt`, SHA-256
`0567debeec80ba4ac6369540c6c248025283cb3ff2b92827509e57e2b3541cb6`.

Create the browser bundle directly from a completed worker output:

```sh
node services/meta-spatial/observation-bundle.mjs \
  --worker-output /path/to/owned/worker-output \
  --frame /path/to/owned/final-frame.png --output /path/to/new/bundle.json

# Or select an actual worker crop, checking its manifest, bytes and dimensions:
node services/meta-spatial/observation-bundle.mjs \
  --worker-output /path/to/owned/worker-output \
  --track p0-o1 --output /path/to/new/crop-bundle.json
```

The exporter refuses existing output files and checks the completed MODEL receipt
and artifact digests. Those checks establish supplied-file consistency, not a
signed runtime identity. It preserves timestamps and evidence mode unchanged.

Import a JSON bundle with exactly `{observation,image}` into the browser. The
observation is the worker envelope. `image` has exactly `kind`, `dataUrl`,
`sha256`, and `trackId`. For a whole-frame PNG/JPEG, `kind="frame"`, `trackId=null`
and the actual decoded byte hash must equal `observation.frame.sha256`. For a
crop, `kind="crop"`, `trackId` selects one track and the byte hash/dimensions must
match its crop descriptor. Remote image URLs and executable SVG are rejected.
The whole bundle is at most 2 MiB; image bytes at most 1 MiB before the stricter
local profile limit. The worker artifact manifest names files within its owned
output directory; the public envelope itself exposes no host filesystem paths.

Current developer-shell capture is the visible fixture session/generation, not
a real DAT session. Imported evidence must match that session and be no older
than 30 seconds at interpretation time. Historical/offline worker output is not
silently relabelled fresh. A production composition supplies current capture and
task context through the private host and its real recorder.

## Host composition and result

`runTaskObservation` in `services/nemotron-vl/task-observation.mjs` accepts one
strict request: `schemaVersion`, `task`, `observation`, `image`. Task contains
`taskId`, `revision`, `status`, `nextStep:{stepId,label}`. Supply a trusted current
context callback, invoked both before and after awaiting the model. It returns
current task/revision, captureEnabled, sessionId, captureGeneration and nowMs.
A revoked or changed context discards the result. A complete production host
must implement its existing admission/lease rules; the development shell uses
only declared local fixture state and reports `hostVerification:not-attested`.

Every result binds nine fields: taskId, expectedRevision, episodeId, sessionId,
captureGeneration, frameSha256, frameIndex, runId and trackGeneration. The UI
checks them again and cancels late responses on task change, reset or revoke.
Model text is displayed as text, never inserted as HTML. The output carries
`physicalIdentityVerified:false` and `taskCompletionAuthorized:false`; it is
not a command for `resume-command.schema.json`. A SAM track cannot become the
private H1 `Observation.subjectId` without current trusted identity resolution.

`createObservationGate` avoids repeat interpretation of identical frames and
stable tracks, and notices task changes, tracking restarts, appearance/movement
and bounded freshness. Its commit refuses an older completion after a newer
frame/revision/generation. This policy reduces unnecessary VLM calls; it does
not claim measured GPU savings or turn visual similarity into verified identity.

## Focused checks

```sh
node --test services/nemotron-vl/task-observation.test.mjs
node --test apps/meta-resume-web/observation-client.test.mjs
node apps/meta-resume-web/verify.mjs /tmp/meta-observation-browser
```

The first two check image/causal binding, fixed provider profiles, ungrounded
output, revoked/late results, out-of-order completion and actual loopback HTTP
with CSRF. The last runs one existing browser journey including the new
observation round, when an approved Playwright/Chromium executor is available.
Do not reinterpret a browser startup failure as product behavior or bypass OS
restrictions. No new workflow, CI matrix or scheduler is installed here.
