# Cloud developer playbook

Purpose: continue any of 34 company lanes from private GitHub source and evidence,
without depending on the original chat or a permanent VM. Read root/ops
`AGENTS.md`, [architecture](../ARCHITECTURE.md), the
[worker brief](COMPANY_WORKER_BRIEF.md), and only the assigned
[continuation record](DEVELOPER_CONTINUITY.md).

## Identities are not execution

| Concept | Convention / record | Meaning |
| --- | --- | --- |
| Companion | `pets/mariadb/`, `junction-mariadb` | Versioned user-facing content |
| Developer owner | `junction-dev-mariadb` | Stable logical responsibility |
| Desired environment | `junction-mariadb`, `ops/environments/mariadb.json` | Reusable configuration, subject to fresh provider checks |
| Finite task | Work ID + actual native/Cloud execution identity | One admitted source-bound job |
| Task branch | `codex/junction-mariadb-<slice>` | Isolated changes, expected remote HEAD |
| Continuation | Progress record + original PR/test/review evidence | Released task and next unstarted proposal |

The older code/test/review roster describes 102 planned roles, not concurrent
jobs. Allocate only verified capacity, initially one or two disjoint writers
and an integrator/reviewer. Increase based on actual delivery, integration,
rework and available quota. Independent review must be independent of authorship.

## Admit a task

1. Read `node scripts/ops-development-progress.mjs --pet <company>`.
   The reader is offline and source-local; follow evidence URLs and resolve
   authenticated current GitHub main, task branch and competing PR heads.
2. Inspect surviving work/claims and dirty or unpushed changes. Do not take an
   overlapping company lease. Preserve existing work even if its process ended.
3. Assign work ID, immutable base SHA/tree, logical owner, actual executor,
   expected remote branch HEAD, disjoint paths, feature, checks and budget.
4. For Cloud, verify the selected existing account, private repository access,
   published/selectable environment and observed immutable provider ID.
   A desired name, historical ID or unrelated task URL is insufficient.
5. Create an isolated task worktree and use [COMPANY_WORKER_BRIEF.md](COMPANY_WORKER_BRIEF.md).
   Send stable implementation/test hashes for independent review while final
   checks run. Do not launch unbounded swarms from a manifest list.

Each company writer owns only its assigned `pets/<company>/**`,
`tests/pet-<company>.test.mjs`, and three generated plugin outputs. The
integrator owns shared files and the accepted progress ledger. Runtime persona
files cannot grant developer or Chibi permissions.

## Cloud configuration versus current availability

Historical [13 November provisioning evidence](../ops/cloud-provisioning-20261113.json)
records 34 Pro/Legacy environments. Those IDs were not selectable in a later
new-Cloud picker; actual early source tasks used separately verified
`chibi-marketplace-cloud`. Do not substitute one identity for the other.
The [dated original queue](../ops/development-queue-20261113.json) remains intact;
the current accepted-task register is [development progress](../ops/development-progress.json).

Maintaining a dedicated environment requires an already authorized management
surface, correct private repository, supported Node setup and independent
provider readback. Record actual IDs/selectability and exact-source smoke
results through the registry owner. Missing IDs remain unknown or
`published-id-pending`; no guessed identifier or fabricated ready state.

`scripts/ops-cloud-dispatch.mjs` only makes an inspectable dry-run plan.
It has no authenticated create/list/publish/execute authority. An environment
is reusable configuration; a task is an isolated, time-bounded workspace.

Normal supported session refresh does not authorize token/session export,
permission bypass, switching accounts to evade quotas or new paid executors.
Stop for mandatory sign-in/approval rather than circumventing it. Keep private
code only within the owner's authorized runner/provider scope.

## Source-to-PR cycle

1. Capture clean baseline and genuine failing new regression where applicable.
2. Implement a bounded slice; version its changed content, retain six authored
   eval definitions and use unchanged producers for generated outputs.
3. Run the brief's baseline/final gates. For shared control-plane/collaboration
   changes also run Wave 2; for Council changes use its isolated Python suite.
4. Publish only the task branch, with expected-old-HEAD and no force push.
   Fetch the actual canonical commit; verify source bytes/tree and rerun decisive
   gates on clean final HEAD. A same-tree different local SHA is not that receipt.
5. Independent reviewer checks exact final bytes. Integrator combines disjoint
   changes, verifies unchanged/shared scope and reruns combined gates before an
   owner-authorized merge. Do not treat hosted checks as green when absent.
6. Preserve source, raw failures/success logs and compact PR handoff. Release
   finite ownership; retain clean worktree while integration still needs it.
   The integrator updates the genuine progress record and runs real `--check`.

Local `ops-work` leases coordinate one filesystem only. Separate Cloud
workspaces additionally require explicit registry ownership, disjoint branches
and remote expected-HEAD updates. PostgreSQL fencing for application dispatch
does not replace Git branch concurrency control.

## Fallbacks and concrete limits

| Blocker | Safe continuation | Do not claim |
| --- | --- | --- |
| Missing/unselectable Cloud environment | Existing authorized isolated portable runner, pinned source and actual executor identity | It ran in the missing provider environment |
| Cloud task launch timeout/outage/quota | Preserve admission/failure; use authorized portable source work where independent | Account rotation or a queued task equals execution |
| Owner Mac offline | Node/Python/synthetic checks on verified Cloud/local executor | iCloud or SSH wakes an offline device |
| Diverged PR/active competing writer | Preserve work; stop overlap and coordinate integration/rebase | Local lease protects every Cloud workspace |
| Unavailable PostgreSQL/Chibi/provider | Synthetic contracts/source checks with external gates explicitly missing | Signed host or real model acceptance |
| Missing original binary assets | Preserve exact remote tree entries; disclose partial checkout | Build success proves artwork/browser acceptance |
| Claude or another reviewer unavailable | Preserve actual prior advice and independent available source review | A different reviewer was Claude or old advice reviewed new bytes |

The existing completion monitor is not a perpetual company dispatcher. A
separate fleet automation was not created after the observed 20-active-task cap.
Do not disable unrelated automations to create capacity. Future work is
`proposed-not-started` until admitted with a real task identity.

## Handoff and permission planes

Use the compact schema in [ops rules](../ops/AGENTS.md). At minimum: work ID,
actual executor, base/head/tree, clean/dirty scope, branch/PR, original command
counts/exit/log hashes, independent reviewed HEAD, limits and next owner/action.
Do not place secrets or private conversations in receipts.

Developer admission authorizes scoped code/test work, not Chibi runtime access.
Only the private host can authorize recipient/tenant-specific model or tool
operations, consent, budget and revocation. Model cases, provider tests, host
acceptance and release are distinct gates.

The owner must separately authorize merge/deploy, spending, credential/permission
changes and public exports where not already within the approved task. This
playbook grants none. Follow source evidence, preserve failed history, and keep
private operations outside the public catalog and Junction submission.
