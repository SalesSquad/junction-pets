# Fixed Stoa → NVIDIA drawing-observation recipe

This finite Node22+ developer recipe composes existing companion identities. Stoa binds a question to declared source/page regions; NVIDIA's existing exact-model transport observes those images and reviews its own output; Stoa validates the returned source, image digests and cited regions before returning an **unverified answer candidate** or abstaining.

It creates no Council, server, account, permission or live plugin. The existing benchmark workflow remains separate: drawing requests need no dummy benchmark rows. The default demo uses the existing authored worksheet, not sponsor drawings or drawing-QA quality evidence.

```sh
node services/stoa-nvidia/cli.mjs
node --test services/nemotron-vl/*.test.mjs
```

The default CLI sends zero requests and reads no credentials, including when a key happens to exist in the environment.

After preserving a clean exact commit on an allowed repository origin, a trusted operator may explicitly execute with a host-configured key:

```sh
node services/stoa-nvidia/cli.mjs --execute --source-commit FULL_HEAD_SHA
# Optional bounded drawing request JSON from standard input:
node services/stoa-nvidia/cli.mjs --execute --source-commit FULL_HEAD_SHA --stdin < cleared-request.json
```

Execution checks clean source/origin and all tracked runtime/fixture/identity files before and after the run. A changed checkout suppresses the result. Keys come only from the existing host environment after explicit execution/source checks; never supply credentials in JSON, command arguments or source. A missing key makes zero provider calls and returns a failed receipt.

## API

`services/nemotron-vl/index.mjs` exports:

- `validateDrawingRequest(request)`: bounded defensive data snapshot.
- `drawingRequestDigest(request)`: digest of that validated snapshot.
- `runDrawingObservation(request, {apiKey,fetchImpl})`: exact Nemotron model, two bounded requests (observation, same-model review), no tools or arbitrary URLs.
- `validateDrawingObservationResult(result, request)`: independent structural recheck at the composing boundary.

Request shape:

```json
{
  "question": "What does the supplied region visibly say?",
  "source": {"id":"drawing-1","sha256":"<64 lowercase hex>","page":1,"dataClass":"synthetic"},
  "regions": [{
    "id":"detail-1",
    "image":"data:image/png;base64,...",
    "imageSha256":"<actual supplied image SHA256>",
    "bounds":[0.1,0.2,0.5,0.7]
  }]
}
```

`dataClass` accepts only `synthetic`, `public`, or `cleared`. It is a caller declaration, never a permission check. Page is1–10000;1–2 regions; normalized page bounds satisfy0≤x0<x1≤1 and0≤y0<y1≤1. Images retain the NVIDIA runtime's PNG/JPEG header/size bounds and must match their byte digests. Complete image decoding and crop-to-document correspondence are not established by this validation.

`services/stoa-nvidia/index.mjs` exports `prepareStoaDrawingTask(request,{sourceCommit})`, `validateStoaDrawingTask(task)` and `runStoaNvidiaDrawing(task,{apiKey,fetchImpl,observe})`. The fixed task binds actor `junction.stoa`, recipient `junction.nvidia`, source commit and parent request digest. The recipe invokes NVIDIA's drawing entrypoint, then checks exact request/source/page/region/image bindings again. `observe` and `fetchImpl` are trusted-host/test injection points, never model-selected implementations. Injected execution is explicitly unqualified.

Receipts name both companion identities, versions, manifest/guidance digests and capabilities (`drawing-evidence-delegation` → `drawing-observation`). A candidate carries cited region bindings, uncertainties and output digest; abstention has a null answer. Neither result claims authenticated geometry, factual correctness, rights, host authority or company endorsement. Same-model review is not independent factual verification. No actual drawing/provider run has been qualified by the injected tests.

## Existing host integration

Production transport belongs to the existing Chibi/Council owner. Use the current `HostPolicy.decide`, `PetExecutor.invoke`, replay fence and `HostArtifactStore` parent-read/consumption seams. A key is not a grant. The host must minimize/authorize source images and recheck current consent, tenant, capability, source, budget and fence immediately before **each** provider call, for example in an injected authorized transport wrapper. This module does not authenticate those checks or issue host-signed receipts. Keep the34-capability offline registry offline.

Existing fixed endpoint, exact model, request/response/image/token/time limits, redirects-off transport, redaction, usage accounting and unknown cost treatment are shared with benchmark mode. There are no retries, fallback models, new daemons, image fetches or arbitrary tool execution. Provider outputs are interpretations; evaluate accuracy and cited-region support on cleared real drawings before calling this Stoa QA.
