/** Real local execution with explicitly scripted test identities. Never a Valio order client. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { mkdtemp, mkdir, realpath, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { createBuyerIdentity } from '../src/buyer-identity.mjs';
import { createPersistentTradeServer } from '../src/server.mjs';
import { createTradeClient } from '../mcp/trade-client.mjs';
import { createJwtHostVerifier } from '../identity/jwt-host.mjs';

export const scenarios = Object.freeze([
  {id:'purchase',title:'Osto ja täysi palautus',description:'1 000 litraa maitoa, täsmällinen budjettipoikkeus, erillinen testimaksu ja palautus.'},
  {id:'reject',title:'Allekirjoitettu hylkäys',description:'Testi-ihminen hylkää ehdotuksen; agentti ei saa tilata tai maksaa.'},
  {id:'stale',title:'Hinta muuttuu kesken oston',description:'Vanha lähdeversio torjutaan; uusi tarjous tarvitsee uuden hyväksynnän.'},
  {id:'revoked',title:'Hyväksyjän oikeus perutaan',description:'Jo hyväksytty tarjous ei oikeuta tilaukseen, kun hyväksyjän oikeus on peruttu.'},
  {id:'retry',title:'Kuittaus katoaa kahdesti',description:'Palvelin käynnistetään uudelleen tilauksen ja maksun jälkeen; vaikutus syntyy vain kerran.'},
  {id:'shortage',title:'Maito loppuu varastosta',description:'Vaatimukset säilyvät: kaurajuomaa ei vaihdeta maidon tilalle ilman lupaa.'},
  {id:'expired',title:'Tarjous ja hyväksyntä vanhenevat',description:'Hallittu kello osoittaa vanhentumisen ilman oikeaa odottamista.'},
].map(value=>Object.freeze(value)));
const buyerId='helsinki-hotel-demo',issuer='https://local-simulation.invalid';
const requirements=[{family:'dairy-milk',lactoseFree:true,quantityLitres:1000,deliverBy:'2026-11-16'}];
const safeCode=error=>{
  if(error?.name==='TimeoutError')return 'SIMULATION_TIMEOUT';
  if(error?.name==='AbortError')return 'SIMULATION_ABORTED';
  if(error?.name==='SyntaxError')return 'SIMULATION_PROTOCOL_JSON_INVALID';
  if(typeof error?.code==='string'&&/^[A-Z0-9_]{1,80}$/.test(error.code))return error.code;
  if(typeof error?.cause?.code==='string'&&/^[A-Z0-9_]{1,60}$/.test(error.cause.code))return 'TRANSPORT_'+error.cause.code;
  return 'SIMULATION_FAILED';
};
const milliseconds=start=>Math.round((performance.now()-start)*100)/100;
const failure=code=>Object.assign(new Error(code),{code});
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const closeServer=async server=>{
  if(!server)return;
  let timer;
  try{
    server.closeAllConnections();
    await Promise.race([new Promise((resolve,reject)=>server.close(error=>error&&error.code!=='ERR_SERVER_NOT_RUNNING'?reject(error):resolve())),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(failure('SIMULATION_CLEANUP_TIMEOUT')),3000);})]);
  }finally{clearTimeout(timer);server.closeAllConnections();}
};
const responseJson=async response=>{
  if(!Number.isInteger(response.status)||response.status<200||response.status>599)throw failure('SIMULATION_PROTOCOL_STATUS_INVALID');
  if(typeof response.headers?.get!=='function'||!/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type')??''))throw failure('SIMULATION_PROTOCOL_MEDIA_INVALID');
  const length=response.headers.get('content-length');
  if(length!==null&&(!/^[0-9]+$/.test(length)||Number(length)>2097152))throw failure('SIMULATION_PROTOCOL_BODY_LIMIT');
  if(typeof response.body?.getReader!=='function')throw failure('SIMULATION_PROTOCOL_BODY_MISSING');
  const reader=response.body.getReader(),chunks=[];let bytes=0;
  try{
    while(true){const part=await reader.read();if(part.done)break;
      if(!(part.value instanceof Uint8Array))throw failure('SIMULATION_PROTOCOL_BODY_INVALID');
      bytes+=part.value.byteLength;if(bytes>2097152)throw failure('SIMULATION_PROTOCOL_BODY_LIMIT');chunks.push(Buffer.from(part.value));}
  }finally{void reader.cancel().catch(()=>{});}
  let value;try{value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));}
  catch{throw failure('SIMULATION_PROTOCOL_JSON_INVALID');}
  if(!object(value))throw failure('SIMULATION_PROTOCOL_SHAPE_INVALID');
  return value;
};


export async function createSimulationLab({stateDirectory}={}) {
  const fromIdentity=createRequire(new URL('../identity/package.json',import.meta.url));
  const {generateKeyPair,exportJWK,SignJWT}=await import(fromIdentity.resolve('jose'));
  const root=stateDirectory?resolve(stateDirectory):await mkdtemp(join(tmpdir(),'valio-simulation-lab-'));
  await mkdir(root,{recursive:true,mode:0o700});
  const directory=await realpath(root),info=await stat(directory);
  if(!info.isDirectory()||(info.mode&0o077)||(process.getuid&&info.uid!==process.getuid()))throw failure('SIMULATION_DIRECTORY_UNSAFE');
  let closing=false;
  const active=new Set();
  const execute=async definition=>{
    const started=performance.now(),steps=[],summary={mode:'LOCAL_SIMULATION',commerce:'SIMULATED_NO_REAL_ORDER',scriptedTestActors:true};
    let client,server,port,base,report,clockOffset=0,serial=0;
    const now=()=>Date.now()+clockOffset;
    const clock=()=>new Date(now());
    const losses={order:0,payment:0},armed={order:false,payment:false};
    const step=async(id,title,operation,expected)=>{
      const began=performance.now();
      try{const observed=await operation();steps.push({id,title,outcome:'PASS',...(expected?{expected}:{}),...(observed!==undefined?{observed}:{}),elapsedMs:milliseconds(began)});return observed;}
      catch(error){steps.push({id,title,outcome:'FAIL',...(expected?{expected}:{}),observed:{code:safeCode(error)},elapsedMs:milliseconds(began)});throw error;}
    };
    const refused=async(operation,codes)=>{
      let caught;try{await operation();}catch(error){caught=error;}
      assert.ok(caught,'Expected a refusal; successful execution is a failure.');
      assert.ok(codes.includes(caught.code),'Unexpected refusal code: '+safeCode(caught));
      return {code:caught.code,expectedRefusal:true};
    };
    try {
      const runDirectory=await realpath(await mkdtemp(join(directory,'run-')));
      const keys=await generateKeyPair('EdDSA');
      const jwk={...await exportJWK(keys.publicKey),kid:'simulation-'+randomUUID(),alg:'EdDSA'};
      const grants=[
        {subject:'scripted-test-agent',buyerId,ownerScope:'simulation-kitchen',principalType:'AGENT',active:true,revision:1,
          actions:['read','prepare','commit','cancel','relay_decision','inventory','audit'],maxOrderCents:250000},
        {subject:'scripted-test-reviewer',buyerId,ownerScope:'simulation-kitchen',principalType:'HUMAN',active:true,revision:1,
          actions:['read','approve','pay'],maxOrderCents:250000},
      ];
      const verifier=await createJwtHostVerifier({issuer,accessAudience:'simulation-api',decisionAudience:'simulation-decisions',
        jwks:{keys:[jwk]},algorithms:['EdDSA'],clock});
      const identity=createBuyerIdentity({profileId:'simulation-'+randomUUID(),issuer,verifier,grants:()=>grants,clock:now});
      const mint=(subject,claims=null)=>new SignJWT(claims??{}).setProtectedHeader({alg:'EdDSA',kid:jwk.kid,typ:claims?'buyer-decision+jwt':'at+jwt'})
        .setIssuer(issuer).setAudience(claims?'simulation-decisions':'simulation-api').setSubject(subject)
        .setIssuedAt(Math.floor(now()/1000)).setExpirationTime(Math.floor(now()/1000)+(claims?120:600)).setJti(randomUUID()).sign(keys.privateKey);
      const access=()=>mint('scripted-test-agent');
      const call=async(path,body,proof,key)=>{
        const url=new URL(path,base);if(url.origin!==base)throw failure('SIMULATION_EXTERNAL_CALL_REFUSED');
        const response=await fetch(url,{method:body===undefined?'GET':'POST',redirect:'error',signal:AbortSignal.timeout(7000),
          headers:{Accept:'application/json','Content-Type':'application/json',Authorization:'Bearer '+await access(),
            ...(body===undefined?{}:{'Idempotency-Key':key??'simulation-command-'+ ++serial}),...(proof?{'X-Buyer-Decision-Proof':proof}:{})},
          body:body===undefined?undefined:JSON.stringify(body)});
        const value=await responseJson(response);
        if(!response.ok)throw failure(typeof value.error?.code==='string'&&/^[A-Z0-9_]{1,80}$/.test(value.error.code)?value.error.code:'SIMULATION_HTTP_REFUSED');
        return value;
      };
      let decision='approve';
      const proofFor=async(quoteId,action,orderId,selected=decision)=>{
        const context=await call('/api/identity/decision-context?quoteId='+encodeURIComponent(quoteId)+'&action='+action+(orderId?'&orderId='+encodeURIComponent(orderId):''));
        return mint('scripted-test-reviewer',{...context,reviewerGrantRevision:grants[1].revision,decision:selected});
      };
      const open=async()=>{
        server=createPersistentTradeServer({stateFile:join(runDirectory,'server.sqlite'),identity,clock:now,
          afterCommitBeforeRespond(request){
            if(armed.order&&/\/commit$/.test(request.url)){armed.order=false;losses.order++;request.socket.destroy();}
            if(armed.payment&&/\/settlement$/.test(request.url)){armed.payment=false;losses.payment++;request.socket.destroy();}
          }});
        const requestedPort=port;
        server.listen(port??0,'127.0.0.1');await once(server,'listening');port=server.address().port;
        if(requestedPort!==undefined)assert.equal(port,requestedPort);
        base='http://127.0.0.1:'+port;
        client=await createTradeClient({baseUrl:base,stateFile:join(runDirectory,'buyer.sqlite'),hostAccessToken:access,
          hostDecisionProof:async context=>({proof:await proofFor(context.quoteId,context.action,context.orderId,decision),decision})});
      };
      const stop=async()=>{try{client?.close();}finally{client=null;await closeServer(server);server=null;}};
      const audit=async()=>{
        const entries=[],seen=new Set();let cursor=null,pages=0,through,snapshot;
        do{
          if(++pages>10)throw failure('SIMULATION_AUDIT_PAGE_INVALID');
          const page=await call('/api/audit?limit=100'+(cursor?'&cursor='+encodeURIComponent(cursor):'')),meta=page.page;
          if(!Array.isArray(page.receipts)||page.receipts.length>100||!object(meta)||
              !Number.isSafeInteger(meta.through)||meta.through<0||meta.through>1000||
              meta.returned!==page.receipts.length||!Number.isSafeInteger(meta.limit)||meta.limit<1||meta.limit>100||
              typeof meta.complete!=='boolean'||typeof meta.snapshotId!=='string'||!meta.snapshotId.length||meta.snapshotId.length>2048||
              !(meta.nextCursor===null||(typeof meta.nextCursor==='string'&&/^[A-Za-z0-9_-]{1,2048}$/.test(meta.nextCursor)))||
              page.receipts.some(entry=>!object(entry)||typeof entry.event!=='string'||!/^[A-Z0-9_]{1,100}$/.test(entry.event)||
                typeof entry.id!=='string'||!/^[A-Z]+-DEMO-[0-9]+$/.test(entry.id)))throw failure('SIMULATION_AUDIT_PAGE_INVALID');
          if(through!==undefined&&(through!==meta.through||snapshot!==meta.snapshotId))throw failure('SIMULATION_AUDIT_SNAPSHOT_CHANGED');
          through=meta.through;snapshot=meta.snapshotId;entries.push(...page.receipts);cursor=meta.nextCursor;
          if(entries.length>through||(cursor&&(page.receipts.length===0||seen.has(cursor))))throw failure('SIMULATION_AUDIT_PAGE_INVALID');
          if(cursor)seen.add(cursor);
        }while(cursor);
        if(entries.length!==through)throw failure('SIMULATION_AUDIT_INCOMPLETE');
        return entries;
      };
      const counts=async()=>{
        const events=await audit();return {orders:events.filter(event=>event.event==='ORDER_SIMULATED').length,
          transfers:events.filter(event=>event.event==='DEMO_MONEY_TRANSFER_SETTLED').length,
          refunds:events.filter(event=>event.event==='DEMO_PAYMENT_REVERSED').length};
      };
      const wallet=async()=>(await call('/api/demo/wallet')).wallet.buyerBalanceCents;
      const prepare=key=>client.prepare({commandKey:key,budgetCents:140000,requirements});
      const approve=async(run,key)=>{const context=await client.reviewContext(run.run.id);return client.decide(run.run.id,key,'approve',context.binding);};
      const settle=async(run,key)=>{const context=await client.paymentContext(run.run.id);return client.settle(run.run.id,key,context.binding,context.pay.proposal.digest);};
      await open();
      await step('identity','Paikallinen testi-identiteetti ja tallennus avataan',async()=>{
        const me=await call('/api/identity/me');assert.equal(me.mode,'HOST_AUTHENTICATED');assert.equal(me.principalType,'AGENT');assert.equal(me.commerce,'SYNTHETIC');
        return {identity:'SCRIPTED_TEST_ACTORS',verification:'REAL_LOCAL_JOSE_SIGNATURES',commerce:'SYNTHETIC'};
      });
      const initialBalance=await wallet();summary.initialBalanceCents=initialBalance;
      if(definition.id==='shortage'){
        await step('stock-empty','Maidon kaksi toimituskelpoista varastoerää tyhjennetään',async()=>{
          for(const sku of ['DEMO-LF-1','DEMO-LF-2'])await call('/api/demo/shock',{sku,unitsAvailable:0});return {availableLitres:0,inventoryGrant:'SCRIPTED_TEST_ONLY'};
        });
        await step('no-substitution','Puutetta ei korvata kaurajuomalla',async()=>{
          const run=await prepare('simulation-shortage-prepare');assert.equal(run.quote,null);assert.equal(run.run.status,'BLOCKED');
          assert.equal(run.originalIntent.requirements[0].family,'dairy-milk');assert.ok(run.review.diagnosis.missingLitres>0);
          return {status:run.run.status,missingLitres:run.review.diagnosis.missingLitres,substitutions:0};
        });
      }else{
        let run;
        await step('prepare','Agentti pyytää 1 000 litraa täsmällisillä rajoilla',async()=>{
          run=await prepare('simulation-initial-prepare');assert.ok(run.quote);assert.equal(run.quote.budgetException.scope,'THIS_QUOTE_ONLY');
          assert.equal(run.quote.budgetException.additionalCents,run.quote.totalCents-140000);
          assert.equal(run.quote.lines.reduce((sum,line)=>sum+line.quantityLitres,0),1000);
          assert.ok(run.quote.lines.every(line=>line.family==='dairy-milk'));
          Object.assign(summary,{quoteId:run.quote.id,totalCents:run.quote.totalCents,budgetGapCents:run.quote.budgetException.additionalCents});
          return {quoteId:run.quote.id,totalCents:run.quote.totalCents,budgetCents:140000,additionalBudgetCents:run.quote.budgetException.additionalCents};
        });
        if(definition.id==='expired'){
          const context=await call('/api/identity/decision-context?quoteId='+run.quote.id+'&action=QUOTE_DECISION');
          const oldProof=await mint('scripted-test-reviewer',{...context,reviewerGrantRevision:1,decision:'approve'});
          assert.ok(Number.isSafeInteger(context.expiresAtMs));
          const advancedClockMs=Math.max(121000,context.expiresAtMs-now()+1);clockOffset+=advancedClockMs;
          const payload={buyerId,quoteId:run.quote.id,snapshotId:run.quote.snapshotId,decision:'approve'};
          await step('proof-expired','Vanhentunut hyväksyntä torjutaan hallitulla kellolla',()=>refused(()=>call('/api/agent/runs/'+run.run.id+'/decision',payload,oldProof),['HOST_ASSERTION_INVALID']),['HOST_ASSERTION_INVALID']);
          const freshProof=await mint('scripted-test-reviewer',{...context,reviewerGrantRevision:1,decision:'approve'});
          await step('quote-expired','Uusi allekirjoitus ei elvytä vanhentunutta tarjousta',()=>refused(()=>call('/api/agent/runs/'+run.run.id+'/decision',payload,freshProof),['QUOTE_EXPIRED']),['QUOTE_EXPIRED']);
          summary.advancedClockMs=advancedClockMs;
        }else if(definition.id==='stale'){
          const oldProof=await proofFor(run.quote.id,'QUOTE_DECISION'),oldSnapshot=run.quote.snapshotId;
          await step('price-change','Synteettinen hinta muuttuu tarjouksen jälkeen',async()=>{await call('/api/demo/reprice',{sku:'DEMO-LF-1',priceCents:175});return {newUnitPriceCents:175};});
          await step('stale-refusal','Vanhan lähteen hyväksyntä estetään palvelimella',()=>refused(()=>call('/api/agent/runs/'+run.run.id+'/decision',
            {buyerId,quoteId:run.quote.id,snapshotId:run.quote.snapshotId,decision:'approve'},oldProof),['QUOTE_STALE']),['QUOTE_STALE']);
          await step('no-old-effect','Vanhasta ehdotuksesta ei synny tilausta tai maksua',async()=>{const value=await counts();assert.equal(value.orders,0);assert.equal(value.transfers,0);return value;});
          await step('fresh-consent','Uusi lähdeversio hyväksytään erikseen ja perutaan tilauksen jälkeen',async()=>{
            run=await prepare('simulation-fresh-prepare');assert.notEqual(run.quote.snapshotId,oldSnapshot);await approve(run,'simulation-fresh-review');
            const committed=await client.commit(run.run.id,'simulation-fresh-commit');assert.equal(committed.order.status,'SIMULATED_COMMITTED');
            const cancelled=await client.cancel(run.run.id,'simulation-fresh-cancel');assert.equal(cancelled.order.status,'SIMULATED_CANCELLED');
            Object.assign(summary,{originalQuoteId:summary.quoteId,originalTotalCents:summary.totalCents,quoteId:run.quote.id,
              totalCents:run.quote.totalCents,budgetGapCents:run.quote.budgetException.additionalCents,orderId:committed.order.id});
            return {newQuoteId:run.quote.id,newSnapshot:true,totalCents:run.quote.totalCents,additionalBudgetCents:run.quote.budgetException.additionalCents,
              orderId:committed.order.id,cancelled:cancelled.order.status==='SIMULATED_CANCELLED'};
          });
        }else if(definition.id==='reject'){
          decision='reject';
          await step('reject','Skriptattu testi-ihminen allekirjoittaa hylkäyksen',async()=>{const result=await approve(run,'simulation-reject-review');assert.equal(result.quote.status,'REJECTED');return {status:result.quote.status};});
          await step('commit-refused','Hylkäys ei anna agentille tilausvaltuutta',()=>refused(()=>client.commit(run.run.id,'simulation-reject-commit'),['CALLER_APPROVAL_MISSING','HUMAN_APPROVAL_REQUIRED']),['CALLER_APPROVAL_MISSING','HUMAN_APPROVAL_REQUIRED']);
        }else{
          await step('approve','Skriptattu testi-ihminen hyväksyy vain tämän tarjouksen',async()=>{const result=await approve(run,'simulation-approve-review');assert.equal(result.quote.status,'APPROVED');return {status:result.quote.status,scope:'THIS_QUOTE_ONLY'};});
          if(definition.id==='revoked'){
            grants[1].active=false;
            await step('reviewer-revoked','Hyväksyjän oikeuden peruminen estää tilauksen',()=>refused(()=>client.commit(run.run.id,'simulation-revoked-commit'),['IDENTITY_REVOKED']),['IDENTITY_REVOKED']);
          }else{
            if(definition.id==='retry'){
              armed.order=true;
              await step('order-ack-lost','Tilauksen COMMIT onnistuu mutta HTTP-kuittaus katoaa',()=>refused(()=>client.commit(run.run.id,'simulation-order-commit'),['HTTP_UNAVAILABLE','HTTP_DEADLINE']),['HTTP_UNAVAILABLE','HTTP_DEADLINE']);
              await step('order-restart','Palvelin ja ostaja avataan samoista tallennetuista tiedoista',async()=>{await stop();await open();assert.equal(losses.order,1);return {serverRestarted:true,buyerRestarted:true,originalPortPreserved:true};});
            }
            await step('commit','Riippumaton ostaja allekirjoittaa ja saa yhden kuitin',async()=>{
              const result=await client.commit(run.run.id,'simulation-order-commit');assert.equal(result.order.status,'SIMULATED_COMMITTED');summary.orderId=result.order.id;
              const value=await counts();assert.equal(value.orders,1);return {orderId:result.order.id,orders:value.orders,commitment:'SIMULATED_ONLY'};
            });
            if(definition.id==='retry'){
              armed.payment=true;
              await step('payment-ack-lost','Erillinen maksu kirjautuu mutta HTTP-kuittaus katoaa',()=>refused(()=>settle(run,'simulation-payment-settle'),['HTTP_UNAVAILABLE','HTTP_DEADLINE']),['HTTP_UNAVAILABLE','HTTP_DEADLINE']);
              await step('payment-restart','Maksun jälkeen avataan sama palvelin ja ostaja uudelleen',async()=>{await stop();await open();assert.equal(losses.payment,1);return {serverRestarted:true,buyerRestarted:true,originalPortPreserved:true};});
            }
            await step('separate-payment','Maksu vaatii oman hyväksynnän eikä toistu uusinnassa',async()=>{
              await settle(run,'simulation-payment-settle');const value=await counts();assert.equal(value.orders,1);assert.equal(value.transfers,1);
              assert.equal(await wallet(),initialBalance-run.quote.totalCents);return {amountCents:run.quote.totalCents,orders:1,transfers:1};
            });
            await step('refund','Peruutus palauttaa koko testisumman ja tasapainoisen kirjanpidon',async()=>{
              const result=await client.cancel(run.run.id,'simulation-refund-cancel');assert.equal(result.order.status,'SIMULATED_CANCELLED');
              assert.equal(await wallet(),initialBalance);const verified=await call('/api/demo/ledger/verify');assert.equal(verified.valid,true);
              const value=await counts();assert.equal(value.refunds,1);return {...value,balanceCents:initialBalance,journalValid:true};
            });
            if(definition.id==='retry')Object.assign(summary,{lostOrderAcks:losses.order,lostPaymentAcks:losses.payment,serverRestarts:2});
          }
        }
      }
      await step('final-invariants','Toteutuneet vaikutukset ja testilompakon saldo tarkistetaan',async()=>{
        const value=await counts(),balance=await wallet();
        const hasOrder=['purchase','retry','stale'].includes(definition.id);
        assert.equal(value.orders,hasOrder?1:0);assert.equal(value.transfers,['purchase','retry'].includes(definition.id)?1:0);
        assert.equal(balance,initialBalance);Object.assign(summary,value,{finalBalanceCents:balance});return {...value,balanceCents:balance,externalProviderCalls:0};
      });
      return report={scenarioId:definition.id,title:definition.title,outcome:'PASS',steps,elapsedMs:milliseconds(started),summary,externalProviderCalls:0};
    }catch(error){
      return report={scenarioId:definition.id,title:definition.title,outcome:'FAIL',steps,elapsedMs:milliseconds(started),summary:{...summary,failureCode:safeCode(error)},externalProviderCalls:0};
    }finally{
      let cleanupFailed=false;
      try{client?.close();}catch{cleanupFailed=true;}
      try{await closeServer(server);}catch{cleanupFailed=true;}
      if(report){
        report.summary.resourcesClosed=!cleanupFailed;
        if(cleanupFailed){report.outcome='FAIL';report.summary.failureCode='SIMULATION_CLEANUP_FAILED';
          report.steps.push({id:'cleanup',title:'Paikalliset resurssit suljetaan',outcome:'FAIL',observed:{code:'SIMULATION_CLEANUP_FAILED'}});}
      }
    }
  };
  return Object.freeze({mode:'LOCAL_SIMULATION',
    runScenario(id){
      if(closing)throw failure('SIMULATION_LAB_CLOSED');
      const definition=scenarios.find(value=>value.id===id);if(!definition)throw failure('SIMULATION_SCENARIO_UNKNOWN');
      const pending=execute(definition);active.add(pending);pending.then(()=>active.delete(pending),()=>active.delete(pending));return pending;
    },
    async close(){closing=true;await Promise.allSettled([...active]);},
  });
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  let lab;
  try{lab=await createSimulationLab();const reports=[];for(const scenario of scenarios)reports.push(await lab.runScenario(scenario.id));
    console.log(JSON.stringify({mode:'LOCAL_SIMULATION',outcome:reports.every(report=>report.outcome==='PASS')?'PASS':'FAIL',reports,externalProviderCalls:0}));
    if(reports.some(report=>report.outcome!=='PASS'))process.exitCode=1;
  }catch(error){console.error(JSON.stringify({mode:'LOCAL_SIMULATION',outcome:'FAIL',code:safeCode(error),externalProviderCalls:0}));process.exitCode=1;}
  finally{await lab?.close();}
}
