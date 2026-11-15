import { tmpdir } from 'node:os';
/** Real JOSE signatures through HTTP and persistent synthetic commerce; no provider calls. */
import assert from 'node:assert/strict';
import { generateKeyPair, exportJWK, SignJWT } from 'jose';
import { generateKeyPairSync, randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { realpath, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createJwtHostVerifier } from '../jwt-host.mjs';
import { loadBuyerIdentity } from '../../src/identity-config.mjs';
import { createPersistentTradeServer } from '../../src/server.mjs';
import { digest, makeDemoMandatePayload, signDemoEnvelope } from '../../src/trust-envelope.mjs';
import { unsignedQuoteBody } from '../../src/core.mjs';

const issuer='https://private-host.example.invalid', buyerId='helsinki-hotel-demo';
const keys=await generateKeyPair('EdDSA'), jwk={...await exportJWK(keys.publicKey),kid:'fixture-host-v1',alg:'EdDSA'};
const verifier=await createJwtHostVerifier({issuer,accessAudience:'valio-local-api',decisionAudience:'valio-local-decisions',jwks:{keys:[jwk]},algorithms:['EdDSA']});
const grants=[
  {subject:'test-only-agent',buyerId,ownerScope:'kitchen-a',principalType:'AGENT',active:true,revision:1,actions:['read','prepare','commit','cancel','relay_decision'],maxOrderCents:250000},
  {subject:'test-only-reviewer',buyerId,ownerScope:'kitchen-a',principalType:'HUMAN',active:true,revision:1,actions:['read','approve','pay'],maxOrderCents:250000},
];
const directory=await realpath(await mkdtemp(join(tmpdir(),'valio-real-jwt-http-'))),stateFile=join(directory,'state.sqlite'),configFile=join(directory,'identity.json');
const config={profileId:'fixture-host-v1',issuer,accessAudience:'valio-local-api',decisionAudience:'valio-local-decisions',jwks:{keys:[jwk]},algorithms:['EdDSA'],grants};
await writeFile(configFile,JSON.stringify(config),{mode:0o600});
const identity=await loadBuyerIdentity(configFile);
const mint=async (sub,decision=null,extra={})=>new SignJWT({...decision,...extra}).setProtectedHeader({alg:'EdDSA',kid:jwk.kid,typ:decision?'buyer-decision+jwt':'at+jwt'})
  .setIssuer(issuer).setAudience(decision?'valio-local-decisions':'valio-local-api').setSubject(sub).setIssuedAt().setExpirationTime(decision?'120s':'600s').setJti(randomUUID()).sign(keys.privateKey);
let access=await mint('test-only-agent'),server,base,serial=0;
const start=async()=>{server=createPersistentTradeServer({stateFile,identity});server.listen(0,'127.0.0.1');await once(server,'listening');base='http://127.0.0.1:'+server.address().port;};
const stop=async()=>{if(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));server=null;}};
const call=async(path,body,proof,expected=body?200:200,key='signed-http-'+ ++serial)=>{
  const response=await fetch(base+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',Authorization:'Bearer '+access,
    ...(body?{'Idempotency-Key':key}:{}),...(proof?{'X-Buyer-Decision-Proof':proof}:{})},body:body?JSON.stringify(body):undefined});
  const value=await response.json();assert.equal(response.status,expected,JSON.stringify(value));return value;
};
try {
  await start();
  const me=await call('/api/identity/me');
  const run=await call('/api/agent/prepare',{buyerId,budgetCents:140000,requirements:[{family:'dairy-milk',lactoseFree:true,quantityLitres:1000,deliverBy:'2026-11-16'}]},null,201,'signed-http-prepare');
  let q=(await call('/api/quotes/'+run.quote.id)).quote;
  const context=await call('/api/identity/decision-context?quoteId='+q.id+'&action=QUOTE_DECISION');
  const claims={...context,reviewerGrantRevision:1,decision:'approve'};
  const wrong=await mint('test-only-agent',claims);
  await call('/api/agent/runs/'+run.run.id+'/decision',{buyerId,quoteId:q.id,snapshotId:q.snapshotId,decision:'approve'},wrong,403);
  const proof=await mint('test-only-reviewer',claims);
  await call('/api/agent/runs/'+run.run.id+'/decision',{buyerId,quoteId:q.id,snapshotId:q.snapshotId,decision:'approve'},proof,200,'signed-http-decision');
  const buyer=generateKeyPairSync('ed25519');
  const {kid}=await call('/api/trust/buyer-key',{buyerId,publicJwk:buyer.publicKey.export({format:'jwk'})},null,201);
  q=(await call('/api/quotes/'+q.id)).quote;
  const {signedOffer}=await call('/api/quotes/'+q.id+'/offer',{buyerId},null,201);
  const signedMandate=signDemoEnvelope(buyer.privateKey,kid,makeDemoMandatePayload({quote:q,signedOffer,now:Date.now(),nonce:randomUUID()}));
  await call('/api/quotes/'+q.id+'/handshake',{buyerId,signedMandate},null,201);
  const committed=await call('/api/agent/runs/'+run.run.id+'/commit',{buyerId,idempotencyKey:'signed-http-order-body'},null,200,'signed-http-commit');
  const order=committed.order;
  const payment=await call('/api/orders/'+order.id+'/payment');
  await call('/api/orders/'+order.id+'/payment-approval',{buyerId,decision:'approve',proposalDigest:payment.proposal.digest},proof,403);
  const payScope=await call('/api/identity/decision-context?quoteId='+q.id+'&action=PAYMENT_DECISION&orderId='+order.id);
  const payProof=await mint('test-only-reviewer',{...payScope,reviewerGrantRevision:1,decision:'approve'});
  await call('/api/orders/'+order.id+'/payment-approval',{buyerId,decision:'approve',proposalDigest:payment.proposal.digest},payProof,200,'signed-http-pay-approval');
  grants[1].active=false;await writeFile(configFile,JSON.stringify(config),{mode:0o600});
  await call('/api/orders/'+order.id+'/settlement',{buyerId,idempotencyKey:'signed-http-transfer'},null,403,'signed-http-settlement');
  grants[1].active=true;await writeFile(configFile,JSON.stringify(config),{mode:0o600});
  await call('/api/orders/'+order.id+'/settlement',{buyerId,idempotencyKey:'signed-http-transfer'},null,201,'signed-http-settlement');
  const paid=(await call('/api/orders/'+order.id+'/payment')).transfer;
  assert.ok(paid);
  await stop();await start();access=await mint('test-only-agent');
  assert.equal((await call('/api/identity/me')).ownerRef,me.ownerRef);
  assert.equal((await call('/api/agent/runs/'+run.run.id)).run.orderId,order.id);
  assert.deepEqual((await call('/api/orders/'+order.id+'/payment')).transfer,paid);
  const handoff=await call('/api/orders/'+order.id+'/supplier-handoff');
  assert.equal(handoff.sendAllowed,false);assert.equal(handoff.references.orderId,order.id);
  await call('/api/agent/runs/'+run.run.id+'/cancel',{buyerId},null,200,'signed-http-cancel');
  assert.equal((await call('/api/orders/'+order.id+'/payment')).transfer.status,'SIMULATED_REFUNDED');
  grants[0].active=false;await writeFile(configFile,JSON.stringify(config),{mode:0o600});
  await call('/api/identity/me',undefined,undefined,403);
  grants[0].active=true;grants[0].revision++;await writeFile(configFile,JSON.stringify(config),{mode:0o600});
  assert.equal((await call('/api/identity/me')).grantRevision,2);
  await stop();
  const bytes=await readFile(stateFile);
  for(const prohibited of [access,proof,payProof,'test-only-agent','test-only-reviewer']) assert.equal(bytes.includes(Buffer.from(prohibited)),false);
  console.log(JSON.stringify({check:'signed-host-http-trade',outcome:'PASS',realJoseSignatures:true,stableOwnerAfterRotationRestart:true,
    machineCannotSelfApprove:true,privateConfigRevocationWithoutRestart:true,reviewerRevocationStopsSettlement:true,quoteProofCannotApprovePayment:true,syntheticSettlementRefund:true,nonSendableHandoff:true,rawHostCredentialsStored:false,providerCalls:0}));
} finally {await stop();}
