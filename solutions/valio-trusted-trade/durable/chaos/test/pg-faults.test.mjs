import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {guardPgPool,isExpectedCrashDisconnect} from '../pg-faults.mjs';

test('checked-out Client error is observed, not an unhandled fatal EventEmitter event',()=>{
  const pool=new EventEmitter(),client=new EventEmitter(),faults=[];
  let expecting=false;
  guardPgPool(pool,{expectedCrash:()=>expecting,onFault:x=>faults.push(x)});
  pool.emit('connect',client);
  client.emit('error',new Error('Connection terminated unexpectedly'));
  assert.deepEqual(faults[0],{origin:'client',code:'UNKNOWN',expected:false});
  expecting=true;
  client.emit('error',new Error('Connection terminated unexpectedly'));
  pool.emit('error',Object.assign(new Error('server closed the connection unexpectedly'),{code:'08006'}));
  assert.equal(faults[1].expected,true);assert.equal(faults[2].expected,true);
});
test('even during crash boundary arbitrary SQL/provider errors remain unexpected',()=>{
  const pool=new EventEmitter(),faults=[];
  guardPgPool(pool,{expectedCrash:()=>true,onFault:x=>faults.push(x)});
  pool.emit('error',Object.assign(new Error('relation does not exist'),{code:'42P01'}));
  assert.equal(faults[0].expected,false);
  assert.equal(isExpectedCrashDisconnect({code:'42P01',message:'relation missing'}),false);
  assert.equal(isExpectedCrashDisconnect({code:'57P01'}),true);
});
