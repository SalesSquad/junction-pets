import {readFile,writeFile,mkdir,readdir,cp,stat} from 'node:fs/promises';
import {resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {sha256} from '../lib/artifact.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const sourceRevision=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim();
const dirty=execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim();
if(dirty)throw new Error('Commit the reviewed source before making the pinned Chibi bundle');
const source=resolve(root,'dist/site');
const catalog=JSON.parse(await readFile(resolve(source,'catalog.json'),'utf8'));
if(catalog.collection.sourceRevision!==sourceRevision)throw new Error('Rebuild the catalogue on this exact source commit');
const destination=resolve(root,'dist/chibi/web/public/junction');
// Never replace an earlier output silently: a fresh build owns its staging directory.
try{await stat(destination);throw new Error('Existing staging directory; use a fresh output checkout or preserve it before rebuilding');}catch(error){if(error.code!=='ENOENT')throw error;}
const html=await readFile(resolve(source,'index.html'),'utf8');
if(!html.includes('src="/junction/assets/'))throw new Error('Build with --base=/junction/ before packaging');
await mkdir(resolve(root,'dist/chibi/web/public'),{recursive:true});
await cp(source,destination,{recursive:true,errorOnExist:true,force:false});
async function files(dir){const result=[];for(const entry of await readdir(dir,{withFileTypes:true})){const path=resolve(dir,entry.name);if(entry.isDirectory())result.push(...await files(path));else if(entry.isFile())result.push(path);else throw new Error('Unsupported bundle entry');}return result;}
const inventory=[];
for(const path of (await files(destination)).sort()){
  const name=relative(destination,path).replaceAll('\\','/');
  if(name.startsWith('qa/')||name.startsWith('junction/'))throw new Error('A QA harness entered the release bundle');
  const bytes=await readFile(path);inventory.push({path:name,bytes:bytes.length,sha256:sha256(bytes)});
}
const lock={schemaVersion:1,sourceRepository:'SalesSquad/junction-pets',sourceRevision,collectionId:'junction-2026',contentSha256:catalog.collection.contentSha256,packages:catalog.pets.map(p=>({id:p.id,slug:p.slug,version:p.version,sha256:p.packageSha256})),files:inventory,publicationStatus:'not-published',recipientJourneyVerified:false};
await writeFile(resolve(destination,'collection.lock.json'),JSON.stringify(lock,null,2)+'\n');
console.log(JSON.stringify({sourceRevision,files:inventory.length,pets:lock.packages.length,destination,publicationStatus:lock.publicationStatus}));
