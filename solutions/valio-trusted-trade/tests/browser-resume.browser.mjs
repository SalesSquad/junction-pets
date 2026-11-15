/** Explicit browser recovery qualification; all commerce and decisions are synthetic. */
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { mkdtemp } from 'node:fs/promises';
import { join } from 'node:path';
import { createPersistentTradeServer } from '../src/server.mjs';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? 'playwright');
const browser = await chromium.launch({ headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {}) });
const directory = await mkdtemp('/private/tmp/valio-browser-recovery-');
let server, port;
const start = async file => {
  server = createPersistentTradeServer({ stateFile: join(directory,file) });
  server.listen(port ?? 0,'127.0.0.1'); await once(server,'listening');
  port = server.address().port;
  return 'http://127.0.0.1:' + port;
};
const stop = async () => { if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); server = null; } };
const context = await browser.newContext({viewport:{width:1440,height:1050}});
const page = await context.newPage();
page.setDefaultTimeout(15000);
const errors = [], external = [];
let base;
const counts = { approval:0,order:0,payment:0 };
let sessionCreations = 0;
page.on('pageerror',error => errors.push(error.message));
page.on('request',request => {
  if (new URL(request.url()).origin !== base) external.push(request.url());
  if (request.method() !== 'POST') return;
  const path = new URL(request.url()).pathname;
  if (path === '/api/demo/session') sessionCreations++;
  if (/\/approval$|\/decision$/.test(path)) counts.approval++;
  if (path === '/api/orders') counts.order++;
  if (/\/settlement$/.test(path)) counts.payment++;
});
const enabled = id => page.waitForFunction(id => !document.getElementById(id).disabled,id);
const text = (id,value) => page.waitForFunction(({id,value}) => document.getElementById(id).textContent.includes(value),{id,value});
const click = async id => { await enabled(id); await page.locator('#'+id).click(); };
const events = async () => (await (await fetch(base+'/api/audit')).json()).receipts;
try {
  base = await start('original.sqlite');
  await page.goto(base+'/mission');
  await enabled('plan-button');
  const initialWallet = await page.locator('#wallet-balance').textContent();
  await click('plan-button'); await click('quote-button'); await enabled('approve-button');
  const quoteBefore = await page.locator('#selected-id').textContent();
  await page.reload(); await enabled('approve-button');
  assert.equal(await page.locator('#selected-id').textContent(),quoteBefore);
  assert.equal(await page.locator('#commit-button').isDisabled(),true);
  assert.deepEqual(counts,{approval:0,order:0,payment:0});
  await page.evaluate(() => new Promise((resolve,reject) => {
    const opened=indexedDB.open('trusted-trade-local-demo-v1',1);
    opened.onerror=()=>reject(opened.error);
    opened.onsuccess=()=>{const db=opened.result;const tx=db.transaction('sessions');const get=tx.objectStore('sessions').get('mission');
      get.onsuccess=async()=>{try{const res=await fetch('/api/demo/reprice',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+get.result.value.token},body:JSON.stringify({sku:'DEMO-LF-1',priceCents:175})});if(!res.ok)throw Error('source change refused');resolve();}catch(e){reject(e);}};tx.oncomplete=()=>db.close();};
  }));
  await page.reload(); await text('buyer-context','Demo capability'); await enabled('plan-button');
  assert.equal(await page.locator('#approve-button').isDisabled(),true,'stale restored quote must not enable a new approval');
  assert.equal(await page.locator('#commit-button').isDisabled(),true);
  assert.match(await page.locator('#trust-message').textContent(),/fresh plan/);
  assert.deepEqual(counts,{approval:0,order:0,payment:0});
  await click('plan-button'); await click('quote-button');
  await click('approve-button'); await click('handshake-button'); await text('crypto-title','Server + browser verified');
  await click('commit-button'); await click('payment-approve-button'); await click('payment-send-button');
  await text('payment-status','BALANCED');
  const receipt = await page.locator('#approval-description').textContent();
  const paidWallet = await page.locator('#wallet-balance').textContent();
  const sideEffects = {...counts};
  await page.reload(); await enabled('payment-refund-button');
  assert.equal(await page.locator('#approval-description').textContent(),receipt);
  assert.equal(await page.locator('#wallet-balance').textContent(),paidWallet);
  assert.equal(await page.locator('#plan-button').isDisabled(),true);
  assert.equal(await page.locator('#commit-button').isDisabled(),true);
  assert.deepEqual(counts,sideEffects);
  assert.equal(await page.evaluate(() => new Promise((resolve,reject) => {
    const opened=indexedDB.open('trusted-trade-local-demo-v1',1);
    opened.onerror=()=>reject(opened.error);
    opened.onsuccess=()=>{ const db=opened.result; const transaction=db.transaction('sessions'); const get=transaction.objectStore('sessions').get('mission');
      get.onsuccess=()=>resolve(get.result.value.buyerKey.privateKey.extractable===false);
      transaction.oncomplete=()=>db.close(); };
  })),true);
  const beforeUnavailable = sessionCreations;
  await page.route('**/api/demo/session', async route => route.request().method()==='GET' ?
    route.fulfill({status:503,contentType:'application/json',body:'{}'}) : route.continue());
  await page.reload(); await text('alert','Recovery paused');
  assert.equal(await page.locator('#plan-button').isDisabled(),true);
  assert.equal(sessionCreations,beforeUnavailable,'temporary backend failure must preserve the original session');
  assert.deepEqual(counts,sideEffects);
  await page.unroute('**/api/demo/session');
  await stop(); await start('original.sqlite');
  await page.reload(); await enabled('payment-refund-button');
  assert.equal(await page.locator('#approval-description').textContent(),receipt);
  assert.equal(await page.locator('#wallet-balance').textContent(),paidWallet);
  assert.deepEqual(counts,sideEffects);
  await click('payment-refund-button'); await text('payment-status','REVERSED');
  assert.equal(await page.locator('#wallet-balance').textContent(),initialWallet);
  const missionEvents = await events();
  assert.equal(missionEvents.filter(e=>e.event==='ORDER_SIMULATED').length,1);
  assert.equal(missionEvents.filter(e=>e.event==='DEMO_MONEY_TRANSFER_SETTLED').length,1);
  assert.equal(missionEvents.filter(e=>e.event==='DEMO_PAYMENT_REVERSED').length,1);

  await page.goto(base+'/');
  await enabled('find'); await page.selectOption('#budget','140000'); await click('find');
  await enabled('approve-exception');
  const classicQuote = await page.locator('#quote-id').textContent();
  const beforeClassicReload = {...counts};
  await page.reload(); await enabled('approve-exception');
  assert.equal(await page.locator('#quote-id').textContent(),classicQuote);
  assert.equal(await page.locator('#order').isDisabled(),true);
  assert.deepEqual(counts,beforeClassicReload);
  await click('approve-exception'); await click('order'); await enabled('cancel');
  const classicReceipt = await page.locator('#policy-explanation').textContent();
  const afterClassicOrder = {...counts};
  await page.reload(); await enabled('cancel');
  assert.equal(await page.locator('#policy-explanation').textContent(),classicReceipt);
  assert.deepEqual(counts,afterClassicOrder);
  await click('cancel'); await text('policy-title','cancelled');

  await stop(); await start('reset.sqlite');
  const beforeResetReload = {...counts};
  await page.goto(base+'/mission'); await enabled('plan-button');
  assert.equal(await page.locator('#commit-button').isDisabled(),true);
  assert.equal(await page.locator('#payment-send-button').isDisabled(),true);
  assert.equal(await page.locator('#payment-status').textContent(),'AWAITING ORDER');
  assert.deepEqual(counts,beforeResetReload);
  assert.equal((await events()).filter(e=>e.event==='ORDER_SIMULATED').length,0);

  await page.evaluate(() => new Promise((resolve,reject) => {
    const opened=indexedDB.open('trusted-trade-local-demo-v1',1);
    opened.onerror=()=>reject(opened.error);
    opened.onsuccess=()=>{ const db=opened.result; const transaction=db.transaction('sessions','readwrite'); const store=transaction.objectStore('sessions');
      const get=store.get('mission'); get.onsuccess=()=>store.put({...get.result,version:999},'mission');
      transaction.oncomplete=()=>{db.close();resolve();}; transaction.onerror=()=>reject(transaction.error); };
  }));
  const beforeIncompatible = sessionCreations;
  await page.reload(); await text('alert','incompatible');
  assert.equal(await page.locator('#plan-button').isDisabled(),true);
  assert.equal(sessionCreations,beforeIncompatible,'an incompatible cache must not silently create a replacement identity');

  const denied = await browser.newContext();
  try {
    await denied.addInitScript(() => Object.defineProperty(window,'indexedDB',{get(){throw Error('Storage denied for test');}}));
    const fallback = await denied.newPage();
    fallback.on('pageerror',error=>errors.push(error.message));
    await fallback.goto(base+'/mission');
    await fallback.waitForFunction(()=>!document.getElementById('plan-button').disabled);
    assert.match(await fallback.locator('#buyer-context').textContent(),/ephemeral tab/);
  } finally { await denied.close(); }
  assert.deepEqual(errors,[]);
  assert.deepEqual(external,[]);
  console.log(JSON.stringify({outcome:'PASS',reloadBeforeApproval:true,staleSourceReloadRefusesAuthority:true,nonextractableBrowserKey:true,
    paidReceiptAndRefundAfterBrowserAndServerRestart:true,classicReviewAndReceipt:true,serverResetRefusesCachedAuthority:true,
    deniedStorageEphemeralFallback:true,temporaryFailurePreservesOriginalSession:true,incompatibleStateFailsClosed:true,newRecoveryFinancialSideEffects:0}));
} finally { await context.close(); await browser.close(); await stop(); }
