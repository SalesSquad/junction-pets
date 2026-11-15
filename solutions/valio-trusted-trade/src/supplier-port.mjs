/**
 * Vendor-neutral read-only adapter prototype.
 * This is NOT a Valio Aimo API client. No external order operation is allowed.
 * See openapi.yaml for the proposed future (unverified) supplier protocol.
 */
import { TradeError } from './core.mjs';

const isLocal = (url) => ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
const validHttpsOrLocalhost = (baseUrl) => {
  let url;
  try { url = new URL(baseUrl); } catch { throw new TradeError('INVALID_PROVIDER_URL', 'Provide an absolute supplier endpoint URL.'); }
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && isLocal(url))) || url.username || url.password || url.search || url.hash) {
    throw new TradeError('INVALID_PROVIDER_URL', 'Supplier API needs HTTPS (localhost HTTP only), no credentials or URL fragments.');
  }
  return url;
};

export function createReadOnlySupplierPort({ baseUrl, fetchImpl = globalThis.fetch, timeoutMs = 5_000 } = {}) {
  const root = validHttpsOrLocalhost(baseUrl);
  if (typeof fetchImpl !== 'function') throw new TradeError('INVALID_TRANSPORT', 'Provide fetch for the adapter.');
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 30_000) throw new TradeError('INVALID_TIMEOUT', 'Use an adapter timeout between 100 and 30,000 milliseconds.');
  const path = (relative) => new URL(relative.replace(/^\//, ''), `${root.href.replace(/\/+$/, '')}/`);
  const fault = (code, message, retryable = false) => new TradeError(code, message, 502, { retryable });
  const transport = async (relative) => {
    const controller = new AbortController();
    let timer;
    let reader;
    let response;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(fault('SUPPLIER_TIMEOUT', 'Supplier read timed out.', true));
      }, timeoutMs);
    });
    const read = async () => {
      response = await fetchImpl(path(relative), { method: 'GET', headers: { Accept: 'application/json' }, signal: controller.signal, redirect: 'error' });
      if (controller.signal.aborted) {
        if (response?.body) void response.body.cancel().catch(() => {});
        throw fault('SUPPLIER_TIMEOUT', 'Supplier read timed out.', true);
      }
      if (!Number.isInteger(response?.status) || response.status < 100 || response.status > 599) throw fault('SUPPLIER_SCHEMA_INVALID', 'Supplier response lacks a valid HTTP status.');
      if (response.status < 200 || response.status >= 300) throw fault('SUPPLIER_UNAVAILABLE', 'Supplier read was unsuccessful.', response.status === 429 || response.status >= 500);
      const mediaType = response.headers?.get('content-type')?.split(';')[0].trim().toLowerCase();
      if (mediaType !== 'application/json') throw fault('SUPPLIER_SCHEMA_INVALID', 'Supplier response must use application/json.');
      const length = response.headers.get('content-length');
      if (length !== null && (!/^\d+$/.test(length) || Number(length) > 262144)) throw fault('SUPPLIER_RESPONSE_TOO_LARGE', 'Supplier response exceeds the read limit.');
      if (!response.body || typeof response.body.getReader !== 'function') throw fault('SUPPLIER_SCHEMA_INVALID', 'Supplier response requires a readable body.');
      reader = response.body.getReader();
      const chunks = [];
      let bytes = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (controller.signal.aborted) throw fault('SUPPLIER_TIMEOUT', 'Supplier read timed out.', true);
        if (done) break;
        if (!(value instanceof Uint8Array)) throw fault('SUPPLIER_SCHEMA_INVALID', 'Supplier response body is invalid.');
        bytes += value.byteLength;
        if (bytes > 262144) throw fault('SUPPLIER_RESPONSE_TOO_LARGE', 'Supplier response exceeds the read limit.');
        chunks.push(value);
      }
      let value;
      try { value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks))); }
      catch { throw fault('SUPPLIER_SCHEMA_INVALID', 'Supplier response is not valid JSON.'); }
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw fault('SUPPLIER_SCHEMA_INVALID', 'Supplier response must be a structured object.');
      return value;
    };
    try { return await Promise.race([read(), deadline]); }
    catch (error) {
      if (error instanceof TradeError) throw error;
      throw fault('SUPPLIER_UNAVAILABLE', 'Supplier read failed.', true);
    } finally {
      clearTimeout(timer);
      controller.abort();
      // Cancellation must not prolong the read deadline on a stalled upstream.
      if (reader) void reader.cancel().catch(() => {});
      else if (response?.body && typeof response.body.cancel === 'function') void response.body.cancel().catch(() => {});
    }
  };
  return Object.freeze({
    protocol: 'supplier-http-json-draft-0.1',
    writesEnabled: false,
    searchCatalog: async (query) => {
      if (typeof query !== 'string' || query.length > 160) throw new TradeError('INVALID_QUERY', 'Search query too long.');
      const response = await transport(`/v1/products?q=${encodeURIComponent(query)}`);
      if (!Array.isArray(response.products) || response.products.length > 100) throw new TradeError('SUPPLIER_SCHEMA_INVALID', 'Expected at most 100 products.', 502);
      for (const item of response.products) {
        if (!item || typeof item !== 'object' || typeof item.sku !== 'string' || !item.sku ||
            !Number.isSafeInteger(item.priceCents) || item.priceCents < 0 ||
            !Number.isSafeInteger(item.availableUnits) || item.availableUnits < 0 ||
            typeof item.sourceVersion !== 'string' || !item.sourceVersion || item.currency !== 'EUR') {
          throw new TradeError('SUPPLIER_SCHEMA_INVALID', 'Product lacks typed price, stock, source version or EUR currency.', 502);
        }
      }
      return response;
    },
    placeOrder: async () => { throw new TradeError('EXTERNAL_ORDER_DISABLED', 'Supplier adapter intentionally prohibits all external order writes.', 403); },
  });
}
