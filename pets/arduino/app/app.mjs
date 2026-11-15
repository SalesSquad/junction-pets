const $ = id => document.getElementById(id);
const state = {design: null, evidence: [], baseline: null, latest: null, latestRevision: -1,
  revision: 0, pending: false, dirtyEditor: false, errors: new Map(), selectedPin: null,
  request: null, timer: null, checkerVersion: null, compareRevision: 0, compareRequest: null};
const limitNames = {powerLimitMa: 'Kokonaisvirtaraja', pinLimitMa: 'Yhden pinnin raja', totalPinLimitMa: 'Pinnivirtojen yhteisraja'};
const statusNames = {consistent: 'Ilmoitukset sopivat', 'needs-review': 'Tarkistettavaa', invalid: 'Virheellinen syöte'};
const evidenceNames = {fictional: 'Kuvitteellinen', supplied: 'Toimitettu, ei tarkastettu', reviewed: 'Oma tarkastus (ei varmennettu)'};
const issueNames = {
  'voltage-mismatch': 'Syöttöjännitteet eivät vastaa toisiaan',
  'logic-voltage-mismatch': 'Signaalijännitteet eivät vastaa toisiaan',
  'missing-ground': 'Yhteistä maata ei ole ilmoitettu', 'duplicate-pin': 'Pinni on varattu useasti',
  'unknown-pin': 'Pinniä ei ole kortin tiedoissa', 'mode-mismatch': 'Pyydetty pinnitila ei ole tuettu',
  'pin-oversubscribed': 'Pinnin virtaraja ylittyy', 'power-oversubscribed': 'Kokonaisvirtaraja ylittyy',
  'signal-oversubscribed': 'Pinnivirtojen yhteisraja ylittyy', 'invalid-number': 'Luku ei ole sallittu',
  'missing-field': 'Pakollinen kenttä puuttuu', 'unknown-field': 'Tuntematon kenttä',
  'invalid-count': 'Ilmoitettu määrä ei vastaa pinnejä', 'malformed-or-unsupported-input': 'Tiedon rakenne ei kelpaa',
};
const safeText = value => value === null ? 'Tuntematon' : value === undefined ? '—' :
  typeof value === 'object' ? '[rakenteinen arvo]' : String(value).slice(0, 2000);
const ma = value => typeof value === 'number' && Number.isFinite(value) ? `${value.toLocaleString('fi-FI')} mA` : 'Tuntematon';
const mv = value => typeof value === 'number' && Number.isFinite(value) ? `${value.toLocaleString('fi-FI')} mV` : 'Tuntematon';
const clone = x => JSON.parse(JSON.stringify(x));
function evidenceURL(value) {
  if (typeof value !== 'string' || /\s/.test(value)) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url : null;
  } catch { return null; }
}
function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function setStatus(message) { $('app-status').textContent = message; }
function setBanner(message) { $('error-banner').textContent = message || ''; $('error-banner').hidden = !message; }
function busyOrInvalid() {
  return state.pending || state.dirtyEditor || state.errors.size > 0 || !state.latest ||
    state.latestRevision !== state.revision || state.latest.review?.status === 'invalid';
}
function updateActions() {
  const blocked = busyOrInvalid();
  $('download-json').disabled = blocked || !state.latest?.report;
  $('download-markdown').disabled = blocked || typeof state.latest?.reportText !== 'string';
  $('save-baseline').disabled = blocked;
  $('add-evidence').disabled = !state.design || state.pending || state.dirtyEditor || state.errors.size > 0 || state.latest?.review?.status === 'invalid';
  $('export-help').textContent = blocked
    ? 'Vienti estetty: keskeneräinen, virheellinen tai vielä tarkastamaton muutos. Tarkasta viimeisin suunnitelma ensin.'
    : 'Raportti vastaa viimeisintä tarkastettua suunnitelmaa. Se ei ole turvallisuustodistus.';
}
function invalidatePending() {
  clearTimeout(state.timer); state.request?.abort(); state.request = null;
  state.compareRevision++; state.compareRequest?.abort(); state.compareRequest = null;
  state.revision++; state.pending = false; updateActions();
}
async function api(path, body, signal) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body), signal});
  let result;
  try { result = await response.json(); } catch { throw new Error('Palvelin ei palauttanut luettavaa JSON-vastausta.'); }
  if (!response.ok) throw new Error(typeof result.error === 'string' ? result.error : 'Paikallinen tarkastelu epäonnistui.');
  return result;
}
function syncEditor() {
  $('design-json').value = JSON.stringify(state.design, null, 2);
  $('design-json').removeAttribute('aria-invalid'); state.dirtyEditor = false;
}
function refreshEvidencePaths() {
  const select = $('evidence-path'), previous = select.value, paths = [];
  let remaining = 4096;
  function walk(value, path, depth = 0) {
    if (--remaining < 0 || depth > 10) return;
    if (value === null || typeof value !== 'object') { if (path) paths.push([path, value]); return; }
    for (const key of Object.keys(value)) {
      const next = Array.isArray(value) ? `${path}[${key}]` : path ? `${path}.${key}` : key;
      walk(value[key], next, depth + 1);
      if (remaining < 0) break;
    }
  }
  walk(state.design, ''); select.replaceChildren();
  const preferred = paths.some(([path]) => path === 'board.supplyVoltageMv') ? 'board.supplyVoltageMv' :
    paths.some(([path]) => path === 'board.voltageMv') ? 'board.voltageMv' : paths[0]?.[0];
  for (const [path, value] of paths) {
    const option = node('option', `${path} · ${safeText(value).slice(0, 70)}`); option.value = path;
    option.defaultSelected = path === preferred; select.append(option);
  }
  if (paths.some(([path]) => path === previous)) select.value = previous;
  else if (preferred) select.value = preferred;
}
function renderEvidence() {
  const container = $('evidence-list'); container.replaceChildren();
  $('evidence-count').textContent = `${state.evidence.length} merkintää`;
  if (!state.evidence.length) { container.append(node('p', 'Ei lähdemerkintöjä. Suunnitelman luvut ovat edelleen vain ilmoitettuja tietoja.', 'field-help')); return; }
  for (const [index, entry] of state.evidence.entries()) {
    const card = node('article', undefined, 'evidence-item'), header = node('div', undefined, 'evidence-item-header');
    const info = node('div'); info.append(node('strong', entry.path), node('span', evidenceNames[entry.status] || entry.status, 'evidence-status'));
    const remove = node('button', 'Poista', 'button remove'); remove.type = 'button'; remove.setAttribute('aria-label', `Poista lähdemerkintä kentältä ${entry.path}`);
    remove.addEventListener('click', () => {state.evidence.splice(index, 1); renderEvidence(); scheduleReview();});
    header.append(info, remove); card.append(header);
    if (entry.url) {
      const url = evidenceURL(entry.url);
      if (url) {const link = node('a', url.hostname); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link);}
    }
    if (entry.revision) card.append(node('p', `Revisio: ${entry.revision}`));
    if (entry.excerpt) card.append(node('p', `Lähdeote: ${entry.excerpt}`));
    if (entry.note) card.append(node('p', entry.note));
    if (entry.status === 'reviewed') card.append(node('p', 'Käyttäjän oma tarkastus. Työkalu ei ole varmentanut lähdettä.'));
    container.append(card);
  }
}
function numericError(path, input, error) {
  state.errors.set(path, error); input.setAttribute('aria-invalid', 'true');
  invalidatePending(); setBanner(error); setStatus('Muutos ei kelpaa. Viimeinen kelvollinen lukuarvo säilyy suunnitelmassa; raportin vienti on estetty.');
  $('review-state').textContent = 'Muokkaus kesken';
}
function readInteger(input, path) {
  const raw = input.value.trim();
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw)) || Number(raw) > 1_000_000_000) {
    numericError(path, input, `${path}: anna kokonaisluku 0–1 000 000 000. Tyhjää arvoa ei tulkita nollaksi.`); return null;
  }
  state.errors.delete(path); input.removeAttribute('aria-invalid'); return Number(raw);
}
function changedDesign() {
  syncEditor(); refreshEvidencePaths();
  if (!state.errors.size) setBanner('');
  scheduleReview();
}
function renderControls() {
  const sensors = $('sensor-controls'), limits = $('limit-controls'); sensors.replaceChildren(); limits.replaceChildren();
  if (!state.design?.board || !Array.isArray(state.design?.sensors)) {
    sensors.append(node('p', 'Korjaa suunnitelman rakenne JSON-editorissa.', 'field-help')); return;
  }
  for (const [index, sensor] of state.design.sensors.entries()) {
    if (!sensor || typeof sensor !== 'object') continue;
    const row = node('div', undefined, 'sensor-row'), heading = node('div', undefined, 'sensor-row-heading');
    const label = node('label', safeText(sensor.id)); label.htmlFor = `sensor-current-${index}`;
    const numberWrap = node('div', undefined, 'number-wrap'), input = node('input');
    input.type = 'number'; input.min = '0'; input.max = '1000000000'; input.step = '1'; input.id = `sensor-current-${index}`;
    input.value = typeof sensor.currentMa === 'number' ? String(sensor.currentMa) : '';
    input.setAttribute('aria-label', `${safeText(sensor.id)}: ilmoitettu syöttövirta milliampeereina`);
    numberWrap.append(input, node('span', 'mA')); heading.append(label, numberWrap);
    const range = node('input'); range.type = 'range'; range.min = '0'; range.step = '1';
    range.max = String(Math.min(1_000_000_000, Math.max(100, typeof sensor.currentMa === 'number' ? sensor.currentMa * 2 : 100)));
    range.value = input.value || '0'; range.id = `sensor-range-${index}`;
    range.setAttribute('aria-label', `${safeText(sensor.id)}: muuta syöttövirtaa`);
    const path = `sensors[${index}].currentMa`;
    input.addEventListener('input', () => {
      const value = readInteger(input, path); if (value === null) return;
      sensor.currentMa = value; range.max = String(Math.max(Number(range.max), value)); range.value = String(value); changedDesign();
    });
    range.addEventListener('input', () => {
      sensor.currentMa = Number(range.value); input.value = range.value;
      state.errors.delete(path); input.removeAttribute('aria-invalid'); changedDesign();
    });
    row.append(heading, range); sensors.append(row);
  }
  for (const [key, title] of Object.entries(limitNames)) {
    const path = `board.${key}`, row = node('div', undefined, 'limit-row');
    const label = node('label', title, 'limit-label'); label.htmlFor = `limit-${key}`;
    const group = node('div', undefined, 'limit-inputs'), wrap = node('div', undefined, 'number-wrap'), input = node('input');
    input.type = 'number'; input.min = '0'; input.max = '1000000000'; input.step = '1'; input.id = `limit-${key}`;
    input.value = typeof state.design.board[key] === 'number' ? String(state.design.board[key]) : '';
    input.disabled = state.design.board[key] === null;
    const unknownLabel = node('label', undefined, 'unknown-label'), unknown = node('input'); unknown.type = 'checkbox';
    unknown.id = `unknown-${key}`; unknown.checked = state.design.board[key] === null;
    unknown.setAttribute('aria-label', `${title}: raja tuntematon`); unknownLabel.append(unknown, document.createTextNode('Tuntematon'));
    let known = typeof state.design.board[key] === 'number' ? state.design.board[key] : null;
    input.addEventListener('input', () => {const value = readInteger(input, path); if (value === null) return; known = value; state.design.board[key] = value; changedDesign();});
    unknown.addEventListener('change', () => {
      input.disabled = unknown.checked; state.errors.delete(path); input.removeAttribute('aria-invalid');
      if (unknown.checked) {state.design.board[key] = null; input.value = ''; changedDesign();}
      else if (known !== null) {input.value = String(known); state.design.board[key] = known; changedDesign();}
      else {input.value = ''; numericError(path, input, `${title}: anna tunnettu raja. Tyhjää kenttää ei korvata nollalla.`); input.focus();}
    });
    wrap.append(input, node('span', 'mA')); group.append(wrap, unknownLabel); row.append(label, group); limits.append(row);
  }
}
function renderBudgets(review) {
  const container = $('budget-bars'); container.replaceChildren();
  for (const [key, title] of [['total', 'Kokonaisvirta'], ['signal', 'Pinnivirrat yhteensä']]) {
    const budget = review?.budgets?.[key]; if (!budget) continue;
    const block = node('div'), labels = node('div', undefined, 'budget-line');
    labels.append(node('strong', title), node('span', `${ma(budget.demandMa)} / ${ma(budget.limitMa)}`));
    const track = node('progress', undefined, 'budget-track'); track.max = 100;
    const over = typeof budget.headroomMa === 'number' && budget.headroomMa < 0;
    if (over) track.classList.add('over');
    const percent = typeof budget.limitMa === 'number' ? budget.limitMa > 0 ? budget.demandMa / budget.limitMa * 100 : budget.demandMa > 0 ? 100 : 0 : 0;
    if (typeof budget.limitMa === 'number') track.value = Math.max(0, Math.min(100, percent));
    track.setAttribute('aria-label', `${title}: tarve ${ma(budget.demandMa)}, raja ${ma(budget.limitMa)}`);
    const caption = node('p', `Virtavara: ${ma(budget.headroomMa)}${over ? ' · raja ylittyy' : ''}`, 'budget-caption');
    if (over) caption.classList.add('over-text'); block.append(labels, track, caption); container.append(block);
  }
}
function pinAssignments(pin) {
  const assignments = [];
  if (Array.isArray(state.design?.sensors)) for (const sensor of state.design.sensors) {
    if (Array.isArray(sensor?.pins)) for (const p of sensor.pins) if (p?.pin === pin) assignments.push({sensor, ...p});
  }
  return assignments;
}
function showPinDetails() {
  const target = $('pin-details'); target.replaceChildren();
  const pins = state.design?.board?.pins;
  const pin = Array.isArray(pins) ? pins.find(p => p?.id === state.selectedPin) : null;
  if (!pin) {target.append(node('p', 'Valitse pinni nähdäksesi sen ilmoitetut varaukset ja rajat.')); return;}
  const assignments = pinAssignments(pin.id), budget = state.latest?.review?.budgets?.pins?.find(p => p.pin === pin.id);
  target.append(node('strong', `${pin.id} · ilmoitetut tiedot`));
  const grid = node('dl', undefined, 'detail-grid');
  const board = state.design.board;
  const entries = [
    ['Tuetut tilat', Array.isArray(pin.modes) ? pin.modes.join(', ') : '—'],
    ['Kortin signaalijännite', mv(board.logicVoltageMv ?? board.voltageMv)],
    ['Ilmoitettu syöttöjännite', mv(board.supplyVoltageMv ?? board.voltageMv)],
    ['Pinnin ilmoitettu virtatarve', ma(budget?.demandMa)],
    ['Yhden pinnin virtaraja', ma(board.pinLimitMa)],
    ['Virtavara', ma(budget?.headroomMa)],
    ['Varaukset', assignments.length ? assignments.map(p => `${safeText(p.sensor.id)} (${safeText(p.mode)}, ${ma(p.currentMa)})`).join('; ') : 'Ei varauksia'],
  ];
  for (const [label, value] of entries) {const item = node('div'); item.append(node('dt', label), node('dd', value)); grid.append(item);}
  target.append(grid);
  const issues = state.latest?.review?.issues?.filter(issue => issue.endsWith(`:${pin.id}`)) || [];
  for (const issue of issues) target.append(node('p', issue, 'over-text'));
  target.append(node('p', 'Näkymä kuvaa ilmoitettua suunnitelmaa. Se ei ole todellinen pinout tai kytkentäohje.', 'field-help'));
}
function renderPinMap(review) {
  const container = $('pin-map'); container.replaceChildren();
  const board = state.design?.board, pins = Array.isArray(board?.pins) ? board.pins : [];
  $('voltage-summary').textContent = board ? `Syöttö ${mv(board.supplyVoltageMv ?? board.voltageMv)} · signaali ${mv(board.logicVoltageMv ?? board.voltageMv)}` : 'Jännitetiedot puuttuvat';
  for (const pin of pins) {
    if (!pin || typeof pin.id !== 'string') continue;
    const assignments = pinAssignments(pin.id), button = node('button', undefined, 'pin-card');
    button.type = 'button'; button.dataset.pin = pin.id;
    button.setAttribute('aria-pressed', String(state.selectedPin === pin.id));
    button.setAttribute('aria-label', `Pinni ${pin.id}, ${assignments.length} varausta. Näytä tiedot.`);
    if (review?.issues?.some(issue => issue.endsWith(`:${pin.id}`))) button.classList.add('has-issues');
    button.append(node('strong', pin.id), node('small', Array.isArray(pin.modes) ? pin.modes.join(' / ') : 'Tila puuttuu'), node('small', assignments.length ? `${assignments.length} varausta` : 'Vapaa suunnitelmassa'));
    button.addEventListener('click', () => {state.selectedPin = pin.id; for (const b of container.querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.pin === pin.id)); showPinDetails();});
    container.append(button);
  }
  if (!pins.length) container.append(node('p', 'Kelvollista pinnilistaa ei ole. Tarkista JSON-suunnitelma.'));
  showPinDetails();
}
function renderFindings(review) {
  const container = $('findings-list'); container.replaceChildren();
  if (!review?.diagnostics?.length) container.append(node('p', 'Ilmoitusten välisiä ristiriitoja ei löytynyt tässä mallissa.', 'good-message'));
  for (const diagnostic of review?.diagnostics || []) {
    const item = node('article', undefined, 'finding'), code = safeText(diagnostic.code);
    item.append(node('span', safeText(diagnostic.path), 'finding-path'), node('h3', issueNames[code.split(':')[0]] || (code.startsWith('unknown-') ? 'Ilmoitettu raja on tuntematon' : code)));
    item.append(node('p', `Ilmoitettu: ${safeText(diagnostic.actual)}`), node('p', `Odotettu: ${safeText(diagnostic.expected)}`));
    item.append(node('p', safeText(diagnostic.correction))); container.append(item);
  }
  const unknowns = node('details', undefined, 'unknowns'), summary = node('summary', 'Mikä jää edelleen tuntemattomaksi?'), list = node('ul');
  for (const unknown of review?.unknowns || []) list.append(node('li', safeText(unknown)));
  list.append(node('li', 'Lähdemerkinnät ovat käyttäjän ilmoituksia, eivät työkalun varmennuksia.')); unknowns.append(summary, list); container.append(unknowns);
}
function renderReview() {
  const review = state.latest?.review;
  $('review-state').textContent = statusNames[review?.status] || 'Ei tulosta';
  $('review-state').classList.toggle('over-text', review?.status !== 'consistent');
  $('review-caption').textContent = review?.status === 'consistent' ? 'Vain ilmoitetun mallin sisällä' : `${review?.issues?.length || 0} tarkastettavaa ilmoitusta`;
  $('summary-total').textContent = ma(review?.budgets?.total?.demandMa);
  $('summary-total-limit').textContent = `Ilmoitettu raja ${ma(review?.budgets?.total?.limitMa)}`;
  $('summary-headroom').textContent = ma(review?.budgets?.total?.headroomMa);
  $('summary-headroom').classList.toggle('over-text', typeof review?.budgets?.total?.headroomMa === 'number' && review.budgets.total.headroomMa < 0);
  const pinCount = Array.isArray(state.design?.board?.pins) ? state.design.board.pins.length : 0;
  $('summary-pins').textContent = String(pinCount);
  $('summary-pin-caption').textContent = `${review?.budgets?.pins?.length || 0} ilmoitettua varausta`;
  renderBudgets(review); renderPinMap(review); renderFindings(review); updateActions();
}
async function compare(revision) {
  if (!state.baseline || busyOrInvalid()) return;
  const baseline = state.baseline, compareRevision = ++state.compareRevision;
  state.compareRequest?.abort();
  const request = new AbortController(); state.compareRequest = request;
  const current = () => compareRevision === state.compareRevision && revision === state.revision && baseline === state.baseline;
  const target = $('compare-result'); target.replaceChildren(node('p', 'Verrataan nykyistä ehdotusta tallennettuun tasoon…'));
  try {
    const result = await api('/api/compare', {baseline, candidate: state.design}, request.signal);
    if (!current()) return;
    target.replaceChildren(node('p', 'Vertailutaso säilyy muistissa. Ehdotus on viimeisin tarkastettu suunnitelma.'));
    const metrics = node('div', undefined, 'compare-metrics');
    for (const [key, title] of [['total', 'Kokonaisvirran virtavara'], ['signal', 'Pinnivirtojen virtavara']]) {
      const change = result.budgetChanges?.[key], cell = node('div', undefined, 'compare-metric');
      const delta = typeof change?.deltaHeadroomMa === 'number' ? `${change.deltaHeadroomMa > 0 ? '+' : ''}${ma(change.deltaHeadroomMa)}` : 'Tuntematon';
      cell.append(node('span', title), node('strong', delta), node('span', `${ma(change?.baselineHeadroomMa)} → ${ma(change?.candidateHeadroomMa)}`)); metrics.append(cell);
    }
    target.append(metrics);
    for (const [key, title, empty] of [['addedIssues', 'Uudet huomiot', 'Ei uusia huomioita.'], ['resolvedIssues', 'Poistuneet huomiot', 'Ei poistuneita huomioita.']]) {
      target.append(node('h3', title));
      if (result[key]?.length) {const list = node('ul'); for (const issue of result[key]) list.append(node('li', safeText(issue))); target.append(list);}
      else target.append(node('p', empty));
    }
    for (const limitation of result.limitations || []) target.append(node('p', safeText(limitation), 'field-help'));
  } catch (error) {if (current() && error.name !== 'AbortError') target.replaceChildren(node('p', `Vertailu epäonnistui: ${error.message}`, 'over-text'));}
}
function scheduleReview() {
  invalidatePending();
  if (state.errors.size || state.dirtyEditor) {updateActions(); return;}
  const revision = state.revision; state.pending = true; updateActions();
  setStatus('Tarkastetaan viimeisintä muutosta…');
  state.timer = setTimeout(async () => {
    const request = new AbortController(); state.request = request;
    try {
      const result = await api('/api/review', {design: state.design, evidence: state.evidence.map(({path, status, url, revision, excerpt, note}) => ({path, status, url, revision, excerpt, note}))}, request.signal);
      if (revision !== state.revision) return;
      state.latest = result; state.latestRevision = revision; state.pending = false;
      state.checkerVersion = result.checkerVersion; $('checker-version').textContent = `Tarkistin ${safeText(result.checkerVersion)}`;
      setBanner(''); renderReview();
      setStatus(result.review.status === 'invalid' ? 'Suunnitelma ei kelpaa. Korjaa ilmoitetut kentät; vienti on estetty.' : 'Viimeisin suunnitelma tarkastettu paikallisesti. Lähtötietoja tai fyysistä turvallisuutta ei ole varmennettu.');
      if (state.baseline) compare(revision);
    } catch (error) {
      if (revision !== state.revision || error.name === 'AbortError') return;
      state.pending = false; state.latestRevision = -1; setBanner(error.message); setStatus('Tarkastelu epäonnistui. Raportin vienti on estetty.'); updateActions();
    }
  }, 120);
}
async function loadExample() {
  invalidatePending(); state.pending = true; updateActions(); setStatus('Ladataan kuvitteellista esimerkkiä…');
  const revision = state.revision;
  try {
    const result = await api('/api/example'); if (revision !== state.revision) return;
    state.design = result.design; state.evidence = []; state.baseline = null; state.latest = null;
    state.selectedPin = null; state.errors.clear(); state.dirtyEditor = false; state.checkerVersion = result.checkerVersion;
    $('compare-result').replaceChildren(node('p', 'Vertailutasoa ei ole vielä tallennettu.'));
    $('save-baseline').textContent = 'Tallenna vertailutaso'; $('evidence-form').reset(); evidenceRequirements();
    $('evidence-error').hidden = true; syncEditor(); renderControls(); refreshEvidencePaths(); renderEvidence(); setBanner(''); scheduleReview();
  } catch (error) {if (revision === state.revision) {state.pending = false; setBanner(error.message); setStatus('Esimerkkiä ei saatu ladattua. Kokeile Palauta esimerkki -painiketta.'); updateActions();}}
}
function applyJson(text) {
  try {
    if (new TextEncoder().encode(text).length > 256 * 1024) throw new Error('Suunnitelma on liian suuri (enintään 256 KiB).');
    const design = JSON.parse(text);
    if (design && typeof design === 'object' && !Array.isArray(design) && ('report' in design || 'review' in design || 'reportVersion' in design)) throw new Error('Tuo suunnitelman JSON, älä raporttia. Suunnitelmassa ovat board ja sensors.');
    state.design = design; state.evidence = []; state.errors.clear(); state.dirtyEditor = false; state.selectedPin = null;
    $('design-json').removeAttribute('aria-invalid'); syncEditor(); renderControls(); refreshEvidencePaths(); renderEvidence(); setBanner(''); scheduleReview();
  } catch (error) {state.dirtyEditor = true; $('design-json').setAttribute('aria-invalid', 'true'); invalidatePending(); setBanner(`JSON ei kelpaa: ${error.message}`); setStatus('JSON-muokkausta ei ole sovellettu. Edellinen suunnitelma säilyy; vienti on estetty.');}
}
function evidenceRequirements() {
  const reviewed = $('evidence-status').value === 'reviewed';
  for (const id of ['evidence-url', 'evidence-revision', 'evidence-excerpt', 'evidence-note']) $(id).required = reviewed;
  $('evidence-help').textContent = reviewed ? 'Oma tarkastus vaatii HTTPS-lähteen, revision, lähdeotteen ja huomion. Merkintä ei ole työkalun varmentama.' : 'Merkinnät eivät muuta tarkistimen tulosta eivätkä anna käyttöoikeuksia.';
}
$('evidence-status').addEventListener('change', evidenceRequirements);
$('evidence-form').addEventListener('submit', event => {
  event.preventDefault();
  if (busyOrInvalid()) return;
  if (state.evidence.length >= 100) {
    $('evidence-error').textContent = 'Enintään 100 lähdemerkintää.';
    $('evidence-error').hidden = false;
    return;
  }
  const entry = Object.fromEntries(['path', 'status', 'url', 'revision', 'excerpt', 'note'].map(key => [key, $(`evidence-${key}`).value.trim()]));
  let error = '';
  if (!entry.path) error = 'Valitse suunnitelman kenttä.';
  if (entry.url && !evidenceURL(entry.url)) error = 'Anna kelvollinen HTTPS-osoite ilman käyttäjätunnusta, salasanaa tai välilyöntejä.';
  if (entry.status === 'reviewed' && ['url', 'revision', 'excerpt', 'note'].some(key => !entry[key])) error = 'Täytä lähde, revisio, lähdeote ja huomio omaa tarkastusta varten.';
  $('evidence-error').textContent = error; $('evidence-error').hidden = !error; if (error) return;
  state.evidence.push(entry); renderEvidence(); scheduleReview();
});
$('save-baseline').addEventListener('click', () => {
  if (busyOrInvalid()) return; state.baseline = clone(state.design);
  $('save-baseline').textContent = 'Korvaa vertailutaso'; compare(state.revision); setStatus('Vertailutaso tallennettu tämän välilehden muistiin. Muuta nyt ehdotusta.');
});
$('reset-example').addEventListener('click', loadExample);
$('design-json').addEventListener('input', () => {
  state.dirtyEditor = true; invalidatePending();
  setStatus('JSON-editorissa on soveltamattomia muutoksia. Paina Tarkasta JSON. Raportin vienti on estetty.');
});
$('apply-json').addEventListener('click', () => applyJson($('design-json').value));
$('import-json').addEventListener('change', async event => {
  const file = event.target.files?.[0]; if (!file) return;
  invalidatePending(); state.dirtyEditor = true; updateActions();
  if (file.size > 256 * 1024) {setBanner('Tiedosto on liian suuri. Suunnitelman enimmäiskoko on 256 KiB.'); setStatus('Tuontia ei sovellettu. Raportin vienti on estetty.'); event.target.value = ''; return;}
  const revision = state.revision;
  try {const text = await file.text(); if (revision !== state.revision) return; $('design-json').value = text; applyJson(text);}
  catch (error) {setBanner(`Tiedoston lukeminen epäonnistui: ${error.message}`);}
  event.target.value = '';
});
function download(format) {
  if (busyOrInvalid()) return;
  const text = format === 'json' ? JSON.stringify(state.latest.report, null, 2) + '\n' : state.latest.reportText;
  const blob = new Blob([text], {type: format === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8'});
  const url = URL.createObjectURL(blob), anchor = node('a'); anchor.href = url;
  anchor.download = `piiripoyta-raportti.${format === 'json' ? 'json' : 'md'}`; document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus('Viimeisimmän tarkastetun suunnitelman raportti ladattu.');
}
$('download-json').addEventListener('click', () => download('json'));
$('download-markdown').addEventListener('click', () => download('markdown'));
loadExample();
