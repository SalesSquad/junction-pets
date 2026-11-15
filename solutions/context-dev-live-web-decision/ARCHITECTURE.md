# SupplyPulse / Live Web Decision Room architecture entrypoint

The existing [README.md](README.md) records this product's components, source
contracts and trust boundaries. This file supplies the monorepo workspace
entrypoint; it does not replace that implementation documentation.

The root page compares two pinned real product sources through Context.dev;
`/replay` retains the synthetic decision controls. `/watches/` adds a local
product-search agent with a durable SQLite schedule, bounded Context requests,
history and in-app notifications. [Watch architecture and limits](watch/README.md)
and the [HTTP contract](watch/API.md) describe the new boundary. Provider
credentials and watch state remain host-side; only fixed Context endpoints and
approved retailer product URLs can be used. The server must be running for
scheduled execution. This does not provision a hosted monitor or purchase.

The [workspace manifest](solution.json) registers source organization only.
No runtime capability use, provider account, deployment or new permission is
asserted. Root [architecture](../../ARCHITECTURE.md) remains authoritative for
shared services and the separate Chibi runtime.
