// Synthetic, supplied-claim consistency only. No I/O, signatures or advisory feed.
export const SBOM_LIMITS = Object.freeze({textBytes: 65536, components: 64, dependencies: 256, advisories: 64, versions: 32});
const IDENTITY_FIELDS = ['ecosystem', 'name', 'version', 'sha256'];
const VERSION = /^(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){0,2}(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?(\+[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$/;
const TOKEN = /^[A-Za-z0-9@][A-Za-z0-9._/@+-]*$/;
const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const known = value => value !== undefined && value !== null;
const invalid = where => { throw new TypeError(`Invalid synthetic SBOM: ${where}`); };

function record(value, keys, required, where) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid(where);
  if (Object.keys(value).some(key => !keys.includes(key)) || required.some(key => !Object.hasOwn(value, key))) invalid(where);
}
function token(value, where, max = 128, pattern = TOKEN) {
  if (typeof value !== 'string' || value.length > max || !pattern.test(value)) invalid(where);
}
function list(value, max, where, min = 0) {
  if (!Array.isArray(value) || value.length < min || value.length > max) invalid(where);
}
function identity(value, where, extra = []) {
  record(value, [...IDENTITY_FIELDS, ...extra], ['ecosystem', 'name'], where);
  token(value.ecosystem, `${where}.ecosystem`, 32, /^[a-z][a-z0-9-]*$/);
  token(value.name, `${where}.name`);
  if (known(value.version)) token(value.version, `${where}.version`, 64, VERSION);
  if (known(value.sha256)) token(value.sha256, `${where}.sha256`, 64, /^[0-9a-f]{64}$/);
}
function requireClaim(value, key, label, issues) {
  if (!Object.hasOwn(value, key)) issues.push(`${label}-missing`);
  else if (value[key] === null) issues.push(`${label}-null`);
}
function compareSubject(component, subject, label, issues) {
  for (const field of ['version', 'sha256']) requireClaim(subject, field, `${label}-${field}`, issues);
  for (const field of IDENTITY_FIELDS) {
    if (known(component[field]) && known(subject[field]) && component[field] !== subject[field]) issues.push(`${label}-${field}-mismatch`);
  }
}

export function reviewSyntheticSbom(text) {
  if (typeof text !== 'string' || text.length > SBOM_LIMITS.textBytes || Buffer.byteLength(text, 'utf8') > SBOM_LIMITS.textBytes) invalid('text bytes');
  let input;
  try { input = JSON.parse(text); } catch { invalid('JSON text'); }
  const rootKeys = ['schemaVersion', 'synthetic', 'components', 'dependencies', 'advisories'];
  record(input, rootKeys, rootKeys, 'root');
  if (input.schemaVersion !== 1 || input.synthetic !== true) invalid('schemaVersion/synthetic');
  list(input.components, SBOM_LIMITS.components, 'components', 1);
  list(input.dependencies, SBOM_LIMITS.dependencies, 'dependencies');
  list(input.advisories, SBOM_LIMITS.advisories, 'advisories');

  const refs = new Set();
  const identityDigests = new Map();
  const identityKey = component => JSON.stringify([component.ecosystem, component.name, component.version]);
  for (const component of input.components) {
    identity(component, 'component', ['ref', 'artifact', 'provenance']);
    token(component.ref, 'component.ref', 64, /^[a-z][a-z0-9-]*$/);
    if (refs.has(component.ref)) invalid('duplicate component ref');
    refs.add(component.ref);
    if (known(component.artifact)) identity(component.artifact, 'artifact');
    if (known(component.provenance)) {
      const provenance = component.provenance;
      record(provenance, ['subject', 'sourceCommit', 'builder', 'buildId'], ['subject'], 'provenance');
      identity(provenance.subject, 'provenance.subject');
      if (known(provenance.sourceCommit)) token(provenance.sourceCommit, 'provenance.sourceCommit', 40, /^[0-9a-f]{40}$/);
      for (const field of ['builder', 'buildId']) if (known(provenance[field])) token(provenance[field], `provenance.${field}`);
    }
    if (known(component.version) && known(component.sha256)) {
      const key = identityKey(component);
      if (!identityDigests.has(key)) identityDigests.set(key, new Set());
      identityDigests.get(key).add(component.sha256);
    }
  }

  const edges = new Set();
  for (const dependency of input.dependencies) {
    record(dependency, ['from', 'to'], ['from', 'to'], 'dependency');
    if (!refs.has(dependency.from) || !refs.has(dependency.to) || dependency.from === dependency.to) invalid('dependency endpoints');
    const key = JSON.stringify([dependency.from, dependency.to]);
    if (edges.has(key)) invalid('duplicate dependency');
    edges.add(key);
  }
  const advisoryIds = new Set();
  for (const advisory of input.advisories) {
    const keys = ['id', 'ecosystem', 'name', 'versions'];
    record(advisory, keys, keys, 'advisory');
    token(advisory.id, 'advisory.id', 64);
    token(advisory.ecosystem, 'advisory.ecosystem', 32, /^[a-z][a-z0-9-]*$/);
    token(advisory.name, 'advisory.name');
    if (advisoryIds.has(advisory.id)) invalid('duplicate advisory id');
    advisoryIds.add(advisory.id);
    list(advisory.versions, SBOM_LIMITS.versions, 'advisory.versions', 1);
    for (const version of advisory.versions) token(version, 'advisory.version', 64, VERSION);
    if (new Set(advisory.versions).size !== advisory.versions.length) invalid('duplicate advisory version');
  }

  const components = [...input.components].sort((a, b) => compare(a.ref, b.ref));
  const componentChecks = components.map(component => {
    const issues = [];
    for (const field of ['version', 'sha256', 'artifact', 'provenance']) requireClaim(component, field, `component-${field}`, issues);
    if (known(component.artifact)) compareSubject(component, component.artifact, 'artifact', issues);
    if (known(component.provenance)) {
      compareSubject(component, component.provenance.subject, 'provenance', issues);
      for (const field of ['sourceCommit', 'builder', 'buildId']) requireClaim(component.provenance, field, `provenance-${field}`, issues);
    }
    if (known(component.version) && identityDigests.get(identityKey(component))?.size > 1) issues.push('identity-digest-conflict');
    const mismatch = issues.some(issue => issue.endsWith('-mismatch') || issue.endsWith('-conflict'));
    return {
      ref: component.ref,
      identity: {ecosystem: component.ecosystem, name: component.name, version: component.version ?? null, sha256: component.sha256 ?? null},
      consistency: mismatch ? 'mismatch' : issues.length ? 'incomplete' : 'consistent',
      issues, verified: false,
    };
  });
  const advisoryChecks = [...input.advisories].sort((a, b) => compare(a.id, b.id)).map(advisory => {
    const candidates = components.filter(component => component.ecosystem === advisory.ecosystem && component.name === advisory.name);
    return {
      id: advisory.id,
      matchedRefs: candidates.filter(component => known(component.version) && advisory.versions.includes(component.version)).map(component => component.ref),
      unknownVersionRefs: candidates.filter(component => !known(component.version)).map(component => component.ref),
      matchBasis: 'exact-declared-ecosystem-name-version', confirmedExploit: false, exploitability: 'not-assessed',
    };
  });
  return {
    kind: 'synthetic-sbom-review', verified: false, provenanceAuthenticated: false, dependencyScope: 'declared-only',
    componentChecks,
    declaredDependencies: input.dependencies.map(({from, to}) => ({from, to})).sort((a, b) => compare(a.from, b.from) || compare(a.to, b.to)),
    advisoryChecks,
  };
}
