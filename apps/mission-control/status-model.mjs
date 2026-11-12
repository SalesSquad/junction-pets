/** Pure, fail-closed presentation model. No network calls or credentials. */
export const SOURCE_REPOSITORY = 'SalesSquad/junction-pets';
const SHA = /^[0-9a-f]{40}$/i;
const SLUG = /^junction-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const CLAIMED_READY_STATES = new Set(['ready', 'running', 'reported-ready', 'reported-running']);

export function text(value, fallback = 'Not recorded') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

export function sourceCommit(source) {
  return SHA.test(source?.commit || '') ? source.commit.toLowerCase() : null;
}

export function cloudAssessment(cloud = {}) {
  const state = text(cloud?.state, 'unprovisioned');
  // Security boundary: this JSON is a potentially user-editable development
  // snapshot. Any `verification:provider-attested` flag, ID, timestamp or
  // receipt object can be forged in the same JSON. There is presently NO
  // configured provider reader, pinned attestation-signing public key or
  // trusted server verification channel. Therefore no serialized field can
  // qualify a cloud as ready/running. A future adapter must verify a signed,
  // source-SHA-bound provider receipt against a key pinned OUTSIDE this JSON
  // before introducing a separate trusted readiness input.
  if (CLAIMED_READY_STATES.has(state)) {
    return {tone: 'critical', label: 'Unverified provider claim', effectiveState: 'unverified'};
  }
  if (state === 'provisioning') return {tone: 'active', label: 'Provisioning', effectiveState: state};
  if (state === 'blocked' || state === 'failed') return {tone: 'critical', label: titleCase(state), effectiveState: state};
  if (state === 'stale') return {tone: 'warning', label: 'Evidence stale', effectiveState: state};
  return {tone: 'neutral', label: 'Not provisioned', effectiveState: 'unprovisioned'};
}

export function validDate(value) {
  return typeof value === 'string' && /\d{4}-\d\d-\d\dT/.test(value) && Number.isFinite(Date.parse(value));
}

export function safeCount(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : 0;
}

export function formatDate(value) {
  if (!validDate(value)) return 'No verified timestamp';
  return new Intl.DateTimeFormat('en-GB', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC'}).format(new Date(value)) + ' UTC';
}

export function snapshotAge(value, now = Date.now()) {
  if (!validDate(value)) return {label: 'Unverified timestamp', stale: true};
  const elapsed = now - Date.parse(value);
  if (elapsed < -60_000) return {label: 'Clock mismatch', stale: true};
  const minutes = Math.max(0, Math.floor(elapsed / 60_000));
  if (minutes < 5) return {label: 'Generated just now', stale: false};
  if (minutes < 60) return {label: `${minutes} min old`, stale: false};
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return {label: `${hours} h old`, stale: hours >= 2};
  return {label: `${Math.floor(hours / 24)} d old`, stale: true};
}

export function normalizeRegistry(value) {
  if (!value || value.schemaVersion !== 1 || !Array.isArray(value.pets)) {
    throw new Error('Unsupported or missing status registry. No readiness can be inferred.');
  }
  const seen = new Set();
  const pets = value.pets.map(item => {
    if (!item || !SLUG.test(item.slug) || seen.has(item.slug)) {
      throw new Error('Invalid or duplicate companion in status registry.');
    }
    seen.add(item.slug);
    const company = item.company || {};
    return {
      ...item,
      company: {
        slug: text(company.slug, item.slug.replace(/^junction-/, '')),
        name: text(company.name, item.slug),
        role: text(company.role, text(item.role, 'unknown')),
      },
      agent: item.agent || {},
      cloud: item.cloud || {},
      plugin: item.plugin || {},
      development: item.development || {},
      evaluation: item.evaluation || {},
      runtime: item.runtime || {},
    };
  });
  if (pets.length !== 34) throw new Error(`Expected 34 companions; received ${pets.length}. Status is incomplete.`);
  return {...value, pets, source: value.source || {}, summary: value.summary || {}};
}

export function filterPets(pets, {query = '', role = 'all', mode = 'all'} = {}) {
  const q = query.trim().toLocaleLowerCase();
  return pets.filter(pet => {
    const assessment = cloudAssessment(pet.cloud);
    if (role !== 'all' && pet.company.role !== role) return false;
    if (mode === 'needs-setup' && assessment.effectiveState !== 'unprovisioned') return false;
    if (mode === 'active' && !['running', 'provisioning'].includes(assessment.effectiveState)) return false;
    if (mode === 'ready' && assessment.effectiveState !== 'ready') return false;
    if (mode === 'issues' && !text(pet.blocker, '') && !['critical', 'warning'].includes(assessment.tone)) return false;
    return !q || [pet.company.name, pet.company.slug, pet.slug, pet.agent?.id, pet.nextAction]
      .some(value => text(value, '').toLocaleLowerCase().includes(q));
  });
}

export function petSourceUrl(pet, source) {
  const ref = source?.verification === 'local-git-only' ? 'main' : (sourceCommit(source) || 'main');
  return `https://github.com/${SOURCE_REPOSITORY}/tree/${ref}/pets/${encodeURIComponent(pet.company.slug)}`;
}

/** Advisory plugin status, deliberately NOT a hosted-install verification. */
export function pluginAssessment(plugin = {}, petSlug = '') {
  if (!plugin || typeof plugin !== 'object' || Array.isArray(plugin)) plugin = {};
  const exactSource = petSlug && plugin.desiredName === petSlug && plugin.sourcePath === `plugins/${petSlug}/plugin.json`;
  let source;
  if (plugin.presence === 'source-present' && exactSource) source = {tone: 'neutral', label: 'Source manifest reported present'};
  else if (plugin.presence === 'source-drift') source = {tone: 'warning', label: 'Source drift reported'};
  else if (plugin.presence === 'missing') source = {tone: 'critical', label: 'Source manifest missing'};
  else source = {tone: 'critical', label: 'Plugin source unverified'};

  let registration;
  if (plugin.installationState === 'not-registered') {
    registration = {tone: 'neutral', label: 'No registration recorded'};
  } else if (plugin.installationState === 'registered-source-matched-reported' && exactSource &&
    plugin.registrationBinding === 'source-matched-reported' &&
    /^[A-Za-z0-9_.:-]{5,200}$/.test(plugin.pluginId || '') &&
    /^[0-9a-f]{64}$/i.test(plugin.sourceBundleSha256 || '') && plugin.visibility === 'USER_PRIVATE') {
    // An exact source-bound self-report is NOT a provider readback.
    registration = {tone: 'warning', label: 'Private registration reported'};
  } else if (plugin.installationState === 'stale-registration' || plugin.registrationBinding === 'stale-source') {
    registration = {tone: 'warning', label: 'Registration evidence stale'};
  } else {
    registration = {tone: 'critical', label: 'Registration not verified'};
  }
  // No trusted provider reader or signed readback verifier is available. A
  // `provider-readback-recorded-not-rechecked` marker is still only a claim.
  const host = {tone: 'neutral', label: 'Host installation not independently verified'};
  return {source, registration, host};
}

/** Only exact canonical plugin-page links, with no query, fragment or redirect. */
export function safePluginPageUrl(plugin = {}) {
  if (!plugin || typeof plugin !== 'object' || Array.isArray(plugin)) return null;
  const id = plugin.pluginId;
  const raw = plugin.pluginUrl;
  if (typeof id !== 'string' || typeof raw !== 'string' || !/^plugins_[A-Za-z0-9_-]{5,200}$/.test(id)) return null;
  try {
    const u = new URL(raw);
    if (u.href !== `https://chatgpt.com/plugins/${id}` || u.search || u.hash || u.username || u.password || u.port) return null;
    return u.href;
  } catch { return null; }
}

function titleCase(value) { return value.charAt(0).toUpperCase() + value.slice(1); }
