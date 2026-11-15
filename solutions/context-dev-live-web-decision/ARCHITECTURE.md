# SupplyPulse / Live Web Decision Room architecture entrypoint

The existing [README.md](README.md) records this product's components, source
contracts and trust boundaries. This file supplies the monorepo workspace
entrypoint; it does not replace that implementation documentation.

Develop the documented synthetic supplier-change decision replay; actual provider admission and live execution remain separate.

The [workspace manifest](solution.json) registers source organization only.
No runtime capability use, provider account, deployment or new permission is
asserted. Root [architecture](../../ARCHITECTURE.md) remains authoritative for
shared services and the separate Chibi runtime.
