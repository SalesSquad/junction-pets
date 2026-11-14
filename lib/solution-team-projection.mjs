import {canonicalJson,sha256} from './artifact.mjs';
import {validateSolution} from '../scripts/solution-workspace.mjs';

/**
 * Read-only view of directory-bound solution.json -> existing pet manifests.
 * This is not a separate membership registry or a Chibi authority decision.
 */
export function projectSolutionTeams(packages,solutionEntries){
  if(!Array.isArray(packages)||!Array.isArray(solutionEntries))throw new Error('Invalid projection input');
  const agents=packages.map(candidate=>candidate.pet??candidate);
  const pets=new Map(agents.map(pet=>[pet.id,pet]));
  const seenSolutions=new Set();
  const teams=solutionEntries.map(entry=>{
    if(!entry||typeof entry.directory!=='string')throw new Error('Solution workspace directory required');
    // PR #82's canonical validator binds identity to the actual workspace directory.
    const solution=validateSolution(entry.manifest,agents,entry.directory);
    if(seenSolutions.has(solution.id))throw new Error('Duplicate solution');
    seenSolutions.add(solution.id);
    const uses=new Map(solution.agentIds.map(id=>[id,[]]));
    for(const use of solution.capabilityUses){
      const capability=pets.get(use.agentId).capabilities.find(item=>item.id===use.capabilityId);
      uses.get(use.agentId).push({
        capabilityId:capability.id,title:capability.title,
        purpose:use.purpose,status:use.status,
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
