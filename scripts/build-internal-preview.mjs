import {cp, mkdir, readFile, stat} from 'node:fs/promises';
import {resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

// Only build the explicitly private development preview; never append it to
// dist/site or the Chibi Maker release bundle.
const root=fileURLToPath(new URL('../',import.meta.url));
const out=resolve(root,'dist/mission-control');
const inDir=resolve(root,'apps/mission-control');
const files=['index.html','style.css','app.js','status-model.mjs'];
await mkdir(out,{recursive:true});
for(const file of files){
  const source=resolve(inDir,file);
  if(!source.startsWith(inDir+sep))throw new Error('Private UI path escaped root');
  await cp(source,resolve(out,file));
}
const status=JSON.parse(await readFile(resolve(out,'status.json'),'utf8'));
if(status.schemaVersion!==1||status.pets?.length!==34||status.summary?.total!==34){
  throw new Error('Internal preview requires the validated 34-pet status snapshot');
}
await stat(resolve(out,'index.html'));
console.log(JSON.stringify({preview:out,pets:status.pets.length,source:status.source,private:true}));
