// Bounded adaptation of PRIVATE Workbase matching semantics; see WORKBASE_REUSE.md.
import { validateCandidate } from './matcher.mjs';
import { fail, identifier, list, isRecord, immutable } from './demo-validation.mjs';
export const RELATED_THRESHOLD = 0.5;
export const RELATED_CREDIT = 0.6;
export const DEFAULT_PREFERRED_WEIGHT = 0.6;
const slug = value => identifier(value).toLowerCase();
const lexical = (a, b) => a < b ? -1 : a > b ? 1 : 0;
export const EVIDENCE_CODES = Object.freeze(['skill_match', 'related_skill_match', 'skill_unknown', 'role_interest_matches_intent', 'role_interest_unknown', 'role_interest_other', 'portfolio_unknown']);
const code = (code, args) => ({ code, args });

// Symmetric, strongest duplicate edge wins. No inferred/transitive relations.
export function createSkillGraph(pairs = [['typescript', 'javascript', 0.85]]) {
  const edges = new Map();
  for (const pair of list(pairs, 128)) {
    if (!Array.isArray(pair) || pair.length !== 3) fail('A relation needs two skills and a weight.');
    const [a, b] = [slug(pair[0]), slug(pair[1])];
    const weight = pair[2];
    if (a === b || !Number.isFinite(weight) || weight < 0 || weight > 1) fail('Relation weights must be finite in [0, 1] between different skills.');
    const key = [a, b].sort(lexical).join(':');
    edges.set(key, Math.max(edges.get(key) ?? 0, weight));
  }
  // Closure protects the graph even if callers retain or mutate their input.
  return Object.freeze({ relatedness(a, b) {
    a = slug(a); b = slug(b);
    return a === b ? 1 : edges.get([a, b].sort(lexical).join(':')) ?? 0;
  }, edgeCount: edges.size });
}
const builtin = createSkillGraph();
export function alignSkills(requirements, owned, graph = builtin) {
  if (!graph || typeof graph.relatedness !== 'function') fail('A skill graph is required.');
  const skills = [...new Set(list(owned, 64).map(slug))].sort(lexical);
  const seen = new Set();
  const rows = list(requirements, 32).map(requirement => {
    if (!isRecord(requirement) || typeof requirement.required !== 'boolean') fail('Distinguish required and preferred skills explicitly.');
    const id = slug(requirement.id);
    if (seen.has(id)) fail('Role skills must be unique after normalization.');
    seen.add(id);
    const weight = requirement.weight ?? (requirement.required ? 1 : DEFAULT_PREFERRED_WEIGHT);
    if (!Number.isFinite(weight) || weight <= 0 || weight > 1) fail('Normalized skill weight must be in (0, 1].');
    const exact = skills.includes(id);
    const related = exact ? [] : skills.map(via => {
      const relation = graph.relatedness(id, via);
      if (!Number.isFinite(relation) || relation < 0 || relation > 1) fail('Invalid graph relation.');
      return { via, relation };
    }).filter(item => item.relation >= RELATED_THRESHOLD).sort((a, b) => b.relation - a.relation || lexical(a.via, b.via));
    const best = related[0];
    const status = exact ? 'exact' : best ? 'related' : 'unknown';
    const credit = exact ? 1 : best ? RELATED_CREDIT * best.relation : 0;
    return { id, required: requirement.required, weight, status, credit, via: best?.via ?? null, relation: exact ? 1 : best?.relation ?? 0 };
  });
  const required = rows.filter(r => r.required), preferred = rows.filter(r => !r.required);
  // Preserve Workbase's required-count coverage and weighted preferred coverage.
  return immutable({ rows,
    requiredCoverage: required.length ? required.reduce((sum, r) => sum + r.credit, 0) / required.length : null,
    preferredCoverage: preferred.length ? preferred.reduce((sum, r) => sum + r.weight * r.credit, 0) / preferred.reduce((sum, r) => sum + r.weight, 0) : null,
    // null is deliberately used for silence rather than presenting perfection.
  });
}

export function conversation(role, candidate, asOf, graph = builtin) {
  if (!isRecord(role)) fail('Choose a role.');
  identifier(role.id);
  const required = list(role.requiredSkills, 32), preferred = list(role.preferredSkills ?? [], 32);
  for (const skill of required) if (!isRecord(skill) || !Number.isFinite(skill.weight) || skill.weight <= 0 || skill.weight > 100) fail('Required role weights must be positive and bounded.');
  const requirements = [...required.map(s => ({ ...s, required: true, weight: 1 })), ...preferred.map(s => ({ ...s, required: false }))];
  if (requirements.length > 32) fail('Too many role skills.');
  list(candidate?.evidence, 32).forEach(e => list(e?.skills, 32));
  validateCandidate(candidate);
  if (typeof asOf !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !Number.isFinite(Date.parse(asOf)) || new Date(asOf).toISOString().slice(0, 10) !== asOf) fail('Use a fixed valid evidence observation date.');
  const eligible = candidate.evidence.filter(e => e.observedDate <= asOf);
  const owned = [...new Set(eligible.flatMap(e => e.skills.map(slug)))];
  if (owned.length > 64) fail('Too many distinct candidate skills.');
  const alignment = alignSkills(requirements, owned, graph);
  const reasons = [], cautions = [];
  const rows = alignment.rows.map(row => {
    const sources = eligible.filter(e => e.skills.some(s => slug(s) === (row.via ?? row.id))).map(e => ({ id: e.id, sourceType: e.sourceType }));
    const evidence = code(row.status === 'exact' ? 'skill_match' : row.status === 'related' ? 'related_skill_match' : 'skill_unknown', {
      skill: row.id, required: row.required, via: row.via, relation: row.relation, credit: row.credit, sources,
    });
    (row.status === 'unknown' ? cautions : reasons).push(evidence);
    return { ...row, evidence };
  });
  let interests = null;
  if (candidate.interests !== undefined && candidate.interests !== null) interests = [...new Set(list(candidate.interests, 16).map(identifier))];
  const interest = !interests?.length ? 'unknown' : interests.includes(role.id) ? 'interested' : 'other';
  const interestEvidence = code(interest === 'interested' ? 'role_interest_matches_intent' : interest === 'unknown' ? 'role_interest_unknown' : 'role_interest_other', { roleId: role.id, interests });
  (interest === 'interested' ? reasons : cautions).push(interestEvidence);
  if (!eligible.length) cautions.push(code('portfolio_unknown', {}));
  return immutable({ candidateId: candidate.id, alignment: { ...alignment, rows }, interest, interestEvidence, reasons, cautions, externalVerification: false });
}

// Language is presentation; codes and args remain inspectable facts.
export function renderEvidence(item, displaySkill = id => id) {
  const a = item.args;
  switch (item.code) {
    case 'skill_match': return `${displaySkill(a.skill)}: exact skill label on self-provided material (${a.sources.map(s => `${s.id}, ${s.sourceType}`).join('; ')}). Proficiency is unverified.`;
    case 'related_skill_match': return `${displaySkill(a.via)} → ${displaySkill(a.skill)}: a seeded transferable relation, not an exact match. Ask how the experience transfers.`;
    case 'skill_unknown': return `${displaySkill(a.skill)}: no eligible exact or related material supplied. Ability is unknown.`;
    case 'role_interest_matches_intent': return 'Candidate explicitly chose this event conversation topic. Confirm together before meeting.';
    case 'role_interest_unknown': return 'Role interest not supplied. Ask the candidate; unknown interest never hides a person.';
    case 'role_interest_other': return 'The candidate listed other event topics. Ask whether this conversation would be useful; they remain selectable.';
    case 'portfolio_unknown': return 'No portfolio supplied. Offer a conversation or a small shared exercise instead.';
    default: return `Unrecognized evidence code: ${String(item.code)}`;
  }
}
