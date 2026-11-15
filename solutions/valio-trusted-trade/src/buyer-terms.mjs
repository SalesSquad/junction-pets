/** Independent HTTP buyer checks. Imports no supplier state or pricing engine. */
import assert from 'node:assert/strict';

export function verifyBuyerTerms(quote, policy) {
  const whole = (v, min = 0) => Number.isSafeInteger(v) && v >= min;
  assert.ok(whole(policy.deliveryFeeCents) && whole(policy.taxBps) && policy.taxBps <= 10000);
  let subtotal = 0;
  for (const line of quote.lines) {
    const source = quote.sourceSnapshot.products.find(p => p.sku === line.sku);
    assert.ok(source, 'Quoted product must have source facts');
    for (const [value, minimum] of [[line.quantityLitres, 1], [line.unitPriceCents, 1],
      [line.packs, 1], [line.packLitres, 1], [line.minOrderPacks, 1]]) assert.ok(whole(value, minimum));
    assert.equal(line.packLitres, source.packLitres);
    assert.equal(line.minOrderPacks, source.minOrderPacks);
    assert.equal(line.unitPriceCents, source.priceCents);
    assert.equal(line.stockVersion, source.version);
    assert.equal(line.quantityLitres, line.packs * line.packLitres);
    assert.ok(line.packs >= line.minOrderPacks && line.quantityLitres <= source.unitsAvailable);
    assert.equal(line.totalCents, line.quantityLitres * line.unitPriceCents);
    subtotal += line.totalCents;
    assert.ok(whole(subtotal));
  }
  const base = subtotal + policy.deliveryFeeCents;
  assert.ok(whole(base));
  // Independent integer oracle, rather than importing the supplier calculation.
  const tax = Number((BigInt(base) * BigInt(policy.taxBps) + 5000n) / 10000n);
  assert.deepEqual(quote.costBreakdown, { subtotalCents: subtotal, deliveryFeeCents: policy.deliveryFeeCents,
    taxCents: tax, taxBps: policy.taxBps });
  assert.equal(quote.totalCents, base + tax);
  assert.ok(whole(quote.totalCents, 1));
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
