# Fleet Control — read-only server adapter

This module is a source-bound, read-only projection for 34 Junction development
agents. It does NOT provision Codex Cloud environments, execute models, run
Chibi tools or confer user entitlements.

## Integration boundary

Use collectFleetStatus from a trusted server-side controller only.

- manifests: the existing 34 ops/environments declarations. These express
  desired per-pet cloud setups, never authoritative provider status. Each pet
  must eventually have its own published and independently observed ID.
- sourceCommit: exact 40-character SHA obtained from an authenticated GitHub
  reader. This module validates shape and binds receipts to SHA; it does not
  itself authenticate GitHub.
- providerAdapter.readEnvironment: fresh authenticated Cloud observation for
  one immutable recorded environment ID. The returned receipt binds that
  environment ID, pet, repository and SHA. The receipt must attest published
  status and pass timestamp validation.
- providerAdapter.verifyReceipt: independent provider-specific attestation
  verification. Return true only after successful authenticated readback.
- ciVerifier, evalVerifier and grantAdapter.verifyReceipt: authenticated
  host-side verifier functions, not self-reported booleans from JSON.
- grantAdapter: optional read-only Chibi host grant status. Revocation denies.
  Even verified active grant evidence is NOT authorization to execute; the
  private Chibi PEP/PDP decides on each actual runtime action.

Provider/account credentials stay inside the approved adapter process and
must never be committed or serialized into the dashboard.

## Read-only usage

Import collectFleetStatus from services/fleet-control/index.mjs, then call it
with manifests, sourceCommit, providerAdapter, ciReceipts, evalReceipts,
ciVerifier, evalVerifier, and optional grantAdapter.

The result (junction-fleet-control/server-projection/v1) is pure JSON containing
34 rows, generated timestamp, exact SHA, cloud/CI/eval/grant status and next
action. It emits only allowlisted identifiers and safe evidence URLs, not raw
provider/host responses. One pet provider failure does not stop the other 33.

### Mission Control

An integrator can consume this JSON alongside dist/mission-control/status.json
and map source-SHA-matched rows in the private owner-only dashboard. The
current browser status-model intentionally distrusts serialized ready flags;
this protection must remain until a separately reviewed backend trust channel
exists. A provider-observed ready state means DEV CLOUD ready, not Chibi
runtime published, model evaluated or recipient-authorized.

## Tests

Run from repo root:

    node --test services/fleet-control/index.test.mjs

Fixtures intentionally use invented Cloud IDs, without real network/model calls
or credentials. They cover fake readiness, source/ID mismatch, denied provider
receipt verification, revoked grants, stale CI/eval SHA, provider outage, all 34
rows and explicit secret stripping.

Rollout blocker: no independently authenticated Codex Cloud environment reader
and external attestation verifier are configured yet. Nothing may be promoted
from manifest self-reports alone.
