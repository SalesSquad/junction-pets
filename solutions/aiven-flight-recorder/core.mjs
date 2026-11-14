// Flight-recorder scenario: the same agent run with and without a durable,
// replayable event log. Adapters supply storage and transport; this module
// owns the fault schedule and the measurements.

export const DEFAULTS = Object.freeze({ actions: 200, tenants: 3, duplicateEvery: 10, crashAt: 120 });

export function plan(opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  if (!(o.actions > 0 && o.duplicateEvery > 1 && o.crashAt > 0 && o.crashAt < o.actions)) throw new RangeError('invalid scenario');
  return Array.from({ length: o.actions }, (_, i) => ({
    seq: i + 1,
    tenant: `tenant-${(i % o.tenants) + 1}`,
    key: `run-1:action-${String(i + 1).padStart(4, '0')}`,
    effect: `send-email:${i + 1}`
  }));
}

function measure(actions, effects) {
  const counts = new Map();
  for (const e of effects) counts.set(e, (counts.get(e) ?? 0) + 1);
  let duplicates = 0, lost = 0;
  for (const a of actions) {
    const n = counts.get(a.effect) ?? 0;
    if (n === 0) lost++;
    if (n > 1) duplicates += n - 1;
  }
  return { expected: actions.length, executed: effects.length, duplicates, lost };
}

// Baseline: in-process queue, producer retries without idempotency, a crash
// drops whatever is still queued. No external service.
export function runBaseline(opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const actions = plan(o);
  const queue = [];
  for (const a of actions) {
    queue.push(a);
    if (a.seq % o.duplicateEvery === 0) queue.push(a); // ack timeout -> blind retry
  }
  const effects = [];
  let delivered = 0;
  while (queue.length) {
    const m = queue.shift();
    effects.push(m.effect);
    delivered++;
    if (delivered === o.crashAt) { queue.length = 0; break; } // process dies, memory queue lost
  }
  return { mode: 'baseline', ...measure(actions, effects) };
}

// Flight recorder: transactional outbox -> relay (at-least-once) -> log ->
// idempotent consumer. Faults: relay re-publishes every duplicateEvery-th row
// (crash between send and mark), and the consumer crashes once after its
// database commit but before its offset commit.
export async function runFlightRecorder(adapter, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const actions = plan(o);
  await adapter.reset();
  for (const a of actions) await adapter.writeWithOutbox(a);
  const published = await adapter.relay({ duplicateEvery: o.duplicateEvery });
  const first = await adapter.consume({ group: 'effects', crashAfterCommitAt: o.crashAt });
  const second = await adapter.consume({ group: 'effects', expectRedelivery: first.crashedAt });
  const effects = await adapter.effects();
  const replay = await adapter.consume({ group: 'replay-audit', fromBeginning: true, dryRun: true });
  const audit = await adapter.auditOrderOk();
  return {
    mode: 'flight-recorder',
    transport: adapter.name,
    ...measure(actions, effects),
    logMessages: published,
    redeliveredAfterCrash: second.redelivered,
    duplicatesSuppressed: first.suppressed + second.suppressed,
    replayMessages: replay.seen,
    replayNewEffects: replay.wouldExecute,
    auditOrderPerTenant: audit
  };
}

export function compare(baseline, recorder) {
  return {
    baseline, recorder,
    verdict: recorder.duplicates === 0 && recorder.lost === 0 && recorder.replayNewEffects === 0 && recorder.auditOrderPerTenant
      ? 'flight-recorder kept exactly-once effects under duplicates, a consumer crash and full replay'
      : 'flight-recorder did NOT meet the exactly-once-effect target'
  };
}
