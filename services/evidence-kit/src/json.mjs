const utf8 = new TextEncoder();
export function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}
export function exact(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      JSON.stringify(Object.keys(value).sort()) !== JSON.stringify([...keys].sort())) {
    fail('INVALID_SCHEMA', `${label}: unexpected or missing fields.`);
  }
}
export function text(value, label, max = 200) {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) {
    fail('INVALID_TEXT', `${label}: expected bounded Unicode text.`);
  }
  return value;
}
/** Strict portable JSON. Never invoke getters, coerce numbers, or silently drop undefined. */
export function canonical(value) {
  let nodes = 0;
  const seen = new Set();
  function visit(v, depth) {
    if (++nodes > 200000 || depth > 40) fail('RESOURCE_EXHAUSTED', 'JSON work budget exceeded.');
    if (v === null) return 'null';
    if (typeof v === 'boolean') return String(v);
    if (typeof v === 'number') {
      if (!Number.isFinite(v)) fail('INVALID_JSON', 'Non-finite JSON number.');
      return JSON.stringify(v);
    }
    if (typeof v === 'string') {
      if (v.length > 8 * 1024 * 1024 || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v)) fail('INVALID_JSON', 'Invalid Unicode string.');
      return JSON.stringify(v);
    }
    if (!v || typeof v !== 'object' || seen.has(v)) fail('INVALID_JSON', 'Unsupported or cyclic JSON value.');
    const proto = Object.getPrototypeOf(v);
    if (Array.isArray(v) ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) {
      fail('INVALID_JSON', 'Use ordinary JSON objects and arrays.');
    }
    const descriptors = Object.getOwnPropertyDescriptors(v);
    if (Reflect.ownKeys(v).some(k => typeof k !== 'string')) fail('INVALID_JSON', 'Symbols are not JSON.');
    for (const [key, desc] of Object.entries(descriptors)) {
      if (!('value' in desc) || (key !== 'length' && !desc.enumerable)) fail('INVALID_JSON', 'Accessors and hidden properties are not JSON.');
    }
    seen.add(v);
    let result;
    if (Array.isArray(v)) {
      if (Object.keys(v).length !== v.length || Object.keys(v).some((k, i) => k !== String(i))) fail('INVALID_JSON', 'Sparse or extended arrays are not accepted.');
      result = '[' + v.map(x => visit(x, depth + 1)).join(',') + ']';
    } else {
      result = '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + visit(descriptors[k].value, depth + 1)).join(',') + '}';
    }
    seen.delete(v);
    return result;
  }
  const encoded = visit(value, 0);
  if (utf8.encode(encoded).length > 8 * 1024 * 1024) fail('RESOURCE_EXHAUSTED', 'JSON exceeds 8 MiB.');
  return encoded;
}
export async function sha256(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength > 16 * 1024 * 1024) fail('INVALID_BYTES', 'Use at most 16 MiB of bytes.');
  const owned = new Uint8Array(bytes);
  const hash = await globalThis.crypto.subtle.digest('SHA-256', owned);
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
}
export const hashJson = value => sha256(utf8.encode(canonical(value)));
export const jsonCopy = value => JSON.parse(canonical(value));
export function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
export const isHash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const encode = value => utf8.encode(value);
export const decode = bytes => new TextDecoder('utf-8', {fatal: true}).decode(bytes);
