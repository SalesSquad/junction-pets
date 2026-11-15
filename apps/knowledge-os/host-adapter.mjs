/** Owner-private host adapter. Dependencies are server-owned functions, never browser configuration. */
export const KNOWLEDGE_MODULES = Object.freeze(['knowledge_os', 'graphify', 'dam', 'repo_control']);
const PROJECT = /^[a-z0-9][a-z0-9._-]{0,127}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const stamp = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value)) && Date.parse(value) <= Date.now() + 300_000;
const unsafe = /[\u0000-\u001f\u007f]|(?:^|[\s"'(])(?:\/(?:Users|home|private|tmp|Volumes|Library|var|root)\/|(?:\.{1,2}|~)[/\\]|[A-Za-z]:\\|file:)|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{16,}|Bearer\s+[A-Za-z0-9._~-]{16,})|-----BEGIN [A-Z ]*PRIVATE KEY-----/i;
const safeText = (value, limit) => typeof value === 'string' && value.length <= limit && !unsafe.test(value);
const response = (value, status = 200) => Response.json(value, {status, headers: {'Cache-Control': 'private, no-store'}});

function descriptors(value, projectId) {
  if (!Array.isArray(value) || value.length > 100) throw new Error('Invalid dataset manifest');
  const seen = new Set();
  return value.map(item => {
    if (!object(item) || item.projectId !== projectId || !KNOWLEDGE_MODULES.includes(item.module) || !DIGEST.test(item.digest) ||
        !stamp(item.observedAt) || !['partial', 'complete_for_declared_source'].includes(item.coverage)) throw new Error('Invalid dataset manifest');
    const key = `${item.module}:${item.digest}`; if (seen.has(key)) throw new Error('Duplicate dataset manifest'); seen.add(key);
    return {projectId, module: item.module, digest: item.digest, observedAt: item.observedAt, coverage: item.coverage};
  });
}
function projectProjection(value, projectId) {
  if (!object(value) || !object(value.project) || value.project.projectId !== projectId || !Array.isArray(value.sources) || value.sources.length > 100) throw new Error('Invalid project projection');
  const works = value.project.works;
  if (!Array.isArray(works) || works.length > 100 || works.some(work => !object(work) || !safeText(work.id, 160))) throw new Error('Invalid work projection');
  return {
    projectId, observedAt: stamp(value.project.observedAt) ? value.project.observedAt : null,
    workIds: works.map(work => work.id),
    sources: value.sources.map(source => {
      if (!object(source) || !safeText(source.sourceKey, 160) || typeof source.stale !== 'boolean') throw new Error('Invalid source projection');
      const success = source.lastSuccess;
      if (success !== null && (!object(success) || !safeText(success.sourceRevision, 160) || !stamp(success.observedAt))) throw new Error('Invalid source projection');
      return {
        sourceKey: source.sourceKey, stale: source.stale || success === null,
        staleReason: safeText(source.staleReason, 160) ? source.staleReason : success === null ? 'no_current_success' : null,
        observedAt: success?.observedAt ?? null, sourceRevision: success?.sourceRevision ?? null,
        lastAttemptAt: stamp(source.lastAttempt?.attemptedAt) ? source.lastAttempt.attemptedAt : null,
      };
    }),
  };
}
function searchProjection(value, selector) {
  if (!object(value) || value.projectId !== selector.projectId || value.module !== selector.module || value.digest !== selector.digest ||
      !Array.isArray(value.items) || value.items.length > selector.limit || !Number.isInteger(value.total) || value.total < value.items.length ||
      typeof value.truncated !== 'boolean' || !['partial', 'complete_for_declared_source'].includes(value.coverage)) throw new Error('Mismatched search projection');
  const items = value.items.map(item => {
    if (!object(item) || !safeText(item.id, 160) || !safeText(item.title, 180) || !safeText(item.summary, 600) ||
        !safeText(item.sourceRef, 1200) || !safeText(item.sourceRevision, 160) || !stamp(item.observedAt)) throw new Error('Invalid search record');
    return {id: item.id, title: item.title, summary: item.summary, sourceRef: item.sourceRef, sourceRevision: item.sourceRevision, observedAt: item.observedAt};
  });
  return {projectId: value.projectId, module: value.module, digest: value.digest, coverage: value.coverage, items, total: value.total, truncated: value.truncated, trust: 'Source-attributed metadata; not runtime or access authority.'};
}
async function inputJson(request) {
  if (request.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() !== 'application/json') throw new Error('Invalid input');
  const reader = request.body?.getReader();
  if (!reader) throw new Error('Invalid input');
  const chunks = []; let bytes = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read(); if (done) break;
      bytes += value.byteLength;
      if (bytes > 8192) {await reader.cancel(); throw new Error('Invalid input');}
      chunks.push(value);
    }
  } finally {reader.releaseLock();}
  const buffer = new Uint8Array(bytes); let at = 0;
  for (const chunk of chunks) {buffer.set(chunk, at); at += chunk.byteLength;}
  return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(buffer));
}

/** @param {import('./host-adapter.mjs').HostDependencies} dependencies */
export function createKnowledgeAppHandler(dependencies = {}) {
  return async function handle(request) {
    let session;
    try {session = await dependencies.authorize?.(request);} catch {return response({error: 'Private host access unavailable.'}, 503);}
    if (!session || session.audience !== 'owner-private' || !safeText(session.actorId, 300) || !session.actorId.trim()) return response({error: 'Open this app through its authenticated private host.'}, 401);
    if (typeof dependencies.readProject !== 'function' || typeof dependencies.listDatasets !== 'function' || typeof dependencies.searchDataset !== 'function') return response({error: 'Private readers are not configured.'}, 503);
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname.endsWith('/api/context')) {
      const origin = request.headers.get('origin');
      const fetchSite = request.headers.get('sec-fetch-site')?.toLowerCase();
      if ((origin !== null && origin !== url.origin) || fetchSite === 'cross-site' || fetchSite === 'same-site') return response({error: 'Cross-origin context request denied.'}, 403);
      const projectId = url.searchParams.get('projectId');
      if (!PROJECT.test(projectId ?? '') || [...url.searchParams.keys()].length !== 1) return response({error: 'Choose a valid project.'}, 400);
      try {
        const scope = {actorId: session.actorId, projectId};
        const [project, datasets] = await Promise.all([dependencies.readProject(scope), dependencies.listDatasets(scope)]);
        return response({schema: 'knowledge-app.context/v1', ...projectProjection(project, projectId), datasets: descriptors(datasets, projectId)});
      } catch {return response({error: 'Private source projection unavailable.'}, 503);}
    }
    if (request.method === 'POST' && url.pathname.endsWith('/api/search')) {
      if (request.headers.get('origin') !== url.origin) return response({error: 'Same-origin request required.'}, 403);
      let selector;
      try {
        selector = await inputJson(request);
        if (!object(selector) || Object.keys(selector).sort().join(',') !== 'digest,limit,module,projectId,query' || typeof selector.projectId !== 'string' || !PROJECT.test(selector.projectId) ||
            !KNOWLEDGE_MODULES.includes(selector.module) || !DIGEST.test(selector.digest ?? '') || !safeText(selector.query, 120) || !selector.query.trim() ||
            !Number.isInteger(selector.limit) || selector.limit < 1 || selector.limit > 20) throw new Error('Invalid input');
      } catch {return response({error: 'Choose a project, module, exact snapshot and bounded query.'}, 400);}
      try {
        const scope = {actorId: session.actorId, projectId: selector.projectId};
        const manifest = descriptors(await dependencies.listDatasets(scope), selector.projectId);
        if (!manifest.some(item => item.module === selector.module && item.digest === selector.digest)) return response({error: 'Snapshot is not declared for this project and module.'}, 409);
        const result = await dependencies.searchDataset({...selector, actorId: session.actorId});
        return response(searchProjection(result, selector));
      } catch {return response({error: 'Snapshot reader unavailable; previous results are not refreshed.'}, 503);}
    }
    return response({error: 'Route not found.'}, 404);
  };
}
