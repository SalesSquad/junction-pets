# CRACI Decision Lab — shadow experiments and source-bound provider evidence

Work ID `J26-CRACI-ADAPTIVE-PROOF-20261114`  
Source base: PR #150, commit `e338251e2f43d1115610d8dbed7f2fc66a801285`  
Owner: CRACI adaptive-proof task; integration owner remains **Portfolio PR Recovery**.

## What this changes

Adds a **read-only adaptive experiment proposal**, a local hash-chained receipt
format and a **read-only CRACI REST API evidence adapter**. No YAML/workflow,
permission, environment variable, budget, CI controller or running campaign is
changed. These tools **cannot dispatch jobs or reserve provider credit**.

The current Chaos/Immune campaign hard stop is **14 Nov 2026 at 18:00 UTC
(20:00 Helsinki)**. The broader Junction credit window ends no later than
**15 Nov 2026 at 17:00 UTC (19:00 Helsinki)**. These are *distinct* stop
conditions. A valid shadow manifest must supply a `campaignHardStopUtc` at or
before `deadlineUtc`, which itself cannot exceed the broader deadline.
Planning after either relevant cutoff fails closed. Do not restart Immune/Chaos
or reset their epochs because a new selector exists.
For `immune-tournament` and `chaos-lab` candidates, the 14 Nov 18:00 UTC stop
is additionally a **hard-coded upper bound**. A later manifest stop is refused.

## Experimental hypothesis selection

`scripts/craci/adaptive-core.mjs` evaluates explicit candidates keyed by
`repository, workload, cell, sourceSha, harnessSha, scenarioDigest, seed`.

Each candidate provides independently motivated **estimated** values in [0,1]:
uncertainty, model disagreement, safety risk and novelty. The selector scores
their weighted sum per square root of worst-case reserved euros, with a
same-group diversity penalty. It excludes unchanged completed-green, unchanged
failed, queued, running and already-reserved source/fixture tuples. Previously
passed or failed tuples remain excluded even after later `cancelled` events.
It checks
the operator-observed meter timestamp (30-minute maximum age), conservative
per-cell reserve, campaign reserve, existing active reservations, 64-job ceiling
and eight-cell parallel ceiling. The **whole proposed wave**, including jobs
inside multi-cell candidates and currently active jobs, must fit `maxParallel`.
It never turns a proposed priority into a
confirmed performance claim.

**Statistical boundary:** adaptive selection is exploratory. Ordinary fixed
sample 95% confidence intervals calculated on adaptively selected worlds are
*not* valid prospective qualification. Freeze a new untouched holdout, register
the evaluation before opening it, or use a rigorously specified anytime-valid
confidence sequence/alpha spending design. The Rokoko baseline remains an
observed **zero advantage over constant PUSH_MEDIUM**, not a positive result.

Input example (source hashes and synthetic reservation values are historical
illustration only; do not use this expired 18:00 UTC campaign to dispatch):

```json
{
  "schema": "craci-adaptive-v1",
  "repository": "SalesSquad/junction-pets",
  "harnessSha": "e338251e2f43d1115610d8dbed7f2fc66a801285",
  "creditWindowOpen": true,
  "dispatchAuthorized": false,
  "deadlineUtc": "2026-11-15T17:00:00Z",
  "campaignHardStopUtc": "2026-11-14T18:00:00Z",
  "maxJobs": 8,
  "maxParallel": 4,
  "creditRemainingEur": 10,
  "campaignRemainingEur": 6,
  "meterReference": "operator-approved-billing-snapshot-or-provider-evidence-link",
  "meterObservedAtUtc": "2026-11-14T16:25:00Z",
  "candidates": [{
    "id": "rokoko-locked-ood17", "group": "rokoko",
    "workload": "rokoko-rl-ablations", "cell": "rokoko-ablation-17",
    "sourceSha": "59479b42b177c1829a2e6678adfff1fb68aef09c",
    "harnessSha": "e338251e2f43d1115610d8dbed7f2fc66a801285",
    "scenarioDigest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "seed": 17, "jobs": 1, "worstCaseEur": 1.5,
    "value": {"uncertainty": 0.9, "disagreement": 0.7, "safetyRisk": 0.8, "novelty": 1},
    "hypothesis": "Untouched OOD scenarios require a nonconstant safety policy."
  }]
}
```

CLI (only in an intact repo checkout with `scripts/craci/plan.mjs`):

```sh
node scripts/craci/adaptive-cli.mjs plan /path/to/manifest.json /path/to/receipts.jsonl
node --test scripts/craci/adaptive-proof.test.mjs
```

The output explicitly says `dispatchAuthorized:false` and
`shadow_plan_only_no_second_dispatcher_or_distributed_reservation_lock`.
Before any real integration, the **sole CRACI integrator** must add an
authoritative shared reservation and unknown-ACK policy to the *existing*
controller. Its current append-only dispatch intent and unknown-ACK restart
STOP remain in effect; local receipts are **not a distributed mutex**.

`appendReceipt()` appends line-delimited `{sequence,prevHash,event,hash}` with
local exclusive lock and rejects broken chains, conflicting heads and missing
GitHub run links on `passed` events. Hash links make accidental/local edits
detectable, but a writer able to replace the entire file could rehash it;
external immutable retention or signed checkpoint is needed for stronger
integrity. No previous receipts are rewritten.

## Actual CRACI provider evidence

The official current endpoint is `https://api.craci.com/v1preview1/`, *not*
the older `api.craci.dev` example. The bounded adapter uses only:

- `GET /network-trace?provider=github&repo=...&job_id=...`
- `GET /sbom?provider=github&repo=...&job_id=...`
- Optional `GET /usage?start=...&end=...`

References: [CRACI API](https://docs.craci.com/api/reference/),
[network trace](https://docs.craci.com/api/reference/operations/getnetworktrace/),
[SBOM](https://docs.craci.com/api/reference/operations/getsbom/),
[usage](https://docs.craci.com/api/reference/operations/getusage/).

`CRACI_API_TOKEN` comes only from the authorized executor's existing
environment, never from repository files or emitted JSON. The adapter uses
hardcoded HTTPS origin, GET only, fixed query selectors, no redirects, bounded
timeout and response length, and no raw URL/log/body output. A network trace
must match **GitHub job ID, run ID, repo, attempt (if provided), and harness
commit SHA**; otherwise its status is `unknown`. CycloneDX itself does not
carry a GitHub source SHA: its status stays `unknown` unless the companion
network trace verifies the exact job/run/harness tuple. Provider-served
CycloneDX then proves at most a job inventory response, **not completeness**.
The documented protocols are `http`, `dns`, `tcp` and `ssh_git` (not `ssh`).
HTTP denials use `policyDenied`; TCP/SSH Git denials use `allowed:false`.
DNS has no equivalent policy-denial field.
HTTP errors, missing token, unavailable
endpoint or mismatched source all fail closed. The API does not supply a
cryptographically signed attestation in these responses: the output keeps
`providerAttestationVerified:false`.

The usage endpoint supplies delayed **organization-aggregate vCPU seconds**;
it does **not** provide per-job invoiced euros. Therefore
`perJobBilledEur:null` remains, even on an HTTP 200 response. Nor does a
SHA256 of a GitHub log become an independent provider network/SBOM proof.

```sh
# Run read-only only where CRACI_API_TOKEN is already legitimately configured.
node scripts/craci/adaptive-cli.mjs provider GITHUB_JOB_ID GITHUB_RUN_ID EXACT_HARNESS_SHA
```

Never set an API token in shell history, commit it, echo it or forward it to a
different host. The CLI does not contact CRACI when the token is absent.

## Handoff / next actions

1. Preserve the scheduled 14 Nov 20:00 Helsinki Immune/Chaos stop and the
   15 Nov 19:00 broader campaign stop. No additional Immune/Chaos dispatch.
2. At the sole integrator's next authorized opportunity, check whether an
   existing CRACI token is available **on the authorized host**. Collect
   `/network-trace` and `/sbom` for one known completed GitHub job and compare
   source/harness IDs; mark network/SBOM unknown if not available. Query usage
   separately and report vCPU seconds, never invent a euro bill.
3. Integrate the selector only after durable cross-run reservation and unknown
   ACK handling is verified. Use new hypotheses and frozen holdouts, not
   another green seed burn. Submit as a separate reviewed PR; never bypass
   Portfolio PR Recovery or alter history to make a failing test green.

**Tests:** `node --test scripts/craci/adaptive-proof.test.mjs` covers source
replay, budget/cutoff (including nonextendable 14 Nov stop), irreversible
green/failure dedupe despite cancellation, per-wave cell caps, chain
corruption, missing provider token, valid mocked API, `ssh_git` parsing,
source/run mismatch, unbound SBOM rejection and HTTP 403. Passing
tests are **synthetic**; live CRACI provider readback is not claimed.
