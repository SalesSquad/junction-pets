/** Advisory UI only. No command, observation admission or confirmation is issued here. */
export const BUNDLE_LIMIT = 2_097_152;
const IMAGE_LIMIT = 1_048_576;
const HASH = /^[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const record = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
const exact = (x, keys) => record(x) && Object.keys(x).length === keys.length && keys.every((key) => Object.hasOwn(x, key));
const text = (x, max = 600) => typeof x === 'string' && x.trim().length > 0 && x.length <= max;
const uint = (x) => Number.isSafeInteger(x) && x >= 0 && x <= 2_147_483_647;
const dimension = (x) => Number.isSafeInteger(x) && x > 0 && x <= 4096;
const fail = () => { throw new Error('This observation file is not supported. Use the exported frame or crop bundle.'); };

export function validateObservationBundle(bundle) {
  if (!exact(bundle, ['observation', 'image'])) fail();
  const o = bundle.observation, image = bundle.image;
  if (!exact(o, ['schemaVersion', 'kind', 'evidenceMode', 'episodeId', 'sessionId', 'captureGeneration', 'runId', 'trackGeneration', 'sourceThroughFrameIndex', 'frame', 'model', 'tracks']) ||
      o.schemaVersion !== 1 || o.kind !== 'meta.sam31.observation' || !['MODEL', 'SYNTHETIC'].includes(o.evidenceMode) ||
      ![o.episodeId, o.sessionId, o.runId].every((x) => typeof x === 'string' && ID.test(x)) ||
      ![o.captureGeneration, o.trackGeneration, o.sourceThroughFrameIndex].every(uint)) fail();
  const f = o.frame;
  if (!exact(f, ['frameIndex', 'sha256', 'capturedAt', 'width', 'height']) ||
      !uint(f.frameIndex) || o.sourceThroughFrameIndex !== f.frameIndex || !HASH.test(f.sha256) ||
      !text(f.capturedAt, 40) || !Number.isFinite(Date.parse(f.capturedAt)) || !dimension(f.width) || !dimension(f.height)) fail();
  const model = o.model;
  if (!exact(model, ['id', 'codeCommit', 'weightsRevision', 'checkpointSha256']) ||
      model.id !== 'facebook/sam3.1' || model.codeCommit !== 'eef6839bcfc3458dd52ea80535dc6bd62aea86b1' ||
      model.weightsRevision !== 'daa63191845a41281374e725f4c9e51c7a824460' || !HASH.test(model.checkpointSha256) ||
      !Array.isArray(o.tracks) || o.tracks.length > 8) fail();
  const ids = new Set();
  for (const t of o.tracks) {
    if (!exact(t, ['trackId', 'label', 'bbox', 'maskSha256', 'crop', 'visibility']) ||
        typeof t.trackId !== 'string' || !ID.test(t.trackId) || ids.has(t.trackId) || !text(t.label, 80) ||
        !HASH.test(t.maskSha256) || t.visibility !== 'visible' || !Array.isArray(t.bbox) || t.bbox.length !== 4 ||
        !t.bbox.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) ||
        t.bbox[0] >= t.bbox[2] || t.bbox[1] >= t.bbox[3] ||
        !exact(t.crop, ['sha256', 'width', 'height', 'mimeType']) || !HASH.test(t.crop.sha256) ||
        !dimension(t.crop.width) || !dimension(t.crop.height) || !['image/png', 'image/jpeg'].includes(t.crop.mimeType)) fail();
    ids.add(t.trackId);
  }
  if (!exact(image, ['kind', 'dataUrl', 'sha256', 'trackId']) || !['frame', 'crop'].includes(image.kind) ||
      !HASH.test(image.sha256) || typeof image.dataUrl !== 'string' || image.dataUrl.length > 1_398_160) fail();
  const match = /^data:image\/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})$/.exec(image.dataUrl);
  if (!match || match[2].length % 4 !== 0) fail();
  const cropTrack = o.tracks.find((t) => t.trackId === image.trackId);
  if (image.kind === 'frame' && (image.trackId !== null || image.sha256 !== f.sha256)) fail();
  if (image.kind === 'crop' && (!cropTrack || image.sha256 !== cropTrack.crop.sha256 || cropTrack.crop.mimeType !== 'image/' + match[1])) fail();
  let binary;
  try { binary = atob(match[2]); } catch { fail(); }
  if (binary.length < 4 || binary.length > IMAGE_LIMIT || btoa(binary) !== match[2]) fail();
  return bundle;
}

export async function parseObservationBundle(raw) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > BUNDLE_LIMIT) fail();
  let bundle;
  try { bundle = JSON.parse(raw); } catch { fail(); }
  validateObservationBundle(bundle);
  const bytes = Uint8Array.from(atob(bundle.image.dataUrl.split(',')[1]), (c) => c.charCodeAt(0));
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((n) => n.toString(16).padStart(2, '0')).join('');
  if (digest !== bundle.image.sha256) throw new Error('The image does not match this observation. Export the frame and its record together.');
  return bundle;
}

export function contextKey(state, policy) {
  return JSON.stringify([state.taskId, state.revision, state.status, state.nextUnconfirmedStep,
    policy.sessionId, policy.captureGeneration, policy.captureEnabled]);
}

export function bundleIsCurrent(bundle, state, policy) {
  return Boolean(bundle && policy.captureEnabled && state.status !== 'completed' &&
    state.nextUnconfirmedStep && bundle.observation.sessionId === policy.sessionId &&
    bundle.observation.captureGeneration === policy.captureGeneration);
}

export function observationRequest(bundle, state, policy) {
  validateObservationBundle(bundle);
  if (!bundleIsCurrent(bundle, state, policy)) throw new Error('This observation belongs to an earlier or different capture. Load a current observation.');
  const step = state.steps.find((x) => x.stepId === state.nextUnconfirmedStep);
  if (!step) throw new Error('There is no unfinished step to look at.');
  return { schemaVersion: 1, task: { taskId: state.taskId, revision: state.revision, status: state.status,
    nextStep: { stepId: step.stepId, label: step.label } }, observation: bundle.observation, image: bundle.image };
}

/** Reject stale replies and purported identity/completion grants before display. */
export function validateObservationResponse(result, request, currentState, currentPolicy) {
  if (!record(result) || !['proposed', 'abstained', 'skipped', 'failed'].includes(result.status)) fail();
  if (currentState.taskId !== request.task.taskId || currentState.revision !== request.task.revision ||
      currentState.status !== request.task.status || currentState.nextUnconfirmedStep !== request.task.nextStep.stepId ||
      !bundleIsCurrent(request, currentState, currentPolicy)) throw new Error('Your task changed while looking. Analyze the current step again.');
  if (result.status === 'failed') return { status: 'failed', proposal: null, receipt: {} };
  const o = request.observation;
  const expected = { taskId: request.task.taskId, expectedRevision: request.task.revision,
    episodeId: o.episodeId, sessionId: o.sessionId, captureGeneration: o.captureGeneration,
    frameSha256: o.frame.sha256, frameIndex: o.frame.frameIndex, runId: o.runId, trackGeneration: o.trackGeneration };
  if (!exact(result.binding, Object.keys(expected)) || Object.keys(expected).some((k) => result.binding[k] !== expected[k])) {
    throw new Error('The answer does not match this observation. Nothing was applied.');
  }
  const p = result.proposal;
  if (p === null && ['skipped', 'abstained'].includes(result.status)) return result;
  const ids = new Set(o.tracks.map((x) => x.trackId));
  if (!exact(p, ['summary', 'observations', 'uncertainties', 'nextQuestion', 'nextStepProposal', 'physicalIdentityVerified', 'taskCompletionAuthorized']) ||
      !text(p.summary) || p.physicalIdentityVerified !== false || p.taskCompletionAuthorized !== false ||
      !Array.isArray(p.observations) || p.observations.length > 8 ||
      !p.observations.every((x) => exact(x, ['trackId', 'text']) && ids.has(x.trackId) && text(x.text, 300)) ||
      !Array.isArray(p.uncertainties) || p.uncertainties.length > 8 || !p.uncertainties.every((x) => text(x, 300)) ||
      !(p.nextQuestion === null || text(p.nextQuestion, 300)) ||
      !(p.nextStepProposal === null || exact(p.nextStepProposal, ['stepId', 'label']) &&
        p.nextStepProposal.stepId === request.task.nextStep.stepId && p.nextStepProposal.label === request.task.nextStep.label)) fail();
  return result;
}

async function jsonResponse(response, limit = BUNDLE_LIMIT) {
  if (!response.ok || !/^application\/json(?:;|$)/i.test(response.headers.get('content-type') || '')) {
    throw new Error('The observation service is unavailable. Your packing controls still work.');
  }
  if (Number(response.headers.get('content-length') || 0) > limit) fail();
  const reader = response.body.getReader();
  let bytes = 0;
  const chunks = [];
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) { await reader.cancel(); fail(); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const joined = new Uint8Array(bytes);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.length; }
  return new TextDecoder().decode(joined);
}

function node(tag, textContent, className) {
  const el = document.createElement(tag);
  if (textContent !== undefined) el.textContent = textContent;
  if (className) el.className = className;
  return el;
}

export function createObservationPanel({ element, read, notify, returnToTask }) {
  const $ = (selector) => element.querySelector(selector);
  let config = null, bundle = null, result = null, status = 'Checking observation connection…';
  let busy = false, requestVersion = 0, abort = null, lastContext = '', displayedBundle = null;

  function cancel() { requestVersion += 1; abort?.abort(); abort = null; busy = false; }

  function render() {
    const { state, policy } = read();
    const current = bundleIsCurrent(bundle, state, policy);
    $('#observationStatus').textContent = status;
    $('#observationAnalyze').disabled = busy || !config || !current;
    $('#observationSample').disabled = busy || !config || !policy.captureEnabled || state.status === 'completed';
    $('#observationImport').disabled = busy || !policy.captureEnabled || state.status === 'completed';
    $('#observationClear').disabled = !bundle && !busy;
    element.setAttribute('aria-busy', String(busy));
    $('#observationAnalyze').textContent = busy ? 'Looking…' : 'Analyze this moment';
    $('#observationBadge').textContent = bundle?.observation.evidenceMode === 'SYNTHETIC' || config?.mode === 'synthetic'
      ? 'SYNTHETIC DEMO' : bundle ? 'IMPORTED OBSERVATION' : 'ADVISORY';
    $('#observationDisclosure').textContent = config?.mode === 'hosted'
      ? 'Analyze sends this one image and the current step to NVIDIA. Your confirmations stay in this browser.'
      : config?.mode === 'local'
        ? 'Analyze sends this one image and the current step to the configured local model service.'
        : config?.mode === 'synthetic'
          ? 'The sample and interpretation are synthetic. No model or camera is running.'
          : 'No observation service connected. The local packing demo remains available.';
    $('#observationPreview').hidden = !bundle;
    if (bundle !== displayedBundle) {
      displayedBundle = bundle;
      const image = $('#observationImage'), svg = $('#observationBoxes');
      svg.replaceChildren();
      image.removeAttribute('src');
      if (bundle) {
        image.src = bundle.image.dataUrl;
        image.alt = bundle.observation.evidenceMode === 'SYNTHETIC' ? 'Synthetic observation sample' : 'Imported observation, identity unverified';
        const visible = bundle.image.kind === 'frame' ? bundle.observation.tracks : [];
        for (const track of visible) {
          const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          const [x, y, right, bottom] = track.bbox;
          for (const [key, value] of Object.entries({ x, y, width: right - x, height: bottom - y })) rect.setAttribute(key, String(value));
          svg.append(rect);
        }
      }
    }
    $('#observationCaption').textContent = bundle
      ? (bundle.image.kind === 'crop' ? 'Selected image region' : bundle.observation.tracks.length + ' visible candidate' + (bundle.observation.tracks.length === 1 ? '' : 's')) + ' · identity unverified'
      : '';
    const output = $('#observationOutput'); output.replaceChildren();
    if (result?.proposal) {
      const p = result.proposal;
      output.append(node('p', p.summary, 'observation-summary'));
      if (p.observations.length) {
        const list = node('ul', undefined, 'observation-facts');
        for (const observation of p.observations) list.append(node('li', observation.text));
        output.append(list);
      }
      for (const uncertainty of p.uncertainties) output.append(node('p', uncertainty, 'observation-uncertainty'));
      if (p.nextQuestion) output.append(node('p', p.nextQuestion, 'observation-question'));
      if (p.nextStepProposal) output.append(node('p', 'Your next step: ' + p.nextStepProposal.label, 'observation-next'));
      const button = node('button', 'Return to my current step ↗', 'secondary-button observation-return');
      button.type = 'button'; button.addEventListener('click', returnToTask); output.append(button);
      output.append(node('p', 'Nothing was marked packed. You check and confirm.', 'observation-advisory'));
    } else if (result?.status === 'skipped') output.append(node('p', 'No new interpretation was needed. Your current step is unchanged.', 'observation-summary'));
    else if (result?.status === 'abstained') output.append(node('p', 'There is not enough visual evidence. Check the item yourself or try a clearer moment.', 'observation-summary'));
    const details = $('#observationDetails'); details.replaceChildren();
    if (bundle) {
      const rows = [
        ['Capture', bundle.observation.sessionId + ' / ' + bundle.observation.captureGeneration],
        ['Frame', String(bundle.observation.frame.frameIndex) + ' · ' + bundle.observation.frame.capturedAt],
        ['Image SHA-256', bundle.image.sha256],
        ['Track source', bundle.observation.evidenceMode === 'SYNTHETIC' ? 'Synthetic fixture, not a SAM execution' : 'Declared SAM output; not physical identity proof'],
        ['Interpretation', config?.mode === 'synthetic' ? 'Synthetic response' : config?.mode === 'local' ? 'Local NVIDIA profile' : config?.mode === 'hosted' ? 'Hosted NVIDIA profile' : 'Unavailable'],
      ];
      for (const [term, value] of rows) { details.append(node('dt', term), node('dd', value)); }
    }
  }

  function sync() {
    const { state, policy } = read(), key = contextKey(state, policy);
    if (lastContext && lastContext !== key) {
      const hadWork = Boolean(result || busy);
      cancel(); result = null;
      if (!policy.captureEnabled || bundle && (bundle.observation.sessionId !== policy.sessionId || bundle.observation.captureGeneration !== policy.captureGeneration)) {
        bundle = null; status = 'Observations stopped. Your confirmations are preserved.';
      } else if (hadWork) status = 'Your task changed. Analyze again for the current step.';
    }
    lastContext = key;
    render();
  }

  function clear(message = 'Observation cleared from this page.') {
    cancel(); bundle = null; result = null; status = message; render();
  }

  async function load(raw, version) {
    const next = await parseObservationBundle(raw);
    if (version !== requestVersion) return;
    const { state, policy } = read();
    if (!bundleIsCurrent(next, state, policy)) throw new Error('This observation is from a different or stopped capture. Load a current one.');
    bundle = next; result = null;
    status = next.observation.evidenceMode === 'SYNTHETIC' ? 'Synthetic sample ready. Analyze when you want.' : 'Observation ready. Nothing has been sent yet.';
    render();
  }

  $('#observationSample').addEventListener('click', async () => {
    cancel(); const version = requestVersion; abort = new AbortController(); busy = true; status = 'Loading the synthetic sample…'; render();
    try {
      const raw = await jsonResponse(await fetch('/api/demo-observation', { credentials: 'same-origin', signal: abort.signal, cache: 'no-store' }));
      if (version !== requestVersion) return;
      await load(raw, version);
    } catch (error) {
      if (version !== requestVersion) return;
      status = error.name === 'AbortError' ? 'Loading cancelled.' : error.message;
      notify(status);
    } finally { if (version === requestVersion) { busy = false; abort = null; render(); } }
  });

  $('#observationImport').addEventListener('click', () => $('#observationFile').click());
  $('#observationFile').addEventListener('change', async (event) => {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    cancel(); const version = requestVersion;
    try {
      if (file.size > BUNDLE_LIMIT) throw new Error('Choose an observation JSON smaller than 2 MiB.');
      const raw = await file.text();
      if (version !== requestVersion) return;
      await load(raw, version);
    } catch (error) {
      if (version !== requestVersion) return;
      status = error.message; notify(status); render();
    }
  });

  $('#observationAnalyze').addEventListener('click', async () => {
    if (!config || busy) return;
    let request;
    try { const { state, policy } = read(); request = observationRequest(bundle, state, policy); }
    catch (error) { status = error.message; notify(status); render(); return; }
    cancel(); const version = requestVersion; abort = new AbortController(); busy = true; result = null;
    status = config.mode === 'synthetic' ? 'Reading the synthetic moment…' : 'Looking at this moment…'; render();
    const timer = setTimeout(() => abort?.abort(), 45_000);
    try {
      const raw = await jsonResponse(await fetch('/api/observe', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-Meta-CSRF': config.csrfToken }, body: JSON.stringify(request), signal: abort.signal }), 262_144);
      if (version !== requestVersion) return;
      const { state, policy } = read();
      result = validateObservationResponse(JSON.parse(raw), request, state, policy);
      status = result.status === 'failed' ? 'The moment could not be interpreted. You can still check and pack the item.'
        : result.status === 'skipped' ? 'Your current context is unchanged.'
          : result.status === 'abstained' ? 'A closer look is needed.' : 'A suggestion for this moment. Your task is unchanged.';
    } catch (error) {
      if (version !== requestVersion) return;
      result = null;
      status = error.name === 'AbortError' ? 'The request took too long. Your task is unchanged.' : error.message;
      notify(status);
    } finally {
      clearTimeout(timer);
      if (version === requestVersion) { busy = false; abort = null; render(); }
    }
  });
  $('#observationClear').addEventListener('click', () => clear());
  $('#observationImage').addEventListener('load', () => {
    const image = $('#observationImage');
    const expected = bundle?.image.kind === 'crop' ? bundle.observation.tracks.find((t) => t.trackId === bundle.image.trackId)?.crop : bundle?.observation.frame;
    if (expected && (image.naturalWidth !== expected.width || image.naturalHeight !== expected.height)) clear('This image does not match its recorded dimensions.');
  });
  $('#observationImage').addEventListener('error', () => {
    if (bundle) clear('This image could not be displayed. Choose a valid PNG or JPEG observation.');
  });

  async function connect() {
    try {
      const raw = await jsonResponse(await fetch('/api/config', { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(5000) }), 8192);
      const data = JSON.parse(raw);
      if (!record(data) || !['synthetic', 'hosted', 'local'].includes(data.mode) || !text(data.csrfToken, 256)) throw new Error('Unavailable');
      config = { mode: data.mode, csrfToken: data.csrfToken };
      status = data.mode === 'synthetic' ? 'Synthetic demo connected. Load a sample or your own observation.' : 'Observation service connected. Choose a moment to analyze.';
    } catch {
      status = 'Observation service unavailable. The local packing demo still works.';
    }
    render();
  }
  sync(); void connect();
  return { sync, clear, mode: () => config?.mode ?? null, dispose: () => clear('Observation cleared. Load a new moment when you return.') };
}

