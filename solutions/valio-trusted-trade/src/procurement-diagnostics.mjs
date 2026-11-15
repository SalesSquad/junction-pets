/**
 * Read-only, snapshot-bound explanations for the invented procurement catalog.
 * This module cannot issue a quote, change policy, approve or place an order.
 */
export class DiagnosticError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'DiagnosticError';
    this.code = code;
  }
}
const fail = (code, message) => { throw new DiagnosticError(code, message); };
const whole = (n, min, max) => Number.isSafeInteger(n) && n >= min && n <= max;
const families = ['dairy-milk', 'oat-drink'];
const day = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;

function validateRequirements(requirements) {
  if (!Array.isArray(requirements) || requirements.length < 1 || requirements.length > 2) {
    fail('INVALID_REQUIREMENTS', 'Provide one or two distinct typed product families.');
  }
  const seen = new Set();
  return requirements.map((need) => {
    if (!need || Array.isArray(need) || typeof need !== 'object' ||
        Object.keys(need).some((key) => !['family', 'quantityLitres', 'lactoseFree', 'deliverBy'].includes(key)) ||
        !families.includes(need.family) || seen.has(need.family) ||
        !whole(need.quantityLitres, 1, 10_000) || typeof need.lactoseFree !== 'boolean' ||
        need.deliverBy !== '2026-11-16') {
      fail('INVALID_REQUIREMENTS', 'Use distinct supported families, whole litres, an explicit dietary flag and fixture date 2026-11-16.');
    }
    seen.add(need.family);
    return { family: need.family, quantityLitres: need.quantityLitres, lactoseFree: need.lactoseFree, deliverBy: need.deliverBy };
  });
}

function validateCatalog(catalog) {
  if (!Array.isArray(catalog) || catalog.length > 10_000) {
    fail('INVALID_CATALOG', 'Expected a bounded array of versioned synthetic product facts.');
  }
  const seen = new Set();
  for (const product of catalog) {
    if (!product || typeof product !== 'object' || Array.isArray(product) ||
        typeof product.sku !== 'string' || !product.sku.trim() || product.sku.length > 128 ||
        seen.has(product.sku) || !families.includes(product.family) ||
        typeof product.lactoseFree !== 'boolean' || !day(product.deliverBy) ||
        !whole(product.unitsAvailable, 0, 1_000_000) ||
        !whole(product.priceCents, 1, 1_000_000) || !whole(product.version, 1, 1_000_000)) {
      fail('INVALID_CATALOG', 'Incomplete, duplicate or invalid product facts; no price, stock, dietary or delivery values are inferred.');
    }
    seen.add(product.sku);
  }
}

const bySku = (a, b) => a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0;

/**
 * Minimum cost is exact only for this whole-litre, linear unit-price fixture.
 * There are no freight, tax, package-size, reservation or external stock claims.
 * Insufficient stock never produces a supposed price for the complete need.
 */
export function diagnoseProcurement({ catalog, requirements, budgetCents, policyBudgetCents } = {}) {
  const typed = validateRequirements(requirements);
  validateCatalog(catalog);
  if (!whole(policyBudgetCents, 1, 5_000_000) || !whole(budgetCents, 1, policyBudgetCents)) {
    fail('INVALID_BUDGET', 'Use integer cents within the existing server-owned budget ceiling.');
  }
  const perFamily = typed.map((need) => {
    const eligible = [];
    const excludedProducts = [];
    for (const product of catalog) {
      if (product.family !== need.family) continue;
      const reasons = [];
      if (need.lactoseFree && !product.lactoseFree) reasons.push('DIETARY_MISMATCH');
      if (product.deliverBy > need.deliverBy) reasons.push('DELIVERY_TOO_LATE');
      if (!product.unitsAvailable) reasons.push('OUT_OF_STOCK');
      if (reasons.length) excludedProducts.push({ sku: product.sku, reasons });
      else eligible.push(product);
    }
    eligible.sort((a, b) => a.priceCents - b.priceCents || bySku(a, b));
    const availableLitres = eligible.reduce((sum, product) => sum + product.unitsAvailable, 0);
    let remaining = need.quantityLitres;
    const lines = [];
    for (const product of eligible) {
      const quantityLitres = Math.min(remaining, product.unitsAvailable);
      if (!quantityLitres) break;
      lines.push({
        sku: product.sku, family: product.family, quantityLitres,
        unitPriceCents: product.priceCents, totalCents: quantityLitres * product.priceCents,
        stockVersion: product.version, deliverBy: product.deliverBy,
      });
      remaining -= quantityLitres;
    }
    const partialBasketCostCents = lines.reduce((sum, line) => sum + line.totalCents, 0);
    return {
      ...need, availableLitres, missingLitres: remaining, lines,
      minimumCostCents: remaining ? null : partialBasketCostCents,
      partialBasketCostCents, excludedProducts: excludedProducts.sort(bySku),
    };
  });
  const missingLitres = perFamily.reduce((sum, item) => sum + item.missingLitres, 0);
  const minimumCostCents = missingLitres ? null :
    perFamily.reduce((sum, item) => sum + item.minimumCostCents, 0);
  const additionalBudgetCents = minimumCostCents === null ? null : Math.max(0, minimumCostCents - budgetCents);
  const outcome = missingLitres ? 'STOCK_SHORTFALL' :
    minimumCostCents > policyBudgetCents ? 'POLICY_LIMIT_EXCEEDED' :
    additionalBudgetCents ? 'BUDGET_REVIEW_NEEDED' : 'FEASIBLE_AT_SNAPSHOT';
  return {
    schema: 'trusted-trade.procurement-diagnostics.v1',
    mode: 'SYNTHETIC_NONCOMMERCIAL',
    adviceOnly: true, isQuote: false, grantsAuthority: false,
    outcome, currency: 'EUR', budgetCents, policyBudgetCents, minimumCostCents,
    additionalBudgetCents, missingLitres, requirements: typed, perFamily,
    budgetReview: additionalBudgetCents ? {
      targetBudgetCents: minimumCostCents, additionalCents: additionalBudgetCents,
      withinExistingPolicy: minimumCostCents <= policyBudgetCents,
      action: minimumCostCents <= policyBudgetCents ? 'REQUEST_BUYER_BUDGET_REVIEW' : 'REFER_TO_POLICY_OWNER',
    } : null,
    explanation: {
      STOCK_SHORTFALL: 'Exact-match stock is insufficient. More budget cannot resolve this snapshot; no full-basket price is claimed.',
      POLICY_LIMIT_EXCEEDED: 'The cheapest complete basket exceeds the server policy ceiling. This advice cannot change that policy.',
      BUDGET_REVIEW_NEEDED: 'A complete basket exists, but the stated budget needs explicit review. This is not approval or a quote.',
      FEASIBLE_AT_SNAPSHOT: 'A complete basket fits the stated budget at this snapshot. Obtain a fresh server quote and all required approvals.',
    }[outcome],
    sourceVersions: catalog.map(({ sku, version, priceCents, unitsAvailable, family, lactoseFree, deliverBy }) =>
      ({ sku, version, priceCents, unitsAvailable, family, lactoseFree, deliverBy })).sort(bySku),
    validity: 'SNAPSHOT_ONLY_NOT_RESERVED; fresh server validation and approval remain mandatory.',
    costModel: 'Invented linear net EUR cents per whole litre; no freight, tax, pack sizes or real supplier guarantees.',
  };
}
