import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const read=path=>readFileSync(resolve(ROOT,path),'utf8');
const hash=value=>createHash('sha256').update(value).digest('hex');
const fail=message=>{throw Error(message)};
const graph=JSON.parse(read('ops/agent-composition-20261113.json'));
if(graph.schema!=='junction-agent-composition/v1'||graph.edges_are_permissions!==false||graph.automatic_dispatch!==false)fail('invalid graph boundary');
const slugs=readdirSync(resolve(ROOT,'pets'),{withFileTypes:true}).filter(x=>x.isDirectory()).map(x=>x.name).sort();
if(slugs.length!==34||graph.agents.length!==34)fail('incomplete agent roster');
const agents=new Map();
for(const a of graph.agents){
 if(agents.has(a.id)||a.id!=='junction.'+a.slug||!slugs.includes(a.slug))fail('invalid agent identity');
 const pet=JSON.parse(read('pets/'+a.slug+'/pet.json'));
 if(pet.id!==a.id||pet.version!==a.packageVersion)fail('manifest version drift: '+a.slug);
 if(hash(read('pets/'+a.slug+'/pet.json'))!==a.manifestSha256||hash(read(a.knowledgeEmbeddedIn))!==a.guidanceSha256)fail('knowledge digest drift: '+a.slug);
 if(hash(read('pets/'+a.slug+'/evals.json'))!==a.evalsSha256)fail('evaluation source drift: '+a.slug);
 if(!read(a.knowledgeEmbeddedIn).includes('Current challenge and peer composition'))fail('missing runtime knowledge: '+a.slug);
 if(!pet.capabilities.some(c=>c.id===a.designCapabilityId))fail('missing design capability: '+a.slug);
 if(!a.challengeReferences.every(x=>/^https:\/\/hackjunction\.app\/participate\/45\/(?:tech-)?challenges\/\d+$/.test(x.url)))fail('invalid primary source');
 agents.set(a.id,{...a,pet});
}
const seen=new Set();
for(const e of graph.edges){
 if(seen.has(e.id)||!agents.has(e.from)||!agents.has(e.to)||e.from===e.to)fail('invalid edge');
 if(e.requiresHostAuthority!==true||!['host-guidance-proposal','developer-recipe'].includes(e.execution))fail('invalid execution boundary');
 const target=agents.get(e.to).pet.capabilities.find(c=>c.id===e.capabilityId);
 if(!target)fail('undeclared target capability: '+e.id);
 if(e.execution==='host-guidance-proposal'&&target.kind!=='planning')fail('guidance edge is not a planning capability');
 if(e.execution==='developer-recipe'&&(e.from!=='junction.stoa'||e.to!=='junction.nvidia'||e.capabilityId!=='drawing-observation'||!target.requiresConnection))fail('unexpected executable recipe');
 seen.add(e.id);
}
if(graph.recipes.length!==1||graph.recipes[0].id!=='stoa-nvidia-drawing'||graph.recipes[0].default!=='offline-plan'||graph.recipes[0].liveProviderVerified!==false||graph.recipes[0].productionHostVerified!==false)fail('invalid recipe qualification');
for(const key of ['entrypoint','prepare','providerEntrypoint']){
 const [path,fn]=graph.recipes[0][key].split('#');
 if(!read(path).includes(fn))fail('missing recipe entry: '+key);
}
const main=new Set(graph.agents.flatMap(a=>a.challengeReferences.filter(x=>!x.url.includes('/tech-challenges/')).map(x=>x.url)));
if(main.size!==19)fail('missing main challenge coverage');
console.log(JSON.stringify({agents:agents.size,proposedEdges:seen.size,mainChallenges:main.size,developerRecipes:1,knowledgeDigests:'verified',hostAuthority:'required',liveProviderVerified:false,productionHostVerified:false},null,2));
