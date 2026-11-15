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
    assert.deepEqual(new Set(apps.map(app => app.petSlug)), new Set(['junction-arduino','junction-intel','junction-city-of-espoo','junction-rokoko','junction-bahn-express','junction-s-pankki','junction-meta','junction-banker','junction-aalto-university','junction-hostinger','junction-cala','junction-context-dev','junction-valio-aimo']));
    assert.equal(apps.filter(app=>app.petSlug==='junction-intel').length,2);
    const valio=apps.find(app=>app.petSlug==='junction-valio-aimo');
    assert.equal(valio.path,'/apps/aimo-trade/browser/dist/index.html');
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
    const replay=await readFile(join(output,'apps/supplypulse-replay/index.html'),'utf8');
    assert.match(replay,/SYNTHETIC_REPLAY/); assert.match(replay,/connect-src 'none'/); assert.match(replay,/src="\.\/app\.mjs"/);
    const roundlens=join(output,'apps/roundlens');
    const names=['core.mjs','fixture.mjs','public/app.mjs','public/index.html','public/style.css'];
    const entries=await Promise.all(names.map(async name=>`${name}\0${createHash('sha256').update(await readFile(join(roundlens,name))).digest('hex')}\n`));
    const expectedDigest=createHash('sha256').update(entries.join('')).digest('hex');
    const core=await import(pathToFileURL(join(roundlens,'core.mjs')).href);
    const {fixture}=await import(pathToFileURL(join(roundlens,'fixture.mjs')).href);
    const artifact=core.makeArtifact(fixture,core.DEFAULT_GOAL,[{id:'inv-larch',note:'',approved:true}]);
    assert.equal(artifact.schema,'roundlens.shortlist.embedded.v1');
    assert.equal(artifact.embeddedClientDigest,expectedDigest);
    assert.match(artifact.upstreamProductSourceDigest,/^[0-9a-f]{64}$/);
    assert.equal(Object.hasOwn(artifact,'productSourceDigest'),false);
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
  }finally{await rm(temp,{recursive:true,force:true});}
});
