import test from 'node:test';
import assert from 'node:assert/strict';
import {auditInterruptedFlights} from '../flight-outcomes.mjs';

const workers=()=>Array.from({length:8},(_,i)=>({pid:1000+i,child:{signalCode:'SIGKILL'}}));
const interrupted=()=>Array.from({length:8},()=>({status:'rejected',
  reason:Object.assign(new Error('Owned test worker stopped: SIGKILL'),{exitSignal:'SIGKILL'})}));

test('eight owned SIGKILL interruptions are accepted, with exact count',()=>{
  assert.deepEqual(auditInterruptedFlights(interrupted(),workers()),
    {committed:0,disconnects:0,killedWorkers:8});
});

test('a known connection termination response during server kill is accepted',()=>{
  const outcomes=interrupted();outcomes[3]={status:'fulfilled',value:{error:{code:'08006',message:'Connection terminated unexpectedly'}}};
  assert.deepEqual(auditInterruptedFlights(outcomes,workers()),
    {committed:0,disconnects:1,killedWorkers:7});
});

test('completed first-time COMMIT during race is accepted, but a replay is not',()=>{
  const outcomes=interrupted();outcomes[0]={status:'fulfilled',value:{result:{status:'SIMULATED_SETTLED',idempotentReplay:false}}};
  assert.equal(auditInterruptedFlights(outcomes,workers()).committed,1);
  outcomes[0].value.result.idempotentReplay=true;
  assert.throws(()=>auditInterruptedFlights(outcomes,workers()),/FLIGHT_UNEXPECTED_SQL_RESULT/);
});

test('injected unrelated SQL 42P01 during verified kill is refused, not replay-classified',()=>{
  const outcomes=interrupted();outcomes[4]={status:'fulfilled',value:{error:{code:'42P01',message:'relation missing'}}};
  assert.throws(()=>auditInterruptedFlights(outcomes,workers()),/FLIGHT_UNEXPECTED_SQL_RESULT: flight 4, code 42P01/);
});

test('unverified child death, arbitrary IPC rejection, missing and duplicate outcomes all refuse qualification',()=>{
  const outcomes=interrupted(),owned=workers();
  owned[2].child.signalCode='SIGTERM';
  assert.throws(()=>auditInterruptedFlights(outcomes,owned),/FLIGHT_UNEXPECTED_REJECTION: flight 2/);
  owned[2].child.signalCode='SIGKILL';
  outcomes[1]={status:'rejected',reason:Object.assign(new Error('broken'),{code:'42P01'})};
  assert.throws(()=>auditInterruptedFlights(outcomes,owned),/FLIGHT_UNEXPECTED_REJECTION: flight 1, code 42P01/);
  assert.throws(()=>auditInterruptedFlights(outcomes.slice(1),owned),/FLIGHT_OUTCOME_COUNT/);
});

test('IPC channel closure requires verified owned SIGKILL, never a generic event',()=>{
  const outcomes=interrupted(),owned=workers();
  outcomes[5]={status:'rejected',reason:Object.assign(new Error('channel closed'),{code:'ERR_IPC_CHANNEL_CLOSED'})};
  assert.equal(auditInterruptedFlights(outcomes,owned).killedWorkers,8);
  owned[5].child.signalCode=null;
  assert.throws(()=>auditInterruptedFlights(outcomes,owned),/FLIGHT_UNEXPECTED_REJECTION: flight 5/);
});
