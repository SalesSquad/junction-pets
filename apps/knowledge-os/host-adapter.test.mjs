import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createKnowledgeAppHandler} from './host-adapter.mjs';

const projectId = 'knowledge-os', digest = 'a'.repeat(64), sourceRevision = 'b'.repeat(40);
const descriptor = {projectId, module: 'graphify', digest, observedAt: '2026-11-01T00:00:00Z', coverage: 'partial'};
const project = {project: {projectId, observedAt: descriptor.observedAt, works: [{id: 'work_existing'}]}, sources: [{sourceKey: 'graphify-index', stale: true, staleReason: 'latest_attempt_failed', lastAttempt: {attemptedAt: '2026-11-02T00:00:00Z'}, lastSuccess: {sourceRevision, observedAt: descriptor.observedAt}}]};
const search = {projectId, module: 'graphify', digest, query: 'routing', limit: 20};
const result = {projectId, module: 'graphify', digest, coverage: 'partial', total: 1, truncated: false, items: [{id: 'record-1', title: 'Source routing', summary: 'Source-attributed metadata.', sourceRef: `https://github.com/Example/project/commit/${sourceRevision}`, sourceRevision, observedAt: descriptor.observedAt}]};
const calls = [];
function dependencies(change = {}) {
  return {
    async authorize() {return {actorId: 'owner', audience: 'owner-private'};},
    async readProject(scope) {calls.push(['project', scope]); return project;},
    async listDatasets(scope) {calls.push(['manifest', scope]); return [descriptor];},
    async searchDataset(scope) {calls.push(['search', scope]); return result;},
    ...change,
  };
}
const contextRequest = (query = '?projectId=knowledge-os') => new Request(`https://app.example/apps/knowledge-os/api/context${query}`);
const searchRequest = (input = search, origin = 'https://app.example') => new Request('https://app.example/apps/knowledge-os/api/search', {method: 'POST', headers: {'Content-Type': 'application/json', Origin: origin}, body: JSON.stringify(input)});

test('anonymous/public host and request-supplied identity cannot unlock private readers', async () => {
  const request = new Request(contextRequest(), {headers: {'oai-authenticated-user-id': 'owner', 'x-owner-private': 'true'}});
  assert.equal((await createKnowledgeAppHandler()(request)).status, 401);
  assert.equal((await createKnowledgeAppHandler(dependencies({authorize: async () => ({actorId: 'owner', audience: 'public'})}))(request)).status, 401);
  assert.equal((await createKnowledgeAppHandler({authorize: dependencies().authorize})(request)).status, 503);
});

test('authenticated context preserves original source freshness and exact snapshot selectors', async () => {
  calls.length = 0;
  const response = await createKnowledgeAppHandler(dependencies())(contextRequest());
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'private, no-store');
  const body = await response.json();
  assert.equal(body.schema, 'knowledge-app.context/v1');
  assert.deepEqual(body.datasets, [descriptor]);
  assert.equal(body.sources[0].stale, true);
  assert.equal(body.sources[0].observedAt, descriptor.observedAt);
  assert.deepEqual(body.workIds, ['work_existing']);
  assert.equal(calls.every(([, scope]) => scope.actorId === 'owner' && scope.projectId === projectId), true);
});

test('search executes only the declared project/module/digest and preserves source evidence', async () => {
  calls.length = 0;
  const response = await createKnowledgeAppHandler(dependencies())(searchRequest());
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.digest, digest);
  assert.equal(body.items[0].sourceRevision, sourceRevision);
  assert.equal(body.coverage, 'partial');
  assert.equal(calls.find(([name]) => name === 'search')[1].actorId, 'owner');
  for (const input of [{...search, digest: 'c'.repeat(64)}, {...search, module: 'dam'}, {...search, projectId: 'other'}]) {
    assert.equal((await createKnowledgeAppHandler(dependencies())(searchRequest(input))).status, input.projectId === 'other' ? 503 : 409);
  }
});

test('search rejects absent implicit version, foreign origin, extra actor fields and unbounded input', async () => {
  for (const input of [{...search, digest: undefined}, {...search, actorId: 'other'}, {...search, limit: 21}, {...search, query: ' '}, {...search, projectId: 1}, {...search, query: 'x'.repeat(9000)}]) {
    assert.equal((await createKnowledgeAppHandler(dependencies())(searchRequest(input))).status, 400);
  }
  assert.equal((await createKnowledgeAppHandler(dependencies())(searchRequest(search, 'https://foreign.example'))).status, 403);
  assert.equal((await createKnowledgeAppHandler(dependencies())(contextRequest('?projectId=knowledge-os&actorId=other'))).status, 400);
});

test('mismatched or unsafe upstream data is unavailable, never substituted into a different source', async () => {
  for (const value of [{...result, projectId: 'other'}, {...result, digest: 'c'.repeat(64)}, {...result, module: 'dam'}, {...result, items: [{...result.items[0], summary: '/Users/private/document'}]}, {...result, items: [{...result.items[0], summary: 'Bearer ' + 'x'.repeat(30)}]}]) {
    assert.equal((await createKnowledgeAppHandler(dependencies({searchDataset: async () => value}))(searchRequest())).status, 503);
  }
  const response = await createKnowledgeAppHandler(dependencies({readProject: async () => {throw new Error('D1 secret SQL path');}}))(contextRequest());
  assert.equal(response.status, 503);
  assert.doesNotMatch(await response.text(), /secret|SQL/);
});

test('public package carries no private host configuration and catalog copies only public assets', async () => {
  const [html, app, producer, navigation] = await Promise.all([
    readFile(new URL('./public/index.html', import.meta.url), 'utf8'),
    readFile(new URL('./public/app.mjs', import.meta.url), 'utf8'),
    readFile(new URL('../../scripts/build-catalog.mjs', import.meta.url), 'utf8'),
    readFile(new URL('../catalog/src/App.tsx', import.meta.url), 'utf8'),
  ]);
  assert.match(html, /Source snapshot/);
  assert.match(app, /digest: \$\('snapshot'\).value/);
  assert.doesNotMatch(html + app, /ervamaamikael|siwc_bypass|OAI-Sites-Authorization|Bearer\s|page_[a-f0-9]{32}|\/Users\//);
  assert.match(producer, /apps\/knowledge-os\/public/);
  assert.doesNotMatch(producer, /cp\([^;]*host-adapter/);
  assert.match(navigation, /publicAsset\('apps\/knowledge-os\/index.html'\)/);
});
