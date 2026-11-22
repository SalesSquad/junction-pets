import {createReview} from '../src/review.mjs';
import {fail} from '../src/json.mjs';
/** A host must call this after Studio captures a form; UI actions never establish review themselves. */
export async function applyStudioReview({dataset, claim, review}, input) {
  if (input.sourceGeneration !== dataset.manifest().generation || input.claimSha256 !== claim.claimSha256) fail('STALE_SOURCE', 'Studio form belongs to another source or answer.');
  const ids = typeof input.entityIds === 'string' ? input.entityIds.split(',').map(s => s.trim()).filter(Boolean) : [];
  return review.apply({id: input.operationId, expectedHead: input.expectedHead, kind: input.kind,
    reviewer: input.reviewer, note: input.note ?? '', value: input.kind === 'correct' ? input.value : null,
    refs: input.kind === 'correct' ? ids.map(id => dataset.ref(id)) : []});
}
export function studioData(dataset, claim, review) {
  return {filename: dataset.manifest().source.filename, sourceGeneration: dataset.manifest().generation,
    claimSha256: claim.claimSha256, expectedHead: review.snapshot().head, engineValue: claim.value ?? 'Abstained',
    evidenceLevel: claim.level, status: 'Host adapter required; this Studio widget alone does not record an evidence review.'};
}
