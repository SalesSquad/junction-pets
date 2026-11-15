import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, mkdir, copyFile, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {exportApps} from './export.mjs';

test('export maps each selected pet to a real entry and its browser assets', async () => {
  const temp = await mkdtemp(join(tmpdir(), 'junction-app-export-'));
  const output = join(temp, 'bundle');
  try {
    const apps = await exportApps(output);
    const catalog = JSON.parse(await readFile(join(output, 'catalog.json'), 'utf8'));
    assert.deepEqual(catalog.apps, apps);
    assert.deepEqual(new Set(apps.map(app => app.petSlug)), new Set(['junction-arduino','junction-intel','junction-city-of-espoo','junction-rokoko','junction-bahn-express','junction-s-pankki','junction-meta','junction-aalto-university','junction-hostinger','junction-cala','junction-context-dev','junction-stoa','junction-mariadb','junction-astrazeneca','junction-valio-aimo']));
    assert.equal(apps.find(app=>app.path==='/apps/banker/index.html').petSlug,'junction-s-pankki');
    assert.equal(apps.filter(app=>app.petSlug==='junction-intel').length,2);
    assert.equal(apps.find(app=>app.petSlug==='junction-context-dev').path,'/apps/supplypulse/index.html');

    assert.equal(apps.filter(app=>app.petSlug==='junction-valio-aimo').length,2);
    const aimoApp=apps.find(app=>app.path.includes('/aimo-trade/'));
    assert.equal(aimoApp.path,'/apps/aimo-trade/browser/dist/index.html');
    for(const asset of ['index.html','app.js','app.css','export.json','NOTICE.txt'])assert.ok((await readFile(join(output,'apps/aimo-trade/browser/dist',asset))).length>0);



    for (const app of apps) assert.match(await readFile(join(output, app.path), 'utf8'), /<html/i);
    assert.match(await readFile(join(output,'apps/spread-director/index.html'), 'utf8'), /Use synthetic example/);
    const example = JSON.parse(await readFile(join(output,'apps/spread-director/demo.json'), 'utf8'));
    assert.equal(example.mode, 'SYNTHETIC_OFFLINE');
    assert.match(await readFile(join(output,'apps/proofmatch/app.mjs'), 'utf8'), /cached in this browser/);
    const lumo = await readFile(join(output,'apps/lumo/web/index.html'), 'utf8');
    assert.match(lumo, /href="\.\/styles\.css"/); assert.match(lumo, /src="\.\/app\.mjs"/); assert.doesNotMatch(lumo, /(?:href|src)="\/web\//);
    assert.match(await readFile(join(output,'apps/lumo/src/coach.mjs'), 'utf8'), /export /);
    assert.match(await readFile(join(output,'apps/banker/index.html'), 'utf8'), /oikeaa maksua ei lähetetä/);
    assert.match(await readFile(join(output,'apps/banker/app.mjs'), 'utf8'), /Maksua ei lähetetty/);
    for (const file of ['app.mjs','guide/index.html','guide/guide-app.mjs']) assert.ok((await readFile(join(output,'apps/meta-lens',file),'utf8')).length > 0);
    const recovery=await readFile(join(output,'apps/recovery-compass/web/index.html'),'utf8');
    assert.match(recovery,/connect-src 'none'/); assert.match(recovery,/href="\.\/styles\.css"/);
    const traffic=await readFile(join(output,'apps/traffic-forensics/public/traffic/index.html'),'utf8');
    assert.match(traffic,/connect-src 'none'/); assert.match(traffic,/src="\.\/app\.mjs"/);
    const stoa=join(output,'apps/stoa-atlas');
    const stoaHtml=await readFile(join(stoa,'public/index.html'),'utf8');
    assert.match(stoaHtml,/connect-src 'none'/);
    assert.match(stoaHtml,/IFC import, source comparison and review export require the local Stoa server/);
    assert.match(stoaHtml,/<details hidden id="revision-tools"/);
    assert.match(stoaHtml,/<details hidden class="review-tools"/);
    assert.match(stoaHtml,/accept="\.dxf"/);
    const stoaClient=await readFile(join(stoa,'public/app.js'),'utf8');
    assert.doesNotMatch(stoaClient,/from '\.\/workspace\.js'/);
    assert.match(stoaClient,/Only ASCII DXF is available in this browser demo/);
    const {createStoaLocalApi}=await import(pathToFileURL(join(stoa,'adapter/stoa-local-api.mjs')).href);
    const {makeDemo}=await import('../../solutions/stoa-blueprint-studio/src/demo.mjs');
    const {answerDrawing}=await import('../../solutions/stoa-blueprint-studio/src/grounding.mjs');
    const api=createStoaLocalApi(),demo=await (await api('/api/demo')).json();
    assert.deepEqual(demo.drawing,makeDemo());
    const question='How many rooms labelled Stanza?';
    const answer=await (await api('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({drawingId:'demo',question})})).json();
    assert.deepEqual(answer.result,answerDrawing(makeDemo(),question));
    const unsupported=await (await api('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({drawingId:'demo',question:'How many doors are there?'})})).json();
    assert.equal(unsupported.result.status,'abstained');
    const dxf='0\nSECTION\n2\nHEADER\n9\n$INSUNITS\n70\n6\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n8\nROOM_OUTLINE\n70\n1\n10\n0\n20\n0\n10\n4\n20\n0\n10\n4\n20\n3\n10\n0\n20\n3\n0\nTEXT\n8\nROOM_TEXT\n1\nStanza\n10\n2\n20\n2\n0\nENDSEC\n0\nEOF\n';
    const imported=await api('/api/import-dxf',{method:'POST',headers:{'Content-Type':'application/dxf','X-Filename':'demo.dxf'},body:new TextEncoder().encode(dxf)});
    assert.equal(imported.status,201);assert.match((await imported.json()).drawing.sha256,/^[0-9a-f]{64}$/);
    assert.equal((await api('/api/import-dxf',{method:'POST',headers:{'Content-Type':'application/dxf'},body:new Uint8Array(6*1024*1024+1)})).status,413);
    assert.equal((await api('https://example.invalid')).status,404);
    const chronicle=join(output,'apps/chronicle-witness');
    const chronicleHtml=await readFile(join(chronicle,'studio/index.html'),'utf8');
    assert.match(chronicleHtml,/connect-src 'none'/);assert.doesNotMatch(chronicleHtml,/option value="real"/);
    const {createChronicleLocalApi}=await import(pathToFileURL(join(chronicle,'adapter/chronicle-local-api.mjs')).href);
    const original=await import('../../solutions/mariadb-wikipedia-time/studio/server.mjs');
    const originalDataset=await original.loadFixture(), chronicleApi=createChronicleLocalApi();
    const expectedCatalog=original.makeCatalog(originalDataset);
    assert.deepEqual(await (await chronicleApi('/api/catalog?source=synthetic')).json(),expectedCatalog);
    for(const page of expectedCatalog.pages) for(const revision of page.revisions) {
      const query={page_id:page.page_id,as_of:revision.revised_at,compare_at:page.revisions[0].revised_at};
      const response=await chronicleApi('/api/compare?source=synthetic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(query)});
      assert.equal(response.status,200);assert.deepEqual(await response.json(),original.evaluate(originalDataset,query));
    }
    assert.equal((await chronicleApi('/api/catalog?source=real')).status,422);
    assert.equal((await chronicleApi('https://example.invalid/api/catalog')).status,404);
    assert.equal((await chronicleApi('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:' '.repeat(2049)})).status,413);
    const sama=join(output,'apps/sama');
    const samaHtml=await readFile(join(sama,'web/index.html'),'utf8');
    assert.match(samaHtml,/patient notes are synthetic/);assert.match(samaHtml,/Live model calls and source verification are unavailable/);
    const samaApp=await readFile(join(sama,'web/app.mjs'),'utf8');
    assert.doesNotMatch(samaApp,/fetch\('\/(?:api|data)\//);
    for(const endpoint of ['scribe','scribe/second','verify-claims']) assert.ok(samaApp.includes(`unavailable('/api/${endpoint}'`));
    const {unavailable}=await import(pathToFileURL(join(sama,'adapter/unavailable.mjs')).href);
    assert.equal((await unavailable()).status,503);
    const {computePortfolio}=await import(pathToFileURL(join(sama,'web/bindings.mjs')).href);
    const originalSama=await import('../../solutions/astrazeneca-care-equity/web/bindings.mjs');
    assert.equal(typeof computePortfolio,'function');assert.equal(computePortfolio.toString(),originalSama.computePortfolio.toString());
    const valio=join(output,'apps/valio-portfolio');
    assert.match(await readFile(join(valio,'valio-planner/index.html'),'utf8'),/connect-src 'none'/);
    const {default:valioCatalog}=await import(pathToFileURL(join(valio,'valio-planner/fixture.mjs')).href);
    const {planProcurementPortfolio}=await import(pathToFileURL(join(valio,'src/procurement-planner.mjs')).href);
    const originalPlanner=await import('../../solutions/valio-trusted-trade/src/procurement-planner.mjs');
    const originalCatalog=(await import('../../solutions/valio-trusted-trade/src/core.mjs')).FIXTURE_CATALOG;
    const requirements=[{family:'dairy-milk',quantityLitres:480,lactoseFree:true,deliverBy:'2026-11-16'},
      {family:'oat-drink',quantityLitres:240,lactoseFree:true,deliverBy:'2026-11-16'}];
    assert.deepEqual(planProcurementPortfolio({catalog:valioCatalog,requirements,budgetCents:175000}),originalPlanner.planProcurementPortfolio({catalog:originalCatalog,requirements,budgetCents:175000}));
    assert.throws(()=>planProcurementPortfolio({catalog:valioCatalog,requirements,budgetCents:1}),{code:'BUDGET_EXCEEDED'});
    const replay=await readFile(join(output,'apps/supplypulse-replay/index.html'),'utf8');
    assert.match(replay,/SYNTHETIC_REPLAY/); assert.match(replay,/connect-src 'none'/); assert.match(replay,/src="\.\/app\.mjs"/);
    const supplypulse=await readFile(join(output,'apps/supplypulse/index.html'),'utf8');
    assert.match(supplypulse,/127\.0\.0\.1:4188\/watches\//);
    const saved=JSON.parse(await readFile(join(output,'apps/supplypulse/evidence.json'),'utf8'));
    assert.equal(saved.mode,'HISTORICAL_CAPTURE');assert.equal(saved.offers.length,2);assert(!('winner' in saved));
    const roundlens=join(output,'apps/roundlens');
    const names=['core.mjs','fixture.mjs','public/app.mjs','public/index.html','public/style.css','workspace/restore.mjs'];
    const entries=await Promise.all(names.map(async name=>`${name}\0${createHash('sha256').update(await readFile(join(roundlens,name))).digest('hex')}\n`));
    const expectedDigest=createHash('sha256').update(entries.join('')).digest('hex');
    const core=await import(pathToFileURL(join(roundlens,'core.mjs')).href);
    const {fixture}=await import(pathToFileURL(join(roundlens,'fixture.mjs')).href);
    const artifact=core.makeArtifact(fixture,core.DEFAULT_GOAL,[{id:'inv-larch',note:'',approved:true}]);
    assert.equal(artifact.schema,'roundlens.shortlist.embedded.v1');
    assert.equal(artifact.embeddedClientDigest,expectedDigest);
    assert.match(artifact.upstreamProductSourceDigest,/^[0-9a-f]{64}$/);
    assert.equal(Object.hasOwn(artifact,'productSourceDigest'),false);
    assert.match(await readFile(join(roundlens,'public/app.mjs'),'utf8'), /from '\.\.\/workspace\/restore\.mjs'/);
    const {recoverArchive}=await import(pathToFileURL(join(roundlens,'workspace/restore.mjs')).href);
    const recovered=recoverArchive(core.safeJSON(artifact),fixture);
    assert.equal(recovered.approvalsRevoked,true);
    assert.equal(recovered.reviews[0].approved,false);
    const altered=structuredClone(artifact); altered.embeddedClientDigest='0'.repeat(64);
    assert.throws(()=>recoverArchive(core.safeJSON(altered),fixture),/ARCHIVE_SOURCE_NOT_SUPPORTED/);
    const sourceArtifact={...artifact,schema:'roundlens.shortlist.v1'};
    assert.throws(()=>recoverArchive(core.safeJSON(sourceArtifact),fixture),/ARCHIVE_FORMAT_NOT_SUPPORTED/);

    const index = await readFile(join(output,'index.html'),'utf8');
    for (const app of apps) assert.ok(index.includes(`href="./${app.path.slice(1)}"`));
    await assert.rejects(exportApps(output), {code:'EEXIST'});
  } finally { await rm(temp, {recursive:true,force:true}); }
});

// Validate the producer in a dependency-free copy, then prove that stale domain
// code and modified distribution bytes cannot pass the companion export gate.
test('Valio browser verification rejects stale shared source and modified assets',async()=>{
  const temp=await mkdtemp(join(tmpdir(),'valio-browser-integrity-'));
  const source=new URL('../../solutions/valio-trusted-trade/',import.meta.url);
  try{
    const manifest=JSON.parse(await readFile(new URL('browser/dist/export.json',source),'utf8'));
    const files=[...manifest.inputs.map(input=>input.path),...manifest.assets.map(asset=>'browser/dist/'+asset.path),'browser/dist/export.json'];
    for(const path of files){await mkdir(dirname(join(temp,path)),{recursive:true});await copyFile(new URL(path,source),join(temp,path));}
    const {verifyBrowserBuild}=await import(pathToFileURL(join(temp,'browser/verify.mjs')).href);
    assert.equal((await verifyBrowserBuild()).valid,true);
    const core=join(temp,'src/core.mjs'),original=await readFile(core);
    await writeFile(core,Buffer.concat([original,Buffer.from('\n// stale source probe\n')]));
    await assert.rejects(verifyBrowserBuild(),{code:'BROWSER_BUILD_STALE'});
    await writeFile(core,original);
    const bundle=join(temp,'browser/dist/app.js');
    await writeFile(bundle,Buffer.concat([await readFile(bundle),Buffer.from('\n// changed bundle\n')]));
    await assert.rejects(verifyBrowserBuild(),{code:'BROWSER_BUILD_STALE'});
    const packaged=join(temp,'packaged');await mkdir(packaged);
    for(const path of [...manifest.assets.map(asset=>asset.path),'export.json'])await copyFile(new URL('browser/dist/'+path,source),join(packaged,path));
    assert.equal((await verifyBrowserBuild({distRoot:packaged})).valid,true);
    await writeFile(join(packaged,'app.js'),Buffer.from('modified exported bytes'));
    await assert.rejects(verifyBrowserBuild({distRoot:packaged}),{code:'BROWSER_BUILD_STALE'});
  }finally{await rm(temp,{recursive:true,force:true});}
});
