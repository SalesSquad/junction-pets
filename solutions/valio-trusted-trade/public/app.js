/* Browser client for a completely fictional local purchasing provider. */
const DEMO_BUYER = 'helsinki-hotel-demo';
const elements = Object.fromEntries([
  'request-text', 'budget', 'find', 'quote-placeholder', 'quote-content',
  'quote-status', 'quote-id', 'items', 'quote-total', 'policy-title',
  'policy-explanation', 'policy-panel', 'approve', 'reject', 'order',
  'reprice', 'cancel', 'decision-status', 'alert', 'audit-events',
  'refresh-audit', 'family', 'quantity', 'need-mode', 'activity', 'replay', 'export-body', 'interop-body', 'quote-title',
].map((id) => [id, document.getElementById(id)]));
const money = (cents) => new Intl.NumberFormat('en-FI', { style: 'currency', currency: 'EUR' }).format(cents / 100);
const state = { quote: null, order: null, idempotencyKey: null, busy: false, stale: false };
let sessionToken;
const sessionReady = fetch('/api/demo/session', { method: 'POST', body: JSON.stringify({ buyerId: DEMO_BUYER }) }).then(async (response) => {
  const body = await response.json();
  if (!response.ok) throw new Error('Demo session unavailable.');
  sessionToken = body.token;
});
const api = async (path, payload) => {
  await sessionReady;
  const response = await fetch(path, {
    method: payload === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken}` },
    body: payload === undefined ? undefined : JSON.stringify(payload),
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
const render = () => {
  const q = state.quote;
  const o = state.order;
  elements['quote-placeholder'].hidden = Boolean(q);
  elements['quote-content'].hidden = !q;
  elements.find.disabled = state.busy;
  if (!q) {
    elements['quote-status'].textContent = 'WAITING';
    step(0);
    return;
  }
  elements['quote-status'].textContent = state.stale ? 'PRICE CHANGED' : q.status.replaceAll('_', ' ');
  elements['quote-id'].textContent = q.id;
  elements['quote-title'].textContent = q.requested.family === 'oat-drink' ? 'Oat drink' : 'Dairy milk';
  elements.replay.disabled = state.busy || !o;
  elements['export-body'].disabled = state.busy;
  elements['quote-total'].textContent = money(q.totalCents);
  elements.items.replaceChildren();
  for (const line of q.lines) {
    const wrapper = addNode('div', '', 'line-item');
    const details = addNode('div', '');
    details.append(addNode('b', `${line.quantityLitres.toLocaleString('en-FI')} L · ${line.name}`));
    details.append(addNode('small', `${line.sku} · ${money(line.unitPriceCents)} / L · catalog v${line.stockVersion}`));
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
  } else if (state.stale) {
    elements['policy-title'].textContent = 'Source changed — quote invalid';
    elements['policy-explanation'].textContent = 'A new quote and a new human decision are required.';
  } else if (q.status === 'REJECTED') {
    elements['policy-title'].textContent = 'Buyer rejected this proposal';
    elements['policy-explanation'].textContent = 'The same quote cannot be committed. Start a fresh request.';
  } else if (q.approvalRequired) {
    elements['policy-title'].textContent = q.status === 'APPROVED' ? 'Fictional buyer decision recorded' : 'Human approval required';
    elements['policy-explanation'].textContent = `Basket ${money(q.totalCents)} exceeds the ${money(75000)} fictional auto-commit limit. This is not authenticated approval.`;
  } else {
    elements['policy-title'].textContent = 'Within bounded demo buying policy';
    elements['policy-explanation'].textContent = 'Policy allows simulated auto-commit without human interaction.';
  }
  const canDecide = !o && !state.stale && q.status === 'AWAITING_HUMAN_APPROVAL';
  elements.approve.disabled = state.busy || !canDecide;
  elements.reject.disabled = state.busy || !canDecide;
  elements.order.disabled = state.busy || state.stale || Boolean(o) || !['APPROVED', 'AUTO_COMMIT_ELIGIBLE'].includes(q.status);
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
  if (state.busy) return;
  const started = performance.now();
  state.busy = true;
  showAlert();
  render();
  try {
    await action();
  } catch (error) {
    showAlert(`${error.code ?? label}: ${error.message}`);
    activity(`Refused: ${error.code ?? label}. ${error.message}`);
    say(`${label} blocked. Policy and earlier decisions remain unchanged.`);
  } finally {
    activity(`${label}: ${(performance.now() - started).toFixed(1)} ms local processing including HTTP. Manual baseline unmeasured.`);
    state.busy = false;
    render();
    try { await refreshAudit(); } catch { /* Audit is optional if the demo server stops. */ }
  }
};

elements.find.addEventListener('click', () => act('Quote', async () => {
  state.quote = null;
  state.order = null;
  state.stale = false;
  state.idempotencyKey = null;
  const { quote } = await api('/api/quotes', {
    buyerId: DEMO_BUYER,
    ...(elements['need-mode'].value === 'typed' ? { need: { family: elements.family.value, quantityLitres: Number(elements.quantity.value), lactoseFree: true, deliverBy: '2026-11-16' } } : { requestText: elements['request-text'].value }),
    budgetCents: Number(elements.budget.value),
  });
  state.quote = quote;
  activity(`${quote.id} · INVENTED_LOCAL_CATALOG · ${quote.explanation}`);
  elements['interop-body'].textContent = '';
  state.idempotencyKey = crypto.randomUUID();
  say(quote.approvalRequired ? 'Quote is ready. This amount requires an explicit fictional buyer decision.' : 'Under the policy threshold: simulated placement is available.');
}));
elements.approve.addEventListener('click', () => act('Approval', async () => {
  const { quote } = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/approval`, { buyerId: DEMO_BUYER, decision: 'approve', approver: 'Hotel North demo reviewer (UNAUTHENTICATED)' });
  state.quote = quote;
  say('Simulated human decision recorded. This demo does not authenticate a real purchasing manager.');
}));
elements.reject.addEventListener('click', () => act('Rejection', async () => {
  const { quote } = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/approval`, { buyerId: DEMO_BUYER, decision: 'reject', approver: 'Hotel North demo reviewer (UNAUTHENTICATED)' });
  state.quote = quote;
  say('Buyer rejected. You cannot reuse this quote.');
}));
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
      await api(`/api/quotes/${state.quote.id}/approval`, { buyerId: DEMO_BUYER, decision: 'approve', approver: 'Synthetic stale probe (never accepted)' });
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
refreshAudit().catch(() => showAlert('The local demo backend is offline. Run npm start in the solution directory.'));

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
