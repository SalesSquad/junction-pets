import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {chromium,firefox,webkit} from 'playwright';

// Independent synthetic browser qualification of the V4 payment UI.
// The supplier and two signed parties are ephemeral loopback-only demos.
const engines={chromium,firefox,webkit};
const engineName=process.argv[2];
assert.ok(Object.hasOwn(engines,engineName),'Select a fixed browser engine');
const sourceRoot=resolve(process.env.CRACI_SOURCE_ROOT);
const sourceSha=process.env.CRACI_SOURCE_SHA;
assert.match(sourceSha,/^[0-9a-f]{40}$/);
assert.equal(execFileSync('git',['-C',sourceRoot,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),sourceSha);
const output=resolve(process.env.CRACI_BROWSER_OUTPUT);
await mkdir(output,{recursive:true});
const {createTradeHttpServer}=await import(pathToFileURL(resolve(sourceRoot,'solutions/valio-trusted-trade/src/server.mjs')).href);

async function clickPost(page,selector,path){
  const [response]=await Promise.all([
    page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===path),
    page.locator(selector).click(),
  ]);
  return {status:response.status(),body:await response.json(),request:response.request()};
}
async function jsonGet(page,base,path,authorization){
  const response=await page.request.get(base+path,{headers:{Authorization:authorization}});
  assert.equal(response.status(),200,path+' read was refused');
  return response.json();
}
async function runViewport(browser,viewport){
  const server=createTradeHttpServer();
  let context;
  let page;
  const errors=[];
  const denied=[];
  try {
    await new Promise((yes,no)=>{server.once('error',no);server.listen(0,'127.0.0.1',yes);});
    const base='http://127.0.0.1:'+server.address().port;
    context=await browser.newContext({viewport,serviceWorkers:'block'});
    context.setDefaultTimeout(15000);
    await context.route('**/*',async route=>{
      const url=route.request().url();
      if(new URL(url).origin!==base){denied.push(new URL(url).origin);await route.abort();}
      else await route.continue();
    });
    page=await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    const opened=await page.goto(base,{waitUntil:'domcontentloaded'});
    assert.equal(opened.status(),200);
    await page.waitForFunction(()=>document.querySelector('#buyer-context')?.textContent.includes('Demo capability'));
    await page.waitForFunction(()=>document.querySelector('#handshake-button')?.disabled===true);
    for(const id of ['payment-approve-button','payment-send-button','payment-replay-button','payment-refund-button'])
      assert.equal(await page.locator('#'+id).isDisabled(),true,id+' opened before order');
    assert.match(await page.locator('#payment-status').textContent(),/AWAITING ORDER/);

    const planned=await clickPost(page,'#plan-button','/api/plans');
    assert.equal(planned.status,201);
    const plan=planned.body.plan;
    assert.equal(plan.totalLitres,720);
    const fixed=await clickPost(page,'#quote-button','/api/plans/'+plan.id+'/quotes');
    assert.equal(fixed.status,201);
    const quote=fixed.body.quote;
    assert.equal(quote.approvalRequired,true);
    assert.equal(await page.locator('#payment-send-button').isDisabled(),true);
    const approved=await clickPost(page,'#approve-button','/api/quotes/'+quote.id+'/approval');
    assert.equal(approved.status,200);
    await page.locator('#handshake-button').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#handshake-button')?.disabled===false);
    const handshake=await clickPost(page,'#handshake-button','/api/quotes/'+quote.id+'/handshake');
    assert.equal(handshake.status,201);
    assert.equal(handshake.body.proof.verification.valid,true);
    assert.match(await page.locator('#trust-badge').textContent(),/SIGNED DEMO PROOF/);
    await page.waitForFunction(()=>document.querySelector('#commit-button')?.disabled===false);

    const committed=await clickPost(page,'#commit-button','/api/orders');
    assert.equal(committed.status,201);
    const order=committed.body.order;
    assert.equal(order.status,'SIMULATED_COMMITTED');
    assert.ok(order.totalCents>0);
    const authorization=(await committed.request.allHeaders()).authorization;
    assert.match(authorization,/^Bearer [a-z0-9-]+$/i);
    assert.equal(await page.locator('#payment-send-button').isDisabled(),true);
    assert.match(await page.locator('#payment-status').textContent(),/APPROVAL REQUIRED/);

    const walletBefore=(await jsonGet(page,base,'/api/demo/wallet',authorization)).wallet;
    assert.equal(walletBefore.buyerBalanceCents,250000);
    const missingCapability=await page.request.post(base+'/api/orders/'+order.id+'/settlement',{
      data:{buyerId:'helsinki-hotel-demo',idempotencyKey:'anonymous-rejected'},
    });
    assert.equal(missingCapability.status(),403);
    assert.equal((await missingCapability.json()).error.code,'BUYER_CAPABILITY_REQUIRED');
    assert.equal((await jsonGet(page,base,'/api/demo/ledger',authorization)).entries.length,0);

    const decision=await clickPost(page,'#payment-approve-button','/api/orders/'+order.id+'/payment-approval');
    assert.equal(decision.status,200);
    assert.equal(decision.body.approval.decision,'approve');
    assert.equal(decision.body.proposal.amountCents,order.totalCents);
    await page.waitForFunction(()=>document.querySelector('#payment-send-button')?.disabled===false);
    assert.match(await page.locator('#payment-status').textContent(),/READY TO TRANSFER/);
    const forged=await page.request.post(base+'/api/orders/'+order.id+'/settlement',{
      headers:{Authorization:authorization},
      data:{buyerId:'helsinki-hotel-demo',idempotencyKey:'forged-amount',amountCents:1},
    });
    assert.notEqual(forged.status(),201);
    assert.equal((await forged.json()).error.code,'PAYMENT_TERMS_FORBIDDEN');
    assert.equal((await jsonGet(page,base,'/api/demo/ledger',authorization)).entries.length,0);

    const paid=await clickPost(page,'#payment-send-button','/api/orders/'+order.id+'/settlement');
    assert.equal(paid.status,201);
    assert.equal(paid.body.transfer.status,'SIMULATED_SETTLED');
    assert.equal(paid.body.transfer.amountCents,order.totalCents);
    assert.equal(paid.body.wallet.buyerBalanceCents,250000-order.totalCents);
    assert.equal(paid.body.transfer.allocations.reduce((sum,x)=>sum+x.amountCents,0),order.totalCents);
    const ledgerAfterPay=(await jsonGet(page,base,'/api/demo/ledger',authorization)).entries;
    assert.ok(ledgerAfterPay.length>0);
    const verifyPaid=await jsonGet(page,base,'/api/demo/ledger/verify',authorization);
    assert.equal(verifyPaid.valid,true);
    assert.equal(verifyPaid.totalDebitCents,order.totalCents);
    assert.match(await page.locator('#payment-status').textContent(),/BALANCED/);

    const replay=await clickPost(page,'#payment-replay-button','/api/orders/'+order.id+'/settlement');
    assert.equal(replay.status,201);
    assert.equal(replay.body.idempotentReplay,true);
    assert.equal(replay.body.transfer.id,paid.body.transfer.id);
    assert.equal(replay.body.wallet.buyerBalanceCents,paid.body.wallet.buyerBalanceCents);
    assert.equal((await jsonGet(page,base,'/api/demo/ledger',authorization)).entries.length,ledgerAfterPay.length);

    const refund=await clickPost(page,'#payment-refund-button','/api/orders/'+order.id+'/cancel');
    assert.equal(refund.status,200);
    assert.equal(refund.body.order.status,'SIMULATED_CANCELLED');
    await page.waitForFunction(()=>document.querySelector('#payment-status')?.textContent.includes('REVERSED'));
    const walletAfter=(await jsonGet(page,base,'/api/demo/wallet',authorization)).wallet;
    assert.equal(walletAfter.buyerBalanceCents,walletBefore.buyerBalanceCents);
    assert.equal(walletAfter.suppliers.reduce((sum,x)=>sum+x.balanceCents,0),0);
    const verifyRefund=await jsonGet(page,base,'/api/demo/ledger/verify',authorization);
    assert.equal(verifyRefund.valid,true);
    const finalEntries=(await jsonGet(page,base,'/api/demo/ledger',authorization)).entries;
    assert.equal(finalEntries.length,ledgerAfterPay.length*2);

    const overflow=await page.evaluate(()=>Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)-innerWidth);
    assert.ok(overflow<=1,'Payment viewport horizontally overflows '+overflow+'px');
    assert.deepEqual(errors,[],'Uncaught browser errors');
    assert.deepEqual(denied,[],'Non-loopback request attempted');
    const result={schema:'craci.valio-payment-browser.v1',sourceSha,engine:engineName,viewport,
      evidence:'SYNTHETIC_NONCOMMERCIAL',signedHandshake:true,humanQuoteApproval:true,
      separatePaymentApproval:true,forgedRequestRefused:true,anonymousRequestRefused:true,
      ledgerBalanced:true,transferReplayedWithoutDuplication:true,refundRestoredWallet:true,
      browserErrors:errors.length,unexpectedNetwork:denied.length,overflow};
    const prefix=engineName+'-'+viewport.width;
    await writeFile(resolve(output,prefix+'.json'),JSON.stringify(result,null,2)+'\n');
    await page.screenshot({path:resolve(output,prefix+'.png'),fullPage:false});
    return result;
  }catch(error){
    if(page)try{await page.screenshot({path:resolve(output,engineName+'-'+viewport.width+'-failure.png')});}catch{}
    throw error;
  }finally{
    if(context)await context.close();
    await new Promise(done=>server.close(done));
  }
}
const browser=await engines[engineName].launch({headless:true});
try{
  for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
    console.log(JSON.stringify(await runViewport(browser,viewport)));
  }
}finally{await browser.close();}
