const names = {knowledge_os: 'Knowledge OS', graphify: 'Graphify', dam: 'DAM', repo_control: 'Repo Control'};
const $ = id => document.getElementById(id);
let module = 'knowledge_os', context = null, generation = 0, pending = null;
const api = path => new URL(`./api/${path}`, document.baseURI);
const short = value => value.length > 24 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
function notice(message, ready = false) {$('connection').textContent = message; $('connection').dataset.state = ready ? 'ready' : 'unavailable';}
function element(tag, text, className) {const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node;}
function empty(message) {$('results').replaceChildren(element('p', message, 'empty')); $('result-count').textContent = 'No snapshot selected';}
function sourceHref(ref) {
  try {
    const url = new URL(ref);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.port) return null;
    if (url.hostname === 'github.com' && /^\/[^/]+\/[^/]+\/(?:commit\/[a-f0-9]{40}|blob\/[a-f0-9]{40}\/.+)/.test(url.pathname)) return url.href;
    if (url.hostname === 'chatgpt.com' && /^\/space\/page_[a-f0-9]{32}$/.test(url.pathname) && !url.hash) return url.href;
  } catch { /* A non-web reference remains visible text, never an executable link. */ }
  return null;
}
function snapshots() {
  const select = $('snapshot'); select.replaceChildren(new Option('Choose an exact source snapshot', ''));
  const available = context?.datasets?.filter(item => item.module === module) ?? [];
  for (const item of available) select.add(new Option(`${new Date(item.observedAt).toLocaleString()} · ${item.digest.slice(0, 12)} · ${item.coverage === 'partial' ? 'partial coverage' : 'declared source'}`, item.digest));
  select.disabled = available.length === 0; $('search').disabled = true;
  if (!available.length) select.replaceChildren(new Option(context ? 'No declared snapshot for this module' : 'Private connection required', ''));
}
function observations() {
  const target = $('observations'); target.replaceChildren();
  if (!context) {target.textContent = 'No private project observation has been loaded.'; return;}
  target.append(element('p', context.workIds.length ? `Linked Work IDs: ${context.workIds.join(', ')}` : 'No Work IDs declared for this project.'));
  for (const source of context.sources) {
    const row = element('div', undefined, 'observation');
    row.append(element('strong', source.sourceKey), element('div', source.stale ? `Stale · ${source.staleReason ?? 'source refresh needed'}` : 'Source observation recorded'));
    row.append(element('div', source.observedAt ? `${new Date(source.observedAt).toLocaleString()} · ${short(source.sourceRevision ?? '')}` : 'No current successful source observation.'));
    target.append(row);
  }
}
async function request(url, options = {}) {
  const response = await fetch(url, {...options, credentials: 'same-origin', cache: 'no-store', signal: pending.signal});
  let body; try {body = await response.json();} catch {body = null;}
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error('Private access required. Open this app through its authenticated owner host.');
    if (response.status === 404) throw new Error('Private reader is not configured on this catalog host.');
    throw new Error('Source reader unavailable. Earlier results, if shown, have not been refreshed.');
  }
  return body;
}
async function loadContext() {
  pending?.abort(); pending = new AbortController(); const current = ++generation;
  const projectId = $('project').value; context = null; snapshots(); observations();
  empty('Connect the private reader, then select a source snapshot.'); notice('Reading private source manifest…');
  try {
    const url = api('context'); url.searchParams.set('projectId', projectId);
    const value = await request(url);
    if (generation !== current) return;
    if (value?.schema !== 'knowledge-app.context/v1' || value.projectId !== projectId || !Array.isArray(value.datasets) || !Array.isArray(value.sources) || !Array.isArray(value.workIds)) throw new Error('Source reader returned a mismatched project.');
    context = value; snapshots(); observations();
    notice('Private source manifest loaded. Choose a snapshot; its receipt does not establish live service health.', true);
  } catch (error) {if (generation === current && error.name !== 'AbortError') notice(error.message);}
}
$('project').addEventListener('change', () => void loadContext());
$('refresh').addEventListener('click', () => void loadContext());
for (const button of document.querySelectorAll('[data-module]')) button.addEventListener('click', () => {
  pending?.abort(); ++generation; module = button.dataset.module;
  for (const other of document.querySelectorAll('[data-module]')) other.setAttribute('aria-pressed', String(other === button));
  $('module-title').textContent = names[module]; snapshots(); empty('Choose a declared snapshot for this module.');
  if (!context) void loadContext();
});
$('snapshot').addEventListener('change', () => {pending?.abort(); ++generation; $('search').disabled = !$('snapshot').value; empty('Search the selected source snapshot.');});
$('search-form').addEventListener('submit', async event => {
  event.preventDefault();
  const selector = {projectId: $('project').value, module, digest: $('snapshot').value, query: $('query').value.trim(), limit: 20};
  if (!selector.digest || !selector.query) return;
  pending?.abort(); pending = new AbortController(); const current = ++generation;
  notice('Searching the selected source snapshot…'); $('search').disabled = true;
  try {
    const value = await request(api('search'), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(selector)});
    if (generation !== current) return;
    if (value?.projectId !== selector.projectId || value.module !== selector.module || value.digest !== selector.digest || !Array.isArray(value.items)) throw new Error('Source reader returned a mismatched snapshot.');
    $('results').replaceChildren(); $('result-count').textContent = `${value.total} matches${value.truncated ? ' · first 20 shown' : ''}`;
    if (!value.items.length) $('results').append(element('p', 'No metadata matches in this exact snapshot. Other snapshots were not searched.', 'empty'));
    for (const item of value.items) {
      const row = element('article', undefined, 'result');
      row.append(element('h3', item.title), element('p', item.summary));
      const meta = element('div', undefined, 'provenance');
      meta.append(element('small', `Source ${short(item.sourceRevision)}`), element('small', new Date(item.observedAt).toLocaleString()), element('small', `Snapshot ${selector.digest.slice(0, 12)}`));
      const href = sourceHref(item.sourceRef);
      if (href) {const link = element('a', 'Open source ↗'); link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; meta.append(link);}
      else meta.append(element('small', item.sourceRef));
      row.append(meta); $('results').append(row);
    }
    notice(`Selected snapshot searched · ${value.coverage === 'partial' ? 'partial source coverage' : 'complete for the declared source'}. Results are source-attributed metadata.`, true);
  } catch (error) {if (generation === current && error.name !== 'AbortError') notice(error.message);}
  finally {if (generation === current) $('search').disabled = !$('snapshot').value;}
});
void loadContext();
