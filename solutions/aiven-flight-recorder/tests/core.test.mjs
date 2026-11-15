import test from 'node:test';
import assert from 'node:assert/strict';
import { plan, runBaseline, runFlightRecorder, compare } from '../core.mjs';
import { memoryAdapter } from '../memory.mjs';

test('baseline without a durable log duplicates and loses effects', () => {
  const b = runBaseline();
  assert.equal(b.expected, 200);
  assert.ok(b.duplicates > 0, 'blind retries must duplicate');
  assert.ok(b.lost > 0, 'a crash must lose queued work');
});

test('flight recorder keeps one effect per action under duplicates, crash and replay', async () => {
  const r = await runFlightRecorder(memoryAdapter());
  assert.deepEqual([r.expected, r.executed, r.duplicates, r.lost], [200, 200, 0, 0]);
  assert.ok(r.logMessages > 200, 'relay must have re-published rows');
  assert.ok(r.duplicatesSuppressed > 0);
  assert.equal(r.redeliveredAfterCrash, 1, 'exactly the crashed message is redelivered');
  assert.equal(r.replayNewEffects, 0);
  assert.equal(r.replayMessages, r.logMessages);
  assert.equal(r.auditOrderPerTenant, true);
  assert.match(compare(runBaseline(), r).verdict, /kept exactly-once effects/);
});

test('scenario is deterministic and rejects an invalid fault schedule', () => {
  assert.deepEqual(plan().slice(0, 2).map(a => a.key), ['run-1:action-0001', 'run-1:action-0002']);
  assert.throws(() => plan({ crashAt: 500 }), RangeError);
});
