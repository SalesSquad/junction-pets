import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {loadPackages} from '../lib/catalog.mjs';
import {canonicalJson,sha256} from '../lib/artifact.mjs';
import {projectSolutionTeams} from '../lib/solution-team-projection.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const packages=await loadPackages(root);
const valio=JSON.parse(await readFile(new URL('../solutions/valio-trusted-trade/solution.json',import.meta.url),'utf8'));

test('Valio team binds three existing pets, declared skills and original avatar indices',()=>{
  const projection=projectSolutionTeams(packages,[valio]);
  assert.equal(projection.executionMode,'declared-memberships-no-dispatch');
  assert.deepEqual(projection.teams[0].members.map(member=>[member.petId,member.artIndex]),[
    ['junction.valio-aimo',1],['junction.aiven',29],['junction.afterquery',8],
  ]);
  for(const member of projection.teams[0].members){
    assert.equal(member.capabilityUses.length,1);
    assert.equal(member.capabilityUses[0].status,'planned');
    assert.ok(member.capabilityUses[0].purpose.length>20);
  }
  const {projectionSha256,...content}=projection;
  assert.equal(projectionSha256,sha256(canonicalJson(content)));
  assert.equal(projection.source.verifiedCommit,null);
});

test('unknown member, unknown capability and duplicate plan fail before visualization',()=>{
  assert.throws(()=>projectSolutionTeams(packages,[{...valio,agentIds:[...valio.agentIds,'junction.fake']}]),/Unknown agent/);
  assert.throws(()=>projectSolutionTeams(packages,[{...valio,capabilityUses:[{...valio.capabilityUses[0],capabilityId:'purchase-live-stock'}]}]),/Unknown or unselected agent capability/);
  assert.throws(()=>projectSolutionTeams(packages,[{...valio,capabilityUses:[{...valio.capabilityUses[0],status:'executed'}]}]),/Capability uses are planned references/);
  assert.throws(()=>projectSolutionTeams(packages,[{...valio,ownedPaths:['apps/collaboration-demo/']}]),/Scaffold ownership/);
  assert.throws(()=>projectSolutionTeams(packages,[valio,valio]),/Duplicate solution/);
});
