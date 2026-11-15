/** Read-only preparation for an UNVERIFIED supplier order connection. No transport. */
import { TradeError, unsignedQuoteBody } from './core.mjs';
import { digest } from './trust-envelope.mjs';
import { calculateBasketTotals } from './purchase-units.mjs';

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,200}$/.test(value);
const whole = (value, minimum, maximum) => Number.isSafeInteger(value) && value >= minimum && value <= maximum;
const refuse = () => { throw new TradeError('INVALID_SUPPLIER_HANDOFF', 'A supplier handoff requires matching committed synthetic quote, receipt and exact quote body.', 409); };
const requiredIntegrationMaterial = Object.freeze([
  'SUPPLIER_APPROVED_ORDER_SCHEMA_AND_SANDBOX',
  'CUSTOMER_BRANCH_AND_BUYER_DELEGATION',
  'SERVER_MANAGED_AUTHENTICATION_AND_OPERATION_SCOPES',
  'FIXED_PRICE_RESERVATION_AND_EXPIRY_RULES',
  'SALES_UNITS_PACKS_TAX_FREIGHT_AND_CUTOFF_SEMANTICS',
  'IDEMPOTENCY_STATUS_LOOKUP_AND_RECONCILIATION',
  'ACCEPTANCE_ACK_PARTIAL_FAILURE_AND_CANCELLATION_RULES',
]);

export function valioOrderConnectionStatus() {
  return {
    mode: 'UNVERIFIED_ORDER_CONNECTION',
    sendAllowed: false,
    endpoint: null,
    authentication: 'NOT_CONFIGURED',
    procurementAuthority: 'NOT_CONFIGURED',
    productionContract: 'UNVERIFIED',
    blocker: 'NO_VERIFIED_ORDER_CONTRACT',
    challengeMock: {
      schema: 'https://junction26.valioaimo.fi/openapi.json',
      evidence: 'OBSERVED_2026_11_15_NOT_A_LIVE_PROBE',
      observedOperations: ['GET /api/ping', 'POST /api/availability', 'POST /api/price', 'GET /api/products/download', 'GET /api/delivery-reliability/download', 'GET /api/carbon-footprint/download'],
      orderEndpointInObservedSchema: false,
    },
    commercialChannels: [
      { channel: 'AIMO_WHOLESALE', source: 'https://www.valioaimo.fi/asiakkaaksi/' },
      { channel: 'VALO_DIRECT_CUSTOMER', source: 'https://www.valioaimo.fi/asiakkaaksi/valo-tilauspalvelu/' },
    ],
    nextRequirements: [...requiredIntegrationMaterial],
  };
}

const lineTerms = line => {
  if (!object(line) || !identifier(line.sku) || !identifier(line.supplierId) ||
      !whole(line.quantityLitres, 1, 10000) || !whole(line.unitPriceCents, 1, 100000) ||
      !whole(line.packLitres, 1, 10000) || !whole(line.packs, 1, 10000) ||
      !whole(line.minOrderPacks, 1, 10000) || line.packs < line.minOrderPacks ||
      line.packs * line.packLitres !== line.quantityLitres || !whole(line.stockVersion, 1, Number.MAX_SAFE_INTEGER) ||
      line.totalCents !== line.quantityLitres * line.unitPriceCents) refuse();
  return {
    sku: line.sku, supplierId: line.supplierId,
    quantityLitres: line.quantityLitres, unit: 'L',
    packLitres: line.packLitres, packs: line.packs, minimumPacks: line.minOrderPacks,
    unitPriceCents: line.unitPriceCents, totalCents: line.totalCents, sourceStockVersion: line.stockVersion,
  };
};

/**
 * Our internal non-sendable envelope, not a Valio API request.
 * Only explicit server-held source fields are projected; arbitrary metadata is dropped.
 */
export function createValioOrderHandoff(input = {}) {
  if (!object(input)) refuse();
  const { quote, order, body } = input;
  if (!object(quote) || !object(order) || !object(body) ||
      !identifier(quote.id) || !identifier(order.id) || !identifier(quote.buyerId) || !identifier(quote.snapshotId) ||
      quote.provider !== 'INVENTED_LOCAL_CATALOG' ||
      quote.status !== 'SIMULATED_COMMITTED' || order.status !== 'SIMULATED_COMMITTED' ||
      order.commitment !== 'SIMULATION_ONLY_NO_REAL_PURCHASE' ||
      quote.orderId !== order.id || order.quoteId !== quote.id ||
      order.buyerId !== quote.buyerId || order.snapshotId !== quote.snapshotId ||
      !object(quote.sourceSnapshot) || quote.sourceSnapshot.id !== quote.snapshotId ||
      !whole(quote.totalCents, 1, 250000) || order.totalCents !== quote.totalCents ||
      !Array.isArray(quote.lines) || quote.lines.length < 1 || quote.lines.length > 100 ||
      !Array.isArray(order.lines) || order.lines.length !== quote.lines.length ||
      !object(quote.costBreakdown) || !object(order.costBreakdown)) refuse();
  const lines = quote.lines.map(lineTerms);
  if (new Set(lines.map(line => line.sku)).size !== lines.length ||
      digest(lines) !== digest(order.lines.map(lineTerms)) || !Array.isArray(quote.sourceSnapshot.products) ||
      quote.sourceSnapshot.products.length > 100) refuse();
  for (const line of quote.lines) {
    const sources = quote.sourceSnapshot.products.filter(product => product?.sku === line.sku);
    const source = sources[0];
    if (sources.length !== 1 || source.priceCents !== line.unitPriceCents || source.version !== line.stockVersion ||
        source.packLitres !== line.packLitres || source.minOrderPacks !== line.minOrderPacks ||
        source.supplierId !== line.supplierId || !whole(source.unitsAvailable, line.quantityLitres, 1000000)) refuse();
  }
  const subtotalCents = lines.reduce((sum, line) => sum + line.totalCents, 0);
  let totals;
  try { totals = calculateBasketTotals({ subtotalCents,
    deliveryFeeCents: quote.costBreakdown.deliveryFeeCents, taxBps: quote.costBreakdown.taxBps }); }
  catch { refuse(); }
  const costBreakdown = {
    subtotalCents, deliveryFeeCents: totals.deliveryFeeCents,
    taxCents: totals.taxCents, taxBps: totals.taxBps,
  };
  if (totals.totalCents !== quote.totalCents ||
      ['subtotalCents', 'deliveryFeeCents', 'taxCents', 'taxBps'].some(key =>
        quote.costBreakdown[key] !== costBreakdown[key] || order.costBreakdown[key] !== costBreakdown[key])) refuse();
  let bodyDigest;
  try {
    bodyDigest = digest(body);
    if (bodyDigest !== digest(unsignedQuoteBody(quote))) refuse();
  } catch { refuse(); }
  const verified = quote.verifiedHandshake?.quoteBodyDigest ?? null;
  if ((verified !== null && verified !== bodyDigest) || (order.verifiedQuoteBodyDigest ?? null) !== verified) refuse();
  const envelope = {
    version: 'valio.internal.non-sendable-handoff.v1',
    source: 'INVENTED_FIXTURE',
    sendAllowed: false,
    blocker: 'NO_VERIFIED_ORDER_CONTRACT',
    vendorRequest: false,
    references: { quoteId: quote.id, orderId: order.id, sourceSnapshotId: quote.snapshotId, quoteBodyDigest: bodyDigest },
    idempotencyReference: 'internal-handoff-' + digest({ orderId: order.id, quoteId: quote.id, quoteBodyDigest: bodyDigest }),
    terms: { currency: 'EUR', totalCents: quote.totalCents, costBreakdown, lines },
    evidence: {
      receipt: 'SIMULATED_COMMITTED_NOT_SUPPLIER_ACCEPTANCE',
      quoteBody: verified ? 'SYNTHETIC_HANDSHAKE_BOUND' : 'UNSIGNED_SYNTHETIC_QUOTE',
      supplierAcceptance: 'NOT_OBTAINED',
      buyerAuthority: 'REQUIRES_SEPARATE_HOST_VERIFICATION',
    },
    requiredIntegrationMaterial: [...requiredIntegrationMaterial],
  };
  return { ...envelope, payloadDigest: digest(envelope) };
}
