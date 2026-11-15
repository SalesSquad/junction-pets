// Typed bridge from the Aiven companion's response.v1 to Chibi's human decision
// API (chibi-store action_decisions: PendingAction -> Approve/Decline bound to
// proposal_hash + version + authority_revision). The model never executes;
// the host hashes each proposal, stores it as pending and waits for a human.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { types } from 'node:util';
import Ajv from 'ajv';

export const RESPONSE_SCHEMA = JSON.parse(readFileSync(new URL('../../pets/aiven/schemas/response.v1.json', import.meta.url), 'utf8'));
export const RESPONSE_SCHEMA_V2 = JSON.parse(readFileSync(new URL('../../pets/aiven/schemas/response.v2.json', import.meta.url), 'utf8'));
const OPS = new Set(RESPONSE_SCHEMA.properties.action_proposals.items.properties.operation.enum);
const HIGH_RISK = new Set(['service_delete', 'consumer_group_reset_offsets', 'service_power', 'credential_rotate']);
const ajv = new Ajv({ allErrors: true });
const validators = new Map([[RESPONSE_SCHEMA, ajv.compile(RESPONSE_SCHEMA)], [RESPONSE_SCHEMA_V2, ajv.compile(RESPONSE_SCHEMA_V2)]]);

// Only finite, bounded JSON values may enter a proposal hash. Never invoke getters.
function isSafeJson(value, active = new Set(), budget = { remaining: 10000 }, depth = 0) {
  if (--budget.remaining < 0 || depth > 32) return false;
  if (value === null || typeof value === 'boolean') return true;
  if (typeof value === 'string') return value.length <= 100000;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value !== 'object' || types.isProxy(value) || active.has(value)) return false;
  const array = Array.isArray(value), proto = Object.getPrototypeOf(value);
  if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) return false;
  const keys = Reflect.ownKeys(value), descriptors = Object.getOwnPropertyDescriptors(value);
  if (array && (value.length > budget.remaining || keys.length !== value.length + 1)) return false;
  active.add(value);
  for (const key of keys) {
    if (array && key === 'length') continue;
    const d = descriptors[key];
    if (typeof key !== 'string' || (array && (!/^(0|[1-9]\d*)$/.test(key) || Number(key) >= value.length)) || !d.enumerable || !Object.hasOwn(d, 'value') || !isSafeJson(d.value, active, budget, depth + 1)) return false;
  }
  active.delete(value);
  return true;
}

// Canonical JSON: sorted keys, no whitespace, so equal proposals hash equally.
export const canonical = v => Array.isArray(v) ? `[${v.map(canonical).join(',')}]`
  : v && typeof v === 'object' ? `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}` : JSON.stringify(v);
const sha = s => createHash('sha256').update(s).digest('hex');

export function validateResponse(r, schema, { officialHosts = ['aiven.io'] } = {}) {
  const errors = [];
  if (!r || typeof r !== 'object' || Array.isArray(r) || !isSafeJson(r)) return ['response must be a bounded JSON object'];
  schema ??= Object.hasOwn(r, 'governance') ? RESPONSE_SCHEMA_V2 : RESPONSE_SCHEMA;
  const req = schema.required;
  let validate = validators.get(schema);
  if (!validate) { validate = ajv.compile(schema); validators.set(schema, validate); }
  if (!validate(r)) errors.push(...validate.errors.map(e => `${e.instancePath || 'response'} ${e.message}`));
  for (const k of req) if (!(k in r)) errors.push(`missing ${k}`);
  for (const k of Object.keys(r)) if (!(k in schema.properties)) errors.push(`unknown field ${k}`);
  for (const h of Array.isArray(r.peer_handoffs) ? r.peer_handoffs : []) if (h?.receipt_label === 'LIVE') errors.push('a handoff proposal cannot be LIVE');
  if (Array.isArray(r.executed_actions) && r.executed_actions.length) errors.push('executed_actions must be empty');
  for (const [i, p] of (Array.isArray(r.action_proposals) ? r.action_proposals : []).entries()) {
    if (!p || typeof p !== 'object' || Array.isArray(p)) continue;
    if (!OPS.has(p.operation)) errors.push(`proposal ${i}: unknown operation`);
    if (!p.target || !p.reason) errors.push(`proposal ${i}: target and reason required`);
    if (!p.owner_role || !p.rollback) errors.push(`proposal ${i}: owner_role and rollback required`);
    if (!['low', 'medium', 'high'].includes(p.risk)) errors.push(`proposal ${i}: invalid risk`);
    if (HIGH_RISK.has(p.operation) && p.risk !== 'high') errors.push(`proposal ${i}: ${p.operation} must be high risk`);
    if (typeof p.reversible !== 'boolean') errors.push(`proposal ${i}: reversible must be boolean`);
  }
  // Facts cite only the companion's own official hosts (Aiven: aiven.io; other pets pass theirs).
  for (const f of Array.isArray(r.facts) ? r.facts : []) { if (!f || typeof f !== 'object' || f.source_url === null) continue; let host = ''; try { const u = new URL(f.source_url); host = u.protocol === 'https:' ? u.hostname : ''; } catch {} if (!officialHosts.some(h => host === h || host.endsWith('.' + h))) errors.push(`non-official source ${f.source_url}`); }
  return errors;
}

// One Chibi PendingAction per proposal. Identity/authority values come from the host.
export function toPendingActions(response, ctx, opts = {}) {
  const errors = validateResponse(response, undefined, opts);
  if (errors.length) throw new TypeError('invalid companion response: ' + errors.join('; '));
  for (const field of ['adoptionId', 'agentVersionId', 'authorityRevision', 'conversationId', 'chibi']) {
    if (!ctx || typeof ctx[field] !== 'string' || !ctx[field].trim()) throw new TypeError(`missing host context: ${field}`);
  }
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
      owner_role: p.owner_role,
      rollback: p.rollback,
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
