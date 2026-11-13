# Focused official-source review — 13 November 2026

Work ID: `junction.aiven.source-provenance-20261113`.

Read from Aiven's public documentation repository, current `main` observed at
`fc97657f9fabcb4e13f7385178aaf77b0d8faf65`. Its README states that this repository
generates aiven.io/docs. The website itself was not fetched in this environment;
website publication parity and service-specific/version-specific availability
remain unverified. No account or service was inspected. Only official Aiven
material was researched; linked third-party/upstream pages were not consulted.

| Exact supporting URL | Pinned official source | Observed support and limits |
| --- | --- | --- |
| https://aiven.io/docs/products/postgresql/howto/identify-pg-slow-queries | [source](https://github.com/aiven/aiven-docs/blob/fc97657f9fabcb4e13f7385178aaf77b0d8faf65/docs/products/postgresql/howto/identify-pg-slow-queries.md) | Describes pg_stat_statements and version-dependent column names; recommends plan inspection as a next step. Does not identify an index for an unseen query. |
| https://aiven.io/docs/products/postgresql/howto/repair-pg-index | [source](https://github.com/aiven/aiven-docs/blob/fc97657f9fabcb4e13f7385178aaf77b0d8faf65/docs/products/postgresql/howto/repair-pg-index.md) | REINDEX addresses corruption; warns of locking/interference. Does not prove corruption from slowness or recommend an index for a query. |
| https://aiven.io/docs/products/kafka/concepts/monitor-consumer-group | [source](https://github.com/aiven/aiven-docs/blob/fc97657f9fabcb4e13f7385178aaf77b0d8faf65/docs/products/kafka/concepts/monitor-consumer-group.md) | Extra consumers beyond partition count remain idle; replication lag is the difference between high watermark and group offset per partition. Does not prove a root cause or an exactly-once processing guarantee. |

The PostgreSQL scaling-performance index page and pgwatch2 monitoring guide were
also inspected during discovery. They are not substituted for the focused pages
above. The slow-query page itself contains examples using differing column names;
the companion must ask for version/evidence rather than blindly copy SQL.

Design decision: strengthen the existing package guidance and six authored eval
cases without changing schema, stable identity, three capabilities or host
permissions. No-hit, irrelevant-hit and tool failure are separate states; all
retain a useful next evidence request. Deterministic tests check this authored
contract and its existing export context, not real model adherence.

Integrator follow-up: regenerate/check `plugins/junction-aiven/` and its shared
source lock using the existing plugin generator, reviewing source-digest changes;
do not rewrite historical registration receipts. Then run the six authored cases
through the existing host-approved behavioral evaluator with this exact package
digest, pinned model/version, actual retrieval outcomes and independent scoring.
The real retriever/host must supply scoped source URLs, content and failure/no-hit
status; this content-only change cannot implement or attest those runtime results.
Shared generator/lock and runtime changes remain outside this writer's scope.
