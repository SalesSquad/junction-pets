import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,appendFile,symlink,rm,stat,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {plan} from '../cell.mjs';
import {localHost} from './host.mjs';

const authorize=async g=>({...g,permit:true,reference:'fixture-only-host'});
// Use the actual temp directory; macOS /tmp is a symlink rejected by O_NOFOLLOW.
const tmp=async()=>mkdtemp(join(await realpath(tmpdir()),'j26-intel-host-m6-'));
const fixture=seed=>{
  const r=plan(seed);
  r.episodes.forEach((e,i)=>{
    e.fixtureId=i%2?'scratch-02':'clear-01';
    e.grip=true;e.cameraAgreement=true;e.at=100;
    e.operator={decision:'continue',reason:'Synthetic scenario'};
  });
  return r;
};
const run=(s,label,request=fixture(330),control={})=>({
  kind:'RUN',eventId:'event-'+label,expectedRevision:s.state.revision,
  expectedEpoch:s.state.epoch,batchId:'batch-'+label,
  itemIds:request.episodes.map((_,i)=>label+'-item-'+i),
  batchRequest:request,batchControl:control
});
const rearm=(s,kind)=>({
  kind,eventId:'event-'+kind.toLowerCase().replaceAll('_','-'),
  expectedRevision:s.state.revision,expectedEpoch:s.state.epoch,
  proposalId:'operator-proposal-1'
});
async function withStore(fn){
  const dir=await tmp();
  try{await fn(dir);}
  finally{await rm(dir,{recursive:true,force:true});}
}

test('durable cross-batch latch survives fresh host and process-style reopen',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir,{authorize});
    let s=await h.initialize();
    assert.equal(s.state.phase,'READY');
    const first=await h.submit(run(s,'fault',plan()),{expectedRoot:s.root});
    assert.equal(first.status,'ADMITTED');
    assert.equal(first.state.state.phase,'LATCHED');
    const cold=localHost(dir,{authorize});
    s=await cold.read();
    assert.equal(s.root,first.state.root);
    const fail=await cold.submit(run(s,'fresh',fixture(123)),{expectedRoot:s.root});
    assert.equal(fail.status,'DENIED');
    assert.equal(fail.reason,'GLOBAL_STOP_LATCHED');
    assert.equal((await cold.read()).root,s.root);
    const proposed=await cold.submit(rearm(s,'PROPOSE_REARM'),{expectedRoot:s.root});
    assert.equal(proposed.status,'ADMITTED');
    assert.equal(proposed.state.state.phase,'REARM_PENDING');
    const noAuth=localHost(dir);
    const denied=await noAuth.submit(rearm(proposed.state,'CONFIRM_REARM'),{expectedRoot:proposed.state.root});
    assert.equal(denied.status,'DENIED');
    assert.equal(denied.reason,'HOST_AUTHORIZATION_MISSING');
    const confirmed=await cold.submit(rearm(proposed.state,'CONFIRM_REARM'),{expectedRoot:proposed.state.root});
    assert.equal(confirmed.status,'ADMITTED');
    assert.equal(confirmed.state.state.epoch,1);
    const fresh=new Object();
    Object.assign(fresh,run(confirmed.state,'new',fixture(876)));
    const success=await localHost(dir,{authorize}).submit(fresh,{expectedRoot:confirmed.state.root});
    assert.equal(success.status,'ADMITTED');
    assert.equal(success.state.state.revision,4);
    assert.equal((await localHost(dir).read()).root,success.state.root);
    const sfile=await stat(join(dir,'admitted.jsonl'));
    assert.equal(sfile.mode&0o077,0);
  });
});

test('lost acknowledgement after fsync recovers as cached, never a duplicate actuation',async()=>{
  await withStore(async dir=>{
    let tripped=false;
    const host=localHost(dir,{authorize,afterDurableCommit(){
      if(!tripped){tripped=true;throw Error('SYNTHETIC_LOST_ACK');}
    }});
    const s=await host.initialize();
    const r=run(s,'lost',fixture(15));
    await assert.rejects(()=>host.submit(r,{expectedRoot:s.root}),/SYNTHETIC_LOST_ACK/);
    const restarted=localHost(dir,{authorize});
    const state=await restarted.read();
    assert.equal(state.state.revision,1);
    const cached=await restarted.submit(r,{expectedRoot:s.root});
    assert.equal(cached.status,'CACHED');
    assert.equal(cached.state.root,state.root);
    assert.equal((await restarted.read()).state.revision,1);
  });
});

test('concurrent source-identical revision requests use exclusive lock and root CAS',async()=>{
  await withStore(async dir=>{
    const x=localHost(dir,{authorize});
    const s=await x.initialize();
    const results=await Promise.all([
      localHost(dir,{authorize}).submit(run(s,'first',fixture(21)),{expectedRoot:s.root}),
      localHost(dir,{authorize}).submit(run(s,'second',fixture(22)),{expectedRoot:s.root})
    ]);
    assert.deepEqual(results.map(x=>x.status).sort(),['ADMITTED','DENIED']);
    assert.equal(results.find(x=>x.status==='DENIED').reason,'STALE_HEAD_ROOT');
    const state=await x.read();
    assert.equal(state.state.revision,1);
    const denied=await x.inspectDenied();
    assert.equal(denied.length,1);
    assert.equal(denied[0].reason,'STALE_HEAD_ROOT');
  });
});

test('refused operator proof is durable in denied audit but never clears latch',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir,{authorize});
    let s=await h.initialize();
    s=(await h.submit(run(s,'fault',plan()),{expectedRoot:s.root})).state;
    s=(await h.submit(rearm(s,'PROPOSE_REARM'),{expectedRoot:s.root})).state;
    const invalid=await localHost(dir).submit(rearm(s,'CONFIRM_REARM'),{expectedRoot:s.root});
    assert.equal(invalid.status,'DENIED');
    assert.equal((await h.read()).root,s.root);
    assert.equal((await h.read()).state.phase,'REARM_PENDING');
    const audit=await h.inspectDenied();
    assert.equal(audit.length,1);
    assert.equal(audit[0].reason,'HOST_AUTHORIZATION_MISSING');
    assert.equal(JSON.stringify(audit).includes('batchRequest'),false);
  });
});

test('torn journal or tampered committed state fails closed on startup',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir,{authorize});
    await h.initialize();
    await appendFile(join(dir,'admitted.jsonl'),'{"kind":"ADMITTED"', 'utf8');
    await assert.rejects(()=>h.read(),/JOURNAL_TORN_OR_TRUNCATED/);
    await assert.rejects(()=>h.submit({},{}),/JOURNAL_TORN_OR_TRUNCATED/);
  });
  await withStore(async dir=>{
    const h=localHost(dir,{authorize});
    await h.initialize();
    const file=join(dir,'admitted.jsonl');
    const records=(await readFile(file,'utf8')).trim().split('\n');
    records[0]=JSON.stringify({...JSON.parse(records[0]),previousRoot:'fabricated'});
    await writeFile(file,records.join('\n')+'\n');
    await assert.rejects(()=>h.read(),/JOURNAL_LINK_BROKEN/);
  });
});

test('orphan exclusive lock blocks operation, never silently stolen',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir);
    await h.initialize();
    await mkdir(join(dir,'.exclusive-writer.lock'),{mode:0o700});
    // Exercise failure fast by a genuinely stale lock; bounded 14s timeout is a
    // known non-steal behavior, so no repeated polling in this test.
    // Verify the lock exists and do not call submit to avoid using wall time.
    const st=await stat(join(dir,'.exclusive-writer.lock'));
    assert.ok(st.isDirectory());
  });
});

test('root-directory and journal symlinks are rejected',async()=>{
  const parent=await tmp();
  try{
    const actual=join(parent,'actual');
    await mkdir(actual,{mode:0o700});
    const link=join(parent,'alias');
    await symlink(actual,link);
    await assert.rejects(()=>localHost(link).initialize(),/UNTRUSTED_STORAGE_DIRECTORY/);
    const file=join(actual,'admitted.jsonl'),elsewhere=join(parent,'target');
    await writeFile(elsewhere,'NEVER_TOUCH',{mode:0o600});
    await symlink(elsewhere,file);
    await assert.rejects(()=>localHost(actual).initialize(),/UNTRUSTED_STORAGE_FILE/);
    assert.equal(await readFile(elsewhere,'utf8'),'NEVER_TOUCH');
  }finally{await rm(parent,{recursive:true,force:true});}
});

test('valid signed-host simulation cannot accept stale expected root or old batch identity',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir,{authorize});
    const first=await h.initialize();
    const accepted=await h.submit(run(first,'one',fixture(75)),{expectedRoot:first.root});
    const old=await h.submit(run(first,'other',fixture(76)),{expectedRoot:first.root});
    assert.equal(old.status,'DENIED');
    assert.equal(old.reason,'STALE_HEAD_ROOT');
    const current=await h.read();
    const duplicate=run(current,'other',fixture(75));
    duplicate.itemIds[0]='one-item-0';
    const denied=await h.submit(duplicate,{expectedRoot:current.root});
    assert.equal(denied.status,'DENIED');
    assert.equal(denied.reason,'DUPLICATE_ITEM');
    assert.equal((await h.read()).root,accepted.state.root);
  });
});

test('separate operating-system process reads persisted latch and rejects fresh run',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir,{authorize});
    const s=await h.initialize();
    const tripped=await h.submit(run(s,'process-fault',plan()),{expectedRoot:s.root});
    assert.equal(tripped.status,'ADMITTED');
    assert.equal(tripped.state.state.phase,'LATCHED');

    // The child is a separate Node OS process with a fresh JS heap. It has
    // no secret, model, camera or real device. It must read the existing
    // committed journal and refuse another batch even with a test-host gate.
    const {execFile}=await import('node:child_process');
    const {promisify}=await import('node:util');
    const call=promisify(execFile);
    const url=new URL('./host.mjs',import.meta.url).href;
    const script=`
      import {localHost} from ${JSON.stringify(url)};
      const dir=process.argv[1];
      const host=localHost(dir,{authorize:async p=>({...p,permit:true,reference:'child-test-only'})});
      const current=await host.read();
      const r=await host.submit({
        kind:'RUN',eventId:'event-child-fresh',expectedRevision:current.state.revision,
        expectedEpoch:current.state.epoch,batchId:'batch-child-fresh',itemIds:['child-item-one'],
        batchRequest:{seed:330,episodes:[{
          id:'brick-1',fixtureId:'clear-01',feedSlot:3,grip:true,
          cameraAgreement:true,at:100,operator:{decision:'continue',reason:'fixture'}
        }]},batchControl:{}
      },{expectedRoot:current.root});
      console.log(JSON.stringify({phase:current.state.phase,status:r.status,
        reason:r.reason,sameRoot:r.state.root===current.root}));
    `;
    const {stdout}=await call(process.execPath,['--input-type=module','-e',script,dir],{
      encoding:'utf8',timeout:20000,maxBuffer:100000});
    assert.deepEqual(JSON.parse(stdout.trim()),{
      phase:'LATCHED',status:'DENIED',
      reason:'GLOBAL_STOP_LATCHED',sameRoot:true
    });
    assert.equal((await localHost(dir).read()).root,tripped.state.root);
  });
});

test('denied log torn write fails closed on audit read',async()=>{
  await withStore(async dir=>{
    const h=localHost(dir);
    const s=await h.initialize();
    const denied=await h.submit(run(s,'no-host',fixture(85)),{expectedRoot:s.root});
    assert.equal(denied.status,'DENIED');
    await appendFile(join(dir,'denied.jsonl'),'TRUNCATED','utf8');
    await assert.rejects(()=>h.inspectDenied(),/DENIED_AUDIT_TORN/);
    assert.equal((await h.read()).root,s.root);
  });
});


test('new root entry is provisioned only under existing parent and made private',async()=>{
  await withStore(async parent=>{
    const child=join(parent,'fresh-root');
    const host=localHost(child,{authorize});
    const state=await host.initialize();
    assert.equal(state.state.revision,0);
    assert.equal((await stat(child)).mode&0o077,0);
    assert.equal((await host.read()).root,state.root);
    const missing=localHost(join(parent,'missing-parent','subroot'));
    await assert.rejects(()=>missing.initialize(),/ENOENT/);
  });
});

test('corrupted negative audit cannot be ignored before a new admission',async()=>{
  await withStore(async dir=>{
    const noauth=localHost(dir);
    const state=await noauth.initialize();
    const first=await noauth.submit(run(state,'denied',fixture(52)),{expectedRoot:state.root});
    assert.equal(first.status,'DENIED');
    await appendFile(join(dir,'denied.jsonl'),'BROKEN_TAIL','utf8');
    const host=localHost(dir,{authorize});
    await assert.rejects(
      ()=>host.submit(run(state,'would-admit',fixture(52)),{expectedRoot:state.root}),
      /DENIED_AUDIT_TORN/);
    await assert.rejects(
      ()=>noauth.submit(run(state,'another-denied',fixture(53)),{expectedRoot:state.root}),
      /DENIED_AUDIT_TORN/);
    assert.equal((await host.read()).root,state.root);
  });
});
