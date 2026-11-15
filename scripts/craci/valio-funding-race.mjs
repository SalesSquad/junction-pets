/**
 * Independent signed two-order wallet contention over loopback HTTP.
 * Synthetic EUR only: no bank, PSP, supplier identity or external network.
 */
import assert from 'node:assert/strict';
import {generateKeyPairSync, randomUUID} from 'node:crypto';
import {once} from 'node:events';
import {writeFile, mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const expectedSha='d45f450a38ec6c8fb2f73b96d181454458ae3928';
const buyerId='helsinki-hotel-demo';
const args=process.argv.slice(2);
const val=k=>{let p=args.indexOf('--'+k);return p<0?undefined:args[p+1];};
const fixtures=Number(val('fixtures')??500);
const width=Number(val('width')??32);
const seed=Number(val('seed')??20261114);
if(![2,500].includes(fixtures)||width!==32||seed!==20261114)
  throw new Error('Only pre-registered 2-smoke/500-final fixtures, width32 seed20261114');
if(process.env.CRACI_SOURCE_SHA!==expectedSha||!process.env.CRACI_SOURCE_ROOT||!process.env.CRACI_RECEIPT_DIR)
  throw new Error('Pinned Valio source/receipt environment required');
const source=resolve(process.env.CRACI_SOURCE_ROOT,'solutions/valio-trusted-trade/src');
const [{createTradeService,FIXTURE_CATALOG},{createTradeHttpServer},{signDemoEnvelope,makeDemoMandatePayload}]=
  await Promise.all(['core.mjs','server.mjs','trust-envelope.mjs'].map(x=>import(pathToFileURL(resolve(source,x)).href)));
const report={
  schema:'craci.valio-funding-race.v1',source_sha:expectedSha,seed,fixtures,width,
  two_signed_orders_per_fixture:true,oversubscribed_wallet_cents:250000,
  signed_orders:0,parallel_payment_posts:0,
  insufficient_funds_denials:0,idempotent_replays:0,
  first_settlements:0,second_settlements_after_refund:0,
  winner_A:0,winner_B:0,ledger_invalid:0,negative_balances:0,duplicate_transfer:0,
  no_real_money:true,no_external_calls:true,violations:0
};
const started=Date.now();
for(let i=0;i<fixtures;i++){
  const service=createTradeService({initialCatalog:FIXTURE_CATALOG.map(x=>({...x,unitsAvailable:10000}))});
  const inventory=new Map(service.catalog().map(x=>[x.sku,x.unitsAvailable]));
  const server=createTradeHttpServer(service);
  server.listen(0,'127.0.0.1');
  await once(server,'listening');
  const base='http://127.0.0.1:'+server.address().port;
  const call=async(path,payload,token)=>{
    const r=await fetch(base+path,{method:payload===undefined?'GET':'POST',
      headers:token?{Authorization:'Bearer '+token}:{},
      body:payload===undefined?undefined:JSON.stringify(payload),
      signal:AbortSignal.timeout(20000)});
    return {status:r.status,...await r.json()};
  };
  try{
    const session=await call('/api/demo/session',{buyerId});
    assert.equal(session.status,201);
    const token=session.token;
    const {publicKey,privateKey}=generateKeyPairSync('ed25519');
    const jwk=publicKey.export({format:'jwk'});
    const registration=await call('/api/trust/buyer-key',{buyerId,publicJwk:{kty:jwk.kty,crv:jwk.crv,x:jwk.x}},token);
    assert.equal(registration.status,201);
    async function signedOrder(which){
      const plan=(await call('/api/plans',{buyerId,budgetCents:250000,requirements:[
        {family:'dairy-milk',lactoseFree:true,quantityLitres:800,deliverBy:'2026-11-16'},
        {family:'oat-drink',lactoseFree:true,quantityLitres:20,deliverBy:'2026-11-16'},
      ]},token)).plan;
      assert.ok(plan?.id);
      const quote=(await call('/api/plans/'+plan.id+'/quotes',{buyerId,optionId:'cost'},token)).quote;
      assert.ok(quote?.id);
      if(quote.approvalRequired)
        assert.equal((await call('/api/quotes/'+quote.id+'/approval',{buyerId,decision:'approve'},token)).status,200);
      const signedOffer=(await call('/api/quotes/'+quote.id+'/offer',{buyerId},token)).signedOffer;
      const mandate=signDemoEnvelope(privateKey,registration.kid,
        makeDemoMandatePayload({quote,signedOffer,now:Date.now(),nonce:randomUUID()}));
      const proof=await call('/api/quotes/'+quote.id+'/handshake',{buyerId,signedMandate:mandate},token);
      assert.equal(proof.proof?.verification?.valid,true);
      const order=(await call('/api/orders',{buyerId,quoteId:quote.id,
        idempotencyKey:'j26-funding-order-'+i+'-'+which},token)).order;
      assert.ok(order?.paymentEligible);
      const payment=(await call('/api/orders/'+order.id+'/payment',undefined,token)).proposal;
      assert.equal((await call('/api/orders/'+order.id+'/payment-approval',{
        buyerId,decision:'approve',proposalDigest:payment.digest},token)).status,200);
      report.signed_orders++;
      return order;
    }
    const orders=[await signedOrder('A'),await signedOrder('B')];
    assert.ok(orders.every(x=>x.totalCents<250000));
    assert.ok(orders[0].totalCents+orders[1].totalCents>250000);
    const requests=Array.from({length:width},(_,j)=>({
      orderIndex:j%2,key:'j26-funding-payment-'+i+'-'+(j%2)}));
    // Fixed per-fixture shuffled call order gives both independently signed orders a chance.
    let state=(seed+i)>>>0;
    for(let j=requests.length-1;j>0;j--){
      state=(Math.imul(1664525,state)+1013904223)>>>0;
      const k=state%(j+1);
      [requests[j],requests[k]]=[requests[k],requests[j]];
    }
    const responses=await Promise.all(requests.map(async r=>({
      orderIndex:r.orderIndex,response:await call('/api/orders/'+orders[r.orderIndex].id+'/settlement',{
        buyerId,idempotencyKey:r.key},token)
    })));
    report.parallel_payment_posts+=width;
    const originals=responses.filter(x=>x.response.status===201&&x.response.idempotentReplay===false);
    assert.equal(originals.length,1,'exactly one signed order can transfer before wallet depletion');
    const winner=originals[0].orderIndex;
    const loser=1-winner;
    const winnerResponses=responses.filter(x=>x.orderIndex===winner);
    const loserResponses=responses.filter(x=>x.orderIndex===loser);
    assert.equal(winnerResponses.filter(x=>x.response.status===201&&x.response.idempotentReplay===true).length,width/2-1);
    assert.equal(loserResponses.filter(x=>x.response.status===409&&x.response.error?.code==='INSUFFICIENT_DEMO_FUNDS').length,width/2);
    report.insufficient_funds_denials+=width/2;
    report.idempotent_replays+=width/2-1;
    report.first_settlements++;
    report[winner===0?'winner_A':'winner_B']++;
    assert.equal(service.paymentJournalVerify().valid,true);
    const mid=service.demoWallet();
    assert.equal(mid.buyerBalanceCents,250000-orders[winner].totalCents);
    assert.ok(mid.buyerBalanceCents>=0);
    const cancelled=await call('/api/orders/'+orders[winner].id+'/cancel',{buyerId},token);
    assert.equal(cancelled.status,200);
    assert.equal(service.demoWallet().buyerBalanceCents,250000);
    assert.equal(service.paymentJournalVerify().valid,true);
    const paidLoser=await call('/api/orders/'+orders[loser].id+'/settlement',{
      buyerId,idempotencyKey:'j26-funding-payment-'+i+'-'+loser},token);
    assert.equal(paidLoser.status,201);
    assert.equal(paidLoser.idempotentReplay,false);
    // The previously declined key must remain unconsumed until funds are restored.
    const retried=await call('/api/orders/'+orders[loser].id+'/settlement',{
      buyerId,idempotencyKey:'j26-funding-payment-'+i+'-'+loser},token);
    assert.equal(retried.status,201);
    assert.equal(retried.idempotentReplay,true);
    assert.equal(retried.transfer.id,paidLoser.transfer.id);
    report.second_settlements_after_refund++;
    assert.equal((await call('/api/orders/'+orders[loser].id+'/cancel',{buyerId},token)).status,200);
    assert.equal((await call('/api/orders/'+orders[loser].id+'/cancel',{buyerId},token)).status,200);
    assert.equal(service.demoWallet().buyerBalanceCents,250000);
    assert.ok(service.demoWallet().suppliers.every(x=>x.balanceCents===0));
    assert.equal(service.paymentJournalVerify().valid,true);
    assert.equal(service.auditVerify().valid,true);
    assert.equal(service.audit().filter(x=>x.event==='DEMO_MONEY_TRANSFER_SETTLED').length,2);
    assert.equal(service.audit().filter(x=>x.event==='DEMO_PAYMENT_REVERSED').length,2);
    for(const item of service.catalog())
      assert.equal(item.unitsAvailable,inventory.get(item.sku),'all stock restored after two signed cancel/refunds');
  }catch(error){
    report.violations++;
    console.error(JSON.stringify({fixture:i,error:String(error?.message??error)}));
    throw error;
  }finally{await new Promise(done=>server.close(done));}
  if(Date.now()-started>900000) throw new Error('15min stress execution budget exceeded');
}
report.duration_seconds=Math.round((Date.now()-started)/1000);
report.qualified=report.violations===0&&report.signed_orders===2*fixtures
  &&report.parallel_payment_posts===32*fixtures
  &&report.insufficient_funds_denials===16*fixtures
  &&report.first_settlements===fixtures
  &&report.second_settlements_after_refund===fixtures
  &&report.winner_A>0&&report.winner_B>0;
assert.equal(report.qualified,true);
const path=resolve(process.env.CRACI_RECEIPT_DIR,'artifacts','valio-funding-race');
await mkdir(path,{recursive:true});
await writeFile(resolve(path,'coverage-proof.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(report));
