#!/usr/bin/env node
/** Read-only shadow experiment planner and authenticated provider evidence fetch. */
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {selectExperiments} from './adaptive-core.mjs';
import {fetchCraciEvidence} from './provider-proof.mjs';

async function main(argv = process.argv.slice(2)) {
  const [mode,...args] = argv;
  if (mode === 'plan' && args.length === 2) {
    const [manifestPath, logPath] = args;
    const [manifestRaw,history]=await Promise.all([
      readFile(manifestPath,'utf8'),readFile(logPath,'utf8').catch(err => {
        if (err.code === 'ENOENT') return '';throw err;
      }),
    ]);
    if (Buffer.byteLength(manifestRaw)>1024*1024) throw new Error('MANIFEST_TOO_LARGE');
    const plan=selectExperiments(JSON.parse(manifestRaw),history);
    process.stdout.write(JSON.stringify(plan,null,2)+'\n');
    return;
  }
  if (mode === 'provider' && args.length === 3) {
    const [jobId,runId,expectedHarnessSha]=args;
    const result=await fetchCraciEvidence({repository:'SalesSquad/junction-pets',jobId,runId,expectedHarnessSha},
      {token:process.env.CRACI_API_TOKEN});
    process.stdout.write(JSON.stringify(result,null,2)+'\n');
    return;
  }
  throw new Error('USAGE: adaptive-cli.mjs plan MANIFEST.json RECEIPTS.jsonl | provider JOB_ID RUN_ID HARNESS_SHA');
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href)
  main().catch(err => {console.error(String(err.message || err).slice(0,140));process.exitCode=1;});
