import {
  cloudAssessment,
  filterPets,
  formatDate,
  normalizeRegistry,
  petSourceUrl,
  pluginAssessment,
  safeCount,
  safeCloudTaskUrl,
  safePluginPageUrl,
  snapshotAge,
  sourceCommit,
  text,
} from './status-model.mjs';
import {advisoryCloudLabel, advisoryEvidenceLabel, normalizeServerProjection} from './server-projection.mjs';

const byId = id => document.getElementById(id);
const elements = {
  list: byId('fleet-list'), grid: byId('fleet-grid'),
  search: byId('search'), role: byId('role'), reload: byId('reload'),
  dialog: byId('detail'), detailTitle: byId('detail-title'),
  detailContent: byId('detail-content'), sourceLink: byId('source-link'),
};

let registry = null;
let fleetProjection = null; // Browser-received JSON: advisory only, never a trust anchor.
let activeMode = 'all';
let activeSearch = '';
let activeRole = 'all';

function make(tag, className = '', content = undefined) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = String(content);
  return element;
}

function put(id, value) { byId(id).textContent = String(value); }

function roleName(value) {
  const names = {challenge: 'CHALLENGE', technology: 'TECH PARTNER', main: 'MAIN PARTNER', collaborator: 'COLLABORATOR'};
  return names[value] || 'COMPANION';
}

function statusBadge(assessment) {
  return make('span', `state-pill ${assessment.tone}`, assessment.label);
}

function renderFleetGrid() {
  elements.grid.replaceChildren();
  const fragment = document.createDocumentFragment();
  for (const pet of registry.pets) {
    const cloud = cloudAssessment(pet.cloud);
    const unit = make('span', `grid-unit ${cloud.tone}`);
    unit.title = `${pet.company.name}: ${cloud.label}`;
    fragment.append(unit);
  }
  elements.grid.append(fragment);
  put('grid-label', `${registry.pets.length} / ${registry.pets.length} DEFINED`);
}

function renderStatusBar() {
  const age = snapshotAge(registry.generatedAt);
  const commit = sourceCommit(registry.source);
  const sourceVerification = text(registry.source.verification, 'unverified');
  put('snapshot-title', age.stale ? 'Stored snapshot — recheck source' : 'Snapshot loaded — not a live monitor');
  put('snapshot-age', `${age.label} · ${formatDate(registry.generatedAt)}`);
  put('source-sha', !commit ? 'NO VERIFIED COMMIT' : sourceVerification === 'local-git-only' ? 'LOCAL RECONSTRUCTION · NOT HOSTED' : `${commit.slice(0, 12)} · ${sourceVerification} claim`);
  // The UI cannot independently attest a GitHub/source snapshot. Freshness is
  // useful metadata but not a green qualification gate.
  byId('snapshot-dot').className = `pulse-dot ${age.stale ? 'warning' : 'neutral'}`;
}

function calcCounts() {
  return {
    cloud: registry.pets.filter(pet => ['running', 'ready'].includes(cloudAssessment(pet.cloud).effectiveState)).length,
    needs: registry.pets.filter(pet => cloudAssessment(pet.cloud).effectiveState === 'unprovisioned').length,
    pendingId: registry.pets.filter(pet => cloudAssessment(pet.cloud).effectiveState === 'published-id-pending').length,
    active: filterPets(registry.pets, {mode: 'active'}).length,
    issues: filterPets(registry.pets, {mode: 'issues'}).length,
    ready: filterPets(registry.pets, {mode: 'ready'}).length,
    blocked: registry.pets.filter(pet => text(pet.blocker, '') || ['blocked', 'failed'].includes(pet.development?.state) || ['blocked', 'failed'].includes(pet.cloud?.state)).length,
    written: registry.pets.reduce((sum, pet) => sum + safeCount(pet.evaluation?.defined), 0),
    executed: registry.pets.reduce((sum, pet) => sum + safeCount(pet.evaluation?.executed), 0),
  };
}

function renderMetrics() {
  const c = calcCounts();
  put('metric-total', registry.pets.length.toString().padStart(2, '0'));
  put('metric-roster', 'One package + developer agent per company');
  put('metric-cloud', c.cloud.toString().padStart(2, '0'));
  put('metric-unprovisioned', `${c.needs} need provisioning · ${c.pendingId} published, ID pending`);
  put('metric-evals', `${c.executed}/${c.written}`);
  put('metric-blocked', c.blocked.toString().padStart(2, '0'));
  put('count-all', registry.pets.length);
  put('count-needs', c.needs);
  put('count-active', c.active);
  put('count-ready', c.ready);
  put('count-issues', c.issues);
}

function petRow(pet) {
  const assessment = cloudAssessment(pet.cloud);
  const serverReport = fleetProjection?.byPet.get(pet.slug);
  const item = make('div');
  item.setAttribute('role', 'listitem');
  const button = make('button', 'pet-row');
  button.type = 'button';
  button.setAttribute('aria-label', `Inspect ${pet.company.name}, ${assessment.label}`);
  button.addEventListener('click', () => openDetail(pet));

  const identity = make('span', 'pet-identity');
  const avatar = make('span', 'pet-avatar', pet.company.name.trim().slice(0, 2).toUpperCase());
  avatar.setAttribute('aria-hidden', 'true');
  const identityText = make('span');
  identityText.append(make('strong', '', pet.company.name), make('small', '', text(pet.agent.id, pet.slug)));
  identity.append(avatar, identityText);

  const cloud = make('span', 'cell-detail');
  cloud.append(statusBadge(assessment), make('span', 'subline', text(pet.cloud?.desiredName, 'No Cloud profile')));
  if (assessment.effectiveState === 'published-id-pending') cloud.append(make('span', 'subline',
    `${safeCount(pet.cloud?.taskCheck?.passed)}/${safeCount(pet.cloud?.taskCheck?.executed)} submission-gate tests · ${pet.cloud?.taskCheck?.binding === 'stale-source' ? 'historical, stale SHA' : 'source matched, reported'}`));
  if (serverReport) cloud.append(make('span', 'subline', advisoryCloudLabel(serverReport)));

  const evals = make('span', 'cell-detail', `${safeCount(pet.evaluation?.executed)} / ${safeCount(pet.evaluation?.defined)} executed`);
  evals.append(make('span', 'subline', `${safeCount(pet.evaluation?.passed)} reported pass · ${safeCount(pet.evaluation?.failed)} reported fail`));
  if (serverReport) evals.append(make('span', 'subline', advisoryEvidenceLabel(serverReport.evaluation, 'Model eval')));

  const action = make('span', 'cell-action');
  action.append(make('span', 'action-text', text(pet.nextAction, 'Next action unassigned')),
    make('span', 'row-arrow', '↗'));
  button.append(identity, cloud, evals, action);
  item.append(button);
  return item;
}

function renderList() {
  if (!registry) return;
  const displayed = filterPets(registry.pets, {query: activeSearch, role: activeRole, mode: activeMode});
  elements.list.replaceChildren();
  if (displayed.length === 0) {
    const empty = make('div', 'placeholder');
    empty.append(make('strong', '', 'No matching companions'),
      make('span', '', 'Try a different search, role or pipeline filter.'));
    elements.list.append(empty);
  } else {
    const fragment = document.createDocumentFragment();
    displayed.forEach(pet => fragment.append(petRow(pet)));
    elements.list.append(fragment);
  }
  put('visible-count', displayed.length.toString().padStart(2, '0'));
  put('list-footer-count', `Showing ${displayed.length} of ${registry.pets.length} source-defined companions`);
}

function detailRow(label, value, code = false) {
  const row = make('div', 'detail-row');
  row.append(make('div', 'detail-row-label', label));
  const content = make('div', 'detail-row-value');
  content.append(make(code ? 'code' : 'span', '', value));
  row.append(content);
  return row;
}

function detailStatusRow(label, assessment, metadata) {
  const row = make('div', 'detail-row');
  row.append(make('div', 'detail-row-label', label), statusBadge(assessment),
    make('div', 'detail-meta', metadata));
  return row;
}

function kpi(value, label) {
  const item = make('div', 'detail-kpi');
  item.append(make('strong', '', value), make('span', '', label));
  return item;
}

function openDetail(pet) {
  const assessment = cloudAssessment(pet.cloud);
  const serverReport = fleetProjection?.byPet.get(pet.slug);
  const plugin = pluginAssessment(pet.plugin, pet.slug);
  elements.detailTitle.textContent = pet.company.name;
  elements.detailContent.replaceChildren();
  const pillRow = make('div', 'detail-row');
  pillRow.append(make('div', 'detail-row-label', 'Codex Cloud'), statusBadge(assessment),
    make('div', 'detail-meta', `Desired environment: ${text(pet.cloud?.desiredName)} · ${text(pet.cloud?.provider)}`));
  elements.detailContent.append(pillRow);

  const columns = make('div', 'detail-row detail-columns');
  columns.append(kpi(`${safeCount(pet.evaluation?.executed)} / ${safeCount(pet.evaluation?.defined)}`, 'reported runs / authored cases'),
    kpi(`${safeCount(pet.evaluation?.passed)}`, 'reported passes · not independently qualified'));
  elements.detailContent.append(columns);
  elements.detailContent.append(
    detailRow('Backend report / browser attestation', serverReport
      ? 'Source-bound server claim loaded; not independently browser-attested'
      : 'No matching backend report · source snapshot only'),
    detailRow('Backend cloud (advisory)', advisoryCloudLabel(serverReport)),
    detailRow('Backend CI (advisory)', advisoryEvidenceLabel(serverReport?.ci, 'CI')),
    detailRow('Backend model evaluations (advisory)', advisoryEvidenceLabel(serverReport?.evaluation, 'Model eval')),
    detailRow('Backend host grant (not execution permission)', serverReport?.grant === 'revoked'
      ? 'Backend reports revoked · deny external execution'
      : serverReport?.grant === 'host-verified'
        ? 'Backend reports active host receipt · runtime still not authorized by UI'
        : 'No browser-verifiable host grant'),
    detailRow('Backend source SHA (advisory)', fleetProjection?.sourceSha || 'No matching backend SHA', true),
  );

  elements.detailContent.append(
    detailRow('Development agent', text(pet.agent?.id), true),
    detailRow('Work item', text(pet.agent?.workItem), true),
    detailRow('Developer instructions', text(pet.agent?.instructions), true),
    detailRow('Company-specific behavior', text(pet.agent?.petInstructions), true),
    detailStatusRow('Plugin / source manifest', plugin.source,
      `Desired: ${text(pet.plugin?.desiredName)} · File: ${text(pet.plugin?.sourcePath)}`),
    detailStatusRow('Plugin / recorded private registration', plugin.registration,
      `Recorded ID: ${text(pet.plugin?.pluginId, 'None')} · Release: ${text(pet.plugin?.releaseId, 'None')} · Visibility: ${text(pet.plugin?.visibility, 'Not recorded')}`),
    detailStatusRow('Plugin / verified host installation', plugin.host,
      `Evidence: ${text(pet.plugin?.verification)} · Binding: ${text(pet.plugin?.registrationBinding)} · Last reported: ${formatDate(pet.plugin?.observedAt)}`),
    detailRow('Plugin source bundle SHA (advisory)', text(pet.plugin?.sourceBundleSha256, 'None'), true),
    detailRow('Environment ID', assessment.effectiveState === 'unverified' ? 'No verified environment ID' : text(pet.cloud?.environmentId, 'Not assigned'), true),
    detailRow('Owner publication observation (not independently rechecked)',
      assessment.effectiveState === 'published-id-pending'
        ? 'Owner report: published/selectable in Codex Settings + task picker · opaque ID still missing'
        : 'No recorded owner publication observation'),
    detailRow('Owner observation recorded at (advisory)', formatDate(pet.cloud?.verifiedAt)),
    detailRow('Codex task checks (advisory, NOT model evaluations)',
      assessment.effectiveState === 'published-id-pending'
        ? `${safeCount(pet.cloud?.taskCheck?.passed)}/${safeCount(pet.cloud?.taskCheck?.executed)} reported pass · ${pet.cloud?.taskCheck?.binding === 'stale-source' ? 'OLD source, rerun needed' : 'source matched'} · not hosted-qualified`
        : 'No current source-bound Cloud task checks'),
    detailRow('Codex task source SHA (advisory)', text(pet.cloud?.sourceCommit, 'Not recorded'), true),
    detailRow('Development status', text(pet.development?.state)),
    detailRow('Work branch', text(pet.development?.branch), true),
    detailRow('Recorded work SHA (advisory)', text(pet.development?.sourceCommit), true),
    detailRow('Recipient runtime', `${text(pet.runtime?.state)} · ${text(pet.runtime?.publicationState, 'not-published')}`),
    detailRow('Open blocker', text(pet.blocker, 'No recorded blocker')),
    detailRow('Next action', text(pet.nextAction, 'Assign an evidence-backed next step')),
  );

  const cloudTaskUrl = safeCloudTaskUrl(pet.cloud);
  if (cloudTaskUrl && assessment.effectiveState === 'published-id-pending') {
    const row = detailRow('Codex Cloud task evidence · not environment readiness', 'Recorded task');
    const value = row.querySelector('.detail-row-value');
    value.replaceChildren();
    const link = make('a', '', 'Open owner-reported Cloud task ↗');
    link.href = cloudTaskUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    value.append(link);
    elements.detailContent.append(row);
  }

  const reportedPluginUrl = safePluginPageUrl(pet.plugin);
  if (reportedPluginUrl) {
    const row = make('div', 'detail-row');
    row.append(make('div', 'detail-row-label', 'Reported plugin page · registration not independently verified'));
    const content = make('div', 'detail-row-value');
    const link = make('a', '', 'Open reported private plugin page ↗');
    link.href = reportedPluginUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    content.append(link);
    row.append(content);
    elements.detailContent.append(row);
  }

  if (typeof pet.development?.prUrl === 'string' && /^https:\/\/github\.com\/SalesSquad\/junction-pets\/pull\/\d+$/.test(pet.development.prUrl)) {
    const row = detailRow('Development PR', pet.development.prUrl);
    const value = row.querySelector('.detail-row-value');
    value.replaceChildren();
    const link = make('a', '', `Open PR ↗`);
    link.href = pet.development.prUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    value.append(link);
    elements.detailContent.append(row);
  }

  elements.sourceLink.href = petSourceUrl(pet, registry.source);
  // A dirty/reconstructed local snapshot has no verified PR or hosted HEAD.
  // Its safe main-branch link is a BASELINE reference, not the package bytes
  // currently displayed in this private operations snapshot.
  elements.sourceLink.textContent = sourceCommit(registry.source) &&
    registry.source?.verification !== 'local-git-only'
    ? 'Open recorded source claim ↗'
    : 'Open main baseline (snapshot unverified) ↗';
  elements.dialog.showModal();
}

function renderError(message) {
  registry = null;
  fleetProjection = null;
  put('projection-status', 'Backend feed unavailable · no Cloud or CI readiness inferred');
  elements.grid.replaceChildren();
  ['metric-total', 'metric-cloud', 'metric-evals', 'metric-blocked', 'visible-count', 'count-all', 'count-needs', 'count-active', 'count-ready', 'count-issues'].forEach(id => put(id, '—'));
  put('grid-label', 'NO VERIFIED SNAPSHOT');
  put('snapshot-title', 'Status unavailable — no readiness inferred');
  put('snapshot-age', message);
  put('source-sha', 'UNVERIFIED');
  byId('snapshot-dot').className = 'pulse-dot critical';
  elements.list.replaceChildren();
  const placeholder = make('div', 'placeholder');
  placeholder.append(make('strong', '', 'Unable to verify the companion registry'),
    make('span', '', message));
  const retry = make('button', '', 'Retry snapshot');
  retry.type = 'button';
  retry.addEventListener('click', loadSnapshot);
  placeholder.append(retry);
  elements.list.append(placeholder);
}

async function readOptionalServerProjection() {
  fleetProjection = null;
  let note = 'No server projection connected · source snapshot only';
  try {
    // An owner-private server may generate this sidecar. The browser cannot
    // independently authenticate its provider/host receipts, so status always
    // remains advisory and the existing non-green Cloud gate is unchanged.
    const response = await fetch('./fleet-projection.json', {
      cache: 'no-store', headers: {'Accept': 'application/json'},
    });
    if (response.ok) {
      fleetProjection = normalizeServerProjection(await response.json(), registry);
      note = fleetProjection.stale
        ? 'Backend report STALE · not browser-attested · stored snapshot retained'
        : 'Backend report loaded · source SHA matched · provider claims NOT browser-attested';
    } else if (response.status !== 404) {
      note = 'Backend report HTTP ' + response.status + ' · stored snapshot retained';
    }
  } catch {
    note = 'Backend report rejected or unavailable · stored snapshot retained';
  }
  put('projection-status', note);
  renderList();
}

async function loadSnapshot() {
  elements.reload.disabled = true;
  fleetProjection = null;
  put('projection-status', 'Checking optional backend report · no readiness assumed');
  put('snapshot-title', 'Reading source snapshot…');
  try {
    const response = await fetch('./status.json', {cache: 'no-store', headers: {'Accept': 'application/json'}});
    if (!response.ok) throw new Error(`Registry request returned HTTP ${response.status}`);
    const payload = await response.json();
    registry = normalizeRegistry(payload);
    renderFleetGrid();
    renderStatusBar();
    renderMetrics();
    renderList();
    await readOptionalServerProjection();
  } catch (error) {
    renderError(error instanceof Error ? error.message : 'Unknown registry failure');
  } finally {
    elements.reload.disabled = false;
  }
}

elements.search.addEventListener('input', event => { activeSearch = event.target.value; renderList(); });
elements.role.addEventListener('change', event => { activeRole = event.target.value; renderList(); });
document.querySelectorAll('[data-mode]').forEach(button => {
  button.addEventListener('click', () => {
    activeMode = button.dataset.mode;
    document.querySelectorAll('[data-mode]').forEach(other => {
      const active = other === button;
      other.classList.toggle('is-active', active);
      other.setAttribute('aria-pressed', String(active));
    });
    renderList();
  });
});
elements.reload.addEventListener('click', loadSnapshot);
byId('close-detail').addEventListener('click', () => elements.dialog.close());
byId('close-detail-bottom').addEventListener('click', () => elements.dialog.close());
elements.dialog.addEventListener('click', event => { if (event.target === elements.dialog) elements.dialog.close(); });
void loadSnapshot();
