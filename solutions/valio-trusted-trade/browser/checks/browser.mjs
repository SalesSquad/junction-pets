/** Focused real-browser evidence. Static asset server is test infrastructure, not an app backend. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { once } from 'node:events';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyBrowserBuild } from '../verify.mjs';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE??'playwright');
await verifyBrowserBuild();
const dist=resolve(dirname(fileURLToPath(import.meta.url)),'../dist');
const names=new Set(['index.html','app.js','app.css','NOTICE.txt','export.json']);
const server=createServer(async(request,response)=>{
  const name=new URL(request.url,'http://test.invalid').pathname.slice(1)||'index.html';
  if(!names.has(name)){response.writeHead(404);response.end();return;}
  try{const body=await readFile(resolve(dist,name));response.writeHead(200,{'Content-Type':name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.json')?'application/json':name.endsWith('.html')?'text/html':'text/plain'});response.end(body);}
  catch{response.writeHead(500);response.end();}
});
server.listen(0,'127.0.0.1');await once(server,'listening');
const base='http://127.0.0.1:'+server.address().port;
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_PATH}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage(),errors=[],external=[],writes=[];
context.on('page',active=>active.on('pageerror',error=>errors.push(error.message)));
context.on('request',request=>{if(new URL(request.url()).origin!==base)external.push(request.url());if(request.method()!=='GET')writes.push(request.method());});
page.on('pageerror',error=>errors.push(error.message));
const enabled=async(active,id)=>active.waitForFunction(id=>!document.getElementById(id).disabled,id);
const click=async(active,id)=>{await enabled(active,id);await active.locator('#'+id).click();};
const view=active=>active.evaluate(()=>window.valioAimoApp.inspect());
const stored=active=>active.evaluate(()=>new Promise((resolve,reject)=>{
  const open=indexedDB.open('valio-aimo-browser-local-v1',1);open.onerror=()=>reject(open.error);open.onsuccess=()=>{
    const db=open.result,tx=db.transaction('workspaces'),get=tx.objectStore('workspaces').get('main');get.onsuccess=()=>resolve(get.result);tx.oncomplete=()=>db.close();};
}));
try{
  await page.goto(base);await enabled(page,'plan');
  await click(page,'plan');await page.waitForSelector('[data-option="cost"]');
  assert.equal(await page.locator('[data-option]').count(),3);
  await page.locator('[data-option="cost"]').click();await enabled(page,'approve');
  const portfolio=await view(page);assert.equal(portfolio.quote.lines.reduce((sum,line)=>sum+line.quantityLitres,0),720);
  await click(page,'exception-preset');await click(page,'plan');await enabled(page,'approve');
  let current=await view(page);assert.equal(current.quote.budgetException.additionalCents,37300);assert.equal(current.quote.budgetCents,140000);
  await click(page,'approve');await click(page,'prove');await enabled(page,'commit');
  current=await view(page);assert.equal(current.proof.verification.valid,true);const quoteId=current.quote.id;
  const keySafe=await page.evaluate(async()=>{
    const row=await new Promise((resolve,reject)=>{const open=indexedDB.open('valio-aimo-browser-local-v1',1);open.onerror=()=>reject(open.error);open.onsuccess=()=>{const db=open.result,tx=db.transaction('workspaces'),get=tx.objectStore('workspaces').get('main');get.onsuccess=()=>resolve(get.result);tx.oncomplete=()=>db.close();};});
    try{await crypto.subtle.exportKey('pkcs8',row.buyerKeys.privateKey);return false;}catch{return row.buyerKeys.privateKey.extractable===false;}
  });assert.equal(keySafe,true,'buyer private key stays non-extractable after IndexedDB structured cloning');
  await page.evaluate(()=>{const original=IDBObjectStore.prototype.put;window.restorePut=()=>{IDBObjectStore.prototype.put=original;};IDBObjectStore.prototype.put=function(value,key){if(this.name==='workspaces'&&key==='main'&&value?.core?.orders?.length)throw new DOMException('Synthetic quota fault','QuotaExceededError');return original.call(this,value,key);};});
  await click(page,'commit');await page.waitForFunction(()=>document.getElementById('error').textContent.includes('STORAGE_UNAVAILABLE'));
  assert.equal(await page.locator('#commit').isDisabled(),true);
  assert.equal((await stored(page)).core.orders.length,0,'failed storage ACK must roll back the local domain candidate');
  await page.evaluate(()=>window.restorePut());await page.reload();await enabled(page,'commit');
  assert.equal((await view(page)).quote.id,quoteId);
  const second=await context.newPage();await second.goto(base);await enabled(second,'commit');
  assert.equal((await view(second)).quote.id,quoteId);
  await page.evaluate(()=>{window.lockHeld=false;window.heldLock=navigator.locks.request('valio-aimo-browser-local-v1:main',()=>new Promise(resolve=>{window.releaseLock=resolve;window.lockHeld=true;}));});
  await page.waitForFunction(()=>window.lockHeld);
  await Promise.all([page.locator('#commit').click(),second.locator('#commit').click()]);
  await page.waitForFunction(async()=>{const locks=await navigator.locks.query();return document.getElementById('commit').disabled&&locks.pending.filter(lock=>lock.name==='valio-aimo-browser-local-v1:main').length>=2;});
  assert.equal(await second.locator('#commit').isDisabled(),true);
  await page.evaluate(async()=>{window.releaseLock();await window.heldLock;});
  await enabled(page,'cancel');await enabled(second,'cancel');
  const a=await view(page),b=await view(second);assert.equal(a.order.id,b.order.id);assert.equal(a.audit.filter(event=>event.event==='ORDER_SIMULATED').length,1);
  await click(page,'payment-approve');await click(page,'settle');await page.waitForFunction(()=>document.getElementById('payment-status').textContent.includes('SIMULATED SETTLED'));
  const paid=await view(page);assert.equal(paid.wallet.buyerBalanceCents,250000-paid.quote.totalCents);
  await click(page,'settle');assert.equal((await view(page)).audit.filter(event=>event.event==='DEMO_MONEY_TRANSFER_SETTLED').length,1);
  await click(page,'cancel');await page.waitForFunction(()=>document.getElementById('order-status').textContent.includes('SIMULATED CANCELLED'));
  assert.equal((await view(page)).wallet.buyerBalanceCents,250000);
  await second.close();
  await click(page,'run-scenarios');await page.waitForFunction(()=>document.querySelectorAll('.scenario-result').length===6&&!document.getElementById('run-scenarios').disabled);
  const cases=(await view(page)).simulations;assert.equal(cases.length,6);assert.ok(cases.every(result=>result.outcome==='PASS'),JSON.stringify(cases));
  assert.equal(cases.find(result=>result.id==='stale').steps.find(step=>step.observed?.expectedRefusal).observed.code,'QUOTE_STALE');
  assert.equal(cases.find(result=>result.id==='expired').steps.find(step=>step.observed?.expectedRefusal).observed.code,'QUOTE_EXPIRED');
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'mobile layout must not overflow');
  await page.reload();await enabled(page,'plan');assert.equal((await view(page)).order.status,'SIMULATED_CANCELLED');
  const denied=await browser.newContext();try{await denied.addInitScript(()=>Object.defineProperty(window,'indexedDB',{get(){throw Error('Storage denied by test');}}));const blocked=await denied.newPage();await blocked.goto(base);await blocked.waitForFunction(()=>!document.getElementById('error').hidden);assert.equal(await blocked.locator('#plan').isDisabled(),true);assert.equal(await blocked.locator('#commit').isDisabled(),true);}finally{await denied.close();}
  const corrupt=await browser.newContext();try{const broken=await corrupt.newPage();await broken.goto(base);await enabled(broken,'plan');await broken.evaluate(()=>new Promise((resolve,reject)=>{const open=indexedDB.open('valio-aimo-browser-local-v1',1);open.onerror=()=>reject(open.error);open.onsuccess=()=>{const db=open.result,tx=db.transaction('workspaces','readwrite'),store=tx.objectStore('workspaces'),get=store.get('main');get.onsuccess=()=>store.put({...get.result,integrity:'BROKEN_TEST_CHECKSUM'},'main');tx.oncomplete=()=>{db.close();resolve();};};}));await broken.reload();await broken.waitForFunction(()=>document.getElementById('error').textContent.includes('STORAGE_CORRUPT'));assert.equal(await broken.locator('#plan').isDisabled(),true);}finally{await corrupt.close();}
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(writes,[]);
  console.log(JSON.stringify({check:'browser-local-original-domain',outcome:'PASS',portfolioOptions:3,budgetException:true,realWebCryptoProof:true,
    nonextractableBuyerKey:true,failedStorageCommitEffects:0,simultaneousTabOrders:1,settlementReplayTransfers:1,refundBalanceCents:250000,
    browserScenarios:6,corruptAndDeniedStorageRefused:true,reloadRecovery:true,mobileNoOverflow:true,externalProviderCalls:0,backendRequests:0}));
}finally{await context.close();await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
