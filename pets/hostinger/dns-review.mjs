/** Bounded, fictional supplied-data comparison. Never resolves DNS or changes an account. */
function fields(value, allowed, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).length !== allowed.length
    || Object.keys(value).some(key => !allowed.includes(key))) throw new TypeError(`${label} fields`);
}

function name(value) {
  if (typeof value !== 'string' || value.length > 253 || !value.endsWith('.example')
    || /[^a-z0-9.-]/.test(value)
    || value.split('.').some(label => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) {
    throw new TypeError('Expected a canonical fictional name under .example');
  }
  return value;
}

function address(value) {
  if (typeof value !== 'string') throw new TypeError('Expected documentation IPv4');
  const parts = value.split('.');
  if (parts.length !== 4 || !['192.0.2', '198.51.100', '203.0.113'].includes(parts.slice(0, 3).join('.'))
    || !Number.isInteger(Number(parts[3])) || Number(parts[3]) < 0 || Number(parts[3]) > 255
    || String(Number(parts[3])) !== parts[3]) throw new TypeError('Expected documentation IPv4');
  return value;
}

function inspect(records, view, owner, findings) {
  if (records === null) return {state: 'not-supplied', recordCount: null, identities: null, duplicateRecordCount: null, knownTtlSeconds: [], unknownTtlCount: null};
  if (!Array.isArray(records) || records.length > 16) throw new TypeError('A view must be null or at most 16 records');
  for (const record of records) {
    fields(record, ['type', 'value', 'ttlSeconds'], 'record');
    if (!['A', 'CNAME'].includes(record.type)) throw new TypeError('Unsupported record type');
    if (record.type === 'A') address(record.value); else name(record.value);
    if (record.ttlSeconds !== null && (!Number.isInteger(record.ttlSeconds) || record.ttlSeconds < 0
      || record.ttlSeconds > 2147483647)) throw new TypeError('Invalid ttlSeconds');
  }
  const aliases = [...new Set(records.filter(r => r.type === 'CNAME').map(r => r.value))];
  const issue = code => findings.push({view, code, basis: 'supplied-records-only'});
  if (aliases.length && records.some(r => r.type === 'A')) issue('cname-with-address');
  if (aliases.length > 1) issue('multiple-cname-targets');
  if (aliases.includes(owner)) issue('self-cname');
  for (const type of ['A', 'CNAME']) {
    if (new Set(records.filter(r => r.type === type && r.ttlSeconds !== null).map(r => r.ttlSeconds)).size > 1) issue('mixed-ttl-within-rrset');
  }
  const identities = [...new Set(records.map(r => `${r.type} ${r.value}`))].sort();
  return {
    state: records.length ? 'supplied' : 'supplied-empty', recordCount: records.length, identities,
    duplicateRecordCount: records.length - identities.length,
    knownTtlSeconds: [...new Set(records.filter(r => r.ttlSeconds !== null).map(r => r.ttlSeconds))].sort((a, b) => a - b),
    unknownTtlCount: records.filter(r => r.ttlSeconds === null).length,
  };
}

export function reviewDnsSnapshot(text) {
  if (typeof text !== 'string') throw new TypeError('Expected JSON text');
  if (Buffer.byteLength(text, 'utf8') > 32768) throw new TypeError('JSON text exceeds 32768 bytes');
  let data;
  try { data = JSON.parse(text); } catch { throw new TypeError('Invalid JSON text'); }
  fields(data, ['schemaVersion', 'scenario', 'owner', 'authoritative', 'recursive'], 'snapshot');
  if (data.schemaVersion !== 1) throw new TypeError('Unsupported schemaVersion');
  if (data.scenario !== 'fictional') throw new TypeError('Only a fictional scenario is supported');
  const owner = name(data.owner), findings = [];
  const observations = {
    authoritative: inspect(data.authoritative, 'authoritative', owner, findings),
    recursive: inspect(data.recursive, 'recursive', owner, findings),
  };
  const a = observations.authoritative.identities, b = observations.recursive.identities;
  let comparison = 'unknown';
  if (findings.length) comparison = 'input-conflict';
  else if (a !== null && b !== null && (a.length || b.length)) comparison = JSON.stringify(a) === JSON.stringify(b) ? 'matching-supplied-records' : 'different-supplied-records';
  const hypotheses = [];
  if (comparison === 'input-conflict') hypotheses.push({id: 'input-or-configuration-conflict', status: 'unconfirmed'});
  if (comparison === 'different-supplied-records') hypotheses.push({id: 'view-or-time-difference', status: 'unconfirmed'});
  return {
    schemaVersion: 1, kind: 'fictional-dns-review', owner, observations, findings, comparison, hypotheses,
    diagnosis: 'not-established', liveDnsVerified: false, networkAccessed: false, accountAccessed: false,
    nextChecks: [
      {action: 'Compare separately authorized read-only captures with the same owner, record type, resolver and capture time recorded.', effect: 'read-only', executed: false},
      {action: 'If a website symptom persists, inspect redacted HTTP/HTTPS and browser observations separately before proposing a change.', effect: 'read-only', executed: false},
    ],
    limitations: [
      'Labels authoritative and recursive are supplied attribution, not verified server identity or authority.',
      'A difference does not prove cache staleness, propagation delay, compromise or the cause of a website symptom.',
      'An empty array is an empty supplied extract, not proof of NXDOMAIN or an absent record.',
      'Matching values do not establish complete DNS, DNSSEC, HTTPS, hosting or launch health; capture time and completeness are unknown.',
    ],
  };
}
