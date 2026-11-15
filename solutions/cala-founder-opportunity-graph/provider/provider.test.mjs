import test from 'node:test';
import assert from 'node:assert/strict';
import { preview, reviewPreview, sha } from './provider.mjs';
import { fakeHost, request } from './replay.mjs';
const run = (scenario, overrides = {}) => preview({ ...request(), host: fakeHost(scenario), limits: { timeoutMs: 30 }, ...overrides });
test('same pipeline walks exact sequence, dynamic keys, approval and integrity chain', async () => {
  const host = fakeHost();
  const a = await run('lead', { host });
  assert.equal(a.status, 'PREVIEW_REQUIRES_HUMAN_REVIEW');
  assert.deepEqual(host.calls, ['entity_search','entity_introspection','entity_retrieval']);
  assert.equal(a.evidence.rounds[0].amount, 'UNKNOWN');
  assert.equal(a.maturity, '2/6');
  assert.equal(reviewPreview(a, { approved: true, evidenceDigest: a.evidenceDigest }).status, 'HUMAN_REVIEWED_EVIDENCE_ONLY_SHORTLIST');
  assert.equal(reviewPreview(a, { approved: true, evidenceDigest: 'forged' }).status, 'HOLD');
  assert(Object.isFrozen(a.evidence.rounds));
  let previous = '0'.repeat(64);
  for (const { hash, ...row } of a.ledger.entries) { assert.equal(row.previous, previous); assert.equal(sha(row), hash); previous = hash; }
  assert.equal(a.ledger.root, previous);
  assert.equal(a.ledger.label, 'INTEGRITY NOT AUTHENTICITY');
  assert.equal((await run('lead')).ledger.root, a.ledger.root);
});
for (const scenario of ['issuer','missing','stale','forged-source','contradiction','filing-only','private-source']) test(`${scenario} abstains`, async () => {
  const result = await run(scenario);
  assert.equal(result.status, 'HOLD');
  assert.equal(result.evidence.rounds.length, 0);
});
for (const scenario of ['wrong-id','timeout','overlarge','ambiguous-identity','ambiguous-fields','revoked']) test(`${scenario} refuses`, async () => assert.equal((await run(scenario)).status, 'REFUSE'));
test('duplicates and filing never inflate economic rounds', async () => {
  const a = await run('duplicates');
  assert.equal(a.evidence.rounds.length, 1);
  assert.equal(a.evidence.rounds[0].citations.length, 1);
});
test('unapproved UUID, absent identity/clock and excessive limits refuse before tools', async () => {
  for (const overrides of [{ approvedEntityId: 'a fuzzy name' }, { identity: null }, { clock: null }, { limits: { maxRows: 101 } }]) {
    const host = fakeHost();
    assert.equal((await run('lead', { ...overrides, host })).status, 'REFUSE');
    assert.deepEqual(host.calls, []);
  }
});
test('unknown/write-capable tools, entity/row bounds and wrong response binding refuse', async () => {
  const host = fakeHost(); host.tools[0].readOnly = false;
  assert.equal((await run('lead', { host })).status, 'REFUSE');
  for (const [name, payload] of [
    ['entity_search', { entities: Array(26).fill({ id: request().approvedEntityId }) }],
    ['entity_retrieval', { entityId: request().approvedEntityId, rows: Array(101).fill({}) }],
    ['entity_introspection', { entityId: 'wrong', fields: [] }]
  ]) {
    const h = fakeHost(), original = h.callTool;
    h.callTool = args => args.name === name ? JSON.stringify(payload) : original(args);
    assert.equal((await run('lead', { host: h })).status, 'REFUSE');
  }
});
test('source verification is bounded and exceptions/private raw payloads never leak', async () => {
  const host = fakeHost(); host.verifySource = () => new Promise(() => {});
  assert.equal((await run('lead', { host })).reason, 'TIMEOUT');
  const h = fakeHost(); h.callTool = () => { throw Error('SECRET_PRIVATE_VALUE'); };
  const result = await run('lead', { host: h });
  assert(!JSON.stringify(result).includes('SECRET_PRIVATE_VALUE'));
  assert(!JSON.stringify(result).includes('synthetic-tenant'));
});
test('source proof must bind exact origin, URL, issuer and verification clock', async () => {
  for (const patch of [{ originId: 'forged' }, { url: 'https://example.invalid/forged' }, { issuerId: request().approvedEntityId }, { verifiedAt: '2022-01-01T00:00:00Z' }]) {
    const host = fakeHost(), verify = host.verifySource;
    host.verifySource = async args => ({ ...await verify(args), ...patch });
    assert.equal((await run('lead', { host })).status, 'HOLD');
  }
});
test('missing event kind and unsafe citation URL abstain without source checker', async () => {
  for (const mutate of [row => { delete row.observed_3; }, row => { row.observed_10.url = 'http://127.0.0.1/private'; }]) {
    const host = fakeHost(), call = host.callTool;
    host.callTool = async args => {
      const raw = await call(args);
      if (args.name !== 'entity_retrieval') return raw;
      const data = JSON.parse(raw); mutate(data.rows[0]); return JSON.stringify(data);
    };
    host.verifySource = () => assert.fail('Unverifiable source must not be checked');
    assert.equal((await run('lead', { host })).status, 'HOLD');
  }
});
test('bounded authorization, overall deadline and call budget refuse', async () => {
  const host = fakeHost(); host.authorize = () => new Promise(() => {});
  assert.equal((await run('lead', { host })).reason, 'TIMEOUT');
  assert.equal((await run('lead', { limits: { maxCalls: 1 } })).reason, 'CALL_LIMIT');
  const slow = fakeHost(), call = slow.callTool;
  slow.callTool = async args => { await new Promise(resolve => setTimeout(resolve, 25)); return call(args); };
  assert.equal((await run('lead', { host: slow, limits: { timeoutMs: 100, totalTimeoutMs: 10 } })).reason, 'TIMEOUT');
});
test('invalid UTF8 and object responses refuse before ingestion', async () => {
  for (const raw of [new Uint8Array([0xff]), { entities: [] }]) {
    const host = fakeHost(); host.callTool = async () => raw;
    assert.equal((await run('lead', { host })).status, 'REFUSE');
  }
});
test('modified evidence cannot reuse review digest', async () => {
  const result = structuredClone(await run('lead'));
  result.evidence.rounds[0].lead = false;
  assert.equal(reviewPreview(result, { approved: true, evidenceDigest: result.evidenceDigest }).status, 'HOLD');
});

test('conflicting duplicate JSON members are rejected before evidence admission', async () => {
  const host=fakeHost(), original=host.callTool;
  host.callTool=async args => {
    const raw=await original(args);
    return args.name==='entity_search' ? '{"entities":[],'+raw.slice(1) : raw;
  };
  const result=await run('lead',{host});
  assert.equal(result.status,'REFUSE');
  assert.equal(result.reason,'INVALID_JSON');
});
