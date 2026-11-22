import {exact, fail, freeze, hashJson, jsonCopy, text} from './json.mjs';
const levels = ['source_observed', 'derived', 'geometry_measured', 'cross_checked', 'unavailable'];
export async function createClaim(dataset, input) {
  const spec = jsonCopy(input);
  exact(spec, ['method', 'question', 'status', 'level', 'value', 'refs', 'checks', 'reason'], 'claim');
  exact(spec.method, ['id', 'version', 'parameters'], 'method');
  text(spec.method.id, 'method ID'); text(spec.method.version, 'method version'); text(spec.question, 'question', 400);
  if (!['supported', 'abstained'].includes(spec.status) || !levels.includes(spec.level)) fail('INVALID_CLAIM', 'Unknown status or evidence level.');
  if (!Array.isArray(spec.refs) || spec.refs.length > 1000 || !Array.isArray(spec.checks) || spec.checks.length > 30 || typeof spec.reason !== 'string' || spec.reason.length > 1000) fail('INVALID_CLAIM', 'Claim limits exceeded.');
  if (spec.status === 'abstained') {
    if (spec.level !== 'unavailable' || spec.value !== null || spec.refs.length) fail('INVALID_CLAIM', 'Abstentions must not contain answers or fabricated citations.');
  } else {
    text(spec.value, 'supported value', 400);
    if (spec.level === 'unavailable' || !spec.refs.length) fail('INVALID_CLAIM', 'Supported claims need canonical source evidence.');
  }
  const ids = new Set();
  for (const ref of spec.refs) {
    dataset.resolve(ref);
    if (ids.has(ref.id)) fail('DUPLICATE_REFERENCE', 'Duplicate claim citation.');
    ids.add(ref.id);
  }
  const payload = {schema: 'evidence-kit.claim/v1', generation: dataset.manifest().generation, ...spec};
  return freeze({...payload, claimSha256: await hashJson(payload)});
}
export async function validateClaim(dataset, claim) {
  const c = jsonCopy(claim);
  const {schema, generation, claimSha256, ...spec} = c;
  const fresh = await createClaim(dataset, spec);
  if (schema !== fresh.schema || generation !== fresh.generation || claimSha256 !== fresh.claimSha256) fail('INVALID_CLAIM', 'Claim digest or source mismatch.');
  return fresh;
}
