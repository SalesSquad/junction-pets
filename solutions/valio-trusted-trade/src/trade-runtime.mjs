/** Atomic persistent execution around the existing synchronous synthetic domain. */
import { createTradeService } from './core.mjs';
import { createDemoTrustRegistry } from './trust-envelope.mjs';
import { openLocalStateStore, StateStoreError } from './local-state-store.mjs';

export const HTTP_MAPS = Object.freeze(['sessions', 'quoteOwners', 'planOwners', 'orderOwners',
  'reviewOwners', 'requestReplay', 'agentRuns']);
export const createHttpContext = () => Object.fromEntries(HTTP_MAPS.map(name => [name, new Map()]));
const invalid = () => { throw new StateStoreError('STATE_CORRUPT', 'Runtime checkpoint is incomplete or incompatible; no fixture reset was performed.'); };

export function createTradeRuntime({ stateFile, clock = () => Date.now(),
  serviceFactory = () => createTradeService({ clock }), storeOptions = {} } = {}) {
  const store = openLocalStateStore(stateFile, storeOptions);
  const context = createHttpContext();
  let currentService, currentTrust, revision = -1;
  const hydrate = value => {
    if (value) {
      if (value.kind !== 'local-trade-runtime' || value.version !== 1 || !value.core || !value.trust ||
          !value.http || Object.keys(value.http).length !== HTTP_MAPS.length) invalid();
      for (const name of HTTP_MAPS) {
        const entries = value.http[name];
        if (!Array.isArray(entries) || entries.length > 20000 ||
            entries.some(pair => !Array.isArray(pair) || pair.length !== 2 || typeof pair[0] !== 'string' || pair[0].length > 1024) ||
            new Set(entries.map(pair => pair[0])).size !== entries.length) invalid();
      }
      currentService = createTradeService({ initialState: value.core, clock });
      currentTrust = createDemoTrustRegistry({ initialState: value.trust, clock });
    } else {
      currentService = serviceFactory();
      currentTrust = createDemoTrustRegistry({ clock });
    }
    for (const name of HTTP_MAPS) {
      context[name].clear();
      for (const [key, entry] of value?.http[name] ?? []) context[name].set(key, entry);
    }
  };
  const snapshot = () => ({
    kind: 'local-trade-runtime', version: 1,
    core: currentService.exportState(), trust: currentTrust.exportState(),
    http: Object.fromEntries(HTTP_MAPS.map(name => [name, [...context[name]]])),
  });
  const proxy = getter => new Proxy({}, { get(_target, name) {
    if (typeof getter()[name] !== 'function') return undefined;
    return (...args) => getter()[name](...args);
  } });
  const execute = (write, action) => {
    try {
      const result = store.transaction(write, row => {
        if (!currentService || row?.revision !== revision) { hydrate(row?.value ?? null); revision = row?.revision ?? 0; }
        const value = action();
        if (value?.then) throw new TypeError('Persistent dispatch must finish I/O before entering a transaction');
        // Validate serialization before commit/HTTP ACK. No credentials are logged.
        JSON.stringify(value);
        return { value, ...(write ? { state: snapshot() } : {}) };
      }, { knownRevision: revision });
      revision = result.revision;
      return result.value;
    } catch (error) {
      // A method may have mutated several closure Maps before storage fails.
      // Rehydrate after rollback, even if the database revision did not change.
      revision = -1;
      const saved = store.read();
      hydrate(saved?.value ?? null);
      revision = saved?.revision ?? 0;
      throw error;
    }
  };
  try { execute(true, () => null); }
  catch (error) { store.close(); throw error; }
  return Object.freeze({
    service: proxy(() => currentService), trust: proxy(() => currentTrust), context,
    execute, backup: destination => store.backup(destination), close: () => store.close(),
    storage: 'LOCAL_SQLITE_WAL_FULL_SYNCHRONOUS_SYNTHETIC',
  });
}
