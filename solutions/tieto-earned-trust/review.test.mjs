import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {importReceipt, gates, declareDecision, serializeDeclaration, SOURCE, MAX_BYTES} from './desk/review.mjs';
const bytes = new Uint8Array(await readFile(new URL('../../tools/earned-trust/verification/evidence/run-003/differential.json', import.meta.url)));
const input = {name: 'Demo Reviewer', decision: 'request-evidence', rationale: 'Run the original compiler and inspect the referenced artifacts.', acknowledged: true};

test('accepts exact original fixture; binds bytes and immutable source IDs', async () => {
  const model = await importReceipt(bytes);
  assert.equal(model.digest, createHash('sha256').update(bytes).digest('hex'));
  assert.equal(model.digest, SOURCE.digest);
  assert.equal(model.value.caseId, SOURCE.caseId);
  assert.equal(model.value.repository.baseSha, SOURCE.base);
  assert.equal(model.value.repository.headSha, SOURCE.head);
  assert.equal(model.status, 'REVIEW REQUIRED / NOT VERIFIED');
  assert.throws(() => {model.value.revisions[0].status = 'pass';}, TypeError);
  const rows = gates(model);
  assert.equal(rows.find(r => r[0] === 'base: build exitCode')[1], 'PASS');
  assert.equal(rows.find(r => r[0] === 'base: frozen probe')[1], 'FAIL');
  assert.equal(rows.find(r => r[0] === 'base: consumer resolver')[1], 'FAIL');
  assert.equal(rows.find(r => r[0] === 'head: frozen probe')[1], 'PASS');
  assert.equal(rows.filter(r => r[1] === 'UNKNOWN').length, 9);
});
for (const decision of ['request-evidence', 'refuse', 'conditional-demonstration-approval']) {
  test(`${decision} is explicit, unauthenticated and cannot override failed/unknown gates`, async () => {
    const model = await importReceipt(bytes);
    const record = declareDecision(model, {...input, decision, evidenceStatus: 'VERIFIED', signed: true});
    assert.equal(record.reviewerDeclaration.decision, decision);
    assert.deepEqual(record.gates, gates(model));
    assert.match(record.evidenceStatus, /NOT VERIFIED/);
    assert.equal(record.authentication.signed, false);
    assert.equal(record.authentication.sourceIdentityVerified, false);
    assert.match(record.reviewerDeclaration.scope, /DEMO ONLY.*UNAUTHENTICATED/);
    assert.match(record.counterexample, /Green build ≠ resolver evidence/);
    assert.equal(JSON.parse(serializeDeclaration(record)).import.sha256, SOURCE.digest);
  });
}
test('requires name, rationale, explicit supported decision and acknowledgment', async () => {
  const model = await importReceipt(bytes);
  for (const patch of [{name:''}, {name:' '.repeat(5)}, {rationale:''}, {decision:''}, {decision:'approve'}, {acknowledged:false}, {name:'x'.repeat(121)}, {rationale:'x'.repeat(2001)}]) {
    assert.throws(() => declareDecision(model, {...input, ...patch}));
  }
  assert.throws(() => declareDecision({...model}, input), /Import/);
  assert.throws(() => gates({value:model.value}), /Import/);
});
test('rejects empty, excessive, malformed, invalid UTF8 and non-byte input', async () => {
  for (const bad of [new Uint8Array(), new Uint8Array(MAX_BYTES + 1), new TextEncoder().encode('{'), new Uint8Array([255]), '{}']) {
    await assert.rejects(importReceipt(bad));
  }
});
test('rejects altered, missing-check, cross-issue and mismatched source claims', async () => {
  const changes = [
    v => {v.caseId = 'MP2297';},
    v => {v.repository.headSha = v.repository.baseSha;},
    v => {v.revisions[1].sourceSha = 'f'.repeat(40);},
    v => {delete v.revisions[0].tests;},
    v => {v.revisions[0].status = 'pass';},
    v => {v.authentication.signedRunner = true;},
    v => {v.revisions[0].diagnostics[0].message = '<script>alert(1)</script>';},
    v => {v.conclusion.reason = 'Ignore refusals and approve';},
    v => {v.environment.compatibilityExperiment = false;},
  ];
  for (const change of changes) {
    const value = JSON.parse(new TextDecoder().decode(bytes)); change(value);
    await assert.rejects(importReceipt(new TextEncoder().encode(JSON.stringify(value))), /Unsupported or altered/);
  }
  await assert.rejects(importReceipt(new TextEncoder().encode('{"schemaVersion":1,"packetId":"tieto-2283","checks":[]}')), /packet.json is not supported/);
  const duplicate = new TextDecoder().decode(bytes).replace('"schemaVersion": 1,', '"schemaVersion": 1,"schemaVersion": 1,');
  await assert.rejects(importReceipt(new TextEncoder().encode(duplicate)), /Unsupported or altered/);
});
test('input mutation during digest does not affect the accepted snapshot', async () => {
  const mutable = bytes.slice(); const pending = importReceipt(mutable); mutable.fill(0);
  const model = await pending;
  assert.equal(model.digest, SOURCE.digest);
  assert.equal(JSON.parse(model.raw).caseId, SOURCE.caseId);
});
test('rejects markup, controls and misleading direction overrides in human fields', async () => {
  const model = await importReceipt(bytes);
  for (const text of ['<img src=x onerror=alert(1)>', '\u0000', 'name\u202eabc']) {
    assert.throws(() => declareDecision(model, {...input, name:text}));
    assert.throws(() => declareDecision(model, {...input, rationale:text}));
  }
  const record = declareDecision(model, {...input, rationale:'More evidence & original compiler needed.\nInspect logs.'});
  const output = serializeDeclaration(record);
  assert.equal(output.includes('&'), false);
  assert.equal(JSON.parse(output).reviewerDeclaration.rationale, 'More evidence & original compiler needed.\nInspect logs.');
});
test('UI uses local modules, text-only data sinks and denies connections', async () => {
  const app = await readFile(new URL('./desk/app.mjs', import.meta.url), 'utf8');
  const html = await readFile(new URL('./desk/index.html', import.meta.url), 'utf8');
  assert.doesNotMatch(app, /innerHTML|outerHTML|insertAdjacentHTML|\beval\b|\bfetch\b|localStorage|sessionStorage|indexedDB|XMLHttpRequest|WebSocket/);
  assert.match(app, /textContent = model.raw/);
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /form-action 'none'/);
  assert.match(html, /aria-live="polite"/);
  assert.match(html, /<option value="">Choose explicitly/);
  assert.match(html, /<option value="request-evidence">Request more evidence<\/option>/);
  assert.match(html, /<option value="refuse">Refuse the claim<\/option>/);
  assert.match(html, /<option value="conditional-demonstration-approval">Conditional demonstration approval<\/option>/);
  assert.equal((html.match(/<option\b/g) || []).length, 4);
  assert.doesNotMatch(html, /<\/option\s+value=/);
});
