/** Distinct OS-process worker, sharing ONLY a disposable PostgreSQL lab schema. */
import pg from 'pg';
import {settleDemoPayment,refundDemoPayment} from './index.mjs';

const schema=process.env.VALIO_LAB_SCHEMA;
const connectionString=process.env.VALIO_TEST_DATABASE_URL;
if (!schema || !connectionString || !process.send) {
  throw new Error('Worker requires IPC, explicit disposable schema and VALIO_TEST_DATABASE_URL.');
}
const pool=new pg.Pool({connectionString,max:2,connectionTimeoutMillis:8000});
process.send({ready:true,pid:process.pid});
process.on('message',async ({taskId,kind,terms,crashAfterCommit=false})=>{
  try {
    const fn=kind==='pay'?settleDemoPayment:kind==='refund'?refundDemoPayment:null;
    if(!fn) throw new Error('Unsupported synthetic operation');
    const result=await fn(pool,{schema,...terms});
    // Fault point: durable COMMIT has returned, the caller has received no ACK.
    if(crashAfterCommit) process.exit(42);
    process.send?.({taskId,result,pid:process.pid});
  } catch(error) {
    process.send?.({taskId,error:{code:error.code||'UNEXPECTED',message:String(error.message)},pid:process.pid});
  }
});
process.on('disconnect',async()=>{await pool.end();});
