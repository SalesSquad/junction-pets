/**
 * Signed fictional EUR settlement race qualification across 1,000 independent
 * in-memory HTTP servers. No PSP, external network, bank or production identity.
 */
import assert from 'node:assert/strict';
import {generateKeyPairSync, randomUUID} from 'node:crypto';
import {once} from 'node:events';
import {writeFile, mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const SOURCE_SHA = 'd45f450a38ec6c8fb2f73b96d181454458ae3928';
const buyerId = 'helsinki-hotel-demo';
const args = process.argv.slice(2);
const value = (key) => {
  const pos = args.indexOf('--'+key);
  return pos < 0 ? undefined : args[pos+1];
};
const fixtures = Number(value('fixtures') ?? 1000);
const width = Number(value('width') ?? 32);
const seed = Number(value('seed') ?? 20261114);
if (![3,1000].includes(fixtures) || width !== 32 || seed !== 20261114)
  throw new Error('Fixed synthetic coverage grid only: 3-fixture smoke or 1,000-fixture final, width32 and seed20261114');
if (!process.env.CRACI_SOURCE_ROOT || !process.env.CRACI_SOURCE_SHA || !process.env.CRACI_RECEIPT_DIR)
  throw new Error('Pinned CRACI source/receipt context required');
assert.equal(process.env.CRACI_SOURCE_SHA, SOURCE_SHA);
const source = resolve(process.env.CRACI_SOURCE_ROOT, 'solutions/valio-trusted-trade/src');
const [
  {createTradeService, FIXTURE_CATALOG},
  {createTradeHttpServer},
  {signDemoEnvelope, makeDemoMandatePayload},
] = await Promise.all(['core.mjs','server.mjs','trust-envelope.mjs'].map(
  x => import(pathToFileURL(resolve(source,x)).href)));
const startTime = Date.now();
const outcomes = {
  schema:'craci.valio-http-concurrency.v1', source_sha:SOURCE_SHA,
  seed, fixtures, width,
  same_key_storms:0, distinct_key_storms:0, cancel_races:0,
  parallel_settlement_posts:0, parallel_cancel_posts:0,
  unapproved_payment_denials:0, tampered_term_denials:0,
  successful_original_settlements:0, idempotent_replays:0,
  duplicate_charge:0, journal_failures:0, nonzero_final_wallets:0,
  violation_count:0, no_real_money:true, no_external_calls:true,
};

async function fixture(i) {
  const service = createTradeService();
  const inventory = new Map(service.catalog().map(item => [item.sku, item.unitsAvailable]));
  const server = createTradeHttpServer(service);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = 'http://127.0.0.1:' + server.address().port;
  const call = async (path,payload,token) => {
    const r = await fetch(base+path,{
      method: payload===undefined?'GET':'POST',
      headers: token?{Authorization:'Bearer '+token}:{},
      body: payload===undefined?undefined:JSON.stringify(payload),
      signal:AbortSignal.timeout(20000)
    });
    return {status:r.status,...await r.json()};
  };
  try {
    const session = await call('/api/demo/session',{buyerId});
    assert.equal(session.status,201);
    const token = session.token;
    const {publicKey,privateKey} = generateKeyPairSync('ed25519');
    const jwk=publicKey.export({format:'jwk'});
    const registration=await call('/api/trust/buyer-key',{buyerId,publicJwk:{kty:jwk.kty,crv:jwk.crv,x:jwk.x}},token);
    assert.equal(registration.status,201);
    const plan=(await call('/api/plans',{buyerId,budgetCents:250000,requirements:[
      {family:'dairy-milk',lactoseFree:true,quantityLitres:100,deliverBy:'2026-11-16'},
      {family:'oat-drink',lactoseFree:true,quantityLitres:20,deliverBy:'2026-11-16'},
    ]},token)).plan;
    assert.ok(plan?.id);
    const quote=(await call('/api/plans/'+plan.id+'/quotes',{buyerId,optionId:'cost'},token)).quote;
    assert.ok(quote?.id);
    if(quote.approvalRequired)
      assert.equal((await call('/api/quotes/'+quote.id+'/approval',{buyerId,decision:'approve'},token)).status,200);
    const signedOffer=(await call('/api/quotes/'+quote.id+'/offer',{buyerId},token)).signedOffer;
    assert.ok(signedOffer);
    const signedMandate=signDemoEnvelope(privateKey,registration.kid,
      makeDemoMandatePayload({quote,signedOffer,now:Date.now(),nonce:randomUUID()}));
    const proof=await call('/api/quotes/'+quote.id+'/handshake',{buyerId,signedMandate},token);
    assert.equal(proof.status,201);
    assert.equal(proof.proof?.verification?.valid,true);
    const orderResponse=await call('/api/orders',{
      buyerId,quoteId:quote.id,idempotencyKey:'j26-stress-order-'+i},token);
    assert.equal(orderResponse.status,201);
    const order=orderResponse.order;
    assert.ok(order?.paymentEligible && order.totalCents>0);
    const settlePath='/api/orders/'+order.id+'/settlement';
    const cancelPath='/api/orders/'+order.id+'/cancel';
    const paymentPath='/api/orders/'+order.id+'/payment';
    const before=await call(settlePath,{buyerId,idempotencyKey:'j26-stress-noauth-'+i},token);
    assert.equal(before.status,403);
    assert.equal(before.error?.code,'PAYMENT_APPROVAL_REQUIRED');
    outcomes.unapproved_payment_denials++;
    const proposal=(await call(paymentPath,undefined,token)).proposal;
    assert.ok(proposal?.digest);
    const approval=await call('/api/orders/'+order.id+'/payment-approval',{
      buyerId,decision:'approve',proposalDigest:proposal.digest},token);
    assert.equal(approval.status,200);
    const illegal=await call(settlePath,{buyerId,idempotencyKey:'j26-stress-injected-'+i,amountCents:1},token);
    assert.equal(illegal.status,400);
    assert.equal(illegal.error?.code,'PAYMENT_TERMS_FORBIDDEN');
    outcomes.tampered_term_denials++;
    const kind=i%3;
    let first=0,replay=0;
    if(kind===0) {
      const key='j26-stress-same-'+i;
      const responses=await Promise.all(Array.from({length:width},()=>call(settlePath,{buyerId,idempotencyKey:key},token)));
      outcomes.parallel_settlement_posts+=width;
      first=responses.filter(x=>x.status===201&&x.idempotentReplay===false).length;
      replay=responses.filter(x=>x.status===201&&x.idempotentReplay===true).length;
      assert.equal(first,1);
      assert.equal(replay,width-1);
      outcomes.same_key_storms++;
    } else if(kind===1) {
      const responses=await Promise.all(Array.from({length:width},(_,j)=>call(settlePath,{
        buyerId,idempotencyKey:'j26-stress-distinct-'+i+'-'+j},token)));
      outcomes.parallel_settlement_posts+=width;
      first=responses.filter(x=>x.status===201&&x.idempotentReplay===false).length;
      assert.equal(first,1);
      assert.equal(responses.filter(x=>x.status===409&&x.error?.code==='PAYMENT_ALREADY_SETTLED').length,width-1);
      outcomes.distinct_key_storms++;
    } else {
      const attempts=Array.from({length:width},(_,j)=>j%2===0
        ? {type:'settle',key:'j26-stress-race-'+i}
        : {type:'cancel'});
      // Reproducible reversal of request start order across the synthetic fixture grid.
      if((seed+i)%2) attempts.reverse();
      const responses=await Promise.all(attempts.map(x=>x.type==='settle'
        ? call(settlePath,{buyerId,idempotencyKey:x.key},token)
        : call(cancelPath,{buyerId},token)));
      outcomes.parallel_settlement_posts+=width/2;
      outcomes.parallel_cancel_posts+=width/2;
      const settleResponses=responses.filter((_,j)=>attempts[j].type==='settle');
      first=settleResponses.filter(x=>x.status===201&&x.idempotentReplay===false).length;
      replay=settleResponses.filter(x=>x.status===201&&x.idempotentReplay===true).length;
      assert.ok(first<=1,'multiple distinct original transfer commits');
      assert.ok(settleResponses.every(x=>x.status===201 || x.status===409 && x.error?.code==='ORDER_NOT_PAYABLE'));
      assert.equal(responses.filter((_,j)=>attempts[j].type==='cancel').every(x=>x.status===200),true);
      outcomes.cancel_races++;
    }
    outcomes.successful_original_settlements+=first;
    outcomes.idempotent_replays+=replay;
    // Explicit post-race cancellation must be idempotent and restore exact stock and EUR.
    assert.equal((await call(cancelPath,{buyerId},token)).status,200);
    assert.equal((await call(cancelPath,{buyerId},token)).status,200);
    assert.equal(service.order(order.id).status,'SIMULATED_CANCELLED');
    const finalPayment=await call(paymentPath,undefined,token);
    const journal=service.paymentJournal();
    const transfer=finalPayment.transfer;
    const allocations=transfer?.allocations?.length??0;
    assert.equal(journal.length,first?allocations*2:0);
    if(first)assert.equal(transfer.status,'SIMULATED_REFUNDED');
    if(!first)assert.equal(transfer,null);
    assert.equal(service.paymentJournalVerify().valid,true);
    assert.equal(service.auditVerify().valid,true);
    const wallet=service.demoWallet();
    assert.equal(wallet.buyerBalanceCents,250000);
    assert.equal(wallet.suppliers.reduce((x,y)=>x+y.balanceCents,0),0);
    assert.ok(wallet.suppliers.every(x=>x.balanceCents>=0));
    for(const item of service.catalog())
      assert.equal(item.unitsAvailable,inventory.get(item.sku),'stock restoration exact per SKU');
    assert.equal(service.audit().filter(x=>x.event==='DEMO_MONEY_TRANSFER_SETTLED').length,first);
    assert.equal(service.audit().filter(x=>x.event==='DEMO_PAYMENT_REVERSED').length,first);
    return {kind,first,replay};
  } finally {await new Promise(done=>server.close(done));}
}

for(let i=0;i<fixtures;i++){
  try {await fixture(i);}
  catch(error){
    outcomes.violation_count++;
    console.error(JSON.stringify({fixture:i,kind:i%3,error:String(error?.message??error)}));
    throw error;
  }
  if(Date.now()-startTime>900000) throw new Error('Fixed 15-minute stress budget exceeded');
}
outcomes.duration_seconds=Math.round((Date.now()-startTime)/1000);
outcomes.qualified=outcomes.violation_count===0
  && outcomes.same_key_storms===Math.ceil(fixtures/3)
  && outcomes.distinct_key_storms===Math.ceil((fixtures-1)/3)
  && outcomes.cancel_races===Math.floor(fixtures/3);
assert.equal(outcomes.qualified,true);
const out=resolve(process.env.CRACI_RECEIPT_DIR,'artifacts','valio-concurrent-money');
await mkdir(out,{recursive:true});
await writeFile(resolve(out,'coverage-proof.json'),JSON.stringify(outcomes,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(outcomes));
