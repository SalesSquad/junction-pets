import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {canonicalOrigin} from '../lib/links.mjs';
import {loadPackages} from '../lib/catalog.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const config=JSON.parse(await readFile(resolve(root,'config/host-config.json'),'utf8'));
const origin=canonicalOrigin(config.canonicalOrigin),packs=await loadPackages(root);
const paths=['/api/rust/v1/me',...packs.map(p=>'/api/rust/v1/catalog/chibis/'+p.pet.slug)];
const results=[];
// Bounded unauthenticated discovery. No cookies, sign-in, adoption or provider call.
for(let at=0;at<paths.length;at+=4){results.push(...await Promise.all(paths.slice(at,at+4).map(async path=>{try{const response=await fetch(origin+path,{redirect:'manual',signal:AbortSignal.timeout(12000),headers:{Accept:'application/json'}});const mime=response.headers.get('content-type')??'';let code=null;if(mime.includes('application/json')){const body=await response.json();code=typeof body?.code==='string'?body.code:typeof body?.error?.code==='string'?body.error.code:null;}return {path,status:response.status,contentType:mime,errorCode:code};}catch(error){return {path,status:null,errorCode:error.name};}})));}
const report={checkedAt:new Date().toISOString(),origin,scope:'unauthenticated-public-reads',realRecipientJourneyVerified:false,results};
await mkdir(resolve(root,'dist/evidence'),{recursive:true});await writeFile(resolve(root,'dist/evidence/host-check.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
