import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {planCloudDispatch} from '../ops/cloud-dispatch.mjs';
import {localSourceCommit} from '../ops/registry.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const tokens=process.argv.slice(2),opts=new Map();
for(let i=0;i<tokens.length;i+=2){
  if(!tokens[i]?.startsWith('--')||!tokens[i+1]||tokens[i+1].startsWith('--')){
    console.error('Usage: node scripts/ops-cloud-dispatch.mjs --pet junction-aiven --branch codex/junction-aiven-slice --source <SHA> --profile plus|pro');
    process.exit(2);
  }
  opts.set(tokens[i].slice(2),tokens[i+1]);
}
try{
  const petSlug=opts.get('pet');
  if(!/^junction-[a-z0-9-]+$/.test(petSlug??''))throw new Error('Invalid pet slug');
  const actualHead=localSourceCommit(root);
  if(!actualHead||opts.get('source')!==actualHead)throw new Error('Source SHA not equal to current local HEAD; refresh and verify');
  const manifest=JSON.parse(await readFile(resolve(root,'ops/environments/'+petSlug.slice('junction-'.length)+'.json'),'utf8'));
  const plan=planCloudDispatch(manifest,{
    petSlug,branch:opts.get('branch'),sourceCommit:opts.get('source'),profile:opts.get('profile')
  });
  console.log(JSON.stringify(plan,null,2));
}catch(error){
  console.error('DISPATCH BLOCKED: '+error.message);
  process.exitCode=1;
}
