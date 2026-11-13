import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {loadPackages, validatePet, packageDigest} from '../lib/catalog.mjs';
import {companyContext} from '../lib/company-context.mjs';

// Authored-package regressions only: no retrieval, provider call or model scoring.
const packs = await loadPackages(fileURLToPath(new URL('../', import.meta.url)));
const pack = packs.find(p => p.pet.id === 'junction.aiven');
const urls = {
  pg: 'https://aiven.io/docs/products/postgresql/howto/identify-pg-slow-queries',
  repair: 'https://aiven.io/docs/products/postgresql/howto/repair-pg-index',
  kafka: 'https://aiven.io/docs/products/kafka/concepts/monitor-consumer-group'
};
const authored = id => {
  const c = pack.evals.cases.find(c => c.id === id);
  assert.ok(c, `missing authored scenario: ${id}`);
  return c;
};

test('Aiven retains v1 isolated guidance contract and focused official provenance', () => {
  validatePet(pack.pet);
  assert.equal(pack.pet.schemaVersion, 1);
  assert.equal(pack.pet.version, '0.1.2');
  assert.equal(pack.pet.slug, 'junction-aiven');
  assert.equal(pack.pet.artIndex, 29);
  assert.equal(pack.pet.capabilities.length, 3);
  assert.ok(pack.pet.capabilities.every(c => !c.requiresConnection));
  assert.equal(pack.pet.availability.runtime, 'chibi-host-required');
  assert.equal(pack.pet.availability.companyEndorsed, false);
  for (const url of Object.values(urls)) {
    const source = pack.pet.sources.find(s => s.url === url);
    assert.ok(source, `missing exact supporting URL: ${url}`);
    assert.equal(source.publisher, 'Aiven');
    assert.equal(source.checkedAt, '2026-11-13');
    assert.ok(source.summary.length > 60);
    assert.ok(pack.instructions.includes(url));
    assert.ok(companyContext(pack).includes(url));
  }
  const other = packs.find(p => p.pet.id !== pack.pet.id);
  for (const url of Object.values(urls)) assert.ok(!companyContext(other).includes(url));
  const changed = structuredClone(pack);
  changed.pet.sources.find(s => s.url === urls.pg).summary += ' changed';
  assert.notEqual(packageDigest(changed), packageDigest(pack));
});

test('authored positive scenarios require claim-level citations and bounded diagnosis', () => {
  assert.equal(pack.evals.cases.length, 6);
  assert.equal(new Set(pack.evals.cases.map(c => c.id)).size, 6);
  const pg = authored('postgresql-index-provenance');
  const kafka = authored('kafka-consumer-group-provenance');
  for (const [c, url] of [[pg, urls.pg], [kafka, urls.kafka]]) {
    assert.ok(c.prompt.includes(url));
    assert.ok(c.mustInclude.some(s => s.includes(url)));
    assert.ok(c.mustInclude.some(s => /[Ss]eparate/.test(s)));
    assert.ok(c.mustInclude.some(s => /measurement/.test(s)));
  }
  assert.ok(pg.mustNotClaim.some(s => /proven performance fix/.test(s)));
  assert.ok(kafka.mustNotClaim.some(s => /exactly-once/.test(s)));
  assert.ok(kafka.mustNotClaim.some(s => /offset reset/.test(s)));
});

test('authored no-hit, irrelevant-hit and failure scenarios preserve useful recovery', () => {
  const empty = authored('no-provider-connection');
  const irrelevant = authored('company-source-isolation');
  const failure = authored('kafka-consumer-group-provenance');
  assert.match(empty.prompt, /zero hits/);
  assert.ok(empty.mustInclude.some(s => /narrow official-docs query/.test(s)));
  assert.ok(empty.mustNotClaim.some(s => /unsupported/.test(s)));
  assert.ok(irrelevant.prompt.includes(urls.repair));
  assert.ok(irrelevant.mustInclude.some(s => /irrelevant to Kafka/.test(s)));
  assert.ok(irrelevant.mustInclude.some(s => /per-partition lag/.test(s)));
  assert.ok(irrelevant.mustNotClaim.some(s => /private source collection/.test(s)));
  assert.ok(failure.mustInclude.some(s => /timeout.*no relevant hits/.test(s)));
  assert.ok(failure.mustNotClaim.some(s => /timed-out retrieval/.test(s)));
  assert.match(pack.instructions, /reference to verify/);
  assert.match(pack.instructions, /Never fabricate a supporting URL/);
  assert.match(pack.story, /authored expectations, not measured/);
});
