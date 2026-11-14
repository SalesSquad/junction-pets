/** One deterministic fallback when the executor cannot start a browser. */
import assert from 'node:assert/strict';
import { createSession, restoreSession } from './state.mjs';
import { FIXTURE, id } from './fixture.mjs';

const session = createSession();
let sequence = 600;
const command = (operation, payload = {}, revision = session.snapshot().revision) => ({
  schemaVersion: 1, taskId: FIXTURE.taskId, commandId: id(++sequence),
  expectedRevision: revision, operation, payload,
});
const apply = (operation, payload) => {
  const result = session.dispatch(command(operation, payload));
  assert.equal(result.error, undefined);
  return result;
};

apply('confirmStep', { stepId: id(201) });
apply('confirmStep', { stepId: id(202) });
apply('interrupt', {});
assert.equal(session.dispatch(command('observe', { evidenceId: id(500) })).code, 'EVIDENCE_UNAVAILABLE');
assert.equal(session.dispatch(command('observe', { evidenceId: id(502) })).code, 'SUBJECT_MISMATCH');
assert.equal(session.snapshot().revision, 3);
const resume = command('resume', { evidenceIds: [] });
const proposed = session.dispatch(resume);
assert.equal(proposed.revision, 4);
assert.deepEqual(proposed.steps.map((step) => step.userConfirmed), [true, true, false]);
assert.equal(proposed.proposal.stepId, id(203));
assert.deepEqual(proposed.proposal.evidenceIds, []);
assert.equal(session.dispatch(resume).replayed, true);
assert.equal(session.dispatch({ ...resume, payload: { evidenceIds: [id(501)] } }).code, 'COMMAND_COLLISION');
assert.equal(session.dispatch(command('confirmStep', { stepId: id(203) }, 3)).code, 'REVISION_CONFLICT');
assert.equal(session.dispatch(command('confirmStep', { stepId: id(203) }), { authority: 'webmcp' }).code, 'AUTHORITY_REQUIRED');
assert.deepEqual(restoreSession(session.exportJournal()).snapshot(), session.snapshot());
assert.equal(apply('confirmStep', { stepId: id(203) }).status, 'completed');
session.revokeCapture();
assert.deepEqual(session.snapshot().steps.map((step) => step.userConfirmed), [true, true, true]);
assert.equal(session.getPolicy().captureGeneration, 2);
assert.equal(session.dispatch(command('observe', { evidenceId: id(501) })).code, 'EVIDENCE_UNAVAILABLE');
const corrected = apply('correctStep', { stepId: id(202) });
assert.deepEqual(corrected.steps.map((step) => step.userConfirmed), [true, false, false]);
assert.equal(corrected.proposal, null);
apply('interrupt', {});
const resumedOffline = apply('resume', { evidenceIds: [] });
assert.equal(resumedOffline.nextUnconfirmedStep, id(202));
assert.deepEqual(resumedOffline.steps.map((step) => step.userConfirmed), [true, false, false]);
console.log(JSON.stringify({
  workId: 'META-EXEC-20261114/U1', result: 'pass', checkedAtUtc: new Date().toISOString(),
  executor: `Linux Node ${process.version}`, scope: 'one deterministic local synthetic scenario',
  observed: ['two confirmations survive interruption', 'old generation rejected', 'lookalike subject rejected', 'empty-evidence proposal does not complete step', 'idempotent retry and conflicting reuse distinguished', 'stale revision refused', 'assistant cannot confirm', 'local journal restores state', 'explicit user confirmation completes', 'capture revoke preserves confirmations and rejects late evidence', 'correction invalidates this and later confirmations', 'offline resume remains available'],
  finalRevision: resumedOffline.revision,
  notVerified: ['Rendered browser UI', '600×600 rendered layout', 'Native WebMCP assistant', 'Physical glasses', 'Chibi host'],
}, null, 2));
