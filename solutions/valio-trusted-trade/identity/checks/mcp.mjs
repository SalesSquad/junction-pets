import { tmpdir } from 'node:os';
/** Official SDK -> private host files -> real JOSE -> persistent HTTP. Synthetic commerce only. */
import assert from 'node:assert/strict';
import { generateKeyPair, exportJWK, SignJWT } from 'jose';
import { createRequire } from 'node:module';
const fromMcp=createRequire(new URL('../../mcp/package.json',import.meta.url));
const { Client }=await import(fromMcp.resolve('@modelcontextprotocol/client'));
const { StdioClientTransport }=await import(fromMcp.resolve('@modelcontextprotocol/client/stdio'));
import { once } from 'node:events';
import { realpath, mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createJwtHostVerifier } from '../jwt-host.mjs';
import { createBuyerIdentity } from '../../src/buyer-identity.mjs';
import { createPersistentTradeServer } from '../../src/server.mjs';

const issuer='https://mcp-host-fixture.invalid',buyerId='helsinki-hotel-demo';
const keys=await generateKeyPair('EdDSA'),jwk={...await exportJWK(keys.publicKey),kid:'test-host',alg:'EdDSA'};
const verifier=await createJwtHostVerifier({issuer,accessAudience:'trade-api',decisionAudience:'trade-consent',jwks:{keys:[jwk]},algorithms:['EdDSA']});
const identity=createBuyerIdentity({profileId:'sdk-host-fixture',issuer,verifier,grants:[
  {subject:'test-agent',buyerId,ownerScope:'kitchen',principalType:'AGENT',active:true,revision:1,actions:['read','prepare','commit','cancel','relay_decision'],maxOrderCents:250000},
  {subject:'test-reviewer',buyerId,ownerScope:'kitchen',principalType:'HUMAN',active:true,revision:1,actions:['read','approve','pay'],maxOrderCents:250000},
]});
const mint=(subject,claims=null)=>new SignJWT(claims??{}).setIssuer(issuer).setSubject(subject)
  .setAudience(claims?'trade-consent':'trade-api').setProtectedHeader({alg:'EdDSA',kid:'test-host',typ:claims?'buyer-decision+jwt':'at+jwt'})
  .setIssuedAt().setExpirationTime(claims?'120s':'600s').setJti(crypto.randomUUID()).sign(keys.privateKey);
const directory=await realpath(await mkdtemp(join(tmpdir(),'valio-jose-sdk-'))),accessFile=join(directory,'host-access'),proofFile=join(directory,'host-proof'),stateFile=join(directory,'buyer.sqlite');
const access=await mint('test-agent');await writeFile(accessFile,access,{mode:0o600});
await writeFile(proofFile,'NO_APPROVAL_PROOF',{mode:0o600});
const server=createPersistentTradeServer({stateFile:join(directory,'server.sqlite'),identity});
server.listen(0,'127.0.0.1');await once(server,'listening');
const base='http://127.0.0.1:'+server.address().port;
const client=new Client({name:'real-signed-host-check',version:'0.1.0'},{versionNegotiation:{mode:{pin:'2026-07-28'}}});
const transport=new StdioClientTransport({command:process.execPath,args:[fileURLToPath(new URL('../../mcp/server.mjs',import.meta.url))],
  env:{PATH:process.env.PATH??'',SUPPLIER_URL:base,VALIO_AGENT_STATE_FILE:stateFile,VALIO_HOST_ACCESS_TOKEN_FILE:accessFile,VALIO_HOST_DECISION_PROOF_FILE:proofFile},stderr:'pipe'});
let stderr='';transport.stderr.on('data',chunk=>stderr+=chunk.toString());
const tool=async(name,args)=>{const r=await client.callTool({name,arguments:args});assert.notEqual(r.isError,true,JSON.stringify(r));return r.structuredContent.data;};
const proofFor=async(quoteId,action,orderId,decision='approve')=>{
  const path='/api/identity/decision-context?quoteId='+quoteId+'&action='+action+(orderId?'&orderId='+orderId:'');
  const response=await fetch(base+path,{headers:{Authorization:'Bearer '+access}});assert.equal(response.status,200);
  const context=await response.json();
  const proof=await mint('test-reviewer',{...context,reviewerGrantRevision:1,decision});
  await writeFile(proofFile,proof,{mode:0o600});return proof;
};
try {
  await client.connect(transport,{timeout:10000});
  assert.equal((await client.listTools()).tools.length,8);
  const prepared=await tool('prepare_purchase',{commandKey:'real-host-prepare-key',budgetCents:140000,
    requirements:[{family:'dairy-milk',quantityLitres:1000,lactoseFree:true,deliverBy:'2026-11-16'}]});
  const runId=prepared.run.id,quoteId=prepared.quote.id;
  const quoteProof=await proofFor(quoteId,'QUOTE_DECISION');
  await tool('review_purchase',{runId,commandKey:'real-host-review-key'});
  const committed=await tool('commit_purchase',{runId,commandKey:'real-host-commit-key'});
  assert.equal(committed.order.status,'SIMULATED_COMMITTED');
  const payProof=await proofFor(quoteId,'PAYMENT_DECISION',committed.order.id);
  await tool('settle_purchase',{runId,commandKey:'real-host-payment-key'});
  const cancelled=await tool('cancel_purchase',{runId,commandKey:'real-host-cancel-key'});
  assert.equal(cancelled.order.status,'SIMULATED_CANCELLED');
  const rejectedPrepared=await tool('prepare_purchase',{commandKey:'signed-reject-prepare',budgetCents:140000,
    requirements:[{family:'dairy-milk',quantityLitres:1000,lactoseFree:true,deliverBy:'2026-11-16'}]});
  await proofFor(rejectedPrepared.quote.id,'QUOTE_DECISION',undefined,'reject');
  const rejected=await tool('review_purchase',{runId:rejectedPrepared.run.id,commandKey:'signed-reject-review'});
  assert.equal(rejected.quote.status,'REJECTED');
  const refusedCommit=await client.callTool({name:'commit_purchase',arguments:{runId:rejectedPrepared.run.id,commandKey:'signed-reject-commit'}});
  assert.equal(refusedCommit.isError,true);
  const payRejectPrepared=await tool('prepare_purchase',{commandKey:'signed-pay-reject-prepare',budgetCents:140000,
    requirements:[{family:'dairy-milk',quantityLitres:1000,lactoseFree:true,deliverBy:'2026-11-16'}]});
  await proofFor(payRejectPrepared.quote.id,'QUOTE_DECISION');
  await tool('review_purchase',{runId:payRejectPrepared.run.id,commandKey:'signed-pay-reject-review'});
  const payRejectOrder=await tool('commit_purchase',{runId:payRejectPrepared.run.id,commandKey:'signed-pay-reject-commit'});
  await proofFor(payRejectPrepared.quote.id,'PAYMENT_DECISION',payRejectOrder.order.id,'reject');
  await tool('settle_purchase',{runId:payRejectPrepared.run.id,commandKey:'signed-payment-rejection'});
  const paymentResponse=await fetch(base+'/api/orders/'+payRejectOrder.order.id+'/payment',{headers:{Authorization:'Bearer '+access}});
  const rejectedPayment=await paymentResponse.json();
  assert.equal(rejectedPayment.approval.decision,'reject');assert.equal(rejectedPayment.transfer,null);
  await tool('cancel_purchase',{runId:payRejectPrepared.run.id,commandKey:'signed-pay-reject-cancel'});
  await client.close();
  const bytes=await readFile(stateFile);
  for(const secret of [access,quoteProof,payProof,'test-agent','test-reviewer']) assert.equal(bytes.includes(Buffer.from(secret)),false);
  assert.equal(stderr.includes(access),false);assert.equal(stderr.includes(quoteProof),false);
  console.log(JSON.stringify({check:'official-sdk-real-host-signatures',outcome:'PASS',tools:8,
    hostSignedQuoteAndSeparatePayment:true,signedQuoteAndPaymentRejections:true,syntheticCommitSettleRefund:true,modelConsentInputs:0,rawHostCredentialsStored:false,providerCalls:0}));
} finally {await client.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
