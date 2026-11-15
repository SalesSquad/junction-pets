# Valio Aimo product retrieval — PostgreSQL / pgvector

**Status (J26-VALIO-RETRIEVAL-20261114):** query port, Aimo-only database schema and parameterized hybrid SQL implemented. The default demo runs an honest **lexical fallback over five invented SKUs**. No live PostgreSQL, Aiven connection, 25,000-product sponsor dataset, embeddings or third-party LLM API was available in the execution environment, so pgvector is **not yet exercised end to end**.

## Contract

- `GET /api/products/search?q=laktoositon%20maito`: requires an ephemeral synthetic buyer session and returns *advisory* candidates, each with product code, source kind, source reference, source version, source SHA-256 and score. `mode` says `FIXTURE_LEXICAL_NO_EMBEDDINGS` until an actual PostgreSQL adapter is injected.
- The SQL adapter combines PostgreSQL `plainto_tsquery('simple', ...)` with pgvector cosine nearest-neighbour search (`<=>`) through reciprocal rank fusion (RRF, `k=60`). Both input strings and the validated 384-dimensional vector are bound SQL parameters.
- Product **identity** is separate: GTIN/EAN always uses `GET /api/scan/resolve`, which requires an exact checksum-valid match. Never use vector similarity to resolve a barcode.
- Discovery is never an authority source. The existing `core.mjs` rechecks exact SKU, buyer policy, fixed price, time, version and stock before creating a quote or order. RAG cannot declare allergens, stock, delivery, price, identity, buyer authorization or verified supplier provenance.
- Own Aimo namespace `aimo_retrieval` and buyer/tenant scopes. **No BIM register, Valmet spatial data, Meta imagery or Taimi personal records** are imported.

## External Aiven / PostgreSQL activation (not performed)

1. Obtain an owner-approved **Aiven for PostgreSQL** service and an appropriately scoped database role, over certificate-validated TLS. Keep credentials in an approved secret manager / runtime environment, never the repo or the browser. An Aiven service is required to claim the Aiven technology challenge.
2. Apply [the migration](sql/001_aimo_retrieval_pgvector.sql) in the authorized database (`CREATE EXTENSION IF NOT EXISTS vector`). Create a dedicated read-only, **non-owner, non-BYPASSRLS** API role with `USAGE` on schema and `SELECT` on documents. Create a distinct scoped ingest role with `USAGE`, `SELECT`, `INSERT` and `UPDATE` but no `DELETE`. The migration defines SELECT/INSERT/UPDATE row policies, including `FORCE ROW LEVEL SECURITY`; an ingest transaction must set *both* `aimo.tenant_id` and `aimo.buyer_scope` locally before writing. Never grant write rights to the API search role. Row-level security uses transaction-local scopes; the hybrid SQL also repeats both predicates.
3. Populate documents from a legitimate Valio Aimo mock-catalog source, storing the original source digest, revision, observed timestamp and expiry. Fill `family` only from an authorized product classification and `lactose_free` only from a source-verified attribute (**NULL means unknown**). **Do not invent** real products, infer food safety from LLM output or copy Valmet's BIM identifiers. A separate, permissioned ingest worker controls catalog revisions and single-current-version uniqueness. Price and stock remain under the sponsor mock API / deterministic transactional trade core, not the vector index.
4. Generate 384-dimensional vectors using the **same pinned multilingual embedding model** for document passages and search queries, using its correct `passage:` / `query:` conventions. The existing Taskupankki embedding code is a reusable algorithmic starting point, but its private content is not imported. No synthetic/random vector may be labeled an embedding in a live retrieval report. **Do not expose semantic-only nearest neighbours without a model-specific benchmarked maximum cosine distance.** Default pgvector adapter omits such hits and uses vectors only to rerank lexically supported results; unknown diet/allergen requests produce an explicit abstention.
5. Supply an authorized node-postgres-compatible `pool` and real `embedQuery` function when constructing the HTTP server:

   ```js
   import { createTradeService } from './src/core.mjs';
   import { createTradeHttpServer } from './src/server.mjs';
   import { createPgvectorCatalogSearch } from './src/catalog-retrieval-pg.mjs';

   // pool: injected pg Pool over an authorized, verified-TLS database connection.
   // embedQuery('query: <text>'): injected trusted model returning
   //   { model: '<pinned model>', vector: [384 finite, nonzero floats] }.
   const catalogSearch = createPgvectorCatalogSearch({
     pool, embedQuery, tenantId: 'valio-demo', embeddingModel: pinnedModel,
   });
   createTradeHttpServer(createTradeService(), { catalogSearch }).listen(4177);
   ```

   This **interface example** requires `pool`, `embedQuery`, and `pinnedModel` to be supplied by a real deployment adapter; it is not a runnable command without them. Do not expose the DSN or the document embedding model's API key to the browser. The SQL adapter starts a READ ONLY transaction, pins row-level security scopes, queries and commits; an error rolls back and returns 503, **without silently falling back** to different data.

6. Run an independent PostgreSQL integration qualification and an adversarial 50–100-query FI/EN benchmark. Include exact SKU searches, negative/ambiguous searches, old source versions, tenant isolation, source expiry, supplier mock price change, and mismatched embeddings. Compare lexical vs vector vs hybrid Recall@5 and hard-constraint safety before enabling an approximate HNSW index. No benchmark or database integration is claimed here.

## What is already tested locally

- Finnish and English lexical retrieval over fictional SKUs; no SKU hallucination for unsupported terms. Explicit category and lactose-free constraints are enforced against structured fixture fields; searches for unverified dairy-free/gluten-free/nut-free claims **abstain** instead of suggesting incompatible foods.
- SHA-256 source snapshot marker and version returned with candidates.
- Authenticated search scope, invalid query rejection and GTIN exact-route separation.
- Pg adapter's parameterized query, explicit tenant/buyer conditions, READ ONLY transaction and RLS `set_config`, trusted embedding-model/dimension guard, rollback/no secret disclosure on backend error; run with a **mock** `pg` pool.
- Scanner and signed order remain independent; retrieval API does not change inventory or purchase authority.

Sources: [pgvector upstream documentation](https://github.com/pgvector/pgvector/blob/master/README.md) and [Aiven's pgvector setup guide](https://aiven.io/docs/products/postgresql/howto/use-pgvector).
