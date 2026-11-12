import {AIVEN_DOCS_COMMIT, AIVEN_DOCS_LICENSE, AIVEN_DOCS_REPOSITORY} from './adapter.mjs';

// Smoke-only acceptance conditions. These validate adapter evidence, NOT a
// cryptographic host attestation or a model/provider invocation.
export function qualifiesLivePinnedResult(result, expected) {
  if (!expected || result?.ok !== true || result?.code !== 'VERIFIED_SOURCE_BYTES' ||
      result?.evidenceKind !== 'pinned-public-docs' ||
      result?.pinnedOfficialDocsVerified !== true ||
      result?.hostGrantVerified !== false ||
      result?.providerInvocationVerified !== false ||
      !Array.isArray(result?.documents) || result.documents.length !== 1 ||
      !Array.isArray(result?.failures) || result.failures.length !== 0) return false;
  const doc = result.documents[0];
  return doc?.id === expected.id &&
    doc?.citation?.url === expected.citationUrl &&
    doc?.citation?.pinnedRawSourceBytesMatched === true &&
    doc?.provenance?.kind === 'pinned-public-docs' &&
    doc?.provenance?.repository === AIVEN_DOCS_REPOSITORY &&
    doc?.provenance?.sourceCommit === AIVEN_DOCS_COMMIT &&
    doc?.provenance?.license === AIVEN_DOCS_LICENSE &&
    doc?.provenance?.contentSha256 === expected.contentSha256 &&
    doc?.provenance?.pinnedRawBytesSha256Matched === true &&
    doc?.provenance?.syntheticFixtureSha256Matched === false &&
    Number.isInteger(doc?.provenance?.contentBytes) &&
    doc.provenance.contentBytes > 0;
}

export function qualifiesNoDocuments(result, expectedCode = 'NO_RELEVANT_DOCUMENTS') {
  return result?.code === expectedCode &&
    (expectedCode !== 'NO_RELEVANT_DOCUMENTS' || result.ok === true) &&
    Array.isArray(result?.documents) && result.documents.length === 0 &&
    Array.isArray(result?.failures) && result.failures.length === 0 &&
    result?.pinnedOfficialDocsVerified === false;
}

export function qualifiesOfflineShortlist(ranked, expectedId = null) {
  return ranked?.ok === true &&
    ranked?.code === (expectedId === null ? 'NO_RELEVANT_DOCUMENTS' : 'MATCHES_UNVERIFIED') &&
    Array.isArray(ranked?.matches) &&
    (expectedId === null ? ranked.matches.length === 0
      : ranked.matches.length === 1 && ranked.matches[0]?.id === expectedId);
}
