const $ = id => document.getElementById(id);
const svgNS = 'http://www.w3.org/2000/svg';
const state = { drawing: null, result: null, selected: null, zoom: 1, busy: false };
const evidenceIds = () => new Set((state.result?.evidence || []).map(e => e.entityId));

function node(tag, attrs = {}, text) {
  const el = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  if (text !== undefined) el.textContent = text;
  return el;
}
function cssClass(entity) {
  switch (entity.layer) {
    case 'ROOM_OUTLINE': return 'layer-room';
    case 'UNIT_OUTLINE': return 'layer-unit';
    case 'WALL': return 'layer-wall';
    case 'DOOR': return 'layer-door';
    case 'WINDOW': return 'layer-window';
    default: return 'layer-other';
  }
}
function projectPoint(drawing, p) {
  const { minX, maxY, width, height } = drawing.dimensions;
  const factor = Math.min(854 / Math.max(width, 1e-5), 530 / Math.max(height, 1e-5));
  const left = (940 - width * factor) / 2;
  const top = (620 - height * factor) / 2;
  return { x: left + (p.x - minX) * factor, y: top + (maxY - p.y) * factor };
}
function entityElements(entity, drawing) {
  const cited = evidenceIds().has(entity.id);
  const selected = state.selected === entity.id;
  const css = cssClass(entity);
  const els = [];
  if (Array.isArray(entity.points)) {
    const points = entity.points.map(p => {
      const v = projectPoint(drawing, p);
      return `${v.x.toFixed(3)},${v.y.toFixed(3)}`;
    }).join(' ');
    const el = node(entity.closed ? 'polygon' : 'polyline', {
      points, class: `${css} source-hit ${cited ? 'is-cited' : ''}`,
      'data-entity-id': entity.id, 'aria-label': `${entity.layer} ${entity.id}`,
    });
    if (selected) el.setAttribute('stroke-width', '5');
    els.push(el);
  } else if (typeof entity.text === 'string') {
    const p = projectPoint(drawing, entity);
    const semantic = /^[\p{L}][\p{L}\s.-]{1,38}$/u.test(entity.text);
    const txt = node('text', { x: p.x, y: p.y, 'font-size': semantic ? 12 : 8.9,
      'text-anchor': 'middle', class: `${semantic ? 'label-name' : 'label-meta'} source-hit ${cited ? 'text-cited' : ''}`,
      'data-entity-id': entity.id, 'aria-label': `Original text: ${entity.text}` }, entity.text);
    els.push(txt);
    if (cited) els.push(node('circle', { cx: p.x, cy: p.y - 3, r: 13,
      class: 'citation-halo' }));
  } else if (Number.isFinite(entity.radius)) {
    const N = entity.type === 'ARC' ? 18 : 36;
    const start = entity.type === 'ARC' ? (entity.start || 0) : 0;
    let end = entity.type === 'ARC' ? (entity.end || 0) : 360;
    if (end <= start) end += 360;
    const ps = Array.from({ length: N + 1 }, (_, i) => {
      const a = (start + (end - start) * i / N) * Math.PI / 180;
      return projectPoint(drawing, { x: entity.x + Math.cos(a) * entity.radius,
        y: entity.y + Math.sin(a) * entity.radius });
    });
    els.push(node('polyline', { points: ps.map(p => `${p.x},${p.y}`).join(' '),
      class: `${css} source-hit ${cited ? 'is-cited' : ''}`, 'data-entity-id': entity.id }));
  }
  return els;
}
function renderDrawing() {
  const d = state.drawing;
  if (!d) return;
  const svg = $('blueprint');
  svg.replaceChildren(node('title', { id: 'blueprint-title' }, `Source geometry of ${d.filename}`));
  const geometry = node('g');
  for (const e of d.entities) if (e.type !== 'TEXT' && e.type !== 'MTEXT') {
    for (const el of entityElements(e, d)) geometry.appendChild(el);
  }
  for (const e of d.entities) if (e.type === 'TEXT' || e.type === 'MTEXT') {
    for (const el of entityElements(e, d)) geometry.appendChild(el);
  }
  svg.appendChild(geometry);
  svg.style.transform = `scale(${state.zoom})`;
  $('zoom-percent').textContent = `${Math.round(state.zoom * 100)}%`;
  svg.querySelectorAll('[data-entity-id]').forEach(el => el.addEventListener('click', () => {
    state.selected = el.getAttribute('data-entity-id');
    renderDrawing();
    renderEvidence();
  }));
}
function renderSource() {
  const d = state.drawing;
  if (!d) return;
  $('source-filename').textContent = d.filename;
  $('drawing-name').textContent = d.filename;
  $('source-kind').textContent = d.format;
  $('source-unit').textContent = d.unitsLabel.toUpperCase();
  const real = Boolean(d.sha256);
  const badge = $('source-badge');
  badge.textContent = real ? 'LOCAL IMPORT · VERIFY SOURCE' : 'SYNTHETIC · NOT VERIFIED';
  badge.classList.toggle('real', real);
  $('drawing-stats').textContent = `${d.entities.length} vector/text entities · ${d.sha256 ? `SHA256 ${d.sha256.slice(0, 12)}…` : 'original demo fixture'}`;
}
function updateQuickQueries() {
  const text = state.drawing.entities.filter(e => e.layer === 'ROOM_TEXT' && typeof e.text === 'string');
  const counts = new Map();
  for (const e of text) {
    if (!/^[\p{L}][\p{L}\s.-]{1,38}$/u.test(e.text) || /^app\.?\s*[a-z]$/i.test(e.text)) continue;
    counts.set(e.text, (counts.get(e.text) || 0) + 1);
  }
  const bestLabel = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0];
  const bestNumber = text.find(e => /^(?:[a-z]-\d+|\d+(?:[.\-]\d+){1,2})$/i.test(e.text))?.text;
  const buttons = [...document.querySelectorAll('.suggestion')];
  if (bestLabel) {
    buttons[0].dataset.q = `How many rooms labelled ${bestLabel}?`;
    buttons[0].firstChild.textContent = `Count rooms labelled ${bestLabel} `;
  }
  buttons[0].disabled = !bestLabel;
  if (bestNumber) {
    buttons[1].dataset.q = `What is the area of room ${bestNumber}?`;
    buttons[1].firstChild.textContent = `Measure room ${bestNumber} `;
  }
  buttons[1].disabled = !bestNumber;
  return bestLabel ? buttons[0].dataset.q : null;
}
function renderAnswer() {
  const result = state.result;
  const supported = result?.status === 'supported';
  const abstained = result?.status === 'abstained';
  $('answer-card').classList.toggle('abstained', abstained);
  $('answer-state').textContent = supported ? '✓ GROUNDED & TRACEABLE' : abstained ? '○ EVIDENCE INSUFFICIENT' : 'AWAITING QUESTION';
  $('answer-mark').textContent = supported ? '↗' : abstained ? '⊘' : '◎';
  $('answer-value').textContent = supported ? result.answer : abstained ? 'Not proven.' : 'Ask to begin.';
  $('answer-explanation').textContent = result?.explanation || 'Select a quick investigation or enter your own question. Unsupported requests fail closed.';
  const n = result?.evidence?.length || 0;
  $('answer-count').textContent = `${n} CITATION${n === 1 ? '' : 'S'}`;
  $('evidence-count').textContent = `${n} REGION${n === 1 ? '' : 'S'}`;
}
function renderEvidence() {
  const list = $('evidence-list');
  list.replaceChildren();
  const cites = state.result?.evidence || [];
  if (!cites.length) {
    const empty = document.createElement('div');
    empty.className = 'evidence-empty';
    empty.textContent = state.result?.status === 'abstained'
      ? 'No fabricated citation. Rephrase your question using only visible labels or a numbered room.'
      : 'Source-linked regions appear here after a supported answer.';
    list.appendChild(empty);
    return;
  }
  cites.forEach((cite, i) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `evidence-item ${state.selected === cite.entityId ? 'selected' : ''}`;
    button.setAttribute('aria-label', `Highlight citation ${i + 1}: ${cite.detail}`);
    const badge = document.createElement('span');
    badge.className = 'evidence-number';
    badge.textContent = String(i + 1).padStart(2, '0');
    const copy = document.createElement('span');
    copy.className = 'evidence-copy';
    const title = document.createElement('strong');
    title.textContent = cite.detail;
    const meta = document.createElement('small');
    meta.textContent = `${cite.layer} · ${cite.entityId} · CLICK TO INSPECT`;
    copy.append(title, meta);
    button.append(badge, copy);
    button.addEventListener('click', () => { state.selected = cite.entityId; renderDrawing(); renderEvidence(); });
    list.appendChild(button);
  });
}
async function ask(question) {
  if (state.busy || !state.drawing) return;
  state.busy = true;
  $('ask-button').disabled = true;
  $('answer-state').textContent = 'MEASURING…';
  try {
    const response = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ drawingId: state.drawing.id, question }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Question service unavailable.');
    state.result = payload.result;
    state.selected = state.result.evidence[0]?.entityId || null;
    renderAnswer(); renderEvidence(); renderDrawing();
  } catch (error) {
    state.result = { status: 'abstained', explanation: `Could not evaluate: ${error.message}`, evidence: [] };
    renderAnswer(); renderEvidence(); renderDrawing();
  } finally { state.busy = false; $('ask-button').disabled = false; }
}
async function useDemo() {
  const response = await fetch('/api/demo');
  if (!response.ok) throw new Error('Demo drawing could not be loaded.');
  state.drawing = (await response.json()).drawing;
  state.result = null; state.selected = null; state.zoom = 1;
  renderSource(); renderAnswer(); renderEvidence(); renderDrawing();
  $('question').value = updateQuickQueries() || '';
  if ($('question').value) await ask($('question').value);
}
async function importDrawing(file) {
  if (!file) return;
  if (!/\.dxf$/i.test(file.name)) throw new Error('Please choose an ASCII DXF file.');
  if (file.size > 6 * 1024 * 1024) throw new Error('Maximum supported file size is 6 MiB.');
  $('import-message').textContent = 'Reading file locally and mapping geometries…';
  const response = await fetch('/api/import-dxf', { method: 'POST', headers: {
    'Content-Type': 'application/dxf', 'X-Filename': encodeURIComponent(file.name) }, body: await file.arrayBuffer() });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'DXF import failed.');
  state.drawing = payload.drawing; state.result = null; state.selected = null; state.zoom = 1;
  $('import-message').textContent = `Imported ${state.drawing.entities.length} source entities. File is never stored on disk. Ask with an exact visible label or room number.`;
  renderSource(); renderAnswer(); renderEvidence(); renderDrawing();
  $('question').value = updateQuickQueries() || '';
  if ($('question').value) await ask($('question').value);
}

$('question-form').addEventListener('submit', e => {
  e.preventDefault();
  ask($('question').value.trim());
});
document.querySelectorAll('[data-q]').forEach(button => button.addEventListener('click', () => {
  $('question').value = button.dataset.q;
  ask(button.dataset.q);
}));
$('drawing-file').addEventListener('change', async event => {
  try { await importDrawing(event.target.files?.[0]); }
  catch (error) { $('import-message').textContent = `Import rejected: ${error.message}`; }
  finally { event.target.value = ''; }
});
$('demo-button').addEventListener('click', () => useDemo().catch(error => $('import-message').textContent = error.message));
$('zoom-in').addEventListener('click', () => { state.zoom = Math.min(3, state.zoom + .2); renderDrawing(); });
$('zoom-out').addEventListener('click', () => { state.zoom = Math.max(.7, state.zoom - .2); renderDrawing(); });
$('zoom-reset').addEventListener('click', () => { state.zoom = 1; renderDrawing(); });
useDemo().catch(error => $('import-message').textContent = `Startup failed: ${error.message}`);
