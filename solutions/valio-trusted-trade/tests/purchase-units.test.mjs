import test from 'node:test';
import assert from 'node:assert/strict';
import { planPurchasableBasket, PurchaseUnitError } from '../src/purchase-units.mjs';

const need = { family: 'dairy-milk', quantityLitres: 12, lactoseFree: true, deliverBy: '2026-11-16' };
const product = (sku, extra = {}) => ({ sku, name: 'Synthetic ' + sku, family: 'dairy-milk',
  lactoseFree: true, deliverBy: '2026-11-16', unitsAvailable: 120, priceCents: 10,
  version: 1, packLitres: 6, minOrderPacks: 1, certification: 'Fictional', ...extra });
const plan = (catalog, extra = {}) => planPurchasableBasket({ catalog, need, ...extra });
const code = (expected) => (error) => error instanceof PurchaseUnitError && error.code === expected;

test('whole packs preserve exact volume and source facts', () => {
  const result = plan([product('A')]);
  assert.equal(result.subtotalCents, 120);
  assert.equal(result.totalCents, 120);
  assert.equal(result.requestedLitres, 12);
  assert.equal(result.deliveredLitres, 12);
  assert.equal(result.pricingModel, 'SYNTHETIC_WHOLE_PACKS');
  assert.deepEqual(result.lines, [{ sku: 'A', name: 'Synthetic A', family: 'dairy-milk',
    quantityLitres: 12, packLitres: 6, minOrderPacks: 1, packs: 2, unitPriceCents: 10, totalCents: 120,
    stockVersion: 1, certification: 'Fictional', deliverBy: '2026-11-16' }]);
});

test('exact allocation can combine distinct pack sizes and skip a cheaper impossible size', () => {
  const catalog = [product('A', { packLitres: 4, priceCents: 10 }), product('B', { packLitres: 6, priceCents: 11 })];
  const combined = plan(catalog, { need: { ...need, quantityLitres: 10 } });
  assert.deepEqual(combined.lines.map((line) => [line.sku, line.quantityLitres]), [['A', 4], ['B', 6]]);
  assert.equal(combined.totalCents, 106);
  const six = plan(catalog, { need: { ...need, quantityLitres: 6 } });
  assert.deepEqual(six.lines.map((line) => line.sku), ['B']);
  assert.equal(six.totalCents, 66);
});

test('a selected SKU must meet its minimum packs while unused SKUs buy zero', () => {
  const catalog = [product('A', { packLitres: 2, priceCents: 1, unitsAvailable: 8, minOrderPacks: 3 }),
    product('B', { packLitres: 2, priceCents: 3, unitsAvailable: 10 })];
  const four = plan(catalog, { need: { ...need, quantityLitres: 4 } });
  assert.deepEqual(four.lines.map((line) => [line.sku, line.packs]), [['B', 2]]);
  const ten = plan(catalog, { need: { ...need, quantityLitres: 10 } });
  assert.deepEqual(ten.lines.map((line) => [line.sku, line.packs]), [['A', 4], ['B', 1]]);
  assert.equal(ten.totalCents, 14);
});

test('partial stock below one whole pack cannot be rounded into inventory', () => {
  const result = plan([product('A', { packLitres: 3, unitsAvailable: 4, priceCents: 1 }),
    product('B', { packLitres: 2, unitsAvailable: 4, priceCents: 2 })], { need: { ...need, quantityLitres: 7 } });
  assert.deepEqual(result.lines.map((line) => [line.sku, line.quantityLitres]), [['A', 3], ['B', 4]]);
  assert.equal(result.totalCents, 11);
});

test('impossible exact volumes abstain with distinct packing or purchasable-stock evidence', () => {
  assert.throws(() => plan([product('A', { packLitres: 4 }), product('B')], {
    need: { ...need, quantityLitres: 5 },
  }), (error) => error.code === 'PACKING_CONSTRAINT' &&
    error.details.reason === 'NO_EXACT_WHOLE_PACK_ALLOCATION' && error.details.requestedLitres === 5);
  assert.throws(() => plan([product('A', { unitsAvailable: 7 })]), (error) =>
    error.code === 'PACKING_CONSTRAINT' && error.details.reason === 'INSUFFICIENT_PURCHASABLE_STOCK' &&
    error.details.purchasableLitres === 6);
  assert.throws(() => plan([product('A', { unitsAvailable: 12, minOrderPacks: 3 })]), (error) =>
    error.code === 'PACKING_CONSTRAINT' && error.details.purchasableLitres === 0);
});

test('hard family, dietary and delivery constraints survive lower incompatible prices', () => {
  const catalog = [
    product('regular', { lactoseFree: false, priceCents: 1 }),
    product('late', { deliverBy: '2026-11-17', priceCents: 1 }),
    product('oat', { family: 'oat-drink', priceCents: 1 }),
    product('matching', { priceCents: 20 }),
  ];
  const result = plan(catalog);
  assert.deepEqual(result.lines.map((line) => line.sku), ['matching']);
  assert.equal(result.totalCents, 240);
  assert.equal(plan([product('oat', { family: 'oat-drink' })], { need: { ...need, family: 'oat-drink' } }).totalCents, 120);
});

test('fee and synthetic tax are charged exactly once after allocation, with nearest-cent rounding', () => {
  const result = plan([product('A', { priceCents: 50 })], { deliveryFeeCents: 99, taxBps: 2500 });
  assert.equal(result.subtotalCents, 600);
  assert.equal(result.deliveryFeeCents, 99);
  assert.equal(result.taxCents, 175);
  assert.equal(result.totalCents, 874);
  const half = plan([product('A', { packLitres: 1, priceCents: 1 })], {
    need: { ...need, quantityLitres: 1 }, taxBps: 5000,
  });
  assert.equal(half.taxCents, 1);
  assert.equal(half.totalCents, 2);
});

test('input order cannot change equal-cost SKU allocation, and inputs remain untouched', () => {
  const catalog = Object.freeze([Object.freeze(product('B')), Object.freeze(product('A'))]);
  const frozenNeed = Object.freeze({ ...need });
  const before = structuredClone(catalog);
  const result = plan(catalog, { need: frozenNeed });
  assert.deepEqual(result, plan([...catalog].reverse(), { need: frozenNeed }));
  assert.deepEqual(result.lines.map((line) => line.sku), ['A']);
  assert.deepEqual(catalog, before);
});

test('incomplete relevant facts, duplicate identifiers and unsafe numeric values are rejected', () => {
  for (const patch of [
    { packLitres: undefined }, { minOrderPacks: undefined }, { packLitres: 0 }, { packLitres: 1.5 },
    { minOrderPacks: 0 }, { unitsAvailable: -1 }, { unitsAvailable: Number.MAX_SAFE_INTEGER },
    { priceCents: 0 }, { priceCents: 1.1 }, { priceCents: Number.MAX_SAFE_INTEGER },
    { version: 0 }, { version: 1.1 }, { lactoseFree: 'true' }, { deliverBy: '2026-02-30' },
    { name: {} }, { certification: [] },
  ]) assert.throws(() => plan([product('A', patch)]), code('INVALID_CATALOG'));
  assert.throws(() => plan([product('A'), product('A', { family: 'oat-drink' })]), code('INVALID_CATALOG'));
  assert.throws(() => plan([product('A'), { sku: 'unknown-family' }]), code('INVALID_CATALOG'));
  assert.equal(plan([product('A'), { sku: 'other', family: 'oat-drink' }]).totalCents, 120);
});

test('unsupported needs and fractional or overflowing delivery/tax terms fail closed', () => {
  for (const patch of [{ quantityLitres: 0 }, { quantityLitres: 1.5 }, { quantityLitres: 10001 },
    { lactoseFree: undefined }, { family: 'unknown' }, { deliverBy: 'Monday' }, { approved: true }]) {
    assert.throws(() => plan([product('A')], { need: { ...need, ...patch } }), code('INVALID_NEED'));
  }
  for (const deliveryFeeCents of [-1, 1.5, null, Infinity, Number.MAX_SAFE_INTEGER]) {
    assert.throws(() => plan([product('A')], { deliveryFeeCents }), code('INVALID_PRICING'));
  }
  for (const taxBps of [-1, 10001, NaN, 1.1, null]) {
    assert.throws(() => plan([product('A')], { taxBps }), code('INVALID_PRICING'));
  }
  assert.throws(() => plan(null), code('INVALID_CATALOG'));
});

test('maximum supported quantity and price retain exact integer-cent totals', () => {
  const result = plan([product('A', { packLitres: 1, priceCents: 1_000_000, unitsAvailable: 1_000_000 })], {
    need: { ...need, quantityLitres: 10_000 }, deliveryFeeCents: 1_000_000, taxBps: 10_000,
  });
  assert.equal(result.subtotalCents, 10_000_000_000);
  assert.equal(result.taxCents, 10_001_000_000);
  assert.equal(result.totalCents, 20_002_000_000);
  assert.ok(Number.isSafeInteger(result.totalCents));
});

test('128 eligible SKUs remain bounded and deterministic; an oversized exact search is refused', () => {
  const catalog = Array.from({ length: 128 }, (_, n) => product(String(n).padStart(3, '0'), {
    packLitres: 1, priceCents: 1, unitsAvailable: 10_000,
  }));
  const result = plan(catalog, { need: { ...need, quantityLitres: 10_000 } });
  assert.equal(result.totalCents, 10_000);
  assert.deepEqual(result.lines.map((line) => line.sku), ['000']);
  assert.throws(() => plan([...catalog, product('129')]), code('CATALOG_LIMIT'));
});

test('bounded DP agrees with exhaustive pack enumeration across 1200 small inventories', () => {
  const enumerate = (catalog, quantity, index = 0, litres = 0, cost = 0) => {
    if (index === catalog.length) return litres === quantity ? cost : Infinity;
    const p = catalog[index];
    let best = enumerate(catalog, quantity, index + 1, litres, cost);
    for (let packs = p.minOrderPacks; packs * p.packLitres <= p.unitsAvailable; packs++) {
      const volume = litres + packs * p.packLitres;
      if (volume > quantity) break;
      best = Math.min(best, enumerate(catalog, quantity, index + 1, volume,
        cost + packs * p.packLitres * p.priceCents));
    }
    return best;
  };
  for (let seed = 0; seed < 100; seed++) {
    const catalog = Array.from({ length: 3 }, (_, index) => {
      const packLitres = 1 + ((seed + index * 3) % 4);
      return product(String(index), { packLitres,
        minOrderPacks: 1 + ((seed + index) % 2),
        unitsAvailable: packLitres * ((seed * (index + 2) + index) % 5),
        priceCents: 1 + ((seed + index * 2) % 3),
      });
    });
    for (let quantity = 1; quantity <= 12; quantity++) {
      const best = enumerate(catalog, quantity);
      if (!Number.isFinite(best)) {
        assert.throws(() => plan(catalog, { need: { ...need, quantityLitres: quantity } }), code('PACKING_CONSTRAINT'));
      } else {
        const result = plan(catalog, { need: { ...need, quantityLitres: quantity } });
        assert.equal(result.subtotalCents, best, 'seed=' + seed + ', quantity=' + quantity);
        assert.equal(result.lines.reduce((sum, line) => sum + line.quantityLitres, 0), quantity);
        for (const line of result.lines) {
          const source = catalog.find((p) => p.sku === line.sku);
          assert.ok(line.packs >= source.minOrderPacks);
          assert.ok(line.quantityLitres <= source.unitsAvailable);
          assert.equal(line.quantityLitres % source.packLitres, 0);
        }
        assert.deepEqual(result, plan([...catalog].reverse(), { need: { ...need, quantityLitres: quantity } }));
      }
    }
  }
});
