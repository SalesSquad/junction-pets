/**
 * Exact whole-pack allocation for the SYNTHETIC purchasing fixture.
 * Prices are integer EUR cents per litre. No stock, price or authority is inferred.
 */
export class PurchaseUnitError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = 'PurchaseUnitError';
    this.code = code;
    this.details = details;
  }
}
const fail = (code, message, details) => { throw new PurchaseUnitError(code, message, details); };
const whole = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
const date = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
const bySku = (a, b) => a.sku < b.sku ? -1 : a.sku > b.sku ? 1 : 0;
const families = ['dairy-milk', 'oat-drink'];

function validateNeed(need) {
  if (!need || typeof need !== 'object' || Array.isArray(need) ||
      Object.keys(need).some((key) => !['family', 'quantityLitres', 'lactoseFree', 'deliverBy'].includes(key)) ||
      !families.includes(need.family) || !whole(need.quantityLitres, 1, 10_000) ||
      typeof need.lactoseFree !== 'boolean' || !date(need.deliverBy)) {
    fail('INVALID_NEED', 'Specify a supported family, 1–10000 whole litres, an explicit dietary flag and a valid delivery date.');
  }
}

function eligibleProducts(catalog, need) {
  if (!Array.isArray(catalog) || catalog.length > 10_000) {
    fail('INVALID_CATALOG', 'Provide a bounded array of structured product facts.');
  }
  const seen = new Set();
  const eligible = [];
  for (const product of catalog) {
    if (!product || typeof product !== 'object' || Array.isArray(product) ||
        typeof product.sku !== 'string' || !product.sku.trim() || product.sku.length > 128 ||
        seen.has(product.sku) || typeof product.family !== 'string' || !product.family) {
      fail('INVALID_CATALOG', 'Each record needs an explicit family and a unique SKU.');
    }
    seen.add(product.sku);
    if (product.family !== need.family) continue;
    if (typeof product.lactoseFree !== 'boolean' || !date(product.deliverBy) ||
        !whole(product.unitsAvailable, 0, 1_000_000) || !whole(product.priceCents, 1, 1_000_000) ||
        !whole(product.version, 1, Number.MAX_SAFE_INTEGER) ||
        !whole(product.packLitres, 1, 10_000) || !whole(product.minOrderPacks, 1, 10_000) ||
        (product.name !== undefined && typeof product.name !== 'string') ||
        (product.certification !== undefined && typeof product.certification !== 'string')) {
      fail('INVALID_CATALOG', 'Relevant products require explicit valid stock, price, version, pack size, minimum packs, diet and date facts.', { sku: product.sku });
    }
    if ((!need.lactoseFree || product.lactoseFree) && product.deliverBy <= need.deliverBy) eligible.push(product);
  }
  if (eligible.length > 128) fail('CATALOG_LIMIT', 'This exact allocator supports at most 128 eligible product records.');
  return eligible.sort(bySku);
}

export function calculateBasketTotals({ subtotalCents, deliveryFeeCents = 0, taxBps = 0 } = {}) {
  if (!whole(subtotalCents, 0, 20_000_000_000) || !whole(deliveryFeeCents, 0, 1_000_000) || !whole(taxBps, 0, 10_000)) {
    fail('INVALID_PRICING', 'Subtotal, delivery fee and synthetic tax rate require bounded integer facts.');
  }
  const taxBase = subtotalCents + deliveryFeeCents;
  const numerator = taxBase * taxBps;
  const taxCents = Math.floor((numerator + 5_000) / 10_000);
  const totalCents = taxBase + taxCents;
  if (![taxBase, numerator, numerator + 5_000, taxCents, totalCents].every(Number.isSafeInteger)) {
    fail('ARITHMETIC_RANGE', 'Basket totals exceed exact integer-cent representation.');
  }
  return { subtotalCents, deliveryFeeCents, taxCents, totalCents, taxBps, pricingModel: 'SYNTHETIC_WHOLE_PACKS' };
}

/**
 * Bounded-knapsack DP: for each SKU choose either zero packs or minOrderPacks
 * through floor(stock / packLitres). Monotone queues make the allocation O(SKUs
 * × requested litres), independent of stock counts. Choice layers reconstruct
 * exact quantities. Equal-cost ties retain the deterministic SKU-sorted result.
 */
export function planPurchasableBasket({ catalog, need, deliveryFeeCents = 0, taxBps = 0 } = {}) {
  validateNeed(need);
  if (!whole(deliveryFeeCents, 0, 1_000_000) || !whole(taxBps, 0, 10_000)) {
    fail('INVALID_PRICING', 'Delivery fee and the synthetic tax rate must be bounded integer cents/basis points.');
  }
  const eligible = eligibleProducts(catalog, need);
  const requestedLitres = need.quantityLitres;
  let previous = new Float64Array(requestedLitres + 1);
  previous.fill(Infinity);
  previous[0] = 0;
  const layers = [];
  for (const product of eligible) {
    const pack = product.packLitres;
    const maxPacks = Math.min(Math.floor(product.unitsAvailable / pack), Math.floor(requestedLitres / pack));
    if (maxPacks < product.minOrderPacks) continue;
    const packCost = pack * product.priceCents;
    const next = previous.slice();
    const choices = new Int32Array(requestedLitres + 1);
    for (let residue = 0; residue < pack && residue <= requestedLitres; residue++) {
      const steps = Math.floor((requestedLitres - residue) / pack);
      const indices = new Int32Array(steps + 1);
      const scores = new Float64Array(steps + 1);
      let head = 0;
      let tail = 0;
      for (let step = 0; step <= steps; step++) {
        const predecessor = step - product.minOrderPacks;
        if (predecessor >= 0) {
          const prior = previous[residue + predecessor * pack];
          if (Number.isFinite(prior)) {
            const score = prior - predecessor * packCost;
            while (tail > head && scores[tail - 1] > score) tail--;
            indices[tail] = predecessor;
            scores[tail++] = score;
          }
        }
        while (head < tail && indices[head] < step - maxPacks) head++;
        if (head < tail) {
          const volume = residue + step * pack;
          const candidate = scores[head] + step * packCost;
          if (candidate < next[volume]) {
            next[volume] = candidate;
            choices[volume] = step - indices[head];
          }
        }
      }
    }
    layers.push({ product, choices });
    previous = next;
  }
  if (!Number.isFinite(previous[requestedLitres])) {
    const products = eligible.map((product) => ({
      sku: product.sku, packLitres: product.packLitres, minOrderPacks: product.minOrderPacks,
      availablePacks: Math.floor(product.unitsAvailable / product.packLitres),
    }));
    const purchasableLitres = products.reduce((sum, product) => sum +
      (product.availablePacks >= product.minOrderPacks ? product.availablePacks * product.packLitres : 0), 0);
    fail('PACKING_CONSTRAINT', 'Exact requested litres cannot be filled using the available whole packs and minimum quantities.', {
      requestedLitres, purchasableLitres, products,
      reason: purchasableLitres < requestedLitres ? 'INSUFFICIENT_PURCHASABLE_STOCK' : 'NO_EXACT_WHOLE_PACK_ALLOCATION',
    });
  }
  const lines = [];
  let remaining = requestedLitres;
  for (let index = layers.length - 1; index >= 0; index--) {
    const { product, choices } = layers[index];
    const packs = choices[remaining];
    if (!packs) continue;
    const quantityLitres = packs * product.packLitres;
    lines.push({
      sku: product.sku, ...(product.name === undefined ? {} : { name: product.name }),
      family: product.family, quantityLitres, packLitres: product.packLitres, minOrderPacks: product.minOrderPacks, packs,
      unitPriceCents: product.priceCents, totalCents: quantityLitres * product.priceCents,
      stockVersion: product.version,
      ...(product.certification === undefined ? {} : { certification: product.certification }),
      deliverBy: product.deliverBy,
    });
    remaining -= quantityLitres;
  }
  lines.sort(bySku);
  const subtotalCents = lines.reduce((sum, line) => sum + line.totalCents, 0);
  const totals = calculateBasketTotals({ subtotalCents, deliveryFeeCents, taxBps });
  if (remaining !== 0 || subtotalCents !== previous[requestedLitres]) {
    fail('ARITHMETIC_RANGE', 'The exact allocation could not be reconstructed safely.');
  }
  return { lines, ...totals, requestedLitres, deliveredLitres: requestedLitres };
}
