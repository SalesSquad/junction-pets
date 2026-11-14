# J26-ESPOO-WORKBASE-REUSE-20261114 — writer handoff

## Source and ownership

- ProofMatch base/current HEAD: `92d3f48efe94c9547a77963371f49102bee4fb61`.
  Branch: `codex/j26-espoo-workbase-reuse-20261114`. Initially clean;
  the author handed the source delta to the coordinator for commit and PR.
- Read-only Workbase source: `4c5ce6e2edb41b83360dd7d0227da9ded06a566b`.
  Both supplied SHAs were verified locally. Workbase remained clean after
  inspection. No fresh remote PR/main status is asserted by this writer.
- Sole writer scope: `solutions/espoo-proofmatch/**`. No root/shared files,
  other solutions, Workbase files, Git refs, dependencies or lockfiles changed.
  No workers, commit, push, PR, merge, deployment or communications launched.
- Source inspection covered actual Rust skill matching and models, evidence
  renderer, reciprocal ranking architecture, invite SQL/worker page and
  CandidateBrowser evidence/caution UX. Exact mapping is in `WORKBASE_REUSE.md`.

## Delivered slice

- Validated symmetric graph with exact/transferable/unknown evidence, direct
  TypeScript→JavaScript example, required-count and weighted preferred credit,
  structured reason/caution codes and explicit lack of verification.
- Five fictional candidates remain visible/selectable in fixture order. Ren
  has no portfolio or preference; Ari demonstrates the transfer path. Explicit
  candidate topic interests provide two-sided event context without filtering.
- Separate 15-minute event proposal lifecycle: employer proposes, intended
  candidate accepts/declines, either intended party cancels. Pending/accepted
  hold times across roles for both parties; decline/cancel release them.
  Active duplicate pairs, invalid states/actors, non-grid slots and conflicting
  ledgers fail validation. Outputs are cloned and deeply frozen.
- UI shows source material, unknowns, human-authored questions, required versus
  preferred skills and separate labelled party controls with visible statuses.
  No visible person score or aptitude ranking. Fictional event: 15 Nov 2026.
- New modules are in the server allowlist and v2 offline shell asset list.
  Known old v1 cache cleanup is scoped; proposals remain in tab memory only.
- Legacy matcher and its 18 tests are unchanged. Its collapsed benchmark is
  explicitly only 2 illustrative cases, not a v2 quality result.

## Focused verification — current working-tree bytes

Executor: local Mac mini restricted Codex sandbox, Node **v26.13.0**, darwin arm64.
Observed **14 November 2026, approximately 02:40 UTC**. These results bind to the author source bytes; the coordinator rechecks the final
committed HEAD. No deployment or release is implied.

```sh
node --test solutions/espoo-proofmatch/skill-graph.test.mjs solutions/espoo-proofmatch/event-meetings.test.mjs solutions/espoo-proofmatch/matcher.test.mjs
```

**PASS: 39 tests, 0 failures, 0 skipped**: 11 skill-graph tests, 10 event-meeting
tests, 18 preserved matcher tests. Includes related credit, strongest/tied paths,
no transitive inference, no portfolio, unknown preference, self-declared source
forms, external-verification rejection, malformed/nonfinite/oversized inputs,
permissions, transitions, pending/accepted conflicts, cross-role candidate and
employer collisions, terminal time release and immutable input/output snapshots.
The legacy fixture result remains 2/2 fixed labels versus keyword 0/2, with no
claim about real people, v2 matching quality or hiring validity.

`node --check` executed for **all 12 local `.mjs`/`.js` files: PASS**, including
all changed/new JavaScript. `git diff --check`: PASS. Changed paths were checked
against the exclusive owned scope; no dependency or lockfile edits.

HTTP attempt:

```sh
PORT=4193 node solutions/espoo-proofmatch/serve.mjs
```

**AUTHOR SANDBOX BLOCKED:** `listen EPERM` on `127.0.0.1:4193`; no workaround or persistent server.

**COORDINATOR HOST SMOKE VERIFIED separately** on the authorized Mac Mini
(Node v26.13.0, 14 Nov 2026 around 04:37 EET): temporary `PORT=4194`
localhost server returned HTTP 200 for `/`, `/app.mjs`, `/skill-graph.mjs`,
`/demo-validation.mjs`, `/event-meetings.mjs`, and `/sw.js`; HTTP 404 for
`/AGENTS.md` and `/WORKBASE_REUSE.md`; POST `/` was HTTP 405. A shell EXIT
trap stopped the task server. These are status-code and allowlist observations,
not browser presentation/media-type or offline-worker qualification.

**Still unverified for v2:** interactive Safari/mobile rendering, responsive
layout, keyboard/screen-reader behavior and service-worker offline reload.
No full monorepo tests, new installs, external reviewers or provider tests ran.

The installed `verify-change` helper path was absent; the explicitly requested
focused commands above were used. newcomp's relocated read-only component
search returned no conversation component; its accessibility guide informed the
existing semantic/native-control approach. No newcomp source was modified.

## Exact changed paths

All paths below have prefix `solutions/espoo-proofmatch/`:

- New: `demo-validation.mjs`, `skill-graph.mjs`, `skill-graph.test.mjs`,
  `event-meetings.mjs`, `event-meetings.test.mjs`, `WORKBASE_REUSE.md`.
- Updated: `app.mjs`, `data.mjs`, `index.html`, `styles.css`, `serve.mjs`, `sw.js`,
  `benchmark.mjs`, `solution.json`, `README.md`, `ARCHITECTURE.md`, `PROGRESS.md`.
- Preserved unchanged: `AGENTS.md`, `matcher.mjs`, `matcher.test.mjs`.

## Claimed scope, deficiencies and next owner

Claimed: a private synthetic deterministic v2 product implementation with
focused Node checks. Workbase is pre-existing PRIVATE IP; translation/adaptation
does not make it event-original or automatically contest-eligible. No contest
clearance, public redistribution license, production, municipal endorsement,
real actor authentication, real consent, signed audit, calendar freshness,
external booking, Workbase application or provider execution is claimed.

Known demo limits: authored one-edge transfer graph; manipulable self-provided
material; Ren's authored availability has no common role time; memory-only
caller-supplied ledger; no cross-tab/transactional controls; one operator can
switch simulated parties. Browser/offline/accessibility evidence is missing.

Coordinator follows through with task-branch PR, confirming the final source
SHA and scope. Next acceptance: actual browser/keyboard flow and a source-rights
review before any public contest submission; competition eligibility remains
uncleared. No deployment or production connection is authorized by this record.
