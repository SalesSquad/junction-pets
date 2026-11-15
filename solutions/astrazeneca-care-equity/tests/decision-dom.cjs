// Optional DOM integration check. This is not a browser or layout qualification.
// npm install --prefix /tmp/sama-dom --ignore-scripts jsdom@26.1.0 esbuild@0.25.11
// SAMA_TEST_MODULES=/tmp/sama-dom/node_modules node tests/decision-dom.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const dependencies = createRequire(path.join(process.env.SAMA_TEST_MODULES || root, 'package.json'));
const { JSDOM, VirtualConsole } = dependencies('jsdom');
const esbuild = dependencies('esbuild');

async function run() {
  const result = await esbuild.build({
    entryPoints: [path.join(root, 'web/app.mjs')], bundle: true, write: false,
    platform: 'browser', format: 'iife',
    plugins: [{ name: 'same-origin-source', setup(build) {
      build.onResolve({ filter: /^\/src\// }, args => ({ path: path.join(root, args.path.slice(1)) }));
    } }],
  });
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', e => errors.push(String(e)));
  virtualConsole.on('error', e => errors.push(String(e)));
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'web/index.html'), 'utf8'), {
    url: 'https://sama.test/', runScripts: 'outside-only', virtualConsole,
  });
  const w = dom.window;
  w.structuredClone = structuredClone;
  w.Blob = Blob;
  w.print = () => {};
  const blobs = new Map();
  w.URL.createObjectURL = blob => { const id = 'blob:test-' + blobs.size; blobs.set(id, blob); return id; };
  w.URL.revokeObjectURL = id => blobs.delete(id);
  w.HTMLAnchorElement.prototype.click = function () {
    assert.match(this.download, /^sama-HVA\d+-brief.json$/);
  };
  const fetched = [];
  // Same routes as web/serve.mjs: app.json and the map from web/data, three files from the repository's data/
  // folder (ROOT_DATA), and no /api/scribe route (static hosting), so the scribe demo reads its stored outputs.
  const ROOT_DATA = ['/data/planner/plans-v1.json', '/data/scribe/demo/demo-notes.json', '/data/scribe/demo/demo-outputs.json'];
  w.fetch = async url => {
    fetched.push(url);
    if (url === '/api/scribe') return { ok: false, status: 404, json: async () => null };
    assert.ok(['/data/app.json', '/data/counties.geo.json', ...ROOT_DATA].includes(url), 'Unexpected network use: ' + url);
    const file = ROOT_DATA.includes(url) ? path.join(root, url.slice(1)) : path.join(root, 'web', url);
    return { ok: true, json: async () => JSON.parse(fs.readFileSync(file, 'utf8')) };
  };
  w.eval(result.outputFiles[0].text);
  for (let attempt = 0; attempt < 200 && !w.document.querySelector('#loading').hidden; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 10));
    if (errors.length) throw new Error(errors.join('; '));
  }
  const document = w.document, byId = id => document.getElementById(id);
  assert.equal(byId('loading').hidden, true, byId('loading').textContent);
  assert.equal(byId('decision-region').options.length, 23);
  // The integrated page (#275) has no forecast section; withholding is carried by the export (forecastStatus below).
  assert.equal(byId('forecast'), null);
  let exports = 0;
  for (const region of ['HVA06', 'HVA90', 'HVA91', 'HVA21']) {
    byId('decision-region').value = region;
    byId('decision-region').dispatchEvent(new w.Event('change', { bubbles: true }));
    assert.equal(byId('region').value, region);
    assert.equal(document.querySelector('#decision-content .decision-card').dataset.decisionRegion, region);
    assert.equal(document.querySelector('#brief-content .decision-card').dataset.decisionRegion, region);
    assert.match(byId('decision-content').textContent, /47.7%/);
    assert.match(byId('decision-content').textContent, /7,097 \/ 14,873/);
    assert.match(byId('decision-content').textContent, /Missing registry information does not mean staging was not performed/);
    byId('download').click();
    const blob = [...blobs.values()].at(-1);
    const brief = JSON.parse(await blob.text());
    assert.equal(brief.decision.regionId, region);
    assert.equal(brief.humanApproval, 'REQUIRED_NOT_GRANTED');
    assert.equal(brief.decision.humanApproval, 'REQUIRED_NOT_GRANTED');
    assert.equal(brief.decision.nationalContext[0].scope.regionId, null);
    assert.equal(brief.forecastStatus.status, 'WITHHELD');
    exports++;
  }
  // Existing county controls must update the short route as well.
  byId('region').value = 'HVA01';
  byId('region').dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.equal(byId('decision-region').value, 'HVA01');
  assert.equal(document.querySelector('#decision-content .decision-card').dataset.decisionRegion, 'HVA01');
  assert.equal(document.querySelectorAll('.forecast-charts').length, 0);
  assert.match(byId('future-context').textContent, /not implemented/);
  for (const label of document.querySelectorAll('label[for]')) assert.ok(byId(label.htmlFor), label.htmlFor);
  const ids = [...document.querySelectorAll('[id]')].map(node => node.id);
  assert.equal(new Set(ids).size, ids.length, 'Duplicate DOM ids');
  assert.deepEqual(errors, []);
  assert.deepEqual([...new Set(fetched)].filter(u => u !== '/api/scribe').sort(), ['/data/app.json', '/data/counties.geo.json', ...ROOT_DATA].sort());
  dom.window.close();
  console.log(JSON.stringify({
    status: 'PASS', environment: 'jsdom 26.1.0 + esbuild 0.25.11; DOM emulation',
    regionsAvailable: 23, exercisedRegionExports: exports,
    verified: ['county-control synchronisation', 'source scope and limitation text', 'decision JSON export', 'forecast withholding', 'future capability label', 'unique ids and form labels'],
    notVerified: ['real browser rendering', 'responsive layout', 'dark-mode contrast', 'screen reader', 'print layout'],
  }, null, 2));
}
run().catch(error => { console.error(error); process.exitCode = 1; });
