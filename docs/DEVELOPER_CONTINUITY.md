# Private developer continuity

`ops/development-progress.json` is an integrator-maintained checkpoint of exactly
34 **completed, released, finite company source tasks**. It is not a scheduler,
live worker list, provider inventory, authority grant or public catalog export.
Keep it private. The reader never writes a receipt, refreshes evidence, launches
work, contacts a provider or performs network requests.

From the repository root, after `npm ci --ignore-scripts`:

```sh
node scripts/ops-development-progress.mjs
node scripts/ops-development-progress.mjs --pet aiven
node scripts/ops-development-progress.mjs --check
node scripts/ops-development-progress.mjs --pet aiven --check
```

The default is a compact count/exception summary. `--pet` returns exactly one
company's complete continuation record and reads no other company's source
files (the entire small ledger is still schema-validated). `--check` exits 1 for
any selected stale/missing/unreadable scope; malformed/missing ledger or invalid
arguments always exit 1. A summary without `--check` can describe stale records
and still exit 0. No command changes stale evidence to green.

## Read progressively

1. Read root `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `ops/AGENTS.md`, the
   package contract and Cloud developer playbook for authority and boundaries.
2. Read the compact summary, then only `--pet <company>` for an assigned lane.
3. Follow that record's exact PR/review/check evidence. Independently resolve
   current authenticated GitHub main, source and competing PR heads. Read only
   the selected company's files and its relevant local contract/test.
4. Recheck source, surviving work, writer ownership and actual executor before
   admitting a new bounded task. `nextAction` is **proposed-not-started**; the
   record's stable logical owner is not an active process or distributed lease.

The dated development queue and prior PR receipts remain historical evidence.
Do not rewrite their earlier counts/times or imply their workers still run.

## Closed schema v1

Every key shown below is required; no unknown fields are accepted. The example
is **synthetic schema guidance**, not a valid 34-company production ledger or a
claim that its hashes, executor, review or test counts are real.

```json
{
  "schemaVersion": 1,
  "repository": "SalesSquad/junction-pets",
  "observedAt": "2026-11-13T08:00:00.000Z",
  "records": [{
    "company": "aiven",
    "agentId": "junction-dev-aiven",
    "workId": "junction.aiven.synthetic-example",
    "branch": "codex/junction-aiven-synthetic-example",
    "source": {
      "base": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "tree": "cccccccccccccccccccccccccccccccccccccccc"
    },
    "pr": {"url": "https://github.com/SalesSquad/junction-pets/pull/1", "mergeCommit": null},
    "integrationPr": null,
    "executor": {"kind": "native", "id": "synthetic-author", "taskUrl": null},
    "review": {
      "reviewer": "synthetic-independent-reviewer",
      "head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "verdict": "pass",
      "evidenceUrl": "https://github.com/SalesSquad/junction-pets/pull/1#issuecomment-1"
    },
    "checks": {
      "focused": {"passed": 3, "total": 3},
      "full": {"passed": 12, "total": 12},
      "evidenceUrl": "https://github.com/SalesSquad/junction-pets/pull/1#issuecomment-2"
    },
    "writerState": "released",
    "nextAction": {"state": "proposed-not-started", "owner": "junction-dev-aiven", "action": "Inspect the next bounded source proposal."},
    "scopeSha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  }]
}
```

`records` must contain each canonical `EXPECTED_COMPANIES` slug exactly once.
`observedAt` uses valid UTC calendar time with exactly three fractional digits.
Source/base/tree and non-null merge commit are 40 lowercase hexadecimal digits;
scope SHA-256 is 64. `source.head` is the **reviewed author/task HEAD**, not a
later aggregate merge. `review.head` must equal it; reviewer must differ from
`executor.id`. These are recorded claims, not authenticated identity or approval.

`pr.url` and optional `integrationPr` identify this repository's PRs;
`pr.mergeCommit` may be null for an unmerged source PR. Integration is separately
recorded, never inferred from an author's completion. Review evidence is a
same-repository PR/comment URL. Check evidence is a same-repository PR/comment
or actual ChatGPT task URL. No URL query strings or credentials are accepted.

Executor kinds are `native` (actual local/attached-cloud task identity, **null**
provider task URL) and `codex-cloud` (actual executor identity plus observed
`https://chatgpt.com/local/<uuid>` or `/codex/tasks/task_<id>` URL). A native
attached Linux run does not become Codex Cloud merely because it runs in a cloud.
Legacy desired environment names/IDs must never stand in for the actual executor.
URL/ID shape validation cannot prove a task exists or authenticate its receipt.

`checks` retain the **original author-HEAD** focused/full passed and total counts
(safe integers, `0 <= passed <= total <= 1000000`, `total > 0`). Do not replace
them with a later aggregate count, independently rerun count or model eval count.
All records require `writerState: released` and one proposed next action with a
bounded owner identifier and a nonempty single-line action of at most 600 chars.
The parser accepts JSON text only, up to 256 KiB. Ordinary `JSON.parse` duplicate
member behavior applies: the final value wins; duplicate company records fail.

## Generate and maintain a source scope digest

On the exact reviewed source checkout (or a separately verified byte-equivalent
company scope), call the exported read-only helper:

```sh
node --input-type=module -e 'import {companyScopeSha256} from "./ops/development-progress.mjs"; console.log(companyScopeSha256(process.cwd(), "aiven"));'
```

It obtains only Git-index-tracked paths under `pets/<company>/**`,
`plugins/junction-<company>/**` and `tests/pet-<company>.test.mjs`. All three scope
parts must be present. Stage intended new files before computing; arbitrary
untracked content is intentionally not scanned. A tracked addition, deletion,
rename, executable-mode or byte change alters the digest. A tracked file absent
from disk is unverified, including a sparse/partial checkout missing company
assets. Unrelated source changes do not make that company's scope stale.

The deterministic SHA-256 stream starts with UTF-8
`junction-company-scope-v1\0<company>\0`. Sort validated ASCII paths in ascending
code-point order; append each path, NUL, normalized actual mode (`100644` or
`100755`), NUL, decimal byte length, NUL, then the exact file bytes. NUL is one
zero byte, not the two printed characters. Git index modes must be regular
files; symlinks, unmerged entries, unsafe paths and nonregular files are refused.
Parent directory symlinks are refused too. Limits are 256 files, 1 MiB per file,
8 MiB total per company and a bounded Git-index response. Index changes or
detected concurrent file changes fail; use a stable checkout, not a concurrently
mutating writer workspace. This is not an atomic filesystem snapshot service.

For every accepted new company slice, the integrator must independently check
the source PR/HEAD/tree/base, review identity/HEAD, actual executor, original test
receipts and integration PR/merge. Compute the digest from those reviewed bytes,
update that company's record and `observedAt`, set its released writer and one
unstarted next action, run the focused tests and `--check`, and commit the record
through the normal reviewed task PR. Preserve earlier receipts. **Never simply
recompute a stale digest to conceal changed, unreviewed source.**

## Qualification and test boundary

`source-matched` means only that local tracked company paths, modes and bytes
agree with the stored scope digest. It does not establish that the recorded
author SHA exists, GitHub currently has those bytes, or the evidence is genuine.
The reader always labels current full-suite, remote, provider and host
qualification **unverified** and provenance authentication **false**. Local dirty
HEAD, unrelated missing binary assets and later integration cannot silently
become hosted/signed CI, browser/artwork acceptance, model evaluation, Chibi
runtime/adoption or recipient permission. No age-based live status is inferred
from `observedAt`; the observation remains historical even when bytes match.

`node --test tests/ops-development-progress.test.mjs` runs the real CLI against
isolated synthetic Git roots and ledgers, without a live progress file, provider,
network or mutable real-checkout dependency. It covers closed records, exact
selection, finite-worker boundaries, byte/mode/path drift, missing files, bounded
reads, symlink refusal and unrelated/untracked content. It remains part of the
ordinary `node --test` discovery without changing package scripts or the roster.
