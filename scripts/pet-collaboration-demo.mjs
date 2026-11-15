import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {mkdir,copyFile,readFile,readdir,writeFile} from 'node:fs/promises';
import {loadPackages} from '../lib/catalog.mjs';
import {runDemo} from '../lib/pet-collaboration.mjs';
import {projectSolutionTeams} from '../lib/solution-team-projection.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const out=resolve(root,'dist/collaboration-demo');
const packages=await loadPackages(root);
const trace=runDemo(packages);
// Read canonical solution.json files with their filesystem directory identities.
const solutionEntries=[];
for(const entry of await readdir(resolve(root,'solutions'),{withFileTypes:true})){
  if(!entry.isDirectory())continue;
  try{
    const manifest=JSON.parse(await readFile(resolve(root,'solutions',entry.name,'solution.json'),'utf8'));
    solutionEntries.push({directory:entry.name,manifest});
  }catch(error){
    if(error?.code!=='ENOENT')throw error;
  }
}
const projection=projectSolutionTeams(packages,solutionEntries);
await mkdir(out,{recursive:true});
await writeFile(join(out,'trace.json'),JSON.stringify(trace,null,2)+'\n');
await writeFile(join(out,'solution-teams.json'),JSON.stringify(projection,null,2)+'\n');
for (const name of ['index.html','style.css','app.js']) {
  await copyFile(resolve(root,'apps/collaboration-demo',name),join(out,name));
}
// Reuse the canonical 34-companion atlas; generated dist remains derivative.
await copyFile(resolve(root,'apps/catalog/public/assets/company-mascots.png'),join(out,'company-mascots.png'));
console.log(JSON.stringify({
  status:'synthetic-trace-generated',
  mode:trace.executionMode,
  participants:trace.participants.length,
  messages:trace.messages.length,
  sourceDeclaredTeams:projection.teams.length,
  projectionSha256:projection.projectionSha256,
  traceSha256:trace.traceSha256,
  output:'dist/collaboration-demo',
  liveModelCalls:0,
  providerActions:0,
},null,2));
