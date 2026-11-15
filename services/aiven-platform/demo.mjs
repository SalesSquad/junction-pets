#!/usr/bin/env node
// Offline demo of the shared capabilities: a typed answer is checked, repaired
// guidance is listed, its change proposal becomes a pending human decision, and the
// flight recorder shows replay-safe effects. No model, host or Aiven call.
import { lintResponse, toPendingActions, decisionFor, runBaseline, runFlightRecorder, compare, memoryAdapter } from './index.mjs';
const request = 'Our orders topic lags. Scale orders-kafka to business-8 before the demo.';
const draft = { answer: 'Scale it up.', facts: [], assumptions: [], action_proposals: [], executed_actions: [], next_check: 'Check per-partition lag first.', risks_and_side_effects: [], governance: { owner_role: 'platform owner', approvals_needed: [], data_classification: 'internal' }, peer_handoffs: [] };
const issues = lintResponse(draft, request);
const repaired = { ...draft, action_proposals: [{ operation: 'service_update_plan', target: 'orders-kafka', parameters: { plan: 'business-8' }, reason: 'Lag after cause check', risk: 'medium', reversible: true, owner_role: 'platform owner', rollback: 'Downgrade to the previous plan' }], risks_and_side_effects: ['Higher cost; verify on current Aiven pricing'] };
const ctx = { adoptionId: '00000000-0000-4000-8000-000000000001', agentVersionId: '00000000-0000-4000-8000-000000000002', authorityRevision: '1', conversationId: 'demo', chibi: 'any.pet' };
const [pending] = toPendingActions(repaired, ctx);
const flight = compare(runBaseline(), await runFlightRecorder(memoryAdapter()));
console.log(JSON.stringify({ lintIssuesBeforeRepair: issues, lintIssuesAfterRepair: lintResponse(repaired, request), pendingAction: { id: pending.id, title: pending.title, state: pending.state, risk: pending.risk }, humanDecision: decisionFor(pending, 'approve'), flightRecorder: { baseline: flight.baseline, recorder: { executed: flight.recorder.executed, duplicates: flight.recorder.duplicates, lost: flight.recorder.lost, replayNewEffects: flight.recorder.replayNewEffects } } }, null, 2));
