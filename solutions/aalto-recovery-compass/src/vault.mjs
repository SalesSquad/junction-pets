/** Minimal local capsule. No drafts, keys, passphrases or arbitrary session serialization. */
import { newSession, checkIn, chooseAction } from './compass.mjs';
export const TTL = 7 * 24 * 60 * 60 * 1000;
export const ITERATIONS = 210_000;
const VERSION = 'aalto-m343-capsule-v1';
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
const bytes = value => Uint8Array.from(value.match(/../g), x => parseInt(x, 16));
const exact = (x, keys) => x !== null && typeof x === 'object' && !Array.isArray(x) && Object.keys(x).sort().join(',') === [...keys].sort().join(',');
const fail = message => { throw new Error(message); };
function contextOK(context) {
  if (typeof context !== 'string' || context.length > 200) fail('Invalid capsule context.');
  const u = new URL(context);
  if (u.origin !== context || !['http:', 'https:'].includes(u.protocol)) fail('Invalid capsule context.');
}
function support(crypto, context) {
  contextOK(context);
  if (!crypto?.subtle || typeof crypto.getRandomValues !== 'function') fail('Local save unavailable: WebCrypto is required.');
}
function passOK(passphrase) {
  if (typeof passphrase !== 'string' || passphrase.length < 12 || encoder.encode(passphrase).length > 256) fail('Use a user-kept passphrase of 12–256 UTF-8 bytes (at least 12 characters).');
}
function validEnvelope(e, context, now) {
  return exact(e, ['version','context','iterations','createdAt','expiresAt','salt','iv','ciphertext']) &&
    e.version === VERSION && e.context === context && e.iterations === ITERATIONS &&
    Number.isSafeInteger(now) && Number.isSafeInteger(e.createdAt) && Number.isSafeInteger(e.expiresAt) &&
    e.createdAt <= now && e.createdAt >= 0 && e.expiresAt === e.createdAt + TTL && e.expiresAt > now &&
    typeof e.salt === 'string' && /^[a-f0-9]{32}$/.test(e.salt) &&
    typeof e.iv === 'string' && /^[a-f0-9]{24}$/.test(e.iv) &&
    typeof e.ciphertext === 'string' && /^[a-f0-9]{32,1024}$/.test(e.ciphertext) && e.ciphertext.length % 2 === 0;
}
const aad = context => encoder.encode(`${VERSION}\n${context}\nselected-action-only`);
async function key(crypto, passphrase, salt, usage) {
  passOK(passphrase);
  const material = await crypto.subtle.importKey('raw', encoder.encode(passphrase), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name:'PBKDF2', salt, iterations:ITERATIONS, hash:'SHA-256' }, material,
    { name:'AES-GCM', length:256 }, false, [usage]);
}
function verifiedSession(payload) {
  const keys = Object.hasOwn(payload ?? {}, 'energy') ? ['action','energy','createdAt','expiresAt'] : ['action','createdAt','expiresAt'];
  if (!exact(payload, keys)) fail('Invalid capsule contents.');
  const checked = checkIn(newSession(), { wish:payload.action, energy:payload.energy ?? 'prefer-not-to-say' });
  if (!checked.ok || (Object.hasOwn(payload, 'energy') && typeof payload.energy !== 'string')) fail('Invalid capsule choice.');
  const chosen = chooseAction(checked.session, { confirmed:true });
  if (!chosen.ok) fail('Invalid capsule choice.');
  return chosen.session;
}
export async function pack({ action, energy, passphrase, context, now = Date.now(), crypto = globalThis.crypto }) {
  support(crypto, context);
  if (!Number.isSafeInteger(now) || now < 0 || !Number.isSafeInteger(now + TTL)) fail('Invalid capsule time.');
  const payload = { action, createdAt:now, expiresAt:now + TTL, ...(energy === undefined ? {} : { energy }) };
  verifiedSession(payload);
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const derived = await key(crypto, passphrase, salt, 'encrypt');
  const ciphertext = await crypto.subtle.encrypt({ name:'AES-GCM', iv, additionalData:aad(context), tagLength:128 }, derived, encoder.encode(JSON.stringify(payload)));
  return { version:VERSION, context, iterations:ITERATIONS, createdAt:now, expiresAt:now+TTL, salt:hex(salt), iv:hex(iv), ciphertext:hex(new Uint8Array(ciphertext)) };
}
export async function unpack(envelope, { passphrase, context, now = Date.now(), crypto = globalThis.crypto }) {
  support(crypto, context);
  if (!validEnvelope(envelope, context, now)) fail('Expired or malformed capsule.');
  const derived = await key(crypto, passphrase, bytes(envelope.salt), 'decrypt');
  let payload;
  try {
    const plain = await crypto.subtle.decrypt({ name:'AES-GCM', iv:bytes(envelope.iv), additionalData:aad(context), tagLength:128 }, derived, bytes(envelope.ciphertext));
    payload = JSON.parse(decoder.decode(plain));
  } catch { fail('Could not unlock: wrong passphrase or damaged capsule.'); }
  if (payload?.createdAt !== envelope.createdAt || payload?.expiresAt !== envelope.expiresAt) fail('Capsule metadata mismatch.');
  return { session:verifiedSession(payload), includesEnergy:Object.hasOwn(payload, 'energy'), expiresAt:payload.expiresAt };
}
// All instances using this database must request this same origin-scoped name.
const LOCK_NAME = `${VERSION}:storage`;
function browserLock() {
  try {
    const locks = globalThis.navigator?.locks;
    return typeof locks?.request === 'function' ? locks.request.bind(locks) : null;
  } catch { return null; }
}
/** requestLock follows navigator.locks.request(name, options, callback), injected only by tests.
 * Request immediately at operation initiation, without a per-instance queue or nested locks.
 * Backends must resolve writes/deletes only after their transaction commits.
 */
export function createVault({ backend, context, crypto = globalThis.crypto, now = Date.now, requestLock = browserLock() }) {
  const exclusive = async operation => {
    if (typeof requestLock !== 'function') fail('Local capsule unavailable: Web Locks are required for cross-tab coordination.');
    return requestLock(LOCK_NAME, { mode:'exclusive' }, operation);
  };
  const read = async () => {
    support(crypto, context);
    const record = await backend.read();
    if (record === undefined || record === null) return null;
    if (!validEnvelope(record, context, now())) { await backend.delete(); return null; }
    return record;
  };
  return {
    inspect: () => exclusive(async () => { const e = await read(); return e ? { expiresAt:e.expiresAt } : null; }),
    save: input => exclusive(async () => {
      const record = await pack({ action:input.action, energy:input.energy, passphrase:input.passphrase, context, crypto, now:now() });
      // Do not retain a record that expired while encryption was pending.
      if (!validEnvelope(record, context, now())) fail('Capsule expired before saving.');
      await backend.write(record);
      return { expiresAt:record.expiresAt };
    }),
    unlock: passphrase => exclusive(async () => {
      const record = await read();
      if (!record) fail('No valid saved capsule.');
      const result = await unpack(record, { passphrase, context, crypto, now:now() });
      if (result.expiresAt <= now()) { await backend.delete(); fail('Capsule expired.'); }
      return result;
    }),
    delete: () => typeof requestLock === 'function'
      ? exclusive(async () => { await backend.delete(); return { coordinated:true }; })
      : Promise.resolve().then(async () => { await backend.delete(); return { coordinated:false }; }),
  };
}
/** One fixed record in this origin's database. Resolve writes only on transaction commit. */
export function indexedDBBackend(indexedDB) {
  if (arguments.length === 0) {
    try { indexedDB = globalThis.indexedDB; } catch { indexedDB = null; }
  }
  const operation = (mode, value) => new Promise((resolve, reject) => {
    if (!indexedDB) { reject(new Error('Local save unavailable: IndexedDB is required.')); return; }
    let db, tx, finished = false, result;
    const finish = error => { if (finished) return; finished = true; clearTimeout(timer); db?.close(); error ? reject(new Error('Local storage failed; deletion or save is not confirmed.')) : resolve(result); };
    const timer = setTimeout(() => { try { tx?.abort(); } catch {} finish(true); }, 5000);
    let request;
    try { request = indexedDB.open(VERSION, 1); } catch { finish(true); return; }
    request.onupgradeneeded = () => { request.result.createObjectStore('capsule'); };
    request.onerror = () => finish(true);
    request.onblocked = () => finish(true);
    request.onsuccess = () => {
      db = request.result;
      if (finished) { db.close(); return; }
      db.onversionchange = () => db.close();
      try {
        tx = db.transaction('capsule', mode === 'read' ? 'readonly' : 'readwrite');
        const store = tx.objectStore('capsule');
        const r = mode === 'read' ? store.get('selected') : mode === 'write' ? store.put(value, 'selected') : store.clear();
        r.onsuccess = () => { result = r.result; };
        tx.oncomplete = () => finish(false);
        tx.onabort = tx.onerror = () => finish(true);
      } catch { finish(true); }
    };
  });
  return { read:() => operation('read'), write:e => operation('write', e), delete:() => operation('delete') };
}
