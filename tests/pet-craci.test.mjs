import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {reviewSyntheticSbom, SBOM_LIMITS} from '../pets/craci/sbom-review.mjs';

const digest = 'a'.repeat(64);
const identity = (name = 'invented-app', version = '1.0.0', sha256 = digest) => ({
  ecosystem: 'fictional', name, version, sha256,
});
const component = (ref = 'app', subject = identity()) => ({
  ref, ...subject, artifact: {...subject},
  provenance: {subject: {...subject}, sourceCommit: 'b'.repeat(40), builder: 'invented-builder', buildId: 'build-1'},
});
const fixture = () => ({
  schemaVersion: 1, synthetic: true,
  components: [component(), component('lib', identity('invented-lib', '2.0.0', 'c'.repeat(64)))],
  dependencies: [{from: 'app', to: 'lib'}],
  advisories: [{id: 'SYNTH-001', ecosystem: 'fictional', name: 'invented-lib', versions: ['2.0.0']}],
});
const review = input => reviewSyntheticSbom(JSON.stringify(input));
const rejected = (mutate, pattern = /Invalid synthetic SBOM/) => {
  const input = fixture(); mutate(input); assert.throws(() => review(input), pattern);
};

test('complete synthetic evidence is internally consistent but never authenticated or an exploit proof', () => {
  const input = fixture();
  const result = review(input);
  assert.equal(result.kind, 'synthetic-sbom-review');
  assert.equal(result.verified, false);
  assert.equal(result.provenanceAuthenticated, false);
  assert.equal(result.dependencyScope, 'declared-only');
  assert.deepEqual(result.componentChecks.map(c => [c.ref, c.consistency, c.verified, c.issues]), [
    ['app', 'consistent', false, []], ['lib', 'consistent', false, []],
  ]);
  assert.deepEqual(result.advisoryChecks, [{
    id: 'SYNTH-001', matchedRefs: ['lib'], unknownVersionRefs: [],
    matchBasis: 'exact-declared-ecosystem-name-version', confirmedExploit: false, exploitability: 'not-assessed',
  }]);
  assert.deepEqual(review(input), result);
  input.components.reverse();
  assert.deepEqual(review(input), result);
});

test('artifact and provenance subjects must bind the exact ecosystem, name, version and digest', () => {
  for (const location of ['artifact', 'provenance']) {
    for (const [field, value] of Object.entries({ecosystem: 'other', name: 'Invented-App', version: '1.0.1', sha256: 'd'.repeat(64)})) {
      const input = fixture();
      const subject = location === 'artifact' ? input.components[0].artifact : input.components[0].provenance.subject;
      subject[field] = value;
      const check = review(input).componentChecks[0];
      assert.equal(check.consistency, 'mismatch');
      assert.ok(check.issues.includes(`${location}-${field}-mismatch`));
      assert.equal(check.verified, false);
    }
  }
});

test('missing and null evidence remain distinct and incomplete; string zero is an exact version', () => {
  for (const field of ['version', 'sha256', 'artifact', 'provenance']) {
    for (const state of ['missing', 'null']) {
      const input = fixture();
      if (state === 'missing') delete input.components[0][field];
      else input.components[0][field] = null;
      const check = review(input).componentChecks[0];
      assert.equal(check.consistency, 'incomplete');
      assert.ok(check.issues.includes(`component-${field}-${state}`));
      assert.equal(check.verified, false);
    }
  }
  for (const field of ['sourceCommit', 'builder', 'buildId']) {
    const input = fixture(); delete input.components[0].provenance[field];
    assert.ok(review(input).componentChecks[0].issues.includes(`provenance-${field}-missing`));
  }
  for (const place of ['artifact', 'provenance']) {
    const input = fixture();
    const subject = place === 'artifact' ? input.components[0].artifact : input.components[0].provenance.subject;
    subject.sha256 = null;
    assert.equal(review(input).componentChecks[0].consistency, 'incomplete');
  }
  const input = fixture(); input.components[0] = component('app', identity('invented-app', '0'));
  assert.equal(review(input).componentChecks[0].consistency, 'consistent');
  for (const version of [0, '', 'unknown', 'latest', '*', '^1.0.0', '>=1.0.0']) {
    rejected(i => { i.components[0].version = version; });
  }
});

test('the same declared identity and version cannot silently name different component digests', () => {
  const input = fixture();
  input.components.push(component('duplicate', identity('invented-app', '1.0.0', 'd'.repeat(64))));
  const result = review(input);
  for (const ref of ['app', 'duplicate']) {
    const check = result.componentChecks.find(c => c.ref === ref);
    assert.equal(check.consistency, 'mismatch');
    assert.ok(check.issues.includes('identity-digest-conflict'));
  }
});

test('advisories match only exact declared identity/version and expose unknown-version candidates', () => {
  const input = fixture();
  input.components.push(component('other-ecosystem', {...identity('invented-lib', '2.0.0'), ecosystem: 'other'}));
  input.components.push(component('other-version', identity('invented-lib', '2.0.1')));
  input.components.push(component('prefix-name', identity('invented-library', '2.0.0')));
  input.components.push(component('unknown', identity('invented-lib', null)));
  input.components.push(component('missing', identity('invented-lib')));
  delete input.components.at(-1).version;
  const [check] = review(input).advisoryChecks;
  assert.deepEqual(check.matchedRefs, ['lib']);
  assert.deepEqual(check.unknownVersionRefs, ['missing', 'unknown']);
  assert.equal(check.confirmedExploit, false);
  input.advisories[0].versions = ['9.0.0'];
  assert.deepEqual(review(input).advisoryChecks[0].matchedRefs, []);
  assert.equal(review(input).verified, false);
});

test('only declared edges are reported; cycles are allowed, dangling/duplicate/self edges are refused', () => {
  const input = fixture();
  input.components.push(component('leaf', identity('invented-leaf')));
  input.dependencies.push({from: 'lib', to: 'leaf'}, {from: 'leaf', to: 'app'});
  assert.deepEqual(review(input).declaredDependencies, [
    {from: 'app', to: 'lib'}, {from: 'leaf', to: 'app'}, {from: 'lib', to: 'leaf'},
  ]);
  rejected(i => { i.dependencies.push({from: 'app', to: 'absent'}); });
  rejected(i => { i.dependencies.push({from: 'absent', to: 'app'}); });
  rejected(i => { i.dependencies.push({...i.dependencies[0]}); });
  rejected(i => { i.dependencies.push({from: 'app', to: 'app'}); });
});

test('malformed shape, duplicate identifiers and unsupported verified/exploit claims are refused', () => {
  for (const mutate of [
    i => { i.synthetic = false; }, i => { i.schemaVersion = 2; },
    i => { i.components = []; }, i => { i.dependencies = null; },
    i => { i.components[1].ref = 'app'; }, i => { i.advisories.push({...i.advisories[0]}); },
    i => { i.components[0].verified = true; }, i => { i.advisories[0].confirmedExploit = true; },
    i => { i.components[0].artifact = {}; }, i => { i.components[0].provenance.subject = []; },
    i => { i.components[0].provenance.sourceCommit = 'main'; },
    i => { i.advisories[0].versions = ['2.0.0', '2.0.0']; },
  ]) rejected(mutate);
  for (const input of ['null', '[]', '{', '{"__proto__":{}}']) assert.throws(() => reviewSyntheticSbom(input), /Invalid synthetic SBOM/);
});

test('input bytes, collection sizes and field formats have explicit finite limits', () => {
  const base = JSON.stringify(fixture());
  assert.equal(reviewSyntheticSbom(base.padEnd(SBOM_LIMITS.textBytes)).verified, false);
  assert.throws(() => reviewSyntheticSbom(base.padEnd(SBOM_LIMITS.textBytes + 1)), /Invalid synthetic SBOM/);
  assert.throws(() => reviewSyntheticSbom('é'.repeat(SBOM_LIMITS.textBytes / 2 + 1)), /Invalid synthetic SBOM/);
  rejected(i => { i.components = Array.from({length: SBOM_LIMITS.components + 1}, (_, n) => component(`c${n}`)); });
  rejected(i => { i.dependencies = Array.from({length: SBOM_LIMITS.dependencies + 1}, () => ({from: 'app', to: 'lib'})); });
  rejected(i => { i.advisories = Array.from({length: SBOM_LIMITS.advisories + 1}, (_, n) => ({...i.advisories[0], id: `SYNTH-${n}`})); });
  rejected(i => { i.advisories[0].versions = Array.from({length: SBOM_LIMITS.versions + 1}, (_, n) => `${n}`); });
  for (const sha256 of ['A'.repeat(64), 'g'.repeat(64), 'a'.repeat(63), 0]) rejected(i => { i.components[0].sha256 = sha256; });
  rejected(i => { i.components[0].name = 'x'.repeat(129); });
  rejected(i => { i.components[0].name = 'invented\nlib'; });
});

test('the API accepts JSON text only; standard JSON duplicate-member last-value semantics apply', () => {
  let touched = false;
  const object = {get components() { touched = true; throw Error('must not evaluate'); }};
  for (const input of [object, Buffer.from('{}'), null, 0]) assert.throws(() => reviewSyntheticSbom(input), /Invalid synthetic SBOM/);
  assert.equal(touched, false);
  const text = JSON.stringify(fixture()).replace('"synthetic":true', '"synthetic":false,"synthetic":true');
  assert.equal(reviewSyntheticSbom(text).verified, false);
  assert.throws(() => reviewSyntheticSbom(text.replace('false,"synthetic":true', 'true,"synthetic":false')), /Invalid synthetic SBOM/);
});

test('the shipped example is synthetic, package version is advanced and six authored evals are byte-preserved', async () => {
  const raw = await readFile(new URL('../pets/craci/example-sbom.json', import.meta.url), 'utf8');
  const example = reviewSyntheticSbom(raw);
  assert.deepEqual(example.advisoryChecks[0].matchedRefs, ['palette']);
  assert.equal(example.componentChecks.find(c => c.ref === 'unversioned').consistency, 'incomplete');
  const pet = JSON.parse(await readFile(new URL('../pets/craci/pet.json', import.meta.url), 'utf8'));
  assert.equal(pet.version, '0.2.0');
  const evals = await readFile(new URL('../pets/craci/evals.json', import.meta.url));
  assert.equal(JSON.parse(evals).cases.length, 6);
  assert.equal(createHash('sha256').update(evals).digest('hex'), 'd5eee6ac7afea8a6f90f5554c9cd2544aca3eb1a1cc1e295db320262d823e5c7');
});
