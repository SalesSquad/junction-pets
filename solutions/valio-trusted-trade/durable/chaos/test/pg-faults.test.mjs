import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {guardPgPool,isExpectedCrashDisconnect,wirePgError} from '../pg-faults.mjs';

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

test('hostile SQLSTATE 42P01 overrides spoofed connection-terminated prose',()=>{
  const hostile={code:'42P01',message:'Connection terminated unexpectedly'};
  assert.equal(isExpectedCrashDisconnect(hostile),false);
  assert.equal(isExpectedCrashDisconnect(wirePgError(hostile)),false);
});

test('all supported transport SQLSTATE and socket codes qualify, not arbitrary codes',()=>{
  const allowed=['57P01','57P02','57P03','08000','08001','08003','08006','08P01',
    'ECONNRESET','EPIPE','ECONNREFUSED','ENOENT'];
  for(const code of allowed)assert.equal(isExpectedCrashDisconnect({code,message:'bogus'}),true,code);
  for(const code of ['42P01','23505','23514','40001','40P01','22000','28P01','XX000','P0001','UNEXPECTED'])
    assert.equal(isExpectedCrashDisconnect({code,message:'Connection terminated unexpectedly'}),false,code);
});

test('source-independent SQLSTATE fuzz never accepts unknown codes via spoofed message',()=>{
  const known=new Set(['57P01','57P02','57P03','08000','08001','08003','08006','08P01']);
  let examined=0;
  for(const prefix of ['00','01','02','03','08','09','10','22','23','28','40','42','55','57','58','XX']){
    for(let n=0;n<127;n++){
      const code=`${prefix}${n.toString(36).toUpperCase().padStart(3,'0')}`;
      if(known.has(code))continue;
      assert.equal(isExpectedCrashDisconnect({code,message:'Connection terminated unexpectedly'}),false,code);
      examined++;
    }
  }
  assert(examined>=2000);
});

test('missing code keeps true node-postgres disconnect distinguishable from fabricated SQLSTATE',()=>{
  const actual=wirePgError(new Error('Connection terminated unexpectedly'));
  assert.equal(actual.code,null);
  assert.equal(isExpectedCrashDisconnect(actual),true);
  assert.equal(isExpectedCrashDisconnect({code:'UNEXPECTED',message:actual.message}),false);
});
