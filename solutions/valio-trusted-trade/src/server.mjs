import { randomUUID } from 'node:crypto';
import { metadata, openapi } from './contract.mjs';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { readFile } from 'node:fs/promises';
import { createTradeService, TradeError, unsignedQuoteBody } from './core.mjs';

const currentDir = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(currentDir, '../public');
const publicFiles = Object.freeze({
  '/': ['index.html', 'text/html; charset=utf-8'],
  '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/style.css': ['style.css', 'text/css; charset=utf-8'],
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

export function createTradeHttpServer(service = createTradeService()) {
  const sessions = new Map();
  const quoteOwners = new Map();
  const orderOwners = new Map();
  return createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', 'http://localhost');
    const send = (status, body) => {
      response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" });
      response.end(JSON.stringify(body));
    };
    try {
      if (request.headers.origin && request.headers.origin !== `http://${request.headers.host}`) throw new TradeError('ORIGIN_REFUSED', 'Cross-origin demo writes forbidden.', 403);
      if (request.method === 'GET' && url.pathname === '/.well-known/trusted-trade') return send(200, metadata);
      if (request.method === 'GET' && url.pathname === '/openapi.json') return send(200, openapi);
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
        const boundQuote = url.pathname.match(/^\/api\/quotes\/([^/]+)\/approval$/)?.[1] ?? payload.quoteId;
        const boundOrder = url.pathname.match(/^\/api\/orders\/([^/]+)\/cancel$/)?.[1];
        if ((boundQuote && quoteOwners.get(boundQuote) !== token) || (boundOrder && orderOwners.get(boundOrder) !== token)) throw new TradeError('BUYER_MISMATCH', 'This demo session does not own these terms.', 403);
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
      if (request.method === 'GET' && url.pathname === '/api/policy') return send(200, service.policy());
      if (request.method === 'GET' && url.pathname === '/api/audit') return send(200, { receipts: service.audit() });
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
      const quote = url.pathname.match(/^\/api\/quotes\/([^/]+)$/);
      if (request.method === 'GET' && quote) return send(200, { quote: service.quote(quote[1]) });
      if (request.method === 'POST' && url.pathname === '/api/orders') {
        const order = service.commitOrder(request.demoPayload);
        orderOwners.set(order.id, token);
        return send(201, { order });
      }
      const cancel = url.pathname.match(/^\/api\/orders\/([^/]+)\/cancel$/);
      if (request.method === 'POST' && cancel) return send(200, { order: service.cancelOrder({ ...request.demoPayload, orderId: cancel[1] }) });
      const order = url.pathname.match(/^\/api\/orders\/([^/]+)$/);
      if (request.method === 'GET' && order) return send(200, { order: service.order(order[1]) });
      if (request.method === 'POST' && url.pathname === '/api/demo/reprice') return send(200, { product: service.simulatePriceChange(request.demoPayload) });
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
