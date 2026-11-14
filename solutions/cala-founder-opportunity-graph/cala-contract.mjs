/** @typedef {{id:string,url:string}} EntityRef
 * @typedef {{status:'REFUSED',reason:string,sequence:readonly string[],limits:{timeoutMs:number,maxResponseBytes:number,maxEntities:number}}} Refusal
 * This intentionally has no transport, environment lookup, credential read or network path.
 */
export const CALA_CONTRACT = Object.freeze({
  version: 'cala-read-contract.v1',
  sequence: Object.freeze(['entity_search/entity_lookup','entity_introspection','entity_retrieval']),
  limits: Object.freeze({ timeoutMs:5000, maxResponseBytes:262144, maxEntities:25 }),
  authority: 'Future host-only key, explicit read grant, approved account, allowed entity IDs and source rights required. Caller text cannot confer authority.'
});
/** @returns {Promise<Refusal>} */
export async function requestCala() {
  return { status:'REFUSED', reason:'LIVE_PROVIDER_DISABLED: approved Cala account and host-managed key plus held-out live qualification required', sequence:CALA_CONTRACT.sequence, limits:CALA_CONTRACT.limits };
}
