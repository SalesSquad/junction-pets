import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { appendFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { performance } from 'node:perf_hooks';

const mode = process.argv[2];
assert(['native', 'cache'].includes(mode), 'Select native or cache');
assert(process.env.SOURCE_DIR, 'SOURCE_DIR is required');
const source = resolve(process.env.SOURCE_DIR);
const expected = process.env.EXPECTED_SOURCE_SHA;
assert.match(expected || '', /^[a-f0-9]{40}$/);
const run = (program, args, options = {}) => execFileSync(program, args, {
  cwd: source, encoding: 'utf8', timeout: 120000, maxBuffer: 20 * 1024 * 1024, ...options,
});
assert.equal(run('git', ['rev-parse', 'HEAD']).trim(), expected);
assert.equal(run('git', ['status', '--porcelain', '--untracked-files=no']).trim(), '', 'Tracked source changed');
assert.equal(process.platform, 'linux');
assert.equal(process.versions.node.split('.')[0], '22', 'Both experiments deliberately use Node 22');
const sha = data => createHash('sha256').update(data).digest('hex');
const canonical = value => value === null || typeof value !== 'object' ? value
  : Array.isArray(value) ? value.map(canonical)
    : Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
const digest = value => sha(JSON.stringify(canonical(value)));
const result = { schemaVersion: 1, experiment: mode, source_sha: expected,
  arch: process.arch, kernel: run('uname', ['-sm']).trim(), node: process.version,
  synthetic: true, provider_integration: false, observed_at: new Date().toISOString() };

if (mode === 'native') {
  assert.equal(process.arch, process.env.EXPECTED_ARCH);
  const base = 'solutions/mariadb-wikipedia-time';
  const fixture = JSON.parse(readFileSync(resolve(source, base, 'fixtures/synthetic.json'), 'utf8'));
  const cases = [
    ['before-first', 'demo:harbor-energy', '2025-01-09T23:59:59Z', null],
    ['exact-first', 'demo:harbor-energy', '2025-01-10T00:00:00Z', '101'],
    ['before-change', 'demo:harbor-energy', '2025-01-10T23:59:59.999Z', '101'],
    ['exact-change', 'demo:harbor-energy', '2025-01-11T00:00:00Z', '102'],
    ['before-revert', 'demo:harbor-energy', '2025-01-11T02:59:59.999Z', '102'],
    ['exact-revert', 'demo:harbor-energy', '2025-01-11T03:00:00Z', '103'],
    ['other-page', 'demo:civic-debate', '2025-02-01T00:00:00Z', '201'],
    ['unknown-page', 'demo:absent', '2025-02-01T00:00:00Z', null],
  ];
  const outputs = [];
  for (const [name, page, at, revision] of cases) {
    const value = JSON.parse(run(process.execPath, [base + '/src/cli.mjs', '--page', page, '--at', at]));
    assert.equal(value.provider, 'NO_MARIADB_CONNECTION');
    assert.equal(value.verified_live_source, false);
    assert.equal(value.snapshot.status, revision ? 'FOUND' : 'NO_EVIDENCE', name);
    if (revision) {
      const row = fixture.revisions.find(item => item.revision_id === revision);
      assert.equal(value.snapshot.revision_id, revision, name);
      assert.equal(value.snapshot.text, row.body, name);
      assert.equal(value.snapshot.sha256, sha(row.body), name);
    }
    outputs.push({ name, value });
  }
  const invalid = spawnSync(process.execPath, [base + '/src/cli.mjs', '--page', 'demo:harbor-energy', '--at', '2025-02-30T00:00:00Z'], {
    cwd: source, encoding: 'utf8', timeout: 10000,
  });
  assert.equal(invalid.status, 2);
  assert.equal(JSON.parse(invalid.stderr).reason, 'INVALID_UTC');
  outputs.push({ name: 'invalid-calendar-date', value: JSON.parse(invalid.stderr) });
  result.cases = outputs.length;
  result.output_sha256 = digest(outputs);
  result.fixture_sha256 = sha(readFileSync(resolve(source, base, 'fixtures/synthetic.json')));
  result.results = outputs;
} else {
  const cacheMode = process.env.CACHE_MODE;
  assert(['cold', 'warm'].includes(cacheMode));
  const cache = resolve(process.env.CRACI_NPM_CACHE || '');
  assert(process.env.CRACI_NPM_CACHE, 'Explicit isolated npm cache required');
  const hit = process.env.CACHE_HIT === 'true';
  assert.equal(hit, cacheMode === 'warm', 'Cache hit must match the declared experiment');
  mkdirSync(cache, { recursive: true });
  if (cacheMode === 'cold') assert.equal(readdirSync(cache).length, 0, 'Cold cache must actually be empty');
  const lockBefore = sha(readFileSync(resolve(source, 'package-lock.json')));
  const start = performance.now();
  run('npm', ['ci', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', cache,
    ...(cacheMode === 'warm' ? ['--offline'] : [])], { timeout: 300000, stdio: ['ignore', 'inherit', 'inherit'] });
  const installMs = Math.round(performance.now() - start);
  assert.equal(sha(readFileSync(resolve(source, 'package-lock.json'))), lockBefore, 'Install changed lockfile');
  const tree = JSON.parse(run('npm', ['ls', '--all', '--json']));
  const packages = [];
  function visit(node, path = '') {
    assert(!node.missing && !node.invalid, 'Invalid installed dependency: ' + path);
    if (path) packages.push({ path, version: node.version || null });
    for (const [name, child] of Object.entries(node.dependencies || {}).sort(([a], [b]) => a.localeCompare(b))) {
      visit(child, path ? path + '>' + name : name);
    }
  }
  visit(tree);
  assert(packages.length > 0);
  const graphSha = digest(packages);
  if (cacheMode === 'warm') {
    assert.equal(lockBefore, process.env.EXPECTED_CACHE_LOCK_SHA, 'Different lockfile');
    assert.equal(graphSha, process.env.EXPECTED_CACHE_GRAPH_SHA, 'Cold/warm installed graph differs');
  }
  run('npm', ['run', 'validate'], { stdio: ['ignore', 'inherit', 'inherit'] });
  Object.assign(result, { mode: cacheMode, cache_hit: hit, cache_key: process.env.CACHE_KEY,
    offline_install: cacheMode === 'warm', install_ms: installMs, lock_sha256: lockBefore,
    package_graph_sha256: graphSha, installed_graph_entries: packages.length,
    source_validation: 'passed', packages });
  if (process.env.GITHUB_OUTPUT) appendFileSync(process.env.GITHUB_OUTPUT,
    `graph_sha=${graphSha}\nlock_sha=${lockBefore}\ninstall_ms=${installMs}\n`);
}
result.status = 'passed';
if (process.env.CRACI_RESULT_FILE) writeFileSync(process.env.CRACI_RESULT_FILE, JSON.stringify(result, null, 2) + '\n');
console.log('CRACI_EXPERIMENT_RESULT=' + JSON.stringify(result));
