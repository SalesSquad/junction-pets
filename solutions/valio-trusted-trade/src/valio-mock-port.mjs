import { createHash } from 'node:crypto';
import { TradeError } from './core.mjs';

const ORIGIN = 'https://junction26.valioaimo.fi';
const PROVIDER = 'VALIO_JUNCTION_MOCK_API';
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
export const isValioProductId = value => typeof value === 'string' && /^[0-9]{1,12}$/.test(value);
const text = (value) => typeof value === 'string' && value.length > 0 && value.length <= 200;
const date = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
const hash = (value) => createHash('sha256').update(value).digest('hex');
const fault = (code, message, status = 502, retryable = false, retryAfterSeconds = null) => new TradeError(code, message, status, { retryable, retryAfterSeconds });

// Validate documented required types only. Empty OpenAPI schemas remain opaque;
// one example cannot establish optional price, cutoff or unit semantics.
const sourceProducts = (value, request) => {
  if (!Array.isArray(value.products) || value.products.length > request.products.length) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor products exceed the narrowed request.');
  const seen = new Set();
  for (const item of value.products) {
    if (!object(item) || !request.products.includes(item.productId) || seen.has(item.productId)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor returned an unexpected or repeated product.');
    seen.add(item.productId);
  }
  return value.products;
};
const matchesRequestedDate = (value, requested) => text(value) && value.slice(0, 10) === requested && (value.length === 10 || (value[10] === 'T' && Number.isFinite(Date.parse(value))));
const validateAvailability = (value, request) => {
  if (!text(value.timeNow) || !matchesRequestedDate(value.requestedDate, request.requestedDate)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor availability source date is invalid.');
  for (const item of sourceProducts(value, request)) {
    if (typeof item.salesBlock !== 'boolean' || !Array.isArray(item.scheduleLines) || item.scheduleLines.length > 1000) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor availability facts are invalid.');
    for (const line of item.scheduleLines) {
      if (!object(line) || typeof line.salesBlock !== 'boolean' || typeof line.availableAmount !== 'number' || !Number.isFinite(line.availableAmount) || !text(line.salesUnit)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor schedule facts are invalid.');
    }
  }
};
const validatePrices = (value, request) => {
  if (value.customerId !== request.customer || !text(value.currency) || !matchesRequestedDate(value.pricingDate, request.requestedDate)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor price source identity or date is invalid.');
  for (const item of sourceProducts(value, request)) {
    if (typeof item.quantity !== 'number' || !Number.isFinite(item.quantity) || typeof item.netPriceFound !== 'boolean' || typeof item.error !== 'boolean') throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor price facts are invalid.');
  }
};

/** Sponsor mock reads only. Source numbers and units never confer purchasing authority. */
export function createValioMockPort({ customer, apiKey, fetchImpl = globalThis.fetch, clock = () => Date.now(), timeoutMs = 5000 } = {}) {
  if (!text(customer) || !['string', 'function'].includes(typeof apiKey) || typeof fetchImpl !== 'function' || typeof clock !== 'function' || !Number.isSafeInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 30000) {
    throw fault('INVALID_PROVIDER_CONFIG', 'Configure the fixed sponsor customer and server-side transport.', 400);
  }
  const read = async (endpoint, request) => {
    const controller = new AbortController();
    let timer, reader, response;
    const deadline = new Promise((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(fault('SPONSOR_TIMEOUT', 'Sponsor read timed out.', 504, true)); }, timeoutMs); });
    const operation = async () => {
      const key = typeof apiKey === 'function' ? await apiKey() : apiKey;
      if (typeof key !== 'string' || !key || /[\r\n]/.test(key)) throw fault('SPONSOR_CREDENTIAL_UNAVAILABLE', 'Sponsor server credential is unavailable.', 503);
      if (controller.signal.aborted) throw fault('SPONSOR_TIMEOUT', 'Sponsor read timed out.', 504, true);
      response = await fetchImpl(`${ORIGIN}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-API-Key': key }, body: JSON.stringify(request), redirect: 'error', signal: controller.signal });
      if (controller.signal.aborted) { if (response?.body) void response.body.cancel().catch(() => {}); throw fault('SPONSOR_TIMEOUT', 'Sponsor read timed out.', 504, true); }
      if (!Number.isInteger(response?.status) || response.status < 100 || response.status > 599) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor response has no valid status.');
      if (response.status < 200 || response.status >= 300) {
        const retryable = response.status === 429 || response.status >= 500;
        const raw = response.headers?.get('retry-after');
        const retryAfter = retryable && /^\d+$/.test(raw ?? '') ? Math.min(Number(raw), 60) : null;
        throw fault('SPONSOR_UNAVAILABLE', 'Sponsor read was unsuccessful.', 502, retryable, retryAfter);
      }
      if (response.headers?.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor response must be JSON.');
      const length = response.headers.get('content-length');
      if (length !== null && (!/^\d+$/.test(length) || Number(length) > 524288)) throw fault('SPONSOR_RESPONSE_TOO_LARGE', 'Sponsor response exceeds the read limit.');
      if (typeof response.body?.getReader !== 'function') throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor response has no readable body.');
      reader = response.body.getReader();
      let bytes = 0; const chunks = [];
      while (true) {
        const { done, value } = await reader.read();
        if (controller.signal.aborted) throw fault('SPONSOR_TIMEOUT', 'Sponsor read timed out.', 504, true);
        if (done) break;
        if (!(value instanceof Uint8Array)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor body is malformed.');
        bytes += value.byteLength;
        if (bytes > 524288) throw fault('SPONSOR_RESPONSE_TOO_LARGE', 'Sponsor response exceeds the read limit.');
        chunks.push(value);
      }
      const raw = Buffer.concat(chunks);
      let value;
      try { value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)); } catch { throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor body is malformed.'); }
      if (JSON.stringify(value).includes(key)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor response contains prohibited credential material.');
      if (!object(value)) throw fault('SPONSOR_SCHEMA_INVALID', 'Sponsor response must be an object.');
      return { value, sha256: hash(raw) };
    };
    try { return await Promise.race([operation(), deadline]); }
    catch (error) { if (error instanceof TradeError) throw error; throw fault('SPONSOR_UNAVAILABLE', 'Sponsor read failed.', 502, true); }
    finally { clearTimeout(timer); controller.abort(); if (reader) void reader.cancel().catch(() => {}); else if (typeof response?.body?.cancel === 'function') void response.body.cancel().catch(() => {}); }
  };
  const cache = new Map();
  const pending = new Map();
  return Object.freeze({
    mode: 'SPONSOR_MOCK_READ_ONLY',
    observe: async (input = {}) => {
      if (!object(input) || Object.keys(input).some((key) => !['products', 'requestedDate'].includes(key)) || !date(input.requestedDate) || !Array.isArray(input.products) || input.products.length < 1 || input.products.length > 20 || !input.products.every(isValioProductId) || new Set(input.products).size !== input.products.length) throw fault('INVALID_SPONSOR_REQUEST', 'Provide one date and 1–20 distinct numeric catalog product IDs (1–12 digits).', 400);
      const request = { customer, requestedDate: input.requestedDate, products: [...input.products] };
      const cacheKey = JSON.stringify(request);
      const now = clock();
      for (const [key, entry] of cache) if (now - entry.storedAt >= 30000 || now < entry.storedAt) cache.delete(key);
      const cached = cache.get(cacheKey);
      if (cached) return { ...structuredClone(cached.result), cache: { hit: true, ageMs: now - cached.storedAt, ttlMs: 30000 } };
      if (pending.has(cacheKey)) {
        const result = await pending.get(cacheKey);
        return { ...structuredClone(result), cache: { hit: true, ageMs: Math.max(0, clock() - Date.parse(result.provenance.observedAt)), ttlMs: 30000 } };
      }
      if (pending.size >= 128) throw fault('SPONSOR_BUSY', 'Sponsor read capacity is busy.', 503, true);
      const observe = async () => {
        const availability = await read('/api/availability', request);
        validateAvailability(availability.value, request);
        const prices = await read('/api/price', request);
        validatePrices(prices.value, request);
        const priceById = new Map(prices.value.products.map((item) => [item.productId, item]));
        const providerTime = Date.parse(availability.value.timeNow);
        const classifications = availability.value.products.map((item) => {
          const cutoff = typeof item.closingTime === 'string' ? Date.parse(item.closingTime) : NaN;
          return { productId: item.productId, purchasingAuthority: 'NONE',
            availability: item.salesBlock || item.scheduleLines.length === 0 || item.scheduleLines.every((line) => line.salesBlock) ? 'UNORDERABLE' : 'UNQUALIFIED_SOURCE_ONLY',
            cutoff: Number.isFinite(cutoff) && Number.isFinite(providerTime) ? (cutoff <= providerTime ? 'PASSED' : 'NOT_PASSED') : 'UNKNOWN',
            scheduleFacts: item.scheduleLines.map((line) => ({ salesBlocked: line.salesBlock,
              stock: item.logisticModel === 'Terminal' && line.availableAmount === 999999 ? 'UNKNOWN_TERMINAL_SENTINEL' : 'OPAQUE_SOURCE_AMOUNT',
              sourceAmount: line.availableAmount, sourceUnit: line.salesUnit, unitInterpretation: 'UNMAPPED' })),
            netPrice: priceById.get(item.productId)?.netPriceFound === true && priceById.get(item.productId)?.error === false ? 'SOURCE_FLAG_TRUE_UNQUALIFIED' : 'UNCONFIRMED' };
        });
        const result = { mode: 'SPONSOR_MOCK_READ_ONLY', availability: availability.value, prices: prices.value, classifications,
          provenance: { provider: PROVIDER, origin: ORIGIN, observedAt: new Date(clock()).toISOString(), requestedDate: request.requestedDate,
            availability: { endpoint: '/api/availability', sha256: availability.sha256, providerTime: availability.value.timeNow },
            prices: { endpoint: '/api/price', sha256: prices.sha256, pricingDate: prices.value.pricingDate },
            interpretation: 'OPAQUE_SOURCE_FACTS_TERMINAL_999999_IS_UNKNOWN_STOCK',
            limitations: ['NO_PURCHASING_AUTHORITY', 'SALES_BLOCK_OR_NO_SCHEDULE_IS_UNORDERABLE', 'CUTOFF_SEMANTICS_UNQUALIFIED', 'UNITS_AND_PRICE_OBJECTS_UNMAPPED', 'NET_PRICE_FALSE_IS_NOT_A_NET_OFFER'] }, requiresTradeCoreValidation: true,
          cache: { hit: false, ageMs: 0, ttlMs: 30000 } };
        if (cache.size >= 128) cache.delete(cache.keys().next().value);
        cache.set(cacheKey, { storedAt: clock(), result: structuredClone(result) });
        return result;
      };
      const promise = observe();
      pending.set(cacheKey, promise);
      try { return await promise; } finally { pending.delete(cacheKey); }

    },
  });
}
