import test from 'node:test';
import assert from 'node:assert/strict';
import {collectFleetStatus, validateFleet} from './index.mjs';
import {EXPECTED_COMPANIES} from '../../lib/catalog.mjs';

const A = 'a'.repeat(40), B = 'b'.repeat(40);
const H = 'c'.repeat(64);
const now = new Date('2026-11-12T20:00:00.000Z');
const aiven = 'junction-aiven';
const canonicalRoster = ['aiven',...EXPECTED_COMPANIES.filter(slug => slug !== 'aiven')];
const fixtureFleet = () => Array.from({length: 34}, (_, i) => {
  const slug = canonicalRoster[i];
  return {
    petSlug: 'junction-' + slug,
    desiredName: 'junction-' + slug,
    agentId: 'junction-dev-' + slug,
    provider: 'codex-cloud',
    repository: 'SalesSquad/junction-pets',
    provisioning: {state:'unprovisioned',environmentId:null,verifiedAt:null,evidenceUrl:null}
  };
});
const publish = fleet => {
  fleet[0].provisioning = {
    state: 'ready',
    environmentId: 'env_junction_aiven_01',
    verifiedAt: now.toISOString(),
    evidenceUrl: 'https://chatgpt.com/codex/environments/env_junction_aiven_01'
  };
  return fleet;
};
const readyObservation = () => ({
  environmentId: 'env_junction_aiven_01',
  petSlug: aiven,
  repository: 'SalesSquad/junction-pets',
  provider: 'codex-cloud',
  published: true,
  state: 'ready',
  receipt: {
    receiptId: 'attestation-123',
    environmentId: 'env_junction_aiven_01',
    petSlug: aiven,
    repository: 'SalesSquad/junction-pets',
    provider: 'codex-cloud',
    sourceCommit: A,
    issuedAt: now.toISOString(),
    evidenceUrl: 'https://chatgpt.com/codex/observations/123',
    secret: 'synthetic-provider-secret'
  },
  accessToken: 'synthetic-provider-token'
});
const provider = (obs=readyObservation(), verifier=async()=>true) => ({
  readEnvironment: async()=>obs,
  verifyReceipt: verifier
});
const grant = (state='active', verified=true) => ({
  readGrant: async()=>({state,petSlug:aiven,sourceCommit:A,receiptId:'signed-grant-1',apiKey:'synthetic-grant-secret'}),
  verifyReceipt: async()=>verified
});
const receipt = (sourceCommit=A) => ({
  petSlug:aiven,sourceCommit,artifactSha256:H,receiptId:'run-123',
  evidenceUrl:'https://github.com/SalesSquad/junction-pets/pull/123',result:'pass',
  providerToken:'synthetic-receipt-secret'
});
const collect = options => collectFleetStatus({manifests:fixtureFleet(),sourceCommit:A,now,...options});

test('34 pet manifests are exact and source-bound',()=>{
  const list=fixtureFleet();
  assert.equal(validateFleet(list,A),true);
  assert.throws(()=>validateFleet(list,'main'),/Exact canonical/);
  assert.throws(()=>validateFleet(list.slice(1),A),/Expected 34/);
  list[1] = structuredClone(list[0]);
  assert.throws(()=>validateFleet(list,A),/Duplicate/);
});

test('editable ready states and fabricated IDs do not promote cloud readiness', async()=>{
  const withoutReader = await collectFleetStatus({manifests:publish(fixtureFleet()),sourceCommit:A,now});
  assert.equal(withoutReader.summary.cloudReady,0);
  assert.equal(withoutReader.pets[0].cloud.state,'unverified');

  const fake = readyObservation();
  fake.environmentId = 'env_forged_other';
  const forged = await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(fake,async()=>true)
  });
  assert.equal(forged.pets[0].cloud.state,'unverified');

  const rejected = await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(readyObservation(),async()=>false)
  });
  assert.equal(rejected.summary.cloudReady,0);
});

test('provider receipt binds immutable environment ID, pet and exact source SHA',async()=>{
  const mismatch=readyObservation();
  mismatch.receipt.sourceCommit=B;
  const result=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(mismatch,async()=>true)
  });
  assert.equal(result.pets[0].cloud.state,'unverified');

  const valid=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider()
  });
  assert.equal(valid.summary.cloudReady,1);
  assert.equal(valid.pets[0].cloud.state,'ready');
  assert.equal(valid.pets[0].cloud.sourceCommit,A);
  assert.equal(valid.pets[1].cloud.state,'unprovisioned');
  assert.equal(valid.summary.runtimeEligible,0);
});

test('revoked and unverifiable Chibi grants deny runtime, regardless of cloud state',async()=>{
  const revoked=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(),grantAdapter:grant('revoked')
  });
  assert.equal(revoked.pets[0].cloud.state,'ready');
  assert.equal(revoked.pets[0].grant.state,'revoked');
  assert.equal(revoked.pets[0].runtimeExecutionAllowed,false);

  const untrusted=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(),grantAdapter:grant('active',false)
  });
  assert.equal(untrusted.pets[0].grant.state,'unverified');
  assert.equal(untrusted.summary.runtimeEligible,0);

  const trusted=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(),grantAdapter:grant('active',true)
  });
  assert.equal(trusted.pets[0].grant.state,'host-verified');
  assert.equal(trusted.summary.runtimeEligible,0);
  assert.equal(trusted.pets[0].runtimeExecutionAllowed,false);
});

test('stale CI/eval SHA cannot count as passed even with a permissive verifier',async()=>{
  const results=await collect({
    ciReceipts:{[aiven]:receipt(B)},
    evalReceipts:{[aiven]:receipt(B)},
    ciVerifier:async()=>true,evalVerifier:async()=>true
  });
  assert.equal(results.pets[0].ci.state,'stale');
  assert.equal(results.pets[0].evaluation.state,'stale');
  assert.equal(results.summary.ciVerifiedPasses,0);
  assert.equal(results.summary.evalVerifiedPasses,0);
});

test('verified CI/eval receipts count, but no supplied secret is projected',async()=>{
  const output=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:provider(),grantAdapter:grant(),
    ciReceipts:{[aiven]:receipt()},
    evalReceipts:{[aiven]:receipt()},
    ciVerifier:async()=>true,evalVerifier:async()=>true
  });
  assert.equal(output.summary.cloudReady,1);
  assert.equal(output.summary.ciVerifiedPasses,1);
  assert.equal(output.summary.evalVerifiedPasses,1);
  const emitted=JSON.stringify(output);
  assert.ok(!emitted.includes('synthetic-provider-secret'));
  assert.ok(!emitted.includes('synthetic-provider-token'));
  assert.ok(!emitted.includes('synthetic-grant-secret'));
  assert.ok(!emitted.includes('synthetic-receipt-secret'));
  assert.equal(output.kind,'junction-fleet-control/server-projection/v1');
  assert.equal(output.source.commit,A);
  assert.equal(output.source.verification,'not-independently-verified');
  assert.equal(output.source.trustBoundary,'caller-supplied-sha-format-only');
  assert.equal(output.pets.length,34);
});

test('provider outage blocks one pet but does not stop the other 33',async()=>{
  const result=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,
    providerAdapter:{readEnvironment:async()=>{throw new Error('secret internal provider failure');},verifyReceipt:async()=>true}
  });
  assert.equal(result.pets[0].cloud.state,'blocked');
  assert.equal(result.pets.filter(p=>p.cloud.state==='unprovisioned').length,33);
  assert.ok(!JSON.stringify(result).includes('secret internal provider failure'));
});

test('caller supplied SHA never becomes a fabricated authenticated source claim', async()=>{
  const result=await collectFleetStatus({
    manifests:publish(fixtureFleet()),sourceCommit:A,now,providerAdapter:provider()
  });
  assert.equal(result.summary.cloudReady,1);
  assert.equal(result.source.commit,A);
  assert.equal(result.source.verification,'not-independently-verified');
  assert.equal(result.source.trustBoundary,'caller-supplied-sha-format-only');
});
