/** Independent buyer process for the local SYNTHETIC HTTP service. */
import { createHash, createPrivateKey, createPublicKey, generateKeyPairSync, randomUUID, verify } from 'node:crypto';
import { canonical, digest, makeDemoMandatePayload, signDemoEnvelope } from '../src/trust-envelope.mjs';
import { verifyBuyerTerms, verifyBuyerBody } from '../src/buyer-terms.mjs';
import { constants, closeSync, fstatSync, lstatSync, openSync, readSync, realpathSync } from 'node:fs';
import { resolve } from 'node:path';

const BUYER = 'helsinki-hotel-demo';
const clone = value => structuredClone(value);
const fingerprint = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export class BridgeError extends Error {
  constructor(code, retryable = false) { super(code); this.code = code; this.retryable = retryable; }
}
const fail = (code, retryable) => { throw new BridgeError(code, retryable); };
const phaseKey = (key, phase) => 'mcp-' + fingerprint([key, phase]).slice(0, 52);
const entries = (state, name) => new Map(state[name]);
function put(state, name, key, value) {
  const map = entries(state, name);
  if (!map.has(key) && map.size >= 1000) fail('CLIENT_STATE_CAPACITY');
  map.set(key, value); state[name] = [...map];
}
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
const validPairs = value => Array.isArray(value) && value.length <= 1000 && value.every(e => Array.isArray(e) && e.length === 2 && typeof e[0] === 'string') && new Set(value.map(e => e[0])).size === value.length;

/** Executor-only provider; never accept this path from a model tool argument. */
export function privateHostCredentialFile(path) {
  if (typeof path !== 'string' || !path || path.length > 4096) fail('HOST_PROVIDER_CONFIG_INVALID');
  const file = resolve(path);
  return async () => {
    let descriptor;
    try {
      const expected = lstatSync(file);
      if (expected.isSymbolicLink() || realpathSync(file) !== file) fail('HOST_CREDENTIAL_UNAVAILABLE');
      descriptor = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW);
      const stat = fstatSync(descriptor);
      if (!stat.isFile() || stat.nlink !== 1 || stat.size < 1 || stat.size > 16384 || stat.ino !== expected.ino || stat.dev !== expected.dev ||
          (stat.mode & 0o077) || (process.getuid && stat.uid !== process.getuid())) fail('HOST_CREDENTIAL_UNAVAILABLE');
      const bytes = Buffer.alloc(16385);
      const length = readSync(descriptor, bytes, 0, bytes.length, 0);
      if (length > 16384) fail('HOST_CREDENTIAL_UNAVAILABLE');
      const value = new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length)).trim();
      if (!/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value)) fail('HOST_CREDENTIAL_UNAVAILABLE');
      return value;
    } catch { fail('HOST_CREDENTIAL_UNAVAILABLE'); } finally { if (descriptor !== undefined) closeSync(descriptor); }
  };
}

export async function createTradeClient({ baseUrl = 'http://127.0.0.1:4177', stateFile, fetchImpl = fetch, timeoutMs = 6000,
  hostAccessToken, hostDecisionProof } = {}) {
  const hostAuthenticated = hostAccessToken !== undefined;
  if ((hostAuthenticated && typeof hostAccessToken !== 'function') ||
      (hostDecisionProof !== undefined && (typeof hostDecisionProof !== 'function' || !hostAuthenticated))) fail('HOST_PROVIDER_CONFIG_INVALID');
  let base;
  try { base = new URL(baseUrl); } catch { fail('LOCAL_URL_REQUIRED'); }
  if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) ||
      base.username || base.password || base.pathname !== '/' || base.search || base.hash) fail('LOCAL_URL_REQUIRED');
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 30000) fail('INVALID_TIMEOUT');
  const lifetime = stateFile ? 'PRIVATE_LOCAL_SQLITE' : 'MEMORY_NON_RESUMABLE';
  const store = stateFile ? (await import('../src/local-state-store.mjs')).openLocalStateStore(stateFile) : null;
  const initial = () => {
    const pair = generateKeyPairSync('ed25519');
    const jwk = pair.publicKey.export({ format: 'jwk' });
    return { kind: 'synthetic-mcp-buyer', version: 1, baseUrl: base.origin, token: null,
      authMode: hostAuthenticated ? 'HOST' : 'DEMO', authBinding: null,
      privateKey: pair.privateKey.export({ format: 'der', type: 'pkcs8' }).toString('base64'),
      publicJwk: { kty: jwk.kty, crv: jwk.crv, x: jwk.x }, kid: null,
      runs: [], commands: [], challenges: [] };
  };
  const validate = state => {
    if (!state || state.kind !== 'synthetic-mcp-buyer' || state.version !== 1 || state.baseUrl !== base.origin ||
        !validPairs(state.runs) || !validPairs(state.commands) || !validPairs(state.challenges) ||
        !(state.token === null || typeof state.token === 'string' && /^[0-9a-f-]{36}$/.test(state.token)) ||
        typeof state.privateKey !== 'string' || state.privateKey.length > 1000 ||
        state.publicJwk?.kty !== 'OKP' || state.publicJwk?.crv !== 'Ed25519' || typeof state.publicJwk.x !== 'string') fail('CLIENT_STATE_INVALID');
    const mode = state.authMode ?? 'DEMO';
    if (!['DEMO', 'HOST'].includes(mode) || (mode === 'HOST' && !hostAuthenticated) ||
        (state.authBinding !== undefined && state.authBinding !== null &&
          (!safeId(state.authBinding.profileId) || !safeId(state.authBinding.ownerRef)))) fail('CLIENT_IDENTITY_SCOPE_MISMATCH');
    if (hostAuthenticated && mode === 'DEMO' && (state.token || state.kid ||
        state.runs.length || state.commands.length || state.challenges.length)) fail('CLIENT_IDENTITY_SCOPE_MISMATCH');
    if (!hostAuthenticated && state.authBinding) fail('CLIENT_IDENTITY_SCOPE_MISMATCH');
    if (hostAuthenticated && state.token !== null) fail('CLIENT_IDENTITY_SCOPE_MISMATCH');
    state.authMode = hostAuthenticated ? 'HOST' : 'DEMO';
    state.authBinding ??= null;
    try {
      const key = createPrivateKey({ key: Buffer.from(state.privateKey, 'base64'), format: 'der', type: 'pkcs8' });
      if (key.asymmetricKeyType !== 'ed25519' || createPublicKey(key).export({ format: 'jwk' }).x !== state.publicJwk.x) fail('CLIENT_STATE_INVALID');
    } catch { fail('CLIENT_STATE_INVALID'); }
    return state;
  };
  let memory;
  try {
    if (store) store.transaction(true, row => ({ state: validate(row?.value ?? initial()), value: null }));
    else memory = initial();
  } catch (error) { store?.close(); throw error; }
  const read = () => validate(store ? store.read().value : memory);
  const update = fn => {
    if (store) return store.transaction(true, row => { const state = validate(row.value); return { value: fn(state), state }; }).value;
    return fn(memory);
  };
  const hostProofs = new Map(); // Credential material is process-local, never checkpointed.
  const hostToken = value => {
    if (typeof value !== 'string' || value.length > 16384 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value)) fail('HOST_CREDENTIAL_UNAVAILABLE');
    return value;
  };
  const bindIdentity = identity => {
    if (identity.mode !== 'HOST_AUTHENTICATED' || identity.commerce !== 'SYNTHETIC' || identity.buyerId !== BUYER ||
        !safeId(identity.ownerRef) || !safeId(identity.profileId) || !safeId(identity.actorRef) ||
        !['HUMAN', 'AGENT'].includes(identity.principalType) || !Array.isArray(identity.actions) ||
        !Number.isSafeInteger(identity.grantRevision)) fail('HOST_IDENTITY_INVALID');
    const binding = { profileId: identity.profileId, ownerRef: identity.ownerRef };
    const prior = read().authBinding;
    if (prior && fingerprint(prior) !== fingerprint(binding)) fail('CLIENT_IDENTITY_SCOPE_MISMATCH');
    if (!prior) update(state => { state.authBinding = binding; });
  };
  const request = async (path, body, commandKey, authenticated = true, decisionProof) => {
    const url = new URL(path, base);
    if (url.origin !== base.origin) fail('CROSS_ORIGIN_REFUSED');
    if (hostAuthenticated && path === '/api/demo/session') fail('HOST_DEMO_SESSION_FORBIDDEN');
    if (decisionProof && !(/\/decision$|\/payment-approval$/.test(url.pathname))) fail('HOST_PROOF_SCOPE_INVALID');
    const controller = new AbortController();
    let rejectDeadline;
    const deadline = new Promise((_, reject) => { rejectDeadline = reject; });
    deadline.catch(() => {});
    const bounded = operation => Promise.race([operation, deadline]);
    const timer = setTimeout(() => { controller.abort(); rejectDeadline(new BridgeError('HTTP_DEADLINE', true)); }, timeoutMs);
    let reader;
    const fetchJson = async (target, token, payload, key, proof) => {
      const response = await bounded(fetchImpl(target, { method: payload === undefined ? 'GET' : 'POST',
        redirect: 'error', signal: controller.signal, headers: { Accept: 'application/json',
          ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }),
          ...(token ? { Authorization: 'Bearer ' + token } : {}),
          ...(key ? { 'Idempotency-Key': key } : {}),
          ...(proof ? { 'X-Buyer-Decision-Proof': proof } : {}) },
        body: payload === undefined ? undefined : JSON.stringify(payload) }));
      if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')) fail('INVALID_HTTP_RESPONSE');
      if (Number(response.headers.get('content-length') ?? 0) > 524288 || !response.body) fail('HTTP_RESPONSE_TOO_LARGE');
      reader = response.body.getReader();
      let bytes = 0; const chunks = [];
      while (true) {
        const part = await bounded(reader.read()); if (part.done) break;
        bytes += part.value.byteLength;
        if (bytes > 524288) fail('HTTP_RESPONSE_TOO_LARGE');
        chunks.push(Buffer.from(part.value));
      }
      let data;
      try { data = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail('INVALID_HTTP_RESPONSE'); }
      if (!data || typeof data !== 'object' || Array.isArray(data)) fail('INVALID_HTTP_RESPONSE');
      if (!response.ok) {
        const code = data.error?.code;
        fail(typeof code === 'string' && /^[A-Z0-9_]{1,80}$/.test(code) ? code : 'HTTP_REFUSED',
          [408, 429, 503, 504].includes(response.status) || data.error?.details?.retryable === true);
      }
      return data;
    };
    try {
      const token = hostAuthenticated ? hostToken(await bounded(Promise.resolve().then(hostAccessToken))) :
        authenticated ? await bounded(session()) : null;
      if (hostAuthenticated) {
        // Check the exact credential used for this request before any workflow effect.
        // A refreshed credential from another owner cannot redirect persisted intent.
        const identity = await fetchJson(new URL('/api/identity/me', base), token);
        bindIdentity(identity);
        if (url.pathname === '/api/identity/me' && body === undefined) return identity;
      }
      return await fetchJson(url, token, body, commandKey, decisionProof);
    } catch (error) {
      if (error instanceof BridgeError) throw error;
      fail(controller.signal.aborted ? 'HTTP_DEADLINE' : 'HTTP_UNAVAILABLE', true);
    } finally { clearTimeout(timer); controller.abort(); reader?.cancel().catch(() => {}); }
  };
  const session = async () => {
    if (hostAuthenticated) return null;
    const existing = read().token; if (existing) return existing;
    const result = await request('/api/demo/session', { buyerId: BUYER }, null, false);
    if (typeof result.token !== 'string' || !/^[0-9a-f-]{36}$/.test(result.token) || result.buyerId !== BUYER ||
        result.mode !== 'SYNTHETIC_NOT_AUTHENTICATED') fail('INVALID_DEMO_SESSION');
    return update(state => { state.token ??= result.token; return state.token; });
  };
  const command = (key, kind, args) => update(state => {
    const fp = fingerprint([kind, args]); const prior = entries(state, 'commands').get(key);
    if (prior && prior.fingerprint !== fp) fail('CLIENT_COMMAND_CONFLICT');
    const record = prior ?? { kind, fingerprint: fp, nonce: randomUUID(), issuedAtMs: Date.now() };
    put(state, 'commands', key, record); return clone(record);
  });
  const runRecord = id => { const saved = entries(read(), 'runs').get(id); if (!saved) fail('CALLER_INTENT_MISSING'); return clone(saved); };
  const status = async (id, full = false) => {
    if (!safeId(id)) fail('INVALID_RUN_ID');
    const result = await request('/api/agent/runs/' + encodeURIComponent(id) + (full ? '?detail=full' : ''));
    if (result.mode !== 'SYNTHETIC' || result.run?.id !== id) fail('INVALID_RUN_RESPONSE');
    return result;
  };
  const terms = full => {
    if (['QUOTE_STALE', 'QUOTE_EXPIRED'].includes(full.run.status)) fail(full.run.status);
    const saved = runRecord(full.run.id), q = full.quote;
    if (!q || !full.policy || q.buyerId !== BUYER || q.id !== full.run.quoteId) fail('QUOTE_NOT_AVAILABLE');
    let ceiling = saved.budgetCents;
    const exception = q.budgetException;
    if (exception && q.totalCents > ceiling) {
      if (exception.scope !== 'THIS_QUOTE_ONLY' || exception.originalBudgetCents !== ceiling ||
          exception.proposedBudgetCents !== q.totalCents || exception.additionalCents !== q.totalCents - ceiling) fail('UNBOUND_BUDGET_EXCEPTION');
      ceiling = q.totalCents;
    }
    try { verifyBuyerTerms(q, full.policy, { requirements: saved.requirements, budgetCents: ceiling }); }
    catch { fail('BUYER_TERMS_REFUSED'); }
    return { q, saved, ceiling, binding: fingerprint([q.id, q.snapshotId, q.totalCents, q.expiresAtMs, full.run.id]) };
  };
  const registerKey = async key => {
    await session();
    const state = read();
    const expected = 'demo-buyer-' + createHash('sha256').update(state.publicJwk.x).digest('hex').slice(0, 16);
    if (state.kid === expected) return expected;
    const result = await request('/api/trust/buyer-key', { buyerId: BUYER, publicJwk: state.publicJwk }, phaseKey(key, 'register'));
    if (result.kid !== expected) fail('BUYER_KEY_MISMATCH');
    update(s => { s.kid = result.kid; }); return expected;
  };
  const verifyEnvelope = (envelope, kid, keys) => {
    const jwk = keys.find(k => k.kid === kid);
    if (!jwk || envelope?.protected?.kid !== kid || envelope.protected.alg !== 'EdDSA' ||
        envelope.protected.typ !== 'kattely.demo.procurement-envelope.v1' || typeof envelope.signature !== 'string') fail('PROOF_REFUSED');
    try {
      if (!verify(null, Buffer.from(canonical(envelope.protected) + '.' + canonical(envelope.payload)),
        createPublicKey({ key: jwk, format: 'jwk' }), Buffer.from(envelope.signature, 'base64url'))) fail('PROOF_REFUSED');
    } catch { fail('PROOF_REFUSED'); }
  };
  const decisionEvidence = async (commandKey, context) => {
    if (!hostAuthenticated || typeof hostDecisionProof !== 'function') fail('HOST_DECISION_REQUIRED');
    context = { ...context, buyerId: BUYER, ...read().authBinding };
    const cacheKey = fingerprint([commandKey, context]);
    const now = Date.now();
    for (const [key, entry] of hostProofs) if (entry.until <= now) hostProofs.delete(key);
    const existing = hostProofs.get(cacheKey);
    if (existing) return { proof: existing.proof, decision: existing.decision, cacheKey };
    if (hostProofs.size >= 1000) fail('CLIENT_STATE_CAPACITY');
    let timer;
    try {
      const supplied = await Promise.race([Promise.resolve().then(() => hostDecisionProof(clone(context))),
        new Promise((_, reject) => { timer = setTimeout(() => reject(new BridgeError('HOST_DECISION_REQUIRED')), timeoutMs); })]);
      const object = supplied && typeof supplied === 'object' && !Array.isArray(supplied);
      if (object && (Object.keys(supplied).some(key => !['proof', 'decision'].includes(key)) ||
          !['approve', 'reject'].includes(supplied.decision))) fail('HOST_DECISION_REQUIRED');
      const proof = hostToken(object ? supplied.proof : supplied);
      let decision = object ? supplied.decision : context.decision;
      let until = now + 300000;
      // Selection/cache minimization only: this decode never verifies identity or grants consent.
      // The server must verify the signature and bind this exact decision and scope.
      try {
        const payload = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(proof.split('.')[1], 'base64url')));
        if (!object && ['approve', 'reject'].includes(payload?.decision)) decision = payload.decision;
        if (Number.isSafeInteger(payload?.exp) && payload.exp >= 0 && payload.exp <= Math.floor(Number.MAX_SAFE_INTEGER / 1000)) {
          until = Math.min(until, payload.exp * 1000); // Unverified metadata may shorten retention, never extend it.
        }
      } catch { /* Old test transports may supply opaque, non-JSON marker payloads. */ }
      if (until > Date.now()) hostProofs.set(cacheKey, { proof, decision, until });
      return { proof, decision, cacheKey };
    } catch { fail('HOST_DECISION_REQUIRED'); } finally { clearTimeout(timer); }
  };
  if (hostAuthenticated) {
    try { await request('/api/identity/me', undefined, null, false); }
    catch (error) { store?.close(); throw error; }
  }
  return Object.freeze({
    lifetime, hostAuthenticated,
    async search(query, limit) { return request('/api/products/search?q=' + encodeURIComponent(query) + '&limit=' + limit); },
    async lookupValioMock(input) {
      try { return await request('/api/suppliers/valio-mock/observe', input, hostAuthenticated ? phaseKey(fingerprint(input), 'mock-observation') : undefined); }
      catch (error) { if (error.code === 'INTEGRATION_NOT_CONFIGURED') error.retryable = false; throw error; }
    },
    async prepare(args) {
      const { commandKey, ...intention } = args;
      command(commandKey, 'prepare', intention);
      const result = await request('/api/agent/prepare', { buyerId: BUYER, ...intention }, phaseKey(commandKey, 'prepare'));
      if (result.mode !== 'SYNTHETIC' || !safeId(result.run?.id)) fail('INVALID_RUN_RESPONSE');
      const existed = update(state => {
        const saved = entries(state, 'runs').get(result.run.id);
        if (saved) {
          if (fingerprint([saved.requirements, saved.budgetCents]) !== fingerprint([intention.requirements, intention.budgetCents])) fail('CLIENT_COMMAND_CONFLICT');
          return true;
        }
        put(state, 'runs', result.run.id, { ...clone(intention), acceptedScope: null });
        return false;
      });
      return !result.quote ? status(result.run.id, true) : existed ? status(result.run.id) : result;
    },
    status,
    async reviewContext(id) {
      const full = await status(id, true); const checked = terms(full);
      // Reading an approved quote grants nothing. A missing caller scope is
      // reconciled through the original keyed decision; decide still requires
      // its prior local authorization or a fresh exact host-signed proof.
      return { ...checked, full, callerScopeAccepted: checked.q.totalCents <= checked.saved.budgetCents || checked.saved.acceptedScope?.binding === checked.binding };
    },
    challenge(commandKey, kind, id, binding, message, extra = {}) {
      command(commandKey, kind, { id, binding });
      return update(state => {
        const existing = entries(state, 'challenges').get(commandKey);
        if (existing && (existing.kind !== kind || existing.id !== id || existing.binding !== binding)) fail('STALE_CONFIRMATION');
        const challenge = existing ?? { kind, id, binding, token: randomUUID(), issuedAtMs: Date.now(), message, ...extra };
        put(state, 'challenges', commandKey, challenge); return clone(challenge);
      });
    },
    checkChallenge(commandKey, token, binding) {
      const record = entries(read(), 'challenges').get(commandKey);
      if (!record || record.token !== token || record.binding !== binding || Date.now() - record.issuedAtMs > 300000) fail('STALE_CONFIRMATION');
      return clone(record);
    },
    authorizeChallenge(commandKey, token, binding, decision) {
      this.checkChallenge(commandKey, token, binding);
      if (!['approve', 'reject'].includes(decision)) fail('INVALID_DECISION');
      update(state => {
        const record = entries(state, 'challenges').get(commandKey);
        if (record.authorization && record.authorization.decision !== decision) fail('CONFIRMATION_FINAL');
        record.authorization ??= { decision, at: Date.now() };
        put(state, 'challenges', commandKey, record);
      });
    },
    async decide(id, commandKey, decision, binding) {
      const full = await status(id, true), checked = terms(full);
      if (checked.binding !== binding) fail('STALE_CONFIRMATION');
      if (!['approve', 'reject'].includes(decision)) fail('INVALID_DECISION');
      let evidence;
      if (hostAuthenticated) {
        command(commandKey, 'review', { id, binding, decision });
        const exported = await request('/api/quotes/' + encodeURIComponent(checked.q.id) + '/body');
        try { verifyBuyerBody(exported.body, checked.q); } catch { fail('BUYER_BODY_REFUSED'); }
        evidence = await decisionEvidence(commandKey, { action: 'QUOTE_DECISION', decision, runId: id,
          quoteId: checked.q.id, snapshotId: checked.q.snapshotId, totalCents: checked.q.totalCents,
          quoteBodyDigest: digest(exported.body) });
      } else {
        const authorization = entries(read(), 'challenges').get(commandKey)?.authorization;
        if (authorization?.decision !== decision) fail('HUMAN_APPROVAL_REQUIRED');
      }
      const actualDecision = evidence?.decision ?? decision;
      const accepted = await request('/api/agent/runs/' + encodeURIComponent(id) + '/decision',
        { buyerId: BUYER, decision: actualDecision, quoteId: checked.q.id, snapshotId: checked.q.snapshotId }, phaseKey(commandKey, 'decision'), true, evidence?.proof);
      if (evidence) hostProofs.delete(evidence.cacheKey); // Successful ACK: do not retain raw proof.
      if (actualDecision === 'approve') update(state => {
        const saved = entries(state, 'runs').get(id);
        put(state, 'runs', id, { ...saved, acceptedScope: { binding, quoteId: checked.q.id, budgetCents: checked.ceiling } });
      });
      return accepted;
    },
    async commit(id, commandKey) {
      command(commandKey, 'commit', { id });
      const full = await status(id, true);
      if (full.run.orderId) return status(id);
      const { q, saved, binding } = terms(full);
      if (q.totalCents > saved.budgetCents && saved.acceptedScope?.binding !== binding) fail('CALLER_APPROVAL_MISSING');
      if (!['APPROVED', 'AUTO_COMMIT_ELIGIBLE'].includes(q.status)) fail('HUMAN_APPROVAL_REQUIRED');
      const kid = await registerKey(commandKey);
      const exported = await request('/api/quotes/' + encodeURIComponent(q.id) + '/body');
      try { verifyBuyerBody(exported.body, q); } catch { fail('BUYER_BODY_REFUSED'); }
      const { signedOffer } = await request('/api/quotes/' + encodeURIComponent(q.id) + '/offer',
        { buyerId: BUYER }, phaseKey(commandKey, 'offer'));
      const keys = (await request('/.well-known/trusted-trade/jwks.json')).keys;
      verifyEnvelope(signedOffer, signedOffer?.protected?.kid, keys);
      if (signedOffer.payload.quoteBodyDigest !== digest(exported.body) || signedOffer.payload.quoteId !== q.id ||
          signedOffer.payload.totalCents !== q.totalCents || signedOffer.payload.buyerId !== BUYER ||
          signedOffer.payload.audience !== 'https://supplier-demo.invalid') fail('PROOF_REFUSED');
      let proof = full.proof;
      if (!proof) {
        const recorded = command(commandKey + ':mandate', 'mandate', { id, quoteId: q.id });
        const signedMandate = signDemoEnvelope(createPrivateKey({ key: Buffer.from(read().privateKey, 'base64'), type: 'pkcs8', format: 'der' }),
          kid, makeDemoMandatePayload({ quote: q, signedOffer, now: recorded.issuedAtMs, nonce: recorded.nonce }));
        proof = (await request('/api/quotes/' + encodeURIComponent(q.id) + '/handshake',
          { buyerId: BUYER, signedMandate }, phaseKey(commandKey, 'handshake'))).proof;
      }
      const refreshedKeys = keys;
      verifyEnvelope(proof?.signedOffer, signedOffer.protected.kid, refreshedKeys);
      verifyEnvelope(proof?.signedMandate, kid, refreshedKeys);
      const mandate = proof.signedMandate.payload, offer = proof.signedOffer.payload, now = Date.now();
      if (offer.quoteId !== q.id || offer.buyerId !== BUYER || offer.totalCents !== q.totalCents ||
          offer.audience !== 'https://supplier-demo.invalid' ||
          offer.quoteBodyDigest !== digest(exported.body) || mandate.signedOfferDigest !== digest(proof.signedOffer) ||
          mandate.quoteId !== q.id || mandate.buyerId !== BUYER || mandate.maxTotalCents !== q.totalCents ||
          mandate.audience !== offer.audience || mandate.allowedAction !== 'CREATE_ONE_SIMULATED_ORDER' ||
          mandate.approval !== (q.approvalRequired ? 'SYNTHETIC_RECORDED_REVIEW' : 'WITHIN_DEMO_POLICY') ||
          !/^[0-9a-f-]{36}$/.test(mandate.nonce) ||
          ![q.createdAtMs, q.expiresAtMs, offer.issuedAtMs, offer.expiresAtMs, mandate.issuedAtMs, mandate.expiresAtMs].every(value => Number.isSafeInteger(value) && value >= 0) ||
          q.createdAtMs >= q.expiresAtMs || offer.issuedAtMs >= offer.expiresAtMs || mandate.issuedAtMs >= mandate.expiresAtMs ||
          offer.issuedAtMs < q.createdAtMs || mandate.issuedAtMs < offer.issuedAtMs || mandate.issuedAtMs > now ||
          now >= q.expiresAtMs || now >= offer.expiresAtMs || now >= mandate.expiresAtMs ||
          offer.expiresAtMs > q.expiresAtMs || mandate.expiresAtMs > offer.expiresAtMs) fail('PROOF_REFUSED');
      return request('/api/agent/runs/' + encodeURIComponent(id) + '/commit',
        { buyerId: BUYER, idempotencyKey: phaseKey(commandKey, 'order') }, phaseKey(commandKey, 'commit'));
    },
    async cancel(id, commandKey) {
      runRecord(id); command(commandKey, 'cancel', { id });
      return request('/api/agent/runs/' + encodeURIComponent(id) + '/cancel', { buyerId: BUYER }, phaseKey(commandKey, 'cancel'));
    },
    async paymentContext(id) {
      const full = await status(id, true), { q, saved, binding } = terms(full);
      if (!full.run.orderId) fail('ORDER_REQUIRED');
      if (q.totalCents > saved.budgetCents && saved.acceptedScope?.binding !== binding) fail('CALLER_APPROVAL_MISSING');
      const pay = await request('/api/orders/' + encodeURIComponent(full.run.orderId) + '/payment');
      const proposal = pay.proposal;
      const allocated = new Map();
      for (const line of q.lines) allocated.set(line.supplierId, (allocated.get(line.supplierId) ?? 0) + line.totalCents);
      for (const [field, account] of [['deliveryFeeCents', 'fictional-delivery-fee'], ['taxCents', 'fictional-tax-holding']]) {
        if (q.costBreakdown[field]) allocated.set(account, q.costBreakdown[field]);
      }
      const expected = [...allocated].sort(([a], [b]) => a.localeCompare(b));
      if (proposal?.orderId !== full.run.orderId || proposal.amountCents !== q.totalCents || proposal.currency !== 'EUR' ||
          proposal.signedQuoteBodyDigest !== digest((await request('/api/quotes/' + encodeURIComponent(q.id) + '/body')).body) ||
          JSON.stringify(proposal.allocations.map(a => [a.supplierId, a.amountCents]).sort(([a], [b]) => a.localeCompare(b))) !== JSON.stringify(expected)) fail('PAYMENT_TERMS_REFUSED');
      const { digest: claimed, ...unsigned } = proposal;
      if (claimed !== digest(unsigned)) fail('PAYMENT_TERMS_REFUSED');
      return { full, pay, binding: fingerprint([id, proposal.digest]), message: 'Approve a separate SYNTHETIC payment of ' +
        proposal.amountCents + ' EUR cents for order ' + full.run.orderId + '? No bank or supplier is connected.' };
    },
    async settle(id, commandKey, binding, proposalDigest) {
      const context = await this.paymentContext(id);
      if (context.binding !== binding || context.pay.proposal.digest !== proposalDigest) fail('STALE_CONFIRMATION');
      if (context.pay.transfer) return status(id);
      let evidence;
      const orderId = context.full.run.orderId;
      if (hostAuthenticated) {
        command(commandKey, 'payment', { id, binding, proposalDigest });
        const q = context.full.quote;
        evidence = await decisionEvidence(commandKey, { action: 'PAYMENT_DECISION', decision: 'approve', runId: id,
          quoteId: q.id, snapshotId: q.snapshotId, totalCents: q.totalCents,
          quoteBodyDigest: context.pay.proposal.signedQuoteBodyDigest, orderId, paymentProposalDigest: proposalDigest });
      } else if (entries(read(), 'challenges').get(commandKey)?.authorization?.decision !== 'approve') fail('HUMAN_APPROVAL_REQUIRED');
      const actualDecision = evidence?.decision ?? 'approve';
      await request('/api/orders/' + encodeURIComponent(orderId) + '/payment-approval',
        { buyerId: BUYER, decision: actualDecision, proposalDigest }, phaseKey(commandKey, 'payment-approval'), true, evidence?.proof);
      if (evidence) hostProofs.delete(evidence.cacheKey);
      if (actualDecision !== 'approve') return { ...await status(id), paymentApproval: 'REJECTED' };
      await request('/api/orders/' + encodeURIComponent(orderId) + '/settlement',
        { buyerId: BUYER, idempotencyKey: phaseKey(commandKey, 'transfer') }, phaseKey(commandKey, 'payment'));
      return status(id);
    },
    close() { hostProofs.clear(); store?.close(); },
  });
}
