#!/usr/bin/env node
// Parity vectors for porting bridge.mjs to Rust (chibi-api). Canonical JSON follows
// RFC 8785 (JCS): keys sorted by UTF-16 code units, ECMAScript number formatting,
// JSON.stringify string escaping. A port must reproduce every canonical string and hash.
//   node vectors/generate.mjs            -> writes vectors/bridge-vectors.v1.json
//   node vectors/generate.mjs --check    -> exits 1 if regeneration differs
import { readFileSync, writeFileSync } from 'node:fs';
import { canonical, toPendingActions } from '../bridge.mjs';

let s = 20261115; const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
const pick = xs => xs[Math.floor(r() * xs.length)];
const OPS = ['service_update_plan', 'service_create', 'service_delete', 'service_power', 'topic_create', 'topic_update', 'consumer_group_reset_offsets', 'integration_create', 'credential_rotate', 'other'];
const HIGH = new Set(['service_delete', 'consumer_group_reset_offsets', 'service_power', 'credential_rotate']);
const TARGETS = ['orders-kafka', 'pg-main', 'pathway.events.v1', 'eq_pg', 'kunta-ä-valkey', 'Ω-search', 'svc-💾'];
const VALUES = [1, 0, -7, 1.5, 0.1, 1e21, 1e-7, 2 ** 53 - 1, 'business-8', 'Äö "quoted"', true, false, null, [], [3, 1, 2], { z: 1, a: { y: 2, b: [1, { d: 4, c: 3 }] } }, { 'ä': 1, 'a': 2, 'Z': 3, 'é': 4, '\u{1F600}': 5 }];
const vectors = [];
for (let i = 0; i < 100; i++) {
  const n = 1 + Math.floor(r() * 3);
  const proposals = Array.from({ length: n }, () => { const op = pick(OPS); const params = {}; for (let k = 0; k < Math.floor(r() * 4); k++) params[pick(['plan', 'partitions', 'retention_ms', 'note', 'opts', 'ä', 'Z'])] = pick(VALUES);
    return { operation: op, target: pick(TARGETS), parameters: params, reason: pick(['lag', 'cost', 'DPO request', 'käyttäjä pyysi']), risk: HIGH.has(op) ? 'high' : pick(['low', 'medium', 'high']), reversible: r() < 0.5, owner_role: pick(['platform owner', 'data protection officer']), rollback: pick(['revert plan', 'restore from backup', 'none possible']) }; });
  const response = { answer: 'a', facts: [], assumptions: [], action_proposals: proposals, executed_actions: [], next_check: 'n' };
  const ctx = { adoptionId: `00000000-0000-4000-8000-${String(i).padStart(12, '0')}`, agentVersionId: '00000000-0000-4000-8000-0000000000aa', authorityRevision: String(1 + (i % 9)), conversationId: `conv-${i}`, chibi: 'junction.aiven' };
  const pending = toPendingActions(response, ctx);
  vectors.push({ i, input: { response, ctx }, canonicalProposals: proposals.map(p => canonical({ ...p, adoption_id: ctx.adoptionId, agent_version_id: ctx.agentVersionId, authority_revision: ctx.authorityRevision })), canonicalPayloads: proposals.map(p => canonical({ operation: p.operation, target: p.target, parameters: p.parameters })), expected: pending.map(p => ({ id: p.id, proposal_hash: p.proposal_hash, payload_hash: p.payload_hash, idempotency_key: p.idempotency_key, title: p.title })) });
}
const out = JSON.stringify({ schemaVersion: 1, canonicalization: 'RFC 8785 (JCS)', hash: 'sha256 hex of UTF-8 canonical JSON', idempotencyKey: '<conversationId>:<proposal index>:<proposal_hash[0..12]>', id: 'act_<proposal_hash[0..16]>', vectors }, null, 1) + '\n';
const file = new URL('./bridge-vectors.v1.json', import.meta.url);
if (process.argv.includes('--check')) { if (readFileSync(file, 'utf8') !== out) { console.error('bridge vectors drifted'); process.exit(1); } console.log('bridge vectors stable'); }
else { writeFileSync(file, out); console.log(JSON.stringify({ vectors: vectors.length, proposals: vectors.reduce((a, v) => a + v.expected.length, 0) })); }
