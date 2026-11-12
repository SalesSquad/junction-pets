import { randomUUID } from 'node:crypto';

const SHA40 = /^[a-f0-9]{40}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;

export class StaleLeaseError extends Error {
  constructor(action) {
    super(`${action}: no live matching lease/fencing token`);
    this.name = 'StaleLeaseError';
  }
}

export class IdempotencyCollisionError extends Error {
  constructor(scope) {
    super(`${scope}: idempotency key reused with a different digest or grant`);
    this.name = 'IdempotencyCollisionError';
  }
}

function namedString(value, name, maxLength = 240) {
  if (typeof value !== 'string' || value.length === 0 || value.length > maxLength || value.trim() !== value) {
    throw new TypeError(`${name} must be a nonempty trimmed string <= ${maxLength}`);
  }
  return value;
}

function sha(value, name, regex = SHA256) {
  if (typeof value !== 'string' || !regex.test(value)) throw new TypeError(`${name} must be a lowercase hex digest`);
  return value;
}

function int(value, name, min, max) {
  if (!Number.isSafeInteger(value) || value < min || value > max) throw new RangeError(`${name} must be an integer in ${min}..${max}`);
  return value;
}

function uuid(value, name) {
  if (typeof value !== 'string' || !UUID.test(value)) throw new TypeError(`${name} must be a UUID`);
  return value;
}

// PostgreSQL BIGINT usually arrives as a decimal string through node-postgres.
// Passing decimal strings back avoids unsafe IEEE-754 rounding of fence tokens.
function fence(value) {
  if (typeof value === 'bigint' && value > 0n && value <= 9223372036854775807n) return value.toString();
  if (typeof value === 'string' && /^[1-9][0-9]*$/.test(value) && BigInt(value) <= 9223372036854775807n) return value;
  if (Number.isSafeInteger(value) && value > 0) return String(value);
  throw new TypeError('fencingToken must be a positive int64 decimal string');
}

function leaseTicket(ticket) {
  if (ticket === null || typeof ticket !== 'object') throw new TypeError('lease ticket object required');
  return {
    jobId: uuid(ticket.jobId, 'jobId'),
    tenantId: namedString(ticket.tenantId, 'tenantId', 160),
    workerId: namedString(ticket.workerId, 'workerId', 160),
    fencingToken: fence(ticket.fencingToken),
  };
}

function queryable(db) {
  if (typeof db?.query !== 'function') throw new TypeError('database adapter with query(sql, parameters) required');
  return db;
}

function one(result) {
  return result?.rows?.[0] ?? null;
}

/**
 * Idempotently records immutable input identity. No payload data is stored.
 * Different input with the same tenant/pet/key is rejected, never overwritten.
 */
export async function enqueueJob(db, {
  jobId = randomUUID(), tenantId, petId, sourceCommit, inputSha256,
  idempotencyKey, maxAttempts = 3, priority = 0,
}) {
  queryable(db);
  uuid(jobId, 'jobId');
  namedString(tenantId, 'tenantId', 160);
  namedString(petId, 'petId', 160);
  sha(sourceCommit, 'sourceCommit', SHA40);
  sha(inputSha256, 'inputSha256');
  namedString(idempotencyKey, 'idempotencyKey');
  int(maxAttempts, 'maxAttempts', 1, 100);
  int(priority, 'priority', -1000, 1000);
  const result = await db.query(`
    INSERT INTO junction_dispatch.jobs
      (job_id, tenant_id, pet_id, source_commit, input_sha256, idempotency_key, max_attempts, priority)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
    ON CONFLICT ON CONSTRAINT jobs_tenant_pet_idempotency
    DO UPDATE SET job_id = junction_dispatch.jobs.job_id
      WHERE junction_dispatch.jobs.input_sha256 = EXCLUDED.input_sha256
        AND junction_dispatch.jobs.source_commit = EXCLUDED.source_commit
    RETURNING job_id, tenant_id, pet_id, state, source_commit, fencing_token`,
  [jobId, tenantId, petId, sourceCommit, inputSha256, idempotencyKey, maxAttempts, priority]);
  const row = one(result);
  if (!row) throw new IdempotencyCollisionError('job');
  return row;
}

/**
 * Atomic per-tenant, per-pet claim. Only the authorized host dispatcher gets
 * database access; a pet's Codex Cloud development environment does not.
 */
export async function claimNextJob(db, { tenantId, petId, workerId, leaseSeconds = 45 }) {
  queryable(db);
  namedString(tenantId, 'tenantId', 160);
  namedString(petId, 'petId', 160);
  namedString(workerId, 'workerId', 160);
  int(leaseSeconds, 'leaseSeconds', 1, 3600);
  const result = await db.query(`
    WITH candidate AS (
      SELECT job_id FROM junction_dispatch.jobs
      WHERE tenant_id = $1 AND pet_id = $2
        AND attempts < max_attempts
        AND ((state = 'queued' AND next_run_at <= clock_timestamp())
          OR (state = 'leased' AND lease_expires_at <= clock_timestamp()))
      ORDER BY priority DESC, next_run_at, created_at, job_id
      FOR UPDATE SKIP LOCKED LIMIT 1
    )
    UPDATE junction_dispatch.jobs AS j
    SET state = 'leased', lease_owner = $3,
        lease_expires_at = clock_timestamp() + ($4::integer * interval '1 second'),
        fencing_token = j.fencing_token + 1,
        attempts = j.attempts + 1, updated_at = clock_timestamp()
    FROM candidate
    WHERE j.job_id = candidate.job_id
    RETURNING j.job_id, j.tenant_id, j.pet_id, j.source_commit,
              j.fencing_token, j.lease_owner, j.lease_expires_at, j.attempts`,
  [tenantId, petId, workerId, leaseSeconds]);
  return one(result);
}

export async function heartbeat(db, ticket, { leaseSeconds = 45 } = {}) {
  queryable(db);
  const { jobId, tenantId, workerId, fencingToken } = leaseTicket(ticket);
  int(leaseSeconds, 'leaseSeconds', 1, 3600);
  const result = await db.query(`
    UPDATE junction_dispatch.jobs
    SET lease_expires_at = clock_timestamp() + ($5::integer * interval '1 second'),
        updated_at = clock_timestamp()
    WHERE job_id = $1 AND tenant_id = $2 AND lease_owner = $3
      AND fencing_token = $4 AND state = 'leased'
      AND lease_expires_at > clock_timestamp()
    RETURNING job_id, fencing_token, lease_expires_at`,
  [jobId, tenantId, workerId, fencingToken, leaseSeconds]);
  const row = one(result);
  if (!row) throw new StaleLeaseError('heartbeat');
  return row;
}

/**
 * A fenced, immutable outbox intent. The Chibi host MUST validate the grant
 * and its revocation status at external execution time, not only here.
 */
export async function recordEffectIntent(db, ticket, {
  effectId = randomUUID(), effectIdempotencyKey, scope, payloadSha256, hostGrantReceiptSha256,
}) {
  queryable(db);
  const { jobId, tenantId, workerId, fencingToken } = leaseTicket(ticket);
  uuid(effectId, 'effectId');
  namedString(effectIdempotencyKey, 'effectIdempotencyKey');
  namedString(scope, 'scope');
  sha(payloadSha256, 'payloadSha256');
  sha(hostGrantReceiptSha256, 'hostGrantReceiptSha256');
  const result = await db.query(`
    WITH live_lease AS (
      SELECT job_id, tenant_id FROM junction_dispatch.jobs
      WHERE job_id = $1 AND tenant_id = $2 AND lease_owner = $3
        AND fencing_token = $4 AND state = 'leased'
        AND lease_expires_at > clock_timestamp()
      FOR UPDATE
    )
    INSERT INTO junction_dispatch.effect_outbox
      (effect_id, job_id, tenant_id, effect_idempotency_key, scope,
       payload_sha256, host_grant_receipt_sha256)
    SELECT $5, job_id, tenant_id, $6, $7, $8, $9 FROM live_lease
    ON CONFLICT ON CONSTRAINT effect_tenant_idempotency
    DO UPDATE SET effect_id = junction_dispatch.effect_outbox.effect_id
      WHERE junction_dispatch.effect_outbox.payload_sha256 = EXCLUDED.payload_sha256
        AND junction_dispatch.effect_outbox.host_grant_receipt_sha256 = EXCLUDED.host_grant_receipt_sha256
        AND junction_dispatch.effect_outbox.job_id = EXCLUDED.job_id
        AND junction_dispatch.effect_outbox.scope = EXCLUDED.scope
    RETURNING effect_id, job_id, state, effect_idempotency_key`,
  [jobId, tenantId, workerId, fencingToken, effectId,
    effectIdempotencyKey, scope, payloadSha256, hostGrantReceiptSha256]);
  const row = one(result);
  if (!row) throw new StaleLeaseError('recordEffectIntent (stale lease or colliding key)');
  return row;
}

/**
 * Records an external provider's idempotency-backed receipt. It does not call
 * the provider and cannot guarantee external exactly-once side effects.
 */
export async function markEffectDelivered(db, ticket, { effectIdempotencyKey, providerReceiptSha256 }) {
  queryable(db);
  const { jobId, tenantId, workerId, fencingToken } = leaseTicket(ticket);
  namedString(effectIdempotencyKey, 'effectIdempotencyKey');
  sha(providerReceiptSha256, 'providerReceiptSha256');
  const result = await db.query(`
    WITH live_lease AS MATERIALIZED (
      SELECT j.job_id FROM junction_dispatch.jobs AS j
      WHERE j.job_id = $1 AND j.tenant_id = $2 AND j.lease_owner = $3
        AND j.fencing_token = $4 AND j.state = 'leased'
        AND j.lease_expires_at > clock_timestamp()
      FOR UPDATE
    )
    UPDATE junction_dispatch.effect_outbox AS e
    SET state = 'delivered', provider_receipt_sha256 = $6,
        delivered_at = COALESCE(e.delivered_at, clock_timestamp())
    FROM live_lease AS locked
    WHERE e.job_id = locked.job_id AND e.job_id = $1
      AND e.tenant_id = $2 AND e.effect_idempotency_key = $5
      AND (e.state = 'pending' OR
        (e.state = 'delivered' AND e.provider_receipt_sha256 = $6))
    RETURNING e.effect_id, e.state, e.provider_receipt_sha256`,
  [jobId, tenantId, workerId, fencingToken, effectIdempotencyKey, providerReceiptSha256]);
  const row = one(result);
  if (!row) throw new StaleLeaseError('markEffectDelivered');
  return row;
}

/** Job completion and immutable result insertion occur in one SQL statement. */
export async function completeJob(db, ticket, { resultSha256 }) {
  queryable(db);
  const { jobId, tenantId, workerId, fencingToken } = leaseTicket(ticket);
  sha(resultSha256, 'resultSha256');
  const result = await db.query(`
    WITH completed AS (
      UPDATE junction_dispatch.jobs AS j
      SET state = 'completed', lease_owner = NULL, lease_expires_at = NULL,
          updated_at = clock_timestamp()
      WHERE j.job_id = $1 AND j.tenant_id = $2 AND j.lease_owner = $3
        AND j.fencing_token = $4 AND j.state = 'leased'
        AND j.lease_expires_at > clock_timestamp()
        AND NOT EXISTS (
          SELECT 1 FROM junction_dispatch.effect_outbox AS e
          WHERE e.job_id = j.job_id AND e.state <> 'delivered'
        )
      RETURNING j.job_id
    )
    INSERT INTO junction_dispatch.results (job_id, fencing_token, result_sha256)
    SELECT job_id, $4, $5 FROM completed
    ON CONFLICT (job_id) DO NOTHING
    RETURNING job_id, fencing_token, result_sha256, completed_at`,
  [jobId, tenantId, workerId, fencingToken, resultSha256]);
  const row = one(result);
  if (!row) throw new StaleLeaseError('completeJob (stale lease or pending effects)');
  return row;
}

export async function failJob(db, ticket, { retrySeconds = 0 } = {}) {
  queryable(db);
  const { jobId, tenantId, workerId, fencingToken } = leaseTicket(ticket);
  int(retrySeconds, 'retrySeconds', 0, 86400);
  const result = await db.query(`
    UPDATE junction_dispatch.jobs
    SET state = CASE WHEN attempts >= max_attempts THEN 'dead_letter' ELSE 'queued' END,
        next_run_at = clock_timestamp() + ($5::integer * interval '1 second'),
        lease_owner = NULL, lease_expires_at = NULL,
        updated_at = clock_timestamp()
    WHERE job_id = $1 AND tenant_id = $2 AND lease_owner = $3
      AND fencing_token = $4 AND state = 'leased'
      AND lease_expires_at > clock_timestamp()
    RETURNING job_id, state, attempts`,
  [jobId, tenantId, workerId, fencingToken, retrySeconds]);
  const row = one(result);
  if (!row) throw new StaleLeaseError('failJob');
  return row;
}

/** Periodic repair. Also permanently retires exhausted expired leases. */
export async function recoverExpiredLeases(db, { limit = 100 } = {}) {
  queryable(db);
  int(limit, 'limit', 1, 10000);
  const result = await db.query(`
    WITH expired AS (
      SELECT job_id FROM junction_dispatch.jobs
      WHERE state = 'leased' AND lease_expires_at <= clock_timestamp()
      ORDER BY lease_expires_at, job_id FOR UPDATE SKIP LOCKED LIMIT $1
    )
    UPDATE junction_dispatch.jobs AS j
    SET state = CASE WHEN j.attempts >= j.max_attempts THEN 'dead_letter' ELSE 'queued' END,
        lease_owner = NULL, lease_expires_at = NULL,
        next_run_at = clock_timestamp(), updated_at = clock_timestamp()
    FROM expired WHERE j.job_id = expired.job_id
    RETURNING j.job_id, j.state, j.fencing_token`, [limit]);
  return result?.rows ?? [];
}
