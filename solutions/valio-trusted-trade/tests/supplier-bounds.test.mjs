import test from 'node:test';
import assert from 'node:assert/strict';
import { createReadOnlySupplierPort } from '../src/supplier-port.mjs';

const product = { sku: 'SUPPLIER-SKU-1', priceCents: 122, availableUnits: 12, sourceVersion: 'v1', currency: 'EUR' };
const json = (value) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const port = (fetchImpl) => createReadOnlySupplierPort({ baseUrl: 'https://example.test', fetchImpl, timeoutMs: 100 });

test('canonical current supplier fixture remains accepted exactly', async () => {
  const payload = { products: [product] };
  assert.deepEqual(await port(async () => json(payload)).searchCatalog('milk'), payload);
});

test('supplier reads reject invalid status, media, JSON, object and typed facts', async () => {
  for (const makeResponse of [
    () => ({ status: undefined }),
    () => new Response('{}', { headers: { 'Content-Type': 'text/html' } }),
    () => new Response('{broken', { headers: { 'Content-Type': 'application/json' } }),
    () => json([]),
    () => json({ products: [{ ...product, priceCents: 1.2 }] }),
    () => json({ products: [{ ...product, availableUnits: -1 }] }),
    () => json({ products: [{ ...product, sourceVersion: '' }] }),
    () => json({ products: Array.from({ length: 101 }, () => product) }),
  ]) await assert.rejects(port(async () => makeResponse()).searchCatalog('milk'), { code: 'SUPPLIER_SCHEMA_INVALID' });
});

test('supplier read bounds declared and streamed bytes', async () => {
  for (const headers of [{ 'Content-Length': '262145' }, {}]) {
    await assert.rejects(port(async () => new Response(' '.repeat(262145), {
      headers: { 'Content-Type': 'application/json', ...headers },
    })).searchCatalog('milk'), { code: 'SUPPLIER_RESPONSE_TOO_LARGE' });
  }
});

test('timeout bounds both stalled fetch and stalled response body without transport error leakage', async () => {
  for (const fetchImpl of [
    () => new Promise(() => {}),
    async () => new Response(new ReadableStream({ start() {} }), { headers: { 'Content-Type': 'application/json' } }),
  ]) await assert.rejects(port(fetchImpl).searchCatalog('milk'), (error) => error.code === 'SUPPLIER_TIMEOUT' && error.details.retryable === true);
  await assert.rejects(port(async () => { throw new Error('SECRET upstream diagnostic'); }).searchCatalog('milk'), (error) => error.code === 'SUPPLIER_UNAVAILABLE' && !error.message.includes('SECRET'));
  await assert.rejects(port(async () => new Response('SECRET', { status: 429 })).searchCatalog('milk'), (error) => error.code === 'SUPPLIER_UNAVAILABLE' && error.details.retryable === true && !error.message.includes('SECRET'));
});
