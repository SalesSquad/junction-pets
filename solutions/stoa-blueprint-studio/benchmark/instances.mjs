/** Instance membership metrics over original source entity IDs; independent labels are required. */
import { readFile } from 'node:fs/promises';
import { digest } from '../src/evidence.mjs';
import { fileURLToPath } from 'node:url';
function partition(groups){
  if(!Array.isArray(groups)||groups.length>500)throw new Error('Use at most 500 instances per partition.');
  const owner=new Map(),sizes=[];
  groups.forEach((g,i)=>{
    if(!Array.isArray(g)||!g.length||g.length>12000)throw new Error('Instances need bounded nonempty source memberships.');
    for(const id of g){if(typeof id!=='string'||!id||id.length>100||owner.has(id))throw new Error('Duplicate or overlapping source membership.');owner.set(id,i);}
    sizes.push(g.length);
  });
  if(owner.size>12000)throw new Error('Source membership budget exceeded.');
  return {owner,sizes};
}
export function instanceMetrics({sourceSha256,truthSourceSha256,truth,predicted,threshold=.5}){
  if(!/^[a-f0-9]{64}$/.test(sourceSha256)||sourceSha256!==truthSourceSha256)throw new Error('Prediction and labels must refer to the same source bytes.');
  if(!Number.isFinite(threshold)||threshold<=0||threshold>1)throw new Error('Invalid IoU threshold.');
  const a=partition(truth),b=partition(predicted),overlap=new Map(),truthNeighbours=new Map(),predNeighbours=new Map();
  for(const [id,i] of a.owner){const j=b.owner.get(id);if(j==null)continue;const key=JSON.stringify([i,j]);overlap.set(key,(overlap.get(key)??0)+1);if(!truthNeighbours.has(i))truthNeighbours.set(i,new Set());truthNeighbours.get(i).add(j);if(!predNeighbours.has(j))predNeighbours.set(j,new Set());predNeighbours.get(j).add(i);}
  const adj=new Map();for(const [key,n] of overlap){const [i,j]=JSON.parse(key);if(n/(a.sizes[i]+b.sizes[j]-n)>=threshold){if(!adj.has(i))adj.set(i,[]);adj.get(i).push(j);}}
  const match=new Map();
  const visit=(i,seen)=>{for(const j of adj.get(i)??[]){if(seen.has(j))continue;seen.add(j);if(!match.has(j)||visit(match.get(j),seen)){match.set(j,i);return true;}}return false;};
  a.sizes.forEach((_,i)=>visit(i,new Set()));
  const choose=n=>n*(n-1)/2,commonPairs=[...overlap.values()].reduce((s,n)=>s+choose(n),0),tp=a.sizes.reduce((s,n)=>s+choose(n),0),pp=b.sizes.reduce((s,n)=>s+choose(n),0);
  return {sourceSha256,threshold,truthInstances:a.sizes.length,predictedInstances:b.sizes.length,matchedInstances:match.size,
    instancePrecision:b.sizes.length?match.size/b.sizes.length:null,instanceRecall:a.sizes.length?match.size/a.sizes.length:null,
    pairPrecision:pp?commonPairs/pp:null,pairRecall:tp?commonPairs/tp:null,
    mergedPredictions:[...predNeighbours.values()].filter(s=>s.size>1).length,splitTruthInstances:[...truthNeighbours.values()].filter(s=>s.size>1).length,
    missedMembers:[...a.owner.keys()].filter(id=>!b.owner.has(id)).length,unknownPredictedMembers:[...b.owner.keys()].filter(id=>!a.owner.has(id)).length,
    semanticTruthVerified:false};
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]){
  if(!process.argv[2])throw new Error('Usage: node benchmark/instances.mjs <independently-labelled-memberships.json>');
  const raw=await readFile(process.argv[2]);if(raw.length>4*1024*1024)throw new Error('Instance input exceeds 4 MiB.');
  console.log(JSON.stringify({inputSha256:digest(raw),scorerSha256:digest(await readFile(fileURLToPath(import.meta.url))),metrics:instanceMetrics(JSON.parse(raw))},null,2));
}
