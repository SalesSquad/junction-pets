import { createTradeService, unsignedQuoteBody } from '../src/core.mjs';
import { createDemoTrustRegistry, canonical, digest, protectedHeader, makeDemoMandatePayload } from '../src/trust-envelope.mjs';
import { verifyBuyerTerms, verifyBuyerBody } from '../src/buyer-terms.mjs';
import { Buffer, createHash, generateKeyPairSync, sign, verify } from './crypto.mjs';
const DB='valio-aimo-browser-local-v1',TABLE='workspaces',BUYER='helsinki-hotel-demo';
export const scenarioDefinitions=Object.freeze([
  {id:'purchase',title:'Purchase & refund'}, {id:'reject',title:'Rejection blocks commit'}, {id:'stale',title:'Changed source'},
  {id:'retry',title:'Resume & retry'}, {id:'shortage',title:'Exact stock shortage'}, {id:'expired',title:'Expired quote'},
]);
const fault=(code,message)=>Object.assign(new Error(message??code),{code});
const storageFault=()=>fault('STORAGE_UNAVAILABLE','Persistent browser storage is unavailable. Purchasing actions are blocked; restore storage and reload.');
const equal=(actual,expected)=>{if(actual!==expected)throw fault('SCENARIO_ASSERTION_FAILED','Observed result did not match the expected invariant.');};
const checksum=row=>createHash('sha256').update(JSON.stringify({core:row.core,trust:row.trust,ui:row.ui,sessionRef:row.sessionRef,buyerPublicJwk:row.buyerPublicJwk,clockOffset:row.clockOffset})).digest('hex');
async function database(){
  try{if(!globalThis.indexedDB||!navigator.locks?.request)throw storageFault();}catch{throw storageFault();}
  return new Promise((resolve,reject)=>{
    let expired=false;const request=indexedDB.open(DB,1),timer=setTimeout(()=>{expired=true;reject(storageFault());},3000);
    request.onupgradeneeded=()=>request.result.createObjectStore(TABLE);
    request.onerror=request.onblocked=()=>{clearTimeout(timer);expired=true;reject(storageFault());};
    request.onsuccess=()=>{clearTimeout(timer);if(expired)request.result.close();else resolve(request.result);};
  });
}
async function readRecord(key){
  const db=await database();return new Promise((resolve,reject)=>{
    const tx=db.transaction(TABLE,'readonly');let result,settled=false;
    const done=(error)=>{if(settled)return;settled=true;clearTimeout(timer);db.close();error?reject(storageFault()):resolve(result);};
    const timer=setTimeout(()=>{try{tx.abort();}catch{}done(true);},3000);
    const request=tx.objectStore(TABLE).get(key);request.onsuccess=()=>{result=request.result;};
    tx.oncomplete=()=>done(false);tx.onerror=tx.onabort=()=>done(true);
  });
}
async function writeRecord(key,value,expectedRevision){
  const db=await database();return new Promise((resolve,reject)=>{
    const tx=db.transaction(TABLE,'readwrite');let settled=false;
    const done=error=>{if(settled)return;settled=true;clearTimeout(timer);db.close();error?reject(storageFault()):resolve();};
    const timer=setTimeout(()=>{try{tx.abort();}catch{}done(true);},3000),store=tx.objectStore(TABLE),get=store.get(key);
    get.onsuccess=()=>{try{if((get.result?.revision??0)!==expectedRevision){tx.abort();return;}store.put(value,key);}catch{try{tx.abort();}catch{}done(true);}};
    tx.oncomplete=()=>done(false);tx.onerror=tx.onabort=()=>done(true);
  });
}
async function removeRecord(key){
  const db=await database();await new Promise((resolve,reject)=>{
    const tx=db.transaction(TABLE,'readwrite'),timer=setTimeout(()=>{try{tx.abort();}catch{}reject(storageFault());},3000);
    tx.objectStore(TABLE).delete(key);tx.oncomplete=()=>{clearTimeout(timer);resolve();};tx.onerror=tx.onabort=()=>{clearTimeout(timer);reject(storageFault());};
  }).finally(()=>db.close());
}
const data=value=>new TextEncoder().encode(value);
async function verifyEnvelope(envelope,jwk){
  const key=await crypto.subtle.importKey('jwk',{kty:jwk.kty,crv:jwk.crv,x:jwk.x},{name:'Ed25519'},false,['verify']);
  return crypto.subtle.verify('Ed25519',key,Buffer.from(envelope.signature,'base64url'),data(canonical(envelope.protected)+'.'+canonical(envelope.payload)));
}
export async function cryptoSelfCheck(){
  if(!crypto.subtle||!crypto.randomUUID)throw fault('BROWSER_CRYPTO_UNAVAILABLE','This app needs browser Ed25519 support in a secure context.');
  const sample=data('Valio Aimo local cryptographic interoperability check'),pair=generateKeyPairSync('ed25519');
  const native=await crypto.subtle.importKey('pkcs8',pair.privateKey.export({format:'der',type:'pkcs8'}),'Ed25519',false,['sign']);
  const signature=await crypto.subtle.sign('Ed25519',native,sample);
  if(!verify(null,sample,pair.publicKey,new Uint8Array(signature)))throw fault('CRYPTO_INTEROP_FAILED');
  const nativePublic=await crypto.subtle.importKey('jwk',pair.publicKey.export({format:'jwk'}),'Ed25519',false,['verify']);
  if(!await crypto.subtle.verify('Ed25519',nativePublic,sign(null,sample,pair.privateKey),sample))throw fault('CRYPTO_INTEROP_FAILED');
  const tampered=new Uint8Array(sample);tampered[0]^=1;
  if(verify(null,tampered,pair.publicKey,new Uint8Array(signature)))throw fault('CRYPTO_TAMPER_CHECK_FAILED');
  const hash=Buffer.from(await crypto.subtle.digest('SHA-256',sample)).toString('hex');
  if(createHash('sha256').update(sample).digest('hex')!==hash)throw fault('CRYPTO_INTEROP_FAILED');
  return {algorithm:'Ed25519',hash:'SHA-256',nativeInteroperability:true,tamperingRefused:true};
}
let checkedCrypto;
const cryptoReady=()=>checkedCrypto??=cryptoSelfCheck().catch(()=>{throw fault('BROWSER_CRYPTO_UNAVAILABLE','This browser cannot verify the required Ed25519/SHA-256 operations. Purchasing is blocked.');});
function hydrate(row){
  try{
    if(row.version!==1||row.scope!=='BROWSER_LOCAL_SYNTHETIC'||!Number.isSafeInteger(row.revision)||row.revision<1||
        !Number.isSafeInteger(row.clockOffset)||row.clockOffset<0||row.clockOffset>86400000||row.integrity!==checksum(row)||
        row.buyerKeys?.privateKey?.type!=='private'||row.buyerKeys.privateKey.extractable!==false||
        row.buyerKeys.privateKey.algorithm?.name!=='Ed25519'||row.buyerKeys?.publicKey?.type!=='public')throw Error();
    const clock=()=>Date.now()+row.clockOffset;
    return {row,clock,service:createTradeService({initialState:row.core,clock}),trust:createDemoTrustRegistry({initialState:row.trust,clock})};
  }catch{throw fault('STORAGE_CORRUPT','Saved local state is incompatible or corrupted. It was preserved and purchasing is blocked.');}
}
async function fresh(){
  await cryptoReady();const buyerKeys=await crypto.subtle.generateKey('Ed25519',false,['sign','verify']);
  const publicKey=await crypto.subtle.exportKey('jwk',buyerKeys.publicKey),service=createTradeService(),trust=createDemoTrustRegistry();
  const row={version:1,scope:'BROWSER_LOCAL_SYNTHETIC',revision:1,clockOffset:0,sessionRef:crypto.randomUUID(),buyerKeys,
    buyerPublicJwk:{kty:publicKey.kty,crv:publicKey.crv,x:publicKey.x},core:service.exportState(),trust:trust.exportState(),
    ui:{intent:null,plan:null,review:null,quoteId:null,orderId:null,orderKey:null,paymentKey:null,simulations:[]}};
  row.integrity=checksum(row);return row;
}
function project(context){
  const {service,trust,row}=context,q=row.ui.quoteId?service.quote(row.ui.quoteId):null;
  const order=q?.orderId?service.order(q.orderId):null,proof=q?trust.findHandshake(q.id):null;
  let freshness='CURRENT';if(q&&!order){try{service.assertQuoteFresh(q.id);}catch(error){freshness=error.code;}}
  const payment=order?.paymentEligible?service.payment(order.id,BUYER):null;
  return {mode:'BROWSER_LOCAL_SYNTHETIC',revision:row.revision,intent:row.ui.intent,plan:row.ui.plan,review:row.ui.review,quote:q,
    order,proof,freshness,payment,wallet:service.demoWallet(),audit:service.audit().slice(-30),auditCount:service.audit().length,
    auditValid:service.auditVerify().valid,simulations:row.ui.simulations,storage:'INDEXEDDB_ATOMIC_WITH_WEB_LOCKS',buyerKeyExtractable:false};
}
const need=(family,quantity)=>({family,quantityLitres:quantity,lactoseFree:true,deliverBy:'2026-11-16'});
function checkDisplay(context,payload){
  const q=context.row.ui.quoteId?context.service.quote(context.row.ui.quoteId):null;
  if(!q||payload.quoteId!==q.id||payload.snapshotId!==q.snapshotId)throw fault('DISPLAY_CHANGED','The displayed quote changed in another tab. Review the current proposal.');return q;
}
function checkBuyer(context,q){
  const intent=context.row.ui.intent,ceiling=q.budgetException&&q.approval?.decision==='approve'?q.totalCents:intent.budgetCents;
  try{verifyBuyerTerms(q,context.service.policy(),{requirements:intent.requirements,budgetCents:ceiling});}catch{throw fault('BUYER_TERMS_REFUSED','The independent buyer refused terms outside the original need or accepted quote-only budget.');}
}
export class BrowserWorkspace {
  constructor(key='main'){
    this.key=key;this.blocked=false;this.listeners=new Set();
    try{this.channel=typeof BroadcastChannel==='function'?new BroadcastChannel(DB):null;}catch{this.channel=null;} // Notifications are optional; Web Locks remain mandatory.
    if(this.channel)this.channel.onmessage=event=>{if(event.data?.key===this.key)for(const listener of this.listeners)listener();};
  }
  subscribe(listener){this.listeners.add(listener);return ()=>this.listeners.delete(listener);}
  async run(operation){
    if(this.blocked)throw storageFault();
    try{
      await cryptoReady();if(!navigator.locks?.request)throw storageFault();
      return await navigator.locks.request(DB+':'+this.key,{mode:'exclusive',signal:AbortSignal.timeout(10000)},async()=>{
        let row=await readRecord(this.key);
        if(!row){row=await fresh();await writeRecord(this.key,row,0);}
        const context=hydrate(row),publicKey=await crypto.subtle.exportKey('jwk',row.buyerKeys.publicKey);
        if(publicKey.x!==row.buyerPublicJwk.x)throw fault('STORAGE_CORRUPT','The stored buyer key no longer matches its public identity.');
        if(!operation)return project(context);
        await operation(context);
        const next={...row,revision:row.revision+1,core:context.service.exportState(),trust:context.trust.exportState()};next.integrity=checksum(next);
        if(new TextEncoder().encode(JSON.stringify({core:next.core,trust:next.trust,ui:next.ui})).byteLength>8388608)throw fault('STORAGE_CAPACITY','Local evidence reached its bounded capacity; no new effect was committed.');
        hydrate(next);await writeRecord(this.key,next,row.revision);
        try{this.channel?.postMessage({key:this.key,revision:next.revision});}catch{}
        return project({...context,row:next});
      });
    }catch(error){if(/^(?:STORAGE_|BROWSER_CRYPTO_|CRYPTO_)/.test(error.code??'')||!error.code)this.blocked=true;throw error;}
  }
  read(){return this.run(null);}
  command(action,payload={}){return this.run(async context=>{
    const {row,service,trust,clock}=context;
    if(action==='prepare'){
      if(row.ui.orderId&&service.order(row.ui.orderId).status==='SIMULATED_COMMITTED')throw fault('ACTIVE_ORDER','Cancel the active synthetic order before starting another mission.');
      const {milkLitres,oatLitres,budgetCents}=payload;
      if(![milkLitres,oatLitres].every(value=>Number.isSafeInteger(value)&&value>=0&&value<=10000)||milkLitres+oatLitres===0||!Number.isSafeInteger(budgetCents)||budgetCents<1||budgetCents>250000)throw fault('INVALID_NEED','Use whole litres and a budget between €0.01 and €2,500.');
      const requirements=[...(milkLitres?[need('dairy-milk',milkLitres)]:[]),...(oatLitres?[need('oat-drink',oatLitres)]:[])];
      const simulations=row.ui.simulations;row.ui={intent:{requirements,budgetCents},plan:null,review:null,quoteId:null,orderId:null,
        orderKey:crypto.randomUUID(),paymentKey:crypto.randomUUID(),simulations};
      if(requirements.length===2)row.ui.plan=service.planBasket({buyerId:BUYER,requirements,budgetCents});
      else{const result=service.requestReview({buyerId:BUYER,need:requirements[0],budgetCents});row.ui.review=result.review;row.ui.quoteId=result.quote?.id??null;}
      return;
    }
    if(action==='select'){
      if(!row.ui.plan||payload.planId!==row.ui.plan.id)throw fault('DISPLAY_CHANGED','Replan before selecting this option.');
      if(row.ui.orderId)throw fault('ACTIVE_ORDER');
      const q=service.quoteBasketPlan({buyerId:BUYER,planId:row.ui.plan.id,optionId:payload.optionId});row.ui.quoteId=q.id;return;
    }
    if(action==='reprice'){service.simulatePriceChange({sku:'DEMO-LF-1',priceCents:service.catalog().find(item=>item.sku==='DEMO-LF-1').priceCents+1});return;}
    if(action==='shortage'){for(const sku of ['DEMO-LF-1','DEMO-LF-2'])service.simulateStockShock({sku,unitsAvailable:0});return;}
    if(action==='advance'){if(!Number.isSafeInteger(payload.milliseconds)||payload.milliseconds<1||row.clockOffset+payload.milliseconds>86400000)throw fault('INVALID_CLOCK');row.clockOffset+=payload.milliseconds;return;}
    if(action==='simulations'){row.ui.simulations=payload.results;return;}
    const q=checkDisplay(context,payload);
    if(action==='approve'||action==='reject'){
      const decision=action==='approve'?'approve':'reject';
      if(q.reviewId)row.ui.review=service.decideReview({buyerId:BUYER,reviewId:q.reviewId,quoteId:q.id,snapshotId:q.snapshotId,decision}).review;
      else service.approve({buyerId:BUYER,quoteId:q.id,decision,approver:'Browser-local fictional reviewer; not an authenticated identity'});return;
    }
    if(action==='prove'){
      service.assertQuoteFresh(q.id);checkBuyer(context,q);
      let proof=trust.findHandshake(q.id);
      if(!proof){
        const {kid}=trust.registerBuyerKey(row.sessionRef,row.buyerPublicJwk),body=unsignedQuoteBody(q),signedOffer=trust.signOffer(q,body);
        verifyBuyerBody(body,q);
        const supplierJwk=trust.publicKeys().keys.find(key=>key.kid===signedOffer.protected.kid);
        if(!await verifyEnvelope(signedOffer,supplierJwk))throw fault('SIGNATURE_INVALID');
        const protectedValue=protectedHeader(kid),mandate=makeDemoMandatePayload({quote:q,signedOffer,now:clock(),nonce:crypto.randomUUID()});
        const signature=await crypto.subtle.sign('Ed25519',row.buyerKeys.privateKey,data(canonical(protectedValue)+'.'+canonical(mandate)));
        const signedMandate={protected:protectedValue,payload:mandate,signature:Buffer.from(signature).toString('base64url')};
        if(!await verifyEnvelope(signedMandate,row.buyerPublicJwk))throw fault('SIGNATURE_INVALID');
        proof=trust.issueHandshake(q,body,signedMandate,row.sessionRef);service.recordVerifiedHandshake({quoteId:q.id,verification:proof.verification});
      }
      trust.verifyHandshake(proof,q,unsignedQuoteBody(q));return;
    }
    if(action==='commit'||action==='replay'){
      if(!q.orderId){service.assertQuoteFresh(q.id);checkBuyer(context,q);const proof=trust.findHandshake(q.id);if(!proof)throw fault('HANDSHAKE_REQUIRED','Verify both cryptographic envelopes first.');trust.verifyHandshake(proof,q,unsignedQuoteBody(q));}
      const order=service.commitOrder({buyerId:BUYER,quoteId:q.id,idempotencyKey:row.ui.orderKey});row.ui.orderId=order.id;return;
    }
    if(!q.orderId||row.ui.orderId!==q.orderId)throw fault('ORDER_REQUIRED');
    if(action==='payment-approve'){
      const proposal=service.payment(q.orderId,BUYER).proposal;
      if(payload.proposalDigest!==proposal.digest)throw fault('PAYMENT_TERMS_CHANGED','Review the current payment proposal.');
      service.approvePayment({orderId:q.orderId,buyerId:BUYER,decision:'approve',proposalDigest:proposal.digest});return;
    }
    if(action==='settle'){service.settlePayment({orderId:q.orderId,buyerId:BUYER,idempotencyKey:row.ui.paymentKey});return;}
    if(action==='cancel'){service.cancelOrder({orderId:q.orderId,buyerId:BUYER});return;}
    throw fault('ACTION_UNAVAILABLE','This action is unavailable in the browser-local scope.');
  });}
  async removeScenario(){if(!this.key.startsWith('scenario-'))throw fault('WORKSPACE_PRESERVED');await navigator.locks.request(DB+':'+this.key,{mode:'exclusive',signal:AbortSignal.timeout(10000)},()=>removeRecord(this.key));this.close();}
  close(){this.channel?.close();this.listeners.clear();}
}
const bound=view=>({quoteId:view.quote.id,snapshotId:view.quote.snapshotId});
export async function runBrowserScenario(id){
  const definition=scenarioDefinitions.find(value=>value.id===id);if(!definition)throw fault('SCENARIO_UNKNOWN');
  const workspace=new BrowserWorkspace('scenario-'+crypto.randomUUID()),steps=[],started=performance.now();let view,result;
  const step=async(title,operation)=>{try{const observed=await operation();steps.push({title,outcome:'PASS',observed});}catch(error){steps.push({title,outcome:'FAIL',observed:{code:error.code??'BROWSER_FAILURE'}});throw error;}};
  const expectRefusal=async(operation,codes)=>{let rejected;try{await operation();}catch(error){rejected=error;}if(!rejected||!codes.includes(rejected.code))throw fault('SCENARIO_ASSERTION_FAILED');return {code:rejected.code,expectedRefusal:true};};
  const command=async(action,payload={})=>view=await workspace.command(action,{...(view?.quote?bound(view):{}),...payload});
  try{
    await workspace.read();
    if(id==='shortage')await step('Exact dairy stock is removed',async()=>{await command('shortage');return {availableLitres:0};});
    await step('The original deterministic domain prepares the need',async()=>{await command('prepare',{milkLitres:1000,oatLitres:0,budgetCents:140000});return {quoteId:view.quote?.id??null,budgetGapCents:view.quote?.budgetException?.additionalCents??null};});
    if(id==='shortage'){await step('No substitute or order is invented',async()=>{equal(view.quote,null);equal(view.wallet.buyerBalanceCents,250000);return {blocked:true,orders:0};});}
    else if(id==='reject'){
      await step('A local simulated rejection is recorded',async()=>{await command('reject');equal(view.quote.status,'REJECTED');return {status:view.quote.status};});
      await step('Commit is refused',()=>expectRefusal(()=>command('commit'),['HANDSHAKE_REQUIRED','BUYER_TERMS_REFUSED','APPROVAL_REQUIRED','BUDGET_EXCEEDED']));
    }else if(id==='stale'||id==='expired'){
      if(id==='stale')await command('reprice');else await command('advance',{milliseconds:Math.max(121000,view.quote.expiresAtMs-Date.now()+1)});
      await step('Changed or expired terms cannot be approved',()=>expectRefusal(()=>command('approve'),[id==='stale'?'QUOTE_STALE':'QUOTE_EXPIRED']));
      const latest=await workspace.read();equal(latest.order,null);equal(latest.wallet.buyerBalanceCents,250000);
    }else{
      await step('Only the displayed budget exception is approved',async()=>{await command('approve');equal(view.quote.status,'APPROVED');return {additionalBudgetCents:view.quote.budgetException.additionalCents};});
      await step('WebCrypto and noble verify real Ed25519 envelopes',async()=>{await command('prove');equal(view.proof.verification.valid,true);return {algorithm:'Ed25519',selfAttestedOnly:true};});
      await step('Exactly one synthetic order is committed',async()=>{await command('commit');equal(view.order.status,'SIMULATED_COMMITTED');return {orderId:view.order.id};});
      if(id==='retry')await step('The saved workspace is reopened and replayed',async()=>{const original=view.order.id,reopened=new BrowserWorkspace(workspace.key);try{view=await reopened.command('replay',bound(await reopened.read()));equal(view.order.id,original);equal(view.audit.filter(event=>event.event==='ORDER_SIMULATED').length,1);return {orderId:original,orders:1};}finally{reopened.close();}});
      await step('Payment requires a separate approval',async()=>{await command('payment-approve',{proposalDigest:view.payment.proposal.digest});await command('settle');equal(view.payment.transfer.status,'SIMULATED_SETTLED');return {amountCents:view.payment.proposal.amountCents};});
      if(id==='retry')await step('Payment replay does not charge twice',async()=>{await command('settle');equal(view.audit.filter(event=>event.event==='DEMO_MONEY_TRANSFER_SETTLED').length,1);return {transfers:1};});
      await step('Cancellation fully refunds the local wallet',async()=>{await command('cancel');equal(view.wallet.buyerBalanceCents,250000);equal(view.order.status,'SIMULATED_CANCELLED');return {balanceCents:250000};});
    }
    const final=await workspace.read();equal(final.auditValid,true);
    result={id,title:definition.title,outcome:'PASS',scope:'BROWSER_LOCAL_SYNTHETIC',steps,elapsedMs:Math.round(performance.now()-started),externalProviderCalls:0};
  }catch(error){result={id,title:definition.title,outcome:'FAIL',scope:'BROWSER_LOCAL_SYNTHETIC',steps,code:/^[A-Z0-9_]{1,80}$/.test(error.code??'')?error.code:'BROWSER_FAILURE',elapsedMs:Math.round(performance.now()-started),externalProviderCalls:0};}
  finally{try{await workspace.removeScenario();}catch{workspace.close();if(result){result.outcome='FAIL';result.code='SCENARIO_CLEANUP_FAILED';}}}
  return result;
}
