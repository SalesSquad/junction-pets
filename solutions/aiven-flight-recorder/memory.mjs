// Deterministic in-memory adapter with Kafka-like semantics (keyed partitions,
// per-group committed offsets, redelivery from the last committed offset).
export function memoryAdapter({ partitions = 3 } = {}) {
  let outbox, log, offsets, processed, effectRows;
  const part = key => [...key].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % partitions;
  return {
    name: 'memory',
    async reset() { outbox = []; log = Array.from({ length: partitions }, () => []); offsets = new Map(); processed = new Set(); effectRows = []; },
    async writeWithOutbox(a) { outbox.push({ id: outbox.length + 1, published: false, msg: { ...a, partKey: a.tenant } }); },
    async relay({ duplicateEvery }) {
      let sent = 0;
      for (let pass = 0; pass < 2; pass++) for (const row of outbox) {
        if (row.published) continue;
        log[part(row.msg.partKey)].push(row.msg); sent++;
        if (pass === 0 && row.id % duplicateEvery === 0) continue; // crash before mark -> resent next pass
        row.published = true;
      }
      return sent;
    },
    async consume({ group, crashAfterCommitAt, fromBeginning, dryRun, expectRedelivery }) {
      let handled = 0, suppressed = 0, redelivered = 0, seen = 0, wouldExecute = 0;
      const committed = offsets.get(group) ?? Array(partitions).fill(fromBeginning ? 0 : 0);
      for (let p = 0; p < partitions; p++) {
        for (let off = committed[p]; off < log[p].length; off++) {
          const m = log[p][off]; seen++;
          if (dryRun) { if (!processed.has(m.key)) wouldExecute++; continue; }
          if (processed.has(m.key)) { suppressed++; if (expectRedelivery && expectRedelivery.partition === p && expectRedelivery.offset === off) redelivered++; }
          else { processed.add(m.key); effectRows.push({ tenant: m.tenant, seq: m.seq, effect: m.effect }); }
          handled++;
          if (crashAfterCommitAt && handled === crashAfterCommitAt) { offsets.set(group, committed); return { suppressed, redelivered, seen, wouldExecute, crashedAt: { partition: p, offset: off } }; }
          committed[p] = off + 1;
        }
      }
      offsets.set(group, committed);
      return { suppressed, redelivered, seen, wouldExecute };
    },
    async effects() { return effectRows.map(r => r.effect); },
    async auditOrderOk() {
      const last = new Map();
      for (const r of effectRows) { if ((last.get(r.tenant) ?? 0) > r.seq) return false; last.set(r.tenant, r.seq); }
      return true;
    }
  };
}
