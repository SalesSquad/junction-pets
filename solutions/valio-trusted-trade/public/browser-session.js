/** Origin-local SYNTHETIC demo recovery. Never exports private CryptoKeys. */
export function browserSession(variant) {
  let available = true;
  let writes = Promise.resolve();
  const transact = (mode, operation) => new Promise((resolve, reject) => {
    const opening = indexedDB.open('trusted-trade-local-demo-v1', 1);
    let expired = false;
    let activeTransaction;
    const timer = setTimeout(() => { expired = true; activeTransaction?.abort(); reject(Error('Local recovery storage unavailable.')); }, 1500);
    opening.onupgradeneeded = () => opening.result.createObjectStore('sessions');
    opening.onerror = () => { clearTimeout(timer); reject(opening.error); };
    opening.onblocked = () => { expired = true; clearTimeout(timer); reject(Error('Local recovery storage blocked.')); };
    opening.onsuccess = () => {
      const database = opening.result;
      if (expired) { database.close(); return; }
      let result;
      try {
        const transaction = database.transaction('sessions', mode);
        activeTransaction = transaction;
        const request = operation(transaction.objectStore('sessions'));
        request.onsuccess = () => { result = request.result; };
        transaction.oncomplete = () => { clearTimeout(timer); database.close(); resolve(result); };
        transaction.onerror = transaction.onabort = () => { clearTimeout(timer); database.close(); reject(transaction.error); };
      } catch (error) { clearTimeout(timer); database.close(); reject(error); }
    };
  });
  return {
    get available() { return available; },
    async load() {
      let stored;
      try { stored = await transact('readonly', store => store.get(variant)); }
      catch { available = false; return null; }
      if (!stored) return null;
      if (stored.version !== 1 || stored.origin !== location.origin || stored.variant !== variant ||
          !stored.value || typeof stored.value.token !== 'string' || !/^[A-Za-z0-9_-]{10,128}$/.test(stored.value.token)) {
        throw Error('Stored browser demo state is incompatible; it was preserved without creating a replacement session.');
      }
      return stored.value;
    },
    save(value) {
      if (!available) return Promise.resolve();
      let detached;
      try { detached = structuredClone(value); } catch { available = false; return Promise.resolve(); }
      writes = writes.then(async () => {
        if (!available) return;
        try { await transact('readwrite', store => store.put({ version: 1, origin: location.origin, variant, value: detached }, variant)); }
        catch { available = false; }
      });
      return writes;
    },
    async clear() {
      try { await writes; await transact('readwrite', store => store.delete(variant)); }
      catch { available = false; }
    },
  };
}

export async function restoredBearer(cache, buyerId) {
  const configuration = await fetch('/api/identity/configuration', { redirect: 'error', signal: AbortSignal.timeout(7000) });
  if (!configuration.ok) throw Error('Identity mode cannot be checked; existing recovery data was preserved.');
  const identity = await configuration.json();
  if (identity.mode === 'HOST_AUTHENTICATED') throw Error('Identity connection required: open this workflow through the configured private host. Local demo sign-in and model approvals are disabled; no external credential is accepted in this page.');
  if (identity.mode !== 'SYNTHETIC') throw Error('Unknown identity mode; recovery was preserved without creating a session.');
  const saved = await cache.load();
  if (saved) {
    const response = await fetch('/api/demo/session', { headers: { Authorization: 'Bearer ' + saved.token },
      redirect: 'error', signal: AbortSignal.timeout(7000) });
    if (response.ok) {
      const current = await response.json();
      if (current.buyerId !== buyerId || current.mode !== 'SYNTHETIC') throw Error('Original local demo identity does not match this page.');
      return { token: saved.token, saved };
    }
    if (![401, 403].includes(response.status)) throw Error('Original demo session cannot be checked; recovery was preserved.');
    await cache.clear();
  }
  const response = await fetch('/api/demo/session', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ buyerId }), redirect: 'error', signal: AbortSignal.timeout(7000) });
  const body = await response.json();
  if (!response.ok || body.mode !== 'SYNTHETIC_NOT_AUTHENTICATED' || typeof body.token !== 'string') throw Error('Demo session unavailable.');
  return { token: body.token, saved: null };
}
