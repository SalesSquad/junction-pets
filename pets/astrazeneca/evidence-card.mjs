/** Pure, offline declaration checks for fictional aggregate cards, not research appraisal. */
export const LIMITS = Object.freeze({jsonBytes: 8192, depth: 6, sampleSize: 1000000, timepoints: 20, sourceId: 64});
const DESIGNS = Object.freeze({
  'randomized-simulation': 'simulated-random',
  'observational-simulation': 'simulated-observed',
  'single-group-simulation': 'not-applicable',
});
const DISCLAIMERS = Object.freeze(['no-real-world-inference', 'source-not-authenticated']);
const ROOT_FIELDS = Object.freeze(['schemaVersion', 'fictional', 'dataScope', 'studyDesign', 'sampleSize',
  'sampleUnit', 'methods', 'comparator', 'source', 'uncertainty', 'claim']);
const own = (value, key) => Object.hasOwn(value, key);
const integer = (value, max) => Number.isSafeInteger(value) && value >= 1 && value <= max;

// JSON.parse has already validated token syntax. Scan without recursion, normalize escaped
// keys and reject duplicate properties rather than silently accepting the last value.
function containerIssue(text) {
  const stack = [];
  for (const [token] of text.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\],:]/g)) {
    if (token === '{' || token === '[') {
      stack.push({object: token === '{', keyNext: true, keys: new Set()});
      if (stack.length > LIMITS.depth) return 'nesting-too-deep';
    } else if (token === '}' || token === ']') {
      stack.pop();
    } else if (token === ',') {
      if (stack.at(-1)?.object) stack.at(-1).keyNext = true;
    } else if (token.startsWith('"') && stack.at(-1)?.object && stack.at(-1).keyNext) {
      const current = stack.at(-1);
      const key = JSON.parse(token);
      if (current.keys.has(key)) return 'duplicate-key';
      current.keys.add(key);
      current.keyNext = false;
    }
  }
  return null;
}

/** Accept JSON text only. No I/O, URL retrieval, model, authorization, or clinical logic. */
export function checkEvidenceCard(text) {
  const findings = [];
  const add = (category, code, path, message) => findings.push({category, code, path, message});
  const invalid = (code, path, message) => add('invalid', code, path, message);
  const missing = path => add('missing', 'missing-field', path, 'An essential declaration is absent.');
  const result = () => ({
    schemaVersion: 1,
    scope: 'fictional-structure-only',
    structuralStatus: findings.some(f => f.category === 'invalid') ? 'rejected' : findings.length ? 'incomplete' : 'complete',
    findings,
    validation: {authorizationGranted: false, sourceAuthenticated: false, evidenceTruthValidated: false, clinicalValidated: false},
    notice: 'Checks declared structure only, not evidence truth, source authenticity, authorization or clinical validity.',
  });
  const rejectInput = (code, message) => { invalid(code, '$', message); return result(); };
  if (typeof text !== 'string') return rejectInput('json-text-required', 'Supply bounded JSON text, not an object or executable value.');
  if (text.length > LIMITS.jsonBytes || Buffer.byteLength(text, 'utf8') > LIMITS.jsonBytes) {
    return rejectInput('input-too-large', 'The JSON text exceeds the fictional fixture byte limit.');
  }
  let card;
  try { card = JSON.parse(text); } catch { return rejectInput('invalid-json', 'The input is not valid JSON.'); }
  const issue = containerIssue(text);
  if (issue) return rejectInput(issue, 'Duplicate keys or excessive nesting are not accepted.');

  function record(value, required, path, optional = []) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      invalid('object-required', path, 'A declaration object is required.');
      return false;
    }
    if (Object.keys(value).some(key => !required.includes(key) && !optional.includes(key))) {
      invalid('unsupported-fields', path, 'Fields outside the fictional card contract are not accepted.');
    }
    for (const key of required) if (!own(value, key)) missing(`${path}.${key}`);
    return true;
  }
  function choice(object, key, choices, path) {
    if (own(object, key) && !choices.includes(object[key])) {
      invalid('invalid-value', `${path}.${key}`, 'The declared value is outside the fictional vocabulary.');
    }
  }
  function count(object, key, max, path) {
    if (own(object, key) && !integer(object[key], max)) {
      invalid('invalid-count', `${path}.${key}`, 'A positive safe integer within the fixture limit is required.');
    }
  }
  if (!record(card, ROOT_FIELDS, '$')) return result();
  for (const [key, expected] of [['schemaVersion', 1], ['fictional', true],
    ['dataScope', 'aggregate-simulation'], ['sampleUnit', 'fictional-record']]) {
    if (card[key] !== expected) invalid('fictional-contract-required', `$.${key}`, 'The explicit fictional aggregate contract is required.');
  }
  choice(card, 'studyDesign', Object.keys(DESIGNS), '$');
  count(card, 'sampleSize', LIMITS.sampleSize, '$');

  if (own(card, 'methods') && record(card.methods, ['allocation', 'measurement', 'analysis', 'timepoints'], '$.methods')) {
    const methods = card.methods;
    choice(methods, 'allocation', Object.values(DESIGNS), '$.methods');
    choice(methods, 'measurement', ['fictional-score'], '$.methods');
    choice(methods, 'analysis', ['descriptive-summary'], '$.methods');
    count(methods, 'timepoints', LIMITS.timepoints, '$.methods');
    if (typeof card.studyDesign === 'string' && own(DESIGNS, card.studyDesign) && own(methods, 'allocation') && methods.allocation !== DESIGNS[card.studyDesign]) {
      invalid('design-method-mismatch', '$.methods.allocation', 'The declared allocation does not match the declared simulation design.');
    }
  }
  if (own(card, 'comparator') && record(card.comparator, ['kind'], '$.comparator', ['sampleSize', 'reason'])) {
    const comparator = card.comparator;
    choice(comparator, 'kind', ['simulated-group', 'none'], '$.comparator');
    if (comparator.kind === 'simulated-group') {
      if (!own(comparator, 'sampleSize')) missing('$.comparator.sampleSize');
      count(comparator, 'sampleSize', LIMITS.sampleSize, '$.comparator');
      if (own(comparator, 'reason')) invalid('contradictory-comparator', '$.comparator', 'A simulated group cannot also declare an absence reason.');
      if (card.studyDesign === 'single-group-simulation') invalid('comparator-design-mismatch', '$.comparator', 'A single-group declaration cannot also declare a comparison group.');
      if (integer(card.sampleSize, LIMITS.sampleSize) && integer(comparator.sampleSize, LIMITS.sampleSize) && comparator.sampleSize >= card.sampleSize) {
        invalid('comparator-count-mismatch', '$.comparator.sampleSize', 'The declared comparison group must leave at least one fictional record in the other group.');
      }
    } else if (comparator.kind === 'none') {
      if (!own(comparator, 'reason')) missing('$.comparator.reason');
      choice(comparator, 'reason', ['single-group-design'], '$.comparator');
      if (own(comparator, 'sampleSize')) invalid('contradictory-comparator', '$.comparator', 'An absent comparator cannot also declare a group size.');
      if (typeof card.studyDesign === 'string' && own(DESIGNS, card.studyDesign) && card.studyDesign !== 'single-group-simulation') {
        invalid('comparator-required', '$.comparator', 'The declared comparison design requires a simulated group.');
      }
    }
  }
  if (own(card, 'source') && record(card.source, ['kind', 'id'], '$.source')) {
    choice(card.source, 'kind', ['fictional-fixture'], '$.source');
    if (own(card.source, 'id') && (typeof card.source.id !== 'string' || card.source.id.length > LIMITS.sourceId ||
      !/^fictional-fixture-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(card.source.id))) {
      invalid('fictional-source-required', '$.source.id', 'Use a bounded fictional-fixture identifier, not a URL or real-study citation.');
    }
  }
  if (own(card, 'uncertainty') && record(card.uncertainty, ['scope', 'missingness', 'limitations'], '$.uncertainty')) {
    const uncertainty = card.uncertainty;
    choice(uncertainty, 'scope', ['simulation-only'], '$.uncertainty');
    choice(uncertainty, 'missingness', ['none-declared', 'some-declared', 'not-assessed'], '$.uncertainty');
    if (own(uncertainty, 'limitations')) {
      const limitations = uncertainty.limitations;
      if (!Array.isArray(limitations) || limitations.length > DISCLAIMERS.length || new Set(limitations).size !== limitations.length ||
        limitations.some(value => !DISCLAIMERS.includes(value))) {
        invalid('invalid-limitations', '$.uncertainty.limitations', 'Use distinct limitations from the fictional vocabulary.');
      } else if (DISCLAIMERS.some(value => !limitations.includes(value))) {
        add('missing', 'missing-limitation', '$.uncertainty.limitations', 'Both no-real-world-inference and source-not-authenticated must be declared.');
      }
    }
  }
  if (own(card, 'claim') && record(card.claim, ['kind', 'outcome'], '$.claim')) {
    choice(card.claim, 'outcome', ['fictional-score'], '$.claim');
    if (own(card.claim, 'kind') && !['descriptive', 'association'].includes(card.claim.kind)) {
      invalid('unsupported-claim', '$.claim.kind', 'Causal, efficacy and other unsupported claim types are outside this structural-only checker.');
    }
    if (card.claim.kind === 'association' && card.comparator?.kind === 'none') {
      invalid('association-needs-comparator', '$.claim.kind', 'An association declaration requires a simulated comparison group.');
    }
  }
  return result();
}
