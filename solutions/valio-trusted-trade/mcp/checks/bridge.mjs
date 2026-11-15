/** Explicit optional SDK qualification; never auto-loaded by the root test walker. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { mkdtemp } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { createTradeClient } from '../trade-client.mjs';

const entry = fileURLToPath(new URL('../server.mjs', import.meta.url));
const need = { family: 'dairy-milk', lactoseFree: true, quantityLitres: 480, deliverBy: '2026-11-16' };
const requirement = { commandKey: 'check-prepare-main-001', budgetCents: 175000,
  requirements: [need, { ...need, family: 'oat-drink', quantityLitres: 240 }] };
const temporary = await mkdtemp('/private/tmp/valio-mcp-check-');
let hostDecision = 'approve', hostAction = 'accept';
const hostMessages = [], stderr = [];
const connect = async (base, stateFile, withHost = true, era = 'modern') => {
  const client = new Client({ name: 'synthetic-sdk-check-host', version: '0.1.0' }, {
    versionNegotiation: { mode: era === 'legacy' ? 'legacy' : { pin: '2026-07-28' } },
    capabilities: withHost ? { elicitation: { form: {} } } : {},
  });
  if (withHost) client.setRequestHandler('elicitation/create', async request => {
    hostMessages.push(request.params.message);
    return hostAction === 'accept' ? { action: 'accept', content: { decision: hostDecision } } : { action: hostAction };
  });
  const transport = new StdioClientTransport({ command: process.execPath, args: [entry], stderr: 'pipe',
    env: { PATH: process.env.PATH ?? '', SUPPLIER_URL: base,
      ...(stateFile ? { VALIO_AGENT_STATE_FILE: stateFile } : {}) }, maxBufferSize: 1048576 });
  transport.stderr.on('data', chunk => stderr.push(chunk.toString()));
  await client.connect(transport, { timeout: 10000 });
  return client;
};
const refused = async promise => {
  let result, rejected = false;
  try { result = await promise; } catch (error) { rejected = true; assert.ok(error); }
  if (!rejected) assert.equal(result.isError, true, 'successful operation must never count as a refusal');
};
const schemaRefused = async promise => {
  let result;
  try { result = await promise; } catch (error) { assert.equal(error.code, -32602); return; }
  assert.equal(result.isError, true);
  assert.equal(result.structuredContent, undefined, 'arguments must fail before bridge HTTP execution');
};
const data = value => { assert.notEqual(value.isError, true, JSON.stringify(value)); assert.equal(value.structuredContent?.ok, true); return value.structuredContent.data; };
let schemaClient;
try {
  schemaClient = await connect('http://127.0.0.1:9');
  const listing = await schemaClient.listTools();
  assert.equal(listing.tools.length, 8);
  for (const tool of listing.tools) {
    assert.equal(tool.inputSchema.additionalProperties, false);
    assert.equal(tool.annotations.openWorldHint, tool.name === 'lookup_valio_mock');
    assert.equal(tool.annotations.idempotentHint, true);
    assert.ok(tool.outputSchema);
  }
  assert.equal(listing.tools.find(t => t.name === 'commit_purchase').annotations.destructiveHint, true);
  assert.equal(listing.tools.find(t => t.name === 'search_products').annotations.readOnlyHint, true);
  await schemaRefused(schemaClient.callTool({ name: 'review_purchase', arguments: { runId: 'R-DEMO-1', commandKey: 'illegal-approve-001', approve: true } }));
  await schemaRefused(schemaClient.callTool({ name: 'settle_purchase', arguments: { runId: 'R-DEMO-1', commandKey: 'illegal-payment-001', decision: 'approve' } }));
  await schemaRefused(schemaClient.callTool({ name: 'prepare_purchase', arguments: { ...requirement, requirements: [{ ...need, quantityLitres: 1.5 }] } }));
  for (const field of ['apiKey', 'customer', 'url']) {
    await schemaRefused(schemaClient.callTool({ name: 'lookup_valio_mock', arguments: {
      products: ['8005803'], requestedDate: '2026-11-16', [field]: 'forbidden-test-value',
    } }));
  }
  await schemaRefused(schemaClient.callTool({ name: 'lookup_valio_mock', arguments: {
    products: ['8005803', '8005803'], requestedDate: '2026-11-16',
  } }));
  await schemaRefused(schemaClient.callTool({ name: 'lookup_valio_mock', arguments: {
    products: ['8005803'], requestedDate: '2026-02-30',
  } }));
  console.log(JSON.stringify({ check: 'official-sdk-discovery-and-strict-inputs', outcome: 'PASS', tools: 8, protocol: '2026-07-28' }));
} finally { await schemaClient?.close(); }

let calls = 0;
await assert.rejects(createTradeClient({ baseUrl: 'https://external.invalid/', fetchImpl() { calls++; } }), { code: 'LOCAL_URL_REQUIRED' });
assert.equal(calls, 0);
const hanging = await createTradeClient({ baseUrl: 'http://127.0.0.1:9', timeoutMs: 40, fetchImpl: () => new Promise(() => {}) });
const started = Date.now();
try { await assert.rejects(hanging.prepare(requirement), { code: 'HTTP_DEADLINE' }); assert.ok(Date.now() - started < 1000); }
finally { hanging.close(); }
console.log(JSON.stringify({ check: 'external-origin-refusal-and-hard-deadline', outcome: 'PASS' }));

if (process.env.VALIO_MCP_CHECK_SCHEMA_ONLY !== '1') {
  const { createTradeRuntime } = await import('../../src/trade-runtime.mjs');
  const { createTradeHttpServer } = await import('../../src/server.mjs');
  let service, server, runtime;
  const startServer = async port => {
    runtime = createTradeRuntime({ stateFile: join(temporary, 'service.sqlite') });
    service = runtime.service;
    server = createTradeHttpServer(undefined, { runtime });
    server.listen(port, '127.0.0.1'); await once(server, 'listening');
  };
  const stopServer = async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); };
  await startServer(0);
  const port = server.address().port;
  const base = 'http://127.0.0.1:' + port;
  const stateFile = join(temporary, 'buyer.sqlite');
  let client;
  const tool = async (name, arguments_) => client.callTool({ name, arguments: arguments_ }, { timeout: 20000 });
  try {
    client = await connect(base, stateFile);
    const prepared = data(await tool('prepare_purchase', requirement));
    const rejectedId = prepared.run.id;
    assert.ok(prepared.nextActions.includes('review_purchase'));
    assert.equal(data(await tool('prepare_purchase', requirement)).run.id, rejectedId);
    await refused(tool('prepare_purchase', { ...requirement, budgetCents: 1 }));
    const before = service.catalog();
    const premature = await tool('commit_purchase', { runId: rejectedId, commandKey: 'premature-order-001' });
    assert.equal(premature.structuredContent.error.code, 'HUMAN_APPROVAL_REQUIRED');
    assert.deepEqual(service.catalog(), before);
    await client.close(); client = await connect(base, stateFile, false);
    await refused(tool('review_purchase', { runId: rejectedId, commandKey: 'missing-host-review-001' }));
    assert.equal(service.quote(prepared.run.quoteId).status, 'AWAITING_HUMAN_APPROVAL');
    await client.close(); client = await connect(base, stateFile);
    hostAction = 'decline';
    const declined = data(await tool('review_purchase', { runId: rejectedId, commandKey: 'declined-review-001' }));
    assert.equal(declined.approval, 'NOT_GRANTED');
    assert.equal(service.quote(prepared.run.quoteId).status, 'AWAITING_HUMAN_APPROVAL');
    hostAction = 'accept'; hostDecision = 'reject';
    data(await tool('review_purchase', { runId: rejectedId, commandKey: 'rejected-review-001' }));
    assert.equal(service.quote(prepared.run.quoteId).status, 'REJECTED');

    const ready = data(await tool('prepare_purchase', { ...requirement, commandKey: 'check-prepare-main-002' }));
    const runId = ready.run.id;
    hostDecision = 'approve';
    data(await tool('review_purchase', { runId, commandKey: 'accepted-review-002' }));
    assert.equal(service.quote(ready.run.quoteId).status, 'APPROVED');
    assert.ok(hostMessages.some(message => message.includes(ready.run.quoteId)));
    await client.close(); await stopServer(); await startServer(port);
    client = await connect(base, stateFile);
    assert.equal(data(await tool('purchase_status', { runId })).run.id, runId);
    const committed = data(await tool('commit_purchase', { runId, commandKey: 'signed-order-main-002' }));
    assert.ok(committed.run.orderId);
    const stock = service.catalog();
    assert.equal(data(await tool('commit_purchase', { runId, commandKey: 'signed-order-main-002' })).run.orderId, committed.run.orderId);
    assert.deepEqual(service.catalog(), stock);
    hostAction = 'decline';
    data(await tool('settle_purchase', { runId, commandKey: 'declined-payment-002' }));
    assert.equal(service.paymentJournal().length, 0);
    hostAction = 'accept';
    data(await tool('settle_purchase', { runId, commandKey: 'accepted-payment-002' }));
    const count = service.paymentJournal().length;
    assert.ok(count > 0);
    data(await tool('settle_purchase', { runId, commandKey: 'accepted-payment-002' }));
    assert.equal(service.paymentJournal().length, count);
    assert.ok(hostMessages.some(message => message.includes(committed.run.orderId) && message.includes('payment')));
    data(await tool('cancel_purchase', { runId, commandKey: 'refund-order-main-002' }));
    assert.equal(service.demoWallet().buyerBalanceCents, 250000);
    assert.equal(service.paymentJournalVerify().valid, true);
    const receipt = data(await tool('purchase_status', { runId }));
    assert.equal(receipt.run.id, runId);
    assert.equal(service.order(committed.run.orderId).status, 'SIMULATED_CANCELLED');
    assert.ok(!JSON.stringify(receipt).includes('privateKey'));
    assert.ok(!JSON.stringify(receipt).includes('token'));
    await client.close(); client = await connect(base, stateFile);
    assert.equal(data(await tool('purchase_status', { runId })).run.orderId, committed.run.orderId);
    const exception = { commandKey: 'exception-prepare-004', budgetCents: 1,
      requirements: [{ ...need, quantityLitres: 1 }] };
    const exceptional = data(await tool('prepare_purchase', exception));
    assert.ok(exceptional.quote.budgetException.additionalCents > 0);
    data(await tool('review_purchase', { runId: exceptional.run.id, commandKey: 'exception-review-004' }));
    data(await tool('commit_purchase', { runId: exceptional.run.id, commandKey: 'exception-commit-004' }));
    data(await tool('cancel_purchase', { runId: exceptional.run.id, commandKey: 'exception-refund-004' }));
    const future = data(await tool('prepare_purchase', { ...exception, commandKey: 'exception-prepare-005' }));
    const futureCommit = await tool('commit_purchase', { runId: future.run.id, commandKey: 'unapproved-future-005' });
    assert.equal(futureCommit.isError, true);
    assert.equal(futureCommit.structuredContent.error.code, 'CALLER_APPROVAL_MISSING');
    const promptsBeforeStale = hostMessages.length;
    runtime.execute(true, () => service.simulatePriceChange({ sku: 'DEMO-LF-1', priceCents: 175 }));
    const stale = await tool('review_purchase', { runId: future.run.id, commandKey: 'stale-review-main-005' });
    assert.equal(stale.structuredContent.error.code, 'QUOTE_STALE');
    assert.equal(hostMessages.length, promptsBeforeStale);
    await client.close(); client = await connect(base, stateFile, true, 'legacy');
    const legacy = data(await tool('prepare_purchase', { ...requirement, commandKey: 'legacy-prepare-006' }));
    hostAction = 'decline';
    assert.equal(data(await tool('review_purchase', { runId: legacy.run.id, commandKey: 'legacy-review-006' })).approval, 'NOT_GRANTED');
    assert.equal(service.quote(legacy.run.quoteId).status, 'AWAITING_HUMAN_APPROVAL');
    console.log(JSON.stringify({ check: 'official-sdk-host-interaction-signed-trade-settlement-refund-and-server-client-resume', outcome: 'PASS',
      syntheticHostPrompts: hostMessages.length, realProviderCalls: 0, quoteScopedBudgetException: true, legacyHostDecline: true }));
  } finally { await client?.close(); await stopServer(); }
  await assert.rejects(createTradeClient({ baseUrl: 'http://127.0.0.1:9', stateFile }), { code: 'CLIENT_STATE_INVALID' });
}
assert.ok(stderr.every(line => !/BEGIN PRIVATE KEY|Authorization: Bearer/.test(line)));
