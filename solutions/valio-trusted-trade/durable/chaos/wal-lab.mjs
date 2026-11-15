/**
 * WAL SIGKILL/recovery test for the NON-PRODUCTION Valio demo ledger.
 * Owns its PostgreSQL cluster, socket, PGDATA and child Node processes.
 */
import {fork} from 'node:child_process';
import {randomBytes,createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import pg from 'pg';
import {createLabSchema,seedAccounts,auditLab} from '../index.mjs';
import {payment,refund,createWalWorkload,flightApplicationNames} from './plan.mjs';
import {createOwnedCluster,startOwnedCluster,sigkillOwnedPostmaster,
  recoverySignals,closeOwnedCluster} from './cluster.mjs';
import {captureOwnedPgFailure,redactPgLine} from './forensics.mjs';
import {guardPgPool} from './pg-faults.mjs';
import {auditInterruptedFlights} from './flight-outcomes.mjs';

const workerPath=fileURLToPath(new URL('./flight-worker.mjs',import.meta.url));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const assert=(good,reason)=>{if(!good)throw new Error(reason);};
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');

async function spawnOwnedWorker(dsn,schema) {
  const child=fork(workerPath,{env:{...process.env,
    VALIO_TEST_DATABASE_URL:dsn,VALIO_LAB_SCHEMA:schema},
    stdio:['ignore','ignore','inherit','ipc']});
  let serial=0,readyResolve,readyReject;
  const pending=new Map(),faults=[];
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
  const rejectAll=err=>{readyReject(err);for(const p of pending.values())p.reject(err);pending.clear();};
  child.on('message',m=>{
    if(m.pgFault){faults.push(m.pgFault);return;}
    if(m.ready){readyResolve(m.pid);return;}
    const p=pending.get(m.taskId);if(!p)return;pending.delete(m.taskId);
    p.resolve(m.error?{error:m.error,pid:m.pid}:m.controlAck?{controlAck:m.controlAck,pid:m.pid}:{result:m.result,pid:m.pid});
  });
  child.once('error',rejectAll);
  child.once('exit',(code,signal)=>{
    const err=Object.assign(new Error(`Owned test worker stopped: ${code??signal}`),
      {exitCode:code,exitSignal:signal});
    rejectAll(err);
  });
  await ready;
  return {pid:child.pid,child,faults,
    call:task=>new Promise((resolve,reject)=>{
      const taskId=++serial;pending.set(taskId,{resolve,reject});
      child.send({...task,taskId},err=>{if(err){pending.delete(taskId);reject(err);}});
    }),
    kill:()=>{if(child.exitCode===null)try{child.kill('SIGKILL');}catch{}},
    stop:()=>{if(child.connected)child.disconnect()}
  };
}

async function pump(tasks,workers,{deadline,expect,counts}={}) {
  for(let offset=0;offset<tasks.length;offset+=workers.length){
    if(Date.now()>deadline)throw new Error(`TIME_BUDGET_EXCEEDED: ${offset}/${tasks.length} completed; no qualification claim.`);
    const batch=tasks.slice(offset,offset+workers.length);
    const result=await Promise.all(batch.map((task,i)=>workers[i].call(task)));
    result.forEach((r,i)=>{
      if(r.error)throw new Error(`Unexpected PostgreSQL outcome: ${r.error.code||'UNKNOWN'} for ${batch[i].kind}`);
      if(r.result?.status!==expect||r.result?.idempotentReplay)
        throw new Error(`Expected first immutable ${expect}, observed unexpected replay/status.`);
      counts.processed++;
    });
  }
}

async function installPauseTrigger(pool,schema){
  // This intentionally pauses ONLY the eight new test orders at a rollback-safe
  // point in the current transaction. The trigger itself is durable DDL.
  const q=`"${schema}"`;
  const marker=`j26wal_${schema.slice(4)}_`;
  // Set a backend-local marker from NEW.order_id *inside* this exact trigger.
  // Parameterized INSERT SQL exposes $1..$4 in pg_stat_activity.query, so this
  // is the only honest link from a waiting PID to its exact flight fixture.
  flightApplicationNames(schema);
  await pool.query(`CREATE FUNCTION ${q}.wal_pause() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.order_id LIKE 'wal_flight_%' THEN
    PERFORM set_config('application_name','${marker}' || NEW.order_id,true);
    PERFORM pg_sleep(8);
  END IF;
  RETURN NEW;
END $$`);
  await pool.query(`CREATE TRIGGER wal_fault_pause BEFORE INSERT ON ${q}.ledger_batches
FOR EACH ROW EXECUTE FUNCTION ${q}.wal_pause()`);
}

async function removePauseTrigger(pool,schema){
  const q=`"${schema}"`;
  await pool.query(`DROP TRIGGER wal_fault_pause ON ${q}.ledger_batches`);
  await pool.query(`DROP FUNCTION ${q}.wal_pause()`);
}

async function waitForInFlightDbWork(pool,schema,maxMs=6000){
  const expected=new Set(flightApplicationNames(schema));
  const limit=Date.now()+maxMs;
  let best=0,correctSql=0;
  while(Date.now()<limit){
    const {rows}=await pool.query("SELECT pid,application_name,query,state,wait_event FROM pg_stat_activity WHERE state='active' AND wait_event='PgSleep'");
    const matches=rows.filter(r=>expected.has(r.application_name));
    const sqlMatches=matches.filter(r=>/INSERT\s+INTO\s+ledger_batches\s*\(\s*batch_id\s*,\s*order_id\s*,\s*kind\s*,\s*intent_digest\s*\)/i.test(r.query||''));
    best=Math.max(best,matches.length);correctSql=Math.max(correctSql,sqlMatches.length);
    const pids=new Set(sqlMatches.map(r=>r.pid));
    const markers=new Set(sqlMatches.map(r=>r.application_name));
    if(pids.size===8&&markers.size===8&&[...expected].every(m=>markers.has(m)))
      return {count:8,pids:[...pids].sort((a,b)=>a-b),matchedFlightIds:markers.size,queryMatched:true};
    await wait(60);
  }
  throw new Error(`NO_8_FLIGHTS: expected eight distinct, schema-bound PgSleep backend PIDs on exact INSERT; observed markers ${best}/8 and matching SQL ${correctSql}/8. Refused SIGKILL.`);
}

async function assertWalSeals(pool,schema,orderId){
  const q=`"${schema}"`;
  const {rows:[batch]}=await pool.query(`SELECT batch_id FROM ${q}.ledger_batches WHERE order_id=$1 AND kind='SIMULATED_PAYMENT'`,[orderId]);
  assert(batch,'Expected recovered durable ledger batch for negative controls.');
  const refuse=async(sql,params,label)=>{
    let got='NO_ERROR';
    try{await pool.query(sql,params);}catch(e){got=e.code||'UNKNOWN';}
    assert(got==='23514',`${label} must be refused by PostgreSQL seal trigger (SQLSTATE ${got}).`);
  };
  await refuse(`DELETE FROM ${q}.ledger_outbox WHERE batch_id=$1`,[batch.batch_id],'Outbox DELETE');
  await refuse(`UPDATE ${q}.ledger_outbox SET event_kind='WRONG' WHERE batch_id=$1`,[batch.batch_id],'Outbox mutation');
  await refuse(`TRUNCATE TABLE ${q}.ledger_outbox`,[],'Outbox TRUNCATE');
  await refuse(`INSERT INTO ${q}.ledger_entries(batch_id,account_id,delta_cents) VALUES ($1,$2,1)`,
    [batch.batch_id,'demo:supplier:farm-c:wallet'],'Post-COMMIT unbalanced append');
  return true;
}

export async function runWalChaos({requests=10000,seed=20261114,workerCount=8,
  maxMinutes=23,allowKill9=false,keepData=false}={}) {
  if(!allowKill9)throw new Error('STOP: explicit --allow-kill9 required for a disposable isolated PostgreSQL cluster.');
  if(!Number.isInteger(workerCount)||workerCount<3||workerCount>8)throw new Error('Workers must be 3..8.');
  if(!Number.isFinite(maxMinutes)||maxMinutes<5||maxMinutes>25)
    throw new Error('Bounded time budget must be 5..25 minutes.');
  const plan=createWalWorkload({requests,seed});
  const startedAt=new Date().toISOString(),deadline=Date.now()+maxMinutes*60_000;
  const t0=performance.now();
  let c=null,pool=null,workers=[],cleanup=null,failure=null,failureStage='INITDB';
  let controllerCrashExpected=false;
  const controllerPgFaults=[];
  const observedPool=dsn=>guardPgPool(new pg.Pool({connectionString:dsn,max:4,connectionTimeoutMillis:8000}),{
    expectedCrash:()=>controllerCrashExpected,
    onFault:fault=>controllerPgFaults.push(fault)
  });
  const facts={workId:'J26-VALIO-WAL-CHAOS-20261114',startedAt,
    simulatedOnly:true,sourceSha:process.env.CRACI_SOURCE_SHA||null,
    workload:{requests:plan.requests,orders:plan.orders,seed,planDigest:plan.planDigest}};
  try {
    c=await createOwnedCluster();
    failureStage='INITIAL_CLUSTER_START';
    const firstPid=await startOwnedCluster(c);
    pool=observedPool(c.dsn);
    const schema=`j26_${randomBytes(10).toString('hex')}`;
    await createLabSchema(pool,schema);
    await seedAccounts(pool,{schema,buyerFundsCents:2_000_000,
      suppliers:['farm-a','farm-b','farm-c']});
    workers=await Promise.all(Array.from({length:workerCount},()=>spawnOwnedWorker(c.dsn,schema)));
    failureStage='ACKNOWLEDGED_ANCHORS';
    assert(new Set(workers.map(w=>w.pid)).size===workerCount,'Initial workers are not distinct OS PIDs.');

    // Two acknowledged COMMITs must remain replayable after forced server death.
    const anchors=[
      payment('wal_anchor_A','wal_anchor_pay_A_0001',1000,[{supplierId:'farm-a',amountCents:1000}],seed),
      payment('wal_anchor_B','wal_anchor_pay_B_0001',1000,[{supplierId:'farm-b',amountCents:1000}],seed)
    ];
    const admitted=await Promise.all(anchors.map((t,i)=>workers[i].call(t)));
    assert(admitted.every(r=>r.result?.status==='SIMULATED_SETTLED'),
      'Two acknowledged durable anchor COMMITs required before kill-9.');

    // First kill ONE Node worker immediately after a third durable COMMIT.
    // The server stays alive; the response is genuinely ambiguous to caller.
    const ambiguous=payment('wal_ambiguous','wal_ambiguous_pay_0001',1000,
      [{supplierId:'farm-c',amountCents:1000}],seed);
    failureStage='WORKER_COMMIT_PRE_ACK_CRASH';
    let workerCrash=false;
    try{await workers[2].call({...ambiguous,crashAfterCommit:true});}
    catch(e){workerCrash=e.exitCode===42;}
    assert(workerCrash,'Required post-COMMIT/pre-ACK OS worker crash was not observed.');
    workers[2]=await spawnOwnedWorker(c.dsn,schema);

    // Eight genuinely in-flight SQL transactions will be terminated by a
    // SIGKILL of only our own verified postmaster and its verified children.
    failureStage='INSTALL_FLIGHT_TRIGGER';
    await installPauseTrigger(pool,schema);
    const flights=Array.from({length:8},(_,i)=>payment(`wal_flight_${i}`,
      `wal_flight_pay_${i}_0001`,500,[{supplierId:'farm-a',amountCents:500}],seed));
    const pending=flights.map((t,i)=>workers[i%workers.length].call(t));
    // Attach rejection handlers before the deliberate SIGKILL so Node never
    // mistakes expected abruptly closed IPC requests for unhandled promises.
    const interruptedOutcomes=Promise.allSettled(pending);
    failureStage='VERIFY_EIGHT_SOURCE_BOUND_FLIGHTS';
    const observedPgSleep=await waitForInFlightDbWork(pool,schema);
    // A checked-out pg Client has no pg-pool idle error listener. All eight
    // workers and the controller must explicitly enter the EXPECTED outage
    // boundary before the verified server SIGKILL, never globally suppressing
    // unrelated PostgreSQL/SQL errors.
    const crashAcks=await Promise.all(workers.map(w=>w.call({control:'expectCrash'})));
    assert(crashAcks.every(r=>r.controlAck==='expectCrash'),
      'A WAL worker did not acknowledge the narrow intentional disconnect boundary.');
    assert(workers.every(w=>w.faults.every(f=>f.expected)),
      'Unexpected PostgreSQL client error before authorized SIGKILL.');
    controllerCrashExpected=true;
    failureStage='SIGKILL_OWNED_POSTMASTER';
    const crash=await sigkillOwnedPostmaster(c);
    for(const w of workers)w.kill();
    const interrupted=await interruptedOutcomes;
    const interruptedFlightAudit=auditInterruptedFlights(interrupted,workers);
    const unexpectedFlightErrors=workers.flatMap(w=>w.faults.filter(f=>!f.expected));
    assert(unexpectedFlightErrors.length===0,'A flight worker reported non-disconnect PostgreSQL errors during SIGKILL.');
    workers=[];
    await pool.end();pool=null;
    controllerCrashExpected=false;
    assert(controllerPgFaults.every(f=>f.expected),
      'Controller pool had unrelated PostgreSQL client errors, not only intentional disconnects.');

    // The exact same PGDATA/WAL is restarted after an abnormal SIGKILL.
    failureStage='RESTART_SAME_PGDATA_WAL';
    const restartPid=await startOwnedCluster(c);
    assert(firstPid!==restartPid,'Postmaster PID did not change across SIGKILL/restart.');
    const signals=await recoverySignals(c);
    assert(signals.interrupted&&signals.redo&&signals.accepting,
      'WAL crash-recovery log evidence missing; not qualified.');
    pool=observedPool(c.dsn);
    failureStage='WAL_RECOVERY_INVARIANTS';
    const version=(await pool.query('SHOW server_version')).rows[0]?.server_version;
    const settings=(await pool.query("SELECT current_setting('fsync') AS fsync,current_setting('synchronous_commit') AS sync_commit,current_setting('full_page_writes') AS full_page_writes")).rows[0];
    assert(settings.fsync==='on'&&settings.sync_commit==='on'&&settings.full_page_writes==='on',
      'Required durable WAL storage settings were not active after recovery.');
    await removePauseTrigger(pool,schema);
    const before=await auditLab(pool,schema);
    assert(before.balanced&&before.matching&&before.nonnegative,'WAL recovery corrupted account/ledger invariants.');
    assert(before.orders>=3&&before.orders<=11,'Unexpected pre-replay WAL recovery settlement count.');
    assert(before.outboxEvents===before.batches,'Recovery lost/duplicated an outbox event.');
    failureStage='REPLAY_ACKNOWLEDGED_AND_AMBIGUOUS';
    workers=await Promise.all(Array.from({length:workerCount},()=>spawnOwnedWorker(c.dsn,schema)));
    assert(new Set(workers.map(w=>w.pid)).size===workerCount,'Recovery workers are not independent OS processes.');
    const replay=await Promise.all([...anchors,ambiguous].map((t,i)=>workers[i].call(t)));
    assert(replay.every(r=>r.result?.idempotentReplay===true),
      'Acknowledged or ambiguous committed operations must replay from WAL without new postings.');
    const unknown=await Promise.all(flights.map((t,i)=>workers[i%workers.length].call(t)));
    assert(unknown.every(r=>r.result?.status==='SIMULATED_SETTLED'),
      'Every interrupted flight must resolve to one durable settlement after replay.');
    const afterFlights=await auditLab(pool,schema);
    assert(afterFlights.orders===11&&afterFlights.batches===11&&afterFlights.outboxEvents===11,
      'Replayed flights created duplicate ledger/outbox rows or lost committed orders.');
    failureStage='RECOVERED_LEDGER_TAMPER_NEGATIVES';
    const tamperRefusals=await assertWalSeals(pool,schema,'wal_ambiguous');
    const afterTamper=await auditLab(pool,schema);
    assert(afterTamper.batches===afterFlights.batches&&afterTamper.outboxEvents===afterFlights.outboxEvents&&
      afterTamper.matching&&afterTamper.balanced,'WAL-era negative control modified recovered ledger.');

    // 10k are DISTINCT state-changing transactions (5k orders + 5k refunds),
    // not 10k repetitions of an unchanged passing tuple.
    const counts={processed:0};
    failureStage='UNIQUE_PAYMENT_PHASE';
    await pump(plan.pays,workers,{deadline,expect:'SIMULATED_SETTLED',counts});
    const midpoint=await auditLab(pool,schema);
    assert(midpoint.orders===plan.orders+11&&midpoint.balanced&&midpoint.matching&&midpoint.nonnegative,
      'Payment-phase ledger invariant/unique-order check failed.');
    failureStage='UNIQUE_REFUND_PHASE';
    await pump(plan.refunds,workers,{deadline,expect:'SIMULATED_REFUNDED',counts});
    failureStage='FINAL_DOUBLE_ENTRY_AND_OUTBOX_AUDIT';
    const final=await auditLab(pool,schema);
    const expected=11+plan.requests;
    assert(counts.processed===plan.requests,'Not all unique benchmark writes executed.');
    assert(final.orders===plan.orders+11&&final.refunds===plan.orders,
      'Unexpected completed order/refund totals.');
    assert(final.batches===expected&&final.outboxEvents===expected,
      'Exactly-once durable batch/outbox count does not match executed unique operations.');
    assert(final.balanced&&final.matching&&final.nonnegative,'Final persistent double-entry audit failed.');
    assert(controllerPgFaults.every(f=>f.expected) &&
      workers.every(w=>w.faults.every(f=>f.expected)),
      'Unexpected PostgreSQL EventEmitter client/pool errors occurred outside SIGKILL.');

    const report={...facts,status:'PASS',postgresVersion:version,
      cluster:{isolated:true,serverFsync:settings.fsync==='on',
        synchronousCommit:settings.sync_commit==='on',fullPageWrites:settings.full_page_writes==='on',
        firstPostmasterPid:firstPid,restartedPostmasterPid:restartPid,
        originalWorkerPids:workerCount,postCrashWorkerPids:workerCount,
        workerPreAckCrash:true,pgWaitEventObserved:'PgSleep',
        observedSleepingBackends:observedPgSleep.count,
        observedBackendPids:observedPgSleep.pids,
        matchedFlightIds:observedPgSleep.matchedFlightIds,
        insertQueryMatched:observedPgSleep.queryMatched,
        interruptedFlightAudit,
        handledExpectedPgDisconnectEvents:controllerPgFaults.filter(f=>f.expected).length,
        ...crash,walRecoverySignals:signals},
      recovery:{priorConfirmedCommits:2,ambiguousCommittedNoAck:1,
        recoveredOrdersBeforeReplay:before.orders,replayedFlightIntents:flights.length,
        ordersAfterFlightResolution:afterFlights.orders,allFourTamperRefusals:tamperRefusals},
      verification:{uniqueStateChangingRequests:counts.processed,
        committedOrders:final.orders,refundedOrders:final.refunds,
        ledgerBatches:final.batches,outboxEvents:final.outboxEvents,
        balanced:final.balanced,balancesMatchLedger:final.matching,
        noNegativeBalances:final.nonnegative},
      elapsedMs:Math.round(performance.now()-t0),
      limits:'Synthetic intent hashes only; no real signed mandates, money, supplier API, delivery, production host, or external exactly-once delivery.'};
    const log=await readFile(c.logFile);
    report.cluster.pgLogSha256=digest(log);
    return report;
  } catch(error) {
    failure=error;
    let forensic=null;
    if(c)try{forensic=await captureOwnedPgFailure(c.logFile);}catch{}
    console.error(JSON.stringify({event:'WAL_CHAOS_FAILURE_FORENSIC',
      workId:facts.workId,stage:failureStage,sourceSha:facts.sourceSha,
      errorCode:error.code||'UNCLASSIFIED',errorMessage:redactPgLine(error.message),
      testOwnedPgdata:c?.root||null,forensic}));
    throw error;
  } finally {
    for(const w of workers){w.kill();w.stop();}
    if(pool)try{await pool.end();}catch{}
    cleanup=await closeOwnedCluster(c,{keepData:keepData||Boolean(failure)});
    // Cleanup concerns only this run-created disposable cluster. The JSON receipt
    // is emitted by the CLI after cleanup; never print the socket URL/password.
    if(cleanup?.retained)console.error(JSON.stringify({event:'OWNED_TEST_DATA_RETAINED',
      path:cleanup.retained,reason:cleanup.reason}));
  }
}

function parseCli(args){
  const result={requests:10000,seed:20261114,workerCount:8,maxMinutes:23,allowKill9:false,keepData:false};
  for(let i=0;i<args.length;i++){
    const a=args[i];
    if(a==='--allow-kill9')result.allowKill9=true;
    else if(a==='--keep-data')result.keepData=true;
    else if(['--requests','--seed','--workers','--max-minutes'].includes(a)&&args[i+1]){
      const value=Number(args[++i]);
      result[{'--requests':'requests','--seed':'seed','--workers':'workerCount','--max-minutes':'maxMinutes'}[a]]=value;
    }else throw new Error(`Unsupported WAL lab option: ${a}`);
  }
  return result;
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{
    const args=parseCli(process.argv.slice(2));
    const output=await runWalChaos(args);
    console.log(JSON.stringify(output,null,2));
  }catch(error){
    console.error(JSON.stringify({status:'FAIL_OR_BLOCKED',code:error.code||null,message:error.message}));
    process.exitCode=1;
  }
}
