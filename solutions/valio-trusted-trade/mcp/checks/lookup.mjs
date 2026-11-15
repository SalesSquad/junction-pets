/** Focused eighth-tool SDK test: injected observer only, no sponsor requests. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { createTradeHttpServer } from '../../src/server.mjs';
import { createTradeService } from '../../src/core.mjs';

const entry = fileURLToPath(new URL('../server.mjs', import.meta.url));
const input = { products: ['8005803'], requestedDate: '2026-11-16' };
const secretMarker = 'TEST_ONLY_NEVER_PROPAGATE';
let observerCalls = 0;
const fixture = () => ({
  mode: 'SPONSOR_MOCK_READ_ONLY', requiresTradeCoreValidation: true, apiKey: secretMarker,
  availability: { customer: secretMarker, products: [{ productId: input.products[0] }] },
  prices: { customerId: secretMarker, currency: 'EUR', products: [{
    productId: input.products[0], quantity: 1, catalogPrice: { value: 174.29, valueWithTax: 197.82, extra: secretMarker },
    netPriceFound: false, error: false,
  }] },
  classifications: [{ productId: input.products[0], purchasingAuthority: 'NONE',
    availability: 'UNQUALIFIED_SOURCE_ONLY', cutoff: 'PASSED', netPrice: 'UNCONFIRMED',
    scheduleFacts: Array.from({ length: 6 }, () => ({ salesBlocked: false,
      stock: 'UNKNOWN_TERMINAL_SENTINEL', sourceAmount: 999999, sourceUnit: 'BOX', unitInterpretation: 'UNMAPPED' })) }],
  provenance: { provider: 'VALIO_JUNCTION_MOCK_API', origin: 'https://junction26.valioaimo.fi',
    observedAt: '2026-11-15T12:00:00Z', requestedDate: input.requestedDate,
    availability: { endpoint: '/api/availability', sha256: 'a'.repeat(64), providerTime: '2026-11-15T12:00:00Z' },
    prices: { endpoint: '/api/price', sha256: 'b'.repeat(64), pricingDate: input.requestedDate },
    interpretation: 'OPAQUE_SOURCE_FACTS_TERMINAL_999999_IS_UNKNOWN_STOCK',
    limitations: ['NO_PURCHASING_AUTHORITY', 'UNITS_AND_PRICE_OBJECTS_UNMAPPED'], extra: secretMarker },
  cache: { hit: false, ageMs: 0, ttlMs: 30000 },
});
let malformedPrice = false;
const valioMockPort = { observe: async value => {
  observerCalls++; assert.deepEqual(value, input);
  const result = fixture();
  if (malformedPrice) result.prices = { currency: 'not-a-currency', products: [{ productId: input.products[0],
    catalogPrice: { value: '174,29', valueWithTax: {} }, netPriceFound: 'false', error: null }] };
  return result;
} };
const open = async observer => {
  const service = createTradeService();
  const server = createTradeHttpServer(service, { valioMockPort: observer });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const client = new Client({ name: 'mock-observation-check', version: '0.1.0' }, {
    versionNegotiation: { mode: { pin: '2026-07-28' } },
  });
  const stderr = [];
  const transport = new StdioClientTransport({ command: process.execPath, args: [entry], stderr: 'pipe',
    env: { PATH: process.env.PATH ?? '', SUPPLIER_URL: 'http://127.0.0.1:' + server.address().port } });
  transport.stderr.on('data', chunk => stderr.push(chunk.toString()));
  await client.connect(transport, { timeout: 10000 });
  return { client, service, async close() {
    await client.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
    assert.ok(stderr.every(value => !value.includes(secretMarker)));
  } };
};
const schemaRefused = async value => {
  let result;
  try { result = await value; } catch (error) { assert.equal(error.code, -32602); return; }
  assert.equal(result.isError, true);
  assert.equal(result.structuredContent, undefined, 'must stop before bridge/observer execution');
};
let active;
try {
  active = await open(valioMockPort);
  const { tools } = await active.client.listTools();
  assert.equal(tools.length, 8);
  const lookup = tools.find(t => t.name === 'lookup_valio_mock');
  assert.deepEqual(lookup.annotations, { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true });
  assert.equal(lookup.inputSchema.additionalProperties, false);
  for (const field of ['apiKey', 'customer', 'url']) {
    await schemaRefused(active.client.callTool({ name: 'lookup_valio_mock', arguments: { ...input, [field]: secretMarker } }));
  }
  await schemaRefused(active.client.callTool({ name: 'lookup_valio_mock', arguments: { ...input, products: ['8005803', '8005803'] } }));
  await schemaRefused(active.client.callTool({ name: 'lookup_valio_mock', arguments: { ...input, requestedDate: '2026-02-30' } }));
  for (const product of ['name@example.invalid','https://example.invalid','1234567890123']) await schemaRefused(active.client.callTool({ name: 'lookup_valio_mock', arguments: { ...input, products: [product] } }));
  assert.equal(observerCalls, 0);
  const before = active.service.catalog();
  const result = await active.client.callTool({ name: 'lookup_valio_mock', arguments: input });
  assert.notEqual(result.isError, true, JSON.stringify(result));
  const out = result.structuredContent.data;
  assert.equal(out.mode, 'SPONSOR_MOCK_READ_ONLY');
  assert.equal(out.requiresTradeCoreValidation, true);
  assert.equal(out.products[0].purchasingAuthority, 'NONE');
  assert.equal(out.products[0].availability, 'UNQUALIFIED_SOURCE_ONLY');
  assert.equal(out.products[0].cutoff, 'PASSED');
  assert.equal(out.products[0].scheduleLineCount, 6);
  assert.equal(out.products[0].scheduleFacts.length, 5);
  assert.equal(out.products[0].scheduleFactsTruncated, true);
  assert.equal(out.products[0].scheduleFacts[0].stock, 'UNKNOWN_TERMINAL_SENTINEL');
  assert.deepEqual(out.products[0].observedPrice, { currency: 'EUR', catalogValue: 174.29, catalogValueWithTax: 197.82,
    netPriceFound: false, error: false, interpretation: 'OPAQUE_SOURCE_ONLY_NOT_NET_OFFER' });
  assert.equal(out.provenance.prices.sha256, 'b'.repeat(64));
  assert.ok(!JSON.stringify(result).includes(secretMarker));
  assert.deepEqual(active.service.catalog(), before);
  assert.equal(active.service.audit().filter(e => e.event === 'ORDER_SIMULATED').length, 0);
  malformedPrice = true;
  const unmapped = await active.client.callTool({ name: 'lookup_valio_mock', arguments: input });
  assert.notEqual(unmapped.isError, true);
  assert.deepEqual(unmapped.structuredContent.data.products[0].observedPrice, { currency: 'UNMAPPED', catalogValue: 'UNMAPPED',
    catalogValueWithTax: 'UNMAPPED', netPriceFound: 'UNMAPPED', error: 'UNMAPPED', interpretation: 'OPAQUE_SOURCE_ONLY_NOT_NET_OFFER' });
  assert.equal(observerCalls, 2);
  await active.close(); active = null;
  active = await open(null);
  const unavailable = await active.client.callTool({ name: 'lookup_valio_mock', arguments: input });
  assert.equal(unavailable.isError, true);
  assert.equal(unavailable.structuredContent.error.code, 'INTEGRATION_NOT_CONFIGURED');
  assert.equal(unavailable.structuredContent.error.retryable, false);
  assert.match(unavailable.structuredContent.error.nextActions.join(' '), /operator.*server-side/i);
  assert.equal(observerCalls, 2);
  console.log(JSON.stringify({ check: 'official-sdk-read-only-sponsor-mock-observation-tool', outcome: 'PASS',
    tools: 8, fakeObserverCalls: observerCalls, realProviderCalls: 0, credentialsAccepted: false,
    rawCustomerOrSecretOutput: false, fixtureCatalogPromoted: false }));
} finally { await active?.close(); }
