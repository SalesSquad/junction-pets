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
  const transport = async (relative) => {
    const response = await fetchImpl(path(relative), { method: 'GET', headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(timeoutMs), redirect: 'error' });
    if (!response.ok) throw new TradeError('SUPPLIER_UNAVAILABLE', `Supplier read returned HTTP ${response.status}.`, 502);
    const value = await response.json();
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TradeError('SUPPLIER_SCHEMA_INVALID', 'Supplier response must be a structured object.', 502);
    return value;
  };
  return Object.freeze({
    protocol: 'supplier-http-json-draft-0.1',
    writesEnabled: false,
    searchCatalog: async (query) => {
      if (typeof query !== 'string' || query.length > 160) throw new TradeError('INVALID_QUERY', 'Search query too long.');
      const response = await transport(`/v1/products?q=${encodeURIComponent(query)}`);
      if (!Array.isArray(response.products)) throw new TradeError('SUPPLIER_SCHEMA_INVALID', 'Expected products array.', 502);
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
