#!/usr/bin/env node
/**
 * Opt-in, REAL PostgreSQL 14+ integration gate for Council dispatch fencing.
 * Requires a disposable database named junction_dispatch_test_* and psql 14+.
 * No new server, credentials, extensions, dependencies, migrations outside that
 * explicit test database, or production data. Missing DB is a hard BLOCKER.
 *
 *    JUNCTION_DISPATCH_TEST_DATABASE_URL=postgresql://.../junction_dispatch_test_w3 \
 *      node services/dispatch-ledger/pg-integration.mjs
 *
 * This runs independent physical psql connections, holds a real row lock,
 * checks SKIP LOCKED, rejects stale fencing, verifies lock_timeout on the
 * effect-ack path, and simulates crash/recovery. Not a mock or CI skip.
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  claimNextJob, completeJob, enqueueJob, heartbeat,
  markEffectDelivered, recordEffectIntent, recoverExpiredLeases,
  StaleLeaseError,
} from './ledger.mjs';

const MARKER = 'JUNCTION_W3_ROW_LOCK_HELD';
const MIGRATION = new URL('./001_dispatch_ledger.sql', import.meta.url);
const COMMIT = 'b8895789e12937be65cd5b49c9705cd9d9716c30';
const DIGEST_A = 'a'.repeat(64);
const DIGEST_B = 'b'.repeat(64);
const EXPECTED_DB = /^junction_dispatch_test_[a-z0-9_]{3,50}$/;

class PsqlCommandError extends Error {
  constructor(code, stderr) {
    super(`psql command failed (exit ${code}): ${scrub(stderr)}`);
    this.name = 'PsqlCommandError';
  }
}

function scrub(message) {
  return String(message).replace(/postgres(?:ql)?:\/\/\S+/gi, '[redacted-uri]')
    .replace(/password\s*=\s*\S+/gi, 'password=[redacted]')
    .slice(0, 1200);
}

function testDatabaseConfig() {
  const value = process.env.JUNCTION_DISPATCH_TEST_DATABASE_URL;
  if (!value) {
    throw new Error('TEST_DB_UNAVAILABLE: JUNCTION_DISPATCH_TEST_DATABASE_URL is not set; real PostgreSQL gate NOT RUN');
  }
  const url = new URL(value);
  if (!['postgres:', 'postgresql:'].includes(url.protocol)) throw new Error('Test DB must use PostgreSQL URI');
  const database = decodeURIComponent(url.pathname.slice(1));
  if (!EXPECTED_DB.test(database)) throw new Error('Refusing non-disposable database name (required junction_dispatch_test_*)');
  const host = url.hostname.toLowerCase();
  if (!host) throw new Error('Test DB host must be explicit');
  const local = ['localhost', '127.0.0.1', '::1', '[::1]'].includes(host);
  if (!local && process.env.JUNCTION_DISPATCH_TEST_ALLOW_REMOTE !== '1') {
    throw new Error('Remote test DB requires JUNCTION_DISPATCH_TEST_ALLOW_REMOTE=1; no implicit remote writes');
  }
  // Drop inherited libpq config so another account/project is not contacted.
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('PG')));
  env.PGHOST = host;
  env.PGPORT = url.port || '5432';
  env.PGDATABASE = database;
  env.PGUSER = decodeURIComponent(url.username || process.env.USER || '');
  env.PGPASSWORD = decodeURIComponent(url.password);
  env.PGPASSFILE = '/dev/null';
  env.PGCONNECT_TIMEOUT = '5';
  env.PGAPPNAME = 'junction-w3-pg-integration';
  env.PGSSLMODE = url.searchParams.get('sslmode') || (local ? 'prefer' : 'require');
  return { env, database };
}

function spawnPsql(env) {
  return spawn('psql', ['-X', '-q', '--csv', '-v', 'ON_ERROR_STOP=1'], {
    env, stdio: ['pipe', 'pipe', 'pipe'], timeout: 20_000,
  });
}

async function psqlScript(env, script) {
  const child = spawnPsql(env);
  let stdout = '';
  let stderr = '';
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  child.stdout.on('data', chunk => { stdout += chunk; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  const exited = new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('close', code => code === 0 ? resolve(stdout) : reject(new PsqlCommandError(code, stderr)));
  });
  child.stdin.end(script);
  return exited;
}

function quote(value) {
  if (value === null) return 'NULL';
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  if (typeof value !== 'string') throw new TypeError('psql adapter supports only decimal/text/null fixture parameters');
  if (value.includes('\0')) throw new TypeError('NUL not allowed in test fixture');
  return `'${value.replaceAll("'", "''")}'`;
}

// PostgreSQL CSV output has row headers. Generic parser supports quoted fields,
// escaped double-quotes and multiline values, including zero-returning updates.
function csvRows(csv) {
  const rows = [];
  let row = [], field = '', quoted = false;
  const input = csv.replace(/\r\n/g, '\n');
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (c === '"') {
      if (quoted && input[i + 1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (c === ',' && !quoted) {
      row.push(field); field = '';
    } else if (c === '\n' && !quoted) {
      row.push(field); rows.push(row); row = []; field = '';
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  if (quoted) throw new Error('Unterminated CSV response from psql');
  return rows;
}

function adapter(env, { lockTimeoutMs = 0 } = {}) {
  return {
    async query(sql, params = []) {
      const name = `jtw3_${randomUUID().replaceAll('-', '').slice(0, 16)}`;
      const prefix = lockTimeoutMs ? `SET lock_timeout = '${lockTimeoutMs}ms';\n` : '';
      const command = `${prefix}PREPARE ${name} AS ${sql.trim().replace(/;\s*$/, '')};\nEXECUTE ${name}(${params.map(quote).join(', ')});\nDEALLOCATE ${name};\n`;
      const output = await psqlScript(env, command);
      const [headers, ...values] = csvRows(output);
      if (!headers) return { rows: [] };
      return { rows: values.map(row => Object.fromEntries(headers.map((h, i) => [h, row[i] ?? null]))) };
    },
  };
}

/** Hold a real jobs row lock in one physical PostgreSQL connection. */
async function holdJobLock(env, jobId) {
  if (!/^[0-9a-f-]{36}$/.test(jobId)) throw new TypeError('Synthetic test UUID required');
  const child = spawnPsql(env);
  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');
  let stdout = '', stderr = '';
  child.stderr.on('data', chunk => { stderr += chunk; });
  const exit = new Promise(resolve => child.once('close', resolve));
  const acquired = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`row lock did not become ready: ${scrub(stderr)}`)), 10_000);
    child.stdout.on('data', chunk => {
      stdout += chunk;
      if (stdout.includes(MARKER)) { clearTimeout(timeout); resolve(); }
    });
    child.once('close', code => {
      clearTimeout(timeout);
      if (!stdout.includes(MARKER)) reject(new PsqlCommandError(code, stderr));
    });
    child.once('error', reject);
  });
  child.stdin.write(`BEGIN;\nSELECT job_id FROM junction_dispatch.jobs WHERE job_id = '${jobId}' FOR UPDATE;\n\\echo ${MARKER}\n`);
  try {
    await acquired;
  } catch (error) {
    child.kill('SIGTERM');
    throw error;
  }
  return {
    async release() {
      child.stdin.end('COMMIT;\n\\quit\n');
      const code = await exit;
      if (code !== 0) throw new PsqlCommandError(code, stderr);
    },
    kill() { child.kill('SIGTERM'); },
  };
}

async function run() {
  const { env, database } = testDatabaseConfig();
  const migration = readFileSync(MIGRATION, 'utf8');
  await psqlScript(env, migration);
  const db1 = adapter(env);
  const db2 = adapter(env);
  const lowLockDb = adapter(env, { lockTimeoutMs: 250 });
  const id = randomUUID();
  const tenantId = `w3-tenant-${id.slice(0, 8)}`;
  const petId = `aiven-${id.slice(0, 8)}`;
  const effectIdempotencyKey = `aiven.docs.read-${id}`;
  await enqueueJob(db1, {
    jobId: id, tenantId, petId, sourceCommit: COMMIT,
    inputSha256: DIGEST_A, idempotencyKey: `job-${id}`, maxAttempts: 3,
  });

  // Barrier 1: physically hold row lock; SKIP LOCKED must return no job.
  let hold = await holdJobLock(env, id);
  try {
    const skipped = await claimNextJob(db2, { tenantId, petId, workerId: 'concurrent-while-locked' });
    assert.equal(skipped, null, 'SKIP LOCKED must not claim the held row');
  } finally { await hold.release(); }

  const [one, two] = await Promise.all([
    claimNextJob(db1, { tenantId, petId, workerId: 'two-connection-worker-a', leaseSeconds: 30 }),
    claimNextJob(db2, { tenantId, petId, workerId: 'two-connection-worker-b', leaseSeconds: 30 }),
  ]);
  assert.equal([one, two].filter(Boolean).length, 1, 'exactly one concurrent claimant');
  const first = one ?? two;
  const firstTicket = { jobId: id, tenantId, workerId: first.lease_owner, fencingToken: first.fencing_token };
  assert.equal(Number(first.fencing_token), 1);
  const effect = {
    effectId: randomUUID(), effectIdempotencyKey, scope: 'aiven.docs.read',
    payloadSha256: DIGEST_A, hostGrantReceiptSha256: DIGEST_A,
  };
  await recordEffectIntent(db1, firstTicket, effect);

  // Simulate crash by losing the session and expiring the lease in the test DB.
  await psqlScript(env, `UPDATE junction_dispatch.jobs SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE job_id = '${id}';\n`);
  const recovered = await recoverExpiredLeases(db2);
  assert.ok(recovered.some(row => row.job_id === id && row.state === 'queued'), 'expired lease requeued');
  const second = await claimNextJob(db2, { tenantId, petId, workerId: 'restart-worker', leaseSeconds: 30 });
  assert.equal(second.job_id, id);
  assert.equal(Number(second.fencing_token), Number(first.fencing_token) + 1);
  const secondTicket = { jobId: id, tenantId, workerId: second.lease_owner, fencingToken: second.fencing_token };
  await assert.rejects(heartbeat(db1, firstTicket), StaleLeaseError);
  await assert.rejects(markEffectDelivered(db1, firstTicket, {
    effectIdempotencyKey, providerReceiptSha256: DIGEST_B,
  }), StaleLeaseError);
  assert.equal((await recordEffectIntent(db2, secondTicket, effect)).effect_id, effect.effectId,
    'restarted worker must reuse immutable outbox intent');

  // Barrier 2: receipt path MUST take job row lock. lock_timeout makes the
  // failure deterministic; without FOR UPDATE this would incorrectly succeed.
  hold = await holdJobLock(env, id);
  try {
    await assert.rejects(markEffectDelivered(lowLockDb, secondTicket, {
      effectIdempotencyKey, providerReceiptSha256: DIGEST_B,
    }), error => error instanceof PsqlCommandError && /lock timeout/i.test(error.message),
    'receipt path must block on current lease row lock');
  } finally { await hold.release(); }

  await markEffectDelivered(db2, secondTicket, { effectIdempotencyKey, providerReceiptSha256: DIGEST_B });
  const completed = await completeJob(db2, secondTicket, { resultSha256: DIGEST_B });
  assert.equal(completed.result_sha256, DIGEST_B);
  await assert.rejects(completeJob(db1, firstTicket, { resultSha256: DIGEST_B }), StaleLeaseError);

  const results = await db1.query(`SELECT count(*)::int AS count FROM junction_dispatch.results WHERE job_id = '${id}'`);
  const outbox = await db2.query(`SELECT count(*)::int AS count FROM junction_dispatch.effect_outbox WHERE job_id = '${id}'`);
  assert.equal(Number(results.rows[0].count), 1, 'one immutable result');
  assert.equal(Number(outbox.rows[0].count), 1, 'one immutable effect intent');
  const ledgerSha256 = createHash('sha256').update(readFileSync(new URL('./ledger.mjs', import.meta.url))).digest('hex');
  console.log(`POSTGRES_INTEGRATION_PASS: 2+ physical psql connections, lock contention, scoped claim, stale fence, crash/recovery, outbox, receipt lock; test DB ${database}; baseline ${COMMIT}; ledger_sha256 ${ledgerSha256}`);
}

if (process.argv.includes('--help')) {
  console.log('REAL PostgreSQL gate: set JUNCTION_DISPATCH_TEST_DATABASE_URL to an isolated database named junction_dispatch_test_*; remote host requires JUNCTION_DISPATCH_TEST_ALLOW_REMOTE=1. No DB is created automatically.');
} else {
  run().catch(error => {
    console.error(`${error.name ?? 'Error'}: ${scrub(error.message)}`);
    process.exitCode = /TEST_DB_UNAVAILABLE|Refusing non-disposable|Remote test DB requires/.test(error.message) ? 3 : 1;
  });
}
