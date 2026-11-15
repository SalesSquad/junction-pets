// Local, deterministic review workspace. No network access or device operations.
import {readFileSync} from 'node:fs';
import {types} from 'node:util';
import {reviewCompatibility} from '../compatibility.mjs';

const checkerVersion = JSON.parse(readFileSync(new URL('../pet.json', import.meta.url), 'utf8')).version;
const limitations = [
  'All designs and electrical declarations are synthetic or user-supplied and unauthenticated.',
  'Evidence labels are user assertions. URLs, revisions and excerpts are not fetched, authenticated or independently verified.',
  'A consistent result is not authorization, physical safety certification or an instruction to energize hardware.',
  'Actual board revisions, component ratings, wiring, tolerances, transients and thermal behavior remain unverified.',
  'Current budgets describe supplied declarations only; unknown limits remain null. No real device or provider was accessed.',
];

export class WorkspaceError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const fail = (message, status = 400) => { throw new WorkspaceError(status, message); };

// Descriptor-only copying prevents caller getters, methods, iterators and hooks
// from running. This also provides fresh values for every output and request.
function copyData(value, state = {values: 12000, properties: 20000, characters: 262144}, depth = 0, seen = new Set()) {
  if (--state.values < 0 || depth > 12 || types.isProxy(value)) fail('Unsupported or oversized plain-data input.');
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    if ((state.characters -= value.length) < 0) fail('Input text exceeds the local workspace limit.');
    return value;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) fail('Nonfinite numbers are unsupported.');
    return value;
  }
  if (typeof value !== 'object' || seen.has(value)) fail('Only acyclic plain JSON-like data is supported.');
  const array = Array.isArray(value), proto = Object.getPrototypeOf(value);
  if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) fail('Unsupported data prototype.');
  const keys = Reflect.ownKeys(value);
  if ((state.properties -= keys.length) < 0 || keys.some(key => typeof key !== 'string')) fail('Unsupported or oversized data properties.');
  if (array) {
    const length = Object.getOwnPropertyDescriptor(value, 'length').value;
    if (length > 100 || keys.length !== length + 1) fail('Arrays must be dense and contain at most 100 entries.');
    for (let i = 0; i < length; i++) if (!Object.hasOwn(value, String(i))) fail('Sparse or extended arrays are unsupported.');
  } else if (keys.length > 20) fail('Record contains too many properties.');
  const result = array ? [] : Object.create(null);
  seen.add(value);
  for (const key of keys) {
    if (array && key === 'length') continue;
    if ((state.characters -= key.length) < 0) fail('Input text exceeds the local workspace limit.');
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) fail('Getters, setters and hidden fields are unsupported.');
    result[key] = copyData(descriptor.value, state, depth + 1, seen);
  }
  seen.delete(value);
  return result;
}
function exactRecord(value, fields, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) fail(`${label} must be a plain record.`);
  const keys = Object.keys(value);
  if (keys.length !== fields.length || fields.some(key => !Object.hasOwn(value, key))) fail(`${label} has missing or unknown fields.`);
}
function requestFields(input, fields, label) {
  if (types.isProxy(input) || input === null || typeof input !== 'object' || Array.isArray(input)) fail(`${label} must be a plain record.`);
  const proto = Object.getPrototypeOf(input);
  if (proto !== Object.prototype && proto !== null) fail(`${label} must be a plain record.`);
  const keys = Reflect.ownKeys(input);
  if (keys.length !== fields.length || keys.some(key => typeof key !== 'string' || !fields.includes(key))) fail(`${label} has missing or unknown fields.`);
  const result = Object.create(null);
  for (const key of fields) {
    const descriptor = Object.getOwnPropertyDescriptor(input, key);
    if (!descriptor || !Object.hasOwn(descriptor, 'value') || !descriptor.enumerable) fail(`${label} requires plain data fields.`);
    result[key] = descriptor.value;
  }
  return result;
}

function checkedDesign(design) {
  const review = reviewCompatibility(design);
  if (review.status === 'invalid') {
    // These diagnostics are fresh core-checker output, never caller objects.
    // Keep the HTTP error actionable without exposing raw input or stacks.
    const diagnostic = review.diagnostics[0];
    const summary = (value, max, fallback) => {
      if (!['string', 'number', 'boolean'].includes(typeof value)) return fallback;
      return String(value).replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, max);
    };
    if (diagnostic) {
      const path = summary(diagnostic.path, 160, '$');
      const expected = summary(diagnostic.expected, 180, 'the documented compatibility schema');
      const correction = summary(diagnostic.correction, 240, 'Review the declaration against the documented schema.');
      fail(`Design invalid at ${path}: expected ${expected}. ${correction}`, 422);
    }
    fail('Design does not match a supported compatibility schema.', 422);
  }
  return review;
}
function scalarAtPath(design, path) {
  // Only the documented board.field / sensors[0].pins[0].field notation.
  if (typeof path !== 'string' || path.length === 0 || path.length > 160 || !/^[A-Za-z][A-Za-z0-9]*(?:(?:\.[A-Za-z][A-Za-z0-9]*)|(?:\[(?:0|[1-9][0-9]*)\]))*$/.test(path)) {
    fail('Evidence path must name an existing scalar design field.');
  }
  const tokens = path.match(/[A-Za-z][A-Za-z0-9]*|[0-9]+/g);
  let value = design;
  for (const token of tokens) {
    if (value === null || typeof value !== 'object' || !Object.hasOwn(value, token)) fail('Evidence path does not exist in this design.');
    if (Array.isArray(value) && !/^(?:0|[1-9][0-9]*)$/.test(token)) fail('Evidence array paths must name indexed design entries.');
    const descriptor = Object.getOwnPropertyDescriptor(value, token);
    if (!Object.hasOwn(descriptor, 'value')) fail('Evidence path must use data properties.');
    value = descriptor.value;
  }
  if (value !== null && !['string', 'number', 'boolean'].includes(typeof value)) fail('Evidence path must end at a scalar field.');
}
function text(value, max, field) {
  if (typeof value !== 'string' || value.length > max) fail(`Evidence ${field} must be text within its documented limit.`);
}
function evidenceRows(rows, design) {
  if (!Array.isArray(rows) || rows.length > 100) fail('Evidence must be an array of at most 100 rows.');
  return rows.map(row => {
    exactRecord(row, ['path', 'status', 'url', 'revision', 'excerpt', 'note'], 'Evidence row');
    text(row.path, 160, 'path'); scalarAtPath(design, row.path);
    if (!['fictional', 'supplied', 'reviewed'].includes(row.status)) fail('Unsupported evidence status.');
    text(row.url, 2048, 'url'); text(row.revision, 160, 'revision');
    text(row.excerpt, 2000, 'excerpt'); text(row.note, 1000, 'note');
    if (row.url !== '') {
      let url;
      try { url = new URL(row.url); } catch { fail('Evidence URL must be an HTTPS URL without credentials.'); }
      if (row.url !== row.url.trim() || /[\u0000-\u0020\u007f]/.test(row.url) || url.protocol !== 'https:' || !url.hostname || url.username || url.password) {
        fail('Evidence URL must be an HTTPS URL without credentials.');
      }
    }
    if (row.status === 'reviewed' && [row.url, row.revision, row.excerpt, row.note].some(value => value.trim() === '')) {
      fail('A user-asserted reviewed row requires URL, revision, excerpt and review note.');
    }
    const attribution = row.status === 'reviewed' ? 'USER-ASSERTED reviewed' : row.status === 'supplied' ? 'USER-SUPPLIED unverified' : 'FICTIONAL declaration';
    return {...row, attribution};
  });
}

// Text exported as Markdown is deliberately escaped; it is never trusted HTML.
const markdown = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/[\\`*_{}\[\]#|!]/g, '\\$&').replace(/[\r\n]+/g, ' ');
const known = value => value === null ? 'unknown' : `${value} mA`;
function readableReport(report) {
  const {review, evidence} = report;
  const lines = ['# Fictional board and sensor review', '',
    `Checker version: ${markdown(report.checkerVersion)}`,
    `Result: ${markdown(review.status)} (${markdown(review.inputSchema)})`,
    'SYNTHETIC / USER-SUPPLIED DATA — authorization: false; safety certification: false.', '',
    '## Declared design', ''];
  function fields(value, path = '') {
    for (const key of Object.keys(value)) {
      const field = Array.isArray(value) ? `${path}[${key}]` : path ? `${path}.${key}` : key;
      const child = value[key];
      if (child !== null && typeof child === 'object') fields(child, field);
      else lines.push(`- ${markdown(field)}: ${markdown(child)}`);
    }
  }
  fields(report.design);
  lines.push('', '## Declared current budgets', '');
  for (const [name, budget] of [['Total', review.budgets.total], ['Signals', review.budgets.signal], ...review.budgets.pins.map(pin => [`Pin ${pin.pin}`, pin])]) {
    lines.push(`- ${markdown(name)}: demand ${known(budget.demandMa)}, limit ${known(budget.limitMa)}, headroom ${known(budget.headroomMa)}.`);
  }
  lines.push('', '## Issues and corrections', '');
  if (!review.diagnostics.length) lines.push('No conflicts detected within the supplied fictional declarations.');
  for (const diagnostic of review.diagnostics) {
    lines.push(`- ${markdown(diagnostic.code)} at ${markdown(diagnostic.path)}: supplied ${markdown(diagnostic.actual)}; expected ${markdown(diagnostic.expected)}. ${markdown(diagnostic.correction)}`);
  }
  lines.push('', '## Evidence supplied by the user', '');
  if (!evidence.length) lines.push('No evidence rows supplied; all declarations remain unauthenticated.');
  for (const row of evidence) {
    lines.push(`- ${markdown(row.path)} — ${markdown(row.attribution)}; URL: ${markdown(row.url || '(none)')}; revision: ${markdown(row.revision || '(none)')}; excerpt: ${markdown(row.excerpt || '(none)')}; note: ${markdown(row.note || '(none)')}.`);
  }
  lines.push('', '## Unknowns and limitations', '', ...report.limitations.map(item => `- ${item}`), ...review.unknowns.map(item => `- ${item}`), '');
  return lines.join('\n');
}

export function buildWorkspace(input) {
  const data = requestFields(input, ['design', 'evidence'], 'Review request');
  const review = checkedDesign(data.design);
  const design = copyData(data.design);
  const evidence = evidenceRows(copyData(data.evidence), design);
  const report = {schemaVersion: 1, checkerVersion, design, review, evidence,
    limitations: [...limitations], synthetic: true, authorization: false, safetyCertification: false};
  return {checkerVersion, review, evidence, reportText: readableReport(report), report};
}

export function compareDesigns(input) {
  const data = requestFields(input, ['baseline', 'candidate'], 'Comparison request');
  const baseline = checkedDesign(data.baseline), candidate = checkedDesign(data.candidate);
  const before = new Set(baseline.issues), after = new Set(candidate.issues);
  const change = key => {
    const baselineHeadroomMa = baseline.budgets[key].headroomMa, candidateHeadroomMa = candidate.budgets[key].headroomMa;
    return {baselineHeadroomMa, candidateHeadroomMa,
      deltaHeadroomMa: baselineHeadroomMa === null || candidateHeadroomMa === null ? null : candidateHeadroomMa - baselineHeadroomMa};
  };
  return {baseline, candidate,
    addedIssues: [...after].filter(issue => !before.has(issue)),
    resolvedIssues: [...before].filter(issue => !after.has(issue)),
    budgetChanges: {total: change('total'), signal: change('signal')}, limitations: [...limitations]};
}
