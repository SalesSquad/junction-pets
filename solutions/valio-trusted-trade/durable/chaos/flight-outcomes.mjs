/**
 * Narrow result classifier for all eight *distinct* in-flight WAL transactions.
 * An SQL exception is NOT evidence of an interrupted server crash merely
 * because it was observed near an intentionally killed postmaster.
 */
import {isExpectedCrashDisconnect} from './pg-faults.mjs';

export function auditInterruptedFlights(outcomes,workers,{expected=8}={}){
  if(!Array.isArray(outcomes)||outcomes.length!==expected||
     !Array.isArray(workers)||workers.length<1)
    throw new Error(`FLIGHT_OUTCOME_COUNT: require ${expected} settled flight results and their owned workers.`);
  const counts={committed:0,disconnects:0,killedWorkers:0};
  for(let i=0;i<outcomes.length;i++){
    const outcome=outcomes[i],owned=workers[i%workers.length];
    if(!owned?.child)throw new Error(`FLIGHT_OUTCOME_UNOWNED: flight ${i}.`);
    if(outcome?.status==='fulfilled'){
      const response=outcome.value;
      if(response?.result?.status==='SIMULATED_SETTLED'&&response.result?.idempotentReplay===false){
        counts.committed++;continue;
      }
      if(response?.error&&isExpectedCrashDisconnect(response.error)){
        counts.disconnects++;continue;
      }
      const code=String(response?.error?.code||'INVALID_SUCCESS');
      throw new Error(`FLIGHT_UNEXPECTED_SQL_RESULT: flight ${i}, code ${code}; refusing WAL qualification.`);
    }
    if(outcome?.status==='rejected'){
      const reason=outcome.reason||{};
      const ownedKilled=owned.child.signalCode==='SIGKILL';
      if(ownedKilled&&(reason.exitSignal==='SIGKILL'||reason.code==='ERR_IPC_CHANNEL_CLOSED')){
        counts.killedWorkers++;continue;
      }
      const code=String(reason.code||reason.exitSignal||reason.exitCode||'UNKNOWN');
      throw new Error(`FLIGHT_UNEXPECTED_REJECTION: flight ${i}, code ${code}; refusing WAL qualification.`);
    }
    throw new Error(`FLIGHT_MISSING_SETTLEMENT: flight ${i}; refusing WAL qualification.`);
  }
  if(counts.committed+counts.disconnects+counts.killedWorkers!==expected)
    throw new Error('FLIGHT_OUTCOME_SUM: not all eight responses classified exactly once.');
  return counts;
}
