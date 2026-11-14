# Chibi Resume — camera-bag continuity

A working, dependency-free local frontend for one task: pack a camera, a
microphone and the correct charger; leave; come back; resume from the last
**user-confirmed** step. A historical sighting and a fresh lookalike cannot
complete the task or establish that the charger is yours.

**Qualification: local synthetic prototype.** No glasses, camera, microphone,
Meta assistant, Chibi host, account, private memory or cross-device connection
is established. The page labels this boundary visibly. Relay and Familiar are
disabled future capabilities, not working features.

## Run

From the repository root, with an existing Python installation:

```sh
python3 -m http.server 4179 --bind 127.0.0.1 --directory apps/meta-resume-web
```

Open `http://127.0.0.1:4179/`. Use `http://127.0.0.1:4179/?display=1` for the
compact display view. Stop the temporary preview with Ctrl-C when finished.
The app itself makes no API, font, image, telemetry or provider requests.
The HTTP origin is needed for ES modules; opening `index.html` directly as a
local file is not the supported launch path.

## Try the complete moment

1. **Confirm camera packed.** The dialog requires an explicit checked statement
   about the physical item, then confirmation. Escape cancels.
2. Do the same for the **microphone**. Two of three steps are now confirmed.
3. **Simulate an interruption.** The local task pauses without losing those
   confirmations. The old charger sighting is labelled historical, 11:00 in the
   synthetic fixture, from a previous capture generation.
4. **Look again & resume.** The fresh white charger is a different synthetic
   subject. The `observe` command is rejected. The app then calls `resume` with
   an empty evidence list and proposes checking the remaining charger step.
   It never converts the lookalike into evidence for the correct item.
5. **Confirm my charger packed** only after the explicit physical-check statement.
   User confirmation completes the task; neither sighting does.
6. **Correct** a previous confirmation to clear it and later confirmations while
   keeping the history. **Revoke** fixture observation capture to advance its
   generation and refuse late observations. Existing task confirmations remain.
   You can still pause and resume using local controls.

Progress is saved in `localStorage` for this origin only. Reloading restores a
bounded, validated synthetic command journal. Storage failure leaves an honest
in-memory-only notice. This is not durable Chibi memory, synchronization or a
production tenant boundary. Restart clears only this synthetic demo journal.

## Product and source reuse

This is a view for the existing **`meta-find-verify`** product, not another
solution-workspace scaffold or scanning engine. Its product metadata and tooling
remain owned by [PR64](https://github.com/SalesSquad/junction-pets/pull/64), read
at `390ecc16fb28a9397c0f515b33d252d482c75e5d`.

The existing [Lens service](../../services/meta-spatial/README.md) owns the
source-only inspect/find/verify contract. This frontend does not copy or replace
that service and does not call its synthetic candidate scorer. The private Chibi
host remains the future authority for identity, consent, capture admission,
memory, commands and effects.

The assignment is `META-EXEC-20261114/U1`, with exclusive ownership of
`apps/meta-resume-web/**`, based on Junction
`98d5a524d61e431ca36acd62b268ede343fc7fe2`. The coordinator owns the separate
shared [command schema](../../docs/meta-execution/resume-command.schema.json)
and [golden fixture](../../docs/meta-execution/golden-path.fixture.json) in the
planning branch; those links become available after the corresponding integration.

## State and command contract

The same deterministic handler is used by the visible controls and the optional
WebMCP proposal tool:

```json
{
  "schemaVersion": 1,
  "taskId": "00000000-0000-4000-8000-000000000100",
  "commandId": "00000000-0000-4000-8000-000000000606",
  "expectedRevision": 3,
  "operation": "resume",
  "payload": { "evidenceIds": [] }
}
```

| Operation | Exact payload | Meaning |
| --- | --- | --- |
| `confirmStep` | `{stepId}` | Visible local user confirmation of the next step |
| `interrupt` | `{}` | Retain progress and pause |
| `observe` | `{evidenceId}` | Resolve a reference through the frozen synthetic adapter |
| `resume` | `{evidenceIds}` | Propose the next unconfirmed step; complete nothing |
| `correctStep` | `{stepId}` | Invalidate this and later confirmations |
| `revokeEvidence` | `{evidenceId}` | Invalidate the referenced observation |

The transport never accepts a subject identity, capture generation, timestamp or
permission claim from the caller. A lookalike uses a different `subjectId` and
fails admission. A `subjectId` in an admitted observation means exact identity
verified by the fixture adapter, not visual similarity. Even admitted exact
identity evidence cannot complete a step.

Task revisions are separate from capture generation. `revokeCapture()` is an
explicit local adapter policy control, not a fabricated extra transport operation.
The fixture clock is fixed at **2026-11-14 12:00:00 UTC**, with a **300-second**
maximum evidence age. This demonstrates freshness and generation semantics;
it is not a live policy clock or real camera session.

Exact command fields, known operations, UUIDs, safe integer revisions, closed
payloads and bounded distinct evidence references are checked at runtime.
Identical command retries return the original applied revision and the current
snapshot; reusing an ID for different input fails. Changed task revisions fail.
Stored commands are replay-validated, bounded to 100 accepted commands.
Browser error labels are presentation reasons, not the eventual public HTTP API
mapping for the private Rust domain. This is a local reference adapter; Chibi
must independently enforce its own authenticated host rules before real use.

## Optional WebMCP

The implementation follows Meta's official
[WebMCP guide at the pinned web-app toolkit source](https://github.com/meta/meta-wearables-webapp/blob/fbf132997d036548ce090761a8bd4cf0afbda52a/plugins/meta-wearables-webapp/skills/ai-glasses-webapp-webmcp/SKILL.md).
The official documentation MCP `search_webapps_docs` was also actually queried
on 14 November 2026, with HTTP 200 / `isError=false`.

The two optional tools correspond to “Where did I stop?” and “Help me resume”:

- `chibi_resume_read_state` is read-only and reports actual local state.
- `chibi_resume_propose_next` accepts scalar `taskId`, `commandId` and
  `expectedRevision`; it calls `resume` with no identity evidence.

Registration is guarded independently on `document.modelContext`. A synchronous
throw, rejected thenable or missing API cannot take down the ordinary UI. No
polyfill is installed. Cancellation is honored and a page-lifetime AbortSignal
cleans up registration. The tools return current state and an explicit next
action; handled errors use `{error, message, next_action}`.

No tool can confirm a step, admit a camera observation, revoke permissions,
contact a person or perform an external action. The local handler also refuses
confirmation requests from its WebMCP caller. This is a UX boundary in a public
local demo, not a substitute for authenticated production authorization.
Native surface detection is labelled **unqualified**, not a successful glasses
or voice-availability claim.

## Verification and limits

One actual browser journey was attempted on the authorized Linux executor.
Chromium failed **before page load** with
`process_singleton_posix.cc: socket() failed: Operation not permitted (1)` and
SIGABRT. Its temporary loopback server was closed. The attached Browser connector
also returned “Browser access requires the originating browser context.” No
browser, Meta Display Simulator, 600×600 rendered layout or native WebMCP result
is claimed passed. No sandbox change, installation or new executor was used.

The fallback is one bounded deterministic scenario using the same state handler:

```sh
node apps/meta-resume-web/scenario.mjs
```

The scenario checks the two confirmations, rejected old/lookalike evidence,
empty-evidence proposal, retries/conflicts, revision refusal, assistant authority
limit, journal restoration, explicit completion, capture revoke, correction and
offline continuation. Its actual outcome is in `verification.json`.

The browser journey remains ready for an existing authorized runner with Node,
Playwright and Chromium already installed:

```sh
node apps/meta-resume-web/verify.mjs /tmp/chibi-resume-browser-check
```

`CHROMIUM_PATH` can select that runner's existing Chromium executable. This
single script checks the visible journey with keyboard confirmation, local
refresh continuity, a 600×600 viewport, cancellation, correction and revoke;
it writes two screenshots and a JSON receipt and always closes its own server.
It does not provision a browser or service, run a matrix, or contact a provider.

No physical-device, live capture, native assistant, host persistence,
cross-device or production qualification is implied by this source. The next
integration is the existing Chibi host command/evidence adapter and DAT capture
lane, under their owners, followed by one admitted real-device journey.
