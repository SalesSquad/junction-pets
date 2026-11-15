import test from 'node:test';
import assert from 'node:assert/strict';
import { createReadOnlySupplierPort } from '../src/supplier-port.mjs';

const jsonResponse = (value) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });

test('independent vendor-neutral adapter supports typed supplier search without write capability', async () => {
  let seen;
  const port = createReadOnlySupplierPort({
    baseUrl: 'http://127.0.0.1:1234/api',
    fetchImpl: async (url, init) => {
      seen = { url: String(url), method: init.method, signal: init.signal, redirect: init.redirect };
      return jsonResponse({ products: [{ sku: 'SUPPLIER-SKU-1', priceCents: 122, availableUnits: 12, sourceVersion: 'v1', currency: 'EUR' }] });
    },
  });
  const response = await port.searchCatalog('lactose free / milk');
  assert.equal(response.products[0].priceCents, 122);
  assert.match(seen.url, /q=lactose%20free%20%2F%20milk/);
  assert.equal(seen.method, 'GET');
  assert.equal(seen.redirect, 'error');
  assert.equal(port.writesEnabled, false);
  await assert.rejects(port.placeOrder({ buyer: 'attacker' }), { code: 'EXTERNAL_ORDER_DISABLED' });
});

test('supplier adapter rejects cleartext network endpoints and malformed supplier payloads', async () => {
  assert.throws(() => createReadOnlySupplierPort({ baseUrl: 'http://untrusted.example' }), { code: 'INVALID_PROVIDER_URL' });
  assert.throws(() => createReadOnlySupplierPort({ baseUrl: 'https://me:secret@untrusted.example' }), { code: 'INVALID_PROVIDER_URL' });
  const bad = createReadOnlySupplierPort({ baseUrl: 'https://example.test', fetchImpl: async () => jsonResponse({ products: 'not-an-array' }) });
  await assert.rejects(bad.searchCatalog('milk'), { code: 'SUPPLIER_SCHEMA_INVALID' });
  const omittedVersion = createReadOnlySupplierPort({ baseUrl: 'https://example.test', fetchImpl: async () => jsonResponse({ products: [{ sku: 'SKU1', priceCents: 999, availableUnits: 20, currency: 'EUR' }] }) });
  await assert.rejects(omittedVersion.searchCatalog('milk'), { code: 'SUPPLIER_SCHEMA_INVALID' });
});
