import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createGuideSession } from './guide-core.mjs';
import { DATA_KEY, EPOCH_KEY, writeGuideMetadata, eraseGuideMetadata, describeGuideErasure } from './guide-storage.mjs';
import { registerGuideTools } from './guide-webmcp.mjs';

// Synthetic storage and minimal DOM contracts, not a browser/render/camera qualification.
function storageFixture(initial = {}) {
  const values = new Map(Object.entries(initial)), calls = [], faults = new Set();
  const storage = {
    getItem(key) { calls.push(['get', key]); if (faults.has(`get:${key}`)) throw new Error('blocked read'); return values.get(key) ?? null; },
    setItem(key, value) { calls.push(['set', key]); if (faults.has(`set:${key}`)) throw new Error('blocked write'); values.set(key, value); storage.afterSet?.(key, value); },
    removeItem(key) { calls.push(['remove', key]); if (faults.has(`remove:${key}`)) throw new Error('blocked delete'); values.delete(key); },
  };
  return { storage, values, calls, faults };
}

test('forget still deletes DATA and checks it when writing the invalidation epoch fails', () => {
  const env = storageFixture({ [EPOCH_KEY]: 'old', [DATA_KEY]: 'private selected text' });
  env.faults.add(`set:${EPOCH_KEY}`);
  const result = eraseGuideMetadata(env.storage, { epoch: 'new' });
  assert.equal(env.values.has(DATA_KEY), false);
  assert.equal(result.dataState, 'cleared');
  assert.equal(result.epochConfirmed, false);
  assert.equal(result.ok, false);
  assert.deepEqual(result.failures, ['EPOCH_WRITE_FAILED']);
  assert.match(describeGuideErasure(result), /other tabs could not be invalidated/);
});

test('failed deletion and failed readback never claim saved data was forgotten', () => {
  const env = storageFixture({ [EPOCH_KEY]: 'old', [DATA_KEY]: 'private selected text' });
  env.faults.add(`remove:${DATA_KEY}`);
  const retained = eraseGuideMetadata(env.storage, { epoch: 'new' });
  assert.equal(retained.ok, false);
  assert.equal(retained.dataState, 'saved');
  assert.match(describeGuideErasure(retained, 'opt-out'), /Saving is off.*kept the saved metadata/);
  env.faults.add(`get:${DATA_KEY}`);
  const unknown = eraseGuideMetadata(env.storage, { epoch: 'newer' });
  assert.equal(unknown.dataState, 'unknown');
  assert.match(describeGuideErasure(unknown), /removal could not be verified/);
});

test('a stale tab cannot resurrect metadata after an acknowledged forget', () => {
  const oldRaw = JSON.stringify({ epoch: 'old', metadata: 'old workbench' });
  const env = storageFixture({ [EPOCH_KEY]: 'old', [DATA_KEY]: oldRaw });
  assert.equal(eraseGuideMetadata(env.storage, { epoch: 'new' }).ok, true);
  const stale = writeGuideMetadata(env.storage, { epoch: 'old', previousRaw: oldRaw, metadata: 'resurrected workbench' });
  assert.equal(stale.code, 'EPOCH_CHANGED');
  assert.equal(env.values.has(DATA_KEY), false);
});

test('forget interleaved during a save removes only that stale writer’s own bytes', () => {
  for (const preserveNewer of [false, true]) {
    const env = storageFixture({ [EPOCH_KEY]: 'old' });
    const newerRaw = JSON.stringify({ epoch: 'new', metadata: 'newly confirmed workbench' });
    env.storage.afterSet = key => {
      if (key !== DATA_KEY) return;
      env.values.set(EPOCH_KEY, 'new');
      if (preserveNewer) env.values.set(DATA_KEY, newerRaw);
    };
    const result = writeGuideMetadata(env.storage, { epoch: 'old', previousRaw: null, metadata: 'stale workbench' });
    assert.equal(result.code, 'EPOCH_CHANGED');
    assert.equal(env.values.get(DATA_KEY), preserveNewer ? newerRaw : undefined);
  }
});

test('assistant tools register only with consent; retained handles deny reads and proposals after revocation', () => {
  const tools = [], removed = [], statuses = []; let enabled = false, reads = 0, proposals = 0;
  const document = { modelContext: {
    registerTool(tool, options) { tools.push({ ...tool, signal: options.signal }); },
    unregisterTool(name) { removed.push(name); },
  } };
  const ports = { isEnabled: () => enabled, read: () => { reads++; return { sessionId: 'session', revision: 1 }; },
    onProposal: () => { proposals++; return { proposed: true, actionAuthorized: false }; }, onStatus: status => statuses.push(status) };
  registerGuideTools(document, ports)();
  assert.equal(tools.length, 0);
  enabled = true; const cleanup = registerGuideTools(document, ports);
  assert.equal(tools.length, 3);
  const read = tools.find(tool => tool.name.endsWith('read_state'));
  assert.equal(read.execute({}).actionAuthorized, false);
  assert.equal(reads, 1);
  enabled = false; // Execute-time consent is enforced even before cleanup is delivered.
  assert.equal(read.execute({}).error, true);
  assert.equal(tools.find(tool => tool.name.endsWith('propose_resume')).execute({ sessionId: 'session', expectedRevision: 1 }).error, true);
  cleanup(); enabled = true; // Old handles must not reactivate when a new permission is granted.
  assert.equal(read.execute({}).error, true);
  assert.equal(reads, 1); assert.equal(proposals, 0);
  assert.equal(tools.every(tool => tool.signal.aborted), true);
  assert.equal(removed.length, 3);
  assert.deepEqual(statuses, ['disabled', 'registered']);
});

class Element {
  constructor(id = '') { this.id = id; this.listeners = new Map(); this.dataset = {}; this.children = []; this.value = ''; this.checked = false; this.disabled = false; this.hidden = false; this.textContent = ''; this.classList = { toggle() {} }; }
  addEventListener(name, handler) { this.listeners.set(name, [...this.listeners.get(name) ?? [], handler]); }
  removeEventListener(name, handler) { this.listeners.set(name, (this.listeners.get(name) ?? []).filter(value => value !== handler)); }
  async emit(name, extra = {}) { for (const handler of this.listeners.get(name) ?? []) await handler({ target: this, preventDefault() {}, ...extra }); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  closest() { return this; }
  focus() {} select() {} pause() {} matches() { return false; }
  getClientRects() { return [1]; }
  showModal() { this.open = true; }
}

let imports = 0;
async function loadUI(storage) {
  const html = await readFile(new URL('./index.html', import.meta.url), 'utf8');
  const elements = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Element(match[1])]));
  const document = new Element(), window = new Element(), registered = [], removed = [];
  Object.assign(document, { hidden: false, body: new Element(), getElementById: id => {
    assert.ok(elements.has(id), `HTML includes #${id}`); return elements.get(id);
  }, createElement: () => new Element(), querySelector: () => null, querySelectorAll: () => [], modelContext: {
    registerTool(tool, options) { registered.push({ ...tool, signal: options.signal }); },
    unregisterTool(name) { removed.push(name); },
  } });
  let timer = 0;
  const globals = { document, window, localStorage: storage, location: { search: '', reload() {} },
    navigator: { onLine: true, locks: { request: async (_name, _options, callback) => callback({ name: 'synthetic-writer-lock' }) } },
    setTimeout: () => ++timer, clearTimeout() {}, setInterval: () => ++timer, clearInterval() {} };
  const previous = new Map(Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const restore = () => { for (const [key, descriptor] of previous) if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; };
  try { await import(`./guide-app.mjs?boundary-test=${++imports}`); }
  catch (error) { restore(); throw error; }
  return { document, window, registered, removed, element: id => elements.get(id),
    async cleanup() { await window.emit('pagehide'); restore(); } };
}

async function savedFixture() {
  let now = Date.now() - 1000, id = 0;
  const session = createGuideSession({ now: () => now, id: () => `synthetic-${++id}` });
  session.setConsent({ memory: true, capture: true });
  session.beginTask({ title: 'Synthetic workbench', mode: 'teach', items: [{ id: 'charger', name: 'Charger' }] });
  const request = session.requestView({ itemId: 'charger', reason: 'overview' }).request;
  const bytes = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3, 4, 5]);
  assert.equal((await session.acceptFrame({ requestId: request.requestId, binding: request.binding, bytes,
    sha256: createHash('sha256').update(bytes).digest('hex'), mimeType: 'image/png', capturedAtMs: ++now, sequence: 1, source: 'phone-camera' })).ok, true);
  assert.equal(session.confirmMemory({ requestId: request.requestId, itemId: 'charger', name: 'Charger', place: 'Desk', confirmed: true }).ok, true);
  return storageFixture({ [EPOCH_KEY]: 'saved-epoch', [DATA_KEY]: JSON.stringify({ epoch: 'saved-epoch', metadata: session.exportState() }) });
}

test('fresh unconsented UI writes no storage and registers no assistant surface', async () => {
  const env = storageFixture(), ui = await loadUI(env.storage);
  try {
    assert.equal(env.calls.some(([operation]) => operation !== 'get'), false);
    assert.equal(ui.registered.length, 0);
    assert.equal(ui.element('assistantSharing').checked, false);
    assert.equal(ui.element('saveLocally').checked, false);
  } finally { await ui.cleanup(); }
});

test('UI revokes assistant access on off, camera revocation, forget and pagehide', async () => {
  for (const action of ['off', 'camera', 'forget', 'pagehide']) {
    const ui = await loadUI(storageFixture().storage);
    try {
      ui.element('assistantSharing').checked = true;
      await ui.element('assistantSharing').emit('change');
      assert.equal(ui.registered.length, 3);
      const read = ui.registered.find(tool => tool.name.endsWith('read_state'));
      assert.equal(read.execute({}).error, undefined);
      if (action === 'off') { ui.element('assistantSharing').checked = false; await ui.element('assistantSharing').emit('change'); }
      if (action === 'camera') await ui.element('revokeCapture').emit('click');
      if (action === 'forget') { ui.element('forgetDialog').returnValue = 'forget'; await ui.element('forgetDialog').emit('close'); }
      if (action === 'pagehide') await ui.window.emit('pagehide');
      assert.equal(ui.element('assistantSharing').checked, false);
      assert.equal(read.execute({}).error, true);
      assert.equal(read.signal.aborted, true);
      assert.equal(ui.removed.length >= 3, true);
    } finally { await ui.cleanup(); }
  }
});

test('failed opt-out and subsequent single-item forget keep persistent-erasure failure visible', async () => {
  const env = await savedFixture(), ui = await loadUI(env.storage);
  try {
    env.faults.add(`remove:${DATA_KEY}`);
    ui.element('saveLocally').checked = false; await ui.element('saveLocally').emit('change');
    assert.equal(ui.element('saveLocally').checked, false);
    assert.match(ui.element('storageStatus').textContent, /kept the saved metadata/);
    const button = new Element(); button.dataset = { action: 'forget', item: 'charger' };
    await ui.element('memoryList').emit('click', { target: button });
    assert.match(ui.element('toast').textContent, /removed from this tab.*saved metadata could not be updated/);
    assert.equal(env.values.has(DATA_KEY), true);
  } finally { await ui.cleanup(); }
});

test('saving can still be turned off after a failed metadata update', async () => {
  const env = await savedFixture(), ui = await loadUI(env.storage);
  try {
    env.faults.add(`set:${DATA_KEY}`);
    ui.element('contextInput').value = JSON.stringify({ schema: 'lens.selected-context/v1', selectionId: 'selected-note', source: 'screenshotcontext', selectedByUser: true,
      entries: [{ id: 'note', title: 'Bag note', summary: 'Bring the charger.', observedAtMs: Date.now() - 100, timeBasis: 'user-note' }] });
    await ui.element('importContext').emit('click');
    assert.match(ui.element('storageStatus').textContent, /could not be updated/);
    assert.equal(ui.element('saveLocally').checked, true);
    assert.equal(ui.element('saveLocally').disabled, false);
    ui.element('saveLocally').checked = false; await ui.element('saveLocally').emit('change');
    assert.equal(env.values.has(DATA_KEY), false);
    assert.match(ui.element('toast').textContent, /Saved metadata was removed/);
  } finally { await ui.cleanup(); }
});
