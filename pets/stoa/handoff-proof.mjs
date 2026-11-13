// Bounded invented declarations only. No BIM inspection, real acceptance or site authority.
const ID = /^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$/;
function requireValue(ok, message) { if (!ok) throw new TypeError(message); }
function fields(value, keys, name) {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)), `${name} fields must be exactly ${keys.join(', ')}`);
}
function id(value, name, nullable = false) {
  requireValue(nullable && value === null || typeof value === 'string' && value.length <= 64 && ID.test(value), `invalid fictional ${name}`);
}
function revision(value, name) {
  requireValue(value === null || Number.isSafeInteger(value) && !Object.is(value, -0) && value >= 0 && value <= 999999, `invalid ${name}`);
}

export function reviewHandoff(jsonText) {
  requireValue(typeof jsonText === 'string' && jsonText.length <= 12288 && new TextEncoder().encode(jsonText).length <= 12288,
    'expected primitive JSON text of at most 12288 UTF-8 bytes');
  let input;
  try { input = JSON.parse(jsonText); } catch { throw new TypeError('invalid JSON text'); }
  fields(input, ['schemaVersion', 'kind', 'document', 'handoff', 'acceptance'], 'input');
  requireValue(input.schemaVersion === 1 && input.kind === 'fictional-document-handoff', 'unsupported schemaVersion or kind');
  const {document, handoff, acceptance} = input;
  fields(document, ['documentId', 'currentRevision', 'owners'], 'document');
  id(document.documentId, 'documentId'); revision(document.currentRevision, 'currentRevision');
  requireValue(document.owners === null || Array.isArray(document.owners) && document.owners.length <= 8, 'owners must be null or 0..8 fictional IDs');
  for (const owner of document.owners ?? []) id(owner, 'owner');
  if (handoff !== null) {
    fields(handoff, ['documentId', 'revision', 'fromOwnerId', 'recipientId'], 'handoff');
    id(handoff.documentId, 'handoff documentId', true); revision(handoff.revision, 'handoff revision');
    id(handoff.fromOwnerId, 'fromOwnerId', true); id(handoff.recipientId, 'handoff recipientId', true);
  }
  if (acceptance !== null) {
    fields(acceptance, ['documentId', 'revision', 'recipientId', 'state'], 'acceptance');
    id(acceptance.documentId, 'acceptance documentId', true); revision(acceptance.revision, 'acceptance revision');
    id(acceptance.recipientId, 'acceptance recipientId', true);
    requireValue([null, 'accepted', 'pending', 'rejected', 'unknown'].includes(acceptance.state), 'invalid acceptance state');
  }

  const findings = [], flag = (code, field) => findings.push({code, field});
  if (document.currentRevision === null) flag('unknown-current-revision', 'document.currentRevision');
  const owners = new Set(document.owners ?? []);
  if (document.owners === null) flag('unknown-owners', 'document.owners');
  else if (document.owners.length === 0) flag('missing-owner', 'document.owners');
  else {
    if (owners.size !== document.owners.length) flag('duplicate-owner', 'document.owners');
    if (owners.size > 1) flag('conflicting-owners', 'document.owners');
  }
  if (handoff === null) flag('missing-handoff', 'handoff');
  else {
    if (handoff.documentId === null) flag('unknown-handoff-document', 'handoff.documentId');
    else if (handoff.documentId !== document.documentId) flag('handoff-document-mismatch', 'handoff.documentId');
    if (handoff.revision === null) flag('unknown-handoff-revision', 'handoff.revision');
    else if (document.currentRevision !== null && handoff.revision !== document.currentRevision) {
      flag(handoff.revision < document.currentRevision ? 'stale-revision' : 'unrecognized-revision', 'handoff.revision');
    }
    if (handoff.fromOwnerId === null) flag('unknown-sender', 'handoff.fromOwnerId');
    else if (document.owners?.length === 1 && !owners.has(handoff.fromOwnerId)) flag('sender-owner-mismatch', 'handoff.fromOwnerId');
    if (handoff.recipientId === null) flag('unknown-recipient', 'handoff.recipientId');
    else if (handoff.recipientId === handoff.fromOwnerId) flag('self-handoff', 'handoff.recipientId');
  }
  if (acceptance === null) flag('missing-acceptance', 'acceptance');
  else {
    if (acceptance.documentId === null) flag('unknown-acceptance-document', 'acceptance.documentId');
    else if (acceptance.documentId !== document.documentId) flag('acceptance-document-mismatch', 'acceptance.documentId');
    if (acceptance.revision === null) flag('unknown-acceptance-revision', 'acceptance.revision');
    else if (handoff?.revision != null && acceptance.revision !== handoff.revision) flag('acceptance-revision-mismatch', 'acceptance.revision');
    if (acceptance.recipientId === null) flag('unknown-acceptance-recipient', 'acceptance.recipientId');
    else if (handoff?.recipientId != null && acceptance.recipientId !== handoff.recipientId) flag('acceptance-recipient-mismatch', 'acceptance.recipientId');
    if (acceptance.state !== 'accepted') flag(
      acceptance.state === null || acceptance.state === 'unknown' ? 'unknown-acceptance' : `${acceptance.state}-acceptance`, 'acceptance.state');
  }
  return {
    schemaVersion: 1, kind: 'fictional-handoff-proof', status: findings.length ? 'needs-review' : 'consistent-declarations', findings,
    summary: {documentId: document.documentId, currentRevision: document.currentRevision, submittedRevision: handoff?.revision ?? null,
      ownerDeclarations: document.owners?.length ?? null, acceptanceDeclaration: acceptance === null ? 'missing' : acceptance.state ?? 'unknown'},
    boundary: {synthetic: true, documentInspected: false, ownershipVerified: false, acceptanceVerified: false, siteActionAuthorized: false},
  };
}
