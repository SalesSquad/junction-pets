# Junction Mission Control: developer control plane

The 34 files in environments/ declare **desired** pet-specific Codex Cloud
environments. They are separate from the private Chibi runtime and from runtime
persona instructions. Currently **33** remain unprovisioned and **Aiven** has
owner-observed published/selectable evidence with an unresolved opaque Cloud
ID (`published-id-pending`). All 34 IDs remain null; source snapshots never
claim provider readiness or Chibi runtime authorization.

The ordinary data flow is:

1. node scripts/ops-build-status.mjs loads all 34 validated pet packages,
   reads the 34 cloud declarations and optional source-bound receipts.
2. It writes dist/mission-control/status.json. The private dashboard reads
   that file. It is a **snapshot**, not a live GitHub/Codex account query.
3. An authorized owner provisions and publishes a named Codex Cloud
   environment from the Codex Cloud UI. If Settings and the task picker show
   publication but no opaque environment ID is exposed, record
   `published-id-pending` with **null ID**, exact observed task URL, UTC owner
   recording time and pinned source/task SHA; it cannot enter Cloud dispatch.
   Only after independent provider ID readback may an integrator move a
   declaration toward an ID-backed state.
4. Each pet uses its own developer agent ID, one owned path and one task branch.
   A new isolated Codex Cloud task can run within a reusable published
   environment. An environment ID is not a promise of a permanent running VM.
5. A worker stores an immutable branch-and-package-bound receipt under
   receipts/<company>/<work-id>.<task-head-prefix>.json
   and asks an independent reviewer to check external provider evidence.
   This generator never upgrades an untrusted receipt to hosted certification.

node scripts/ops-work.mjs status prints an executable work queue.

The local source SHA is emitted only for a clean Git worktree. A dirty or
reconstructed worktree cannot be presented as a canonical GitHub source
revision. The hosted PR HEAD must be checked independently.

node scripts/ops-work.mjs claim --pet junction-aiven --agent junction-dev-aiven --work junction.aiven.cloud-bootstrap --source <exact-GitHub-SHA>
acquires a local lease under ignored dist/ops-claims. Use release --pet
junction-aiven --lease <ID> to release. An unexpired competing claim fails.
This provides protection only for agents **sharing one filesystem**, not
distributed coordination across 34 separate cloud sandboxes. Cross-cloud
mutual exclusion requires the remote Git ref expected-HEAD check plus the
integrator's task ownership register. Do not describe this CLI as distributed
lock infrastructure.

The short filesystem mutex uses an atomically published owner.json (owner UUID,
local PID, host, expiry). If the process crashes while holding this mutex,
never silently steal it. Inspect dist/ops-claims/<company>.lock/owner.json, then
use node scripts/ops-work.mjs reclaim-stale-lock --pet junction-aiven --owner
<exact-owner-uuid>. Recovery only succeeds when the local owner process is
dead, the lock has expired beyond its safety grace, and the owner UUID matches.
The durable pet work lease itself expires and can be reacquired with a new
source-bound task. A surviving process or remote-host lock requires manual
coordination, not an unsafe timeout bypass.

## Evidence contract

Each pet can retain several source-bound receipts. Example:

~~~json
{
  "schemaVersion": 2,
  "petSlug": "junction-aiven",
  "workId": "junction.aiven.sql-review",
  "taskHeadSha": "40 lowercase hexadecimal task-branch Git commit SHA",
  "packageSha256": "64 lowercase hexadecimal package digest",
  "recordedAt": "2026-11-12T18:00:00.000Z",
  "branch": "codex/junction-aiven-slice",
  "prUrl": "https://github.com/SalesSquad/junction-pets/pull/123",
  "prHeadSha": "same task-branch Git commit SHA",
  "checks": [
    {"name":"portable-ci","result":"pass","taskHeadSha":"same task-branch SHA","evidenceUrl":"https://example.org/actual-run"}
  ],
  "evaluation": {
    "executed": 6,
    "passed": 6,
    "model": "actual model and version",
    "taskHeadSha": "same task-branch SHA",
    "evidenceUrl": "https://example.org/actual-evaluation-run"
  }
}
~~~

The sample above is a schema example, not a real receipt. The file name must
be the exact workId followed by the first 12 characters of taskHeadSha.
Require an exact pet content digest and task/PR HEAD for every receipt;
do not conflate a branch's completion with an integration into main. Optional
integration evidence binds a distinct mainHeadSha. Multiple branches for one
pet are retained, and older failures cannot be cherry-picked away. If the
current pet digest differs, a receipt is stale even if its Git commit matches.
Failed checks or model evaluations always create an explicit blocker.
Actual source and provider verification must occur independently. Do not place
secrets, bearer URLs, personal information or private Chibi data in any receipt.

## Per-pet Plugin Creator registration (private, source-bound)

Generated plugin packages live under plugins/junction-<company>/, and do not
prove installation. For each plugin whose actual USER/PRIVATE registration is
observed through the provider, create exactly one optional registration
receipt at ops/plugin-registrations/<company>.json:

~~~json
{
  "schemaVersion": 1,
  "petSlug": "junction-mariadb",
  "pluginName": "junction-mariadb",
  "provider": "chatgpt-plugin-creator",
  "pluginId": "exact-opaque-plugin-ID-from-provider",
  "pluginUrl": "https://chatgpt.com/plugins/actual-private-route",
  "releaseId": "exact-release-ID-from-provider",
  "visibility": "USER_PRIVATE",
  "observedAt": "2026-11-12T20:00:00.000Z",
  "sourceFiles": {
    "plugins/junction-mariadb/plugin.json": "SHA256-of-exact-file-bytes",
    "plugins/junction-mariadb/skills/junction-mariadb-companion/SKILL.md": "SHA256-of-exact-file-bytes",
    "plugins/junction-mariadb/assets/source-manifest.json": "SHA256-of-exact-file-bytes"
  },
  "sourceBundleSha256": "SHA256-of-canonical-JSON-sourceFiles-map",
  "evidenceUrl": "https://chatgpt.com/plugins/actual-private-route"
}
~~~

The example is **not** a real registration. The exported helper
pluginSourceFingerprint(root,pet) in ops/registry.mjs computes sourceFiles and
sourceBundleSha256 from the three actual on-disk files. Never invent digests.
Copy the exact plugin ID, URL, release ID and owner-private scope only from
actual provider readback; never place auth query strings or bearer links here.

The status generator distinguishes:

- source-present: three files exist and their plugin/provenance identity matches
  the pet package; **no installation claim**.
- registered-source-matched-reported: the private receipt matches all exact
  source bytes. This is still **reported provider evidence, not independent
  live verification**. ID and release are displayed with that label.
- stale-registration or malformed-registration: no plugin ID is treated as
  current; a clear blocker asks for renewed source-bound registration evidence.
- not-registered: there is no private receipt.

Never publish the owner-private control plane or these registration receipts
in a public Junction submission bundle.

dist/mission-control is operational output and **must not** be published with
dist/site, Chibi Maker packages or the Junction submission artifact. The
control plane can be privately hosted later with explicit deployment authority.

## Aiven Cloud publication — owner observation, not a readiness grant

At source `b8895789e12937be65cd5b49c9705cd9d9716c30`, the owner observed
`junction-aiven` as **published/selectable** in Codex Cloud Settings and task
picker. An exact fresh [Codex task](https://chatgpt.com/local/6af63cbd-674c-8191-83e7-d7be6dd6e040)
fetched that SHA, reported a clean source tree and passed **21/21 submission-gate
checks**. The registry timestamp `2026-11-12T22:32:40.000Z` is when we recorded
the owner's handoff, **not** a provider-issued event timestamp. No separate
opaque Cloud environment ID was exposed. The task URL is evidence of task
execution, not the immutable environment-ID receipt. The 21 tests are NOT
model evaluations, Chibi host/recipient acceptance, or verified hosted CI.

The source SHA is pinned independently in the manifest and task evidence. When
Mission Control is generated for a different/unknown source SHA, the Aiven
publication observation remains amber `published-id-pending`, but its 21
historical task checks become `stale-source` and do not qualify current CI,
model evaluation or Cloud readiness. Editable
manifest/owner readback never becomes independently provider-attested readiness.
No new credentials were used to create these records.

## Optional Codex CLI dispatch planning

node scripts/ops-cloud-dispatch.mjs --pet junction-aiven --branch
codex/junction-aiven-guidance --source <exact-clean-HEAD> --profile plus
only generates an argv array and an isolated task prompt. It does not run
Codex Cloud, provision an environment, access a Mac or change accounts.
All 34 manifests still make it fail, including the published-ID-pending
Aiven declaration, because no independent provider IDs have been recorded. Even after the owner records a verified
published environment, the plan clearly says a fresh provider and remote
HEAD check is required before executing through an already authorized CLI.
