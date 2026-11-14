// Private synthetic demo boundaries. No identity, consent or external verification.
export const fail = message => { throw new TypeError(message); };
export const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
export function identifier(value) {
  if (typeof value !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$/.test(value)) fail('Use a bounded demo identifier.');
  return value;
}
export function list(value, limit = 100) {
  if (!Array.isArray(value) || value.length > limit || Array.from({ length: value.length }, (_, i) => !Object.hasOwn(value, i)).some(Boolean)) fail('Use a bounded, complete list.');
  return value;
}
export function utc(value) {
  if (typeof value !== 'string' || !/^2026-11-15T\d{2}:\d{2}:00Z$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().replace('.000', '') !== value) fail('Use a valid UTC time on fictional 15 November 2026.');
  return Date.parse(value);
}
export function availability(value) {
  for (const window of list(value, 24)) {
    if (!isRecord(window) || utc(window.start) >= utc(window.end)) fail('Availability needs an increasing UTC window.');
  }
  return value;
}
export function immutable(value) {
  const copy = structuredClone(value);
  const freeze = item => {
    if (item && typeof item === 'object') { Object.values(item).forEach(freeze); Object.freeze(item); }
    return item;
  };
  return freeze(copy);
}
