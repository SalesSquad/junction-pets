import { createHash } from 'node:crypto';
import { validateGoal, validDate } from '../core.mjs';

export const MODE = 'SYNTHETIC_PROVIDER_REPLAY';
export const LIMITS = Object.freeze({ timeoutMs: 5000, totalTimeoutMs: 15000, maxResponseBytes: 262144, maxEntities: 25, maxRows: 100, maxCalls: 106 });
export const sha = value => createHash('sha256').update(typeof value === 'string' ? value : JSON.stringify(value)).digest('hex');
const uuid = x => typeof x === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(x);
const text = x => typeof x === 'string' && x.length > 0 && x.length <= 300 && !/[\x00-\x1f<>]/.test(x);
const fail = reason => { throw new Error(reason); };
const require = (ok, reason) => { if (!ok) fail(reason); };
const publicURL = (x, synthetic) => {
  try { const u = new URL(x); return u.protocol === 'https:' && !u.username && !u.password && !u.port && !u.hash && !u.search && (synthetic ? u.hostname === 'example.invalid' : /^[a-z][a-z0-9.-]*\.[a-z]{2,}$/i.test(u.hostname) && !/(^|\.)(localhost|local|internal|invalid|test|example)$/.test(u.hostname)); } catch { return false; }
};
const freeze = x => { if (x && typeof x === 'object') { Object.values(x).forEach(freeze); Object.freeze(x); } return x; };
const semantics = ['investorId','issuerId','economicRoundId','kind','role','lead','eventDate','stage','sector','geography','source'];

/** Host bridge protocol, NOT a claim about Cala's undocumented wire schema.
 * callTool returns UTF-8 JSON bytes after host-side streaming cap enforcement.
 * Host must enforce abort, authorization/revocation, public-data rights and MCP schema translation.
 */
export async function preview({ host, query, approvedEntityId, goal, clock, identity, limits = {} }) {
  const audit = [], synthetic = host?.mode === MODE;
  let calls = 0, previous = '0'.repeat(64);
  const ledger = (stage, digest) => { const row = { index: audit.length, stage, digest, previous }; row.hash = sha(row); previous = row.hash; audit.push(row); };
  const output = (status, reason, extra = {}) => freeze({ status, reason, mode: synthetic ? MODE : 'HOST_INJECTED_UNQUALIFIED', maturity: '2/6', autoOutreach: false, ...extra, ledger: { label: 'INTEGRITY NOT AUTHENTICITY', algorithm: 'SHA256 JSON chain v1', entries: audit, root: previous } });
  let lim, deadline;
  // Total deadline covers tools AND all asynchronous host policy/source checks.
  const bounded = async (fn, stage) => {
    require(++calls <= lim.maxCalls, 'CALL_LIMIT');
    require(Date.now() < deadline, 'TIMEOUT');
    const controller = new AbortController();
    let timer;
    try {
      return await Promise.race([
        Promise.resolve().then(() => fn(controller.signal)),
        new Promise((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(Error('TIMEOUT')); }, Math.min(lim.timeoutMs, deadline - Date.now())); })
      ]);
    } catch (e) { fail(e?.message === 'TIMEOUT' ? 'TIMEOUT' : `HOST_FAILURE_${stage}`); }
    finally { clearTimeout(timer); controller.abort(); }
  };
  try {
    require(host && ['callTool','authorize','verifySource'].every(k => typeof host[k] === 'function'), 'HOST_CAPABILITIES_REQUIRED');
    lim = { ...LIMITS, ...limits };
    require(Object.keys(limits).every(k => Object.hasOwn(LIMITS,k)) && Object.entries(lim).every(([k,v]) => Number.isInteger(v) && v > 0 && v <= LIMITS[k]), 'INVALID_LIMITS');
    deadline = Date.now() + lim.totalTimeoutMs;
    require(clock && validDate(clock.asOf) && typeof clock.now === 'string' && Number.isFinite(Date.parse(clock.now)) && clock.now.slice(0,10) === clock.asOf, 'CLOCK_REQUIRED');
    require(identity && text(identity.actorRef) && text(identity.tenantRef) && text(identity.approvalRef), 'IDENTITY_CONTEXT_REQUIRED');
    require(uuid(approvedEntityId), 'EXACT_USER_APPROVED_UUID_REQUIRED');
    require(text(query) && query.length <= 160, 'BOUNDED_QUERY_REQUIRED');
    validateGoal(goal, clock.asOf);
    ledger('request-context', sha({ query, approvedEntityId, goal, clock, identity, mode: host.mode ?? 'HOST_INJECTED_UNQUALIFIED', limits: lim }));
    const tools = ['entity_search','entity_introspection','entity_retrieval'];
    require(Array.isArray(host.tools) && host.tools.length === 3 && tools.every(t => host.tools.filter(x => x.name === t && x.capability === 'read' && x.readOnly === true).length === 1), 'READ_ONLY_TOOL_ALLOWLIST_REQUIRED');
    const context = { identity: { ...identity }, clock: { ...clock }, approvedEntityId, goal: { ...goal } };
    const call = async (name, args) => {
      require(tools.includes(name), 'TOOL_REFUSED');
      require(await bounded(signal => host.authorize({ ...structuredClone(context), name, signal }), 'AUTH') === true, 'HOST_AUTHORIZATION_REFUSED');
      const raw = await bounded(signal => host.callTool({ name, arguments: args, signal, maxResponseBytes: lim.maxResponseBytes }), name);
      require(typeof raw === 'string' || raw instanceof Uint8Array, 'BYTE_RESPONSE_REQUIRED');
      const bytes = typeof raw === 'string' ? Buffer.from(raw) : raw;
      require(bytes.byteLength <= lim.maxResponseBytes, 'RESPONSE_TOO_LARGE');
      let data;
      try { data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); } catch { fail('INVALID_JSON'); }
      ledger(name, sha(Buffer.from(bytes).toString('utf8')));
      return data;
    };
    const found = await call('entity_search', { query, limit: lim.maxEntities });
    require(Array.isArray(found.entities) && found.entities.length <= lim.maxEntities, 'ENTITY_LIMIT_OR_SCHEMA');
    require(found.entities.every(e => uuid(e.id)), 'SEARCH_IDENTITY_INVALID');
    const matches = found.entities.filter(e => e.id === approvedEntityId);
    require(matches.length === 1 && matches[0].identity === 'resolved' && matches[0].public === true, 'IDENTITY_ABSTENTION');
    const schema = await call('entity_introspection', { entityId: approvedEntityId });
    require(schema.entityId === approvedEntityId && Array.isArray(schema.fields) && schema.fields.length <= 40, 'INTROSPECTION_ID_OR_SCHEMA');
    const fields = {};
    for (const meaning of semantics) {
      const defs = schema.fields.filter(f => f.semantic === meaning);
      require(defs.length === 1 && text(defs[0].key) && !['__proto__','constructor','prototype'].includes(defs[0].key), 'MISSING_OR_AMBIGUOUS_FIELD');
      fields[meaning] = defs[0].key;
    }
    require(new Set(Object.values(fields)).size === semantics.length, 'AMBIGUOUS_FIELD_MAPPING');
    const retrieved = await call('entity_retrieval', { entityId: approvedEntityId, fields: Object.values(fields), limit: lim.maxRows });
    require(retrieved.entityId === approvedEntityId && Array.isArray(retrieved.rows) && retrieved.rows.length <= lim.maxRows, 'RETRIEVAL_ID_OR_LIMIT');
    const groups = new Map(), exclusions = [];
    for (const raw of retrieved.rows) {
      require(raw && typeof raw === 'object' && !Array.isArray(raw), 'ROW_SCHEMA');
      const row = Object.fromEntries(semantics.map(k => [k, Object.hasOwn(raw,fields[k]) ? raw[fields[k]] : null]));
      // A wrong identity invalidates the entire response; never accept a nearby name/UUID.
      require(row.investorId === approvedEntityId, 'WRONG_ENTITY_ID');
      if (!uuid(row.issuerId) || !text(row.economicRoundId)) { exclusions.push('MISSING_ECONOMIC_IDENTITY'); continue; }
      const key = JSON.stringify([row.issuerId,row.economicRoundId]);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    const rounds = [];
    for (const [key, rows] of groups) {
      if (rows.some(r => !['FUNDING_ROUND','FILING'].includes(r.kind))) { exclusions.push('MISSING_OR_AMBIGUOUS_EVENT_KIND'); continue; }
      const claims = rows.filter(r => r.kind === 'FUNDING_ROUND');
      if (!claims.length) { exclusions.push('FILING_IS_NOT_ROUND'); continue; }
      // Missing or contradictory role/lead/date in an economic round blocks that round.
      if (claims.some(r => r.role !== 'INVESTOR' || r.lead !== true || !validDate(r.eventDate)) || new Set(claims.map(r => r.eventDate)).size !== 1) { exclusions.push('AMBIGUOUS_ROLE_LEAD_OR_DATE'); continue; }
      if (claims.some(r => r.stage !== goal.stage || r.sector !== goal.sector || r.geography !== goal.geography || r.eventDate < goal.from || r.eventDate > goal.to || Date.parse(clock.asOf) - Date.parse(r.eventDate) > 365*86400000)) { exclusions.push('OUTSIDE_GOAL_OR_STALE'); continue; }
      const citations = [];
      let verified = true;
      for (const row of claims) {
        const s = row.source;
        if (!s || s.credibility !== 'primary' || !text(s.id) || !text(s.originId) || !publicURL(s.url,synthetic) || !validDate(s.publishedAt) || s.publishedAt < row.eventDate || s.publishedAt > clock.asOf) { verified = false; break; }
        const claimDigest = sha(row);
        const proof = await bounded(signal => host.verifySource({ ...structuredClone(context), source: structuredClone(s), claim: structuredClone(row), claimDigest, signal }), 'SOURCE');
        // Verification is outside the provider response, binds the exact assertion, and must
        // establish public disclosure rights and original issuer provenance (not URL shape).
        if (!proof || proof.claimDigest !== claimDigest || proof.url !== s.url || proof.originId !== s.originId || proof.issuerId !== row.issuerId || proof.primary !== true || proof.public !== true || proof.verifiedAt !== clock.now) { verified = false; break; }
        ledger('host-source-check', sha({ claimDigest, proof }));
        citations.push({ id: s.id, url: s.url, originId: s.originId, publishedAt: s.publishedAt, claimDigest });
      }
      if (!verified) { exclusions.push('UNVERIFIABLE_OR_FORGED_SOURCE'); continue; }
      rounds.push({ key, issuerId: claims[0].issuerId, economicRoundId: claims[0].economicRoundId, eventDate: claims[0].eventDate, lead: true, amount: 'UNKNOWN', citations: [...new Map(citations.map(s => [s.claimDigest,s])).values()] });
    }
    const evidence = { entityId: approvedEntityId, goal: { ...goal }, asOf: clock.asOf, rounds, exclusions: [...new Set(exclusions)].sort(), totalFunding: 'UNKNOWN' };
    const evidenceDigest = sha(evidence);
    return output(rounds.length ? 'PREVIEW_REQUIRES_HUMAN_REVIEW' : 'HOLD', rounds.length ? 'Evidence coverage only; no suitability or live activity assertion' : 'NO_SUPPORTED_LEAD', { evidence, evidenceDigest });
  } catch (error) {
    // Never return host exceptions, raw payloads, identity context or provider free text.
    const reason = /^[A-Z_]+$/.test(error.message) ? error.message : 'INVALID_INPUT';
    return output('REFUSE', reason);
  }
}

export function reviewPreview(result, { approved, evidenceDigest } = {}) {
  if (result?.status !== 'PREVIEW_REQUIRES_HUMAN_REVIEW' || approved !== true || evidenceDigest !== result.evidenceDigest || sha(result.evidence) !== evidenceDigest) return freeze({ status: 'HOLD', reason: 'EXACT_PREVIEW_HUMAN_APPROVAL_REQUIRED' });
  return freeze({ ...result, status: 'HUMAN_REVIEWED_EVIDENCE_ONLY_SHORTLIST', review: 'Local human assertion; host must authenticate reviewer before disclosure', investmentAdvice: false });
}
