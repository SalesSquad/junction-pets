# Verification — J26-PF-CALA-M2-20261114

Executor: existing Mac Mini Codex CLI workspace, restricted filesystem/network sandbox. Date: 2026-11-14. Base source: `a33f525171b6424d39dfc4c889b63e0fc5cb459e`; final source is the commit containing this record (resolve with `git log -1 -- solutions/cala-founder-opportunity-graph`). No external dispatch or service was used.

- `node --test solutions/cala-founder-opportunity-graph/test/core.test.mjs solutions/cala-founder-opportunity-graph/test/handler.test.mjs`: **23 passed, 0 failed, 0 skipped**. Includes duplicate rounds/filings, ISSUER exclusion and visibility, unknowns, stale evidence, collisions, circular/fake leads, contradictions, event/source dates, XSS escaping, prototype pollution, human-approved export, no secret/network/send path, and in-process static HTTP handler boundaries.
- `npm run build --prefix solutions/cala-founder-opportunity-graph`: **passed** (native module syntax and static asset presence).
- Socket HTTP smoke was **attempted and blocked**, not passed: `listen EPERM: operation not permitted 127.0.0.1`. The initial combined `npm test` reported 20 logic tests passed and the one HTTP test failed at socket creation, before any request. Do not classify this as a successful HTTP run. Socket test assertions are retained unchanged in `test/http.test.mjs` and remain part of `npm test`; separate `test:unit` and `test:http` commands make the boundary explicit. No unchanged socket retry or safeguard bypass.
- In-process handler tests exercise file serving, response headers, hostile Host denial, GET/HEAD boundary, write denial, traversal and private route refusal. This is **not** a listening-server smoke or browser observation.
- Installed runtime observed: **Node v26.13.0**, not Node 22. Uses only Node APIs available in 22 and native browser modules; exact Node 22 execution remains unverified.
- Desktop/390px styles and keyboard semantics were source-reviewed. **No browser screenshot, interactive DOM test, real screen-reader, Safari, download or viewport observation** was obtained. Browser dependencies were not present in this checkout. No dependencies were installed or remote browser service used.
- Cala provider: deliberately refused; no account/key/credit read or request. No live data, Atlas, outreach, recipient execution or investment outcome qualified.

Self-review: all authored product files are under the assigned solution directory. Static HTML uses no untrusted interpolation; dynamic strings pass HTML escaping and links pass HTTPS URL validation. Selection does not approve a candidate. Note edits revoke approval; goal rebuild clears reviews. Unsupported/ambiguous IDs cannot export. No root suites or CRACI dispatch.

Next local verification: in a socket-enabled authorized local session, `npm run test:http`, start the app, inspect desktop and 390px keyboard flow, then approve/download and inspect JSON. Next **external** gate remains approved Cala account + host-managed key and held-out live search/lookup → introspection → retrieval qualification.

## Preservation / commit blocker

`git add -- solutions/cala-founder-opportunity-graph` was refused by the sandbox: `Unable to create .../.git/index.lock: Operation not permitted`. The checkout's Git metadata is read-only in this session. No index or commit was created, and no alternate Git directory or remote executor was used to bypass that restriction. Source files are preserved in the assigned directory, untracked. HEAD remains the supplied base SHA; status cannot be called clean. Once Git writes are permitted, stage only this solution directory and create the requested local commit; do not push. The lifecycle done gate is read-only here; an unpushed/untracked result must not trigger rescue because the user explicitly prohibited all pushes.

## Independent coordinator qualification, same source bytes (2026-11-14)

After the isolated Codex writer exited, the authorized Mac Mini terminal outside its restricted code sandbox ran the existing **unmodified** tests with installed exact **Node v22.23.0**. The previously denied loopback socket opened under normal authorized test execution: all **24/24** tests passed, including the real HTTP smoke with GET assets, CSP, read-only methods, hostile Host refusal and path boundaries; zero failures/skips. The same Node 22 binary ran `build.mjs` successfully. This is a new distinct positive verification, **not a retroactive edit** of the worker sandbox's authentic earlier `EPERM` failure. Browser/voiceover screenshot, live Cala API and account/credit entitlement remain unverified; tests use fictional fixtures exclusively. The coordinator subsequently stages/commits only this owned product directory after separate source and scope review.

## Targeted P2 provenance repair — J26-PF-CALA-PROVENANCE-FIX-20261114

Repair baseline: clean `91bf2fc4f068f1ae5d8a3008f6891a9830b511e0`, branch `codex/j26-cala-founder-graph-20261114`. Independent Codex Plus read-only review reported one BLOCK P2: `artifact.sourceSha` named the initial base, not the product source. Resolution: explicit `baseSourceSha` plus canonical eight-file `productSourceDigest`, static metadata module, browser allowlist and fail-on-stale build. README defines exact scope and independent reproduction. No new product Git SHA is claimed; these repair bytes remain uncommitted for the coordinator. This record is author verification, not a new independent acceptance review.

On 2026-11-14 in the same restricted Mac Mini sandbox, Node **v26.13.0**:

- `npm run test:unit --prefix solutions/cala-founder-opportunity-graph`: **25/25 passed**, zero failures/skips. Exported digest equals current source bytes; independent manifest reconstruction matches; modifying each of the eight covered files in a temporary copy triggers the build verifier's stale-digest rejection. Existing provider refusal, approval, identity, XSS and Host/method/path/CSP assertions pass. In-process serving verifies the exact metadata digest is returned.
- `npm run build --prefix solutions/cala-founder-opportunity-graph`: **passed**, current static digest and syntax/assets checked without metadata rewriting.
- `npm run test:http --prefix solutions/cala-founder-opportunity-graph`: **blocked/failed at socket creation**, `listen EPERM: operation not permitted 127.0.0.1`, zero passed. Updated smoke includes the metadata browser module; no listening-server assertion was reached. No bypass or fake socket result.

Earlier sandbox EPERM and the coordinator's exact Node22 **24/24** pass above are preserved as distinct historical evidence, not evidence for these changed bytes. This repair has no fresh Node22/socket/browser qualification or independent re-review. No provider network, dependency, auth/approval policy or deployment change. Git staging/commit/push are explicitly reserved to the coordinator; none attempted for this repair.
