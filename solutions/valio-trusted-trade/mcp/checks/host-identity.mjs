/** Callback/transport qualification only. Fake host assertions do not prove an identity issuer. */
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, chmod, symlink, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { randomUUID, generateKeyPairSync, sign, verify } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { createTradeClient, privateHostCredentialFile } from '../trade-client.mjs';
import { createTradeService, unsignedQuoteBody } from '../../src/core.mjs';
import { openLocalStateStore } from '../../src/local-state-store.mjs';
import { digest } from '../../src/trust-envelope.mjs';

const BUYER='helsinki-hotel-demo';
const accessMarker='TESTACCESS', proofMarker='TESTPROOF';
const need={family:'dairy-milk',lactoseFree:true,quantityLitres:1000,deliverBy:'2026-11-16'};
const prepared={commandKey:'host-prepare-command-001',requirements:[need],budgetCents:140000};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
const initialIdentity={mode:'HOST_AUTHENTICATED',commerce:'SYNTHETIC',buyerId:BUYER,
  actorRef:'actor_test_001',ownerRef:'owner_test_001',profileId:'profile_test_001',principalType:'AGENT',actions:['read','prepare','commit','relay_decision'],grantRevision:1};
function backend(requireHostProof=true){
  const service=createTradeService();
  let quoteId,reviewId,serial=0;
  const calls=[],replays=new Map();
  const state={identity:{...initialIdentity},lostDecisionAck:false,decisionEffects:0,paymentDecisionEffects:0,settlementEffects:0,order:null,payment:null,verifyProof:null};
  const full=()=>{
    const q=service.quote(quoteId),quote=state.order?{...q,orderId:state.order.id,status:'SIMULATED_COMMITTED'}:q;
    return {mode:'SYNTHETIC',run:{id:'RUN-DEMO-HOST-001',buyerId:BUYER,quoteId,reviewId,status:quote.status,...(state.order?{orderId:state.order.id}:{})},
      quote,policy:service.policy(),nextActions:['request_human_approval'],...(state.order?{order:state.order,payment:state.payment}:{})};
  };
  const respond=async(url,init={})=>{
    const path=new URL(url).pathname,method=init.method??'GET',headers=new Headers(init.headers);
    const body=init.body===undefined?undefined:JSON.parse(init.body);
    calls.push({path,method,authorization:headers.get('authorization'),proof:headers.get('x-buyer-decision-proof')});
    if(path==='/api/identity/me') return json(state.identity);
    if(path==='/api/demo/session') return json({mode:'SYNTHETIC_NOT_AUTHENTICATED',buyerId:BUYER,token:randomUUID()},201);
    if(path==='/api/products/search') return json({mode:'FIXTURE',candidates:[]});
    if(path==='/api/agent/prepare'){
      const made=service.requestReview({buyerId:BUYER,need:body.requirements[0],budgetCents:body.budgetCents});
      quoteId=made.quote.id;reviewId=made.review.id;serial++;
      return json(full(),201);
    }
    if(path==='/api/agent/runs/RUN-DEMO-HOST-001')return json(full());
    if(path==='/api/quotes/'+quoteId+'/body')return json({body:unsignedQuoteBody(service.quote(quoteId))});
    if(path==='/api/agent/runs/RUN-DEMO-HOST-001/decision'){
      if(requireHostProof)assert.ok(headers.get('x-buyer-decision-proof'));
      state.verifyProof?.(headers.get('x-buyer-decision-proof'),body,'QUOTE_DECISION');
      const key=headers.get('idempotency-key');assert.ok(key);
      if(replays.has(key))return json(replays.get(key));
      service.decideReview({...body,reviewId});state.decisionEffects++;
      const result=full();replays.set(key,result);
      if(state.lostDecisionAck){state.lostDecisionAck=false;return json({error:{code:'ACK_LOST'}},503);}
      return json(result);
    }
    if(state.order&&path==='/api/orders/'+state.order.id+'/payment')return json(state.payment);
    if(state.order&&path==='/api/orders/'+state.order.id+'/payment-approval'){
      state.verifyProof?.(headers.get('x-buyer-decision-proof'),body,'PAYMENT_DECISION');
      assert.equal(body.proposalDigest,state.payment.proposal.digest);
      state.paymentDecisionEffects++;state.payment.approval={decision:body.decision};return json(state.payment);
    }
    if(path.endsWith('/settlement')){state.settlementEffects++;throw Error('Unexpected settlement after rejection');}
    throw Error('Unexpected fixture operation: '+path);
  };
  return {state,calls,respond,full};
}
const directory=await realpath(await mkdtemp(join(tmpdir(),'valio-mcp-host-check-')));
const readState=file=>{const store=openLocalStateStore(file);try{return store.read().value;}finally{store.close();}};
const host=backend();let accessCalls=0,proofCalls=0;
const hostAccessToken=async()=>accessMarker+'.'+(++accessCalls)+'.signature';
const hostDecisionProof=async context=>{
  proofCalls++;assert.equal(context.action,'QUOTE_DECISION');assert.equal(context.decision,'approve');
  assert.equal(context.buyerId,BUYER);assert.equal(context.ownerRef,initialIdentity.ownerRef);assert.equal(context.profileId,initialIdentity.profileId);
  assert.match(context.quoteBodyDigest,/^[A-Za-z0-9_-]{43}$/);assert.ok(context.totalCents>prepared.budgetCents);
  return proofMarker+'.exact.signature';
};
const file=join(directory,'host.sqlite');
let client=await createTradeClient({stateFile:file,fetchImpl:host.respond,hostAccessToken,hostDecisionProof});
try{
  assert.equal(client.hostAuthenticated,true);
  await client.search('milk',2);await client.search('oat',2);
  assert.equal(host.calls.filter(c=>c.path==='/api/demo/session').length,0);
  assert.equal(accessCalls,3,'startup plus each workflow request obtains a fresh host token');
  const searches=host.calls.filter(c=>c.path==='/api/products/search');
  assert.notEqual(searches[0].authorization,searches[1].authorization);
  const beforeWrongOwner=host.calls.length;
  host.state.identity={...initialIdentity,ownerRef:'owner_other'};
  await assert.rejects(client.search('milk',2),{code:'CLIENT_IDENTITY_SCOPE_MISMATCH'});
  assert.deepEqual(host.calls.slice(beforeWrongOwner).map(c=>c.path),['/api/identity/me'],'owner mismatch refuses before workflow request');
  host.state.identity={...initialIdentity};
  const run=await client.prepare(prepared);assert.equal(run.run.id,'RUN-DEMO-HOST-001');
  let context=await client.reviewContext(run.run.id);
  host.state.lostDecisionAck=true;
  await assert.rejects(client.decide(run.run.id,'host-review-command-001','approve',context.binding),{code:'ACK_LOST'});
  assert.equal(readState(file).runs[0][1].acceptedScope,null,'unacknowledged host decision never creates local accepted scope');
  context=await client.reviewContext(run.run.id);
  assert.equal(context.q.status,'APPROVED');assert.equal(context.callerScopeAccepted,false);
  await client.decide(run.run.id,'host-review-command-001','approve',context.binding);
  assert.equal(host.state.decisionEffects,1);assert.equal(proofCalls,1,'same command reuses in-memory exact host proof after lost ACK');
  await client.decide(run.run.id,'host-review-command-001','approve',context.binding);
  assert.equal(proofCalls,2,'successful ACK discarded the previous raw proof from process memory');
  assert.equal(host.state.decisionEffects,1);
  const snapshot=JSON.stringify(readState(file));
  assert.equal(snapshot.includes(accessMarker),false);assert.equal(snapshot.includes(proofMarker),false);
  assert.equal(readState(file).runs[0][1].acceptedScope.binding,context.binding);
  client.close();
  client=await createTradeClient({stateFile:file,fetchImpl:host.respond,hostAccessToken,hostDecisionProof});
  await client.status(run.run.id);
  client.close();
  const before=JSON.stringify(readState(file));
  host.state.identity={...initialIdentity,profileId:'profile_other'};
  await assert.rejects(createTradeClient({stateFile:file,fetchImpl:host.respond,hostAccessToken}),{code:'CLIENT_IDENTITY_SCOPE_MISMATCH'});
  assert.equal(JSON.stringify(readState(file)),before,'failed profile restore preserves private workflow');
  await assert.rejects(createTradeClient({stateFile:file,fetchImpl:host.respond}),{code:'CLIENT_IDENTITY_SCOPE_MISMATCH'});
  host.state.identity={...initialIdentity};
}finally{client?.close();}
const demoFile=join(directory,'demo.sqlite');
const demo=await createTradeClient({stateFile:demoFile,fetchImpl:host.respond});
try{await demo.search('milk',2);}finally{demo.close();}
await assert.rejects(createTradeClient({stateFile:demoFile,fetchImpl:host.respond,hostAccessToken}),{code:'CLIENT_IDENTITY_SCOPE_MISMATCH'});
const demoRetryBackend=backend(false),demoRetryFile=join(directory,'demo-retry.sqlite');
const demoRetry=await createTradeClient({stateFile:demoRetryFile,fetchImpl:demoRetryBackend.respond});
try{
  const run=await demoRetry.prepare(prepared),context=await demoRetry.reviewContext(run.run.id),key='demo-review-lost-ack';
  const challenge=demoRetry.challenge(key,'review',run.run.id,context.binding,'Explicit scripted synthetic decision');
  demoRetry.authorizeChallenge(key,challenge.token,context.binding,'approve');
  demoRetryBackend.state.lostDecisionAck=true;
  await assert.rejects(demoRetry.decide(run.run.id,key,'approve',context.binding),{code:'ACK_LOST'});
  assert.equal(readState(demoRetryFile).runs[0][1].acceptedScope,null);
  const restored=await demoRetry.reviewContext(run.run.id);
  assert.equal(restored.callerScopeAccepted,false);
  await demoRetry.decide(run.run.id,key,'approve',restored.binding);
  assert.equal(demoRetryBackend.state.decisionEffects,1);
  assert.equal(readState(demoRetryFile).runs[0][1].acceptedScope.binding,context.binding);
}finally{demoRetry.close();}

const noProof=await createTradeClient({fetchImpl:host.respond,hostAccessToken});
try{
  const run=await noProof.prepare({...prepared,commandKey:'host-no-proof-prepare'});
  const context=await noProof.reviewContext(run.run.id);
  await assert.rejects(noProof.decide(run.run.id,'host-no-proof-decision','approve',context.binding),{code:'HOST_DECISION_REQUIRED'});
}finally{noProof.close();}
await assert.rejects(createTradeClient({fetchImpl:host.respond,hostAccessToken:async()=>{throw Error(accessMarker);}}),error=>error.code==='HTTP_UNAVAILABLE'&&!error.message.includes(accessMarker));
await assert.rejects(createTradeClient({fetchImpl:host.respond,hostAccessToken:async()=>new Promise(()=>{}),timeoutMs:20}),{code:'HTTP_DEADLINE'});
// Test-only signed host proofs: production verification remains the server's responsibility.
const signing=generateKeyPairSync('ed25519');
const signedProof=context=>{
  const parts=[Buffer.from(JSON.stringify({alg:'EdDSA',typ:'buyer-decision+jwt'})).toString('base64url'),
    Buffer.from(JSON.stringify({...context,jti:randomUUID(),iat:Math.floor(Date.now()/1000),exp:Math.floor(Date.now()/1000)+60})).toString('base64url')];
  return parts.join('.')+'.'+sign(null,Buffer.from(parts.join('.')),signing.privateKey).toString('base64url');
};
const verifySignedProof=(token,body,action)=>{
  const parts=token.split('.');assert.equal(verify(null,Buffer.from(parts.slice(0,2).join('.')),signing.publicKey,Buffer.from(parts[2],'base64url')),true);
  const payload=JSON.parse(Buffer.from(parts[1],'base64url').toString('utf8'));
  assert.equal(payload.decision,body.decision);assert.equal(payload.action,action);
};
const objectRejectBackend=backend(),objectRejectFile=join(directory,'object-reject.sqlite');
objectRejectBackend.state.verifyProof=verifySignedProof;
const objectReject=await createTradeClient({stateFile:objectRejectFile,fetchImpl:objectRejectBackend.respond,hostAccessToken,
  hostDecisionProof:async context=>({proof:signedProof({...context,decision:'reject'}),decision:'reject'})});
try{
  const run=await objectReject.prepare(prepared),context=await objectReject.reviewContext(run.run.id);
  const rejected=await objectReject.decide(run.run.id,'host-object-reject-001','approve',context.binding);
  assert.equal(rejected.quote.status,'REJECTED');assert.equal(readState(objectRejectFile).runs[0][1].acceptedScope,null);
}finally{objectReject.close();}
const tokenFile=join(directory,'access.jwt'),proofFile=join(directory,'proof.jwt');
await writeFile(tokenFile,accessMarker+'.file.signature',{mode:0o600});await writeFile(proofFile,proofMarker+'.file.signature',{mode:0o600});
assert.equal(await privateHostCredentialFile(tokenFile)(),accessMarker+'.file.signature');
await chmod(tokenFile,0o644);await assert.rejects(privateHostCredentialFile(tokenFile)(),{code:'HOST_CREDENTIAL_UNAVAILABLE'});await chmod(tokenFile,0o600);
const linked=join(directory,'linked.jwt');await symlink(tokenFile,linked);await assert.rejects(privateHostCredentialFile(linked)(),{code:'HOST_CREDENTIAL_UNAVAILABLE'});
await assert.rejects(privateHostCredentialFile(join(directory,'missing.jwt'))(),{code:'HOST_CREDENTIAL_UNAVAILABLE'});
const sdkBackend=backend();
const server=createServer(async(request,response)=>{
  try{
    const chunks=[];for await(const chunk of request)chunks.push(chunk);
    const result=await sdkBackend.respond('http://127.0.0.1'+request.url,{method:request.method,headers:request.headers,
      ...(chunks.length?{body:Buffer.concat(chunks).toString('utf8')}: {})});
    response.writeHead(result.status,{'Content-Type':'application/json'});response.end(await result.text());
  }catch{response.writeHead(500,{'Content-Type':'application/json'});response.end(JSON.stringify({error:{code:'FIXTURE_FAILURE'}}));}
});
server.listen(0,'127.0.0.1');await once(server,'listening');
const sdk=new Client({name:'host-identity-callback-check',version:'0.1.0'},{versionNegotiation:{mode:{pin:'2026-07-28'}}});
const stderr=[];
const transport=new StdioClientTransport({command:process.execPath,args:[fileURLToPath(new URL('../server.mjs',import.meta.url))],stderr:'pipe',
  env:{PATH:process.env.PATH??'',SUPPLIER_URL:'http://127.0.0.1:'+server.address().port,VALIO_HOST_ACCESS_TOKEN_FILE:tokenFile,VALIO_HOST_DECISION_PROOF_FILE:proofFile}});
transport.stderr.on('data',chunk=>stderr.push(chunk.toString()));
try{
  await sdk.connect(transport,{timeout:10000});
  const found=await sdk.listTools();assert.equal(found.tools.length,8);
  for(const tool of found.tools)for(const name of ['hostAccessToken','hostDecisionProof','token','credential','role'])assert.equal(tool.inputSchema.properties?.[name],undefined);
  const forbidden=await sdk.callTool({name:'prepare_purchase',arguments:{...prepared,hostAccessToken:accessMarker}});
  assert.equal(forbidden.isError,true);assert.equal(forbidden.structuredContent,undefined,'model credentials refuse at strict schema boundary');
  const made=await sdk.callTool({name:'prepare_purchase',arguments:prepared});assert.notEqual(made.isError,true,JSON.stringify(made));
  const approved=await sdk.callTool({name:'review_purchase',arguments:{runId:made.structuredContent.data.run.id,commandKey:'sdk-host-decision-001'}});
  assert.notEqual(approved.isError,true,JSON.stringify(approved));assert.equal(approved.structuredContent.data.quote.status,'APPROVED');
  assert.equal(sdkBackend.state.decisionEffects,1);assert.equal(sdkBackend.calls.some(c=>c.path==='/api/demo/session'),false);
  sdkBackend.state.verifyProof=verifySignedProof;
  const paidQuote=sdkBackend.full().quote,allocations=new Map();
  for(const line of paidQuote.lines)allocations.set(line.supplierId,(allocations.get(line.supplierId)??0)+line.totalCents);
  const unsignedProposal={orderId:'O-DEMO-HOST-001',amountCents:paidQuote.totalCents,currency:'EUR',
    signedQuoteBodyDigest:digest(unsignedQuoteBody(paidQuote)),allocations:[...allocations].map(([supplierId,amountCents])=>({supplierId,amountCents}))};
  sdkBackend.state.order={id:unsignedProposal.orderId,quoteId:paidQuote.id,status:'SIMULATED_COMMITTED',totalCents:paidQuote.totalCents};
  sdkBackend.state.payment={proposal:{...unsignedProposal,digest:digest(unsignedProposal)},transfer:null};
  await writeFile(proofFile,signedProof({action:'PAYMENT_DECISION',decision:'reject',orderId:unsignedProposal.orderId,
    paymentProposalDigest:sdkBackend.state.payment.proposal.digest}));
  const deniedPayment=await sdk.callTool({name:'settle_purchase',arguments:{runId:made.structuredContent.data.run.id,commandKey:'sdk-host-payment-reject-001'}});
  assert.notEqual(deniedPayment.isError,true,JSON.stringify(deniedPayment));assert.equal(deniedPayment.structuredContent.data.paymentApproval,'REJECTED');
  assert.equal(sdkBackend.state.paymentDecisionEffects,1);assert.equal(sdkBackend.state.settlementEffects,0);
  sdkBackend.state.order=null;sdkBackend.state.payment=null;
  const second=await sdk.callTool({name:'prepare_purchase',arguments:{...prepared,commandKey:'sdk-host-reject-prepare'}});
  assert.notEqual(second.isError,true,JSON.stringify(second));
  await writeFile(proofFile,signedProof({action:'QUOTE_DECISION',decision:'reject',quoteId:second.structuredContent.data.quote.id}));
  const rejected=await sdk.callTool({name:'review_purchase',arguments:{runId:second.structuredContent.data.run.id,commandKey:'sdk-host-quote-reject-001'}});
  assert.notEqual(rejected.isError,true,JSON.stringify(rejected));assert.equal(rejected.structuredContent.data.quote.status,'REJECTED');
  const cannotCommit=await sdk.callTool({name:'commit_purchase',arguments:{runId:second.structuredContent.data.run.id,commandKey:'sdk-host-reject-commit-001'}});
  assert.equal(cannotCommit.isError,true,'signed rejection must not grant caller approval or commitment');
  assert.equal(JSON.stringify([made,approved]).includes(accessMarker),false);assert.equal(JSON.stringify([made,approved]).includes(proofMarker),false);
  assert.ok(sdkBackend.calls.filter(c=>c.proof).every(c=>c.path.endsWith('/decision')||c.path.endsWith('/payment-approval')));
  assert.equal(stderr.some(line=>line.includes(accessMarker)||line.includes(proofMarker)),false);
}finally{await sdk.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
console.log(JSON.stringify({check:'official-sdk-host-credential-callback-boundary',outcome:'PASS',tools:8,noDemoMint:true,freshCredentialPerWorkflowRequest:true,
  lostAckDecisionEffects:1,signedHostRejection:true,rejectedPaymentSettlementEffects:0,proofDiscardedAfterAck:true,ownerAndProfilePinned:true,rawHostCredentialsPersisted:false,modelCredentialArguments:false,realIdentityIssuer:false,realProviderCalls:0}));
