/**
 * Trusted Trade — deterministic buyer-side control plane.
 * All products, stock, people and orders are invented demo data.
 * No calls to Valio or a production purchasing system are made.
 */

export const FIXTURE_CATALOG = Object.freeze([
  { sku: 'DEMO-LF-1', name: 'Lactose-free dairy milk · 1 L', family: 'dairy-milk', lactoseFree: true, unitsAvailable: 780, priceCents: 174, deliverBy: '2026-11-16', certification: 'Finnish origin · fictional', version: 1 },
  { sku: 'DEMO-LF-2', name: 'Lactose-free dairy milk · 1 L', family: 'dairy-milk', lactoseFree: true, unitsAvailable: 900, priceCents: 189, deliverBy: '2026-11-16', certification: 'Animal welfare · fictional', version: 1 },
  { sku: 'DEMO-LF-3', name: 'Organic lactose-free dairy milk · 1 L', family: 'dairy-milk', lactoseFree: true, unitsAvailable: 140, priceCents: 217, deliverBy: '2026-11-17', certification: 'Organic · fictional', version: 1 },
  { sku: 'DEMO-REG-1', name: 'Standard dairy milk · 1 L', family: 'dairy-milk', lactoseFree: false, unitsAvailable: 1900, priceCents: 143, deliverBy: '2026-11-16', certification: 'Finnish origin · fictional', version: 1 },
  { sku: 'DEMO-OAT-1', name: 'Oat drink · 1 L', family: 'oat-drink', lactoseFree: true, unitsAvailable: 2100, priceCents: 162, deliverBy: '2026-11-16', certification: 'Plant-based · fictional', version: 1 },
]);

export const FIXTURE_POLICY = Object.freeze({
  buyerId: 'helsinki-hotel-demo',
  name: 'Hotel North · demonstration only',
  autoCommitLimitCents: 75_000,
  perOrderBudgetCents: 250_000,
  quoteLifetimeMs: 120_000,
  substitutionsRequireApproval: true,
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

/** No LLM claims: the demo deliberately accepts only the supported request shape. */
export function parseBuyerRequest(raw) {
  if (typeof raw !== 'string' || raw.length > 1000) {
    throw new TradeError('INVALID_REQUEST', 'Enter one short purchasing request.');
  }
  const matched = raw.match(/(?:^|\W)(\d[\d,\s]*)(?:\s*)(?:litres?|liters?|l)\b/i);
  if (!matched) {
    throw new TradeError('UNSUPPORTED_REQUEST', 'State a whole litre quantity, for example 1,000 L.');
  }
  const quantityLitres = Number(matched[1].replace(/[\s,]/g, ''));
  safeWhole(quantityLitres, 1, 10_000, 'Quantity');
  if (!/lactose[\s-]*free/i.test(raw) || !/milk/i.test(raw)) {
    throw new TradeError('UNSUPPORTED_REQUEST', 'This demo supports lactose-free dairy milk only; it will not guess another product.');
  }
  return {
    quantityLitres,
    family: 'dairy-milk',
    lactoseFree: true,
    deliverBy: '2026-11-16',
    parsedFrom: raw.slice(0, 200),
  };
}

export function createTradeService({ initialCatalog = FIXTURE_CATALOG, policy = FIXTURE_POLICY, clock = () => Date.now() } = {}) {
  const catalog = new Map(initialCatalog.map((item) => [item.sku, { ...item }]));
  const quotes = new Map();
  const orders = new Map();
  const idempotency = new Map();
  const audit = [];
  let serial = 0;
  const nextId = (prefix) => `${prefix}-DEMO-${String(++serial).padStart(4, '0')}`;
  const record = (event, detail) => {
    const receipt = { id: nextId('EV'), time: new Date(clock()).toISOString(), event, detail };
    audit.push(receipt);
    return receipt;
  };
  const catalogList = () => [...catalog.values()].map((x) => ({ ...x }));
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

  const requestQuote = ({ buyerId, requestText, budgetCents = policy.perOrderBudgetCents } = {}) => {
    if (buyerId !== policy.buyerId) throw new TradeError('BUYER_NOT_FOUND', 'Only the fictional demo buyer is available.', 403);
    safeWhole(budgetCents, 1, policy.perOrderBudgetCents, 'Maximum budget');
    const requested = parseBuyerRequest(requestText);
    const suitable = catalogList().filter((x) => x.family === requested.family && x.lactoseFree && x.deliverBy <= requested.deliverBy);
    suitable.sort((a, b) => a.priceCents - b.priceCents || a.sku.localeCompare(b.sku));
    let remaining = requested.quantityLitres;
    const lines = [];
    for (const item of suitable) {
      if (remaining <= 0) break;
      const quantity = Math.min(remaining, item.unitsAvailable);
      if (quantity) {
        lines.push({ sku: item.sku, name: item.name, quantityLitres: quantity, unitPriceCents: item.priceCents, totalCents: quantity * item.priceCents, stockVersion: item.version, certification: item.certification, deliverBy: item.deliverBy });
        remaining -= quantity;
      }
    }
    if (remaining) {
      record('QUOTE_REFUSED', { reason: 'INSUFFICIENT_AVAILABILITY', missingLitres: remaining });
      throw new TradeError('INSUFFICIENT_AVAILABILITY', `Cannot deliver ${requested.quantityLitres} L by ${requested.deliverBy}: ${remaining} L unavailable.`, 409, { missingLitres: remaining, viableLines: lines });
    }
    const totalCents = lines.reduce((sum, item) => sum + item.totalCents, 0);
    if (totalCents > budgetCents) {
      record('QUOTE_REFUSED', { reason: 'BUDGET_EXCEEDED', totalCents, budgetCents });
      throw new TradeError('BUDGET_EXCEEDED', 'Fixed-price basket exceeds the declared buyer budget.', 409, { totalCents, budgetCents, lines });
    }
    const quoteId = nextId('Q');
    const approvalRequired = totalCents > policy.autoCommitLimitCents;
    const quote = {
      id: quoteId,
      buyerId,
      requested,
      lines,
      totalCents,
      budgetCents,
      approvalRequired,
      approval: null,
      status: approvalRequired ? 'AWAITING_HUMAN_APPROVAL' : 'AUTO_COMMIT_ELIGIBLE',
      createdAtMs: clock(),
      expiresAtMs: clock() + policy.quoteLifetimeMs,
      orderId: null,
      provider: 'INVENTED_LOCAL_CATALOG',
    };
    quotes.set(quote.id, quote);
    record('QUOTE_CREATED', { quoteId, lines: lines.map((x) => ({ sku: x.sku, quantityLitres: x.quantityLitres, stockVersion: x.stockVersion })), totalCents, approvalRequired });
    return structuredClone(quote);
  };

  const assertFresh = (q) => {
    if (clock() >= q.expiresAtMs) throw new TradeError('QUOTE_EXPIRED', 'Quote expired; request new fixed prices and stock.', 409);
    for (const line of q.lines) {
      const current = catalog.get(line.sku);
      if (!current || current.version !== line.stockVersion || current.priceCents !== line.unitPriceCents || current.unitsAvailable < line.quantityLitres) {
        throw new TradeError('QUOTE_STALE', 'Catalog price or availability changed. Old approval cannot be used.', 409, { sku: line.sku });
      }
    }
  };

  const decideApproval = ({ quoteId, decision, buyerId, approver = 'Fictional buyer' }) => {
    const q = getQuote(quoteId);
    if (buyerId !== q.buyerId) throw new TradeError('BUYER_MISMATCH', 'Approval must match the original buyer.', 403);
    if (q.orderId) throw new TradeError('ALREADY_COMMITTED', 'The quote has already been used.', 409);
    assertFresh(q);
    if (!['approve', 'reject'].includes(decision)) throw new TradeError('INVALID_DECISION', 'Choose approve or reject.');
    if (typeof approver !== 'string' || !approver.trim() || approver.length > 80) throw new TradeError('INVALID_APPROVER', 'Provide a short fictional reviewer label.');
    if (q.approval) throw new TradeError('ALREADY_DECIDED', 'Decision already recorded; make a fresh quote.', 409);
    if (q.status !== 'AWAITING_HUMAN_APPROVAL') throw new TradeError('NO_APPROVAL_NEEDED', 'This quote does not request a human approval.', 409);
    q.approval = { decision, approver: approver.trim(), at: new Date(clock()).toISOString(), simulatedIdentity: true };
    q.status = decision === 'approve' ? 'APPROVED' : 'REJECTED';
    record('HUMAN_DECISION_SIMULATED', { quoteId: q.id, decision, approver: q.approval.approver });
    return structuredClone(q);
  };

  const commitOrder = ({ quoteId, buyerId, idempotencyKey } = {}) => {
    if (typeof idempotencyKey !== 'string' || !/^[A-Za-z0-9_-]{10,80}$/.test(idempotencyKey)) {
      throw new TradeError('INVALID_IDEMPOTENCY_KEY', 'Supply a stable unique 10–80 character idempotency key.');
    }
    const fingerprint = digestLike({ quoteId, buyerId });
    const prior = idempotency.get(idempotencyKey);
    if (prior) {
      if (prior.fingerprint !== fingerprint) throw new TradeError('IDEMPOTENCY_CONFLICT', 'Idempotency key was already used for a different order.', 409);
      return { ...structuredClone(getOrder(prior.orderId)), idempotentReplay: true };
    }
    const q = getQuote(quoteId);
    if (q.buyerId !== buyerId) throw new TradeError('BUYER_MISMATCH', 'Buyer does not match the quote.', 403);
    if (q.orderId) throw new TradeError('ALREADY_COMMITTED', 'A quote can produce one order.', 409);
    if (q.status === 'REJECTED') throw new TradeError('APPROVAL_REJECTED', 'The buyer refused the quote.', 403);
    if (q.approvalRequired && q.status !== 'APPROVED') throw new TradeError('APPROVAL_REQUIRED', 'A human buyer decision is required before order commitment.', 403);
    if (!q.approvalRequired && q.status !== 'AUTO_COMMIT_ELIGIBLE') throw new TradeError('QUOTE_STATE_INVALID', 'The quote cannot be committed.', 409);
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
      lines: structuredClone(q.lines),
      totalCents: q.totalCents,
      status: 'SIMULATED_COMMITTED',
      createdAt: new Date(clock()).toISOString(),
      commitment: 'SIMULATION_ONLY_NO_REAL_PURCHASE',
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

  return Object.freeze({
    catalog: catalogList,
    policy: () => ({ ...policy, provider: 'FIXTURE_ONLY', approverAuthentication: 'NOT_IMPLEMENTED' }),
    requestQuote,
    quote: (id) => structuredClone(getQuote(id)),
    approve: decideApproval,
    order: (id) => structuredClone(getOrder(id)),
    commitOrder,
    cancelOrder,
    simulatePriceChange,
    audit: () => structuredClone(audit),
  });
}
