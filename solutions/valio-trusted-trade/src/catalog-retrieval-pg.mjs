/**
 * Optional Aiven/PostgreSQL pgvector RRF adapter. No credentials, DB driver,
 * embeddings or real supplier data are bundled. Inject an authorized pg pool
 * and a real query-embedding function; without them the app uses lexical demo.
 */
import { RetrievalFault, validateCatalogQuery, resolveSearchConstraints } from './catalog-retrieval.mjs';

export const PG_EMBEDDING_DIMENSION = 384;
export const PG_HYBRID_QUERY = `
WITH authorized AS MATERIALIZED (
  SELECT sku, product_title, family, lactose_free, catalog_version, source_kind, source_ref,
         source_sha256, source_observed_at, document_tsv, embedding, embedding_model
  FROM aimo_retrieval.product_documents
  WHERE tenant_id = $1 AND buyer_scope = $2 AND status = 'ACTIVE'
    AND is_current AND (valid_until IS NULL OR valid_until > now())
    AND ($7::text IS NULL OR family = $7)
    AND ($8::boolean IS NULL OR lactose_free = $8)
), lexical AS (
  SELECT sku, row_number() OVER (
    ORDER BY ts_rank_cd(document_tsv, plainto_tsquery('simple', $3)) DESC, sku
  ) AS rank
  FROM authorized
  WHERE document_tsv @@ plainto_tsquery('simple', $3)
  ORDER BY ts_rank_cd(document_tsv, plainto_tsquery('simple', $3)) DESC, sku
  LIMIT 30
), semantic AS (
  SELECT sku, embedding <=> $5::vector AS semantic_distance,
    row_number() OVER (ORDER BY embedding <=> $5::vector, sku) AS rank
  FROM authorized
  WHERE embedding IS NOT NULL AND embedding_model = $4
  ORDER BY embedding <=> $5::vector, sku
  LIMIT 30
), fused AS (
  SELECT coalesce(l.sku, s.sku) AS sku, l.rank IS NOT NULL AS lexical_match,
    s.semantic_distance,
    coalesce(1.0 / (60 + l.rank), 0) + coalesce(1.0 / (60 + s.rank), 0) AS rrf_score
  FROM lexical l FULL OUTER JOIN semantic s ON l.sku = s.sku
)
SELECT d.sku, d.product_title, d.family, d.catalog_version, d.source_kind, d.source_ref,
       d.source_sha256, d.source_observed_at, f.rrf_score,
       f.lexical_match, f.semantic_distance
FROM fused f JOIN authorized d ON d.sku = f.sku
ORDER BY f.rrf_score DESC, d.sku ASC
LIMIT $6`;

const scope = (value, name) => {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{3,100}$/.test(value)) {
    throw new RetrievalFault('INVALID_SEARCH_SCOPE', `Invalid ${name} scope.`, 403);
  }
  return value;
};

export function createPgvectorCatalogSearch({ pool, embedQuery, tenantId, embeddingModel, maxCosineDistance = null, maxSourceAgeMs = 86400000, clock = () => Date.now() } = {}) {
  if (!pool || typeof pool.connect !== 'function' || typeof embedQuery !== 'function' ||
      typeof embeddingModel !== 'string' || embeddingModel.length < 3 || embeddingModel.length > 120) {
    throw new TypeError('Explicit pg pool, model name and embedding provider are required.');
  }
  scope(tenantId, 'tenant');
  if (!Number.isSafeInteger(maxSourceAgeMs) || maxSourceAgeMs < 1 || maxSourceAgeMs > 30 * 86400000 || typeof clock !== 'function') {
    throw new TypeError('Source freshness needs an explicit bounded age and clock.');
  }
  if (maxCosineDistance !== null && (typeof maxCosineDistance !== 'number' ||
      !Number.isFinite(maxCosineDistance) || maxCosineDistance < 0 || maxCosineDistance > 2)) {
    throw new TypeError('Semantic-only retrieval requires a model-calibrated cosine distance in 0–2.');
  }
  return Object.freeze({
    async search({ query: raw, buyerId, limit = 5 } = {}) {
      const query = validateCatalogQuery(raw);
      scope(buyerId, 'buyer');
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 10) throw new RetrievalFault('INVALID_SEARCH_LIMIT', 'Limit must be 1–10.');
      const constraints = resolveSearchConstraints(query);
      if (constraints.abstainReason) {
        return { query, mode: 'PGVECTOR_HYBRID_RRF', candidates: [], reason: constraints.abstainReason,
          requiresTradeCoreValidation: true };
      }
      if (/^(?:[0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})$/.test(query)) {
        return { query, mode: 'PGVECTOR_HYBRID_RRF', candidates: [], reason: 'EXACT_GTIN_ROUTE_REQUIRED', requiresTradeCoreValidation: true };
      }
      let embedding;
      try { embedding = await embedQuery(`query: ${query}`); }
      catch { throw new RetrievalFault('EMBEDDING_BACKEND_UNAVAILABLE', 'Configured query embedding provider is unavailable.', 503); }
      if (!embedding || embedding.model !== embeddingModel || !Array.isArray(embedding.vector) ||
          embedding.vector.length !== PG_EMBEDDING_DIMENSION ||
          embedding.vector.some((v) => typeof v !== 'number' || !Number.isFinite(v)) ||
          embedding.vector.every((v) => v === 0)) {
        throw new RetrievalFault('INVALID_EMBEDDING', 'Query embedding source, dimension or values are invalid.', 503);
      }
      const vectorLiteral = `[${embedding.vector.join(',')}]`;
      let client;
      let began = false;
      try {
        client = await pool.connect();
        await client.query('BEGIN TRANSACTION READ ONLY');
        began = true;
        // SET LOCAL requires a pinned transaction client. RLS is defense in
        // depth; the hybrid SELECT also has explicit tenant/buyer predicates.
        await client.query("SELECT set_config('aimo.tenant_id', $1, true)", [tenantId]);
        await client.query("SELECT set_config('aimo.buyer_scope', $1, true)", [buyerId]);
        const result = await client.query(PG_HYBRID_QUERY,
          [tenantId, buyerId, query, embeddingModel, vectorLiteral, limit,
            constraints.requiredFamily, constraints.requiredLactoseFree]);
        if (!Array.isArray(result.rows)) throw new Error('Invalid DB result.');
        const parsed = result.rows.map((row) => {
          if (!row || typeof row.sku !== 'string' || typeof row.product_title !== 'string' ||
              typeof row.source_ref !== 'string' || !row.source_ref.trim() ||
              typeof row.catalog_version !== 'string' || !row.catalog_version.trim() ||
              !['dairy-milk', 'oat-drink'].includes(row.family) ||
              !Number.isFinite(new Date(row.source_observed_at).getTime()) ||
              !Number.isSafeInteger(clock()) ||
              new Date(row.source_observed_at).getTime() > clock() + 60000 ||
              clock() - new Date(row.source_observed_at).getTime() > maxSourceAgeMs ||
              typeof row.source_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(row.source_sha256) ||
              typeof row.source_kind !== 'string' || !Number.isFinite(Number(row.rrf_score)) ||
              typeof row.lexical_match !== 'boolean' ||
              (row.semantic_distance !== null && row.semantic_distance !== undefined &&
                !Number.isFinite(Number(row.semantic_distance)))) {
            throw new Error('Untrusted retrieval document shape.');
          }
          return { sku: row.sku, name: row.product_title, family: row.family,
            rrfScore: Number(row.rrf_score),
            provenance: { sourceKind: row.source_kind, sourceRef: row.source_ref,
              sourceVersion: row.catalog_version, sourceSha256: row.source_sha256,
              observedAt: row.source_observed_at },
            requiresTradeCoreValidation: true,
            _lexicalMatch: row.lexical_match,
            _distance: row.semantic_distance === null || row.semantic_distance === undefined ? null : Number(row.semantic_distance) };
        });
        const candidates = parsed.filter((candidate) => candidate._lexicalMatch ||
          (maxCosineDistance !== null && candidate._distance !== null && candidate._distance <= maxCosineDistance))
          .map(({ _lexicalMatch, _distance, ...candidate }) => candidate);
        await client.query('COMMIT');
        began = false;
        return { query, mode: 'PGVECTOR_HYBRID_RRF', candidates,
          reason: candidates.length ? 'RANKED_ADVISORY_CANDIDATES' : parsed.length ? 'LOW_CONFIDENCE_ABSTAINED' : 'NO_SUPPORTED_MATCH',
          requiresTradeCoreValidation: true };
      } catch (error) {
        if (began) { try { await client.query('ROLLBACK'); } catch { /* connection is unhealthy */ } }
        if (error instanceof RetrievalFault) throw error;
        throw new RetrievalFault('RETRIEVAL_BACKEND_UNAVAILABLE', 'Scoped PostgreSQL retrieval unavailable; no purchase decision was made.', 503);
      } finally { client?.release?.(); }
    },
  });
}
