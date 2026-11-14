#!/usr/bin/env node
/** Source-bound real WAL crash/recovery chaos qualification on disposable CRACI PG. */
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {mkdir,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';

const exec=promisify(execFile);
const SOURCE='d7a20d8d5ce47157e6d42348de73c64e347ef3a7';
const fail=code=>{throw new Error(code)};
const root=resolve(process.env.CRACI_SOURCE_ROOT||'');
const output=resolve(process.env.CRACI_RECEIPT_DIR||'', 'artifacts','valio-wal');
await mkdir(output,{recursive:false});
let report=null;
try {
  if (process.env.CRACI_SOURCE_SHA!==SOURCE) fail('EXPECTED_SOURCE_SHA_MISMATCH');
  const {stdout:gitHead}=await exec('git',['-C',root,'rev-parse','HEAD'],{timeout:15000});
  if(gitHead.trim()!==SOURCE)fail('UNEXPECTED_GIT_SOURCE');
  const durable=join(root,'solutions','valio-trusted-trade','durable');
  const {stdout,stderr}=await exec('node',[
    'chaos/wal-lab.mjs','--allow-kill9','--workers','8','--requests','10000',
    '--seed','20261114','--max-minutes','23'],
    {cwd:durable,timeout:24*60*1000,maxBuffer:2*1024*1024});
  if(stderr.trim())console.error(stderr.slice(-1000).replaceAll(/socket:[^\s]+/g,'[private-socket]'));
  report=JSON.parse(stdout);
  await writeFile(join(output,'raw-result.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  const v=report.verification||{}, c=report.cluster||{}, w=c.walRecoverySignals||{},
    r=report.recovery||{}, t=report.workload||{};
  const checks={
    source_pin:report.sourceSha===SOURCE,
    simulated_only:report.simulatedOnly===true,
    unique_intents:t.requests===10000&&t.orders===5000&&/^[a-f0-9]{64}$/.test(t.planDigest||''),
    postmaster_isolated:c.isolated===true&&c.firstPostmasterPid!==c.restartedPostmasterPid,
    actual_sigkill:c.signal==='SIGKILL'&&c.workerPreAckCrash===true,
    pg_durable:c.serverFsync===true&&c.synchronousCommit===true&&c.fullPageWrites===true,
    wal_redo:w.interrupted===true&&w.redo===true&&w.accepting===true,
    replay_anchor:r.priorConfirmedCommits===2&&r.ambiguousCommittedNoAck===1&&r.replayedFlightIntents===8,
    replay_integrity:r.ordersAfterFlightResolution===11&&r.allFourTamperRefusals===true,
    real_workers:c.originalWorkerPids===8&&c.postCrashWorkerPids===8,
    state_changing_10k:v.uniqueStateChangingRequests===10000&&v.committedOrders===5011&&v.refundedOrders===5000,
    exact_outbox:v.ledgerBatches===10011&&v.outboxEvents===10011,
    balanced:v.balanced===true&&v.balancesMatchLedger===true&&v.noNegativeBalances===true,
  };
  const passed=Object.values(checks).every(Boolean)&&report.status==='PASS';
  const qualification={schema:'junction.valio.wal.craci.qualification.v1',
    source_sha:SOURCE,status:passed?'passed':'failed',checks,
    actual_postgres_version:report.postgresVersion||null,
    elapsedMs:report.elapsedMs??null,
    limits:'10k fictional state changes and one owned PG WAL recovery; no banking or external delivery'};
  await writeFile(join(output,'qualification.json'),JSON.stringify(qualification,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify(qualification));
  if(!passed)process.exitCode=1;
}catch(error){
  const failure={schema:'junction.valio.wal.craci.qualification.v1',
    source_sha:SOURCE,status:'failed_or_blocked',
    error_code:/^[A-Z_]{4,80}$/.test(error.message||'')?error.message:'WAL_LAB_EXECUTION_FAILED',
    exit_code:error.code??null};
  await writeFile(join(output,'failed.json'),JSON.stringify(failure,null,2)+'\n',{flag:'wx'});
  console.error(JSON.stringify(failure));
  process.exitCode=1;
}
