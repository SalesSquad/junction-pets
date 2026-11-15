/** The interactive command UI uses only local synthetic HTTP contracts. */
const BUYER = 'helsinki-hotel-demo';
const state = { token: null, plan: null, optionId: null, quote: null, proof: null, order: null,
  idempotencyKey: null, paymentKey: null, payment: null, wallet: null,
  busy: false, browserVerified: false, buyerKey: null, buyerKid: null,
  pendingRecipe: null, scanKey: null, scanInput: null };
const $ = (id) => document.getElementById(id);
const euro = (cents) => new Intl.NumberFormat('en-FI', { style: 'currency', currency: 'EUR' }).format(cents / 100);
const node = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};

async function api(path, payload) {
  const res = await fetch(path, { method: payload === undefined ? 'GET' : 'POST',
    headers: { ...(payload === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}) },
    body: payload === undefined ? undefined : JSON.stringify(payload), redirect: 'error', signal: AbortSignal.timeout(7000) });
  const body = await res.json();
  if (!res.ok) {
    const error = Error(body.error?.message ?? `HTTP ${res.status}`);
    error.code = body.error?.code ?? `HTTP_${res.status}`;
    throw error;
  }
  return body;
}

function timeline(headline, detail, warning = false) {
  const row = node('li', undefined, `timeline-event${warning ? ' warn' : ''}`);
  row.append(node('span', warning ? '!' : '✓', 'event-mark'));
  const copy = node('span');
  copy.append(node('strong', headline), node('small', detail));
  row.append(copy);
  $('timeline-events').prepend(row);
  while ($('timeline-events').children.length > 8) $('timeline-events').lastElementChild.remove();
}

function selectOption(id) {
  state.optionId = id;
  state.quote = null;
  state.proof = null;
  state.order = null;
  state.payment = null;
  state.paymentKey = null;
  state.browserVerified = false;
  state.idempotencyKey = null;
  renderOptions();
  renderTrust();
  renderPayment();
}

function appendMetric(parent, label, value, fill) {
  const row = node('div', undefined, 'metric');
  row.append(node('span', label), node('strong', value));
  const meter = node('div', undefined, 'metric-meter');
  const bar = node('i');
  bar.style.width = `${Math.min(100, Math.max(4, fill))}%`;
  meter.append(bar);
  const item = node('div', undefined, 'metric-item');
  item.append(row, meter);
  parent.append(item);
}

function renderOptions() {
  const grid = $('option-grid');
  grid.replaceChildren();
  if (!state.plan) {
    grid.append(node('div', 'Define a purchase and let the agent compare exact-match supply options.', 'option-placeholder'));
    $('plan-status').textContent = 'AWAITING MISSION';
    return;
  }
  $('plan-status').textContent = `PLAN ${state.plan.id} · ${state.plan.totalLitres.toLocaleString('en-FI')} L`;
  const icons = { cost: '€', resilience: '⬡', footprint: '♧' };
  for (const option of state.plan.options) {
    const selected = option.id === state.optionId;
    const card = node('button', undefined, `option-card${selected ? ' selected' : ''}${option.withinBudget ? '' : ' over-budget'}`);
    card.type = 'button';
    card.disabled = !option.withinBudget || state.busy || state.order?.status === 'SIMULATED_COMMITTED';
    card.setAttribute('aria-pressed', String(selected));
    card.title = option.explanation;
    const head = node('div', undefined, 'option-head');
    const title = node('div');
    title.append(node('span', icons[option.id]), node('b', ` ${option.title}`));
    head.append(title, node('span', '', 'option-radio'));
    const price = node('div', euro(option.totalCents), 'option-price');
    price.append(node('small', '  / complete synthetic total'));
    const metrics = node('div', undefined, 'option-metrics');
    appendMetric(metrics, 'Disruption risk*', `${option.riskScorePct}%`, 100 - option.riskScorePct * 6);
    appendMetric(metrics, 'Emissions*', `${option.carbonKgEstimate} kg`, 100 - option.carbonKgEstimate / 18);
    appendMetric(metrics, 'Largest supplier share', `${option.largestSupplierExposurePct}%`, 100 - option.largestSupplierExposurePct);
    const foot = node('div', undefined, 'option-footer');
    foot.append(node('span', `${option.supplierCount} fictional suppliers`));
    if (option.equivalentTo) foot.append(node('b', `= ${option.equivalentTo.toUpperCase()} STOCK`));
    else if (option.id === state.plan.recommendedOptionId) foot.append(node('b', '✧ AGENT PICK'));
    card.append(head, price, metrics, foot);
    card.addEventListener('click', () => selectOption(option.id));
    grid.append(card);
  }
}

function renderTrust() {
  $('plan-button').disabled = state.busy || state.order?.status === 'SIMULATED_COMMITTED';
  const option = state.plan?.options.find((candidate) => candidate.id === state.optionId);
  const q = state.quote;
  $('selected-price').textContent = q ? euro(q.totalCents) : option ? euro(option.totalCents) + ' · indicative' : '—';
  $('selected-id').textContent = q ? `${q.id} · price and stock fixed until expiry` : option ? `${option.title} · ${option.lines.length} lines · not yet quoted` : 'Select a plan to generate an immutable quote';
  const costs = q?.costBreakdown ?? option?.costBreakdown;
  $('selected-costs').textContent = costs ? 'Products ' + euro(costs.subtotalCents) + ' · delivery ' + euro(costs.deliveryFeeCents) + ' · tax ' + euro(costs.taxCents) + ' (' + costs.taxBps / 100 + '% synthetic)' : 'Delivery and tax use explicit fictional policy rates.';
  $('crypto-title').textContent = state.proof ? (state.browserVerified ? 'Server + browser verified ✓' : 'Server verified · browser unconfirmed') : 'Awaiting signed exchange';
  $('crypto-info').textContent = state.proof ? `Supplier + browser-held buyer Ed25519 proof, quote ${q.id}; self-attested keys` : 'Independent buyer private key stays in this browser';
  $('trust-badge').textContent = state.proof ? 'SIGNED DEMO PROOF' : 'NOT YET VERIFIED';
  $('trust-badge').classList.toggle('verified', Boolean(state.proof));
  $('approval-summary').textContent = q?.approval ? q.approval.decision.toUpperCase() + ' · synthetic reviewer' : q?.approvalRequired ? 'Explicit approval required' : q ? 'Within synthetic auto policy' : 'Human by exception';
  $('approval-description').textContent = state.order ? `${state.order.id} is a simulated order, no commercial side effect.` : q?.approval ? 'Decision is tied to this quote only, not to future replan.' : 'Changes of price or stock require new quote and decision.';
  const deciding = q && q.status === 'AWAITING_HUMAN_APPROVAL' && !state.order;
  const ready = q && ['APPROVED', 'AUTO_COMMIT_ELIGIBLE'].includes(q.status) && !state.order;
  $('quote-button').disabled = state.busy || !state.plan || !option || !!q;
  $('approve-button').disabled = state.busy || !deciding;
  $('reject-button').disabled = state.busy || !deciding;
  $('handshake-button').disabled = state.busy || !ready || !!state.proof || !state.buyerKey;
  $('commit-button').disabled = state.busy || !ready || !state.proof;
  $('replay-button').disabled = state.busy || !state.order;
  $('shock').disabled = state.busy || !state.plan || !!state.order;
  $('decision-badge').textContent = state.order ? 'ONE RECEIPT' : state.proof ? 'PROOF VERIFIED' : q ? q.status.replaceAll('_', ' ') : 'NO QUOTE';
  $('trust-message').textContent = state.order ? `Simulated order ${state.order.id} was committed exactly once; replay may only return the same receipt.` :
    state.proof ? 'Both synthetic signatures verified. The mandate authorizes precisely one simulated commitment.' :
    deciding ? 'The amount exceeds the demo auto-limit. A separate human decision must be recorded.' :
    q?.status === 'REJECTED' ? 'Decision refused; this fixed-price quote is terminal and cannot be committed.' :
    ready ? 'Supplier terms fixed and policy checked. Create a cryptographic, quote-bound mandate next.' :
    option ? 'Selected candidate is not a quote. Fix its terms before any authorization.' :
    'Choose an option. The service fixes its price and inventory version before any decision.';
}

function renderPayment() {
  const order = state.order;
  const pay = state.payment;
  const transfer = pay?.transfer;
  const active = order?.status === 'SIMULATED_COMMITTED';
  $('wallet-balance').textContent = euro(state.wallet?.buyerBalanceCents ?? 250_000);
  $('payment-amount').textContent = order ? euro(order.totalCents) : '—';
  $('payment-approve-button').disabled = state.busy || !active || Boolean(pay?.approval);
  $('payment-send-button').disabled = state.busy || !active || pay?.approval?.decision !== 'approve' || Boolean(transfer);
  $('payment-replay-button').disabled = state.busy || !transfer;
  $('payment-refund-button').disabled = state.busy || !active;
  $('payment-refund-button').textContent = transfer ? 'Cancel & reverse fictional payment' : 'Cancel unpaid demo order';
  $('payment-status').textContent = transfer?.status === 'SIMULATED_REFUNDED' ? 'REVERSED ✓' :
    transfer ? 'BALANCED ✓' : pay?.approval?.decision === 'approve' ? 'READY TO TRANSFER' :
    pay?.approval?.decision === 'reject' ? 'REFUSED' : order ? 'APPROVAL REQUIRED' : 'AWAITING ORDER';
  if (!order) {
    $('payment-description').textContent = 'Commit an order to see its server-derived supplier payout split.';
  } else if (transfer) {
    const allocations = transfer.allocations.map((item) => `${item.supplierId}: ${euro(item.amountCents)}`).join(' · ');
    $('payment-description').textContent = `${transfer.id} · ${transfer.status.replaceAll('_', ' ')} · ${transfer.journalEntryIds.length} balanced postings. ${allocations}. Fictional funds only.`;
  } else {
    const recipients = (pay?.proposal?.allocations ?? []).map(({ supplierId, amountCents }) => `${supplierId}: ${euro(amountCents)}`).join(' · ');
    $('payment-description').textContent = `Server-owned ${order.id}: ${recipients}. Proposal ${pay?.proposal?.digest.slice(0, 12) ?? 'pending'}… A separate synthetic human payment decision is mandatory.`;
  }
}

function alertError(message) {
  $('alert').hidden = !message;
  $('alert').textContent = message ?? '';
}

async function refreshAudit() {
  const { receipts } = await api('/api/audit');
  const chain = await api('/api/audit/verify');
  $('event-count').textContent = `${receipts.length} hash-linked events ${chain.valid ? '✓' : '!'}`;
  const list = $('audit-events');
  list.replaceChildren();
  for (const receipt of [...receipts].reverse().slice(0, 18)) {
    const row = node('li');
    row.append(node('strong', receipt.event.replaceAll('_', ' ')), node('span', `${receipt.id} · ${JSON.stringify(receipt.detail).slice(0, 135)}`), node('span', new Date(receipt.time).toLocaleTimeString('en-FI')));
    list.append(row);
  }
  if (!receipts.length) list.append(node('li', 'No synthetic receipts yet.'));
}

async function act(label, callback) {
  if (state.busy) return;
  state.busy = true;
  alertError(null);
  renderOptions();
  renderTrust();
  renderPayment();
  try { await callback(); }
  catch (error) {
    alertError(`${label} refused: ${error.code ?? 'ERROR'} · ${error.message}`);
    timeline(`${label} safely blocked`, `${error.code ?? 'ERROR'}: ${error.message}`, true);
  }
  finally {
    state.busy = false;
    renderOptions();
    renderTrust();
    renderPayment();
    try { await refreshAudit(); } catch { /* Local server may have stopped. */ }
  }
}

function requirementsFromForm() {
  const dairy = Number($('dairy').value), oat = Number($('oat').value), budgetEuros = Number($('budget').value);
  if (![dairy, oat, budgetEuros].every(Number.isSafeInteger) || dairy < 1 || oat < 1 ||
      dairy > 10000 || oat > 10000 || budgetEuros < 1 || budgetEuros > 2500) {
    throw Error('Specify whole-litre quantities and an integer €1–€2500 budget.');
  }
  return { buyerId: BUYER, budgetCents: budgetEuros * 100,
    requirements: [
      { family: 'dairy-milk', lactoseFree: true, quantityLitres: dairy, deliverBy: '2026-11-16' },
      { family: 'oat-drink', lactoseFree: true, quantityLitres: oat, deliverBy: '2026-11-16' },
    ] };
}

function setPlan(plan) {
  if (state.order?.status === 'SIMULATED_COMMITTED') throw Error('Cancel or refund the current simulated order before replacing its receipt with a new plan.');
  state.plan = plan;
  state.optionId = plan.recommendedOptionId;
  state.quote = null;
  state.proof = null;
  state.order = null;
  state.payment = null;
  state.paymentKey = null;
  state.browserVerified = false;
  state.idempotencyKey = null;
  state.scanKey = null;
  state.scanInput = null;
}

function scanMessage(heading, lines = [], warning = false) {
  const result = $('scan-result');
  result.replaceChildren();
  result.classList.toggle('scan-warning', warning);
  result.append(node('strong', heading));
  for (const line of lines) result.append(node('span', line));
}

function resetScanObservation() {
  state.pendingRecipe = null;
  state.scanKey = null;
  state.scanInput = null;
  $('scan-confirm-button').hidden = true;
}

function scanMode() { return $('scan-purpose').value; }

function readBarcodeCandidates(text) {
  if (typeof text !== 'string') return [];
  return [...new Set((text.match(/(?<![0-9])[0-9]{8}(?:[0-9]{4,6})?(?![0-9])/g) ?? []).filter((value) =>
    [8, 12, 13, 14].includes(value.length)))];
}

async function detectBrowserBarcode(file) {
  if (typeof BarcodeDetector === 'undefined' || typeof createImageBitmap !== 'function') return [];
  let bitmap;
  try {
    const supported = await BarcodeDetector.getSupportedFormats();
    const formats = ['ean_13', 'ean_8', 'upc_a', 'itf'].filter((format) => supported.includes(format));
    if (!formats.length) return [];
    bitmap = await createImageBitmap(file);
    const detector = new BarcodeDetector({ formats });
    const detected = await detector.detect(bitmap);
    return [...new Set(detected.map((candidate) => candidate.rawValue).filter((code) =>
      typeof code === 'string' && /^\d{8}$|^\d{12}$|^\d{13}$|^\d{14}$/.test(code)))];
  } catch {
    // Progressive enhancement: image OCR and explicit typing remain available.
    return [];
  } finally { bitmap?.close?.(); }
}

async function prepareOcrImage(file) {
  const maxBytes = 1_500_000;
  if (file.size > 16_000_000) throw Error('Photo exceeds the 16 MB browser processing limit.');
  if (['image/png', 'image/jpeg'].includes(file.type) && file.size >= 8 && file.size <= maxBytes) return file;
  if (!['image/png', 'image/jpeg', 'image/heic', 'image/heif'].includes(file.type)) {
    throw Error('Choose a JPEG, PNG or iPhone HEIC image.');
  }
  if (typeof createImageBitmap !== 'function') throw Error('This browser cannot resize the photo; choose a JPEG smaller than 1.5 MB.');
  const bitmap = await createImageBitmap(file);
  try {
    const canvas = document.createElement('canvas');
    for (const [maxEdge, quality] of [[1600, 0.82], [1200, 0.64], [900, 0.55]]) {
      const ratio = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
      canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
      canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
      if (blob && blob.size >= 8 && blob.size <= maxBytes) return blob;
    }
    throw Error('Photo could not be reduced to the 1.5 MB scan limit.');
  } finally { bitmap.close?.(); }
}

async function recognizeScanImage(file) {
  if (!state.token) throw Error('Start the demo session before uploading an image.');
  const upload = await prepareOcrImage(file);
  const response = await fetch('/api/scan/ocr', { method: 'POST',
    headers: { Authorization: `Bearer ${state.token}`, 'Content-Type': upload.type },
    body: upload, redirect: 'error', signal: AbortSignal.timeout(9000) });
  const body = await response.json();
  if (!response.ok) {
    const error = Error(body.error?.message ?? `OCR HTTP ${response.status}`);
    error.code = body.error?.code ?? 'OCR_FAILED';
    throw error;
  }
  return body;
}

$('scan-purpose').addEventListener('change', () => {
  resetScanObservation();
  scanMessage(scanMode() === 'recipe' ? 'Recipe quantities are suggestions until you review them.' :
    scanMode() === 'delivery' ? 'Commit a signed demo order first, then scan its product GTIN.' :
      'Scan an exact barcode to look up one fictional catalog product.');
});
$('scan-code').addEventListener('input', resetScanObservation);
$('scan-image').addEventListener('change', resetScanObservation);

$('scan-image-button').addEventListener('click', () => act('Camera / image scan', async () => {
  resetScanObservation();
  const file = $('scan-image').files?.[0];
  if (!file) throw Error('Choose or take a photo first.');
  if (scanMode() === 'recipe') {
    const observation = await recognizeScanImage(file);
    state.pendingRecipe = observation;
    const eligible = observation.candidates?.filter((item) => !observation.duplicateFamilies.includes(item.family)) ?? [];
    $('scan-confirm-button').hidden = eligible.length === 0;
    scanMessage(eligible.length ? 'OCR suggests quantities — please verify the printed recipe.' : 'No supported recipe quantities recognized.', [
      ...((observation.candidates ?? []).map((item) => `${item.family}: ${item.quantityLitres} L · source: ${item.sourceLine}`)),
      ...(observation.duplicateFamilies.length ? [`Ambiguous repeated lines: ${observation.duplicateFamilies.join(', ')}. These will not be applied.`] : []),
      'Only “480 L lactose-free milk” and “240 L oat drink” style lines are parsed. No allergen conclusions.',
    ], !eligible.length || observation.duplicateFamilies.length > 0);
    timeline('Untrusted recipe OCR proposed', `${observation.candidates?.length ?? 0} quantity candidate(s) · awaiting human review · image not stored`);
    return;
  }

  let codes = await detectBrowserBarcode(file);
  let source = 'browser barcode detector';
  if (!codes.length) {
    const observation = await recognizeScanImage(file);
    codes = readBarcodeCandidates(observation.text);
    source = 'untrusted server OCR';
  }
  if (codes.length !== 1) {
    scanMessage(codes.length ? 'Multiple barcode candidates — no automatic selection.' : 'No barcode recognized.',
      [codes.length ? `Candidates: ${codes.join(', ')}` : 'Enter the package GTIN manually. OCR support is optional.', 'A scan does not prove origin, receipt or allergy status.'], true);
    return;
  }
  $('scan-code').value = codes[0];
  scanMessage(`Detected ${codes[0]} via ${source}.`, ['Check the code against the packaging, then press “Check exact code”.',
    scanMode() === 'delivery' ? 'A separate explicit click records one self-attested delivery observation.' : 'No order has been placed.']);
  timeline('Candidate barcode captured', `${codes[0]} · ${source} · requires explicit exact-match confirmation`);
}));

$('scan-confirm-button').addEventListener('click', () => act('Recipe observation confirmation', async () => {
  const observation = state.pendingRecipe;
  if (!observation || scanMode() !== 'recipe') throw Error('Scan a supported recipe image first.');
  const accepted = observation.candidates.filter((item) => !observation.duplicateFamilies.includes(item.family));
  for (const candidate of accepted) {
    const field = candidate.family === 'dairy-milk' ? 'dairy' : candidate.family === 'oat-drink' ? 'oat' : null;
    if (field) $(field).value = String(candidate.quantityLitres);
  }
  resetScanObservation();
  scanMessage('Human-confirmed OCR quantities entered.', [
    ...accepted.map((candidate) => `${candidate.family}: ${candidate.quantityLitres} L`),
    'Review the quantities, delivery date and budget; press Plan autonomous basket to request a new plan.',
  ]);
  timeline('Recipe quantity observations confirmed', `${accepted.length} supported field(s) applied to request · no order or money created`);
}));

$('scan-code-button').addEventListener('click', () => act('Exact GTIN lookup', async () => {
  if (scanMode() === 'recipe') throw Error('Choose Product barcode or Delivery mode for a GTIN.');
  const code = $('scan-code').value.trim();
  const { product } = await api(`/api/scan/resolve?gtin=${encodeURIComponent(code)}`);
  if (scanMode() !== 'delivery') {
    scanMessage('Exact fictional catalog match ✓', [
      `${product.name} · ${product.sku}`, `${product.gtin} · ${euro(product.priceCents)} per 1 L · ${product.unitsAvailable} L in synthetic stock`,
      'Checksum + catalog equality only. No claim of package authenticity or dietary suitability.',
    ]);
    timeline('Exact product identifier resolved', `${code} → ${product.sku} · fictional source, stock version ${product.stockVersion}`);
    return;
  }
  if (!state.order || state.order.status !== 'SIMULATED_COMMITTED') throw Error('Commit a signed demo order before delivery comparison.');
  const fingerprint = `${state.order.id}:${product.gtin}`;
  if (!state.scanKey || state.scanInput !== fingerprint) {
    state.scanKey = crypto.randomUUID();
    state.scanInput = fingerprint;
  }
  const { observation } = await api(`/api/orders/${encodeURIComponent(state.order.id)}/scan`, {
    buyerId: BUYER, gtin: product.gtin, idempotencyKey: state.scanKey,
  });
  scanMessage(observation.idempotentReplay ? 'Existing observation replayed — no double count ✓' : 'Signed-order item matched ✓', [
    `${product.sku} · ${product.gtin}`, `Observed ${observation.observedCount} / ${observation.orderedCount} packs × ${observation.packLitres} L (${observation.observedLitres} L)`,
    `${observation.receiptId} · self-attested observation only, not proof of physical delivery.`,
    'Scan a different image or edit the GTIN for a fresh observation.',
  ]);
  timeline(observation.idempotentReplay ? 'Duplicate scan safely replayed' : 'Delivery observation hash-linked',
    `${observation.receiptId} · ${product.sku} · ${observation.observedCount}/${observation.orderedCount} · NOT physical proof`);
}));

$('search-products-button').addEventListener('click', () => act('Product discovery', async () => {
  const { query, mode, candidates, reason } = await api(`/api/products/search?q=${encodeURIComponent($('product-query').value)}`);
  const panel = $('product-search-result');
  panel.replaceChildren();
  panel.append(node('strong', `${candidates.length} search candidates · ${mode === 'PGVECTOR_HYBRID_RRF' ? 'pgvector + full-text RRF' : 'fictional lexical index'}`));
  if (reason === 'EXACT_GTIN_ROUTE_REQUIRED') panel.append(node('span', 'Barcode identity requires the exact GTIN field above, not a fuzzy search.'));
  if (reason === 'NO_SUPPORTED_MATCH') panel.append(node('span', 'No candidates in the current data scope. No products were invented.'));
  if (reason === 'UNVERIFIED_DIETARY_CONSTRAINT') panel.append(node('span',
    'Safety abstention: the available catalog cannot verify this diet or allergen requirement. No product is suggested.'));
  if (reason === 'LOW_CONFIDENCE_ABSTAINED') panel.append(node('span',
    'No sufficiently relevant, source-backed match. Semantic-only nearest neighbours are withheld without calibrated confidence.'));
  for (const candidate of candidates) {
    const row = node('div', undefined, 'search-candidate');
    row.append(node('b', `${candidate.name} · ${candidate.sku}`));
    row.append(node('span', `Source ${candidate.provenance.sourceKind} · revision ${candidate.provenance.sourceVersion} · SHA-256 ${candidate.provenance.sourceSha256.slice(0, 12)}…`));
    panel.append(row);
  }
  panel.append(node('small', 'Search only proposes candidates. The signed trade core independently revalidates exact product, eligibility, stock and fixed price.'));
  timeline('Read-only product discovery', `${query.slice(0, 80)} · ${candidates.length} provisional candidates · ${mode}`);
}));

$('mission-form').addEventListener('submit', (event) => {
  event.preventDefault();
  act('Portfolio planning', async () => {
    const { plan } = await api('/api/plans', requirementsFromForm());
    setPlan(plan);
    timeline('Autonomous basket planned', `${plan.totalLitres} L across ${plan.options.length} policy-valid alternatives · ${plan.id}`);
    $('timeline-status').textContent = 'OPTIONS READY';
  });
});

$('quote-button').addEventListener('click', () => act('Fixed-price quotation', async () => {
  const { quote } = await api(`/api/plans/${encodeURIComponent(state.plan.id)}/quotes`, { buyerId: BUYER, optionId: state.optionId });
  state.quote = quote;
  state.proof = null;
  state.idempotencyKey = crypto.randomUUID();
  timeline('Supplier terms fixed', `${quote.id} · ${euro(quote.totalCents)} · ${quote.lines.length} stock-versioned lines`);
}));

$('approve-button').addEventListener('click', () => act('Synthetic buyer approval', async () => {
  const { quote } = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/approval`, { buyerId: BUYER, decision: 'approve', approver: 'Hotel North demo reviewer · UNAUTHENTICATED' });
  state.quote = quote;
  timeline('Explicit demo buyer decision', `${quote.id} approved by a fictional, unauthenticated reviewer`);
}));

$('reject-button').addEventListener('click', () => act('Buyer rejection', async () => {
  const { quote } = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/approval`, { buyerId: BUYER, decision: 'reject', approver: 'Hotel North demo reviewer · UNAUTHENTICATED' });
  state.quote = quote;
  timeline('Human exercised veto', `${quote.id} is now terminally rejected. No commitment possible.`, true);
}));

const canonical = (value) => {
  if (value === null || typeof value === 'boolean' || typeof value === 'string' || typeof value === 'number') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
};
const base64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
async function digest(obj) {
  return base64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(obj))));
}
async function verifyInBrowser(proof) {
  if (!crypto.subtle) return false;
  const { keys } = await api('/.well-known/trusted-trade/jwks.json');
  for (const envelope of [proof.signedOffer, proof.signedMandate]) {
    const keyData = keys.find((key) => key.kid === envelope.protected.kid);
    if (!keyData) throw Error('Signed key not published by this synthetic supplier.');
    const key = await crypto.subtle.importKey('jwk', keyData, 'Ed25519', false, ['verify']);
    const bytes = Uint8Array.from(atob(envelope.signature.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
    const message = new TextEncoder().encode(`${canonical(envelope.protected)}.${canonical(envelope.payload)}`);
    if (!(await crypto.subtle.verify('Ed25519', key, bytes, message))) return false;
  }
  // Verify the MEANING of both signatures, not just their cryptographic bytes.
  // The supplier's unsigned body and the browser-held fixed quote must agree.
  const q = state.quote;
  const exported = await api(`/api/quotes/${encodeURIComponent(q.id)}/body`);
  const offer = proof.signedOffer.payload;
  const mandate = proof.signedMandate.payload;
  const now = Date.now();
  if (exported.signature !== 'UNSIGNED' || proof.signedMandate.protected.kid !== state.buyerKid ||
      offer.kind !== 'SYNTHETIC_SUPPLIER_QUOTE' || mandate.kind !== 'SYNTHETIC_BUYER_MANDATE' ||
      offer.quoteId !== q.id || mandate.quoteId !== q.id || offer.buyerId !== BUYER || mandate.buyerId !== BUYER ||
      offer.totalCents !== q.totalCents || mandate.maxTotalCents !== q.totalCents ||
      offer.quoteBodyDigest !== await digest(exported.body) ||
      mandate.signedOfferDigest !== await digest(proof.signedOffer) ||
      offer.audience !== 'https://supplier-demo.invalid' || mandate.audience !== offer.audience ||
      mandate.allowedAction !== 'CREATE_ONE_SIMULATED_ORDER' ||
      mandate.approval !== (q.approvalRequired ? 'SYNTHETIC_RECORDED_REVIEW' : 'WITHIN_DEMO_POLICY') ||
      !/^[0-9a-f-]{36}$/.test(mandate.nonce) ||
      ![q.createdAtMs, q.expiresAtMs, offer.issuedAtMs, offer.expiresAtMs, mandate.issuedAtMs, mandate.expiresAtMs].every((value) => Number.isSafeInteger(value) && value >= 0) ||
      q.createdAtMs >= q.expiresAtMs || offer.issuedAtMs > now || mandate.issuedAtMs > now ||
      offer.issuedAtMs < q.createdAtMs || mandate.issuedAtMs < offer.issuedAtMs ||
      mandate.expiresAtMs > offer.expiresAtMs ||
      offer.issuedAtMs >= offer.expiresAtMs || mandate.issuedAtMs >= mandate.expiresAtMs ||
      now >= q.expiresAtMs || now >= offer.expiresAtMs || now >= mandate.expiresAtMs ||
      offer.expiresAtMs > q.expiresAtMs || mandate.expiresAtMs > q.expiresAtMs) return false;
  return true;
}

$('handshake-button').addEventListener('click', () => act('Kättely handshake', async () => {
  const { signedOffer } = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/offer`, { buyerId: BUYER });
  const header = { typ: 'kattely.demo.procurement-envelope.v1', alg: 'EdDSA', kid: state.buyerKid };
  const payload = { kind: 'SYNTHETIC_BUYER_MANDATE', quoteId: state.quote.id, buyerId: BUYER,
    audience: 'https://supplier-demo.invalid', issuedAtMs: Date.now(), expiresAtMs: state.quote.expiresAtMs,
    allowedAction: 'CREATE_ONE_SIMULATED_ORDER', maxTotalCents: state.quote.totalCents,
    approval: state.quote.approvalRequired ? 'SYNTHETIC_RECORDED_REVIEW' : 'WITHIN_DEMO_POLICY',
    signedOfferDigest: await digest(signedOffer), nonce: crypto.randomUUID() };
  const message = new TextEncoder().encode(`${canonical(header)}.${canonical(payload)}`);
  const signature = base64url(await crypto.subtle.sign('Ed25519', state.buyerKey.privateKey, message));
  const { proof } = await api(`/api/quotes/${encodeURIComponent(state.quote.id)}/handshake`, { buyerId: BUYER,
    signedMandate: { protected: header, payload, signature } });
  if (!proof.verification?.valid) throw Error('The server did not verify both signatures.');
  state.proof = proof;
  try { state.browserVerified = await verifyInBrowser(proof); }
  catch { state.browserVerified = false; }
  timeline('Two independent actors signed', `Supplier's server-held and buyer's browser-held Ed25519 signatures verified${state.browserVerified ? ' in browser too' : ' on server'}; amount and expiry bound to ${state.quote.id}`);
}));

$('commit-button').addEventListener('click', () => act('Simulated order commitment', async () => {
  const { order } = await api('/api/orders', { buyerId: BUYER, quoteId: state.quote.id, idempotencyKey: state.idempotencyKey });
  state.order = order;
  state.paymentKey = crypto.randomUUID();
  state.payment = await api(`/api/orders/${encodeURIComponent(order.id)}/payment`);
  state.wallet = state.payment.wallet;
  timeline('ONE simulated commitment', `${order.id} · ${euro(order.totalCents)} · zero external order or payment`);
  $('timeline-status').textContent = 'RECEIPT RECORDED';
}));

$('payment-approve-button').addEventListener('click', () => act('Independent demo payment approval', async () => {
  state.payment = await api(`/api/orders/${encodeURIComponent(state.order.id)}/payment-approval`, { buyerId: BUYER, decision: 'approve', proposalDigest: state.payment.proposal.digest });
  state.wallet = state.payment.wallet;
  timeline('Explicit payment consent recorded', `Separate fictional approval for ${state.order.id} · ${euro(state.order.totalCents)} · NOT banking consent`);
}));

$('payment-send-button').addEventListener('click', () => act('Synthetic EUR transfer', async () => {
  state.payment = await api(`/api/orders/${encodeURIComponent(state.order.id)}/settlement`, { buyerId: BUYER, idempotencyKey: state.paymentKey });
  state.wallet = state.payment.wallet;
  const verification = await api('/api/demo/ledger/verify');
  if (!verification.valid) throw Error('The fictional double-entry journal failed balance verification.');
  timeline('Fictional EUR settled to supplier wallets', `${state.payment.transfer.id} · ${euro(state.payment.transfer.amountCents)} · ${verification.journalEntries} hash-linked balanced postings · no PSP or bank`);
  $('timeline-status').textContent = 'TRANSFER PROVEN · SYNTHETIC';
}));

$('payment-replay-button').addEventListener('click', () => act('Payment replay defense', async () => {
  const replay = await api(`/api/orders/${encodeURIComponent(state.order.id)}/settlement`, { buyerId: BUYER, idempotencyKey: state.paymentKey });
  if (!replay.idempotentReplay || replay.transfer.id !== state.payment.transfer.id ||
      replay.wallet.buyerBalanceCents !== state.wallet.buyerBalanceCents) throw Error('Replay unexpectedly changed the fictional EUR balance.');
  timeline('Duplicate transfer safely blocked', `${replay.transfer.id} returned again without new journal entries or wallet changes`);
}));

$('payment-refund-button').addEventListener('click', () => act('Simulated order cancellation and refund', async () => {
  const hadTransfer = Boolean(state.payment?.transfer);
  const { order } = await api(`/api/orders/${encodeURIComponent(state.order.id)}/cancel`, { buyerId: BUYER });
  state.order = order;
  state.payment = await api(`/api/orders/${encodeURIComponent(order.id)}/payment`);
  state.wallet = state.payment.wallet;
  const verification = await api('/api/demo/ledger/verify');
  if (!verification.valid) throw Error('The fictional refund journal did not balance.');
  timeline(hadTransfer ? 'Fictional transfer reversed' : 'Unpaid order cancelled',
    hadTransfer ? `${order.id} cancelled · ${euro(order.totalCents)} back in buyer demo wallet · stock restored` :
      `${order.id} cancelled before payment · no wallet transfer or refund was needed · stock restored`);
  $('timeline-status').textContent = hadTransfer ? 'CANCELLED / REVERSED' : 'CANCELLED / UNPAID';
}));

$('replay-button').addEventListener('click', () => act('Replay resistance', async () => {
  const { order } = await api('/api/orders', { buyerId: BUYER, quoteId: state.quote.id, idempotencyKey: state.idempotencyKey });
  if (!order.idempotentReplay || order.id !== state.order.id) throw Error('Expected the same simulated receipt, without new stock deduction.');
  timeline('Replay refused new side effects', `Exactly the same receipt ${order.id} returned · idempotentReplay=true`);
}));

$('shock').addEventListener('click', () => act('Autonomous supply recovery', async () => {
  const formerQuote = state.quote;
  const selected = state.plan.options.find((option) => option.id === state.optionId);
  const disruptedLine = (formerQuote?.lines ?? selected?.lines ?? []).find((line) => line.family === 'dairy-milk');
  if (!disruptedLine) throw Error('The selected portfolio lacks a dairy supply line to disrupt.');
  await api('/api/demo/shock', { sku: disruptedLine.sku, unitsAvailable: 0 });
  timeline('Supplier disruption detected', `${disruptedLine.supplierId ?? 'Fictional dairy supplier'} / ${disruptedLine.sku}: available stock falls to zero; quoted versions must be revalidated.`, true);
  if (formerQuote) {
    let staleRefused = false;
    try {
      if (state.proof) {
        await api('/api/orders', { buyerId: BUYER, quoteId: formerQuote.id, idempotencyKey: state.idempotencyKey });
      } else {
        await api(`/api/quotes/${formerQuote.id}/offer`, { buyerId: BUYER });
      }
    } catch (error) {
      if (error.code !== 'QUOTE_STALE') throw error;
      staleRefused = true;
      timeline('Previous authority correctly refused', `Server returned QUOTE_STALE for ${formerQuote.id}; old price, approval and mandate cannot create a purchase.`, true);
    }
    if (!staleRefused) throw Error('The old quote unexpectedly survived the stock disruption; recovery stopped.');
  }
  const originalId = state.plan.id;
  const { plan } = await api(`/api/plans/${encodeURIComponent(originalId)}/recover`, { buyerId: BUYER });
  setPlan(plan);
  $('timeline-status').textContent = 'SELF-HEALED · REAPPROVAL NEEDED';
  timeline('Autonomous recovery planned', `${originalId} → ${plan.id}; alternatives recalculated from current stock. Fresh quote, fresh decision, fresh signatures.`);
}));

$('audit-refresh').addEventListener('click', () => act('Audit refresh', refreshAudit));

async function boot() {
  try {
    const response = await api('/api/demo/session', { buyerId: BUYER });
    state.token = response.token;
    $('buyer-context').textContent = `Demo capability ${state.token.slice(0, 8)}… · NOT real authentication`;
    if (crypto.subtle) {
      try {
        state.buyerKey = await crypto.subtle.generateKey('Ed25519', false, ['sign', 'verify']);
        const jwk = await crypto.subtle.exportKey('jwk', state.buyerKey.publicKey);
        const registered = await api('/api/trust/buyer-key', { buyerId: BUYER,
          publicJwk: { kty: jwk.kty, crv: jwk.crv, x: jwk.x } });
        state.buyerKid = registered.kid;
      } catch (error) {
        state.buyerKey = null;
        timeline('Browser signing unavailable', `This browser cannot create an Ed25519 key (${error.message}); the separate Node buyer agent can still complete Kättely.`, true);
      }
    }
    const discovery = await api('/.well-known/trusted-trade');
    if (discovery.mode !== 'SYNTHETIC_NONCOMMERCIAL') throw Error('Wrong supplier mode; writes remain disabled.');
    const [, wallet] = await Promise.all([api('/api/catalog'), api('/api/demo/wallet'), refreshAudit()]);
    state.wallet = wallet.wallet;
    timeline('Independent signing key registered', state.buyerKey ? 'Buyer private key remains in browser; supplier receives public key only.' : 'This browser does not support Ed25519; cryptographic handshake disabled.');
  } catch (error) { alertError(`Demo backend unavailable: ${error.message}. Start npm start in solutions/valio-trusted-trade.`); }
  renderOptions();
  renderTrust();
  renderPayment();
}
boot();
