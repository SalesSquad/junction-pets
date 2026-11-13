import assert from 'node:assert/strict';
import test from 'node:test';
import {cloudAssessment} from './status-model.mjs';
import {
  normalizeServerProjection,
  advisoryCloudLabel,
  advisoryEvidenceLabel,
} from './server-projection.mjs';

const SHA = 'a'.repeat(40);
const OTHER_SHA = 'b'.repeat(40);
const NOW = Date.parse('2026-11-12T15:00:00Z');
const slugs = Array.from({length: 34}, (_, i) => 'junction-company-' + (i + 1));
const registry = () => ({
  source: {repository: 'SalesSquad/junction-pets', commit: SHA, verification: 'source-reported'},
  pets: slugs.map(slug => ({slug, company: {name: slug}, cloud: {state: 'unprovisioned'}})),
});
const projection = () => ({
  schemaVersion: 1,
  kind: 'junction-fleet-control/server-projection/v1',
  generatedAt: '2026-11-12T14:59:50Z',
  source: {repository: 'SalesSquad/junction-pets', commit: SHA,
    trustBoundary: 'provided by server; not attested in browser'},
  summary: {total: 34, cloudReady: 0},
  pets: slugs.map(slug => ({
    petSlug: slug,
    developerAgentId: 'junction-dev-' + slug.slice(9),
    desiredEnvironment: slug,
    cloud: {state: 'unprovisioned', reason: 'Not created'},
    ci: {state: 'missing', reason: 'No receipt'},
    evaluation: {state: 'missing', reason: 'No receipt'},
    grant: {state: 'unverified', reason: 'No host'},
    runtimeExecutionAllowed: false,
    nextAction: 'Create environment',
  })),
});

test('34-row source-bound projection remains advisory', () => {
  const result = normalizeServerProjection(projection(), registry(), NOW);
  assert.equal(result.advisoryOnly, true);
  assert.equal(result.byPet.size, 34);
  assert.equal(result.stale, false);
  assert.equal(result.byPet.get(slugs[0]).cloud, 'unprovisioned');
});

test('even correctly shaped backend ready is NOT browser qualification', () => {
  const p = projection();
  p.pets[0].cloud = {
    state: 'ready',
    environmentId: 'env.opaque.01',
    sourceCommit: SHA,
    verifiedAt: '2026-11-12T14:59:50Z',
  };
  const record = normalizeServerProjection(p, registry(), NOW).byPet.get(slugs[0]);
  assert.equal(record.cloud, 'ready');
  assert.match(advisoryCloudLabel(record), /unverified in browser/);
  assert.equal(cloudAssessment({state: 'ready'}).effectiveState, 'unverified');
});

test('fake ready / missing matching source receipt downgrades to unverified', () => {
  const p = projection();
  p.pets[0].cloud = {
    state: 'ready', environmentId: 'env.fake.01', sourceCommit: OTHER_SHA,
    verifiedAt: '2026-11-12T14:59:50Z',
  };
  assert.equal(normalizeServerProjection(p, registry(), NOW).byPet.get(slugs[0]).cloud, 'unverified');
});

test('CI or model-eval verified-pass claims lacking same SHA become stale', () => {
  const p = projection();
  p.pets[0].ci = {state: 'verified-pass', sourceCommit: OTHER_SHA};
  p.pets[0].evaluation = {state: 'verified-pass', sourceCommit: SHA};
  const record = normalizeServerProjection(p, registry(), NOW).byPet.get(slugs[0]);
  assert.equal(record.ci, 'stale');
  assert.equal(record.evaluation, 'verified-pass');
  assert.match(advisoryEvidenceLabel(record.evaluation, 'Model eval'), /not browser-attested/);
});

test('unknown pet, duplicate pet, omitted pet, wrong source or browser-execution grant fail', () => {
  for (const change of [
    p => { p.pets[0].petSlug = p.pets[1].petSlug; },
    p => { p.pets.pop(); },
    p => { p.source.commit = OTHER_SHA; },
    p => { p.pets[0].runtimeExecutionAllowed = true; },
    p => { p.pets[0].petSlug = 'junction-unknown'; },
  ]) {
    const p = projection(); change(p);
    assert.throws(() => normalizeServerProjection(p, registry(), NOW));
  }
});

test('backend raw reasons, provider tokens and URLs are never echoed into presentation model', () => {
  const p = projection();
  p.pets[0].cloud.reason = 'Bearer secret-value';
  p.pets[0].cloud.accessToken = 'not-for-browser';
  p.pets[0].cloud.evidenceUrl = 'https://secret.example/proof?token=abc';
  p.pets[0].grant = {state: 'revoked', reason: 'internal customer name'};
  const record = normalizeServerProjection(p, registry(), NOW).byPet.get(slugs[0]);
  const rendered = JSON.stringify(record);
  assert.equal(record.grant, 'revoked');
  assert.doesNotMatch(rendered, /Bearer|secret|accessToken|customer|evidenceUrl|not-for-browser/);
});

test('realistic 12-minute-old backend feed downgrades Cloud, CI, eval and grant claims', () => {
  const p = projection();
  p.generatedAt = new Date(NOW - 12 * 60_000).toISOString();
  p.pets[0].cloud = {
    state: 'ready', environmentId: 'env.old.01', sourceCommit: SHA,
    verifiedAt: new Date(NOW - 13 * 60_000).toISOString(),
  };
  p.pets[0].ci = {state: 'verified-pass', sourceCommit: SHA};
  p.pets[0].evaluation = {state: 'verified-pass', sourceCommit: SHA};
  p.pets[0].grant = {state: 'host-verified'};
  const result = normalizeServerProjection(p, registry(), NOW);
  const record = result.byPet.get(slugs[0]);
  assert.equal(result.stale, true);
  assert.equal(record.cloud, 'stale');
  assert.match(advisoryCloudLabel(record), /stale/);
  assert.equal(record.environmentId, null);
  assert.equal(record.ci, 'stale');
  assert.equal(record.evaluation, 'stale');
  assert.equal(record.grant, 'unverified');
  assert.equal(cloudAssessment({state: 'ready'}).effectiveState, 'unverified');
});

test('stale and future browser snapshots are explicit', () => {
  const p = projection();
  assert.equal(normalizeServerProjection(p, registry(), NOW + 2 * 3600_000).stale, true);
  assert.throws(() => normalizeServerProjection(p, registry(), NOW - 120_000), /timestamp/);
});

test('reported counts cannot be turned into trusted green counts', () => {
  const p = projection();
  p.summary = {cloudReady: 34, ciVerifiedPasses: 34, evalVerifiedPasses: 34};
  const result = normalizeServerProjection(p, registry(), NOW);
  assert.equal([...result.byPet.values()].filter(row => row.cloud === 'ready').length, 0);
  assert.equal(result.advisoryOnly, true);
});
