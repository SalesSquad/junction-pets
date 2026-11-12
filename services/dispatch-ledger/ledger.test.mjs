import test from 'node:test';
import assert from 'node:assert/strict';
import {
  enqueueJob, claimNextJob, heartbeat, recordEffectIntent,
  markEffectDelivered, completeJob, failJob, recoverExpiredLeases,
  IdempotencyCollisionError, StaleLeaseError,
} from './ledger.mjs';

const H = 'a'.repeat(64);
const OTHER = 'b'.repeat(64);
const COMMIT = 'c'.repeat(40);
const JOB = '11111111-1111-4111-8111-111111111111';
const EFFECT = '22222222-2222-4222-8222-222222222222';

/**
 * Deterministic query adapter that models transactional outcomes. It is NOT a
 * real PostgreSQL fixture. DB concurrency is a separate release gate.
 */
class FakePg {
  constructor() {
    this.now = 0;
    this.jobs = new Map();
    this.effects = new Map();
    this.results = new Map();
    this.statements = [];
  }

  advance(seconds) { this.now += seconds; }
  ticket(row) {
    return {
      jobId: row.job_id, tenantId: row.tenant_id,
      workerId: row.lease_owner, fencingToken: row.fencing_token,
    };
  }

  async query(sql, v) {
    this.statements.push({ sql, values: v });
    const ret = (...rows) => ({ rows });
    if (sql.includes('ON CONFLICT ON CONSTRAINT jobs_tenant_pet_idempotency')) {
      const [jobId, tenantId, petId, sourceCommit, inputHash, key, maxAttempts, priority] = v;
      const existing = [...this.jobs.values()].find(j => j.tenant_id === tenantId && j.pet_id === petId && j.key === key);
      if (existing) return existing.source_commit === sourceCommit && existing.inputHash === inputHash ? ret(existing) : ret();
      const row = { job_id: jobId, tenant_id: tenantId, pet_id: petId, source_commit: sourceCommit,
        inputHash, key, max_attempts: maxAttempts, priority, state: 'queued',
        attempts: 0, fencing_token: 0, lease_owner: null, lease_expires_at: null,
        next_run_at: this.now };
      this.jobs.set(jobId, row);
      return ret(row);
    }
    if (sql.includes('FOR UPDATE SKIP LOCKED') && sql.includes('WITH candidate AS')) {
      const [tenantId, petId, workerId, leaseSeconds] = v;
      const eligible = [...this.jobs.values()].filter(j =>
        j.tenant_id === tenantId && j.pet_id === petId && j.attempts < j.max_attempts &&
        ((j.state === 'queued' && j.next_run_at <= this.now) ||
        (j.state === 'leased' && j.lease_expires_at <= this.now)));
      eligible.sort((a, b) => b.priority - a.priority || a.next_run_at - b.next_run_at);
      if (!eligible[0]) return ret();
      const j = eligible[0];
      j.state = 'leased'; j.lease_owner = workerId; j.lease_expires_at = this.now + leaseSeconds;
      j.fencing_token++; j.attempts++;
      return ret({ ...j });
    }
    if (sql.includes('UPDATE junction_dispatch.jobs') && sql.includes('SET lease_expires_at')) {
      const [id, tenant, worker, fence, leaseSeconds] = v;
      const j = this.live(id, tenant, worker, fence);
      if (!j) return ret();
      j.lease_expires_at = this.now + leaseSeconds;
      return ret({ ...j });
    }
    if (sql.includes('ON CONFLICT ON CONSTRAINT effect_tenant_idempotency')) {
      const [id, tenant, worker, fence, effectId, key, scope, payloadHash, grantHash] = v;
      const j = this.live(id, tenant, worker, fence);
      if (!j) return ret();
      const index = `${tenant}:${key}`;
      const existing = this.effects.get(index);
      if (existing) return existing.job_id === id && existing.scope === scope && existing.payloadHash === payloadHash && existing.grantHash === grantHash ? ret(existing) : ret();
      const e = { effect_id: effectId, job_id: id, effect_idempotency_key: key, scope,
        payloadHash, grantHash, state: 'pending', provider_receipt_sha256: null };
      this.effects.set(index, e);
      return ret(e);
    }
    if (sql.includes('UPDATE junction_dispatch.effect_outbox AS e')) {
      const [id, tenant, worker, fence, key, receipt] = v;
      if (!this.live(id, tenant, worker, fence)) return ret();
      const e = this.effects.get(`${tenant}:${key}`);
      if (!e || e.job_id !== id || (e.state === 'delivered' && e.provider_receipt_sha256 !== receipt)) return ret();
      e.state = 'delivered'; e.provider_receipt_sha256 = receipt;
      return ret(e);
    }
    if (sql.includes('INSERT INTO junction_dispatch.results') && sql.includes('WITH completed AS')) {
      const [id, tenant, worker, fence, digest] = v;
      const j = this.live(id, tenant, worker, fence);
      if (!j || [...this.effects.values()].some(e => e.job_id === id && e.state !== 'delivered')) return ret();
      if (this.results.has(id)) return ret();
      j.state = 'completed'; j.lease_owner = null; j.lease_expires_at = null;
      const row = { job_id: id, fencing_token: fence, result_sha256: digest };
      this.results.set(id, row);
      return ret(row);
    }
    if (sql.includes('UPDATE junction_dispatch.jobs') && sql.includes('SET state = CASE') && !sql.includes('WITH expired AS')) {
      const [id, tenant, worker, fence, delay] = v;
      const j = this.live(id, tenant, worker, fence);
      if (!j) return ret();
      j.state = j.attempts >= j.max_attempts ? 'dead_letter' : 'queued';
      j.next_run_at = this.now + delay;
      j.lease_owner = null; j.lease_expires_at = null;
      return ret({ ...j });
    }
    if (sql.includes('WITH expired AS')) {
      const [limit] = v;
      const expired = [...this.jobs.values()].filter(j => j.state === 'leased' && j.lease_expires_at <= this.now).slice(0, limit);
      for (const j of expired) {
        j.state = j.attempts >= j.max_attempts ? 'dead_letter' : 'queued';
        j.lease_owner = null; j.lease_expires_at = null; j.next_run_at = this.now;
      }
      return { rows: expired.map(j => ({ ...j })) };
    }
    throw new Error(`unexpected fake SQL: ${sql.slice(0,100)}`);
  }

  live(id, tenant, worker, fence) {
    const j = this.jobs.get(id);
    return j && j.tenant_id === tenant && j.lease_owner === worker &&
      String(j.fencing_token) === String(fence) && j.state === 'leased' && j.lease_expires_at > this.now ? j : null;
  }
}

function seed(db, options = {}) {
  return enqueueJob(db, { jobId: options.jobId ?? JOB, tenantId: 'demo-tenant',
    petId: 'aiven', sourceCommit: COMMIT, inputSha256: options.inputSha256 ?? H,
    idempotencyKey: 'wave2-aiven-001', maxAttempts: options.maxAttempts ?? 3 });
}

// All ordinary fixture claims must explicitly select the tenant and pet lane.
function claimInDemoLane(db, options) {
  return claimNextJob(db, { tenantId: 'demo-tenant', petId: 'aiven', ...options });
}

test('immutable enqueue handles exact retry and denies collision', async () => {
  const db = new FakePg();
  assert.equal((await seed(db)).job_id, JOB);
  assert.equal((await seed(db)).job_id, JOB);
  await assert.rejects(seed(db, { inputSha256: OTHER }), IdempotencyCollisionError);
  assert.equal(db.jobs.size, 1);
});

test('tenant/pet-scoped claim rejects global or cross-company worker dispatch', async () => {
  const db = new FakePg();
  await seed(db);
  await enqueueJob(db, {
    jobId: EFFECT, tenantId: 'another-tenant', petId: 'nvidia',
    sourceCommit: COMMIT, inputSha256: OTHER, idempotencyKey: 'nvidia-001',
  });
  const before = db.statements.length;
  await assert.rejects(claimNextJob(db, { workerId: 'unscoped' }), TypeError);
  await assert.rejects(claimNextJob(db, { tenantId: 'demo-tenant', workerId: 'missing-pet' }), TypeError);
  assert.equal(db.statements.length, before, 'invalid claims never query the database');

  const aiven = await claimNextJob(db, {
    tenantId: 'demo-tenant', petId: 'aiven', workerId: 'aiven-worker',
  });
  assert.equal(aiven.job_id, JOB);
  assert.equal(await claimNextJob(db, {
    tenantId: 'demo-tenant', petId: 'aiven', workerId: 'another-aiven-worker',
  }), null, 'aiven worker cannot claim NVIDIA job');
  assert.equal(db.jobs.get(EFFECT).state, 'queued');
  const nvidia = await claimNextJob(db, {
    tenantId: 'another-tenant', petId: 'nvidia', workerId: 'nvidia-worker',
  });
  assert.equal(nvidia.job_id, EFFECT);
  const claim = db.statements.find(x => x.sql.includes('WITH candidate AS'));
  assert.match(claim.sql, /WHERE tenant_id = \$1 AND pet_id = \$2/);
  assert.deepEqual(claim.values, ['demo-tenant', 'aiven', 'aiven-worker', 45]);
});

test('competing model workers receive at most one first claim; SQL uses SKIP LOCKED', async () => {
  const db = new FakePg(); await seed(db);
  const [a, b] = await Promise.all([
    claimInDemoLane(db, { workerId: 'codex-a', leaseSeconds: 10 }),
    claimInDemoLane(db, { workerId: 'codex-b', leaseSeconds: 10 }),
  ]);
  assert.equal([a, b].filter(Boolean).length, 1);
  assert.equal(db.jobs.get(JOB).fencing_token, 1);
  const query = db.statements.find(x => x.sql.includes('WITH candidate AS'))?.sql;
  assert.match(query, /FOR UPDATE SKIP LOCKED/);
  assert.match(query, /fencing_token = j\.fencing_token \+ 1/);
});

test('crash, expired lease and new fencing token invalidate first worker', async () => {
  const db = new FakePg(); await seed(db);
  const first = await claimInDemoLane(db, { workerId: 'first', leaseSeconds: 5 });
  db.advance(6);
  const second = await claimInDemoLane(db, { workerId: 'replacement', leaseSeconds: 10 });
  assert.equal(second.fencing_token, first.fencing_token + 1);
  await assert.rejects(heartbeat(db, db.ticket(first)), StaleLeaseError);
  await assert.rejects(completeJob(db, db.ticket(first), { resultSha256: H }), StaleLeaseError);
  assert.equal((await heartbeat(db, db.ticket(second))).fencing_token, second.fencing_token);
});

test('effect outbox is immutable; unfinished effect prevents completion', async () => {
  const db = new FakePg(); await seed(db);
  const lease = await claimInDemoLane(db, { workerId: 'host' });
  const ticket = db.ticket(lease);
  const input = { effectId: EFFECT, effectIdempotencyKey: 'aiven.readonly.search.v1',
    scope: 'aiven.docs.read', payloadSha256: H, hostGrantReceiptSha256: H };
  assert.equal((await recordEffectIntent(db, ticket, input)).effect_id, EFFECT);
  assert.equal((await recordEffectIntent(db, ticket, input)).effect_id, EFFECT);
  await assert.rejects(recordEffectIntent(db, ticket, { ...input, payloadSha256: OTHER }), StaleLeaseError);
  assert.equal(db.effects.size, 1);
  await assert.rejects(completeJob(db, ticket, { resultSha256: H }), StaleLeaseError);
  await markEffectDelivered(db, ticket, { effectIdempotencyKey: input.effectIdempotencyKey, providerReceiptSha256: OTHER });
  await assert.rejects(markEffectDelivered(db, ticket, { effectIdempotencyKey: input.effectIdempotencyKey, providerReceiptSha256: H }), StaleLeaseError);
  assert.equal((await completeJob(db, ticket, { resultSha256: H })).result_sha256, H);
  await assert.rejects(completeJob(db, ticket, { resultSha256: H }), StaleLeaseError);
  assert.equal(db.results.size, 1);
});

test('adversarial receipt/reassignment: expired fence cannot mark delivery; SQL locks job', async () => {
  const db = new FakePg(); await seed(db);
  const first = await claimInDemoLane(db, { workerId: 'abandoned', leaseSeconds: 2 });
  const effectIdempotencyKey = 'aiven.docs.read/v1';
  await recordEffectIntent(db, db.ticket(first), {
    effectId: EFFECT, effectIdempotencyKey, scope: 'aiven.docs.read',
    payloadSha256: H, hostGrantReceiptSha256: H,
  });
  db.advance(3);
  const replacement = await claimInDemoLane(db, { workerId: 'replacement', leaseSeconds: 20 });
  await assert.rejects(markEffectDelivered(db, db.ticket(first), {
    effectIdempotencyKey, providerReceiptSha256: OTHER,
  }), StaleLeaseError);
  const sql = db.statements.at(-1).sql;
  assert.match(sql, /WITH live_lease AS MATERIALIZED/);
  assert.match(sql, /SELECT j\.job_id FROM junction_dispatch\.jobs AS j/);
  assert.match(sql, /FOR UPDATE/);
  assert.match(sql, /j\.fencing_token = \$4 AND j\.state = 'leased'/);
  assert.match(sql, /j\.lease_expires_at > clock_timestamp\(\)/);
  assert.match(sql, /FROM live_lease AS locked/);
  assert.equal((await markEffectDelivered(db, db.ticket(replacement), {
    effectIdempotencyKey, providerReceiptSha256: OTHER,
  })).state, 'delivered');
});

test('bounded attempts go to dead letter; recovery requeues after crash', async () => {
  const db = new FakePg(); await seed(db, { maxAttempts: 2 });
  const first = await claimInDemoLane(db, { workerId: 'first', leaseSeconds: 2 });
  assert.equal((await failJob(db, db.ticket(first), { retrySeconds: 3 })).state, 'queued');
  assert.equal(await claimInDemoLane(db, { workerId: 'too-soon' }), null);
  db.advance(3);
  const second = await claimInDemoLane(db, { workerId: 'second', leaseSeconds: 2 });
  db.advance(3);
  assert.deepEqual((await recoverExpiredLeases(db)).map(x => x.state), ['dead_letter']);
  assert.equal(await claimInDemoLane(db, { workerId: 'third' }), null);
  await assert.rejects(failJob(db, db.ticket(second)), StaleLeaseError);
});

test('invalid scope or source digest never reaches database', async () => {
  const db = new FakePg();
  await assert.rejects(enqueueJob(db, { jobId: JOB, tenantId: 't', petId: 'p',
    sourceCommit: 'not-a-commit', inputSha256: H, idempotencyKey: 'k' }), TypeError);
  assert.equal(db.statements.length, 0);
  await seed(db);
  const lease = await claimInDemoLane(db, { workerId: 'host' });
  const count = db.statements.length;
  await assert.rejects(recordEffectIntent(db, db.ticket(lease), {
    effectId: EFFECT, effectIdempotencyKey: 'a', scope: '',
    payloadSha256: H, hostGrantReceiptSha256: H,
  }), TypeError);
  assert.equal(db.statements.length, count);
});
