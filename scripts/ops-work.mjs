import {fileURLToPath} from 'node:url';
import {buildStatus,leaseContent,acquireLease,releaseLease,reclaimStaleCriticalLock,localSourceCommit} from '../ops/registry.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const [command,...tokens]=process.argv.slice(2);
const opts=new Map();
for(let i=0;i<tokens.length;i+=2) {
  if(!tokens[i]?.startsWith('--')||!tokens[i+1]||tokens[i+1].startsWith('--')) {
    console.error('Invalid CLI arguments');
    process.exit(2);
  }
  opts.set(tokens[i].slice(2),tokens[i+1]);
}
const value=(name)=>opts.get(name);

try {
  if(command==='status'){
    if(opts.size)throw new Error('status takes no options');
    const {summary,pets,source}=await buildStatus(root);
    console.log(JSON.stringify({source,summary,workQueue:pets.map(p=>({
      petSlug:p.slug,agentId:p.agent.id,cloud:p.cloud.state,claim:p.development.claim,
      blocker:p.blocker,nextAction:p.nextAction
    }))},null,2));
  } else if(command==='claim') {
    if(!value('pet')||!value('agent')||!value('work')||!value('source'))throw new Error('claim requires --pet, --agent, --work and --source exact SHA');
    if(value('source')!==localSourceCommit(root))throw new Error('The requested source SHA does not match this local worktree HEAD; refresh source and retry.');
    const lease=leaseContent({petSlug:value('pet'),agentId:value('agent'),workId:value('work'),sourceCommit:value('source'),minutes:value('minutes')?Number(value('minutes')):30});
    await acquireLease(root,lease);
    console.log(JSON.stringify({result:'local-workspace-lease-acquired',distributedAuthority:false,lease},null,2));
  } else if(command==='release'){
    if(!value('pet')||!value('lease'))throw new Error('release requires --pet and --lease ID');
    await releaseLease(root,{petSlug:value('pet'),leaseId:value('lease')});
    console.log(JSON.stringify({result:'local-workspace-lease-released',pet:value('pet')}));
  } else if(command==='reclaim-stale-lock'){
    if(!value('pet')||!value('owner'))throw new Error('reclaim-stale-lock requires --pet and exact --owner ID');
    const result=await reclaimStaleCriticalLock({claimRoot:new URL('../dist/ops-claims/',import.meta.url).pathname,petSlug:value('pet'),expectedOwnerId:value('owner')});
    console.log(JSON.stringify(result));
  } else {
    throw new Error('Usage: node scripts/ops-work.mjs status | claim --pet junction-aiven --agent junction-dev-aiven --work junction.aiven.cloud-bootstrap --source <40hexsha> [--minutes 30] | release --pet junction-aiven --lease <uuid> | reclaim-stale-lock --pet junction-aiven --owner <owner UUID>');
  }
} catch(error) {
  console.error(error.message);
  process.exitCode=1;
}
