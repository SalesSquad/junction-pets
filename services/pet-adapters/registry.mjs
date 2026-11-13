// Explicit Node-only, offline capability bindings. No inferred provider or Chibi authority.
import {checkExperimentCard as run0} from '../../pets/aalto-university/experiment-card.mjs';
import {evaluateTrace as run1} from '../../pets/afterquery/failure-rubric.mjs';
import {rankAivenDocs as run2} from './aiven/adapter.mjs';
import {reviewCompatibility as run3} from '../../pets/arduino/compatibility.mjs';
import {checkEvidenceCard as run4} from '../../pets/astrazeneca/evidence-card.mjs';
import {checkBom as run5} from '../../pets/atech-dev/bom-checker.mjs';
import {assessCustodyTimeline as run6} from '../../pets/bahn-express/custody-timeline.mjs';
import {checkFieldProvenance as run7} from '../../pets/cala/provenance.mjs';
import {checkServiceRouting as run8} from '../../pets/city-of-espoo/service-routing.mjs';
import {planResponsiveMedia as run9} from '../../pets/cloudinary/responsive-media.mjs';
import {extractSnapshotFields as run10} from '../../pets/context-dev/extract-snapshot.mjs';
import {reviewSyntheticSbom as run11} from '../../pets/craci/sbom-review.mjs';
import {rankSuppliedResults as run12} from '../../pets/exa/search-ranking.mjs';
import {compareModelCandidates as run13} from '../../pets/featherless/model-selection.mjs';
import {checkEvaluationPlan as run14} from '../../pets/google-deepmind/evaluation-plan.mjs';
import {reviewDnsSnapshot as run15} from '../../pets/hostinger/dns-review.mjs';
import {reviewExperimentPlan as run16} from '../../pets/ignite-next/experiment-plan.mjs';
import {compareBenchmarkProtocols as run17} from '../../pets/intel/benchmark-protocol.mjs';
import {reviewStorageMatrix as run18} from '../../pets/ironshard/storage-matrix.mjs';
import {inspectEvidence as run19} from '../../pets/mariadb/explain-example.mjs';
import {evaluateWearableHistory as run20} from '../../pets/meta/wearable-permission.mjs';
import {reviewJobSpec as run21} from '../../pets/modal/job-spec.mjs';
import {compare as run22} from '../../pets/nvidia/comparability.mjs';
import {verifySyntheticHandoff as run23} from '../../pets/openai-codex/handoff.mjs';
import {reviewCollectionPlan as run24} from '../../pets/oxylabs/collection-plan.mjs';
import {reviewEpisode as run25} from '../../pets/qualia/episode-review.mjs';
import {checkRetargeting as run26} from '../../pets/rokoko/retargeting.mjs';
import {reviewFictionalSms as run27} from '../../pets/s-pankki/sms-guidance.mjs';
import {reviewPerceptionCoverage as run28} from '../../pets/scailab/perception-coverage.mjs';
import {reviewHandoff as run29} from '../../pets/stoa/handoff-proof.mjs';
import {reviewWorkflow as run30} from '../../pets/tieto/workflow-review.mjs';
import {scaleFictionalRecipe as run31} from '../../pets/valio-aimo/recipe-scale.mjs';
import {reviewGpuRunPlan as run32} from '../../pets/verda/gpu-run-plan.mjs';
import {triageFictionalSensorLog as run33} from '../../pets/wendy/sensor-triage.mjs';

const MAX_INPUT_BYTES = 65_536;
const MAX_OUTPUT_BYTES = 262_144;
const MAX_DEPTH = 12;
const MAX_NODES = 10_000;
const FORBIDDEN_KEYS = new Set(['__proto__', 'prototype', 'constructor']);
const definitions = [

  ['aalto-university', 'experiment-card', 'Check an invented experiment card', 'object', run0],
  ['afterquery', 'failure-rubric', 'Evaluate a synthetic failure trace', 'object', run1],
  ['aiven', 'docs-shortlist', 'Rank two pinned public documentation topics', 'query', run2],
  ['arduino', 'compatibility', 'Review declared board and sensor compatibility', 'object', run3],
  ['astrazeneca', 'evidence-card', 'Review a fictional aggregate evidence card', 'text', run4],
  ['atech-dev', 'bom-check', 'Review a fictional bill of materials', 'object', run5],
  ['bahn-express', 'custody-timeline', 'Review a fictional custody timeline', 'object', run6],
  ['cala', 'field-provenance', 'Check declared fictional field provenance', 'object', run7],
  ['city-of-espoo', 'service-routing', 'Route against fictional public service declarations', 'object', run8],
  ['cloudinary', 'responsive-media', 'Plan responsive variants for a declared public asset', 'text', run9],
  ['context-dev', 'snapshot-extraction', 'Extract literal fields from a supplied fictional snapshot', 'text', run10],
  ['craci', 'sbom-review', 'Review a synthetic software bill of materials', 'text', run11],
  ['exa', 'search-ranking', 'Rank supplied fictional search results', 'text', run12],
  ['featherless', 'model-comparison', 'Compare fictional model candidate declarations', 'text', run13],
  ['google-deepmind', 'evaluation-plan', 'Check a fictional model evaluation split plan', 'text', run14],
  ['hostinger', 'dns-review', 'Review a supplied fictional DNS snapshot', 'text', run15],
  ['ignite-next', 'experiment-plan', 'Review an invented customer experiment plan', 'text', run16],
  ['intel', 'benchmark-comparison', 'Compare fictional benchmark protocol declarations', 'text', run17],
  ['ironshard', 'storage-matrix', 'Review a fictional storage access matrix', 'text', run18],
  ['mariadb', 'explain-evidence', 'Classify supplied synthetic EXPLAIN evidence', 'object', run19],
  ['meta', 'wearable-permission', 'Replay a synthetic wearable permission history', 'object', run20],
  ['modal', 'job-spec', 'Review a fictional bounded compute job plan', 'text', run21],
  ['nvidia', 'benchmark-comparability', 'Compare declared synthetic graphics workload timings', 'pair', run22],
  ['openai-codex', 'handoff-review', 'Review a synthetic coding handoff', 'text', run23],
  ['oxylabs', 'collection-plan', 'Review a fictional public collection plan', 'text', run24],
  ['qualia', 'episode-review', 'Review a fictional robot episode declaration', 'text', run25],
  ['rokoko', 'retargeting', 'Check declared retargeting mappings', 'object', run26],
  ['s-pankki', 'sms-guidance', 'Review fictional SMS risk cue declarations', 'text', run27],
  ['scailab', 'perception-coverage', 'Review fictional perception sample coverage', 'text', run28],
  ['stoa', 'handoff-proof', 'Review a fictional document handoff', 'text', run29],
  ['tieto', 'workflow-review', 'Review a fictional workflow responsibility map', 'text', run30],
  ['valio-aimo', 'recipe-scaling', 'Scale a fictional recipe with explicit unknowns', 'text', run31],
  ['verda', 'gpu-run-plan', 'Review a fictional GPU run plan', 'text', run32],
  ['wendy', 'sensor-triage', 'Triage a fictional sensor snapshot', 'text', run33],

];

function exactRecord(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.length !== keys.length || actual.some(key => typeof key !== 'string' ||
      !keys.includes(key) || !Object.hasOwn(descriptors[key], 'value') || !descriptors[key].enumerable)) return null;
  return Object.fromEntries(keys.map(key => [key, descriptors[key].value]));
}

// Refuse ambiguous duplicate keys before JSON.parse can silently pick a value.
function parseBounded(text) {
  if (typeof text !== 'string' || text.length < 2 || text.length > MAX_INPUT_BYTES ||
      !text.isWellFormed() || Buffer.byteLength(text, 'utf8') > MAX_INPUT_BYTES) throw Error('input');
  const value = JSON.parse(text);
  const stack = [];
  for (const [token] of text.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\],:]/g)) {
    if (token === '{' || token === '[') {
      stack.push({object: token === '{', keyNext: true, keys: new Set()});
      if (stack.length > MAX_DEPTH) throw Error('depth');
    } else if (token === '}' || token === ']') stack.pop();
    else if (token === ',') {if (stack.at(-1)?.object) stack.at(-1).keyNext = true;}
    else if (token.startsWith('"') && stack.at(-1)?.object && stack.at(-1).keyNext) {
      const entry = stack.at(-1), key = JSON.parse(token);
      if (entry.keys.has(key) || FORBIDDEN_KEYS.has(key)) throw Error('key');
      entry.keys.add(key); entry.keyNext = false;
    }
  }
  let nodes = 0;
  function visit(node, depth = 0) {
    if (++nodes > MAX_NODES || depth > MAX_DEPTH) throw Error('bounds');
    if (typeof node === 'number' && !Number.isFinite(node)) throw Error('number');
    if (typeof node === 'string' && !node.isWellFormed()) throw Error('unicode');
    if (node && typeof node === 'object') {
      if (Array.isArray(node) && node.length > 1_000) throw Error('array');
      for (const child of Object.values(node)) visit(child, depth + 1);
    }
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('root');
  visit(value);
  return value;
}

function checkTraceFields(value) {
  if (!exactRecord(value, ['schemaVersion', 'synthetic', 'operation', 'expectedArtifact', 'events']) ||
      !Array.isArray(value.events) || value.events.length > 128) throw Error('trace');
  const eventFields = {
    'tool-call': [['type', 'id', 'operation']],
    'tool-result': [['type', 'callId', 'status'], ['type', 'callId', 'status', 'artifact']],
    'policy-refusal': [['type', 'reason']],
    'success-claim': [['type', 'artifact']],
  };
  for (const event of value.events) {
    const options = eventFields[event?.type];
    if (!options || !options.some(keys => exactRecord(event, keys))) throw Error('event');
  }
}

function schema(mode) {
  const key = mode === 'query' ? 'query' : 'jsonText';
  return {type: 'object', properties: {[key]: {type: 'string', minLength: mode === 'query' ? 3 : 2,
    maxLength: mode === 'query' ? 256 : MAX_INPUT_BYTES,
    description: mode === 'query' ? 'Public documentation topic only; zero network requests.' :
      'JSON text matching the linked company module contract. UTF-8 byte, nesting and collection bounds also apply.'}},
    required: [key], additionalProperties: false};
}

const bindings = new Map(definitions.map(([companySlug, operation, title, mode, run]) => {
  const id = `${companySlug}.${operation}`;
  return [id, {run, mode, descriptor: {
    id, petSlug: `junction-${companySlug}`, companySlug, title,
    description: `${title}. Runs local deterministic analysis only; declarations remain unverified.`,
    execution: 'offline-deterministic', available: true,
    effect: 'none', network: 'none', evidenceTier: 'deterministic-analysis',
    inputSchema: schema(mode), readOnly: true, networkAccess: false,
    providerConnected: false, chibiHostVerified: false,
    contractPath: companySlug === 'aiven' ? 'services/pet-adapters/aiven/README.md' : `pets/${companySlug}/`,
  }}];
}));

/** Safe copies: caller mutations never alter routing, schema or future discovery. */
export function discoverCapabilities(options = {}) {
  const keys = options && typeof options === 'object' ? Reflect.ownKeys(options) : [];
  const parsed = exactRecord(options, keys.length === 0 ? [] : ['petSlug']);
  if (!parsed || parsed.petSlug !== undefined && (typeof parsed.petSlug !== 'string' ||
      !/^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(parsed.petSlug))) throw new TypeError('Invalid capability filter');
  return [...bindings.values()].filter(({descriptor}) => parsed.petSlug === undefined ||
    descriptor.petSlug === parsed.petSlug).map(({descriptor}) => structuredClone(descriptor));
}

export function getCapability(id) {
  return typeof id === 'string' && bindings.has(id) ? structuredClone(bindings.get(id).descriptor) : null;
}

/** Complete bounded computation; ok does not mean the supplied scenario passed its review. */
export async function executeCapability(id, input) {
  const binding = typeof id === 'string' ? bindings.get(id) : undefined;
  if (!binding) return {ok: false, code: 'UNKNOWN_CAPABILITY'};
  const fail = code => ({ok: false, code, capabilityId: id, petSlug: binding.descriptor.petSlug});
  try {
    const key = binding.mode === 'query' ? 'query' : 'jsonText';
    const parsed = exactRecord(input, [key]);
    if (!parsed) return fail('INVALID_INPUT');
    let result;
    if (binding.mode === 'query') {
      if (typeof parsed.query !== 'string' || parsed.query.length < 3 || parsed.query.length > 256 ||
          !parsed.query.isWellFormed()) return fail('INVALID_INPUT');
      result = binding.run(parsed.query);
    } else {
      const value = parseBounded(parsed.jsonText);
      if (binding.descriptor.companySlug === 'afterquery') checkTraceFields(value);
      if (binding.mode === 'pair') {
        if (!exactRecord(value, ['baseline', 'candidate'])) return fail('INVALID_INPUT');
        result = binding.run(value.baseline, value.candidate);
      } else result = binding.run(binding.mode === 'text' ? parsed.jsonText : value);
    }
    const serialized = JSON.stringify(result);
    if (typeof serialized !== 'string' || Buffer.byteLength(serialized, 'utf8') > MAX_OUTPUT_BYTES) return fail('RESULT_TOO_LARGE');
    return {ok: true, capabilityId: id, petSlug: binding.descriptor.petSlug,
      execution: 'offline-deterministic', providerConnected: false, chibiHostVerified: false,
      result: JSON.parse(serialized)};
  } catch {
    // No stack traces, supplied text, provider errors or private input in failures.
    return fail('INVALID_INPUT');
  }
}
