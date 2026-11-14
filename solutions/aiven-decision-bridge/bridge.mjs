// Typed bridge from the Aiven companion's response.v1 to Chibi's human decision
// API (chibi-store action_decisions: PendingAction -> Approve/Decline bound to
// proposal_hash + version + authority_revision). The model never executes;
// the host hashes each proposal, stores it as pending and waits for a human.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

export const RESPONSE_SCHEMA = JSON.parse(readFileSync(new URL('../../pets/aiven/schemas/response.v1.json', import.meta.url), 'utf8'));
const OPS = new Set(RESPONSE_SCHEMA.properties.action_proposals.items.properties.operation.enum);
const HIGH_RISK = new Set(['service_delete', 'consumer_group_reset_offsets', 'service_power', 'credential_rotate']);

// Canonical JSON: sorted keys, no whitespace, so equal proposals hash equally.
export const canonical = v => Array.isArray(v) ? `[${v.map(canonical).join(',')}]`
  : v && typeof v === 'object' ? `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}` : JSON.stringify(v);
const sha = s => createHash('sha256').update(s).digest('hex');

export function validateResponse(r) {
  const errors = [];
  const req = RESPONSE_SCHEMA.required;
  if (!r || typeof r !== 'object') return ['not an object'];
  for (const k of req) if (!(k in r)) errors.push(`missing ${k}`);
  for (const k of Object.keys(r)) if (!(k in RESPONSE_SCHEMA.properties)) errors.push(`unknown field ${k}`);
  if (Array.isArray(r.executed_actions) && r.executed_actions.length) errors.push('executed_actions must be empty');
  for (const [i, p] of (r.action_proposals ?? []).entries()) {
    if (!OPS.has(p.operation)) errors.push(`proposal ${i}: unknown operation`);
    if (!p.target || !p.reason) errors.push(`proposal ${i}: target and reason required`);
    if (!['low', 'medium', 'high'].includes(p.risk)) errors.push(`proposal ${i}: invalid risk`);
    if (HIGH_RISK.has(p.operation) && p.risk !== 'high') errors.push(`proposal ${i}: ${p.operation} must be high risk`);
    if (typeof p.reversible !== 'boolean') errors.push(`proposal ${i}: reversible must be boolean`);
  }
  for (const f of r.facts ?? []) if (f.source_url !== null && !/^https:\/\/aiven\.io\//.test(f.source_url ?? '')) errors.push(`non-official source ${f.source_url}`);
  return errors;
}

// One Chibi PendingAction per proposal. Identity/authority values come from the host.
export function toPendingActions(response, ctx) {
  const errors = validateResponse(response);
  if (errors.length) throw new TypeError('invalid companion response: ' + errors.join('; '));
  return response.action_proposals.map((p, i) => {
    const payload = canonical({ operation: p.operation, target: p.target, parameters: p.parameters });
    const proposal = canonical({ ...p, adoption_id: ctx.adoptionId, agent_version_id: ctx.agentVersionId, authority_revision: ctx.authorityRevision });
    const proposal_hash = sha(proposal);
    return {
      id: `act_${proposal_hash.slice(0, 16)}`,
      adoption_id: ctx.adoptionId,
      proposal_hash,
      payload_hash: sha(payload),
      version: '1',
      authority_revision: ctx.authorityRevision,
      agent_version_id: ctx.agentVersionId,
      idempotency_key: `${ctx.conversationId}:${i}:${proposal_hash.slice(0, 12)}`,
      state: 'pending',
      preview_available: true,
      decision_available: true,
      title: `${p.operation} on ${p.target}`,
      chibi: ctx.chibi,
      risk: p.risk
    };
  });
}

// What the human UI sends back (ActionDecisionBinding + decision).
export const decisionFor = (pending, decision) => {
  if (!['approve', 'decline'].includes(decision)) throw new TypeError('decision must be approve or decline');
  return { decision, binding: { proposal_hash: pending.proposal_hash, version: pending.version, authority_revision: pending.authority_revision } };
};
