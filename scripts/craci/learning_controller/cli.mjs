#!/usr/bin/env node
/** Offline only. No network, GitHub writes, worker creation or dispatch. */
import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {compileCycle, sha} from './core.mjs';

async function main(argv=process.argv.slice(2)) {
  const flags={};
  for(let i=0;i<argv.length;i+=2){
    const key=argv[i];
    if(!key?.startsWith('--') || !argv[i+1] || flags[key])throw new Error('INVALID_ARGUMENTS');
    flags[key]=argv[i+1];
  }
  const required=['--pins','--training','--transitions','--manifest','--qualification',
    '--replay','--readout','--receipt','--candidate-commit','--candidate-weights','--out'];
  if(required.some(k=>!flags[k]) || Object.keys(flags).some(k=>![...required,'--prior'].includes(k)))
    throw new Error('USAGE: cli.mjs --pins PINS.json --training TRAINING.json --transitions FULL.jsonl.gz --manifest MANIFEST.json --qualification QUALIFICATION.json --replay POSITIVE_REPLAY.json --readout PAIRED_READOUT.json --receipt RECEIPT.json --candidate-commit SHA40 --candidate-weights SHA256 --out NEW.json [--prior PREVIOUS.json]');
  const pins=JSON.parse(await readFile(flags['--pins'],'utf8'));
  const paths={training:flags['--training'],transitions:flags['--transitions'],
    manifest:flags['--manifest'],qualification:flags['--qualification'],
    replay:flags['--replay'],readout:flags['--readout'],receipt:flags['--receipt']};
  let nextSeedStart=515000;
  if(flags['--prior']) {
    const prior=JSON.parse(await readFile(flags['--prior'],'utf8'));
    if(prior.schema!=='junction.craci.learning-controller.v1.evidence-cycle' ||
       prior.activationState!=='ADVISORY_NO_DISPATCH_NO_MODEL_PROMOTION' ||
       prior.input?.rawSha256?.training===pins.sha256?.training ||
       prior.input?.sourceSha===pins.sourceSha ||
       !Number.isInteger(prior.next?.proposedProspective?.nextTrainSeedStart))
      throw new Error('PRIOR_NOT_DISTINCT_OR_NOT_SOURCE_BOUND');
    nextSeedStart=prior.next.proposedProspective.nextTrainSeedStart+512;
  }
  const cycle=await compileCycle(paths,pins,{
    candidateCommit:flags['--candidate-commit'],
    candidateWeightsSha:flags['--candidate-weights'],nextSeedStart});
  if(flags['--prior'])cycle.priorCycleSha256=sha(await readFile(flags['--prior']));
  const output=JSON.stringify(cycle,null,2)+'\n';
  await writeFile(flags['--out'],output,{flag:'wx',mode:0o600});
  process.stdout.write(JSON.stringify({report:flags['--out'],reportSha256:sha(Buffer.from(output)),
    evidenceSha256:cycle.input.rawSha256.training,verdict:cycle.observation.scienceVerdict,
    pairedWorlds:cycle.observation.paired.worlds,
    nextTrainSeedStart:cycle.next.proposedProspective.nextTrainSeedStart,
    dispatchAuthorized:false,modelPromotionAuthorized:false})+'\n');
}

if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)
  main().catch(err=>{process.stderr.write(`CRACI_LEARNING_CONTROLLER_STOP ${String(err.message||err).slice(0,180)}\n`);process.exitCode=2;});
