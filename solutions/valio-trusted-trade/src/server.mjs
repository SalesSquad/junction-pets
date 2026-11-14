import { randomUUID } from 'node:crypto';
import { metadata, openapi } from './contract.mjs';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { readFile } from 'node:fs/promises';
import { createTradeService, TradeError, unsignedQuoteBody } from './core.mjs';
import { createDemoTrustRegistry, TrustFault } from './trust-envelope.mjs';
import { recognizeImage, ScanFault } from './scanning.mjs';

const currentDir = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(currentDir, '../public');
const publicFiles = Object.freeze({
  '/': ['mission.html', 'text/html; charset=utf-8'],
  '/classic': ['index.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/style.css': ['style.css', 'text/css; charset=utf-8'],
  '/mission.js': ['mission.js', 'text/javascript; charset=utf-8'],
  '/mission.css': ['mission.css', 'text/css; charset=utf-8'],
});

const readRequest = async (request) => {
  let bytes = 0;
  const chunks = [];
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > 16_384) throw new TradeError('PAYLOAD_TOO_LARGE', 'Request is over the demo limit.', 413);
    chunks.push(chunk);
  }
  if (!bytes) return {};
  try {
    const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Object required');
    return value;
  } catch {
    throw new TradeError('INVALID_JSON', 'Expected one JSON object.');
  }
};

const readImage = async (request) => {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > 1_500_000) throw new TradeError('PAYLOAD_TOO_LARGE', 'Scanned image exceeds 1.5 MB.', 413);
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
};

export function createTradeHttpServer(service = createTradeService()) {
  const sessions = new Map();
  const quoteOwners = new Map();
  const planOwners = new Map();
  const orderOwners = new Map();
  const trust = createDemoTrustRegistry();
  let ocrRunning = false;
  return createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', 'http://localhost');
    const send = (status, body) => {
      response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" });
      response.end(JSON.stringify(body));
    };
    try {
      if (request.headers.origin && request.headers.origin !== `http://${request.headers.host}`) throw new TradeError('ORIGIN_REFUSED', 'Cross-origin demo writes forbidden.', 403);
      if (request.method === 'GET' && url.pathname === '/.well-known/trusted-trade') return send(200, metadata);
      if (request.method === 'GET' && url.pathname === '/.well-known/trusted-trade/jwks.json') return send(200, trust.publicKeys());
      if (request.method === 'GET' && url.pathname === '/openapi.json') return send(200, openapi);
      if (request.method === 'POST' && url.pathname === '/api/scan/ocr') {
        const buyerToken = request.headers.authorization?.replace(/^Bearer /, '');
        if (!sessions.has(buyerToken)) throw new TradeError('BUYER_CAPABILITY_REQUIRED', 'Scanning requires a synthetic demo session.', 403);
        if (ocrRunning) throw new TradeError('OCR_BUSY', 'One local OCR request at a time; retry shortly.', 503);
        ocrRunning = true;
        try {
          const mediaType = request.headers['content-type'];
          if (!['image/jpeg', 'image/png'].includes(mediaType)) throw new TradeError('INVALID_IMAGE', 'Upload a PNG or JPEG only.');
          const buffer = await readImage(request);
          const observation = await recognizeImage(buffer, mediaType);
          return send(200, { ...observation, mode: 'LOCAL_TESSERACT_OCR_UNTRUSTED',
            persistence: 'IMAGE_NOT_STORED', requiresHumanConfirmation: true });
        } catch (error) {
          if (error instanceof ScanFault) throw new TradeError(error.code, error.message, error.status);
          throw error;
        } finally { ocrRunning = false; }
      }
      let token;
      if (request.method === 'POST') {
        const payload = await readRequest(request);
        if (url.pathname === '/api/demo/session') {
          if (Object.keys(payload).some((key) => key !== 'buyerId') || payload.buyerId !== service.policy().buyerId) throw new TradeError('BUYER_MISMATCH', 'Only the explicitly synthetic buyer is available.', 403);
          token = randomUUID();
          sessions.set(token, payload.buyerId);
          return send(201, { token, buyerId: payload.buyerId, mode: 'SYNTHETIC_NOT_AUTHENTICATED' });
        }
        token = request.headers.authorization?.replace(/^Bearer /, '');
        if (!sessions.has(token)) throw new TradeError('BUYER_CAPABILITY_REQUIRED', 'Obtain an ephemeral synthetic session first.', 403);
        if (payload.buyerId !== undefined && payload.buyerId !== sessions.get(token)) throw new TradeError('BUYER_MISMATCH', 'Capability does not match buyer.', 403);
        const boundQuote = url.pathname.match(/^\/api\/quotes\/([^/]+)\/(?:approval|offer|handshake)$/)?.[1] ?? payload.quoteId;
        const boundPlan = url.pathname.match(/^\/api\/plans\/([^/]+)\/(?:quotes|recover)$/)?.[1];
        const boundOrder = url.pathname.match(/^\/api\/orders\/([^/]+)\/(?:cancel|payment-approval|settlement|scan)$/)?.[1];
        if ((boundQuote && quoteOwners.get(boundQuote) !== token) || (boundOrder && orderOwners.get(boundOrder) !== token) ||
            (boundPlan && planOwners.get(boundPlan) !== token)) throw new TradeError('BUYER_MISMATCH', 'This demo session does not own these terms.', 403);
        request.demoPayload = payload;
      }

      if (request.method === 'GET' && publicFiles[url.pathname]) {
        const [file, type] = publicFiles[url.pathname];
        const body = await readFile(resolve(publicDir, file));
        response.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" });
        response.end(body);
        return;
      }
      if (request.method === 'GET' && url.pathname === '/api/health') return send(200, { status: 'ok', mode: 'SIMULATED', provider: 'invented-local-catalog' });
      if (request.method === 'GET' && url.pathname === '/api/catalog') {
        const items = service.catalog();
        const needle = (url.searchParams.get('q') ?? '').toLocaleLowerCase('en');
        return send(200, { mode: 'INVENTED_FIXTURE', products: items.filter((item) => `${item.name} ${item.sku}`.toLowerCase().includes(needle)) });
      }
      if (request.method === 'GET' && url.pathname === '/api/scan/resolve') {
        return send(200, { product: service.resolveProductScan(url.searchParams.get('gtin')) });
      }
      if (request.method === 'GET' && url.pathname === '/api/policy') return send(200, service.policy());
      if (request.method === 'GET' && ['/api/demo/wallet', '/api/demo/ledger/verify', '/api/demo/ledger'].includes(url.pathname)) {
        const buyerToken = request.headers.authorization?.replace(/^Bearer /, '');
        if (!sessions.has(buyerToken)) throw new TradeError('BUYER_CAPABILITY_REQUIRED', 'Synthetic wallet requires a demo buyer session.', 403);
        if (url.pathname === '/api/demo/wallet') return send(200, { wallet: service.demoWallet() });
        if (url.pathname === '/api/demo/ledger/verify') return send(200, service.paymentJournalVerify());
        return send(200, { entries: service.paymentJournal(), mode: 'IN_MEMORY_SYNTHETIC' });
      }
      if (request.method === 'GET' && url.pathname === '/api/audit') return send(200, { receipts: service.audit() });
      if (request.method === 'GET' && url.pathname === '/api/audit/verify') return send(200, service.auditVerify());
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
        if (current.planId && !current.orderId) {
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
        const buyerToken = request.headers.authorization?.replace(/^Bearer /, '');
        if (!sessions.has(buyerToken) || orderOwners.get(paymentRead[1]) !== buyerToken) {
          throw new TradeError('BUYER_MISMATCH', 'Synthetic settlement details belong to the ordering session.', 403);
        }
        return send(200, service.payment(paymentRead[1], sessions.get(buyerToken)));
      }
      const order = url.pathname.match(/^\/api\/orders\/([^/]+)$/);
      if (request.method === 'GET' && order) return send(200, { order: service.order(order[1]) });
      if (request.method === 'POST' && url.pathname === '/api/demo/reprice') return send(200, { product: service.simulatePriceChange(request.demoPayload) });
      if (request.method === 'POST' && url.pathname === '/api/demo/shock') return send(200, { product: service.simulateStockShock(request.demoPayload) });
      return send(404, { error: { code: 'NOT_FOUND', message: 'Unknown demo route.' } });
    } catch (error) {
      const isTrade = error instanceof TradeError;
      service.recordRefusal(isTrade ? error.code : 'INTERNAL_ERROR', url.pathname);
      return send(isTrade ? error.httpStatus : 500, {
        error: { code: isTrade ? error.code : 'INTERNAL_ERROR', message: isTrade ? error.message : 'Unexpected demo error.', details: isTrade ? error.details : null },
      });
    }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT ?? '4177');
  if (!Number.isSafeInteger(port) || port < 0 || port > 65535) throw new Error('Invalid PORT');
  createTradeHttpServer().listen(port, '127.0.0.1', () => {
    process.stdout.write(`Trusted Trade DEMO (fictional backend) at http://127.0.0.1:${port}/\n`);
  });
}
