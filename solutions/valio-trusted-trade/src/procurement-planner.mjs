/**
 * Deterministic whole-litre procurement portfolio planner.
 * Every supplier, quality score, stock figure and carbon estimate is fictional.
 * The policy checks and quote/commit gates live in core.mjs, not in this planner.
 */

export class PlannerFault extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

const whole = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
const round1 = (value) => Math.round(value * 10) / 10;

export function validatePortfolioRequirements(requirements) {
  if (!Array.isArray(requirements) || requirements.length !== 2) {
    throw new PlannerFault('INVALID_PORTFOLIO', 'This two-family demo needs exactly two typed product requirements.');
  }
  const seen = new Set();
  return requirements.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item) ||
        Object.keys(item).some((key) => !['family', 'quantityLitres', 'lactoseFree', 'deliverBy'].includes(key)) ||
        !['dairy-milk', 'oat-drink'].includes(item.family) || seen.has(item.family) ||
        typeof item.lactoseFree !== 'boolean' || item.deliverBy !== '2026-11-16' ||
        !whole(item.quantityLitres, 1, 10_000)) {
      throw new PlannerFault('INVALID_PORTFOLIO', 'Unsupported family, duplicate family, non-whole quantity, dietary flag or delivery date.');
    }
    seen.add(item.family);
    return { family: item.family, quantityLitres: item.quantityLitres, lactoseFree: item.lactoseFree, deliverBy: item.deliverBy };
  });
}

const metrics = (offer) => ({
  supplierId: offer.supplierId ?? `fictional-${offer.sku}`,
  reliabilityBps: offer.reliabilityBps ?? 9500,
  emissionsGramsPerL: offer.emissionsGramsPerL ?? 1000,
});

function selectLines(catalog, requirements, mode) {
  const lines = [];
  for (const requirement of requirements) {
    const eligible = catalog.filter((product) => product.family === requirement.family &&
      (!requirement.lactoseFree || product.lactoseFree) &&
      product.deliverBy <= requirement.deliverBy && whole(product.unitsAvailable, 0, 1_000_000) &&
      whole(product.priceCents, 1, 1_000_000) && product.unitsAvailable > 0 &&
      whole(product.version, 1, 1_000_000) &&
      whole(metrics(product).reliabilityBps, 1, 10_000) && whole(metrics(product).emissionsGramsPerL, 1, 100_000));
    if (!eligible.length || eligible.reduce((sum, product) => sum + product.unitsAvailable, 0) < requirement.quantityLitres) {
      throw new PlannerFault('INSUFFICIENT_AVAILABILITY', `There is not enough exact-match ${requirement.family} for ${requirement.quantityLitres} L.`, { family: requirement.family });
    }
    const byCost = (a, b) => a.priceCents - b.priceCents || a.sku.localeCompare(b.sku);
    const byFootprint = (a, b) => metrics(a).emissionsGramsPerL - metrics(b).emissionsGramsPerL || byCost(a, b);
    const byReliability = (a, b) => metrics(b).reliabilityBps - metrics(a).reliabilityBps || byCost(a, b);
    const sorted = [...eligible].sort(mode === 'footprint' ? byFootprint : mode === 'resilience' ? byReliability : byCost);
    const allocation = new Map();
    const allocate = (product, quantity) => {
      const reserved = allocation.get(product.sku) ?? 0;
      const units = Math.min(quantity, product.unitsAvailable - reserved);
      if (units > 0) allocation.set(product.sku, reserved + units);
      return units;
    };
    let remaining = requirement.quantityLitres;
    if (mode === 'resilience') {
      // Diversify the eligible category across distinct suppliers where possible.
      // Allocation is a bounded 60/40 target, not a probabilistic guarantee.
      const distinct = sorted.filter((candidate, index, list) => list.findIndex((x) => metrics(x).supplierId === metrics(candidate).supplierId) === index);
      if (distinct.length > 1 && remaining > 1) {
        remaining -= allocate(distinct[0], Math.ceil(remaining * 0.60));
        remaining -= allocate(distinct[1], Math.min(remaining, Math.floor(requirement.quantityLitres * 0.40)));
      }
    }
    for (const product of sorted) {
      if (!remaining) break;
      remaining -= allocate(product, remaining);
    }
    if (remaining) throw new PlannerFault('INSUFFICIENT_AVAILABILITY', `Unable to fill exact ${requirement.family} requirement.`, { missingLitres: remaining });
    for (const product of sorted) {
      const quantityLitres = allocation.get(product.sku) ?? 0;
      if (!quantityLitres) continue;
      lines.push({ sku: product.sku, name: product.name, family: product.family,
        supplierId: metrics(product).supplierId, quantityLitres, unitPriceCents: product.priceCents,
        totalCents: quantityLitres * product.priceCents, stockVersion: product.version,
        certification: product.certification, deliverBy: product.deliverBy,
        reliabilityBps: metrics(product).reliabilityBps, emissionsGramsPerL: metrics(product).emissionsGramsPerL });
    }
  }
  return lines;
}

export function planProcurementPortfolio({ catalog, requirements, budgetCents }) {
  const typed = validatePortfolioRequirements(requirements);
  if (!Array.isArray(catalog) || !whole(budgetCents, 1, 5_000_000)) {
    throw new PlannerFault('INVALID_PORTFOLIO', 'A valid catalog and integer-cent budget are required.');
  }
  const totalLitres = typed.reduce((sum, need) => sum + need.quantityLitres, 0);
  const modes = [
    { id: 'cost', title: 'Lowest cost', explanation: 'Cheapest exact-match inventory in whole litres, without unapproved substitutes.' },
    { id: 'resilience', title: 'Resilient supply', explanation: 'Use two independent fictional suppliers for a category where available, with reliability-first fallback.' },
    { id: 'footprint', title: 'Lower footprint', explanation: 'Choose the lowest fictional per-litre emission factor while obeying delivery, diet and stock limits.' },
  ];
  const candidates = modes.map((mode) => {
    const lines = selectLines(catalog, typed, mode.id);
    const totalCents = lines.reduce((sum, line) => sum + line.totalCents, 0);
    const grams = lines.reduce((sum, line) => sum + line.quantityLitres * line.emissionsGramsPerL, 0);
    const supplierUnits = new Map();
    for (const line of lines) supplierUnits.set(line.supplierId, (supplierUnits.get(line.supplierId) ?? 0) + line.quantityLitres);
    return {
      ...mode, lines, totalCents, currency: 'EUR', totalLitres, withinBudget: totalCents <= budgetCents,
      carbonKgEstimate: round1(grams / 1000),
      riskScorePct: round1(lines.reduce((sum, line) => sum + line.quantityLitres * (10_000 - line.reliabilityBps), 0) / (totalLitres * 100)),
      largestSupplierExposurePct: round1((Math.max(...supplierUnits.values()) * 100) / totalLitres),
      supplierCount: supplierUnits.size,
    };
  });
  const allocationSignature = (option) => option.lines.map((line) => `${line.sku}:${line.quantityLitres}`).sort().join('|');
  for (const [index, candidate] of candidates.entries()) {
    const same = candidates.slice(0, index).find((earlier) => allocationSignature(earlier) === allocationSignature(candidate));
    candidate.equivalentTo = same?.id ?? null;
  }
  if (!candidates.some((option) => option.withinBudget)) {
    throw new PlannerFault('BUDGET_EXCEEDED', 'No fully filled portfolio option fits the buyer ceiling.', { cheapestCents: candidates[0].totalCents, budgetCents });
  }
  // Keep options visible even when one is dominated: the UI shows the explainable tradeoff.
  const [cheap, resilient, green] = candidates;
  const recommended = resilient.withinBudget && resilient.totalCents <= cheap.totalCents * 1.15 &&
    resilient.largestSupplierExposurePct < cheap.largestSupplierExposurePct ? 'resilience' :
    green.withinBudget && green.carbonKgEstimate < cheap.carbonKgEstimate && green.totalCents <= cheap.totalCents * 1.05 ? 'footprint' : 'cost';
  return { requirements: typed, budgetCents, totalLitres, recommendedOptionId: recommended,
    options: candidates, metrics: 'SYNTHETIC_HEURISTICS_NOT_SUPPLIER_ASSERTIONS', algorithm: 'whole-litre constrained deterministic allocation v1' };
}
