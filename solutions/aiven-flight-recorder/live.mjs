// Aiven adapter: Aiven for PostgreSQL (outbox, processed keys, effects) and
// Aiven for Apache Kafka (keyed topic, consumer groups, manual offset commits).
// Configuration comes only from the environment; nothing is written to disk.
import { readFileSync } from 'node:fs';
import { Kafka, logLevel } from 'kafkajs';
import pg from 'pg';

export function liveConfigFromEnv(env = process.env) {
  const need = ['AIVEN_KAFKA_BROKER', 'AIVEN_KAFKA_CA', 'AIVEN_KAFKA_CERT', 'AIVEN_KAFKA_KEY', 'AIVEN_PG_URL', 'AIVEN_PG_CA'];
  const missing = need.filter(k => !env[k]);
  if (missing.length) throw new Error('missing live configuration: ' + missing.join(', '));
  return { ...Object.fromEntries(need.map(k => [k, env[k]])), AIVEN_KAFKA_TOPIC: env.AIVEN_KAFKA_TOPIC || '' };
}

export function liveAdapter(cfg, { runId = Date.now().toString(36), partitions = 2 } = {}) {
  const ssl = { ca: [readFileSync(cfg.AIVEN_KAFKA_CA, 'utf8')], cert: readFileSync(cfg.AIVEN_KAFKA_CERT, 'utf8'), key: readFileSync(cfg.AIVEN_KAFKA_KEY, 'utf8') };
  const kafka = new Kafka({ clientId: 'flight-recorder', brokers: [cfg.AIVEN_KAFKA_BROKER], ssl, logLevel: logLevel.NOTHING });
  const pool = new pg.Pool({ connectionString: cfg.AIVEN_PG_URL.replace(/\?.*$/, ''), ssl: { ca: readFileSync(cfg.AIVEN_PG_CA, 'utf8'), rejectUnauthorized: true }, max: 4 });
  const topic = cfg.AIVEN_KAFKA_TOPIC || `flight-recorder-${runId}`; // free plans: pre-create the topic via the Aiven API
  const s = `fr_${runId.replace(/[^a-z0-9]/g, '')}`;
  const producer = kafka.producer({ idempotent: false });

  async function endOffsets() {
    const admin = kafka.admin(); await admin.connect();
    const o = await admin.fetchTopicOffsets(topic); await admin.disconnect();
    return new Map(o.map(x => [x.partition, Number(x.high)]));
  }

  return {
    name: 'aiven',
    topic, schema: s,
    async reset() {
      await pool.query(`create schema ${s}`);
      await pool.query(`create table ${s}.task(key text primary key, tenant text not null, seq int not null)`);
      await pool.query(`create table ${s}.outbox(id bigserial primary key, key text not null, tenant text not null, seq int not null, effect text not null, published boolean not null default false)`);
      await pool.query(`create table ${s}.processed(key text primary key)`);
      await pool.query(`create table ${s}.effect(id bigserial primary key, tenant text not null, seq int not null, effect text not null)`);
      if (!cfg.AIVEN_KAFKA_TOPIC) {
        const admin = kafka.admin(); await admin.connect();
        await admin.createTopics({ topics: [{ topic, numPartitions: partitions, replicationFactor: -1 }], waitForLeaders: true });
        await admin.disconnect();
      }
      await producer.connect();
    },
    async writeWithOutbox(a) {
      const c = await pool.connect();
      try {
        await c.query('begin');
        await c.query(`insert into ${s}.task(key,tenant,seq) values($1,$2,$3)`, [a.key, a.tenant, a.seq]);
        await c.query(`insert into ${s}.outbox(key,tenant,seq,effect) values($1,$2,$3,$4)`, [a.key, a.tenant, a.seq, a.effect]);
        await c.query('commit');
      } catch (e) { await c.query('rollback'); throw e; } finally { c.release(); }
    },
    async relay({ duplicateEvery }) {
      let sent = 0;
      for (let pass = 0; pass < 2; pass++) {
        const { rows } = await pool.query(`select * from ${s}.outbox where not published order by id`);
        for (const r of rows) {
          await producer.send({ topic, acks: -1, messages: [{ key: r.tenant, value: JSON.stringify({ run: runId, key: r.key, tenant: r.tenant, seq: r.seq, effect: r.effect }) }] });
          sent++;
          if (pass === 0 && Number(r.id) % duplicateEvery === 0) continue; // crash between send and mark
          await pool.query(`update ${s}.outbox set published = true where id = $1`, [r.id]);
        }
      }
      await producer.disconnect();
      return sent;
    },
    async consume({ group, crashAfterCommitAt, fromBeginning = false, dryRun = false, expectRedelivery }) {
      const ends = await endOffsets();
      const consumer = kafka.consumer({ groupId: `${topic}-${group}`, sessionTimeout: 10000, rebalanceTimeout: 10000 });
      await consumer.connect();
      await consumer.subscribe({ topic, fromBeginning: true });
      let handled = 0, suppressed = 0, redelivered = 0, seen = 0, wouldExecute = 0, crashed = false, crashedAt = null;
      const done = new Set();
      await new Promise((resolve, reject) => {
        const finishIfDone = () => { if ([...ends].every(([p, hi]) => hi === 0 || done.has(p))) resolve(); };
        finishIfDone();
        consumer.run({ autoCommit: false, eachMessage: async ({ partition, message }) => {
          if (crashed) return;
          const off = Number(message.offset);
          const m = JSON.parse(message.value.toString());
          if (m.run !== runId) { // earlier run on a reused topic: skip, but keep the group moving
            if (!dryRun) await consumer.commitOffsets([{ topic, partition, offset: String(off + 1) }]);
            if (off + 1 >= ends.get(partition)) { done.add(partition); finishIfDone(); }
            return;
          }
          seen++;
          if (dryRun) {
            const { rowCount } = await pool.query(`select 1 from ${s}.processed where key=$1`, [m.key]);
            if (!rowCount) wouldExecute++;
          } else {
            const c = await pool.connect();
            try {
              await c.query('begin');
              const ins = await c.query(`insert into ${s}.processed(key) values($1) on conflict do nothing`, [m.key]);
              if (ins.rowCount === 1) await c.query(`insert into ${s}.effect(tenant,seq,effect) values($1,$2,$3)`, [m.tenant, m.seq, m.effect]);
              else { suppressed++; if (expectRedelivery && expectRedelivery.partition === partition && expectRedelivery.offset === off) redelivered++; }
              await c.query('commit');
            } catch (e) { await c.query('rollback'); reject(e); return; } finally { c.release(); }
            handled++;
            if (crashAfterCommitAt && handled === crashAfterCommitAt) { crashed = true; crashedAt = { partition, offset: off }; resolve(); return; } // die before offset commit
            await consumer.commitOffsets([{ topic, partition, offset: String(off + 1) }]);
          }
          if (off + 1 >= ends.get(partition)) { done.add(partition); finishIfDone(); }
        } }).catch(reject);
      });
      await consumer.disconnect();
      return { suppressed, redelivered, seen, wouldExecute, crashedAt };
    },
    async effects() { const { rows } = await pool.query(`select effect from ${s}.effect order by id`); return rows.map(r => r.effect); },
    async auditOrderOk() {
      const { rows } = await pool.query(`select tenant, seq from ${s}.effect order by id`);
      const last = new Map();
      for (const r of rows) { if ((last.get(r.tenant) ?? 0) > r.seq) return false; last.set(r.tenant, r.seq); }
      return true;
    },
    async close() { await pool.end(); }
  };
}
