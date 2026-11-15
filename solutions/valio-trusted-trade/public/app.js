import { browserSession, restoredBearer } from './browser-session.js';
/* Browser client for a completely fictional local purchasing provider. */
const DEMO_BUYER = 'helsinki-hotel-demo';
const elements = Object.fromEntries([
  'exception-card', 'exception-title', 'exception-status', 'exception-amounts',
  'exception-before', 'exception-after', 'exception-delta', 'exception-constraints',
  'exception-validity', 'approve-exception', 'reject-exception', 'refresh-review',
  'review-source-id', 'snapshot-summary', 'cost-products', 'cost-delivery', 'cost-tax',
  'request-text', 'budget', 'find', 'quote-placeholder', 'quote-content',
  'quote-status', 'quote-id', 'items', 'quote-total', 'policy-title',
  'policy-explanation', 'policy-panel', 'approve', 'reject', 'order',
  'reprice', 'cancel', 'decision-status', 'alert', 'audit-events',
  'refresh-audit', 'family', 'quantity', 'need-mode', 'activity', 'replay', 'export-body', 'interop-body', 'quote-title',
].map((id) => [id, document.getElementById(id)]));
const money = (cents) => new Intl.NumberFormat('en-FI', { style: 'currency', currency: 'EUR' }).format(cents / 100);
const state = { quote: null, review: null, order: null, idempotencyKey: null, busy: true, stale: false, dirty: false, recoveryBlocked: false, expired: false, expiryTimer: null, intentRevision: 0, quotedForm: null };
const recoveryCache = browserSession('classic');
let sessionToken, savedSession;
const sessionReady = restoredBearer(recoveryCache, DEMO_BUYER).then(({ token, saved }) => {
  sessionToken = token; savedSession = saved;
});
const persistBrowser = () => recoveryCache.save({
  token: sessionToken, quoteId: state.quote?.id ?? null, snapshotId: state.quote?.snapshotId ?? null,
  review: state.review, orderId: state.order?.id ?? null, idempotencyKey: state.idempotencyKey,
  dirty: state.dirty, stale: state.stale,
  // Free text is deliberately absent from both cached form copies.
  quotedForm: state.quotedForm ? Object.fromEntries(Object.entries(state.quotedForm).filter(([id]) => id !== 'request-text')) : null,
  form: Object.fromEntries(['need-mode','family','quantity','budget'].map(id => [id,elements[id].value])),
});
const api = async (path, payload) => {
  await sessionReady;
  const response = await fetch(path, {
    method: payload === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken}` },
    body: payload === undefined ? undefined : JSON.stringify(payload), redirect: 'error', signal: AbortSignal.timeout(7000),
  });
  const body = await response.json();
  if (!response.ok) {
    const reason = body.error?.message || `Request failed (${response.status})`;
    const error = new Error(reason);
    error.code = body.error?.code || 'REQUEST_FAILED';
    throw error;
  }
  return body;
};

const showAlert = (message = '') => {
  elements.alert.textContent = message;
  elements.alert.hidden = !message;
};
const activity = (message) => {
  elements.activity.prepend(addNode('li', message));
};
const say = (message) => { elements['decision-status'].textContent = message; activity(message); };
const step = (stage) => {
  const names = ['request', 'quote', 'approve', 'commit'];
  names.forEach((name, index) => {
    const el = document.getElementById(`step-${name}`);
    el.classList.toggle('active', index === stage);
    el.classList.toggle('done', index < stage);
  });
};
const addNode = (tag, text, className) => {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
};
const renderReview = () => {
  const review = state.review;
  const quote = state.quote;
  const diagnosis = review?.diagnosis;
  const visible = review && diagnosis.outcome !== 'FEASIBLE_AT_SNAPSHOT';
  elements['exception-card'].hidden = !visible;
  if (!visible) return;
  const exception = Boolean(quote?.budgetException);
  const blocked = !quote;
  elements['exception-title'].textContent = exception ? 'Review a budget exception' :
    diagnosis.outcome === 'STOCK_SHORTFALL' ? 'Compatible stock is missing' : diagnosis.outcome === 'PACKING_CONSTRAINT' ? 'Whole packs cannot fill this exact quantity' : 'This exceeds the buying policy';
  elements['exception-status'].textContent = state.dirty ? 'Your request changed. Get a fresh offer before deciding.' :
    state.expired ? 'This offer expired. Get a fresh offer and review it again.' :
    state.stale ? 'Source information changed. This offer can no longer be approved.' :
    quote?.status === 'APPROVED' ? 'Approved for this quote only.' :
    quote?.status === 'REJECTED' ? 'You rejected this proposal.' :
    blocked ? diagnosis.explanation : 'The exact products fit your requirements. Only the requested budget needs your decision.';
  elements['exception-amounts'].hidden = !exception;
  elements['exception-before'].textContent = money(review.originalBudgetCents);
  elements['exception-after'].textContent = quote ? money(quote.totalCents) : 'Unavailable';
  elements['exception-delta'].textContent = money(quote?.budgetException?.additionalCents ?? 0);
  elements['exception-constraints'].replaceChildren();
  const need = review.requested;
  for (const text of [
    need.quantityLitres.toLocaleString('en-FI') + ' L · ' + (need.family === 'dairy-milk' ? 'dairy milk' : 'oat drink'),
    need.lactoseFree ? 'Lactose-free requirement preserved' : 'Original dietary requirement preserved',
    'Delivery by ' + need.deliverBy + ' · unchanged',
    ...(diagnosis.missingLitres ? [diagnosis.missingLitres.toLocaleString('en-FI') + ' L of compatible stock missing'] : []),
  ]) elements['exception-constraints'].append(addNode('li', text));
  elements['exception-validity'].textContent = quote ?
    'Valid until ' + new Date(quote.expiresAtMs).toLocaleTimeString() + '. Availability is checked, not reserved; checked again before commitment.' :
    'No approvable quote exists. A fresh source or a separate policy-owner decision is needed.';
  elements['review-source-id'].textContent = review.snapshotId;
  const canDecide = exception && quote.status === 'AWAITING_HUMAN_APPROVAL' &&
    !state.busy && !state.stale && !state.dirty && !state.expired && !state.order;
  elements['approve-exception'].hidden = blocked;
  elements['reject-exception'].hidden = blocked;
  elements['approve-exception'].disabled = !canDecide;
  elements['reject-exception'].disabled = !canDecide;
  elements['approve-exception'].textContent = 'Approve ' + money(quote?.budgetException?.additionalCents ?? 0) + ' increase & this quote';
  elements['refresh-review'].disabled = state.busy || state.order?.status === 'SIMULATED_COMMITTED';
};
const render = () => {
  const q = state.quote;
  const o = state.order;
  renderReview();
  elements['quote-placeholder'].hidden = Boolean(q || state.review);
  elements['quote-content'].hidden = !q;
  elements.find.disabled = state.busy || o?.status === 'SIMULATED_COMMITTED';
  if (!q) {
    elements['quote-status'].textContent = state.review ? state.review.diagnosis.outcome.replaceAll('_', ' ') : 'WAITING';
    step(0);
    return;
  }
  elements['quote-status'].textContent = state.dirty ? 'REQUEST CHANGED' : state.expired ? 'OFFER EXPIRED' :
    state.stale ? 'SOURCE CHANGED' : q.status.replaceAll('_', ' ');
  elements['snapshot-summary'].textContent = 'Prices, availability and policy checked together · offer valid until ' +
    new Date(q.expiresAtMs).toLocaleTimeString() + ' · stock not reserved.';
  elements['quote-id'].textContent = q.id;
  elements['quote-title'].textContent = q.requested.family === 'oat-drink' ? 'Oat drink' : 'Dairy milk';
  elements.replay.disabled = state.busy || !o;
  elements['export-body'].disabled = state.busy;
  elements['quote-total'].textContent = money(q.totalCents);
  elements['cost-products'].textContent = money(q.costBreakdown.subtotalCents);
  elements['cost-delivery'].textContent = money(q.costBreakdown.deliveryFeeCents);
  elements['cost-tax'].textContent = money(q.costBreakdown.taxCents);
  elements.items.replaceChildren();
  for (const line of q.lines) {
    const wrapper = addNode('div', '', 'line-item');
    const details = addNode('div', '');
    details.append(addNode('b', `${line.quantityLitres.toLocaleString('en-FI')} L · ${line.name}`));
    details.append(addNode('small', `${line.sku} · ${line.packs} whole pack(s) × ${line.packLitres} L · ${money(line.unitPriceCents)} / L · catalog v${line.stockVersion}`));
    wrapper.append(details, addNode('strong', money(line.totalCents)));
    elements.items.append(wrapper);
  }
  elements['policy-panel'].classList.toggle('refused', q.status === 'REJECTED' || state.stale);
  if (o?.status === 'SIMULATED_CANCELLED') {
    elements['policy-title'].textContent = 'Simulated order cancelled';
    elements['policy-explanation'].textContent = 'Demo inventory has been restored. The evidence trail is retained.';
  } else if (o) {
    elements['policy-title'].textContent = 'Simulation committed · no purchase';
    elements['policy-explanation'].textContent = `Receipt ${o.id}. Retry reuses this order; it cannot place a duplicate.`;
  } else if (state.stale || state.expired || state.dirty) {
    elements['policy-title'].textContent = 'Fresh offer required';
    elements['policy-explanation'].textContent = 'A new quote and a new human decision are required.';
  } else if (q.status === 'REJECTED') {
    elements['policy-title'].textContent = 'Buyer rejected this proposal';
    elements['policy-explanation'].textContent = 'The same quote cannot be committed. Start a fresh request.';
  } else if (q.budgetException) {
    elements['policy-title'].textContent = q.status === 'APPROVED' ? 'Quote-only budget exception approved' : 'Review the budget exception above';
    elements['policy-explanation'].textContent = 'Additional ' + money(q.budgetException.additionalCents) +
      ' applies only to this basket. The policy ceiling is unchanged.';
  } else if (q.approvalRequired) {
    elements['policy-title'].textContent = q.status === 'APPROVED' ? 'Fictional buyer decision recorded' : 'Human approval required';
    elements['policy-explanation'].textContent = `Basket ${money(q.totalCents)} exceeds the ${money(q.sourceSnapshot.policy.autoCommitLimitCents)} fictional auto-commit limit. This is not authenticated approval.`;
  } else {
    elements['policy-title'].textContent = 'Within bounded demo buying policy';
    elements['policy-explanation'].textContent = 'Policy allows simulated auto-commit without human interaction.';
  }
  const invalid = state.stale || state.expired || state.dirty;
  const canDecide = !o && !invalid && q.status === 'AWAITING_HUMAN_APPROVAL';
  elements.approve.hidden = Boolean(q.budgetException);
  elements.reject.hidden = Boolean(q.budgetException);
  elements.approve.disabled = state.busy || !canDecide;
  elements.reject.disabled = state.busy || !canDecide;
  elements.order.disabled = state.busy || invalid || Boolean(o) || !['APPROVED', 'AUTO_COMMIT_ELIGIBLE'].includes(q.status);
  elements.reprice.disabled = state.busy || state.stale || Boolean(o);
  elements.cancel.disabled = state.busy || !o || o.status !== 'SIMULATED_COMMITTED';
  step(o ? 3 : q.status === 'APPROVED' || q.status === 'REJECTED' ? 2 : q.approvalRequired ? 2 : 1);
};
const refreshAudit = async () => {
  const body = await api('/api/audit');
  const receipts = [...body.receipts].reverse();
  elements['audit-events'].replaceChildren();
  if (!receipts.length) {
    const empty = addNode('li', 'Make a purchasing request to create the first control-plane receipt.');
    elements['audit-events'].append(empty);
    return;
  }
  for (const receipt of receipts) {
    const li = document.createElement('li');
    const details = document.createElement('div');
    details.append(addNode('b', receipt.event.replaceAll('_', ' ')));
    details.append(addNode('small', `${receipt.id} · ${new Date(receipt.time).toLocaleString()} · ${JSON.stringify(receipt.detail)}`));
    li.append(addNode('span', '●'), details);
    elements['audit-events'].append(li);
  }
};
const act = async (label, action) => {
  if (state.busy || state.recoveryBlocked) return;
  const started = performance.now();
  state.busy = true;
  showAlert();
  render();
  try {
    await persistBrowser();
    await action();
  } catch (error) {
    if (error.code === 'QUOTE_STALE') state.stale = true;
    if (error.code === 'QUOTE_EXPIRED') state.expired = true;
    showAlert(`${error.code ?? label}: ${error.message}`);
    activity(`Refused: ${error.code ?? label}. ${error.message}`);
    say(`${label} blocked. Policy and earlier decisions remain unchanged.`);
  } finally {
    activity(`${label}: ${(performance.now() - started).toFixed(1)} ms local processing including HTTP. Manual baseline unmeasured.`);
    state.busy = false;
    render();
    await persistBrowser();
    if (!recoveryCache.available) activity('Local recovery storage unavailable; this tab is ephemeral. Keep it open until cancellation or completion.');
    try { await refreshAudit(); } catch { /* Audit is optional if the demo server stops. */ }
  }
};

elements.find.addEventListener('click', () => act('Quote', async () => {
  const requestedRevision = state.intentRevision;
  const requestedForm = Object.fromEntries(['need-mode','family','quantity','request-text','budget'].map(id => [id,elements[id].value]));
  clearTimeout(state.expiryTimer);
  state.quote = null;
  state.review = null;
  state.order = null;
  state.stale = false;
  state.expired = false;
  state.dirty = false;
  state.idempotencyKey = null;
  const { quote, review } = await api('/api/reviews', {
    buyerId: DEMO_BUYER,
    ...(elements['need-mode'].value === 'typed' ? { need: { family: elements.family.value, quantityLitres: Number(elements.quantity.value), lactoseFree: true, deliverBy: '2026-11-16' } } : { requestText: elements['request-text'].value }),
    budgetCents: Number(elements.budget.value),
  });
  state.review = review;
  state.quote = quote;
  state.quotedForm = requestedForm;
  state.dirty = state.intentRevision !== requestedRevision;
  if (!quote) {
    say(review.diagnosis.explanation);
    renderReview();
    elements['exception-title'].focus();
    return;
  }
  state.expiryTimer = setTimeout(() => {
    if (!state.order) { state.expired = true; render(); }
  }, Math.max(0, quote.expiresAtMs - Date.now()));
  activity(`${quote.id} · INVENTED_LOCAL_CATALOG · ${quote.explanation}`);
  elements['interop-body'].textContent = '';
  state.idempotencyKey = crypto.randomUUID();
  if (quote.budgetException) { renderReview(); elements['exception-title'].focus(); }
  say(quote.approvalRequired ? 'Quote is ready. This amount requires an explicit fictional buyer decision.' : 'Under the policy threshold: simulated placement is available.');
}));
const decideDisplayedReview = async (decision) => {
  const result = await api('/api/reviews/' + encodeURIComponent(state.review.id) + '/decision', {
    buyerId: DEMO_BUYER, decision, quoteId: state.quote.id, snapshotId: state.review.snapshotId,
  });
  state.quote = result.quote;
  state.review = result.review;
  say(decision === 'approve' ? 'Simulated decision recorded for this exact quote. Buying policy unchanged.' :
    'Buyer rejected. You cannot reuse this quote.');
};
elements.approve.addEventListener('click', () => act('Approval', () => decideDisplayedReview('approve')));
elements.reject.addEventListener('click', () => act('Rejection', () => decideDisplayedReview('reject')));
elements['approve-exception'].addEventListener('click', () => act('Exception approval', () => decideDisplayedReview('approve')));
elements['reject-exception'].addEventListener('click', () => act('Exception rejection', () => decideDisplayedReview('reject')));
elements['refresh-review'].addEventListener('click', () => elements.find.click());
elements.order.addEventListener('click', () => act('Commit', async () => {
  const { order } = await api('/api/orders', { quoteId: state.quote.id, buyerId: DEMO_BUYER, idempotencyKey: state.idempotencyKey });
  state.order = order;
  say(`Simulated commitment ${order.id} created. NO order was sent to any supplier or payment provider.`);
}));
elements.reprice.addEventListener('click', () => act('Stale-price simulation', async () => {
  const source = state.quote.lines[0];
  await api('/api/demo/reprice', { sku: source.sku, priceCents: source.unitPriceCents + 35 });
  try {
    if (state.quote.status === 'AWAITING_HUMAN_APPROVAL') {
      await decideDisplayedReview('approve');
    } else {
      await api('/api/orders', { quoteId: state.quote.id, buyerId: DEMO_BUYER, idempotencyKey: state.idempotencyKey });
    }
  } catch (error) { activity(`Server refused old terms: ${error.code}. Requote and reapprove.`); }
  state.stale = true;
  say('Price changed at the fictional source. The original quote cannot be used; request a fresh one.');
}));
elements.cancel.addEventListener('click', () => act('Cancel', async () => {
  const { order } = await api(`/api/orders/${encodeURIComponent(state.order.id)}/cancel`, { buyerId: DEMO_BUYER });
  state.order = order;
  say('Simulated order cancelled; demo availability restored. No external system was contacted.');
}));
elements['refresh-audit'].addEventListener('click', () => act('Audit refresh', async () => refreshAudit()));
render();
async function bootClassic() {
  try {
    await sessionReady;
    if (savedSession?.quoteId) {
      const { quote } = await api('/api/quotes/' + encodeURIComponent(savedSession.quoteId));
      if (quote.buyerId !== DEMO_BUYER || quote.snapshotId !== savedSession.snapshotId) throw Error('Stored proposal does not match the current server source.');
      const { freshness } = await api('/api/quotes/' + encodeURIComponent(quote.id) + '/proof');
      state.quote = quote;
      state.review = savedSession.review?.id === quote.reviewId && savedSession.review.snapshotId === quote.snapshotId ? savedSession.review : null;
      if (state.review) {
        state.review.status = quote.status; state.review.quoteId = quote.id;
        state.review.requested = quote.requested; state.review.sourceSnapshot = quote.sourceSnapshot;
        state.review.originalBudgetCents = quote.budgetCents;
        state.review.diagnosis = { ...state.review.diagnosis, missingLitres: 0, minimumCostCents: quote.totalCents,
          outcome: quote.budgetException ? 'BUDGET_REVIEW_NEEDED' : 'FEASIBLE_AT_SNAPSHOT' };
      }
      state.idempotencyKey = savedSession.idempotencyKey;
      state.dirty = savedSession.dirty === true;
      state.stale = savedSession.stale === true || freshness?.valid !== true;
      state.expired = Date.now() >= quote.expiresAtMs;
      const orderId = quote.orderId ?? savedSession.orderId;
      if (orderId) {
        const { order } = await api('/api/orders/' + encodeURIComponent(orderId));
        if (order.quoteId !== quote.id || order.snapshotId !== quote.snapshotId || order.buyerId !== DEMO_BUYER) throw Error('Stored receipt does not match current server terms.');
        state.order = order;
      }
      for (const [id,value] of Object.entries(savedSession.form ?? {})) if (['need-mode','family','quantity','budget'].includes(id) && typeof value === 'string') elements[id].value = value;
      state.quotedForm = savedSession.quotedForm ? Object.fromEntries(Object.entries(savedSession.quotedForm).filter(([id]) => id !== 'request-text')) : null;
      state.dirty ||= elements['need-mode'].value !== 'typed' || !state.quotedForm || Object.keys(state.quotedForm).some(id => elements[id]?.value !== state.quotedForm[id]) ||
        Number(elements.budget.value) !== quote.budgetCents || (elements['need-mode'].value === 'typed' &&
          (elements.family.value !== quote.requested.family || Number(elements.quantity.value) !== quote.requested.quantityLitres));
      elements['request-text'].disabled = elements['need-mode'].value === 'typed';
      elements.family.disabled = elements.quantity.disabled = elements['need-mode'].value !== 'typed';
      if (!state.order) state.expiryTimer = setTimeout(() => { state.expired = true; render(); }, Math.max(0,quote.expiresAtMs - Date.now()));
      say('Original local demo session restored; current quote and receipt were rechecked. No new decision or order was made.');
    }
    await refreshAudit();
    await persistBrowser();
    if (!recoveryCache.available) say('Local recovery storage unavailable; this tab is ephemeral. Keep it open until cancellation or completion.');
  } catch (error) {
    // Preserve the original cache on network failures; never autoapprove/recommit it.
    state.stale = true; state.recoveryBlocked = true;
    showAlert('Recovery paused: ' + error.message + ' Reload when the original local backend is available; no purchasing action was taken.');
  } finally { state.busy = state.recoveryBlocked; render(); }
}
bootClassic();

elements.replay.addEventListener('click', () => act('Replay verification', async () => {
  const { order } = await api('/api/orders', { quoteId: state.quote.id, buyerId: DEMO_BUYER, idempotencyKey: state.idempotencyKey });
  say(`Server replay: ${order.id}, same receipt ${order.id === state.order.id}; idempotentReplay=${order.idempotentReplay}. No second stock deduction.`);
}));
elements['export-body'].addEventListener('click', () => act('Unsigned quote export', async () => {
  const payload = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/body`);
  elements['interop-body'].textContent = JSON.stringify(payload, null, 2);
  say('UNSIGNED synthetic Kättely-compatible quote BODY shown below. No cryptographic proof or delegation.');
}));
elements['need-mode'].addEventListener('change', () => {
  const typed = elements['need-mode'].value === 'typed';
  elements['request-text'].disabled = typed;
  elements.family.disabled = !typed;
  elements.quantity.disabled = !typed;
});

// Edited inputs never silently change the terms currently displayed for consent.
for (const id of ['need-mode', 'family', 'quantity', 'request-text', 'budget']) {
  elements[id].addEventListener('input', () => {
    state.intentRevision += 1;
    if (state.quote || state.review) { state.dirty = true; render(); }
    if (sessionToken) persistBrowser();
  });
  elements[id].addEventListener('change', () => {
    state.intentRevision += 1;
    if (state.quote || state.review) { state.dirty = true; render(); }
    if (sessionToken) persistBrowser();
  });
}
