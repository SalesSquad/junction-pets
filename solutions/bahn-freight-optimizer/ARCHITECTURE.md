# Spread offline dispatch director architecture entrypoint

The existing [README.md](README.md) records this product's components, source
contracts and trust boundaries. This file supplies the monorepo workspace
entrypoint; it does not replace that implementation documentation.

The [workspace manifest](solution.json) registers source organization only.
No runtime capability use, provider account, deployment or new permission is
asserted. Root [architecture](../../ARCHITECTURE.md) remains authoritative.
