import {canonicalJson,sha256} from './artifact.mjs';

/**
 * Read-only view of solution.json -> existing pet manifests.
 * This is not a separate membership registry or a Chibi authority decision.
 */
export function projectSolutionTeams(packages,solutions){
  if(!Array.isArray(packages)||!Array.isArray(solutions))throw new Error('Invalid projection input');
  const pets=new Map(packages.map(candidate=>{
    const pet=candidate.pet??candidate;
    return [pet.id,pet];
  }));
  const seenSolutions=new Set();
  const teams=solutions.map(solution=>{
    if(!solution||typeof solution.id!=='string'||typeof solution.title!=='string'
      ||!Array.isArray(solution.agentIds)||!Array.isArray(solution.capabilityUses)
      ||!Array.isArray(solution.challengeSlugs))throw new Error('Invalid solution composition');
    if(seenSolutions.has(solution.id))throw new Error('Duplicate solution');
    seenSolutions.add(solution.id);
    if(new Set(solution.agentIds).size!==solution.agentIds.length)throw new Error('Duplicate solution member');
    const selected=new Set(solution.agentIds);
    const uses=new Map(solution.agentIds.map(id=>[id,[]]));
    const seenUses=new Set();
    for(const use of solution.capabilityUses){
      const pet=pets.get(use.agentId);
      const capability=pet?.capabilities?.find(candidate=>candidate.id===use.capabilityId);
      const key=use.agentId+'/'+use.capabilityId;
      if(!selected.has(use.agentId)||!capability||use.status!=='planned'
        ||typeof use.purpose!=='string'||!use.purpose.trim()||seenUses.has(key))
        throw new Error('Unknown, duplicate or non-planned capability use');
      seenUses.add(key);
      uses.get(use.agentId).push({
        capabilityId:capability.id,title:capability.title,
        purpose:use.purpose,status:'planned',
      });
    }
    const members=solution.agentIds.map(id=>{
      const pet=pets.get(id);
      if(!pet||!Number.isInteger(pet.artIndex)||pet.artIndex<0||pet.artIndex>=36)
        throw new Error('Unknown pet or avatar in solution');
      return {
        petId:id,displayName:pet.displayName,company:pet.company.name,
        artIndex:pet.artIndex,capabilityUses:uses.get(id),
      };
    });
    return {
      id:solution.id,title:solution.title,stage:solution.stage,
      challengeSlugs:[...solution.challengeSlugs],members,
      // The first listing is a visual anchor, NOT a runtime coordinator grant.
      displayAnchorId:members[0]?.petId??null,
    };
  }).sort((a,b)=>a.id.localeCompare(b.id));
  const content={
    schemaVersion:1,
    executionMode:'declared-memberships-no-dispatch',
    source:{repository:'SalesSquad/junction-pets',verifiedCommit:null},
    teams,
    limitations:['No Chibi adoption, user consent or host authorization',
      'Membership and peer arrows are plans, not executed requests'],
  };
  return {...content,projectionSha256:sha256(canonicalJson(content))};
}
