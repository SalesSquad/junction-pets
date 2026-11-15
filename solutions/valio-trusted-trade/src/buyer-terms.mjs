/** Independent HTTP buyer checks. Imports no supplier state or pricing engine. */
import assert from 'node:assert/strict';

const whole = (value, min = 0, max = Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(value) && value >= min && value <= max;
const day = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
const families = ['dairy-milk', 'oat-drink'];
const normalizeRequirements = (requirements) => {
  assert.ok(Array.isArray(requirements) && requirements.length >= 1 && requirements.length <= 2,
    'Original intent needs one or two typed requirements');
  const seen = new Set();
  return requirements.map((need) => {
    assert.ok(need && typeof need === 'object' && !Array.isArray(need) &&
      families.includes(need.family) && !seen.has(need.family) &&
      whole(need.quantityLitres, 1, 10_000) && typeof need.lactoseFree === 'boolean' && day(need.deliverBy),
    'Original requirements must have distinct families, exact quantities, typed dietary flags and dates');
    seen.add(need.family);
    return { family: need.family, quantityLitres: need.quantityLitres,
      lactoseFree: need.lactoseFree, deliverBy: need.deliverBy };
  }).sort((a, b) => a.family < b.family ? -1 : a.family > b.family ? 1 : 0);
};

/**
 * Third argument is caller-owned intent, never reconstructed from supplier data.
 * Legacy two-argument calls remain pricing checks; executable buyers always pass
 * their original requirements and declared budget before approving or signing.
 */
export function verifyBuyerTerms(quote, policy, intent) {
  assert.ok(quote && typeof quote === 'object' && !Array.isArray(quote));
  assert.ok(policy && typeof policy === 'object' && !Array.isArray(policy));
  assert.ok(whole(policy.deliveryFeeCents, 0, 1_000_000) && whole(policy.taxBps, 0, 10_000),
    'Policy must explicitly declare bounded delivery and tax terms');
  assert.ok(whole(policy.perOrderBudgetCents, 1), 'Policy budget ceiling must be an exact positive integer');
  assert.ok(whole(quote.totalCents, 1) && quote.totalCents <= policy.perOrderBudgetCents,
    'Quote exceeds the policy budget ceiling');
  assert.ok(Array.isArray(quote.lines) && quote.lines.length >= 1 && quote.lines.length <= 256);
  const products = quote.sourceSnapshot?.products;
  assert.ok(Array.isArray(products) && products.length <= 10_000, 'Bounded structured source products are required');
  const sourceBySku = new Map();
  for (const source of products) {
    assert.ok(source && typeof source === 'object' && typeof source.sku === 'string' &&
      source.sku.trim() && source.sku.length <= 128 && !sourceBySku.has(source.sku),
    'Source SKUs must be explicit and unique');
    sourceBySku.set(source.sku, source);
  }
  let expected = null;
  let requiredByFamily = null;
  if (intent !== undefined) {
    assert.ok(intent && typeof intent === 'object' && !Array.isArray(intent), 'Caller-owned intent is required');
    expected = normalizeRequirements(intent.requirements);
    assert.ok(whole(intent.budgetCents, 1) && intent.budgetCents <= policy.perOrderBudgetCents,
      'Original budget must be within policy');
    assert.ok(quote.totalCents <= intent.budgetCents, 'Quote exceeds the original caller-owned budget');
    assert.equal(quote.buyerId, policy.buyerId, 'Quote buyer must match the requested buyer policy');
    const requested = quote.requested;
    const constraints = quote.sourceSnapshot.constraints;
    assert.deepEqual(normalizeRequirements(requested?.requirements ?? [requested]), expected,
      'Quoted requirements must match original intent');
    assert.deepEqual(normalizeRequirements(constraints?.requirements ?? [constraints]), expected,
      'Snapshot constraints must match original intent');
    requiredByFamily = new Map(expected.map((need) => [need.family, need]));
  }
  let subtotal = 0;
  const volumes = new Map();
  const quotedSkus = new Set();
  for (const line of quote.lines) {
    assert.ok(line && typeof line === 'object' && typeof line.sku === 'string' && !quotedSkus.has(line.sku),
      'Quoted SKUs must be explicit and unique');
    quotedSkus.add(line.sku);
    const source = sourceBySku.get(line.sku);
    assert.ok(source, 'Quoted product must have source facts');
    assert.ok(families.includes(source.family) && typeof source.lactoseFree === 'boolean' &&
      day(source.deliverBy) && whole(source.unitsAvailable, 0, 1_000_000) &&
      whole(source.priceCents, 1, 1_000_000) && whole(source.version, 1) &&
      whole(source.packLitres, 1, 10_000) && whole(source.minOrderPacks, 1, 10_000),
    'Source eligibility, stock and pack facts must be explicit typed values');
    for (const [value, minimum, maximum] of [[line.quantityLitres, 1, 10_000], [line.unitPriceCents, 1, 1_000_000],
      [line.packs, 1, 10_000], [line.packLitres, 1, 10_000], [line.minOrderPacks, 1, 10_000]]) {
      assert.ok(whole(value, minimum, maximum), 'Quoted pack and price facts must be bounded integers');
    }
    assert.equal(line.family, source.family, 'Quoted family must match source facts');
    assert.equal(line.deliverBy, source.deliverBy, 'Quoted delivery must match source facts');
    assert.equal(line.packLitres, source.packLitres);
    assert.equal(line.minOrderPacks, source.minOrderPacks);
    assert.equal(line.unitPriceCents, source.priceCents);
    assert.equal(line.stockVersion, source.version);
    assert.equal(line.quantityLitres, line.packs * line.packLitres);
    assert.ok(line.packs >= line.minOrderPacks && line.quantityLitres <= source.unitsAvailable);
    assert.equal(line.totalCents, line.quantityLitres * line.unitPriceCents);
    if (requiredByFamily) {
      const requirement = requiredByFamily.get(source.family);
      assert.ok(requirement, 'Quoted family was not requested');
      assert.ok(!requirement.lactoseFree || source.lactoseFree === true,
        'Quoted product must meet the original typed dietary requirement');
      assert.ok(source.deliverBy <= requirement.deliverBy, 'Quoted delivery misses the original deadline');
      volumes.set(source.family, (volumes.get(source.family) ?? 0) + line.quantityLitres);
    }
    subtotal += line.totalCents;
    assert.ok(whole(subtotal));
  }
  if (expected) for (const need of expected) {
    assert.equal(volumes.get(need.family) ?? 0, need.quantityLitres,
      'Exactly requested volume must be delivered for each original family');
  }
  const base = subtotal + policy.deliveryFeeCents;
  assert.ok(whole(base));
  // Independent integer oracle, rather than importing the supplier calculation.
  const taxBig = (BigInt(base) * BigInt(policy.taxBps) + 5000n) / 10000n;
  assert.ok(taxBig <= BigInt(Number.MAX_SAFE_INTEGER), 'Tax must remain exact integer cents');
  const tax = Number(taxBig);
  assert.deepEqual(quote.costBreakdown, { subtotalCents: subtotal, deliveryFeeCents: policy.deliveryFeeCents,
    taxCents: tax, taxBps: policy.taxBps });
  assert.ok(whole(base + tax));
  assert.equal(quote.totalCents, base + tax);
}

export function verifyBuyerBody(body, quote) {
  assert.deepEqual(body, { version: 'kattely.procurement.quote.v3', quote_id: quote.id,
    supplier_id: 'supplier-demo', buyer_id: quote.buyerId, audience: 'https://supplier-demo.invalid', currency: 'EUR',
    issued_at: Math.floor(quote.createdAtMs / 1000), expires_at: Math.floor(quote.expiresAtMs / 1000),
    lines: quote.lines.map(line => ({ sku: line.sku, quantity: line.quantityLitres, unit: 'L',
      unit_price_cents: line.unitPriceCents, stock_version: line.stockVersion, supplier_id: line.supplierId,
      pack_litres: line.packLitres, pack_count: line.packs, min_order_packs: line.minOrderPacks })),
    cost_breakdown: { subtotal_cents: quote.costBreakdown.subtotalCents, delivery_fee_cents: quote.costBreakdown.deliveryFeeCents,
      tax_cents: quote.costBreakdown.taxCents, tax_bps: quote.costBreakdown.taxBps },
    source_snapshot_id: quote.snapshotId, total_cents: quote.totalCents });
}
