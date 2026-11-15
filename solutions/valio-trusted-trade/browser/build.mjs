import { build } from 'esbuild';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyBrowserBuild } from './verify.mjs';
const here=dirname(fileURLToPath(import.meta.url)),root=resolve(here,'..'),dist=resolve(here,'dist');
const sha=value=>createHash('sha256').update(value).digest('hex');
await mkdir(dist,{recursive:true});
const result=await build({absWorkingDir:here,entryPoints:['app.mjs'],outfile:'dist/app.js',bundle:true,format:'esm',platform:'browser',target:'es2022',minify:true,metafile:true,legalComments:'inline',
  inject:[resolve(here,'globals.mjs')],plugins:[{name:'explicit-browser-boundaries',setup(builder){
    builder.onResolve({filter:/^node:crypto$/},()=>({path:resolve(here,'crypto.mjs')}));
    builder.onResolve({filter:/^node:assert\/strict$/},()=>({path:resolve(here,'assert.mjs')}));
    builder.onResolve({filter:/^node:child_process$/},()=>({path:resolve(here,'process-disabled.mjs')}));
    builder.onResolve({filter:/^node:/},args=>{throw Error('Unsupported Node boundary in browser bundle: '+args.path);});
  }}]});
await copyFile(resolve(here,'index.html'),resolve(dist,'index.html'));await copyFile(resolve(here,'app.css'),resolve(dist,'app.css'));
const libraries=[],notices=[];
for(const name of ['@noble/curves','@noble/hashes']){
  const base=resolve(here,'node_modules',name),pkg=JSON.parse(await readFile(resolve(base,'package.json'),'utf8'));
  libraries.push({name,version:pkg.version,license:pkg.license});notices.push(name+' '+pkg.version+' — '+pkg.license+'\n\n'+await readFile(resolve(base,'LICENSE'),'utf8'));
}
await writeFile(resolve(dist,'NOTICE.txt'),'Valio Aimo browser-local synthetic app\n\nRuntime dependency notices. esbuild is a build tool only.\n\n'+notices.join('\n\n---\n\n'));
const inputs=new Set(['app.mjs','runtime.mjs','crypto.mjs','globals.mjs','process-disabled.mjs','assert.mjs','build.mjs','verify.mjs','package.json','package-lock.json','index.html','app.css'].map(path=>'browser/'+path));
for(const input of Object.keys(result.metafile.inputs))if(!input.includes('node_modules/'))inputs.add(relative(root,resolve(here,input)).split('\\').join('/'));
const manifest={format:1,app:'valio-aimo-browser-local',scope:'BROWSER_LOCAL_SYNTHETIC',
  inputs:await Promise.all([...inputs].sort().map(async path=>({path,sha256:sha(await readFile(resolve(root,path)))}))),
  assets:await Promise.all(['index.html','app.js','app.css','NOTICE.txt'].map(async path=>{const value=await readFile(resolve(dist,path));return {path,bytes:value.byteLength,sha256:sha(value)};})),
  libraries,crypto:'NOBLE_ED25519_SHA256_AND_NONEXTRACTABLE_WEBCRYPTO_BUYER_KEY',unsupported:['server OCR','pgvector','MCP transport','host JWT identity','real supplier orders','real payments']};
await writeFile(resolve(dist,'export.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify(await verifyBrowserBuild()));
