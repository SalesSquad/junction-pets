#!/usr/bin/env node
import {execFileSync} from 'node:child_process';
import {realpathSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {ENDPOINT,MODEL,LIMITS,runNemotron,companionBinding} from './index.mjs';
import {syntheticFixture} from './fixture.mjs';

const ROOT=realpathSync(fileURLToPath(new URL('../../',import.meta.url)));
const ORIGINS=new Set(['https://github.com/SalesSquad/junction-pets.git','git@github.com:SalesSquad/junction-pets.git']);
const TRACKED=['services/nemotron-vl/index.mjs','services/nemotron-vl/cli.mjs','services/nemotron-vl/fixture.mjs',
  'services/nemotron-vl/synthetic-worksheet.png','pets/nvidia/comparability.mjs','pets/nvidia/pet.json','pets/nvidia/AGENTS.md'];
function verifySourceTree(sha) {
  const git=(...args)=>execFileSync('git',args,{cwd:ROOT,encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:5000,maxBuffer:1_000_000}).trim();
  if(realpathSync(git('rev-parse','--show-toplevel'))!==ROOT || git('rev-parse','HEAD')!==sha ||
    !ORIGINS.has(git('remote','get-url','origin')) || git('status','--porcelain=v1','--untracked-files=normal')) throw new Error('source-verification-failed');
  for(const file of TRACKED) git('ls-files','--error-unmatch','--',file);
}
async function main(args) {
  let execute=false,sha=null;
  for(let i=0;i<args.length;i++) {
    if(args[i]==='--execute' && !execute) execute=true;
    else if(args[i]==='--source-commit' && !sha && /^[a-f0-9]{40}$/.test(args[i+1] ?? '')) sha=args[++i];
    else throw new Error('invalid-cli-arguments');
  }
  const fixture=syntheticFixture();
  if(!execute) {
    console.log(JSON.stringify({mode:'plan-only',companion:companionBinding(),model:MODEL,endpoint:ENDPOINT,sourceCommit:sha,
      workflow:['visual_observation','bounded_tool_selection','evidence_synthesis','evidence_verification'],limits:LIMITS,
      fixture:{kind:'authored-synthetic-diagram',imageSha256:createHash('sha256').update(Buffer.from(fixture.images[0].split(',')[1],'base64')).digest('hex'),
        benchmarkEvidence:'authored-estimate',measuredPerformanceVerified:false},
      providerAccess:'not-checked',networkRequests:0,secretReads:0,hostVerification:'unverified',
      next:'On a clean pinned checkout with the verified origin and NVIDIA_API_KEY configured, run --execute --source-commit <full HEAD SHA>.'},null,2));
    return;
  }
  if(!sha) throw new Error('source-commit-required');
  verifySourceTree(sha);
  // Deliberately read credentials only after explicit execution and source verification.
  const receipt=await runNemotron(fixture,{apiKey:process.env.NVIDIA_API_KEY});
  try { verifySourceTree(sha); }
  catch { receipt.status='failed'; receipt.error={code:'source-changed-during-run'}; delete receipt.result; }
  receipt.source={commit:sha,localCleanPinVerifiedAtStart:true,localCleanPinVerifiedAtEnd:receipt.error?.code!=='source-changed-during-run',origin:'SalesSquad/junction-pets',
    qualification:'Local Git checks; no hosted, signed or authenticated host qualification.'};
  console.log(JSON.stringify(receipt,null,2));
  if(receipt.status!=='completed') process.exitCode=1;
}
main(process.argv.slice(2)).catch(error=>{
  const allowed=new Set(['invalid-cli-arguments','source-commit-required']);
  console.error(JSON.stringify({status:'failed',error:{code:allowed.has(error?.message)?error.message:'source-verification-failed'},hostVerification:'unverified'}));
  process.exitCode=1;
});
