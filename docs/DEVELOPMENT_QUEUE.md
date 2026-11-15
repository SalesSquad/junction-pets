# Company development: current handoff index

The canonical accepted-task register is
[`ops/development-progress.json`](../ops/development-progress.json), not this
page or an old conversation. It contains one reviewed, integrated, released
source task for each of the 34 companies, with a stable `junction-dev-<company>`
owner and one **proposed, not started** follow-up. A logical owner is not a
running process; no background dispatcher is implied.

From the repository root:

```sh
node scripts/ops-development-progress.mjs --check
node scripts/ops-development-progress.mjs --pet aiven
```

The first command checks every tracked company scope against its accepted
digest and prints only counts/exceptions. The second returns one complete
source/PR/review/test/executor/continuation record. Substitute any company slug
from the ledger. Read the [exact reader contract](DEVELOPER_CONTINUITY.md) before
treating a match as evidence: it proves local company-scope agreement only,
not remote freshness, current full-suite success, live workers or provider access.

## Current ownership: G1 Moves and CRACI

| Lane | Logical owner | Work and evidence |
| --- | --- | --- |
| Rokoko | `junction-dev-rokoko` | [G1 Moves offline motion research](../solutions/rokoko-teleoperation-gym/learning/G1_MOVES.md), including the completed CRACI training result and retargeting follow-up. |
| CRACI | `junction-dev-craci` | Its own [build-provenance and supply-chain challenge](CRACI.md#independent-craci-challenge-lane), including SBOM and advisory evidence. CRACI also supplied the G1 compute; that does not transfer ownership of the motion work. |

The two entries in `ops/development-progress.json` are independent,
proposed-not-started continuations; they are not running workers or leases.
The prior G1 experiment remains complete historical evidence, not an active
training job. At source `d9a6ff7700ff0ca41580acc193691b2e2f658c5d` on 15
November, the local scope check reported all 34 historical company digests,
including these two, as stale. The old evidence and digests are retained; the
lane routing here is not a source-matched or active-worker claim.

## Resume one lane

1. Resolve current authenticated GitHub main, the recorded source PR and any
   competing task branch. Preserve surviving work and inspect actual ownership.
2. Read the selected record's original receipts and `nextAction`; do not assume
   the proposal was launched. Obtain the actual existing executor/source pin.
3. Follow [COMPANY_WORKER_BRIEF.md](COMPANY_WORKER_BRIEF.md) for an exclusively
   assigned company scope and the [Cloud playbook](CLOUD_DEVELOPER_PLAYBOOK.md)
   for admission, supported fallback and finite task delivery.
4. After independent review and authorized integration, the integrator updates
   that record from real source/evidence, checks the new scope and runs
   `npm run verify:source`. Original author counts stay with their original SHA;
   a later aggregate test count must not replace them.

The [dated early queue](../ops/development-queue-20261113.json) is preserved
historical evidence, including its then-current running/queued states. It is
not today's queue. The [development-system map](DEVELOPMENT_SYSTEM.md) explains
the separation from Cloud configuration, local leases and private runtime.

Future feature proposals remain unstarted until admitted. New live model/tool,
recipient, provider, database, browser and release proof requires its own actual
authorized environment and source-bound receipt. This source checkpoint never
grants those permissions or starts an always-on worker.
