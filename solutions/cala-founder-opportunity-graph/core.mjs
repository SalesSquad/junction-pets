import { PRODUCT_SOURCE_DIGEST } from './source-meta.mjs';
export const BASE_SOURCE_SHA = 'a33f525171b6424d39dfc4c889b63e0fc5cb459e';
export const DEFAULT_GOAL = { sector: 'Climate software', geography: 'Nordics', stage: 'Seed', from: '2025-11-14', to: '2026-11-14' };
export const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function safeURL(value) {
  try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; } catch { return null; }
}
export function validDate(s) { return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0,10) === s; }
export function validateGoal(input, asOf) {
  if (!input || Object.getPrototypeOf(input) !== Object.prototype || Object.keys(input).some(k => !Object.hasOwn(DEFAULT_GOAL, k))) throw Error('Unknown goal field');
  const goal = Object.fromEntries(Object.keys(DEFAULT_GOAL).map(k => [k, input[k]]));
  if (!['Climate software','Health software'].includes(goal.sector) || !['Nordics','UK'].includes(goal.geography) || goal.stage !== 'Seed' || !validDate(goal.from) || !validDate(goal.to) || goal.from > goal.to || goal.to > asOf) throw Error('Choose a valid seed goal and date window ending on or before the fixture date.');
  return goal;
}
const dateIn = (date, from, to) => validDate(date) && date >= from && date <= to;
export function rank(data, input = DEFAULT_GOAL) {
  const goal = validateGoal(input, data.asOf);
  const ids = new Map(data.entities.map(e => [e.id, e]));
  const recentFrom = new Date(Date.parse(data.asOf) - 365*86400000).toISOString().slice(0,10);
  return data.entities.filter(e => e.kind !== 'company').map(entity => {
    const evidence = data.events.filter(e => e.investorId === entity.id);
    const issuerRecords = data.events.filter(e => e.role === 'ISSUER' && evidence.some(own => own.roundId === e.roundId && own.issuerId === e.issuerId));
    const reasons = [];
    const identityOK = entity.identity === 'resolved' && safeURL(entity.url) && data.entities.filter(e => e.id === entity.id || e.url === entity.url).length === 1;
    if (!identityOK) reasons.push('Ambiguous or conflicting exact identity — abstain');
    const groups = new Map();
    for (const e of evidence) {
      // Economic identity must be explicit; dates and names cannot establish a match.
      if (!e.roundId || !ids.has(e.issuerId)) continue;
      const key = JSON.stringify([e.issuerId, e.roundId]);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(e);
    }
    const accepted = [], rejected = [];
    for (const [key, rows] of groups) {
      const primary = rows.filter(e => e.source?.credibility === 'primary' && safeURL(e.source.url) && e.source.id && e.source.originId);
      const claims = primary.filter(e => e.kind === 'FUNDING_ROUND' && e.role === 'INVESTOR');
      const conflicting = claims.some(e => e.lead === true) && claims.some(e => e.lead === false);
      const dates = new Set(claims.map(e => e.eventDate));
      const eligible = claims.filter(e => e.lead === true && dateIn(e.eventDate,goal.from,goal.to) && dateIn(e.source.publishedAt,e.eventDate,data.asOf) && e.stage === goal.stage && e.sector === goal.sector && e.geography === goal.geography);
      if (conflicting || dates.size > 1) rejected.push({key, reason:'Contradictory round claims — withheld'});
      else if (eligible.length) accepted.push({key, event: eligible.sort((a,b)=>a.id.localeCompare(b.id))[0], citations: rows.map(e=>e.source)});
    }
    if (issuerRecords.length) reasons.push('ISSUER records describe the company raising capital, not investor participation');
    if (rejected.length) reasons.push('Contradiction: a round has conflicting lead or event-date claims');
    if (!accepted.length) reasons.push('No credible, explicit lead example in this goal and date window');
    if (evidence.some(e=>e.lead == null)) reasons.push('Lead or amount fields may be UNKNOWN; missing is not zero');
    if (evidence.some(e=>validDate(e.eventDate) && e.eventDate < recentFrom)) reasons.push('Stale evidence is excluded from active status');
    if (evidence.some(e=>e.source?.credibility !== 'primary')) reasons.push('Circular / secondary claim is not primary lead proof');
    const eligible = Boolean(identityOK && accepted.length);
    const active = eligible && accepted.some(r => dateIn(r.event.eventDate,recentFrom,data.asOf));
    return { entity, eligible, active, score: eligible ? accepted.length * 10 : null, roundCount: eligible ? accepted.length : null, amount: 'UNKNOWN', reasons, accepted: identityOK ? accepted : [], rejected, evidence, issuerRecords };
  }).sort((a,b)=>(b.score ?? -1)-(a.score ?? -1)||a.entity.id.localeCompare(b.entity.id));
}
export function makeArtifact(data, goal, reviews) {
  validateGoal(goal,data.asOf);
  if (!Array.isArray(reviews) || !reviews.length || reviews.length > 20) throw Error('Select at least one reviewed candidate');
  const ranked = rank(data,goal), seen = new Set();
  const shortlist = reviews.map(r => {
    if (!r || Object.keys(r).some(k=>!['id','note','approved'].includes(k)) || typeof r.id !== 'string' || typeof r.note !== 'string' || r.note.length > 2000 || r.approved !== true || seen.has(r.id)) throw Error('Each candidate needs explicit human approval and a bounded note');
    seen.add(r.id);
    const row = ranked.find(x=>x.entity.id === r.id && x.eligible);
    if (!row) throw Error('Unresolved or unsupported candidate cannot be shortlisted');
    return { entity: row.entity, humanReview: { state:'APPROVED_BY_LOCAL_USER', note:r.note }, score:row.score, active:row.active, economicRoundCount:row.roundCount, totalFunding:'UNKNOWN', rounds:row.accepted, warnings:row.reasons };
  });
  return { schema:'roundlens.shortlist.v1', mode:data.mode, baseSourceSha:BASE_SOURCE_SHA, productSourceDigest:PRODUCT_SOURCE_DIGEST, asOf:data.asOf, goal, rankingPolicy:'10 points per unique primary-sourced explicit lead round; identity abstention; 365-day active threshold', approvalMeaning:'Local user assertion, not verified identity or investment advice', shortlist, autoSend:false };
}
export const safeJSON = value => JSON.stringify(value,null,2).replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026');
