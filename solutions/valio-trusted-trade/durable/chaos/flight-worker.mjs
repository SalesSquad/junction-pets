/** Dedicated bounded WAL worker, with intentional DB-disconnect EventEmitter guards. */
import pg from 'pg';
import {settleDemoPayment,refundDemoPayment} from '../index.mjs';
import {guardPgPool,wirePgError} from './pg-faults.mjs';

const schema=process.env.VALIO_LAB_SCHEMA;
const connectionString=process.env.VALIO_TEST_DATABASE_URL;
if(!schema||!connectionString||!process.send)
  throw new Error('WAL worker requires IPC and an isolated run-owned PG schema/socket.');

let expectedCrash=false;
const unexpectedFaults=[];
const pool=guardPgPool(new pg.Pool({connectionString,max:2,connectionTimeoutMillis:8000}),{
  expectedCrash:()=>expectedCrash,
  onFault:fault=>{
    if(!fault.expected)unexpectedFaults.push(fault);
    process.send?.({pgFault:fault,pid:process.pid});
  }
});
process.send({ready:true,pid:process.pid});

process.on('message',async ({taskId,control,kind,terms,crashAfterCommit=false})=>{
  if(control==='expectCrash'){
    if(unexpectedFaults.length){
      process.send?.({taskId,error:{code:'UNEXPECTED_PG_FAULT_BEFORE_CRASH'},pid:process.pid});
    } else {
      expectedCrash=true;
      process.send?.({taskId,controlAck:'expectCrash',pid:process.pid});
    }
    return;
  }
  try {
    if(unexpectedFaults.length)throw Object.assign(new Error('Unexpected PostgreSQL connection fault'),{code:'UNEXPECTED_PG_FAULT'});
    const fn=kind==='pay'?settleDemoPayment:kind==='refund'?refundDemoPayment:null;
    if(!fn)throw Object.assign(new Error('Unsupported synthetic worker operation'),{code:'BAD_WORKER_OPERATION'});
    const result=await fn(pool,{schema,...terms});
    if(crashAfterCommit)process.exit(42); // Server COMMIT complete, NO caller ACK.
    process.send?.({taskId,result,pid:process.pid});
  }catch(error){
    process.send?.({taskId,error:wirePgError(error),pid:process.pid});
  }
});
process.on('disconnect',async()=>{await pool.end();});
