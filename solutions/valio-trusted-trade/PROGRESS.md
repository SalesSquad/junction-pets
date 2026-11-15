# J26-VALIO-TRUSTED-TRADE-001: progress

**Status (15 Nov 2026):** judge-ready as a local, fully synthetic prototype. Challenge: Valio Aimo #327, Trusted Trade Agents.

## Start here

- [SUBMISSION.md](SUBMISSION.md): judge guide with the 3-minute demo path and observed results.
- [FRONTIER_RUNBOOK.md](FRONTIER_RUNBOOK.md): Mission Control demo script and honesty boundary.
- [AGENT_USAGE_AUDIT.md](AGENT_USAGE_AUDIT.md): MCP, recovery, persistence and sponsor-read audit.

## Verification

- `node --test tests/*.test.mjs`: **146 / 146 pass** (re-run 15 Nov 2026 at `320b8cf`, Node v22.23.4, no third-party installs). The coordinator observed the same 146/146 at `0ef075a`.
- Demo commands in SUBMISSION.md were run against a live server: `/api/health`, `/`, `/mission`, `demo:frontier happy` and `shock --decision=approve` all behaved as documented. State went to a `/tmp` path.
- Browser scripts (`tests/*.browser.mjs`) need Playwright and were not re-run in this pass.

## Implemented

- Zero-dependency Node HTTP supplier, Mission Control UI and snapshot-bound review UI.
- Independent buyer agents (`demo:agent`, `demo:frontier`): Ed25519 offer and mandate, human decision gate, stock-shock recovery, idempotent orders, SHA-256 hash-linked audit.
- Local SQLite durability (WAL, FULL sync) with backup command.
- Optional MCP v2 bridge in `mcp/`, optional read-only sponsor-mock adapter.

## In flight separately

- PR #301 (host buyer identity and exact human consent) merged to main on 15 November 2026 as `2c71caf`; see BUYER_IDENTITY.md.

## Not integrated

1. Sponsor-authenticated catalog, quotes or orders: unverified, no order endpoint upstream.
2. Authenticated buyer approval and scoped delegated identity.
3. Transactional idempotency and supplier-side reconciliation for live procurement.
4. Public deployment and multi-device browser matrix.

All supplier, catalog, price and order data is synthetic. No real Valio Aimo system is connected.
