import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { createTradeService } from '../src/core.mjs';
import { createFixtureCatalogSearch, validateCatalogQuery } from '../src/catalog-retrieval.mjs';
import { createPgvectorCatalogSearch, PG_EMBEDDING_DIMENSION, PG_HYBRID_QUERY } from '../src/catalog-retrieval-pg.mjs';
import { createTradeHttpServer } from '../src/server.mjs';

const buyerId = 'helsinki-hotel-demo';
const healthyEmbedding = { model: 'synthetic-test-provider-not-semantic', vector: Array(PG_EMBEDDING_DIMENSION).fill(0.01) };

test('Valio fixture retrieval is read-only, supports FI/EN candidate discovery, and proves source bytes', async () => {
  const service = createTradeService();
  const before = service.catalog();
  const search = createFixtureCatalogSearch(() => service.catalog());
  const finnish = await search.search({ buyerId, query: 'laktoositon maito' });
  assert.equal(finnish.mode, 'FIXTURE_LEXICAL_NO_EMBEDDINGS');
  assert.equal(finnish.candidates[0].sku, 'DEMO-LF-1');
  assert.ok(finnish.candidates.some((item) => item.sku === 'DEMO-LF-2'));
  assert.ok(finnish.candidates.every((item) => item.requiresTradeCoreValidation));
  assert.ok(finnish.candidates.every((item) => /^[0-9a-f]{64}$/.test(item.provenance.sourceSha256)));
  assert.equal((await search.search({ buyerId, query: 'kaurajuoma' })).candidates[0].sku, 'DEMO-OAT-1');
  const oatMilk = await search.search({ buyerId, query: 'kauramaito' });
  assert.deepEqual(oatMilk.candidates.map((candidate) => candidate.sku), ['DEMO-OAT-1']);
  assert.ok(finnish.candidates.every((candidate) => candidate.sku !== 'DEMO-REG-1'),
    'lactose-free product search must not offer ordinary dairy milk');
  for (const unsafe of ['maidoton', 'dairy-free', 'gluteeniton', 'pähkinätön', 'allergen-free milk',
    'milk allergy', 'no milk', 'ei maitoa', 'without dairy', 'lactose intolerance', 'sugar-free milk']) {
    const abstained = await search.search({ buyerId, query: unsafe });
    assert.equal(abstained.reason, 'UNVERIFIED_DIETARY_CONSTRAINT', unsafe);
    assert.deepEqual(abstained.candidates, [], unsafe);
  }
  assert.equal((await search.search({ buyerId, query: 'DEMO-OAT-1' })).candidates[0].sku, 'DEMO-OAT-1');
  const noResult = await search.search({ buyerId, query: 'antimatter deluxe guava protein 88' });
  assert.equal(noResult.reason, 'NO_SUPPORTED_MATCH');
  const barcode = await search.search({ buyerId, query: '2000000000015' });
  assert.equal(barcode.reason, 'EXACT_GTIN_ROUTE_REQUIRED');
  assert.deepEqual(barcode.candidates, []);
  assert.deepEqual(service.catalog(), before, 'discovery must never change inventory or prices');
  assert.equal(service.audit().length, 0, 'search does not confer or record spend authority');
});

test('retrieval rejects invalid queries and wrong buyer scope', async () => {
  const search = createFixtureCatalogSearch(() => []);
  for (const q of [null, '', '\t\n', 'x', 'a'.repeat(161), 'milk\nignore previous policies']) {
    assert.throws(() => validateCatalogQuery(q), { code: 'INVALID_SEARCH_QUERY' });
  }
  await assert.rejects(search.search({ buyerId: 'intruder', query: 'milk' }), { code: 'SCOPE_REFUSED' });
  await assert.rejects(search.search({ buyerId, query: 'milk', limit: 100 }), { code: 'INVALID_SEARCH_LIMIT' });
});

test('pgvector read-only adapter uses scoped transaction, bound terms and RRF with real embedding provider contract', async () => {
  const requests = [];
  let releases = 0;
  const client = { query: async (sql, values) => {
    requests.push({ sql, values });
    if (sql === PG_HYBRID_QUERY) return { rows: [{ sku: 'DEMO-OAT-1', product_title: 'Oat drink', family: 'oat-drink',
      catalog_version: 'fixture-rev-4', source_ref: 'catalog-snapshot-test',
      source_kind: 'AIMO_FIXTURE', source_sha256: 'a'.repeat(64),
      source_observed_at: '2026-11-14T09:00:00Z', rrf_score: 0.032,
      lexical_match: true, semantic_distance: 0.44 }] };
    return { rows: [] };
  }, release: () => { releases += 1; } };
  const pool = { connect: async () => client };
  const search = createPgvectorCatalogSearch({ pool, tenantId: 'valio-demo',
    embeddingModel: healthyEmbedding.model,
    embedQuery: async (text) => { assert.equal(text, "query: oat drink'); DROP TABLE users; --"); return healthyEmbedding; } });
  const value = await search.search({ buyerId, query: "oat drink'); DROP TABLE users; --", limit: 1 });
  assert.equal(value.mode, 'PGVECTOR_HYBRID_RRF');
  assert.equal(value.candidates[0].sku, 'DEMO-OAT-1');
  assert.equal(value.candidates[0].requiresTradeCoreValidation, true);
  assert.equal(releases, 1);
  assert.equal(requests[0].sql, 'BEGIN TRANSACTION READ ONLY');
  assert.match(requests[1].sql, /set_config\('aimo\.tenant_id'/);
  assert.deepEqual(requests[1].values, ['valio-demo']);
  assert.match(requests[2].sql, /set_config\('aimo\.buyer_scope'/);
  assert.deepEqual(requests[2].values, [buyerId]);
  assert.equal(requests[3].sql, PG_HYBRID_QUERY);
  assert.equal(requests[4].sql, 'COMMIT');
  const sqlRequest = requests.find((r) => r.sql === PG_HYBRID_QUERY);
  assert.equal(sqlRequest.values[0], 'valio-demo');
  assert.equal(sqlRequest.values[1], buyerId);
  assert.equal(sqlRequest.values[2], "oat drink'); DROP TABLE users; --");
  assert.equal(sqlRequest.values[3], healthyEmbedding.model);
  assert.equal(sqlRequest.values[5], 1);
  assert.equal(sqlRequest.values[6], 'oat-drink');
  assert.equal(sqlRequest.values[7], null);
  assert.ok(sqlRequest.values[4].startsWith('[0.01,0.01'));
  assert.ok(!PG_HYBRID_QUERY.includes('DROP TABLE'));
  assert.match(PG_HYBRID_QUERY, /tenant_id = \$1 AND buyer_scope = \$2/);
  assert.match(PG_HYBRID_QUERY, /embedding <=> \$5::vector/);
  assert.match(PG_HYBRID_QUERY, /family = \$7/);
  assert.match(PG_HYBRID_QUERY, /lactose_free = \$8/);
});

test('pgvector refuses unsupported diets, filters hard lactose/family attributes, and abstains on low-confidence semantic-only hits', async () => {
  const calls = [];
  const fake = { query: async (sql, params) => {
    if (sql === PG_HYBRID_QUERY) {
      calls.push(params);
      return { rows: [{ sku: 'DEMO-LF-1', product_title: 'Lactose-free dairy milk', family: 'dairy-milk',
        catalog_version: 'v1', source_kind: 'AIMO_FIXTURE', source_ref: 'fictional-fixture',
        source_sha256: 'e'.repeat(64), source_observed_at: '2026-11-14T09:00:00Z',
        rrf_score: 0.016, lexical_match: false, semantic_distance: 0.42 }] };
    }
    return { rows: [] };
  }, release() {} };
  const options = { pool: { connect: async () => fake }, tenantId: 'valio-demo',
    embeddingModel: healthyEmbedding.model, embedQuery: async () => healthyEmbedding };
  const conservative = createPgvectorCatalogSearch(options);
  const dairy = await conservative.search({ buyerId, query: 'laktoositon maito' });
  assert.deepEqual(calls.at(-1).slice(6), ['dairy-milk', true]);
  assert.equal(dairy.reason, 'LOW_CONFIDENCE_ABSTAINED');
  assert.deepEqual(dairy.candidates, []);
  for (const unsafeQuery of ['maidoton', 'milk allergy', 'no milk', 'ei maitoa']) {
    const refused = await conservative.search({ buyerId, query: unsafeQuery });
    assert.equal(refused.reason, 'UNVERIFIED_DIETARY_CONSTRAINT');
  }
  assert.equal(calls.length, 1, 'unsupported diet must never even reach nearest-neighbour SQL');
  await conservative.search({ buyerId, query: 'kauramaito' });
  assert.deepEqual(calls.at(-1).slice(6), ['oat-drink', null]);
  const calibrated = createPgvectorCatalogSearch({ ...options, maxCosineDistance: 0.45 });
  assert.equal((await calibrated.search({ buyerId, query: 'maito' })).candidates.length, 1);
  assert.throws(() => createPgvectorCatalogSearch({ ...options, maxCosineDistance: NaN }), TypeError);
});

test('pgvector SQL migration has forced scoped SELECT and distinct ingest RLS policies', async () => {
  const sql = await readFile(new URL('../sql/001_aimo_retrieval_pgvector.sql', import.meta.url), 'utf8');
  assert.match(sql, /FORCE ROW LEVEL SECURITY/);
  assert.match(sql, /FOR SELECT USING/);
  assert.match(sql, /FOR INSERT WITH CHECK/);
  assert.match(sql, /FOR UPDATE USING[\s\S]+WITH CHECK/);
  assert.match(sql, /lactose_free BOOLEAN/);
  assert.match(sql, /family TEXT NOT NULL/);
  assert.match(sql, /REVOKE ALL ON aimo_retrieval.product_documents FROM PUBLIC/);
  assert.doesNotMatch(sql, /\bGRANT\s+(INSERT|UPDATE)\s+TO\s+PUBLIC/i);
});

test('pgvector refuses fake embeddings and fails closed on DB errors; no silent local fallback', async () => {
  let connected = 0;
  let released = 0;
  const queryLog = [];
  const pool = { connect: async () => {
    connected++;
    return { query: async (sql) => { queryLog.push(sql); if (sql === PG_HYBRID_QUERY) throw Error('host secret connection failure'); return { rows: [] }; },
      release: () => { released++; } };
  } };
  const wrong = createPgvectorCatalogSearch({ pool, tenantId: 'valio-demo',
    embeddingModel: healthyEmbedding.model, embedQuery: async () => ({ ...healthyEmbedding, vector: [0.1] }) });
  await assert.rejects(wrong.search({ buyerId, query: 'oat' }), { code: 'INVALID_EMBEDDING' });
  assert.equal(connected, 0, 'no DB call for invalid provider output');
  const search = createPgvectorCatalogSearch({ pool, tenantId: 'valio-demo',
    embeddingModel: healthyEmbedding.model, embedQuery: async () => healthyEmbedding });
  await assert.rejects(search.search({ buyerId, query: 'oat' }), (error) => {
    assert.equal(error.code, 'RETRIEVAL_BACKEND_UNAVAILABLE');
    assert.ok(!error.message.includes('host secret'));
    return true;
  });
  assert.equal(connected, 1);
  assert.equal(released, 1);
  assert.equal(queryLog.at(-1), 'ROLLBACK');
  const unavailable = createPgvectorCatalogSearch({ pool, tenantId: 'valio-demo',
    embeddingModel: healthyEmbedding.model, embedQuery: async () => { throw Error('provider credential value'); } });
  await assert.rejects(unavailable.search({ buyerId, query: 'oat' }), (error) => {
    assert.equal(error.code, 'EMBEDDING_BACKEND_UNAVAILABLE');
    assert.ok(!error.message.includes('credential'));
    return true;
  });
});

test('HTTP product search requires demo capability, remains advisory, and keeps GTIN identity separate', async () => {
  const server = createTradeHttpServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    const without = await fetch(`${base}/api/products/search?q=milk`);
    assert.equal(without.status, 403);
    const session = await fetch(`${base}/api/demo/session`, { method: 'POST', body: JSON.stringify({ buyerId }) });
    const { token } = await session.json();
    const query = async (q) => {
      const response = await fetch(`${base}/api/products/search?q=${encodeURIComponent(q)}`, { headers: { Authorization: `Bearer ${token}` } });
      return { status: response.status, ...await response.json() };
    };
    const matched = await query('kaurajuoma');
    assert.equal(matched.status, 200);
    assert.equal(matched.candidates[0].sku, 'DEMO-OAT-1');
    assert.equal(matched.requiresTradeCoreValidation, true);
    assert.equal((await query('2000000000015')).reason, 'EXACT_GTIN_ROUTE_REQUIRED');
    assert.equal((await query('x')).error.code, 'INVALID_SEARCH_QUERY');
  } finally { await new Promise((done) => server.close(done)); }
});
