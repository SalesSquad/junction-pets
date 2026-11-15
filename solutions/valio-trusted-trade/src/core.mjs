/**
 * Trusted Trade — deterministic buyer-side control plane.
 * All products, stock, people and orders are invented demo data.
 * No calls to Valio or a production purchasing system are made.
 */
import { planProcurementPortfolio, PlannerFault } from './procurement-planner.mjs';
import { digest, restorePrivateComponent, restorePrivateEntries, invalidPrivateState } from './trust-envelope.mjs';
import { createSyntheticSettlement } from './settlement.mjs';
import { resolveGtin, ScanFault } from './scanning.mjs';

import { createHash, randomUUID } from 'node:crypto';
import { diagnoseProcurement } from './procurement-diagnostics.mjs';
import { planPurchasableBasket, calculateBasketTotals, PurchaseUnitError } from './purchase-units.mjs';

export const FIXTURE_CATALOG = Object.freeze([
  { sku: 'DEMO-LF-1', gtin: '2000000000015', name: 'Lactose-free dairy milk · 1 L', family: 'dairy-milk', lactoseFree: true, unitsAvailable: 780, priceCents: 174, deliverBy: '2026-11-16', certification: 'Finnish origin · fictional', version: 1, supplierId: 'fictional-north-dairy', reliabilityBps: 9640, emissionsGramsPerL: 1150 },
  { sku: 'DEMO-LF-2', gtin: '2000000000022', name: 'Lactose-free dairy milk · 1 L', family: 'dairy-milk', lactoseFree: true, unitsAvailable: 900, priceCents: 189, deliverBy: '2026-11-16', certification: 'Animal welfare · fictional', version: 1, supplierId: 'fictional-coastal-foods', reliabilityBps: 9910, emissionsGramsPerL: 960 },
  { sku: 'DEMO-LF-3', gtin: '2000000000039', name: 'Organic lactose-free dairy milk · 1 L', family: 'dairy-milk', lactoseFree: true, unitsAvailable: 140, priceCents: 217, deliverBy: '2026-11-17', certification: 'Organic · fictional', version: 1, supplierId: 'fictional-hill-farm', reliabilityBps: 9700, emissionsGramsPerL: 910 },
  { sku: 'DEMO-REG-1', gtin: '2000000000046', name: 'Standard dairy milk · 1 L', family: 'dairy-milk', lactoseFree: false, unitsAvailable: 1900, priceCents: 143, deliverBy: '2026-11-16', certification: 'Finnish origin · fictional', version: 1, supplierId: 'fictional-north-dairy', reliabilityBps: 9640, emissionsGramsPerL: 1120 },
  { sku: 'DEMO-OAT-1', gtin: '2000000000053', name: 'Oat drink · 1 L', family: 'oat-drink', lactoseFree: true, unitsAvailable: 2100, priceCents: 162, deliverBy: '2026-11-16', certification: 'Plant-based · fictional', version: 1, supplierId: 'fictional-oatworks', reliabilityBps: 9820, emissionsGramsPerL: 380 },
].map((product) => ({ ...product, packLitres: 1, minOrderPacks: 1 })));

export const FIXTURE_POLICY = Object.freeze({
  buyerId: 'helsinki-hotel-demo',
  name: 'Hotel North · demonstration only',
  autoCommitLimitCents: 75_000,
  perOrderBudgetCents: 250_000,
  quoteLifetimeMs: 120_000,
  substitutionsRequireApproval: true,
  deliveryFeeCents: 0, taxBps: 0, pricingQualification: 'SYNTHETIC_NO_REAL_TAX_OR_FREIGHT_TARIFF',
});

export class TradeError extends Error {
  constructor(code, message, httpStatus = 400, details = null) {
    super(message);
    this.name = 'TradeError';
    this.code = code;
    this.httpStatus = httpStatus;
    this.details = details;
  }
}

const safeWhole = (value, min, max, label) => {
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new TradeError('INVALID_REQUEST', `${label} must be a whole number from ${min} to ${max}.`);
  }
  return value;
};

const digestLike = (value) => JSON.stringify(value);

/** Checks the local receipt chain; persistence and external anchoring are out of scope. */
export function verifyAuditChain(receipts) {
  if (!Array.isArray(receipts)) return { valid: false, firstInvalidIndex: 0 };
  let prevHash = 'GENESIS';
  for (const [index, receipt] of receipts.entries()) {
    if (!receipt || receipt.prevHash !== prevHash ||
        receipt.hash !== digest({ id: receipt.id, time: receipt.time, event: receipt.event,
          detail: receipt.detail, prevHash: receipt.prevHash })) {
      return { valid: false, firstInvalidIndex: index };
    }
    prevHash = receipt.hash;
  }
  return { valid: true, count: receipts.length, headDigest: prevHash, mode: 'IN_MEMORY_HASH_LINKED_NOT_EXTERNAL_ANCHORED' };
}

/** No LLM claims: the demo deliberately accepts only the supported request shape. */
export function parseBuyerRequest(raw) {
  if (typeof raw !== 'string' || raw.length > 1000 || !raw.trim()) {
    throw new TradeError('INVALID_REQUEST', 'Enter one short purchasing request.');
  }
  // Full-sentence grammar, deliberately not an extraction/search regex: never
  // turn a negative, decimal, second SKU, instruction or currency into quantity.
  // One explicitly supported product and delivery fixture; no guesses.
  const normalized = raw.trim().replace(/\s+/g, ' ');
  const matched = normalized.match(/^(?:(?:(?:i|we)\s+need|need|order|buy|please\s+(?:order|buy))\s+)?(\d{1,3}(?:,\d{3})+|\d+)\s*(?:litres?|liters?|l)\s+(?:of\s+)?lactose[ -]+free\s+(?:dairy\s+)?milk(?:\s+by\s+monday)?[.!]?$/i);
  if (!matched) {
    throw new TradeError('UNSUPPORTED_REQUEST', 'Use one positive whole-litre lactose-free dairy milk request (for example: I need 1,000 L of lactose-free milk by Monday). No decimals, extra products or instructions.');
  }
  const quantityLitres = Number(matched[1].replace(/,/g, ''));
  safeWhole(quantityLitres, 1, 10_000, 'Quantity');
  return {
    quantityLitres,
    family: 'dairy-milk',
    lactoseFree: true,
    deliverBy: '2026-11-16',
    parsedFrom: raw.slice(0, 200),
  };
}

/** Typed needs never infer substitutions, prices or authority from prose. */
export function validateBuyingNeed(need) {
  const keys = ['family', 'quantityLitres', 'lactoseFree', 'deliverBy'];
  if (!need || typeof need !== 'object' || Array.isArray(need) ||
      Object.keys(need).some((key) => !keys.includes(key)) ||
      !['dairy-milk', 'oat-drink'].includes(need.family) ||
      typeof need.lactoseFree !== 'boolean' || need.deliverBy !== '2026-11-16') {
    throw new TradeError('INVALID_NEED', 'Specify dairy-milk or oat-drink, lactoseFree boolean, whole litres and fixture date 2026-11-16 only.');
  }
  safeWhole(need.quantityLitres, 1, 10_000, 'Quantity');
  return { ...need };
}

export function unsignedQuoteBody(q) {
  const lines = q.lines.map((line) => ({ sku: line.sku, quantity: line.quantityLitres,
    unit: 'L', unit_price_cents: line.unitPriceCents, stock_version: line.stockVersion,
    pack_litres: line.packLitres, pack_count: line.packs, min_order_packs: line.minOrderPacks,
    supplier_id: line.supplierId ?? 'supplier-demo' }));
  return { version: 'kattely.procurement.quote.v3', quote_id: q.id, supplier_id: 'supplier-demo',
    buyer_id: q.buyerId, audience: 'https://supplier-demo.invalid', currency: 'EUR',
    issued_at: Math.floor(q.createdAtMs / 1000), expires_at: Math.floor(q.expiresAtMs / 1000),
    lines, cost_breakdown: q.costBreakdown ? {
      subtotal_cents: q.costBreakdown.subtotalCents, delivery_fee_cents: q.costBreakdown.deliveryFeeCents,
      tax_cents: q.costBreakdown.taxCents, tax_bps: q.costBreakdown.taxBps,
    } : null,
    source_snapshot_id: q.snapshotId ?? null, total_cents: q.totalCents };
}

export function createTradeService({ initialCatalog = FIXTURE_CATALOG, policy = FIXTURE_POLICY, clock = () => Date.now(), initialState } = {}) {
  const restored = restorePrivateComponent(initialState, 'trade-service',
    ['catalog', 'quotes', 'plans', 'orders', 'reviews', 'sourceEpoch', 'idempotency', 'deliveryObservations', 'deliveryReplay', 'audit', 'serial', 'policy', 'settlement']);
  if (restored) policy = restored.policy;
  if (restored && (!policy || typeof policy.buyerId !== 'string' || !policy.buyerId ||
      !Number.isSafeInteger(policy.perOrderBudgetCents) || policy.perOrderBudgetCents < 1 ||
      !Number.isSafeInteger(policy.autoCommitLimitCents) || policy.autoCommitLimitCents < 0 || policy.autoCommitLimitCents > policy.perOrderBudgetCents ||
      !Number.isSafeInteger(policy.quoteLifetimeMs) || policy.quoteLifetimeMs < 1 ||
      !Number.isSafeInteger(policy.deliveryFeeCents) || policy.deliveryFeeCents < 0 ||
      !Number.isSafeInteger(policy.taxBps) || policy.taxBps < 0 || policy.taxBps > 10000)) invalidPrivateState();
  const catalog = restored ? restorePrivateEntries(restored.catalog, (item, sku) => item?.sku === sku &&
    Number.isSafeInteger(item.unitsAvailable) && item.unitsAvailable >= 0 && item.unitsAvailable <= 1000000 &&
    Number.isSafeInteger(item.priceCents) && item.priceCents > 0 && Number.isSafeInteger(item.version) && item.version > 0 &&
    Number.isSafeInteger(item.packLitres) && item.packLitres > 0 && Number.isSafeInteger(item.minOrderPacks) && item.minOrderPacks > 0) : new Map(initialCatalog.map((item) => [item.sku, { ...item }]));
  const entity = (item, id) => item && item.id === id && typeof item.buyerId === 'string';
  const quotes = restored ? restorePrivateEntries(restored.quotes, (item, id) => entity(item, id) && Array.isArray(item.lines) && item.requested && item.sourceSnapshot &&
    typeof item.snapshotId === 'string' && Number.isSafeInteger(item.totalCents) && item.totalCents > 0 &&
    Number.isSafeInteger(item.createdAtMs) && Number.isSafeInteger(item.expiresAtMs) && item.expiresAtMs > item.createdAtMs && typeof item.status === 'string') : new Map();
  const plans = restored ? restorePrivateEntries(restored.plans, (item, id) => entity(item, id) && Array.isArray(item.options) && Array.isArray(item.requirements) && item.sourceSnapshot) : new Map();
  const orders = restored ? restorePrivateEntries(restored.orders, (item, id) => entity(item, id) && quotes.has(item.quoteId) && Array.isArray(item.lines) &&
    Number.isSafeInteger(item.totalCents) && item.totalCents > 0 && ['SIMULATED_COMMITTED', 'SIMULATED_CANCELLED'].includes(item.status)) : new Map();
  const reviews = restored ? restorePrivateEntries(restored.reviews, (item, id) => entity(item, id) && item.sourceSnapshot && (item.quoteId === null || quotes.has(item.quoteId))) : new Map();
  const sourceEpoch = restored?.sourceEpoch ?? randomUUID();
  const idempotency = restored ? restorePrivateEntries(restored.idempotency, (entry) => typeof entry?.fingerprint === 'string' && orders.has(entry.orderId)) : new Map();
  const deliveryObservations = restored ? restorePrivateEntries(restored.deliveryObservations, (entry, id) => Array.isArray(entry) && orders.has(id)) : new Map();
  if (restored) for (const [id, tally] of deliveryObservations) deliveryObservations.set(id, restorePrivateEntries(tally, (count) => Number.isSafeInteger(count) && count >= 0));
  const deliveryReplay = restored ? restorePrivateEntries(restored.deliveryReplay, (entry) => typeof entry?.fingerprint === 'string' && entry.result && orders.has(entry.result.orderId)) : new Map();
  const audit = restored?.audit ?? [];
  let serial = restored?.serial ?? 0;
  if (restored) {
    try {
      if (typeof sourceEpoch !== 'string' || !/^[0-9a-f-]{36}$/.test(sourceEpoch) || !Number.isSafeInteger(serial) || serial < 0 ||
          !verifyAuditChain(audit).valid || [...quotes.values(), ...plans.values(), ...orders.values(), ...reviews.values(), ...audit].some((entry) =>
            !/^[A-Z]+-DEMO-[0-9]+$/.test(entry.id) || Number(entry.id.split('-').at(-1)) > serial)) invalidPrivateState();
    } catch { invalidPrivateState(); }
  }
  const nextId = (prefix) => `${prefix}-DEMO-${String(++serial).padStart(4, '0')}`;
  const record = (event, detail) => {
    const prevHash = audit.at(-1)?.hash ?? 'GENESIS';
    const receipt = { id: nextId('EV'), time: new Date(clock()).toISOString(), event, detail, prevHash };
    receipt.hash = digest(receipt);
    audit.push(receipt);
    return receipt;
  };
  const catalogList = () => [...catalog.values()].map((x) => ({ ...x }));
  // Synchronous local reads form one coherent source snapshot. The hash is a
  // revision identifier, not a supplier signature or verified identity.
  const captureSnapshot = (requested) => {
    const needs = (requested.requirements ?? [requested]).map((need) => ({
      family: need.family, quantityLitres: need.quantityLitres, lactoseFree: need.lactoseFree, deliverBy: need.deliverBy,
    }));
    const families = new Set(needs.map((need) => need.family));
    const products = catalogList().filter((p) => families.has(p.family))
      .sort((a, b) => a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0);
    const constraints = requested.requirements ? { requirements: needs, mode: 'TYPED_PORTFOLIO' } : needs[0];
    const terms = { products, policy: { ...policy }, constraints };
    return { ...terms, id: 'S-' + sourceEpoch + '-' +
      createHash('sha256').update(JSON.stringify(terms)).digest('hex'),
      observedAtMs: clock(), mode: 'INVENTED_FIXTURE', stockReserved: false };
  };
  const getReview = (reviewId) => {
    const review = reviews.get(reviewId);
    if (!review) throw new TradeError('REVIEW_NOT_FOUND', 'This review does not exist.', 404);
    return review;
  };
  const getQuote = (quoteId) => {
    const q = quotes.get(quoteId);
    if (!q) throw new TradeError('QUOTE_NOT_FOUND', 'This quote does not exist.', 404);
    return q;
  };
  const getOrder = (orderId) => {
    const o = orders.get(orderId);
    if (!o) throw new TradeError('ORDER_NOT_FOUND', 'This order does not exist.', 404);
    return o;
  };
  const settlement = createSyntheticSettlement({ getOrder, TradeError, record, clock, ...(restored ? { initialState: restored.settlement } : {}) });

  const resolveProductScan = (gtin) => {
    try { return resolveGtin(catalogList(), gtin); }
    catch (error) {
      if (error instanceof ScanFault) throw new TradeError(error.code, error.message, error.status);
      throw error;
    }
  };

  /** A matching GTIN is an observation, not proof the goods were delivered. */
  const scanDelivery = ({ orderId, buyerId, gtin, idempotencyKey, ...unknown } = {}) => {
    if (Object.keys(unknown).length) throw new TradeError('INVALID_DELIVERY_SCAN', 'Only order, buyer, GTIN and idempotency key are accepted.');
    if (typeof idempotencyKey !== 'string' || !/^[A-Za-z0-9_-]{10,80}$/.test(idempotencyKey)) {
      throw new TradeError('INVALID_IDEMPOTENCY_KEY', 'Provide a stable 10–80 character scan idempotency key.');
    }
    const order = getOrder(orderId);
    if (order.buyerId !== buyerId) throw new TradeError('BUYER_MISMATCH', 'Only the original demo buyer can record receipt evidence.', 403);
    if (!order.verifiedQuoteBodyDigest) throw new TradeError('SIGNED_TRADE_REQUIRED', 'Receipt comparison requires a previously verified signed trade.', 403);
    const product = resolveProductScan(gtin);
    const fingerprint = digestLike({ orderId, buyerId, gtin: product.gtin });
    const prior = deliveryReplay.get(idempotencyKey);
    if (prior) {
      if (prior.fingerprint !== fingerprint) throw new TradeError('IDEMPOTENCY_CONFLICT', 'Scan key belongs to another observation.', 409);
      return { ...structuredClone(prior.result), idempotentReplay: true };
    }
    if (order.status !== 'SIMULATED_COMMITTED') throw new TradeError('ORDER_NOT_ACTIVE', 'Cannot scan against a cancelled order.', 409);
    const line = order.lines.find((item) => item.sku === product.sku);
    if (!line) throw new TradeError('PRODUCT_NOT_ON_ORDER', 'This barcode belongs to another product; no receipt recorded.', 409);
    const tally = deliveryObservations.get(orderId) ?? new Map();
    const previousUnits = tally.get(product.sku) ?? 0;
    if (previousUnits >= line.packs) throw new TradeError('RECEIPT_OVER_COUNT', 'The ordered quantity has already been observed.', 409);
    tally.set(product.sku, previousUnits + 1);
    deliveryObservations.set(orderId, tally);
    const receipt = record('ORDER_GTIN_OBSERVED', { orderId, sku: product.sku, gtin: product.gtin,
      observedCount: previousUnits + 1, orderedCount: line.packs, packLitres: line.packLitres,
      observedLitres: (previousUnits + 1) * line.packLitres, orderedLitres: line.quantityLitres, signedQuoteBodyDigest: order.verifiedQuoteBodyDigest,
      evidenceLevel: 'SELF_ATTESTED_SCAN_NOT_PROOF_OF_DELIVERY' });
    const result = { orderId, sku: product.sku, gtin: product.gtin,
      observedCount: previousUnits + 1, orderedCount: line.packs, packLitres: line.packLitres,
      observedLitres: (previousUnits + 1) * line.packLitres, orderedLitres: line.quantityLitres, receiptId: receipt.id,
      matchedSignedOrder: true, evidenceLevel: 'SELF_ATTESTED_SCAN_NOT_PROOF_OF_DELIVERY',
      idempotentReplay: false };
    deliveryReplay.set(idempotencyKey, { fingerprint, result });
    return structuredClone(result);
  };

  const buildQuote = ({ buyerId, requestText, need, budgetCents = policy.perOrderBudgetCents } = {}, reviewId = null) => {
    if (buyerId !== policy.buyerId) throw new TradeError('BUYER_NOT_FOUND', 'Only the fictional demo buyer is available.', 403);
    safeWhole(budgetCents, 1, policy.perOrderBudgetCents, 'Maximum budget');
    if (need !== undefined && requestText !== undefined) throw new TradeError('INVALID_NEED', 'Use typed need OR legacy text, never both.');
    const requested = need !== undefined ? validateBuyingNeed(need) : parseBuyerRequest(requestText);
    const sourceSnapshot = captureSnapshot(requested);
    let basket;
    try {
      basket = planPurchasableBasket({ catalog: sourceSnapshot.products, need: sourceSnapshot.constraints,
        deliveryFeeCents: policy.deliveryFeeCents ?? 0, taxBps: policy.taxBps ?? 0 });
    } catch (error) {
      if (!(error instanceof PurchaseUnitError)) throw error;
      const code = error.code === 'PACKING_CONSTRAINT' && error.details?.reason === 'INSUFFICIENT_PURCHASABLE_STOCK'
        ? 'INSUFFICIENT_AVAILABILITY' : error.code;
      record('QUOTE_REFUSED', { reason: code, details: error.details });
      throw new TradeError(code, error.message, 409, error.details);
    }
    const lines = basket.lines.map((line) => ({
      ...line, supplierId: sourceSnapshot.products.find((p) => p.sku === line.sku)?.supplierId ?? 'supplier-demo',
    }));
    const totalCents = basket.totalCents;
    if (totalCents > budgetCents && (!reviewId || totalCents > policy.perOrderBudgetCents)) {
      record('QUOTE_REFUSED', { reason: 'BUDGET_EXCEEDED', totalCents, budgetCents });
      throw new TradeError('BUDGET_EXCEEDED', 'Fixed-price basket exceeds the declared buyer budget.', 409, { totalCents, budgetCents, lines });
    }
    const quoteId = nextId('Q');
    const approvalRequired = totalCents > policy.autoCommitLimitCents || Boolean(reviewId && totalCents > budgetCents);
    const quote = {
      id: quoteId,
      buyerId,
      requested,
      lines,
      totalCents,
      budgetCents,
      costBreakdown: { subtotalCents: basket.subtotalCents, deliveryFeeCents: basket.deliveryFeeCents, taxCents: basket.taxCents, taxBps: basket.taxBps },
      reviewId,
      snapshotId: sourceSnapshot.id,
      sourceSnapshot,
      budgetException: totalCents > budgetCents ? {
        originalBudgetCents: budgetCents, proposedBudgetCents: totalCents,
        additionalCents: totalCents - budgetCents, scope: 'THIS_QUOTE_ONLY',
      } : null,
      approvalRequired,
      approval: null,
      status: approvalRequired ? 'AWAITING_HUMAN_APPROVAL' : 'AUTO_COMMIT_ELIGIBLE',
      createdAtMs: sourceSnapshot.observedAtMs,
      expiresAtMs: sourceSnapshot.observedAtMs + policy.quoteLifetimeMs,
      orderId: null,
      provider: 'INVENTED_LOCAL_CATALOG',
      explanation: 'Lowest unit price first among exact-family, dietary and delivery matches; split only when cheaper SKU stock is exhausted. No substitution. Prices are synthetic net cents; stock is checked, not reserved.',
    };
    quotes.set(quote.id, quote);
    record('QUOTE_CREATED', { quoteId, lines: lines.map((x) => ({ sku: x.sku, quantityLitres: x.quantityLitres, stockVersion: x.stockVersion })), totalCents, approvalRequired });
    return structuredClone(quote);
  };

  const requestQuote = (args) => buildQuote(args);
  const requestReview = ({ buyerId, requestText, need, budgetCents = policy.perOrderBudgetCents } = {}) => {
    if (buyerId !== policy.buyerId) throw new TradeError('BUYER_NOT_FOUND', 'Only the fictional demo buyer is available.', 403);
    safeWhole(budgetCents, 1, policy.perOrderBudgetCents, 'Maximum budget');
    if (need !== undefined && requestText !== undefined) throw new TradeError('INVALID_NEED', 'Use typed need OR legacy text, never both.');
    const requested = need !== undefined ? validateBuyingNeed(need) : parseBuyerRequest(requestText);
    const source = captureSnapshot(requested);
    const diagnosis = diagnoseProcurement({ catalog: source.products,
      requirements: [source.constraints], budgetCents, policyBudgetCents: source.policy.perOrderBudgetCents,
      deliveryFeeCents: policy.deliveryFeeCents ?? 0, taxBps: policy.taxBps ?? 0 });
    const reviewId = nextId('R');
    const quote = ['FEASIBLE_AT_SNAPSHOT', 'BUDGET_REVIEW_NEEDED'].includes(diagnosis.outcome)
      ? buildQuote({ buyerId, need: source.constraints, budgetCents }, reviewId) : null;
    const review = { id: reviewId, buyerId, snapshotId: quote?.snapshotId ?? source.id,
      sourceSnapshot: quote?.sourceSnapshot ?? source, requested: source.constraints,
      originalBudgetCents: budgetCents, diagnosis, quoteId: quote?.id ?? null,
      status: quote?.status ?? 'BLOCKED', expiresAtMs: quote?.expiresAtMs ?? source.observedAtMs + policy.quoteLifetimeMs };
    reviews.set(review.id, review);
    record('REVIEW_CREATED', { reviewId, snapshotId: review.snapshotId, quoteId: review.quoteId, outcome: diagnosis.outcome });
    return { review: structuredClone(review), quote };
  };

  const planBasket = ({ buyerId, requirements, budgetCents = policy.perOrderBudgetCents, ...unknown } = {}) => {
    if (Object.keys(unknown).length) throw new TradeError('INVALID_PORTFOLIO', 'Portfolio only accepts buyer, typed requirements and budget.');
    if (buyerId !== policy.buyerId) throw new TradeError('BUYER_NOT_FOUND', 'Only the fictional demo buyer is available.', 403);
    safeWhole(budgetCents, 1, policy.perOrderBudgetCents, 'Maximum budget');
    let planned;
    try { planned = planProcurementPortfolio({ catalog: catalogList(), requirements, budgetCents, deliveryFeeCents: policy.deliveryFeeCents ?? 0, taxBps: policy.taxBps ?? 0 }); }
    catch (error) {
      if (!(error instanceof PlannerFault)) throw error;
      record('PORTFOLIO_REFUSED', { reason: error.code, detail: error.details });
      throw new TradeError(error.code, error.message, error.code === 'INVALID_PORTFOLIO' ? 400 : 409, error.details);
    }
    const now = clock();
    const sourceSnapshot = captureSnapshot({ requirements: planned.requirements });
    const plan = { ...planned, sourceSnapshot, snapshotId: sourceSnapshot.id, id: nextId('P'), buyerId, createdAtMs: now, expiresAtMs: now + policy.quoteLifetimeMs, status: 'PROPOSED_NOT_ORDERED' };
    plans.set(plan.id, plan);
    record('PORTFOLIO_PLANNED', { planId: plan.id, variants: plan.options.map((option) => ({ id: option.id, totalCents: option.totalCents, supplierCount: option.supplierCount })), recommended: plan.recommendedOptionId });
    return structuredClone(plan);
  };

  const quoteBasketPlan = ({ buyerId, planId, optionId, ...unknown } = {}) => {
    if (Object.keys(unknown).length) throw new TradeError('ORDER_TERMS_FORBIDDEN', 'Only a server-held plan and option may be quoted.');
    const plan = plans.get(planId);
    if (!plan) throw new TradeError('PLAN_NOT_FOUND', 'Plan is unknown; create one from typed needs.', 404);
    if (buyerId !== plan.buyerId) throw new TradeError('BUYER_MISMATCH', 'Plan belongs to another buyer.', 403);
    if (clock() >= plan.expiresAtMs) throw new TradeError('PLAN_EXPIRED', 'Plan expired; replan with current source terms.', 409);
    if (plan.snapshotId !== captureSnapshot({ requirements: plan.requirements }).id) throw new TradeError('PLAN_STALE', 'Source terms or policy changed; replan first.', 409);
    const option = plan.options.find((candidate) => candidate.id === optionId);
    if (!option) throw new TradeError('OPTION_NOT_FOUND', 'Choose one of the server-owned portfolio options.', 404);
    if (!option.withinBudget) throw new TradeError('BUDGET_EXCEEDED', 'This plan option exceeds the declared budget.', 409);
    for (const line of option.lines) {
      const current = catalog.get(line.sku);
      if (!current || current.priceCents !== line.unitPriceCents || current.version !== line.stockVersion || current.unitsAvailable < line.quantityLitres) {
        throw new TradeError('PLAN_STALE', 'Portfolio must be replanned from new supplier facts.', 409, { sku: line.sku });
      }
    }
    const now = clock();
    const quote = { id: nextId('Q'), buyerId, planId, optionId, reviewId: null, budgetException: null,
      snapshotId: plan.snapshotId, sourceSnapshot: plan.sourceSnapshot, costBreakdown: structuredClone(option.costBreakdown),
      requested: { requirements: structuredClone(plan.requirements), mode: 'TYPED_PORTFOLIO' },
      lines: structuredClone(option.lines), totalCents: option.totalCents,
      budgetCents: plan.budgetCents, approvalRequired: option.totalCents > policy.autoCommitLimitCents,
      approval: null, status: option.totalCents > policy.autoCommitLimitCents ? 'AWAITING_HUMAN_APPROVAL' : 'AUTO_COMMIT_ELIGIBLE',
      createdAtMs: now, expiresAtMs: now + policy.quoteLifetimeMs, orderId: null,
      provider: 'INVENTED_LOCAL_CATALOG',
      explanation: `Server-held ${option.title.toLowerCase()} basket: ${option.explanation} Fixed synthetic prices, stock versions and policy are rechecked on commitment.` };
    quotes.set(quote.id, quote);
    record('PORTFOLIO_QUOTED', { planId, optionId, quoteId: quote.id, totalCents: quote.totalCents, approvalRequired: quote.approvalRequired });
    return structuredClone(quote);
  };

  const recoverPlan = ({ buyerId, planId, ...unknown } = {}) => {
    if (Object.keys(unknown).length) throw new TradeError('INVALID_PORTFOLIO', 'Recovery can only use original server-owned requirements.');
    const original = plans.get(planId);
    if (!original) throw new TradeError('PLAN_NOT_FOUND', 'Original plan not found.', 404);
    if (buyerId !== original.buyerId) throw new TradeError('BUYER_MISMATCH', 'Only the original buyer may replan.', 403);
    const recovered = planBasket({ buyerId, requirements: original.requirements, budgetCents: original.budgetCents });
    record('SUPPLY_SELF_HEALED', { fromPlanId: planId, toPlanId: recovered.id, buyerDecision: 'FRESH_DECISION_REQUIRED', changedOptions: recovered.options.map((x) => x.id) });
    return { ...recovered, recoveredFrom: planId, humanApprovalCarriedOver: false };
  };

  const recordVerifiedHandshake = ({ quoteId, verification }) => {
    const q = getQuote(quoteId);
    if (!verification || verification.valid !== true || verification.quoteId !== quoteId || verification.buyerId !== q.buyerId ||
        !Array.isArray(verification.signedBy) || verification.signedBy.length !== 2 ||
        typeof verification.signedOfferDigest !== 'string' || typeof verification.signedMandateDigest !== 'string') {
      throw new TradeError('INVALID_TRUST_EVIDENCE', 'Only a cryptographically verified quote-bound receipt may extend the audit.', 409);
    }
    q.verifiedHandshake = { quoteBodyDigest: verification.quoteBodyDigest,
      signedOfferDigest: verification.signedOfferDigest,
      signedMandateDigest: verification.signedMandateDigest };
    return record('TRUST_HANDSHAKE_VERIFIED', {
      quoteId, buyerId: q.buyerId, signedOfferDigest: verification.signedOfferDigest,
      signedMandateDigest: verification.signedMandateDigest, quoteBodyDigest: verification.quoteBodyDigest,
      signingKeyIds: verification.signedBy, keys: 'UNVERIFIED_SELF_ATTESTED_DEMO', verified: true,
    });
  };

  const assertFresh = (q) => {
    if (clock() >= q.expiresAtMs) throw new TradeError('QUOTE_EXPIRED', 'Quote expired; request new fixed prices and stock.', 409);
    if (q.snapshotId !== captureSnapshot(q.requested).id) {
      throw new TradeError('QUOTE_STALE', 'Source prices, stock or policy changed. Obtain a fresh quote and decision.', 409);
    }
    for (const line of q.lines) {
      const current = catalog.get(line.sku);
      if (!current || current.version !== line.stockVersion || current.priceCents !== line.unitPriceCents || current.unitsAvailable < line.quantityLitres) {
        throw new TradeError('QUOTE_STALE', 'Catalog price or availability changed. Old approval cannot be used.', 409, { sku: line.sku });
      }
    }
  };

  const recordDecision = ({ quoteId, decision, buyerId, approver = 'Fictional buyer', boundReviewId = null }) => {
    const q = getQuote(quoteId);
    if (buyerId !== q.buyerId) throw new TradeError('BUYER_MISMATCH', 'Approval must match the original buyer.', 403);
    if (q.reviewId && q.reviewId !== boundReviewId) {
      throw new TradeError('REVIEW_CONFIRMATION_REQUIRED', 'Confirm the exact review, quote and snapshot before deciding.', 403);
    }
    if (q.orderId) throw new TradeError('ALREADY_COMMITTED', 'The quote has already been used.', 409);
    assertFresh(q);
    if (!['approve', 'reject'].includes(decision)) throw new TradeError('INVALID_DECISION', 'Choose approve or reject.');
    if (typeof approver !== 'string' || !approver.trim() || approver.length > 80) throw new TradeError('INVALID_APPROVER', 'Provide a short fictional reviewer label.');
    if (q.approval) throw new TradeError('ALREADY_DECIDED', 'Decision already recorded; make a fresh quote.', 409);
    if (q.status !== 'AWAITING_HUMAN_APPROVAL') throw new TradeError('NO_APPROVAL_NEEDED', 'This quote does not request a human approval.', 409);
    q.approval = { decision, approver: approver.trim(), at: new Date(clock()).toISOString(), simulatedIdentity: true,
      quoteId: q.id, snapshotId: q.snapshotId, reviewId: q.reviewId, totalCents: q.totalCents,
      additionalBudgetCents: q.budgetException?.additionalCents ?? 0 };
    q.status = decision === 'approve' ? 'APPROVED' : 'REJECTED';
    record('HUMAN_DECISION_SIMULATED', { quoteId: q.id, decision, approver: q.approval.approver, snapshotId: q.snapshotId, reviewId: q.reviewId, additionalBudgetCents: q.approval.additionalBudgetCents });
    return structuredClone(q);
  };

  const decideApproval = (args) => recordDecision({ ...args, boundReviewId: null });
  const decideReview = ({ reviewId, buyerId, decision, snapshotId, quoteId, ...extra } = {}) => {
    if (Object.keys(extra).length) throw new TradeError('INVALID_REVIEW_DECISION', 'Only the displayed review and source identifiers may be confirmed.');
    const review = getReview(reviewId);
    if (review.buyerId !== buyerId) throw new TradeError('BUYER_MISMATCH', 'Review belongs to another buyer.', 403);
    if (!review.quoteId) throw new TradeError('REVIEW_BLOCKED', 'Missing stock or policy limits cannot be approved here.', 409);
    if (snapshotId !== review.snapshotId || quoteId !== review.quoteId) {
      throw new TradeError('REVIEW_MISMATCH', 'Decision does not match the displayed quote and source snapshot.', 409);
    }
    const quote = recordDecision({ quoteId, buyerId, decision, boundReviewId: review.id,
      approver: 'Review card demo buyer (UNAUTHENTICATED)' });
    review.status = quote.status;
    return { review: structuredClone(review), quote };
  };

  const commitOrder = ({ quoteId, buyerId, idempotencyKey, ...extra } = {}) => {
    if (Object.keys(extra).length) throw new TradeError('ORDER_TERMS_FORBIDDEN', 'Order accepts only quoteId, buyerId and idempotencyKey; terms are server-owned.');
    if (typeof idempotencyKey !== 'string' || !/^[A-Za-z0-9_-]{10,80}$/.test(idempotencyKey)) {
      throw new TradeError('INVALID_IDEMPOTENCY_KEY', 'Supply a stable unique 10–80 character idempotency key.');
    }
    const fingerprint = digestLike({ quoteId, buyerId });
    const prior = idempotency.get(idempotencyKey);
    if (prior) {
      if (prior.fingerprint !== fingerprint) throw new TradeError('IDEMPOTENCY_CONFLICT', 'Idempotency key was already used for a different order.', 409);
      record('ORDER_REPLAYED', { orderId: prior.orderId, quoteId });
      return { ...structuredClone(getOrder(prior.orderId)), idempotentReplay: true };
    }
    const q = getQuote(quoteId);
    if (q.buyerId !== buyerId) throw new TradeError('BUYER_MISMATCH', 'Buyer does not match the quote.', 403);
    if (q.orderId) throw new TradeError('ALREADY_COMMITTED', 'A quote can produce one order.', 409);
    if (q.status === 'REJECTED') throw new TradeError('APPROVAL_REJECTED', 'The buyer refused the quote.', 403);
    if (q.approvalRequired && q.status !== 'APPROVED') throw new TradeError('APPROVAL_REQUIRED', 'A human buyer decision is required before order commitment.', 403);
    if (!q.approvalRequired && q.status !== 'AUTO_COMMIT_ELIGIBLE') throw new TradeError('QUOTE_STATE_INVALID', 'The quote cannot be committed.', 409);
    if (q.reviewId && q.approvalRequired && (q.approval?.reviewId !== q.reviewId ||
        q.approval?.snapshotId !== q.snapshotId || q.approval?.quoteId !== q.id || q.approval?.totalCents !== q.totalCents)) {
      throw new TradeError('REVIEW_CONFIRMATION_REQUIRED', 'The approved decision must match these exact terms.', 403);
    }
    assertFresh(q);
    for (const line of q.lines) {
      const item = catalog.get(line.sku);
      item.unitsAvailable -= line.quantityLitres;
      item.version += 1;
    }
    const orderId = nextId('O');
    const order = {
      id: orderId,
      buyerId,
      quoteId,
      snapshotId: q.snapshotId,
      reviewId: q.reviewId,
      lines: structuredClone(q.lines),
      costBreakdown: structuredClone(q.costBreakdown),
      totalCents: q.totalCents,
      status: 'SIMULATED_COMMITTED',
      createdAt: new Date(clock()).toISOString(),
      commitment: 'SIMULATION_ONLY_NO_REAL_PURCHASE',
      paymentEligible: Boolean(q.verifiedHandshake),
      verifiedQuoteBodyDigest: q.verifiedHandshake?.quoteBodyDigest ?? null,
      humanDecision: q.approval ? structuredClone(q.approval) : null,
    };
    orders.set(orderId, order);
    idempotency.set(idempotencyKey, { fingerprint, orderId });
    q.status = 'SIMULATED_COMMITTED';
    q.orderId = orderId;
    record('ORDER_SIMULATED', { orderId, quoteId, totalCents: q.totalCents, approved: Boolean(q.approval), idempotencyKey });
    return { ...structuredClone(order), idempotentReplay: false };
  };

  const cancelOrder = ({ orderId, buyerId }) => {
    const o = getOrder(orderId);
    if (o.buyerId !== buyerId) throw new TradeError('BUYER_MISMATCH', 'Only this demo buyer may cancel the order.', 403);
    if (o.status === 'SIMULATED_CANCELLED') return structuredClone(o);
    if (o.status !== 'SIMULATED_COMMITTED') throw new TradeError('CANNOT_CANCEL', 'Order is not cancelable.', 409);
    // In this deliberately in-memory fixture, cancellation reverses all posted
    // supplier transfers before stock is restored. Nothing reaches a bank.
    settlement.refundForCancellation(o);
    for (const line of o.lines) {
      const item = catalog.get(line.sku);
      item.unitsAvailable += line.quantityLitres;
      item.version += 1;
    }
    o.status = 'SIMULATED_CANCELLED';
    record('ORDER_CANCELLED_SIMULATED', { orderId });
    return structuredClone(o);
  };

  const simulatePriceChange = ({ sku, priceCents }) => {
    const p = catalog.get(sku);
    if (!p) throw new TradeError('SKU_NOT_FOUND', 'Unknown synthetic product.', 404);
    safeWhole(priceCents, 1, 100_000, 'Price');
    p.priceCents = priceCents;
    p.version += 1;
    record('DEMO_STOCK_SOURCE_CHANGED', { sku, priceCents, version: p.version });
    return { ...p };
  };

  const simulateStockShock = ({ sku, unitsAvailable, ...unknown } = {}) => {
    if (Object.keys(unknown).length) throw new TradeError('INVALID_STOCK_CHANGE', 'Only SKU and integer stock may be changed in this simulation.');
    const p = catalog.get(sku);
    if (!p) throw new TradeError('SKU_NOT_FOUND', 'Unknown synthetic product.', 404);
    safeWhole(unitsAvailable, 0, 1_000_000, 'Available litres');
    const committedUnits = [...orders.values()].filter((order) => order.status === 'SIMULATED_COMMITTED')
      .reduce((sum, order) => sum + order.lines.filter((line) => line.sku === sku).reduce((units, line) => units + line.quantityLitres, 0), 0);
    if (unitsAvailable + committedUnits > 1_000_000) {
      throw new TradeError('STOCK_CAPACITY_EXCEEDED', 'Available stock plus cancellable allocations must stay within the fixture stock limit.', 409);
    }
    const previousUnitsAvailable = p.unitsAvailable;
    p.unitsAvailable = unitsAvailable;
    p.version += 1;
    record('DEMO_SUPPLIER_DISRUPTION', { sku, previousUnitsAvailable, unitsAvailable, version: p.version, type: 'INVENTED_STOCK_SHOCK' });
    return { ...p };
  };

  return Object.freeze({
    exportState: () => structuredClone({ kind: 'trade-service', version: 1, catalog: [...catalog], quotes: [...quotes], plans: [...plans], orders: [...orders], reviews: [...reviews],
      sourceEpoch, idempotency: [...idempotency], deliveryObservations: [...deliveryObservations].map(([id, tally]) => [id, [...tally]]),
      deliveryReplay: [...deliveryReplay], audit, serial, policy, settlement: settlement.exportState() }),
    catalog: catalogList,
    resolveProductScan,
    scanDelivery,
    policy: () => ({ ...policy, provider: 'FIXTURE_ONLY', approverAuthentication: 'NOT_IMPLEMENTED' }),
    requestQuote,
    requestReview,
    decideReview,
    planBasket,
    quoteBasketPlan,
    recoverPlan,
    assertQuoteFresh: (quoteId) => { assertFresh(getQuote(quoteId)); return true; },
    quote: (id) => structuredClone(getQuote(id)),
    approve: decideApproval,
    order: (id) => structuredClone(getOrder(id)),
    commitOrder,
    cancelOrder,
    payment: settlement.payment,
    demoWallet: settlement.wallet,
    approvePayment: settlement.approve,
    settlePayment: settlement.settle,
    paymentJournal: settlement.journal,
    paymentJournalVerify: settlement.verify,
    simulatePriceChange,
    simulateStockShock,
    audit: () => structuredClone(audit),
    auditVerify: () => verifyAuditChain(audit),
    recordVerifiedHandshake,
    recordRefusal: (code, path) => record('HTTP_REFUSED', { reason: code, path }),
  });
}
