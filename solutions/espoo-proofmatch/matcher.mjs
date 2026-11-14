// Policy v1. Pure functions: no IO, model calls, current clock or input mutation.
const types = Object.freeze({ artifact: 0.9, walkthrough: 0.7, statement: 0.2 });
const fail = (message) => { throw new TypeError(message); };
const text = (v) => typeof v === 'string' && v.trim().length > 0;
const id = (v) => text(v) && /^[a-zA-Z0-9-]+$/.test(v);
const date = (v) => text(v) && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v;
const timestamp = (v) => text(v) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().replace('.000', '') === v;
const unique = (items, key) => new Set(items.map(key)).size === items.length;
function windows(items) {
  if (!Array.isArray(items) || items.length > 100) fail('Availability must be a bounded list.');
  for (const w of items) if (!w || !timestamp(w.start) || !timestamp(w.end) || w.start >= w.end) fail('Availability needs valid UTC start and end times.');
}
export function validateRole(role) {
  if (!role || !id(role.id) || !id(role.employerId) || !Array.isArray(role.requiredSkills) || !role.requiredSkills.length || !unique(role.requiredSkills, s => s?.id)) fail('Choose a role with unique required skills.');
  for (const s of role.requiredSkills) if (!s || !id(s.id) || !text(s.label) || !Number.isFinite(s.weight) || s.weight <= 0 || s.weight > 100) fail('Skill weights must be positive and bounded.');
  windows(role.availability);
}
export function validateCandidate(candidate) {
  if (!candidate || !id(candidate.id) || !text(candidate.name) || typeof candidate.bio !== 'string' || !Array.isArray(candidate.evidence) || !unique(candidate.evidence, e => e?.id)) fail('Candidate needs an ID, name, bio and unique evidence cards.');
  windows(candidate.availability);
  for (const e of candidate.evidence) {
    if (!e || !id(e.id) || !Array.isArray(e.skills) || !e.skills.length || !e.skills.every(id) || !unique(e.skills, s => s) || !Object.hasOwn(types, e.sourceType) || !text(e.title) || !text(e.excerpt) || typeof e.outcome !== 'string' || !text(e.issuer) || !text(e.ref) || !date(e.observedDate) || e.externalVerification !== false) fail('Evidence needs labelled self-provided provenance; external verification is unsupported.');
  }
}
export function match(role, candidate, asOf) {
  validateRole(role); validateCandidate(candidate);
  if (!date(asOf)) fail('A fixed observation date is required.');
  const total = role.requiredSkills.reduce((n, s) => n + s.weight, 0);
  const skills = role.requiredSkills.map(skill => {
    const evidence = candidate.evidence.filter(e => e.skills.includes(skill.id) && e.observedDate <= asOf).map(e => {
      const ageDays = (Date.parse(asOf) - Date.parse(e.observedDate)) / 86400000;
      // Declared source form is a heuristic, never authenticity verification.
      const quality = Math.min(1, types[e.sourceType] + (e.outcome.trim() ? 0.1 : 0)) * (ageDays > 180 ? 0.8 : 1);
      return { id: e.id, quality: Math.round(quality * 100) / 100, ageDays };
    }).sort((a, b) => b.quality - a.quality || lexical(a.id, b.id));
    const support = evidence[0]?.quality ?? 0;
    return { ...skill, status: !evidence.length ? 'UNKNOWN' : support < 0.5 ? 'CLAIM_ONLY' : 'SELF_PROVIDED', support, evidence, contribution: 100 * skill.weight / total * support };
  });
  return { candidateId: candidate.id, score: Math.round(skills.reduce((n, s) => n + s.contribution, 0) * 10) / 10, skills, unknown: skills.filter(s => s.status === 'UNKNOWN').map(s => s.id) };
}
const lexical = (a, b) => a < b ? -1 : a > b ? 1 : 0;
export function rank(role, candidates, asOf) {
  validateRole(role);
  if (!Array.isArray(candidates) || !unique(candidates, c => c?.id)) fail('Candidate IDs must be unique.');
  return candidates.map(c => match(role, c, asOf)).sort((a, b) => b.score - a.score || lexical(a.candidateId, b.candidateId));
}
export function keywordRank(role, candidates) {
  validateRole(role);
  if (!Array.isArray(candidates) || !unique(candidates, c => c?.id)) fail('Candidate IDs must be unique.');
  return candidates.map(c => {
    validateCandidate(c);
    const tokens = c.bio.toLowerCase().match(/[a-z]+/g) ?? [];
    return { candidateId: c.id, score: role.requiredSkills.reduce((n, s) => n + tokens.filter(t => t === s.id).length, 0) };
  }).sort((a, b) => b.score - a.score || lexical(a.candidateId, b.candidateId));
}
const overlaps = (a, b) => a.start < b.end && b.start < a.end;
function ledger(records) {
  if (!Array.isArray(records)) fail('Draft ledger must be a list.');
  for (const r of records) {
    if (!r || !id(r.roleId) || !id(r.employerId) || !id(r.candidateId) || r.status !== 'DRAFT' || r.employerConsent !== true || r.candidateConsent !== true) fail('Invalid draft ledger entry.');
    windows([r.slot]);
  }
}
export function sharedSlots(role, candidate, records = []) {
  validateRole(role); validateCandidate(candidate); ledger(records);
  const slots = new Map();
  const duration = 20 * 60000;
  for (const a of role.availability) for (const b of candidate.availability) {
    const end = Math.min(Date.parse(a.end), Date.parse(b.end));
    // Fixed 20-minute UTC grid makes overlapping availability windows canonical.
    for (let start = Math.ceil(Math.max(Date.parse(a.start), Date.parse(b.start)) / duration) * duration; start + duration <= end; start += duration) {
      const slot = { start: new Date(start).toISOString().replace('.000', ''), end: new Date(start + duration).toISOString().replace('.000', '') };
      if (!records.some(r => (r.candidateId === candidate.id || r.employerId === role.employerId) && overlaps(slot, r.slot))) slots.set(slot.start, slot);
    }
  }
  return [...slots.values()].sort((a, b) => lexical(a.start, b.start));
}
export function createDraft({ role, candidate, slot, employerConsent, candidateConsent, records = [] }) {
  validateRole(role); validateCandidate(candidate); ledger(records);
  if (employerConsent !== true || candidateConsent !== true) fail('Both demo consent fields must be checked. These are simulated, not real consent.');
  if (records.some(r => r.roleId === role.id && r.candidateId === candidate.id)) fail('An introduction draft already exists for this pair. Reset the demo to start again.');
  windows([slot]);
  if (!sharedSlots(role, candidate, records).some(s => s.start === slot.start && s.end === slot.end)) fail('This slot is unavailable or conflicts with an existing draft. Choose another slot.');
  const draft = { id: `draft-${role.id}-${candidate.id}`, roleId: role.id, employerId: role.employerId, candidateId: candidate.id, slot: { ...slot }, status: 'DRAFT', employerConsent: true, candidateConsent: true };
  return { draft, records: [...records, draft] };
}
