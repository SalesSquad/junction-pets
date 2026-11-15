// RoundLens portable, offline-only recovery. Historical approvals are revoked.
import { makeArtifact, validateGoal, safeJSON } from '../core.mjs';
import { PRODUCT_SOURCE_DIGEST } from '../source-meta.mjs';

export const MAX_ARCHIVE_BYTES = 256 * 1024;
// First published fixture export predates recovery UI. This is the only
// historical digest accepted, with full evidence reconstruction below.
export const LEGACY_FIXTURE_DIGESTS = Object.freeze([
  '28d12b5e69bc709fc55b6a6b30cb91bde509f70b4bfa71008518fb56cb6517c7'
]);
const fail = code => { throw new Error(code); };
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value) &&
  Object.getPrototypeOf(value) === Object.prototype;

/**
 * Recover only note/ID data from an original RoundLens FICTIONAL_FIXTURE
 * export. Entire evidence object must match freshly reconstructed fixture.
 * No file-provided citation, source, score, or approval becomes authoritative.
 */
export function recoverArchive(raw, fixture) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).byteLength > MAX_ARCHIVE_BYTES)
    fail('ARCHIVE_TOO_LARGE_OR_INVALID');
  let archived;
  try { archived = JSON.parse(raw); } catch { fail('ARCHIVE_NOT_JSON'); }
  if (raw !== safeJSON(archived)) fail('ARCHIVE_NONCANONICAL_JSON');
  if (!isRecord(archived) || archived.schema !== 'roundlens.shortlist.v1' ||
      archived.mode !== 'FICTIONAL_FIXTURE' || !Array.isArray(archived.shortlist))
    fail('ARCHIVE_FORMAT_NOT_SUPPORTED');
  if (![PRODUCT_SOURCE_DIGEST, ...LEGACY_FIXTURE_DIGESTS].includes(archived.productSourceDigest))
    fail('ARCHIVE_SOURCE_NOT_SUPPORTED');
  let goal;
  try { goal = validateGoal(archived.goal, fixture.asOf); }
  catch { fail('ARCHIVE_GOAL_INVALID'); }
  if (archived.shortlist.length < 1 || archived.shortlist.length > 20)
    fail('ARCHIVE_SHORTLIST_INVALID');
  const reviews = [];
  const seen = new Set();
  for (const entry of archived.shortlist) {
    if (!isRecord(entry) || !isRecord(entry.entity) ||
        typeof entry.entity.id !== 'string' || !isRecord(entry.humanReview) ||
        entry.humanReview.state !== 'APPROVED_BY_LOCAL_USER' ||
        typeof entry.humanReview.note !== 'string' ||
        entry.humanReview.note.length > 2000 || seen.has(entry.entity.id))
      fail('ARCHIVE_REVIEW_INVALID');
    seen.add(entry.entity.id);
    reviews.push({ id: entry.entity.id, note: entry.humanReview.note, approved: false });
  }

  // Rebuild exported graph from trusted local source. Historical UI digest
  // differs but every investor, claim, date, and citation must still match.
  let reconstructed;
  try {
    reconstructed = makeArtifact(fixture, goal, reviews.map(r => ({ ...r, approved: true })));
  } catch { fail('ARCHIVE_EVIDENCE_NO_LONGER_SUPPORTED'); }
  reconstructed.productSourceDigest = archived.productSourceDigest;
  if (JSON.stringify(archived) !== JSON.stringify(reconstructed))
    fail('ARCHIVE_EVIDENCE_CHANGED_OR_TAMPERED');

  return { goal, reviews, approvalsRevoked: true, mode: 'FICTIONAL_FIXTURE' };
}
