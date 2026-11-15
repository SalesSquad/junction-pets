import { randomUUID, createHash } from 'node:crypto';
import { metadata, openapi } from './contract.mjs';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { readFile } from 'node:fs/promises';
import { createTradeService, TradeError, unsignedQuoteBody } from './core.mjs';
import { createDemoTrustRegistry, TrustFault } from './trust-envelope.mjs';
import { recognizeImage, ScanFault } from './scanning.mjs';
import { createFixtureCatalogSearch, RetrievalFault } from './catalog-retrieval.mjs';

import { createAgentApi } from './agent-api.mjs';
import { createHttpContext, createTradeRuntime } from './trade-runtime.mjs';
import { createValioMockPort, isValioProductId } from './valio-mock-port.mjs';
import { StateStoreError } from './local-state-store.mjs';
import { catalogPage, auditPage, onlyQuery, recoveryFor } from './api-navigation.mjs';

const currentDir = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(currentDir, '../public');
const publicFiles = Object.freeze({
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/mission': ['mission.html', 'text/html; charset=utf-8'],
  '/classic': ['index.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/style.css': ['style.css', 'text/css; charset=utf-8'],
  '/mission.js': ['mission.js', 'text/javascript; charset=utf-8'],
  '/browser-session.js': ['browser-session.js', 'text/javascript; charset=utf-8'],
  '/mission.css': ['mission.css', 'text/css; charset=utf-8'],
});

const hash = value => createHash('sha256').update(value).digest('hex');
const bearerKey = request => {
  const raw = request.headers.authorization?.match(/^Bearer ([A-Za-z0-9_-]{10,128})$/)?.[1];
  return raw ? hash(raw) : null;
};
const canonicalInput = value => Array.isArray(value) ? '[' + value.map(canonicalInput).join(',') + ']' :
  value && typeof value === 'object' ? '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonicalInput(value[key])).join(',') + '}' : JSON.stringify(value);

const readBytes = (request, { maxBytes, timeoutMs, label }) => new Promise((resolve, reject) => {
  const chunks = [];
  let bytes = 0, finished = false;
  const finish = error => {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    request.off('data', data); request.off('end', end); request.off('aborted', abort); request.off('error', abort);
    if (error) { request.pause(); reject(error); } else resolve(Buffer.concat(chunks));
  };
  const data = chunk => {
    bytes += chunk.length;
    if (bytes > maxBytes) return finish(new TradeError('PAYLOAD_TOO_LARGE', label + ' exceeds its byte limit.', 413));
    chunks.push(chunk);
  };
  const end = () => finish();
  const abort = () => finish(new TradeError('UPLOAD_ABORTED', label + ' was interrupted.', 400));
  const timer = setTimeout(() => finish(new TradeError('UPLOAD_TIMEOUT', label + ' exceeded its wall-clock deadline.', 408)), timeoutMs);
  request.on('data', data); request.once('end', end); request.once('aborted', abort); request.once('error', abort);
});
const readRequest = async (request, timeoutMs) => {
  if (request.headers['content-type'] && !/^application\/json(?:\s*;|$)/i.test(request.headers['content-type'])) {
    throw new TradeError('UNSUPPORTED_MEDIA_TYPE', 'Use application/json for typed commands.', 415);
  }
  const bytes = await readBytes(request, { maxBytes: 16384, timeoutMs, label: 'JSON request' });
  if (!bytes.length) return {};
  try {
    const value = JSON.parse(bytes.toString('utf8'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error();
    return value;
  } catch { throw new TradeError('INVALID_JSON', 'Send a JSON object, not executable instructions.'); }
};
const headers = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" };

export function createTradeHttpServer(initialService = createTradeService(), {
  runtime = null, catalogSearch, valioMockPort = null, imageUploadTimeoutMs = 5000, jsonUploadTimeoutMs = 5000,
  afterCommitBeforeRespond,
} = {}) {
  for (const timeout of [imageUploadTimeoutMs, jsonUploadTimeoutMs]) {
    if (!Number.isSafeInteger(timeout) || timeout < 1 || timeout > 30000) throw new TypeError('Invalid upload deadline');
  }
  const service = runtime?.service ?? initialService;
  const context = runtime?.context ?? createHttpContext();
  const { sessions, quoteOwners, planOwners, orderOwners, reviewOwners, requestReplay } = context;
  const trust = runtime?.trust ?? createDemoTrustRegistry();
  const execute = (write, action) => runtime ? runtime.execute(write, action) : action();
  const requireSession = session => {
    if (!session || !sessions.has(session)) throw new TradeError('BUYER_CAPABILITY_REQUIRED', 'Resume the original synthetic session or explicitly create a new workflow session.', 403);
  };
  const search = catalogSearch ?? createFixtureCatalogSearch(() => execute(false, () => service.catalog()));
  const agent = createAgentApi({ service, trust, context });
  let ocrRunning = false;
  const send = (status, body) => ({ status, body });
  const dispatch = (request, url) => {
    if (request.method === 'GET' && url.pathname === '/.well-known/trusted-trade') return send(200, metadata);
    if (request.method === 'GET' && url.pathname === '/.well-known/trusted-trade/jwks.json') return send(200, trust.publicKeys());
    if (request.method === 'GET' && url.pathname === '/openapi.json') return send(200, openapi);
    if (request.method === 'GET' && url.pathname === '/api/integrations/status') return send(200, {
      mode: 'SYNTHETIC_WORKFLOWS', storage: runtime?.storage ?? 'EPHEMERAL_MEMORY',
      valioMock: { configured: Boolean(valioMockPort), authenticated: 'NOT_PROBED_BY_STATUS', schema: 'https://junction26.valioaimo.fi/openapi.json', scope: 'SPONSOR_MOCK_READ_ONLY', orderEndpoint: false },
      purchasingSource: 'INVENTED_FIXTURE_ONLY', catalogSearch: catalogSearch ? 'INJECTED_ADVISORY_ADAPTER' : 'FIXTURE_LEXICAL_NO_EMBEDDINGS',
    });
    if (request.method === 'GET' && url.pathname === '/api/demo/session') {
      const session = bearerKey(request); requireSession(session);
      return send(200, { buyerId: sessions.get(session), mode: 'SYNTHETIC', storage: runtime?.storage ?? 'EPHEMERAL_MEMORY' });
    }
    const proofRead = url.pathname.match(/^\/api\/quotes\/([^/]+)\/proof$/);
    if (request.method === 'GET' && proofRead) {
      const session = bearerKey(request); requireSession(session);
      if (quoteOwners.get(proofRead[1]) !== session) throw new TradeError('BUYER_MISMATCH', 'Proof belongs to the quoting demo session.', 403);
      const current = service.quote(proofRead[1]);
      let freshness = { valid: true, code: null };
      if (!current.orderId) {
        try { service.assertQuoteFresh(current.id); }
        catch (error) {
          if (!['QUOTE_STALE','QUOTE_EXPIRED'].includes(error.code)) throw error;
          freshness = { valid: false, code: error.code };
        }
      }
      return send(200, { proof: trust.findHandshake(proofRead[1]), freshness });
    }
      let token;
      if (request.method === 'POST') {
        const payload = request.demoPayload;
        if (url.pathname === '/api/demo/session') {
          if (Object.keys(payload).some((key) => key !== 'buyerId') || payload.buyerId !== service.policy().buyerId) throw new TradeError('BUYER_MISMATCH', 'Only the explicitly synthetic buyer is available.', 403);
          if (sessions.size >= 512) throw new TradeError('SESSION_CAPACITY', 'Reuse an existing demo session; this bounded executor is at capacity.', 429);
          const rawToken = randomUUID();
          sessions.set(hash(rawToken), payload.buyerId);
          return send(201, { token: rawToken, buyerId: payload.buyerId, mode: 'SYNTHETIC_NOT_AUTHENTICATED' });
        }
        token = bearerKey(request);
        if (!sessions.has(token)) throw new TradeError('BUYER_CAPABILITY_REQUIRED', 'Obtain an ephemeral synthetic session first.', 403);
        if (payload.buyerId !== undefined && payload.buyerId !== sessions.get(token)) throw new TradeError('BUYER_MISMATCH', 'Capability does not match buyer.', 403);
        const boundQuote = url.pathname.match(/^\/api\/quotes\/([^/]+)\/(?:approval|offer|handshake)$/)?.[1] ?? payload.quoteId;
        const boundPlan = url.pathname.match(/^\/api\/plans\/([^/]+)\/(?:quotes|recover)$/)?.[1];
        const boundOrder = url.pathname.match(/^\/api\/orders\/([^/]+)\/(?:cancel|payment-approval|settlement|scan)$/)?.[1];
        if ((boundQuote && quoteOwners.get(boundQuote) !== token) || (boundOrder && orderOwners.get(boundOrder) !== token) ||
            (boundPlan && planOwners.get(boundPlan) !== token)) throw new TradeError('BUYER_MISMATCH', 'This demo session does not own these terms.', 403);
        const boundReview = url.pathname.match(/^\/api\/reviews\/([^/]+)\/decision$/)?.[1];
        if (boundReview && reviewOwners.get(boundReview) !== token) throw new TradeError('BUYER_MISMATCH', 'This demo session does not own this review.', 403);
        request.demoPayload = payload;
      }

      if (request.method === 'GET' && url.pathname === '/api/health') return send(200, { status: 'ok', mode: 'SIMULATED', provider: 'invented-local-catalog', storage: runtime?.storage ?? 'EPHEMERAL_MEMORY' });
      if (request.method === 'GET' && url.pathname === '/api/catalog') {
        return send(200, catalogPage(service.catalog(), url.searchParams));
      }
      if (request.method === 'GET' && url.pathname === '/api/scan/resolve') {
        return send(200, { product: service.resolveProductScan(url.searchParams.get('gtin')) });
      }
      if (request.method === 'GET' && url.pathname === '/api/policy') return send(200, service.policy());
      if (request.method === 'GET' && ['/api/demo/wallet', '/api/demo/ledger/verify', '/api/demo/ledger'].includes(url.pathname)) {
        const buyerToken = bearerKey(request);
        if (!sessions.has(buyerToken)) throw new TradeError('BUYER_CAPABILITY_REQUIRED', 'Synthetic wallet requires a demo buyer session.', 403);
        if (url.pathname === '/api/demo/wallet') return send(200, { wallet: service.demoWallet(), scope: 'SHARED_PUBLIC_SINGLE_BUYER_FIXTURE' });
        if (url.pathname === '/api/demo/ledger/verify') return send(200, { ...service.paymentJournalVerify(), scope: 'SHARED_PUBLIC_SINGLE_BUYER_FIXTURE' });
        return send(200, { ...auditPage(service.paymentJournal(), url.searchParams, 'entries'), mode: 'SYNTHETIC', scope: 'SHARED_PUBLIC_SINGLE_BUYER_FIXTURE' });
      }
      if (request.method === 'GET' && url.pathname === '/api/audit') return send(200, auditPage(service.audit(), url.searchParams));
      if (request.method === 'GET' && url.pathname === '/api/audit/verify') return send(200, service.auditVerify());
      if (request.method === 'POST' && url.pathname === '/api/agent/prepare') {
        if (!request.headers['idempotency-key']) throw new TradeError('IDEMPOTENCY_KEY_REQUIRED', 'Workflow creation requires a stable Idempotency-Key.');
        return send(201, agent.prepare(request.demoPayload, token));
      }
      const runRoute = url.pathname.match(/^\/api\/agent\/runs\/([^/]+)(?:\/(decision|commit|cancel))?$/);
      if (runRoute) {
        const session = bearerKey(request);
        requireSession(session);
        if (request.method === 'GET' && !runRoute[2]) {
          onlyQuery(url.searchParams, ['detail']);
          const detail = url.searchParams.get('detail');
          if (detail !== null && detail !== 'full') throw new TradeError('INVALID_QUERY', 'detail must be full or omitted.');
          return send(200, agent.status(runRoute[1], session, detail === 'full'));
        }
        if (request.method === 'POST' && ['decision', 'commit', 'cancel'].includes(runRoute[2])) {
          return send(200, agent[runRoute[2] === 'decision' ? 'decide' : runRoute[2]](runRoute[1], request.demoPayload, session));
        }
      }
      if (request.method === 'POST' && url.pathname === '/api/trust/buyer-key') {
        if (Object.keys(request.demoPayload).some((key) => !['buyerId', 'publicJwk'].includes(key)) || request.demoPayload.buyerId !== sessions.get(token)) {
          throw new TradeError('BUYER_MISMATCH', 'Public demo key must be bound to the current buyer capability.', 403);
        }
        try { return send(201, trust.registerBuyerKey(token, request.demoPayload.publicJwk)); }
        catch (error) { if (error instanceof TrustFault) throw new TradeError(error.code, error.message, 400); throw error; }
      }
      if (request.method === 'POST' && url.pathname === '/api/plans') {
        const plan = service.planBasket(request.demoPayload);
        planOwners.set(plan.id, token);
        return send(201, { plan });
      }
      const planQuote = url.pathname.match(/^\/api\/plans\/([^/]+)\/quotes$/);
      if (request.method === 'POST' && planQuote) {
        const quote = service.quoteBasketPlan({ ...request.demoPayload, planId: planQuote[1] });
        quoteOwners.set(quote.id, token);
        return send(201, { quote });
      }
      const recover = url.pathname.match(/^\/api\/plans\/([^/]+)\/recover$/);
      if (request.method === 'POST' && recover) {
        const plan = service.recoverPlan({ ...request.demoPayload, planId: recover[1] });
        planOwners.set(plan.id, token);
        return send(201, { plan });
      }
      if (request.method === 'POST' && url.pathname === '/api/quotes') {
        if (Object.keys(request.demoPayload).some((key) => !['buyerId', 'requestText', 'need', 'budgetCents'].includes(key))) throw new TradeError('INVALID_REQUEST', 'Quote terms contain unsupported fields.');
        const quote = service.requestQuote(request.demoPayload);
        quoteOwners.set(quote.id, token);
        return send(201, { quote });
      }
      if (request.method === 'POST' && url.pathname === '/api/reviews') {
        if (Object.keys(request.demoPayload).some((key) => !['buyerId', 'requestText', 'need', 'budgetCents'].includes(key))) throw new TradeError('INVALID_REQUEST', 'Review request contains unsupported fields.');
        const result = service.requestReview(request.demoPayload);
        reviewOwners.set(result.review.id, token);
        if (result.quote) quoteOwners.set(result.quote.id, token);
        return send(201, result);
      }
      const reviewDecision = url.pathname.match(/^\/api\/reviews\/([^/]+)\/decision$/);
      if (request.method === 'POST' && reviewDecision) {
        if (Object.keys(request.demoPayload).some((key) => !['buyerId', 'decision', 'snapshotId', 'quoteId'].includes(key))) throw new TradeError('INVALID_REVIEW_DECISION', 'Only the displayed review, quote and snapshot may be confirmed.');
        return send(200, service.decideReview({ ...request.demoPayload, reviewId: reviewDecision[1] }));
      }
      const bodyExport = url.pathname.match(/^\/api\/quotes\/([^/]+)\/body$/);
      if (request.method === 'GET' && bodyExport) return send(200, { mode: 'SYNTHETIC', signature: 'UNSIGNED', body: unsignedQuoteBody(service.quote(bodyExport[1])) });
      const approval = url.pathname.match(/^\/api\/quotes\/([^/]+)\/approval$/);
      if (request.method === 'POST' && approval) return send(200, { quote: service.approve({ ...request.demoPayload, quoteId: approval[1] }) });
      const offer = url.pathname.match(/^\/api\/quotes\/([^/]+)\/offer$/);
      if (request.method === 'POST' && offer) {
        if (Object.keys(request.demoPayload).some((key) => key !== 'buyerId')) throw new TradeError('ORDER_TERMS_FORBIDDEN', 'Supplier-signed offer accepts only a buyerId.');
        const q = service.quote(offer[1]);
        if (request.demoPayload.buyerId !== q.buyerId) throw new TradeError('BUYER_MISMATCH', 'Quote buyer mismatch.', 403);
        service.assertQuoteFresh(q.id);
        try { return send(201, { signedOffer: trust.signOffer(q, unsignedQuoteBody(q)) }); }
        catch (error) { if (error instanceof TrustFault) throw new TradeError(error.code, error.message, error.code === 'APPROVAL_REQUIRED' ? 403 : 409); throw error; }
      }
      const handshake = url.pathname.match(/^\/api\/quotes\/([^/]+)\/handshake$/);
      if (request.method === 'POST' && handshake) {
        if (Object.keys(request.demoPayload).some((key) => !['buyerId', 'signedMandate'].includes(key))) throw new TradeError('ORDER_TERMS_FORBIDDEN', 'Only buyerId and independent signedMandate may be supplied.');
        const q = service.quote(handshake[1]);
        if (request.demoPayload.buyerId !== q.buyerId) throw new TradeError('BUYER_MISMATCH', 'Handshake buyer is not the quote owner.', 403);
        service.assertQuoteFresh(q.id);
        let proof;
        try { proof = trust.issueHandshake(q, unsignedQuoteBody(q), request.demoPayload.signedMandate, token); }
        catch (error) {
          if (error instanceof TrustFault) throw new TradeError(error.code, error.message, error.code === 'APPROVAL_REQUIRED' ? 403 : 409);
          throw error;
        }
        service.recordVerifiedHandshake({ quoteId: q.id, verification: proof.verification });
        return send(201, { proof });
      }
      const quote = url.pathname.match(/^\/api\/quotes\/([^/]+)$/);
      if (request.method === 'GET' && quote) return send(200, { quote: service.quote(quote[1]) });
      if (request.method === 'POST' && url.pathname === '/api/orders') {
        const current = service.quote(request.demoPayload.quoteId);
        if ((current.planId || current.verifiedHandshake) && !current.orderId) {
          const proof = trust.findHandshake(current.id);
          if (!proof) throw new TradeError('HANDSHAKE_REQUIRED', 'Portfolio commitments need a verified, quote-bound synthetic Kättely mandate.', 403);
          try { trust.verifyHandshake(proof, current, unsignedQuoteBody(current)); }
          catch (error) {
            if (error instanceof TrustFault) throw new TradeError(error.code, error.message, 409);
            throw error;
          }
        }
        const order = service.commitOrder(request.demoPayload);
        orderOwners.set(order.id, token);
        return send(201, { order });
      }
      const cancel = url.pathname.match(/^\/api\/orders\/([^/]+)\/cancel$/);
      if (request.method === 'POST' && cancel) return send(200, { order: service.cancelOrder({ ...request.demoPayload, orderId: cancel[1] }) });
      const paymentApproval = url.pathname.match(/^\/api\/orders\/([^/]+)\/payment-approval$/);
      if (request.method === 'POST' && paymentApproval) return send(200, service.approvePayment({ ...request.demoPayload, orderId: paymentApproval[1] }));
      const settlement = url.pathname.match(/^\/api\/orders\/([^/]+)\/settlement$/);
      if (request.method === 'POST' && settlement) return send(201, service.settlePayment({ ...request.demoPayload, orderId: settlement[1] }));
      const deliveryScan = url.pathname.match(/^\/api\/orders\/([^/]+)\/scan$/);
      if (request.method === 'POST' && deliveryScan) {
        return send(201, { observation: service.scanDelivery({ ...request.demoPayload, orderId: deliveryScan[1] }) });
      }
      const paymentRead = url.pathname.match(/^\/api\/orders\/([^/]+)\/payment$/);
      if (request.method === 'GET' && paymentRead) {
        const buyerToken = bearerKey(request);
        if (!sessions.has(buyerToken) || orderOwners.get(paymentRead[1]) !== buyerToken) {
          throw new TradeError('BUYER_MISMATCH', 'Synthetic settlement details belong to the ordering session.', 403);
        }
        return send(200, service.payment(paymentRead[1], sessions.get(buyerToken)));
      }
      const order = url.pathname.match(/^\/api\/orders\/([^/]+)$/);
      if (request.method === 'GET' && order) return send(200, { order: service.order(order[1]) });
      if (request.method === 'POST' && url.pathname === '/api/demo/reprice') return send(200, { product: service.simulatePriceChange(request.demoPayload) });
      if (request.method === 'POST' && url.pathname === '/api/demo/shock') return send(200, { product: service.simulateStockShock(request.demoPayload) });
      throw new TradeError('NOT_FOUND', 'Unknown demo route.', 404);
  };
  const server = createServer(async (request, response) => {
    let url;
    const requestId = /^[A-Za-z0-9_-]{1,80}$/.test(request.headers['x-request-id'] ?? '') ? request.headers['x-request-id'] : randomUUID();
    const writeReply = reply => {
      if (response.destroyed) return;
      const body = JSON.stringify(reply.body);
      if (Buffer.byteLength(body) > 2097152) throw new TradeError('RESPONSE_TOO_LARGE', 'Use a smaller page or compact workflow response.', 413);
      response.writeHead(reply.status, { ...headers, 'Content-Type': 'application/json; charset=utf-8',
        'X-Request-Id': requestId, ...([408, 413].includes(reply.status) || (reply.status >= 400 && request.method === 'POST') ? { Connection: 'close' } : {}),
        ...(reply.replayed ? { 'Idempotency-Replayed': 'true' } : {}),
        ...(reply.body?.error?.retryAfterMs ? { 'Retry-After': String(Math.ceil(reply.body.error.retryAfterMs / 1000)) } : {}) });
      response.end(body);
    };
    try {
      try { url = new URL(request.url ?? '/', 'http://localhost'); }
      catch { throw new TradeError('INVALID_URL', 'Invalid request target.', 400); }
      if (!/^(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?$/.test(request.headers.host ?? '')) {
        throw new TradeError('HOST_REFUSED', 'This local synthetic executor accepts loopback hosts only.', 403);
      }
      if (request.headers.origin && request.headers.origin !== 'http://' + request.headers.host) throw new TradeError('ORIGIN_REFUSED', 'Cross-origin demo requests forbidden.', 403);
      if (!['GET', 'POST'].includes(request.method)) throw new TradeError('METHOD_NOT_ALLOWED', 'Use a documented GET or POST operation.', 405);
      if (request.method === 'GET' && publicFiles[url.pathname]) {
        const [file, type] = publicFiles[url.pathname];
        const body = await readFile(resolve(publicDir, file));
        if (!response.destroyed) { response.writeHead(200, { ...headers, 'Content-Type': type }); response.end(body); }
        return;
      }
      if (request.method === 'POST' && url.pathname === '/api/scan/ocr') {
        const session = bearerKey(request);
        execute(false, () => requireSession(session));
        const mediaType = request.headers['content-type'];
        if (!['image/jpeg', 'image/png'].includes(mediaType)) throw new TradeError('INVALID_IMAGE', 'Upload a PNG or JPEG only.');
        const buffer = await readBytes(request, { maxBytes: 1500000, timeoutMs: imageUploadTimeoutMs, label: 'Image upload' });
        execute(false, () => requireSession(session));
        if (ocrRunning) throw new TradeError('OCR_BUSY', 'One local OCR request at a time; retry shortly.', 503);
        ocrRunning = true;
        try {
          const observation = await recognizeImage(buffer, mediaType);
          writeReply(send(200, { ...observation, mode: 'LOCAL_TESSERACT_OCR_UNTRUSTED', persistence: 'IMAGE_NOT_STORED', requiresHumanConfirmation: true }));
          return;
        } finally { ocrRunning = false; }
      }
      if (request.method === 'GET' && url.pathname === '/api/products/search') {
        const session = bearerKey(request);
        execute(false, () => requireSession(session));
        onlyQuery(url.searchParams, ['q', 'limit']);
        const limit = url.searchParams.has('limit') ? Number(url.searchParams.get('limit')) : 5;
        if (!Number.isSafeInteger(limit) || limit < 1 || limit > 10) throw new TradeError('INVALID_SEARCH_LIMIT', 'Search limit must be1–10.');
        const result = await search.search({ query: url.searchParams.get('q'),
          buyerId: execute(false, () => sessions.get(session)), limit });
        writeReply(send(200, result)); return;
      }
      if (request.method === 'POST' && url.pathname !== '/api/demo/session') execute(false, () => requireSession(bearerKey(request)));
      request.demoPayload = request.method === 'POST' ? await readRequest(request, jsonUploadTimeoutMs) : {};
      if (request.method === 'POST' && url.pathname === '/api/suppliers/valio-mock/observe') {
        const input = request.demoPayload;
        if (Object.keys(input).some(key => !['products','requestedDate'].includes(key)) ||
            !Array.isArray(input.products) || input.products.length < 1 || input.products.length > 20 ||
            !input.products.every(isValioProductId) ||
            new Set(input.products).size !== input.products.length ||
            typeof input.requestedDate !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(input.requestedDate) ||
            !Number.isFinite(Date.parse(input.requestedDate)) || new Date(input.requestedDate).toISOString().slice(0,10) !== input.requestedDate) {
          throw new TradeError('INVALID_SPONSOR_REQUEST', 'Use narrowed product IDs and a valid date; never send credentials or customer overrides.');
        }
        if (!valioMockPort) throw new TradeError('INTEGRATION_NOT_CONFIGURED', 'The read-only mock adapter needs an operator-managed server credential; local purchasing continues in explicit fixture mode.', 503);
        const observed = await valioMockPort.observe(input);
        writeReply(send(200, observed)); return;
      }
      const reply = execute(request.method === 'POST', () => {
        const key = request.method === 'POST' ? request.headers['idempotency-key'] : undefined;
        let replayKey, fingerprint;
        if (key !== undefined) {
          if (!/^[A-Za-z0-9_-]{10,80}$/.test(key)) throw new TradeError('INVALID_IDEMPOTENCY_KEY', 'Use a stable10–80 character command key.');
          if (url.pathname === '/api/demo/session') throw new TradeError('IDEMPOTENCY_SCOPE_INVALID', 'Session bearer tokens are never cached as replayable command results.');
          const session = bearerKey(request);
          requireSession(session);
          replayKey = session + ':' + key;
          fingerprint = hash(canonicalInput({ method: request.method, path: url.pathname + url.search, body: request.demoPayload }));
          const previous = requestReplay.get(replayKey);
          if (previous) {
            if (previous.fingerprint !== fingerprint) throw new TradeError('IDEMPOTENCY_CONFLICT', 'Command key already belongs to different exact input.', 409);
            return { ...structuredClone(previous.reply), replayed: true };
          }
          if (requestReplay.size >= 5000) throw new TradeError('STATE_CAPACITY', 'The bounded demo command ledger is full.', 429);
        }
        const outcome = dispatch(request, url);
        if (Buffer.byteLength(JSON.stringify(outcome.body)) > 2097152) throw new TradeError('RESPONSE_TOO_LARGE', 'Use bounded pages instead of full history.', 413);
        if (replayKey && outcome.status < 400) requestReplay.set(replayKey, { fingerprint, reply: structuredClone(outcome) });
        return outcome;
      });
      afterCommitBeforeRespond?.(request, reply); // test-only lost-ACK fault seam, no HTTP configuration.
      writeReply(reply);
    } catch (error) {
      let typed = error;
      if (error instanceof ScanFault || error instanceof RetrievalFault || error instanceof TrustFault) {
        typed = new TradeError(error.code, error.message, error.status ?? 409);
      } else if (error instanceof StateStoreError) {
        typed = new TradeError(error.code, error.message, error.retryable ? 503 : error.code === 'STATE_CAPACITY' ? 429 : 503);
      }
      const known = typed instanceof TradeError;
      try { execute(true, () => service.recordRefusal(known ? typed.code : 'INTERNAL_ERROR', url?.pathname ?? '[invalid request target]')); } catch { /* failed state stays fail-closed; never reseed */ }
      writeReply(send(known ? typed.httpStatus : 500, { error: {
        code: known ? typed.code : 'INTERNAL_ERROR', message: known ? typed.message : 'Unexpected demo error.',
        details: known ? typed.details : null, ...recoveryFor(known ? typed.code : 'INTERNAL_ERROR', known ? typed.details : null),
      } }));
    }
  });
  server.requestTimeout = 20000; server.headersTimeout = 5000; server.keepAliveTimeout = 2000;
  server.maxConnections = 64; server.maxHeadersCount = 32; server.maxRequestsPerSocket = 100;
  if (runtime) server.on('close', () => runtime.close());
  return server;
}

export function createPersistentTradeServer(options) {
  const runtime = createTradeRuntime(options);
  return createTradeHttpServer(undefined, { ...options, runtime });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT ?? '4177');
  if (!Number.isSafeInteger(port) || port < 0 || port > 65535) throw new Error('Invalid PORT');
  const stateFile = process.env.VALIO_STATE_FILE ?? resolve(currentDir, '../.runtime/state.sqlite');
  const valioMockPort = process.env.VALIO_MOCK_API_KEY ? createValioMockPort({ customer: 'junction-agent-audit', apiKey: () => process.env.VALIO_MOCK_API_KEY }) : null;
  const server = process.env.VALIO_EPHEMERAL === '1' ? createTradeHttpServer(undefined, { valioMockPort }) : createPersistentTradeServer({ stateFile, valioMockPort });
  server.listen(port, '127.0.0.1', () => process.stdout.write('Trusted Trade local SYNTHETIC executor at http://127.0.0.1:' + server.address().port + '/\n'));
}
