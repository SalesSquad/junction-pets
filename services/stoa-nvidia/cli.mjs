#!/usr/bin/env node
import {execFileSync} from 'node:child_process';
import {realpathSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {prepareStoaDrawingTask,runStoaNvidiaDrawing} from './index.mjs';
import {drawingFixture} from './fixture.mjs';
import {MODEL,drawingRequestDigest,LIMITS,validateDrawingRequest} from '../nemotron-vl/index.mjs';

const ROOT=realpathSync(fileURLToPath(new URL('../../',import.meta.url)));
const TRACKED=['services/stoa-nvidia/index.mjs','services/stoa-nvidia/cli.mjs','services/stoa-nvidia/fixture.mjs',
 'services/nemotron-vl/index.mjs','services/nemotron-vl/synthetic-worksheet.png','pets/nvidia/comparability.mjs',
 'pets/nvidia/pet.json','pets/nvidia/AGENTS.md','pets/stoa/pet.json','pets/stoa/AGENTS.md'];
const ORIGINS=new Set(['https://github.com/SalesSquad/junction-pets.git','git@github.com:SalesSquad/junction-pets.git']);
function verifySource(sha) {
 const git=(...args)=>execFileSync('git',args,{cwd:ROOT,encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:5000,maxBuffer:1000000}).trim();
 if(realpathSync(git('rev-parse','--show-toplevel'))!==ROOT||git('rev-parse','HEAD')!==sha||
  !ORIGINS.has(git('remote','get-url','origin'))||git('status','--porcelain=v1','--untracked-files=normal'))throw Error('source-verification-failed');
 for(const path of TRACKED)git('ls-files','--error-unmatch','--',path);
}
async function main(args) {
 let execute=false,sourceCommit=null,stdin=false;
 for(let i=0;i<args.length;i++) {
  if(args[i]==='--execute'&&!execute)execute=true;
  else if(args[i]==='--source-commit'&&!sourceCommit&&/^[a-f0-9]{40}$/.test(args[i+1]??''))sourceCommit=args[++i];
  else if(args[i]==='--stdin'&&!stdin)stdin=true;
  else throw Error('invalid-cli-arguments');
 }
 if(stdin&&!execute)throw Error('invalid-cli-arguments');
 if(!execute) {
  const r=drawingFixture();console.log(JSON.stringify({mode:'plan-only',actor:'junction.stoa',recipient:'junction.nvidia',
   capabilityId:'drawing-observation',requestedModel:MODEL,sourceCommit,requestDigest:drawingRequestDigest(r),
   source:r.source,regions:r.regions.map(({id,imageSha256,bounds})=>({id,imageSha256,bounds})),
   workflow:['stoa-source-bound-request','nvidia-drawing-observation','nvidia-same-model-review','stoa-region-validation'],
   networkRequests:0,secretReads:0,hostVerification:'unverified',
   limitations:['Authored synthetic worksheet, not a sponsor drawing.','No provider call or authenticated collaboration.']},null,2));return;
 }
 if(!sourceCommit)throw Error('source-commit-required');
 verifySource(sourceCommit);
 let request=drawingFixture();
 if(stdin) {
  let text='';for await(const chunk of process.stdin){text+=chunk;if(Buffer.byteLength(text)>LIMITS.bodyBytes)throw Error('invalid-input');}
  try {request=validateDrawingRequest(JSON.parse(text));}catch{throw Error('invalid-input');}
 }
 const task=prepareStoaDrawingTask(request,{sourceCommit});
 const receipt=await runStoaNvidiaDrawing(task,{apiKey:process.env.NVIDIA_API_KEY});
 try {verifySource(sourceCommit);}catch{receipt.status='failed';receipt.error={code:'source-changed-during-run'};delete receipt.result;delete receipt.outputDigest;}
 receipt.source={commit:sourceCommit,localCleanPinVerifiedAtStart:true,
  localCleanPinVerifiedAtEnd:receipt.error?.code!=='source-changed-during-run',
  qualification:'Local source checks, not signed host attestation.'};
 console.log(JSON.stringify(receipt,null,2));
 if(!['candidate','abstained'].includes(receipt.status))process.exitCode=1;
}
main(process.argv.slice(2)).catch(error=>{
 const allowed=new Set(['invalid-cli-arguments','source-commit-required','invalid-input']);
 console.error(JSON.stringify({status:'failed',error:{code:allowed.has(error?.message)?error.message:'source-verification-failed'},hostVerification:'unverified'}));
 process.exitCode=1;
});
