import assert from 'node:assert/strict';
import { test } from 'node:test';
import { validateSpaceSources } from '../scripts/check-space-source-index.mjs';

const id = n => `page_${n.toString(16).padStart(32, '0')}`;
const fixtures = () => {
  const pages = Array.from({length:35}, (_,n) => ({page_id:id(n),url:`https://chatgpt.com/space/${id(n)}`,readback_verified:true}));
  // Nineteen official tech briefs map to eleven tech cards and two shared
  // main cards; the remaining five tech partner cards are supplemental.
  const coverage = (count,kind) => Array.from({length:count},(_,n)=>{
    const page = kind === 'tech-' ? pages[
      n < 11 ? 19+n : n < 13 ? n-11 : 19+(n-13)
    ] : pages[n];
    return {source_url:`https://hackjunction.app/participate/45/${kind}challenges/${n+1}`,page_urls:[page.url]};
  });
  const index = {schemaVersion:1,repository:'SalesSquad/junction-pets',observedMainHead:'a'.repeat(40),agents:Array.from({length:34},(_,n)=>({id:`junction.a${n}`,slug:`a${n}`,manifest:`pets/a${n}/pet.json`,runtimeProfile:`pets/a${n}/AGENTS.md`,research:`pets/a${n}/CHALLENGE_RESEARCH.md`,developerConfiguration:`ops/environments/a${n}.json`})),extensions:[{pullRequest:61,observedState:'open',observedCommit:'b'.repeat(40),isMainImplementation:true,mainIntegration:{viaPullRequest:66,mergeCommit:'c'.repeat(40)}}]};
  const map = {schema:'junction-spaces-reconciliation/v1',main_coverage:coverage(19,''),tech_coverage:coverage(19,'tech-'),card_pages:pages,canonical_page_inventory:{main:pages.slice(0,19).map(p=>p.page_id),tech:pages.slice(19).map(p=>p.page_id)}};
  return {index,map};
};

test('valid 34-agent, 19+19 source, 35-page inventory',()=>{
  const {index,map}=fixtures();
  assert.deepEqual(validateSpaceSources(index,map).stats,{agents:34,mainSources:19,techSources:19,cardPages:35,mainPages:19,techPages:16});
  assert.equal(validateSpaceSources(index,map).ok,true);
});
test('reject duplicate page ID and inventory drift',()=>{
  const {index,map}=fixtures();
  map.card_pages[1].page_id=map.card_pages[0].page_id;
  const r=validateSpaceSources(index,map);
  assert.equal(r.ok,false);
  assert.match(r.errors.join(' '),/duplicate card page ID/);
});
test('reject absent main integration despite observed proof',()=>{
  const {index,map}=fixtures();
  index.extensions[0].isMainImplementation=false;
  assert.match(validateSpaceSources(index,map).errors.join(' '),/marked pending despite main integration/);
});
test('reject missing agents and stale mapped source coverage',()=>{
  const {index,map}=fixtures();
  index.agents.pop();
  map.tech_coverage.pop();
  const r=validateSpaceSources(index,map);
  assert.equal(r.ok,false);
  assert.match(r.errors.join(' '),/agent count/);
  assert.match(r.errors.join(' '),/tech_coverage/);
});
test('reject invalid source URL and card URL',()=>{
  const {index,map}=fixtures();
  map.main_coverage[0].source_url='https://example.com';
  map.card_pages[0].url='https://example.com';
  const r=validateSpaceSources(index,map);
  assert.match(r.errors.join(' '),/source URL/);
  assert.match(r.errors.join(' '),/noncanonical card URL/);
});
test('reject coverage links to a Page missing from the verified catalog',()=>{
  const {index,map}=fixtures();
  map.main_coverage[0].page_urls=['https://chatgpt.com/space/page_ffffffffffffffffffffffffffffffff'];
  assert.match(validateSpaceSources(index,map).errors.join(' '),/source references a missing canonical Page/);
});
test('reject a malformed agent source route before it breaks onboarding',()=>{
  const {index,map}=fixtures();
  index.agents[0].manifest='pets/wrong-company/pet.json';
  assert.match(validateSpaceSources(index,map).errors.join(' '),/invalid canonical manifest route/);
});
test('report malformed entries without throwing TypeError',()=>{
  const {index,map}=fixtures();
  index.agents[0]=null;
  map.card_pages[0]=null;
  assert.doesNotThrow(()=>validateSpaceSources(index,map));
  assert.equal(validateSpaceSources(index,map).ok,false);
});
