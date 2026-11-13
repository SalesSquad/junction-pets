/** Offline synthetic design example. No host policy, device API or real grant. */
const SCOPE = 'synthetic-reminder-preview';
const MAX_AGE = 60_000;
const record = x => x !== null && typeof x === 'object' && !Array.isArray(x) && Object.getPrototypeOf(x) === Object.prototype;
const exact = (x, keys) => record(x) && Object.keys(x).length === keys.length && keys.every(k => Object.hasOwn(x,k));
const time = x => Number.isSafeInteger(x) && x >= 0;
const member = (x, values) => values.includes(x);

/** Replay a complete caller-owned synthetic history. It is not authenticated or durable.
 * Dropping history drops replay protection: a real host must persist its own ledger.
 * Millisecond integers are synthetic clock values, not platform timestamps.
 */
export function evaluateWearableHistory(input) {
  const fallback = {mode:'text',cameraRequired:false,
    text:'Type a reminder manually. No camera, microphone or bystander data is needed.',
    controls:['Edit reminder','Cancel','Clear reminder'],announcement:'Preview only; no real action was performed.'};
  const result = (state, permission='unknown', simulationAllowed=false, reason=state) =>
    ({state,permission,simulationAllowed,realActionAuthorized:false,reason,fallback});
  const invalid = () => result('invalid');
  if (!exact(input,['scope','now','events']) || input.scope !== SCOPE || !time(input.now) || !Array.isArray(input.events) || input.events.length > 128) return invalid();
  let state='unavailable', permission='unknown', available=false, bystanders='unknown';
  let grant=null, previous=0;
  const seen=new Set();
  for (const event of input.events) {
    if (!record(event) || event.scope !== SCOPE || !time(event.at) || event.at < previous || event.at > input.now || input.now-event.at > MAX_AGE) return invalid();
    previous=event.at;
    if (grant && event.at >= grant.expiresAt) {grant=null;state='expired';}
    if (event.decision === 'snapshot') {
      if (!exact(event,['decision','at','scope','available','permission','bystanders']) || typeof event.available !== 'boolean' || !member(event.permission,['unknown','denied','granted']) || !member(event.bystanders,['unknown','clear','present'])) return invalid();
      available=event.available; permission=event.permission; bystanders=event.bystanders;
      if (!available || permission !== 'granted' || bystanders !== 'clear') grant=null;
      // A snapshot is observation only; even 'granted' cannot replace consent.
      if (!member(state,['canceled','revoked','expired'])) state=grant?'consented':available?'unknown':'unavailable';
    } else if (event.decision === 'consent') {
      if (!exact(event,['decision','at','scope','id','expiresAt']) || typeof event.id !== 'string' || !/^[a-z0-9-]{1,64}$/.test(event.id) || seen.has(event.id) || !time(event.expiresAt) || event.expiresAt <= event.at || event.expiresAt-event.at > MAX_AGE) return invalid();
      seen.add(event.id);
      if (!available || permission === 'denied' || bystanders !== 'clear') return invalid();
      // Explicit consent covers this fictional preview only, never OS permission.
      grant={expiresAt:event.expiresAt}; state='consented';
    } else if (member(event.decision,['cancel','revoke'])) {
      if (!exact(event,['decision','at','scope'])) return invalid();
      grant=null;state=event.decision==='cancel'?'canceled':'revoked';
    } else return invalid();
  }
  if (grant && input.now >= grant.expiresAt) {grant=null;state='expired';}
  return result(state,permission,grant !== null);
}
