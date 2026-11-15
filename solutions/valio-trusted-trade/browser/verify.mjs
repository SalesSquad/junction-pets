/** Builtins-only freshness verification for exporters; does not install or load runtime dependencies. */
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const sha=value=>createHash('sha256').update(value).digest('hex');
const fail=()=>{throw Object.assign(new Error('Browser export is stale, incomplete or modified; run its declared build producer.'),{code:'BROWSER_BUILD_STALE'});};
export async function verifyBrowserBuild({solutionRoot=root}={}){
  try{
    const manifest=JSON.parse(await readFile(resolve(solutionRoot,'browser/dist/export.json'),'utf8'));
    if(manifest.format!==1||manifest.app!=='valio-aimo-browser-local'||manifest.scope!=='BROWSER_LOCAL_SYNTHETIC'||!Array.isArray(manifest.inputs)||!Array.isArray(manifest.assets))fail();
    const required=['browser/app.mjs','browser/runtime.mjs','browser/crypto.mjs','browser/build.mjs','browser/verify.mjs','browser/package.json','browser/package-lock.json','browser/index.html','browser/app.css','browser/globals.mjs','browser/process-disabled.mjs','browser/assert.mjs','src/core.mjs','src/trust-envelope.mjs','src/settlement.mjs','src/procurement-planner.mjs','src/procurement-diagnostics.mjs','src/purchase-units.mjs','src/scanning.mjs','src/buyer-terms.mjs'];
    if(manifest.inputs.length>256)fail();
    if(required.some(path=>!manifest.inputs.some(input=>input.path===path)))fail();
    const seen=new Set();
    for(const input of manifest.inputs){
      if(!input||! /^[a-f0-9]{64}$/.test(input.sha256??'')||typeof input.path!=='string'||! /^(?:browser|src)\/[A-Za-z0-9_./-]+\.(?:mjs|json|css|html)$/.test(input.path)||input.path.split('/').includes('..')||input.path.includes('/node_modules/')||seen.has(input.path))fail();
      seen.add(input.path);if(sha(await readFile(resolve(solutionRoot,input.path)))!==input.sha256)fail();
    }
    const names=['index.html','app.js','app.css','NOTICE.txt'];
    if(manifest.assets.length!==names.length||names.some(name=>!manifest.assets.some(asset=>asset.path===name)))fail();
    for(const asset of manifest.assets){if(!names.includes(asset.path))fail();const bytes=await readFile(resolve(solutionRoot,'browser/dist',asset.path));if(bytes.byteLength!==asset.bytes||sha(bytes)!==asset.sha256)fail();}
    return {valid:true,scope:manifest.scope,inputs:manifest.inputs.length,assets:manifest.assets.length};
  }catch{fail();}
}
