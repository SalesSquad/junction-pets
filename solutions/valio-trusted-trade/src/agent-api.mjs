/** Compact, deterministic workflow projection. No model-generated authority. */
import { randomUUID } from 'node:crypto';
import { TradeError, unsignedQuoteBody } from './core.mjs';

const only = (value, fields) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !fields.includes(key))) {
    throw new TradeError('INVALID_REQUEST', 'Request contains unsupported fields.');
  }
};
export function createAgentApi({ service, trust, context, clock = () => Date.now() }) {
  const own = (id, session) => {
    const run = context.agentRuns.get(id);
    if (!run || run.owner !== session) throw new TradeError('BUYER_MISMATCH', 'This workflow belongs to its original demo session.', 403);
    return run;
  };
  const project = (run, full = false) => {
    const quote = run.quoteId ? service.quote(run.quoteId) : null;
    const orderId = quote?.orderId ?? run.orderId ?? null;
    const order = orderId ? service.order(orderId) : null;
    let status = order?.status ?? quote?.status ?? 'BLOCKED';
    if (quote && !order) {
      try { service.assertQuoteFresh(quote.id); }
      catch (error) {
        if (['QUOTE_STALE', 'QUOTE_EXPIRED'].includes(error.code)) status = error.code;
        else throw error;
      }
    }
    const proof = quote ? trust.findHandshake(quote.id) : null;
    const payment = order?.paymentEligible ? service.payment(order.id, run.buyerId) : null;
    const nextActions = order ? (order.status === 'SIMULATED_CANCELLED' ? ['view_receipt', 'prepare_new_purchase'] :
      [payment?.transfer ? 'view_receipt' : payment?.approval?.decision === 'approve' ? 'settle_payment' : 'request_separate_payment_approval', 'cancel_refund']) :
      ['QUOTE_EXPIRED', 'QUOTE_STALE', 'REJECTED', 'BLOCKED'].includes(status) ? ['prepare_new_purchase'] :
      status === 'AWAITING_HUMAN_APPROVAL' ? ['request_human_approval', 'reject'] :
      proof ? ['commit_purchase'] : ['verify_signed_mandate'];
    const compactQuote = quote ? { id: quote.id, buyerId: quote.buyerId, snapshotId: quote.snapshotId,
      status: quote.status, approvalRequired: quote.approvalRequired, approval: quote.approval,
      totalCents: quote.totalCents, budgetCents: quote.budgetCents, budgetException: quote.budgetException,
      costBreakdown: quote.costBreakdown, expiresAtMs: quote.expiresAtMs,
      lines: quote.lines.map(({ sku, family, quantityLitres, packs, packLitres, minOrderPacks, supplierId, totalCents }) =>
        ({ sku, family, quantityLitres, packs, packLitres, minOrderPacks, supplierId, totalCents })) } : null;
    return { mode: 'SYNTHETIC', run: { id: run.id, buyerId: run.buyerId, quoteId: run.quoteId,
      reviewId: run.reviewId, planId: run.planId, orderId, status },
      quote: full ? quote : compactQuote, nextActions,
      ...(order ? { order: full ? order : { id: order.id, status: order.status, totalCents: order.totalCents } } : {}),
      ...(full ? { policy: service.policy(), review: run.review ?? null, proof, payment,
        originalIntent: { requirements: run.requirements, budgetCents: run.budgetCents } } : {}) };
  };
  return Object.freeze({
    prepare(payload, session) {
      only(payload, ['buyerId', 'requirements', 'budgetCents']);
      if (!Number.isSafeInteger(payload.budgetCents) || payload.budgetCents < 1 || payload.budgetCents > service.policy().perOrderBudgetCents) throw new TradeError('INVALID_BUDGET', 'Declare an integer-cent budget within the server policy ceiling.');
      if (payload.buyerId !== service.policy().buyerId || !Array.isArray(payload.requirements) ||
          payload.requirements.length < 1 || payload.requirements.length > 2) {
        throw new TradeError('INVALID_NEED', 'Provide one or two exact typed product requirements.');
      }
      if (context.agentRuns.size >= 5000) throw new TradeError('STATE_CAPACITY', 'This bounded demo workflow store is full.', 429);
      let quote, review = null, plan = null;
      if (payload.requirements.length === 1) {
        ({ quote, review } = service.requestReview({ buyerId: payload.buyerId,
          need: payload.requirements[0], budgetCents: payload.budgetCents }));
        context.reviewOwners.set(review.id, session);
      } else {
        plan = service.planBasket(payload);
        quote = service.quoteBasketPlan({ buyerId: payload.buyerId, planId: plan.id, optionId: plan.recommendedOptionId });
        context.planOwners.set(plan.id, session);
      }
      if (quote) context.quoteOwners.set(quote.id, session);
      const run = { id: 'RUN-DEMO-' + randomUUID(), owner: session, buyerId: payload.buyerId,
        quoteId: quote?.id ?? null, reviewId: review?.id ?? null, planId: plan?.id ?? null,
        review, requirements: structuredClone(payload.requirements), budgetCents: payload.budgetCents };
      context.agentRuns.set(run.id, run);
      return project(run);
    },
    status(id, session, full = false) { return project(own(id, session), full); },
    decide(id, payload, session) {
      only(payload, ['buyerId', 'decision', 'quoteId', 'snapshotId']);
      const run = own(id, session);
      if (payload.buyerId !== run.buyerId || payload.quoteId !== run.quoteId) throw new TradeError('REVIEW_MISMATCH', 'Decision must match the displayed workflow and quote.', 409);
      const quote = service.quote(run.quoteId);
      if (payload.snapshotId !== quote.snapshotId) throw new TradeError('REVIEW_MISMATCH', 'Decision must match the displayed source snapshot.', 409);
      if (run.reviewId) {
        const result = service.decideReview({ ...payload, reviewId: run.reviewId });
        run.review = result.review;
      } else service.approve({ buyerId: run.buyerId, quoteId: run.quoteId, decision: payload.decision,
        approver: 'Agent host confirmed SYNTHETIC review; not a real authenticated approver' });
      return project(run);
    },
    commit(id, payload, session) {
      only(payload, ['buyerId', 'idempotencyKey']);
      const run = own(id, session);
      if (payload.buyerId !== run.buyerId || !run.quoteId) throw new TradeError('BUYER_MISMATCH', 'Workflow has no owned quote to commit.', 403);
      const quote = service.quote(run.quoteId);
      const proof = trust.findHandshake(quote.id);
      if (!quote.orderId) {
        if (!proof) throw new TradeError('HANDSHAKE_REQUIRED', 'Agent workflow commitments require a verified quote-bound mandate.', 403);
        trust.verifyHandshake(proof, quote, unsignedQuoteBody(quote));
        service.assertQuoteFresh(quote.id);
      }
      const order = service.commitOrder({ buyerId: run.buyerId, quoteId: quote.id, idempotencyKey: payload.idempotencyKey });
      context.orderOwners.set(order.id, session);
      run.orderId = order.id;
      return project(run);
    },
    cancel(id, payload, session) {
      only(payload, ['buyerId']);
      const run = own(id, session);
      if (payload.buyerId !== run.buyerId) throw new TradeError('BUYER_MISMATCH', 'Workflow belongs to another buyer.', 403);
      const idToCancel = service.quote(run.quoteId).orderId;
      if (!idToCancel || context.orderOwners.get(idToCancel) !== session) throw new TradeError('ORDER_NOT_FOUND', 'Workflow has no owned committed order.', 404);
      service.cancelOrder({ buyerId: run.buyerId, orderId: idToCancel });
      return project(run);
    },
  });
}
