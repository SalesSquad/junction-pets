# Lens Guide delivery — LENS-GUIDE-20261115

## Source and scope

Source commit: `f65ae75047977ca62b7f7c6fafa0f9eba50ebf8f`.
Tree: `1352a236038123843ea5a3a05f2abd2562a4d638`.
Branch: `codex/meta-lens-guide-20261115`.
Review: [PR222](https://github.com/SalesSquad/junction-pets/pull/222).
Ownership claim: [issue80comment6885724319](https://github.com/SalesSquad/junction-pets/issues/80#issuecomment-6885724319).

The source implements a local teach/request/capture/confirm/resume flow, a
ten-item notebook, opt-in browser persistence, selected ScreenshotContext note
conversion, optional proposal-only WebMCP, and phone AR surface markers scoped
to the original live world. The native notebook lasts for the view's lifetime.
Browser and native notebooks are separate; neither silently becomes the private
Chibi identity, authorization or durable-memory host.

PR142's earlier ARKit capture slice was integrated at
`a2d73f70b6e302866e262535fb026fcbfa4c2f4c`; PR222 starts there. Existing model,
training, retrieval, CRACI and DATMockApp work is preserved. This delivery adds
no SAM/Nemotron inference, new training, paid provider call or deployment.

The workspace was a partial source materialization, not a git checkout.
`source-binding.json` records SHA-256 and Git blob identities for all 25 owned
source/document paths, independently matched to the authenticated GitHub tree.
The execution receipt binds its 16 browser/HTTP inputs separately. Later
evidence-only commits do not change these executable bytes.

## Actual executed checks

The focused integrated run completed on **14 November 2026, 23:46:04 UTC**,
in the ChatGPT Linux workspace using **Node v24.22.1**:

```sh
node --test apps/meta-resume-web/guide/guide-core.test.mjs \
  apps/meta-resume-web/guide/context-handoff.test.mjs \
  apps/meta-resume-web/guide/guide-ui-boundaries.test.mjs \
  services/meta-spatial/guide-server.test.mjs
```

**25 passed, 0 failed, 0 skipped.** Raw stdout and empty stderr are retained in
`checks.stdout.txt` and `checks.stderr.txt`; `checks.json` records the command,
times, executor, digests and limits. Four changed JavaScript entry modules also
passed syntax checks. The native runner passed Python AST parsing only.

The checks exercise copied image bytes and SHA-256 binding, asynchronous
revocation/task/forget races, request expiry, historical-only restoration,
strict handoff conversion, storage failures and stale writers, revoked retained
assistant handles, fresh-page defaults, and the actual fixed HTTP route/origin
boundary. Storage and DOM checks use synthetic inputs and a minimal DOM contract.
The HTTP server and client run in the same executor process. These checks do not
establish browser rendering, camera behavior or physical object identity.

## Independent review and retained findings

One read-only reviewer checked the material consent/provenance changes. Repairs
were returned to the source owner and only affected deltas were reviewed again.
The final browser privacy delta and native marker/coordinator delta were clear
of remaining P1/P2 findings. The reviewer did not execute tests or compile Apple
code; the runtime evidence above belongs to the integrating executor.

The actual findings and repairs were:

1. Native image review consent could survive a new accepted image. It now resets
   on request ID, accepted-image digest and selected target.
2. A new packing task could retain previous completion marks. New tasks clear
   them; resuming the same paused task keeps them.
3. Permission completion/dismissal could leave pending state or restart a
   dismissed view. A synchronous ticket, presented lifetime and post-await
   application-state check now fence camera startup.
4. A failed replacement raycast could preserve the previous pending marker.
   Replacement now clears both the pending point and visible marker first.
5. The nested native gesture coordinator lacked explicit main-actor isolation.
   Its initializer and callback are now `@MainActor`.
6. Browser deletion errors could be presented as successful erasure. Epoch
   write, data removal and both readbacks now execute independently; uncertain
   deletion and incomplete cross-tab invalidation have distinct messages.
7. Saving opt-out became inaccessible after a storage failure, and subsequent
   single-item deletion could hide that persistent data remained. Opt-out stays
   available and the retained-data failure remains visible.
8. Assistant sharing needed its own default-off choice. Registration, every
   invocation, revocation and retained callbacks now enforce that choice;
   teardown aborts the lifetime and unregisters the tools.

Final reviewed privacy hashes are listed in `source-binding.json`: app
`d8d281889ce4c517feaa130d7876c71779acc6a8a64903e621c08a4fbe99eaa6`,
storage `1533802988d0e02d6f8860496f600dad04a9ad4fbd72480bd0d93054e896b9d3`,
WebMCP `fd4a748148aa4d9aa2ddf829e51dd698f774db60ca4b7697353b7550bf50cdf5`,
index `c182f583d40f46c31eadcb0633d0c5e6dbed1173e6cf073573fe3ff6a9766f8c`,
and UI boundary tests
`baef4ef62abe0039e7a2f4238960804860d3592e7e3e5a0a5ab847a875532b1f`.
Native marker repair binds model
`aff2594ac75a8be5345f5dce419a24976f0eecc10fc45055ef978ed034d4a838`;
the coordinator repair binds view
`f390e660e02c6115ef0d975e480a10a73f0226942e6f0a9abc5154bb816bbec4`.

## Native execution: blocked before compilation

`native-attempt01.json` is the original failed execution record for earlier
milestone `ceeaadf92eb656cbcc3bdd55c8ee2be216789f49`. At **23:25:32 UTC** the
MacBook Pro reported **18.679 GiB** free against its existing **20 GiB** native
reserve. The runner exited before launching any compiler: `phases` is empty.
No simulator, camera or physical device started. This record has not been
rewritten to refer to the later source.

Later admission observations were MBP 17.426 GiB, Air 7.05 GiB and Mini 20.54 GiB;
the Mini's existing native reserve is 60 GiB. These are dated observations, not
current disk readings. No reserve was lowered and no other owner's data was
removed. There is no Swift compiler in the Linux executor.

All eleven final native compilation inputs were matched to the GitHub source
tree and copied into a separate continuation bundle on the verified MBP:

- `~/Developer/lens-guide-native-20261115-final-source.json`
- Source commit `f65ae75047977ca62b7f7c6fafa0f9eba50ebf8f`
- Bundle SHA-256 `a76c05f3b12cccbb16bc00760d8aadd6e02d89e60ec91c32cd1bae7d74afd7af`
- Existing runner `~/Developer/lens-guide-native-20261115-check.py`
- Runner SHA-256 `53ee3fc416d3394e717f2f8e1c5f956d957a713dadd1e9c0356a8b174668fe27`

The copied bundle and its per-file SHA-256/Git blob bindings were read back and
validated on the Mac. **The final source has not been compiled.** The source
runner is also committed at `apps/meta-lens-apple/scripts/verify-guide-native.py`.

Next native owner: the existing Meta/native lane after host operations admits
one verified Mac meeting its unchanged reserve. Use the named-session helper,
the final bundle and a new output directory; preserve attempt01. The next check
is Core → ARKit → UI module emission and the synthetic Swift state executable.
Physical iPhone capture/raycast and actual glasses qualification remain separate.

The named Mac session `lens-guide-native-20261115` and the two source bundles
are retained for that blocked continuation. A final session-status read stalled
in the remote connection and was abandoned; closure is not claimed. The prior
compiler attempt had already ended before compilation. The Mac done gate
reported `git: false` for its materialized source directory; GitHub preservation
is established by the source/blob readback above, not by a clean-checkout claim.

## Browser execution: infrastructure blocked

No rendered screenshot or real-browser camera pass was produced:

- Installed Playwright/Chromium failed before a page opened with
  `process_singleton_posix.cc:297 socket() failed: Operation not permitted (1)`.
- The connected-browser tool required an originating browser context which
  this session did not have.
- The permitted cloud-browser fallback could not reach the temporary preview:
  `net::ERR_CONNECTION_REFUSED`. Separate executor/browser sessions did not share
  its loopback listener.

These are retained observations from the attempted tools, not fabricated raw
browser logs or successful product assertions. No sandbox setting, permission,
browser profile or network policy was weakened. The temporary server was stopped.

The actual existing CRACI workflow was inspected at the source base. Its
`meta-browser` workload calls `apps/meta-resume-web/verify.mjs` for the prior
Resume journey; it does not qualify the new Guide. No unchanged browser suite
was dispatched as substitute evidence. The CRACI owner retains that harness
and budget admission. Next browser owner: the Meta UI lane, using an admitted
browser on the same origin as the Guide server for the real camera, responsive
layout, storage and assistant-surface checks.

## Delivery state and boundaries

The source is complete and reviewable in PR222. The PR remains draft with
concrete native/browser qualification gaps; it is not represented as merged,
installed, signed, deployed or device-qualified. Portfolio PR Recovery remains
the sole integrator. No additional integration automation was created.

Historical memory does not establish current presence. A surface point is a
phone-world estimate, not glasses pose or verified identity. User confirmation
does not manufacture a private-host receipt. The selected ScreenshotContext
adapter uses note/export-time metadata only; no personal screenshot archive,
OCR corpus, browser session database or private implementation was copied.
