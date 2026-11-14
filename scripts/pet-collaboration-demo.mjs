import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
import {mkdir,copyFile,writeFile} from 'node:fs/promises';
import {loadPackages} from '../lib/catalog.mjs';
import {runDemo} from '../lib/pet-collaboration.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const out=resolve(root,'dist/collaboration-demo');
const trace=runDemo(await loadPackages(root));
await mkdir(out,{recursive:true});
await writeFile(join(out,'trace.json'),JSON.stringify(trace,null,2)+'\n');
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
  traceSha256:trace.traceSha256,
  output:'dist/collaboration-demo',
  liveModelCalls:0,
  providerActions:0,
},null,2));
