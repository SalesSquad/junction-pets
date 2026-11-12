# Aiven public documentation adapter — Junction Wave 3

A narrow, **public/read-only knowledge tool** for the independently built Junction Aiven companion. It is not an Aiven account integration, a Chibi Rust/Cedar grant issuer, a live model, a LangGraph node, or an official Aiven endorsement. No user, tenant, credential, OAuth token or private service data is read or stored.

## Exact source provenance

The only two document bodies this adapter can request are pinned to the public upstream [aiven/aiven-docs](https://github.com/aiven/aiven-docs) repository:

- Git commit: `fc97657f9fabcb4e13f7385178aaf77b0d8faf65`
- Upstream license: **Apache-2.0**, confirmed from [LICENSE at that commit](https://github.com/aiven/aiven-docs/blob/fc97657f9fabcb4e13f7385178aaf77b0d8faf65/LICENSE)
- Copyright belongs to upstream contributors. This repository contains only our short original summaries, metadata and source citations; no copied article bodies.

| Topic | Exact pinned source path | Official end-user citation | SHA-256 of raw upstream Markdown |
| --- | --- | --- | --- |
| Kafka consumer groups | `docs/products/kafka/concepts/monitor-consumer-group.md` | [Monitor a consumer group](https://aiven.io/docs/products/kafka/concepts/monitor-consumer-group) | `5719fb1d842b76527dc1e54fd84ce1e5bbecd6c7adfda65e0256238086173f1f` |
| PostgreSQL slow queries | `docs/products/postgresql/howto/optimize-pg-slow-queries.md` | [Optimize slow queries](https://aiven.io/docs/products/postgresql/howto/optimize-pg-slow-queries) | `b7189c102de0e3662a866f0f5f96c30614d2fe6543915882c7009b686cda29bd` |

The Git source commit above describes **Aiven documentation only**. It is not the Junction monorepo's `sourceSha`, which must be independently resolved and approved by the Chibi host in any future agent-to-agent workflow.

## API and evidence levels

- `rankAivenDocs(query)`: offline, deterministic source-topic matching; `MATCHES_UNVERIFIED` is a shortlist, **not** evidence that document bytes were fetched.
- `listAivenPinnedSources()`: fixed source URL/digest declarations, all `bytesVerifiedThisRun:false`.
- `searchAivenPublicDocs(query, {fetchImpl, timeoutMs, signal})`: fetches at most two **fixed**, exact-commit URLs from `raw.githubusercontent.com/aiven/aiven-docs`, checks response origin/path, status, text MIME, byte limit and SHA-256 **before** returning a curated summary and official citation. Results are `pinned-public-docs`, meaning source bytes matched our declared content hashes, *not* a provider execution or signed Chibi receipt.
- `discoverAivenDocsLinks(...)`: optional HTTPS GET to exactly `https://aiven.io/docs/llms.txt`. This live, unpinned index is advisory. It can only report matches with the two already-fixed end-user citations and can never supply a new fetch URL or override the pinned corpus.
- `searchSyntheticAivenFixture(...)`: deterministic unit-test seam with custom small fake text/hashes. Its outputs always retain `synthetic-fixture` classification and cannot claim upstream proof.

For valid questions, the output contains only a short human-authored summary, official citation URL, source path/commit, computed body digest and a bounded score; **never the raw upstream Markdown**, snippets from arbitrary sites, customer data or a model answer. A nonsense, unrelated or too-generic question returns no documents and makes zero document requests. A source mismatch or fetch failure returns a bounded error code, never a fabricated citation.

All HTTP requests are **GET only**, `credentials:'omit'`, `redirect:'error'`, `referrerPolicy:'no-referrer'`, with an AbortSignal and a hard 5-second maximum timeout. Document bodies are capped at 16 KiB, optional index at 96,000 bytes. No query, user, model or fetched document body can change those endpoints. Errors are redacted codes rather than network exceptions or response text. No per-user or inter-pet state persists here.

## Reproducible sponsor smoke

From the monorepo root:

    node --test services/pet-adapters/aiven/adapter.test.mjs
    node services/pet-adapters/aiven/smoke.mjs --offline
    node services/pet-adapters/aiven/smoke.mjs

Both smoke modes execute exactly three fixed scenarios:

1. Kafka consumer group lag
2. PostgreSQL slow queries indexes
3. Nonsense question: abstain, return zero sources

`--offline` prints the declared URLs and expected hashes labelled **unverified this run**, making the demonstration resilient without network access. The default live smoke makes two anonymous, read-only HTTPS requests to the exact pinned public documents and prints only citations, source hashes, result/error codes and `hostGrantVerified:false`/`providerInvocationVerified:false`. Network failure exits nonzero without making up evidence. No Aiven credentials or project are needed; no service is provisioned.

## Integration boundary

The future Python LangGraph Council may call this as a **public source-retrieval tool** before preparing a proposal or explanation. It must not turn a source citation into authority for model/tool execution. Any delegated pet action, tenant-private context, provider use, durable replay or external effect remains exclusively governed by the private Chibi Rust/Cedar host and `contracts/pet-collaboration/v1`. A public document digest is not a Chibi receipt, a verified Codex Cloud environment, a model invocation, or Aiven support approval.

A later integrator can add Council discovery/wiring and production host verification in their own owned paths; this module deliberately changes no shared package, Council, schema, export or deployment files.
