import test from 'node:test';
import assert from 'node:assert/strict';
import { createTradeService, TradeError, FIXTURE_CATALOG, verifyAuditChain } from '../src/core.mjs';
import { planProcurementPortfolio, PlannerFault } from '../src/procurement-planner.mjs';

const buyerId = 'helsinki-hotel-demo';
const requirements = [
  { family: 'dairy-milk', quantityLitres: 480, lactoseFree: true, deliverBy: '2026-11-16' },
  { family: 'oat-drink', quantityLitres: 240, lactoseFree: true, deliverBy: '2026-11-16' },
];

test('portfolio choices are exact-family, whole-litre, source-versioned and genuinely distinct', () => {
  const plan = planProcurementPortfolio({ catalog: FIXTURE_CATALOG, requirements, budgetCents: 175000 });
  assert.deepEqual(plan.options.map((x) => x.id), ['cost', 'resilience', 'footprint']);
  assert.equal(plan.totalLitres, 720);
  assert.equal(plan.options[0].totalCents, 122400);
  assert.equal(plan.options[0].lines.find((line) => line.family === 'dairy-milk').sku, 'DEMO-LF-1');
  assert.ok(plan.options[1].lines.length > plan.options[0].lines.length, 'resilience splits dairy into two supplier sources');
  assert.ok(plan.options[1].largestSupplierExposurePct < plan.options[0].largestSupplierExposurePct);
  assert.ok(plan.options[2].carbonKgEstimate < plan.options[0].carbonKgEstimate);
  assert.ok(plan.options[2].totalCents > plan.options[0].totalCents);
  for (const option of plan.options) {
    assert.equal(option.totalCents, option.lines.reduce((sum, line) => sum + line.quantityLitres * line.unitPriceCents, 0));
    for (const need of requirements) {
      const lines = option.lines.filter((line) => line.family === need.family);
      assert.equal(lines.reduce((sum, line) => sum + line.quantityLitres, 0), need.quantityLitres);
      assert.ok(lines.every((line) => line.deliverBy <= need.deliverBy));
      assert.ok(lines.every((line) => FIXTURE_CATALOG.find((x) => x.sku === line.sku)?.lactoseFree));
      assert.ok(lines.every((line) => line.stockVersion === 1));
    }
  }
});

test('strict typed portfolio input, budgets and inventory prevent agent-invented rights', () => {
  assert.throws(() => planProcurementPortfolio({ catalog: FIXTURE_CATALOG, requirements: [{ ...requirements[0] }], budgetCents: 175000 }), (error) => error instanceof PlannerFault && error.code === 'INVALID_PORTFOLIO');
  for (const altered of [
    [{ ...requirements[0], quantityLitres: 1.5 }, requirements[1]],
    [{ ...requirements[0], family: 'oat-drink' }, requirements[1]],
    [{ ...requirements[0], deliverBy: '2026-11-17' }, requirements[1]],
    [{ ...requirements[0], priceCents: 1 }, requirements[1]],
  ]) assert.throws(() => planProcurementPortfolio({ catalog: FIXTURE_CATALOG, requirements: altered, budgetCents: 175000 }), (error) => error.code === 'INVALID_PORTFOLIO');
  assert.throws(() => planProcurementPortfolio({ catalog: FIXTURE_CATALOG, requirements, budgetCents: 1 }), (error) => error.code === 'BUDGET_EXCEEDED');
  assert.throws(() => planProcurementPortfolio({ catalog: FIXTURE_CATALOG.map((x) => ({ ...x, unitsAvailable: 0 })), requirements, budgetCents: 175000 }), (error) => error.code === 'INSUFFICIENT_AVAILABILITY');
});

test('server holds all option prices; source disruption invalidates old plan and approval', () => {
  const service = createTradeService();
  const original = service.planBasket({ buyerId, requirements, budgetCents: 175000 });
  const q = service.quoteBasketPlan({ buyerId, planId: original.id, optionId: original.recommendedOptionId });
  assert.ok(q.approvalRequired);
  assert.throws(() => service.quoteBasketPlan({ buyerId, planId: original.id, optionId: 'cost', totalCents: 1 }), (error) => error instanceof TradeError && error.code === 'ORDER_TERMS_FORBIDDEN');
  service.approve({ buyerId, quoteId: q.id, decision: 'approve' });
  service.simulateStockShock({ sku: 'DEMO-LF-1', unitsAvailable: 0 });
  assert.throws(() => service.assertQuoteFresh(q.id), (error) => error.code === 'QUOTE_STALE');
  assert.throws(() => service.quoteBasketPlan({ buyerId, planId: original.id, optionId: 'cost' }), (error) => error.code === 'PLAN_STALE');
  const recovered = service.recoverPlan({ buyerId, planId: original.id });
  assert.equal(recovered.recoveredFrom, original.id);
  assert.equal(recovered.humanApprovalCarriedOver, false);
  const fresh = service.quoteBasketPlan({ buyerId, planId: recovered.id, optionId: recovered.recommendedOptionId });
  assert.notEqual(fresh.id, q.id);
  assert.equal(fresh.approval, null);
  assert.ok(fresh.lines.every((line) => line.sku !== 'DEMO-LF-1'));
  assert.equal(recovered.options[1].equivalentTo, 'cost', 'single remaining dairy source makes resilience equivalent, not a false new supply choice');
  assert.equal(recovered.options[2].equivalentTo, 'cost', 'same stock cannot promise fake emission gains');
  assert.ok(service.audit().some((receipt) => receipt.event === 'SUPPLY_SELF_HEALED'));
});

test('evidence receipts are SHA-256 hash-linked and independent copy tampering is detected', () => {
  const service = createTradeService();
  service.planBasket({ buyerId, requirements, budgetCents: 175000 });
  service.simulateStockShock({ sku: 'DEMO-LF-1', unitsAvailable: 0 });
  const receipts = service.audit();
  assert.equal(service.auditVerify().valid, true);
  assert.equal(verifyAuditChain(receipts).valid, true);
  receipts[0].detail.recommended = 'maliciously replaced';
  assert.deepEqual(verifyAuditChain(receipts), { valid: false, firstInvalidIndex: 0 });
  assert.equal(service.auditVerify().valid, true, 'cloned read cannot mutate server-owned audit');
});
