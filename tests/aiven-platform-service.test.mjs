import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import * as platform from '../services/aiven-platform/index.mjs';

test('shared Aiven platform service exports every registered capability source', () => {
  for (const name of ['validateResponse', 'toPendingActions', 'decisionFor', 'lintResponse', 'systemFor', 'runFlightRecorder', 'memoryAdapter']) assert.equal(typeof platform[name], 'function', name);
});

test('offline demo: lint finds the missing proposal, repair clears it, the human decision binds the proposal', () => {
  const out = JSON.parse(execFileSync(process.execPath, ['services/aiven-platform/demo.mjs'], { encoding: 'utf8' }));
  assert.ok(out.lintIssuesBeforeRepair.some(i => /action_proposals is empty/.test(i)));
  assert.deepEqual(out.lintIssuesAfterRepair, []);
  assert.equal(out.pendingAction.state, 'pending');
  assert.equal(out.humanDecision.decision, 'approve');
  assert.deepEqual([out.flightRecorder.recorder.duplicates, out.flightRecorder.recorder.lost], [0, 0]);
});
