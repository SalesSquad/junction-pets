import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { fork } from 'node:child_process';
import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { mkdtemp, realpath, stat, chmod, rm, readFile, writeFile, access } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { DatabaseSync } from 'node:sqlite';
import { createPersistentTradeServer } from '../src/server.mjs';
import { createTradeRuntime } from '../src/trade-runtime.mjs';
import { createTradeService, FIXTURE_CATALOG } from '../src/core.mjs';
import { makeDemoMandatePayload, signDemoEnvelope } from '../src/trust-envelope.mjs';

const buyerId = 'helsinki-hotel-demo';
const need = { family: 'dairy-milk', quantityLitres: 1, lactoseFree: true, deliverBy: '2026-11-16' };
const root = async () => realpath(await mkdtemp(join(tmpdir(), 'valio-persistent-http-')));
const call = async (base, path, body, token, key) => {
  const response = await fetch(base + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(key ? { 'Idempotency-Key': key } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) });
  return { status: response.status, replayed: response.headers.get('idempotency-replayed'), body: await response.json() };
};
const ok = async promise => { const result = await promise; assert.ok(result.status < 400, result.body.error?.code); return result.body; };
const session = async base => (await ok(call(base, '/api/demo/session', { buyerId }))).token;
async function listen(stateFile, options = {}) {
  const server = createPersistentTradeServer({ stateFile, ...options });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  return { server, base: 'http://127.0.0.1:' + server.address().port };
}
async function close(server) {
  if (!server?.listening) return;
  server.closeAllConnections();
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}
function checkpoint(stateFile) {
  const db = new DatabaseSync(stateFile, { readOnly: true });
  try { const row = db.prepare('SELECT body FROM trade_runtime WHERE singleton=1').get(); return { text: row.body, value: JSON.parse(row.body) }; }
  finally { db.close(); }
}
async function signedQuote(base, token, { large = false } = {}) {
  const plan = (await ok(call(base, '/api/plans', { buyerId, budgetCents: 250000, requirements: [
    { ...need, quantityLitres: large ? 480 : 12 }, { ...need, family: 'oat-drink', quantityLitres: large ? 240 : 8 },
  ] }, token, 'persistent-plan-' + randomUUID()))).plan;
  let quote = (await ok(call(base, '/api/plans/' + plan.id + '/quotes', { buyerId, optionId: 'cost' }, token, 'persistent-quote-' + randomUUID()))).quote;
  if (quote.approvalRequired) quote = (await ok(call(base, '/api/quotes/' + quote.id + '/approval', { buyerId, decision: 'approve' }, token, 'persistent-approval-001'))).quote;
  const pair = generateKeyPairSync('ed25519');
  const jwk = pair.publicKey.export({ format: 'jwk' });
  const registered = await ok(call(base, '/api/trust/buyer-key', { buyerId, publicJwk: { kty: jwk.kty, crv: jwk.crv, x: jwk.x } }, token));
  const { signedOffer } = await ok(call(base, '/api/quotes/' + quote.id + '/offer', { buyerId }, token));
  const signedMandate = signDemoEnvelope(pair.privateKey, registered.kid,
    makeDemoMandatePayload({ quote, signedOffer, now: Date.now(), nonce: randomUUID() }));
  const handshakeBody = { buyerId, signedMandate };
  const handshake = await ok(call(base, '/api/quotes/' + quote.id + '/handshake', handshakeBody, token, 'persistent-handshake-001'));
  assert.equal(handshake.proof.verification.valid, true);
  return { quote, handshake, handshakeBody };
}

// Every DB below is created in a fresh private temporary directory owned by this test.
test('real HTTP restarts preserve ownership, approval, signer, nonce, order and balanced refund', { timeout: 30000 }, async () => {
  const dir = await root(), stateFile = join(dir, 'state.sqlite');
  let running;
  try {
    running = await listen(stateFile);
    const token = await session(running.base), other = await session(running.base);
    const fixture = await signedQuote(running.base, token, { large: true });
    const publicKeys = await ok(call(running.base, '/.well-known/trusted-trade/jwks.json'));
    await close(running.server); running = await listen(stateFile);
    assert.deepEqual(await ok(call(running.base, '/.well-known/trusted-trade/jwks.json')), publicKeys);
    const quote = (await ok(call(running.base, '/api/quotes/' + fixture.quote.id))).quote;
    assert.equal(quote.snapshotId, fixture.quote.snapshotId);
    assert.equal(quote.status, 'APPROVED');
    const repeatedApproval = await call(running.base, '/api/quotes/' + quote.id + '/approval', { buyerId, decision: 'approve' }, token, 'persistent-approval-001');
    assert.equal(repeatedApproval.status, 200); assert.equal(repeatedApproval.replayed, 'true');
    const foreign = await call(running.base, '/api/quotes/' + quote.id + '/offer', { buyerId }, other);
    assert.equal(foreign.status, 403); assert.equal(foreign.body.error.code, 'BUYER_MISMATCH');
    const repeatedHandshake = await call(running.base, '/api/quotes/' + quote.id + '/handshake', fixture.handshakeBody, token, 'persistent-handshake-001');
    assert.equal(repeatedHandshake.replayed, 'true'); assert.deepEqual(repeatedHandshake.body, fixture.handshake);
    assert.equal((await call(running.base, '/api/quotes/' + quote.id + '/handshake', fixture.handshakeBody, token, 'new-mandate-command-001')).body.error.code, 'MANDATE_REPLAY');
    const orderRequest = { buyerId, quoteId: quote.id, idempotencyKey: 'persistent-domain-order-001' };
    const order = (await ok(call(running.base, '/api/orders', orderRequest, token))).order;
    const paymentPath = '/api/orders/' + order.id;
    const proposal = (await ok(call(running.base, paymentPath + '/payment', undefined, token))).proposal;
    await ok(call(running.base, paymentPath + '/payment-approval', { buyerId, decision: 'approve', proposalDigest: proposal.digest }, token));
    const instruction = { buyerId, idempotencyKey: 'persistent-domain-payment-001' };
    const paid = await ok(call(running.base, paymentPath + '/settlement', instruction, token));
    const stock = (await ok(call(running.base, '/api/catalog'))).products;
    const journal = await ok(call(running.base, '/api/demo/ledger/verify', undefined, token));
    await close(running.server); running = await listen(stateFile);
    assert.equal((await ok(call(running.base, '/api/orders', orderRequest, token))).order.idempotentReplay, true);
    const replay = await ok(call(running.base, paymentPath + '/settlement', instruction, token));
    assert.equal(replay.idempotentReplay, true); assert.equal(replay.transfer.id, paid.transfer.id);
    assert.equal(replay.wallet.buyerBalanceCents, paid.wallet.buyerBalanceCents);
    assert.deepEqual((await ok(call(running.base, '/api/catalog'))).products, stock);
    assert.equal((await ok(call(running.base, '/api/demo/ledger/verify', undefined, token))).journalEntries, journal.journalEntries);
    await ok(call(running.base, paymentPath + '/cancel', { buyerId }, token));
    await close(running.server); running = await listen(stateFile);
    const refunded = await ok(call(running.base, paymentPath + '/settlement', instruction, token));
    assert.equal(refunded.transfer.status, 'SIMULATED_REFUNDED'); assert.equal(refunded.wallet.buyerBalanceCents, 250000);
    assert.equal((await ok(call(running.base, '/api/demo/ledger/verify', undefined, token))).valid, true);
    await close(running.server); running = null;
    assert.equal(checkpoint(stateFile).text.includes(token), false, 'bearer must be hashed at rest');
  } finally { await close(running?.server); await rm(dir, { recursive: true, force: true }); }
});

test('two HTTP instances refresh the same DB revision and serialize competing stock commitments', { timeout: 20000 }, async () => {
  const dir = await root(), stateFile = join(dir, 'state.sqlite');
  let first, second;
  try {
    first = await listen(stateFile, { serviceFactory: () => createTradeService({ initialCatalog: FIXTURE_CATALOG.map(p => ({ ...p,
      unitsAvailable: p.sku === 'DEMO-LF-1' ? 1 : 0 })) }) });
    second = await listen(stateFile);
    const a = await session(first.base), b = await session(second.base);
    const qa = (await ok(call(first.base, '/api/quotes', { buyerId, need, budgetCents: 10000 }, a))).quote;
    const qb = (await ok(call(second.base, '/api/quotes', { buyerId, need, budgetCents: 10000 }, b))).quote;
    assert.equal(qa.snapshotId, qb.snapshotId);
    const result = await Promise.all([
      call(first.base, '/api/orders', { buyerId, quoteId: qa.id, idempotencyKey: 'competing-stock-first' }, a),
      call(second.base, '/api/orders', { buyerId, quoteId: qb.id, idempotencyKey: 'competing-stock-second' }, b),
    ]);
    assert.deepEqual(result.map(r => r.status).sort(), [201, 409]);
    assert.equal(result.find(r => r.status === 409).body.error.code, 'QUOTE_STALE');
    for (const base of [first.base, second.base]) {
      assert.equal((await ok(call(base, '/api/catalog'))).products.find(p => p.sku === 'DEMO-LF-1').unitsAvailable, 0);
      assert.equal((await ok(call(base, '/api/audit?limit=100'))).receipts.filter(e => e.event === 'ORDER_SIMULATED').length, 1);
    }
  } finally { await close(first?.server); await close(second?.server); await rm(dir, { recursive: true, force: true }); }
});

test('before-COMMIT failure returns no creation ACK and rolls back owner/cache/domain state', { timeout: 15000 }, async () => {
  const dir = await root(), stateFile = join(dir, 'state.sqlite');
  let armed = false, running;
  try {
    running = await listen(stateFile, { storeOptions: { beforeCommit() {
      if (armed) { armed = false; throw Error('test-only failure before durable commit'); }
    } } });
    const token = await session(running.base);
    armed = true;
    const body = { buyerId, need, budgetCents: 10000 }, command = 'failed-review-command-001';
    const failed = await call(running.base, '/api/reviews', body, token, command);
    assert.equal(failed.status, 500); assert.notEqual(failed.status, 201);
    const state = checkpoint(stateFile).value;
    assert.equal(state.core.quotes.length, 0); assert.equal(state.core.reviews.length, 0);
    assert.equal(state.http.quoteOwners.length, 0); assert.equal(state.http.reviewOwners.length, 0); assert.equal(state.http.requestReplay.length, 0);
    const retry = await call(running.base, '/api/reviews', body, token, command);
    assert.equal(retry.status, 201); assert.equal(retry.replayed, null);
    const replay = await call(running.base, '/api/reviews', body, token, command);
    assert.equal(replay.status, 201); assert.equal(replay.replayed, 'true'); assert.equal(replay.body.quote.id, retry.body.quote.id);
    assert.equal(checkpoint(stateFile).value.core.quotes.length, 1);
  } finally { await close(running?.server); await rm(dir, { recursive: true, force: true }); }
});

async function childServer(stateFile, marker, stopAt) {
  const child = fork(fileURLToPath(new URL('./fixtures/persistent-child.mjs', import.meta.url)), [stateFile, marker, stopAt],
    { env: { ...process.env, VALIO_PERSISTENT_TEST_CHILD: '1' }, stdio: ['ignore', 'ignore', 'pipe', 'ipc'] });
  let stderr = '';
  child.stderr.on('data', data => { stderr = (stderr + data).slice(-2000); });
  let ready;
  try { ready = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('Disposable HTTP child did not become ready: ' + stderr)), 10000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', () => { clearTimeout(timer); reject(Error('Disposable child exited before readiness: ' + stderr)); });
    child.on('message', value => { if (value?.type === 'ready') { clearTimeout(timer); resolve(value); } });
  }); } catch (error) { await stopChild(child); throw error; }
  return { child, base: 'http://127.0.0.1:' + ready.port };
}
async function killAfterCommit(child, marker, request) {
  let settled = false;
  const pending = request.then(value => { settled = true; return { value }; }, error => { settled = true; return { error }; });
  const deadline = Date.now() + 10000;
  while (true) {
    try { await access(marker); break; } catch { if (Date.now() >= deadline) throw Error('No durable commit marker before child kill'); await delay(10); }
  }
  assert.equal(await readFile(marker, 'utf8'), 'DURABLE_COMMIT_BEFORE_HTTP_ACK');
  assert.equal(settled, false, 'the durable commit must precede any HTTP ACK');
  const exited = once(child, 'exit');
  assert.equal(child.kill('SIGKILL'), true, 'only this known task-created child is killed');
  assert.equal((await exited)[1], 'SIGKILL');
  const lost = await pending; assert.ok(lost.error, 'the first reply is actually lost');
}
async function stopChild(child) {
  if (child && child.exitCode === null && child.signalCode === null) {
    const exited = once(child, 'exit'); child.kill('SIGKILL'); await exited;
  }
}

test('actual SIGKILL after COMMIT before ACK replays exactly one order and one payment', { timeout: 45000 }, async () => {
  const dir = await root(), stateFile = join(dir, 'state.sqlite');
  let running, child;
  try {
    running = await childServer(stateFile, join(dir, 'order-committed'), 'order'); child = running.child;
    const token = await session(running.base);
    const { quote } = await signedQuote(running.base, token);
    const orderBody = { buyerId, quoteId: quote.id, idempotencyKey: 'kill9-domain-order-001' };
    await killAfterCommit(child, join(dir, 'order-committed'), call(running.base, '/api/orders', orderBody, token, 'kill9-order-command-001'));
    running = await childServer(stateFile, join(dir, 'payment-committed'), 'payment'); child = running.child;
    const replayed = await call(running.base, '/api/orders', orderBody, token, 'kill9-order-command-001');
    assert.equal(replayed.status, 201); assert.equal(replayed.replayed, 'true');
    const order = replayed.body.order, path = '/api/orders/' + order.id;
    const proposal = (await ok(call(running.base, path + '/payment', undefined, token))).proposal;
    await ok(call(running.base, path + '/payment-approval', { buyerId, decision: 'approve', proposalDigest: proposal.digest }, token));
    const instruction = { buyerId, idempotencyKey: 'kill9-domain-payment-001' };
    await killAfterCommit(child, join(dir, 'payment-committed'), call(running.base, path + '/settlement', instruction, token, 'kill9-payment-command-001'));
    running = await listen(stateFile);
    const paid = await call(running.base, path + '/settlement', instruction, token, 'kill9-payment-command-001');
    assert.equal(paid.status, 201); assert.equal(paid.replayed, 'true');
    assert.equal(paid.body.wallet.buyerBalanceCents, 250000 - order.totalCents);
    assert.equal((await ok(call(running.base, '/api/orders', orderBody, token))).order.idempotentReplay, true);
    const state = checkpoint(stateFile).value;
    assert.equal(state.core.orders.length, 1); assert.equal(state.core.settlement.transfers.length, 1);
    assert.equal(state.core.audit.filter(e => e.event === 'ORDER_SIMULATED').length, 1);
    assert.equal(state.core.audit.filter(e => e.event === 'DEMO_MONEY_TRANSFER_SETTLED').length, 1);
    assert.equal((await ok(call(running.base, '/api/demo/ledger/verify', undefined, token))).valid, true);
    await ok(call(running.base, path + '/cancel', { buyerId }, token));
    assert.equal((await ok(call(running.base, '/api/demo/wallet', undefined, token))).wallet.buyerBalanceCents, 250000);
  } finally { await stopChild(child); await close(running?.server); await rm(dir, { recursive: true, force: true }); }
});

test('private files, foreign/corrupt DB refusal and verified no-overwrite backup reopen', { timeout: 20000 }, async () => {
  const dir = await root(), stateFile = join(dir, 'state.sqlite');
  let runtime, running;
  try {
    runtime = createTradeRuntime({ stateFile });
    assert.equal((await stat(dir)).mode & 0o777, 0o700); assert.equal((await stat(stateFile)).mode & 0o777, 0o600);
    for (const suffix of ['-wal', '-shm']) assert.equal((await stat(stateFile + suffix)).mode & 0o777, 0o600);
    const quote = runtime.execute(true, () => runtime.service.requestQuote({ buyerId, need, budgetCents: 10000 }));
    const backup = join(dir, 'backup.sqlite');
    assert.equal((await runtime.backup(backup)).integrity, 'ok');
    const prior = await readFile(backup);
    await assert.rejects(runtime.backup(backup), { code: 'BACKUP_EXISTS' });
    assert.equal(Buffer.compare(await readFile(backup), prior), 0);
    runtime.close(); runtime = null;
    running = await listen(backup);
    const restored = (await ok(call(running.base, '/api/quotes/' + quote.id))).quote;
    assert.equal(restored.snapshotId, quote.snapshotId); assert.equal(restored.totalCents, quote.totalCents);
    await close(running.server); running = null;
    await chmod(backup, 0o644);
    assert.throws(() => createPersistentTradeServer({ stateFile: backup }), { code: 'STATE_PATH_UNSAFE' });
    await chmod(backup, 0o600);
    await chmod(dir, 0o755);
    assert.throws(() => createPersistentTradeServer({ stateFile: backup }), { code: 'STATE_PATH_UNSAFE' });
    await chmod(dir, 0o700);
    const foreignPath = join(dir, 'foreign.sqlite'), foreign = new DatabaseSync(foreignPath);
    foreign.exec('CREATE TABLE other_application(id INTEGER PRIMARY KEY);'); foreign.close(); await chmod(foreignPath, 0o600);
    assert.throws(() => createPersistentTradeServer({ stateFile: foreignPath }), { code: 'STATE_FOREIGN_DATABASE' });
    const checkForeign = new DatabaseSync(foreignPath, { readOnly: true });
    try { assert.deepEqual(checkForeign.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map(r => r.name), ['other_application']); }
    finally { checkForeign.close(); }
    const emptyPath = join(dir, 'empty.sqlite');
    await writeFile(emptyPath, '', { mode: 0o600 });
    assert.throws(() => createPersistentTradeServer({ stateFile: emptyPath }), { code: 'STATE_CORRUPT' });
    const missingPath = join(dir, 'missing.sqlite');
    const initialized = createTradeRuntime({ stateFile: missingPath }); initialized.close();
    const missing = new DatabaseSync(missingPath); missing.exec('DELETE FROM trade_runtime'); missing.close();
    assert.throws(() => createPersistentTradeServer({ stateFile: missingPath }), { code: 'STATE_CORRUPT' });
    const stillMissing = new DatabaseSync(missingPath, { readOnly: true });
    try { assert.equal(stillMissing.prepare('SELECT count(*) AS n FROM trade_runtime').get().n, 0); }
    finally { stillMissing.close(); }
    const corrupt = new DatabaseSync(stateFile); corrupt.prepare('UPDATE trade_runtime SET body=?,sha256=? WHERE singleton=1').run('{}', 'a'.repeat(64)); corrupt.close();
    assert.throws(() => createPersistentTradeServer({ stateFile }), { code: 'STATE_CORRUPT' });
    assert.equal(checkpoint(stateFile).text, '{}', 'corruption must not silently seed a fresh fixture');
  } finally { runtime?.close(); await close(running?.server); await rm(dir, { recursive: true, force: true }); }
});
