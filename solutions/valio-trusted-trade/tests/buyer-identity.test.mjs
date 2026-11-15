/** Injected verifier tests: policy/HTTP/persistence, not cryptographic qualification. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { request as httpRequest } from 'node:http';
import { mkdtemp, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createTradeHttpServer, createPersistentTradeServer } from '../src/server.mjs';
import { createTradeService } from '../src/core.mjs';
import { createBuyerIdentity } from '../src/buyer-identity.mjs';

const issuer = 'https://host-fixture.invalid';
const BUYER = 'helsinki-hotel-demo';
const need = { family: 'dairy-milk', quantityLitres: 1000, lactoseFree: true, deliverBy: '2026-11-16' };
async function fixture({ persistent = true, afterVerify, stateFile: supplied } = {}) {
  let now = Date.now(), serial = 0, accesses = 0;
  const records = new Map();
  const grants = [
    { subject: 'fixture-agent', buyerId: BUYER, ownerScope: 'kitchen-a', principalType: 'AGENT', active: true, revision: 1,
      actions: ['read','prepare','commit','cancel','relay_decision'], maxOrderCents: 250000 },
    { subject: 'fixture-reviewer', buyerId: BUYER, ownerScope: 'kitchen-a', principalType: 'HUMAN', active: true, revision: 1,
      actions: ['read','approve','pay'], maxOrderCents: 250000 },
    { subject: 'fixture-other-agent', buyerId: BUYER, ownerScope: 'kitchen-b', principalType: 'AGENT', active: true, revision: 1,
      actions: ['read','prepare','commit','cancel','relay_decision'], maxOrderCents: 250000 },
  ];
  const token = (subject = 'fixture-agent', extra = {}) => {
    const raw = 'fixture-assertion-' + ++serial;
    records.set(raw, { iss: issuer, sub: subject, iat: Math.floor(now/1000), exp: Math.floor(now/1000)+600, ...extra }); return raw;
  };
  const verifier = { async verifyAccessToken(raw) { accesses++; if (!records.has(raw)) throw Error('unverified'); const value = structuredClone(records.get(raw)); afterVerify?.(grants); return value; },
    async verifyDecisionProof(raw) { if (!records.has(raw)) throw Error('unverified'); return structuredClone(records.get(raw)); } };
  const identity = createBuyerIdentity({ profileId: 'test-host-v1', issuer, verifier, grants: () => grants, clock: () => now });
  const directory = await mkdtemp('/private/tmp/valio-identity-');
  const stateFile = supplied ?? join(directory, 'state.sqlite');
  let server, base;
  const start = async () => {
    server = persistent ? createPersistentTradeServer({ stateFile, clock: () => now, identity }) :
      createTradeHttpServer(createTradeService({ clock: () => now }), { identity });
    server.listen(0,'127.0.0.1'); await once(server,'listening'); base = 'http://127.0.0.1:' + server.address().port;
  };
  const stop = async () => { if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); server = null; } };
  await start();
  const request = async (path, { method, body, bearer, proof, key, headers = {} } = {}) => {
    const r = await fetch(base + path, { method: method ?? (body === undefined ? 'GET' : 'POST'),
      headers: { 'Content-Type':'application/json', ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}),
        ...(proof ? { 'X-Buyer-Decision-Proof':proof } : {}), ...(key ? { 'Idempotency-Key':key } : {}), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body) });
    return { status:r.status, body:await r.json() };
  };
  const prepare = async (bearer, key = 'fixture-prepare-key-1') => {
    const r = await request('/api/agent/prepare', { bearer, key, body:{ buyerId:BUYER, requirements:[need], budgetCents:140000 } });
    assert.equal(r.status,201,JSON.stringify(r.body)); return r.body;
  };
  const decision = async (run, bearer, extra = {}) => {
    const { body: scope } = await request('/api/identity/decision-context?quoteId=' + run.quote.id + '&action=QUOTE_DECISION', { bearer });
    const raw = token('fixture-reviewer', { exp:Math.floor(now/1000)+120, jti:'decision-' + ++serial,
      ...scope, reviewerGrantRevision:grants[1].revision, decision:'approve', ...extra });
    return raw;
  };
  return { request, prepare, decision, token, grants, records, stateFile, start, stop, identity,
    setNow:value=>{now=value;}, get now(){return now;}, get accesses(){return accesses;}, get base(){return base;} };
}

test('host identity denies anonymous mint, forged identity/proxy fields and unsigned model approval', async () => {
  const f = await fixture();
  try {
    assert.equal((await f.request('/api/identity/configuration')).body.anonymousSessionMinting,false);
    assert.throws(()=>createTradeHttpServer(createTradeService(),{identity:f.identity}),{code:'HOST_PERSISTENCE_REQUIRED'});
    assert.equal((await f.request('/api/demo/session',{body:{buyerId:BUYER}})).status,401);
    assert.equal((await f.request('/api/quotes/Q-DEMO-1')).status,401);
    const access = f.token(), run = await f.prepare(access);
    const me = await f.request('/api/identity/me',{bearer:access});
    assert.equal(me.body.mode,'HOST_AUTHENTICATED');
    assert.equal(JSON.stringify(me.body).includes('fixture-agent'),false);
    const fake = await f.request('/api/agent/runs/' + run.run.id + '/decision',{bearer:access,key:'unsigned-decision-key',
      body:{buyerId:BUYER,quoteId:run.quote.id,snapshotId:run.quote.snapshotId,decision:'approve'},
      headers:{'X-User-Role':'human','X-Authenticated-User':'admin'}});
    assert.equal(fake.body.error.code,'HOST_DECISION_REQUIRED');
    const falseBuyer = await f.request('/api/agent/prepare',{bearer:access,key:'forged-buyer-key',
      body:{buyerId:'forged-buyer',requirements:[need],budgetCents:140000,role:'human'}});
    assert.equal(falseBuyer.status,403);
    const humanToken = f.token('fixture-reviewer');
    assert.equal((await f.request('/api/agent/runs/' + run.run.id + '/decision',{bearer:humanToken,key:'human-no-proof-key',
      body:{buyerId:BUYER,quoteId:run.quote.id,snapshotId:run.quote.snapshotId,decision:'approve'}})).body.error.code,'HOST_DECISION_REQUIRED');
    assert.equal((await f.request('/api/audit',{bearer:access})).status,403);
  } finally { await f.stop(); }
});

test('rotated tokens retain exact owner, unrelated scope cannot read any private resource or replay', async () => {
  const f = await fixture();
  try {
    const access=f.token(), run=await f.prepare(access), rotated=f.token(), other=f.token('fixture-other-agent');
    assert.equal((await f.prepare(rotated)).run.id,run.run.id);
    for (const path of ['/api/quotes/'+run.quote.id,'/api/quotes/'+run.quote.id+'/body','/api/quotes/'+run.quote.id+'/proof',
      '/api/agent/runs/'+run.run.id]) {
      assert.equal((await f.request(path,{bearer:rotated})).status,200);
      assert.equal((await f.request(path,{bearer:other})).status,403);
    }
    f.grants[0].active=false;
    assert.equal((await f.request('/api/agent/prepare',{bearer:rotated,key:'fixture-prepare-key-1',
      body:{buyerId:BUYER,requirements:[need],budgetCents:140000}})).body.error.code,'IDENTITY_REVOKED');
  } finally { await f.stop(); }
});

test('exact signed-host decision is atomic and replay safe; cross-action/source/amount/reviewer/nonces refuse', async () => {
  const f = await fixture();
  try {
    const access=f.token(), run=await f.prepare(access);
    const input={buyerId:BUYER,quoteId:run.quote.id,snapshotId:run.quote.snapshotId,decision:'approve'};
    for (const wrong of [{totalCents:1},{quoteId:'Q-foreign'},{snapshotId:'foreign'},{ownerRef:'owner-foreign'},
      {action:'PAYMENT_DECISION'},{sub:'fixture-agent'},{reviewerGrantRevision:999},{decision:'reject'},
      {quoteBodyDigest:'unbound'},{exp:Math.floor(f.now/1000)-1}]) {
      const proof=await f.decision(run,access,wrong);
      assert.equal((await f.request('/api/agent/runs/'+run.run.id+'/decision',{bearer:access,key:'wrong-proof-'+Math.random().toString(36).slice(2),proof,body:input})).status,wrong.exp?401:403);
    }
    const proof=await f.decision(run,access);
    const send=()=>f.request('/api/agent/runs/'+run.run.id+'/decision',{bearer:access,key:'exact-host-decision-key',proof,body:input});
    const first=await send();assert.equal(first.status,200,JSON.stringify(first));assert.equal(first.body.quote.status,'APPROVED');
    const replay=await send();assert.deepEqual(replay.body,first.body);
    assert.equal((await f.request('/api/agent/runs/'+run.run.id+'/decision',{bearer:access,key:'different-command-key',proof,body:input})).body.error.code,'HOST_DECISION_REPLAY');
    f.grants[1].active=false;
    assert.equal((await send()).status,403,'revoked reviewer must fail even for successful cached command');
  } finally { await f.stop(); }
});

test('expiry and grant revision are rechecked after verification and before cached success', async () => {
  const f=await fixture();
  try {
    const access=f.token(), run=await f.prepare(access);
    f.grants[0].revision++;
    assert.equal((await f.request('/api/agent/runs/'+run.run.id,{bearer:access})).status,200,'fresh resolution sees current operator revision');
    f.setNow(f.now+601000);
    assert.equal((await f.request('/api/agent/prepare',{bearer:access,key:'fixture-prepare-key-1',
      body:{buyerId:BUYER,requirements:[need],budgetCents:140000}})).status,401);
    assert.equal((await f.request('/api/identity/me',{bearer:f.token('unknown-subject')})).status,403);
  } finally {await f.stop();}
});

test('persistent identity profile survives restart without raw host credentials and refuses mode adoption', async () => {
  const f=await fixture({persistent:true});
  try {
    const access=f.token(), run=await f.prepare(access), proof=await f.decision(run,access);
    const body={buyerId:BUYER,quoteId:run.quote.id,snapshotId:run.quote.snapshotId,decision:'approve'};
    assert.equal((await f.request('/api/agent/runs/'+run.run.id+'/decision',{bearer:access,proof,key:'persistent-host-decision',body})).status,200);
    await f.stop();await f.start();
    assert.equal((await f.request('/api/agent/runs/'+run.run.id,{bearer:f.token()})).body.quote.status,'APPROVED');
    assert.equal((await f.request('/api/agent/runs/'+run.run.id+'/decision',{bearer:f.token(),proof,key:'persistent-host-decision',body})).status,200);
    await f.stop();
    assert.throws(()=>createPersistentTradeServer({stateFile:f.stateFile}),{code:'IDENTITY_STATE_PROFILE_MISMATCH'});
    const bytes=await readFile(f.stateFile);
    for (const prohibited of [access,proof,'fixture-agent','fixture-reviewer']) assert.equal(bytes.includes(Buffer.from(prohibited)),false);
  } finally {await f.stop();}
});


test('revocation during a real delayed request body refuses before domain write', async () => {
  let markVerified;
  const verified=new Promise(resolve=>{markVerified=resolve;});
  const f=await fixture({afterVerify:()=>markVerified()});
  try {
    const access=f.token();
    const body=JSON.stringify({buyerId:BUYER,requirements:[need],budgetCents:140000});
    const result=new Promise((resolve,reject)=>{
      const req=httpRequest(f.base+'/api/agent/prepare',{method:'POST',headers:{'Content-Type':'application/json',
        Authorization:'Bearer '+access,'Idempotency-Key':'delayed-body-command'}},res=>{
        const chunks=[];res.on('data',chunk=>chunks.push(chunk));res.on('end',()=>resolve({status:res.statusCode,body:JSON.parse(Buffer.concat(chunks).toString())}));
      });
      req.on('error',reject);req.flushHeaders();req.write(body.slice(0,1));
      void verified.then(async()=>{await new Promise(done=>setTimeout(done,30));f.grants[0].active=false;req.end(body.slice(1));});
    });
    const refused=await result;assert.equal(refused.status,403);assert.equal(refused.body.error.code,'IDENTITY_REVOKED');
    f.grants[0].active=true;f.grants[0].revision++;f.grants[0].actions.push('audit');
    const audit=await f.request('/api/audit',{bearer:f.token()});
    assert.equal(audit.body.receipts.some(value=>['QUOTE_CREATED','REVIEW_CREATED'].includes(value.event)),false);
  } finally {await f.stop();}
});
