/**
 * Deterministic, non-production multi-process PostgreSQL chaos harness.
 * TEST ONLY: no real money, no external order, no sponsor credentials.
 * Usage: VALIO_TEST_DATABASE_URL=postgres://... node smoke.mjs [request-count]
 */
import {fork} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import pg from 'pg';
import {fileURLToPath} from 'node:url';
import {createLabSchema,seedAccounts,auditLab} from './index.mjs';

const workerPath=fileURLToPath(new URL('./worker.mjs',import.meta.url));
const sha='a'.repeat(64);
const proposal='b'.repeat(64);
const pay=(orderId,idempotencyKey,amountCents,supplierId='farm-a')=>({
  kind:'pay',terms:{orderId,idempotencyKey,buyerAccount:'demo:buyer:wallet',
    totalCents:amountCents,allocations:[{supplierId,amountCents}],
    verifiedQuoteBodyDigest:sha,approvedProposalDigest:proposal}
});
const refund=(orderId,idempotencyKey)=>({kind:'refund',terms:{orderId,idempotencyKey}});
const assert=(cond,message)=>{if(!cond)throw new Error(message);};

async function startWorker(connectionString,schema) {
  const child=fork(workerPath,{env:{...process.env,VALIO_TEST_DATABASE_URL:connectionString,VALIO_LAB_SCHEMA:schema},
    stdio:['ignore','ignore','inherit','ipc']});
  let next=0;const pending=new Map();
  let readyResolve,readyReject;
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
  const failAll=error=>{readyReject(error);for(const {reject} of pending.values())reject(error);pending.clear();};
  child.on('message',m=>{
    if(m.ready) {readyResolve(m.pid);return;}
    const job=pending.get(m.taskId);if(!job)return;
    pending.delete(m.taskId);
    job.resolve(m.error?{error:m.error,pid:m.pid}:{result:m.result,pid:m.pid});
  });
  child.once('error',failAll);
  child.once('exit',(code,signal)=>failAll(Object.assign(new Error(`Worker exited ${code}/${signal}`),{exitCode:code})));
  await ready;
  return {pid:child.pid,child,call:(task)=>new Promise((resolve,reject)=>{
    const taskId=++next;pending.set(taskId,{resolve,reject});child.send({...task,taskId},error=>{
      if(error){pending.delete(taskId);reject(error);}
    });
  }),stop:()=>{child.disconnect();}};
}

export async function runChaosLab({connectionString,requestCount=400,workerCount=8,keepSchema=false}={}) {
  if(!connectionString)throw new Error('BLOCKED: supply disposable VALIO_TEST_DATABASE_URL (no production DB).');
  if(!Number.isSafeInteger(requestCount)||requestCount<0||requestCount>10_000)
    throw new Error('Request count must be 0..10000.');
  if(!Number.isSafeInteger(workerCount)||workerCount<2||workerCount>8)
    throw new Error('Expected 2–8 distinct OS worker processes.');
  const schema=`j26_${randomBytes(10).toString('hex')}`;
  const admin=new pg.Pool({connectionString,max:2,connectionTimeoutMillis:8000});
  let workers=[];let schemaCreated=false;
  const t0=performance.now();
  try {
    await createLabSchema(admin,schema);schemaCreated=true;
    await seedAccounts(admin,{schema,buyerFundsCents:250_000,suppliers:['farm-a','farm-b','farm-c']});
    workers=await Promise.all(Array.from({length:workerCount},()=>startWorker(connectionString,schema)));
    assert(new Set(workers.map(w=>w.pid)).size===workerCount,'Workers must have distinct OS PIDs.');

    // Two independent signed-intent fixtures compete for 250,000 synthetic cents.
    // At most one 150,000-cent order can commit; both cannot overdraw.
    const races=await Promise.all([workers[0].call(pay('race_A','race_payment_A_0001',150_000)),
      workers[1].call(pay('race_B','race_payment_B_0001',150_000))]);
    assert(races.filter(x=>x.result?.status==='SIMULATED_SETTLED').length===1,'Race must settle exactly once.');
    assert(races.filter(x=>x.error?.code==='INSUFFICIENT_DEMO_FUNDS').length===1,'Losing order must be refused.');
    const winner=races.find(x=>x.result)?.result.orderId;
    const returned=await workers[0].call(refund(winner,'race_refund_0000001'));
    assert(returned.result?.status==='SIMULATED_REFUNDED','Winner refund failed.');

    // Intentionally kill one worker AFTER actual COMMIT but BEFORE the IPC ACK.
    const crashTask=pay('crash_A','crash_payment_00001',50_000,'farm-b');
    let observedCrash=false;
    try { await workers[2].call({...crashTask,crashAfterCommit:true}); }
    catch(e) { observedCrash=e.exitCode===42; }
    assert(observedCrash,'Fault hook must kill worker at post-commit/pre-ACK.');
    const recovered=await workers[3].call(crashTask);
    assert(recovered.result?.idempotentReplay===true,'Crash recovery must replay same durable result.');

    // 100 distinct orders and refunds, followed by mixed concurrent requests.
    const orders=Array.from({length:100},(_,i)=>({
      orderId:`case_${String(i).padStart(3,'0')}`,
      payKey:`case_payment_${String(i).padStart(4,'0')}`,
      refundKey:`case_refund_${String(i).padStart(4,'0')}`,
      amount:700,
      supplier:['farm-a','farm-b','farm-c'][i%3]
    }));
    let cursor=0;
    async function batched(tasks,accept) {
      for(let offset=0;offset<tasks.length;offset+=workerCount*2) {
        const chunk=tasks.slice(offset,offset+workerCount*2);
        const outcomes=await Promise.all(chunk.map(task=>{
          const worker=workers[(cursor++)%workers.length];
          if(worker.child.exitCode!==null)throw new Error('Unexpected dead worker in batch.');
          return worker.call(task);
        }));
        outcomes.forEach((out,i)=>accept?.(out,chunk[i]));
      }
    }
    // Avoid the intentionally dead worker in subsequent operations.
    workers=workers.filter(w=>w.child.exitCode===null);
    cursor=0;
    await batched(orders.map(o=>pay(o.orderId,o.payKey,o.amount,o.supplier)),o=>
      assert(o.result?.status==='SIMULATED_SETTLED','A distinct seeded payment must commit.'));
    await batched(orders.map(o=>refund(o.orderId,o.refundKey)),o=>
      assert(o.result?.status==='SIMULATED_REFUNDED','A distinct seeded refund must commit.'));
    let allowedReplays=0,refusals=0;
    const tasks=Array.from({length:requestCount},(_,i)=>{
      const o=orders[(i*37)%orders.length];
      switch(i%5) {
        case 0: return pay(o.orderId,o.payKey,o.amount,o.supplier);
        case 1: return refund(o.orderId,o.refundKey);
        case 2: return pay(o.orderId,o.payKey,o.amount+1,o.supplier); // conflict after canonicalization
        case 3: return pay(o.orderId,`alt_payment_${i}_x`,o.amount,o.supplier);
        default:return refund(o.orderId,`alt_refund_${i}_x`);
      }
    });
    await batched(tasks,out=>{
      if(out.result?.idempotentReplay)allowedReplays++;
      else if(['IDEMPOTENCY_CONFLICT','ORDER_ALREADY_SETTLED','ORDER_ALREADY_REFUNDED','AMOUNT_MISMATCH'].includes(out.error?.code))refusals++;
      else throw new Error(`Unexpected mixed response: ${JSON.stringify(out)}`);
    });
    const a=await auditLab(admin,schema);
    assert(a.balanced&&a.matching&&a.nonnegative,'Persistent ledger invariant failed.');
    assert(a.orders===102 && a.refunds===101,'Unexpected duplicate settlement or refund.');
    assert(a.batches===203 && a.outboxEvents===203,'Ledger/outbox must record each actual commit exactly once.');
    const elapsedMs=Math.round(performance.now()-t0);
    return {runId:schema,workersStarted:workerCount,independentOsPids:workerCount,
      requests:requestCount+205, mixedRequests:requestCount,allowedReplays,refusals,
      postCommitCrashObserved:true,crashReplayed:true,elapsedMs,
      verified:{balanced:a.balanced,matching:a.matching,nonnegative:a.nonnegative,
        exactlyOneRaceWinner:true,committedOrders:a.orders,refunds:a.refunds,
        batches:a.batches,outboxEvents:a.outboxEvents},
      limits:'Fictional preverified mandates, disposable PostgreSQL lab; no payment provider, real buyer identity or external exactly-once delivery.'};
  } finally {
    for(const w of workers){if(w.child.connected)w.stop();}
    // The caller owns the schema lifecycle when evidence persistence is requested.
    if(schemaCreated&&!keepSchema) {
      const safe=`"${schema}"`;
      try {await admin.query(`DROP SCHEMA ${safe} CASCADE`);} catch { /* preserve original error */ }
    }
    await admin.end();
  }
}

if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const args=process.argv.slice(2);let n=400,workers=8,keepSchema=false;
  for(let i=0;i<args.length;i++) {
    if(args[i]==='--requests' && args[i+1]) n=Number(args[++i]);
    else if(args[i]==='--workers' && args[i+1]) workers=Number(args[++i]);
    else if(args[i]==='--keep-schema') keepSchema=true;
    else if(i===0 && /^\d+$/.test(args[i])) n=Number(args[i]);
    else throw new Error(`Unknown option: ${args[i]}`);
  }
  try {
    const report=await runChaosLab({connectionString:process.env.VALIO_TEST_DATABASE_URL,requestCount:n,
      workerCount:workers,keepSchema:keepSchema||process.env.VALIO_LAB_KEEP_SCHEMA==='true'});
    console.log(JSON.stringify(report,null,2));
  }catch(e){console.error(JSON.stringify({status:'FAIL_OR_BLOCKED',code:e.code||null,message:e.message}));process.exitCode=1;}
}
