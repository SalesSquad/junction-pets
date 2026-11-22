import {canonical, exact, fail, freeze, hashJson, jsonCopy, sha256} from './json.mjs';
import {restoreDataset} from './dataset.mjs';
import {validateClaim} from './claim.mjs';
import {restoreReview} from './review.mjs';
export async function exportPacket(dataset, claim, review, {historical = []} = {}) {
  const validated = await validateClaim(dataset, claim);
  const ledger = review.snapshot ? review.snapshot() : review;
  await restoreReview(dataset, validated, ledger);
  if (!Array.isArray(historical) || historical.length > 10) fail('RESOURCE_EXHAUSTED', 'At most 10 historical records.');
  const payload = jsonCopy({schema: 'evidence-kit.packet/v2', dataset: dataset.snapshot(), claim: validated,
    review: ledger, historical, authenticity: 'not-authenticated'});
  return freeze({payload, integrity: {algorithm: 'sha256', sha256: await hashJson(payload), signed: false}});
}
export async function openPacket(input, {expectedPacketSha256 = null, sourceBytes = null} = {}) {
  const packet = jsonCopy(input);
  exact(packet, ['payload', 'integrity'], 'packet');
  exact(packet.integrity, ['algorithm', 'sha256', 'signed'], 'integrity');
  if (packet.payload.schema !== 'evidence-kit.packet/v2') fail('UNSUPPORTED_VERSION', 'Unknown packet version; use an explicit migration adapter.');
  exact(packet.payload, ['schema', 'dataset', 'claim', 'review', 'historical', 'authenticity'], 'packet payload');
  if (packet.integrity.algorithm !== 'sha256' || packet.integrity.signed !== false ||
      packet.integrity.sha256 !== await hashJson(packet.payload)) fail('INTEGRITY_MISMATCH', 'Packet digest mismatch.');
  if (expectedPacketSha256 !== null && expectedPacketSha256 !== packet.integrity.sha256) fail('TRUSTED_PIN_MISMATCH', 'Packet differs from the separately supplied pin.');
  if (!Array.isArray(packet.payload.historical) || packet.payload.historical.length > 10 || packet.payload.authenticity !== 'not-authenticated') fail('INVALID_HISTORY', 'Invalid historical records or authenticity claim.');
  const dataset = await restoreDataset(packet.payload.dataset);
  if (sourceBytes !== null && await sha256(sourceBytes) !== dataset.manifest().source.sha256) fail('SOURCE_MISMATCH', 'Original source bytes differ.');
  const claim = await validateClaim(dataset, packet.payload.claim);
  const review = await restoreReview(dataset, claim, packet.payload.review);
  return {dataset, claim, review, historical: freeze(packet.payload.historical),
    verification: freeze({integrity: 'matched', trustedPinMatched: expectedPacketSha256 !== null,
      sourceBytesMatched: sourceBytes !== null, extractionReplayed: false, authenticity: 'not-authenticated'})};
}
export async function replayPacket(input, {bytes, adapter, run}) {
  if (!(bytes instanceof Uint8Array)) fail('SOURCE_REQUIRED', 'Replay requires the original source bytes.');
  const original = new Uint8Array(bytes);
  const opened = await openPacket(input, {sourceBytes: original});
  const source = opened.dataset.manifest().source;
  if (adapter.id !== source.adapter.id) fail('WRONG_ADAPTER', 'Replay adapter differs from the source adapter.');
  const current = await adapter.ingest(original, {filename: source.filename, frame: source.frame, rights: source.rights, expectedSha256: source.sha256});
  if (current.manifest().source.sha256 !== source.sha256) fail('SOURCE_MISMATCH', 'Replay adapter returned a different source.');
  const claim = await validateClaim(current, await run(current));
  const sameGeneration = current.manifest().generation === opened.dataset.manifest().generation;
  const sameClaim = claim.claimSha256 === opened.claim.claimSha256;
  return {dataset: current, claim, historical: opened,
    review: sameGeneration && sameClaim ? await restoreReview(current, claim, opened.review.snapshot()) : null,
    status: sameGeneration && sameClaim ? 'replayed' : 'revalidation_required',
    verification: {...opened.verification, extractionReplayed: true, currentClaimMatches: sameClaim}};
}
/** Preserve an actual Stoa v1 packet as historical evidence; never promote its old review. */
export async function preserveStoaV1(input) {
  const packet = jsonCopy(input);
  if (packet?.payload?.schema !== 'stoa.evidence-packet/v1' || packet.integrity?.algorithm !== 'sha256' || packet.integrity.signed !== false ||
      await hashJson(packet.payload) !== packet.integrity.sha256) fail('INVALID_LEGACY_PACKET', 'Stoa v1 packet integrity mismatch.');
  return freeze({schema: 'evidence-kit.historical/v1', originalSchema: packet.payload.schema,
    originalPacketSha256: packet.integrity.sha256, sourceSha256: packet.payload.source.sha256,
    original: packet, status: 'historical_requires_revalidation', independentVerification: false});
}
