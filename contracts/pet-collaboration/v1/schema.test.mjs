import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';

const root = new URL('./', import.meta.url);
const request = JSON.parse(readFileSync(new URL('request.schema.json', root), 'utf8'));
const receipt = JSON.parse(readFileSync(new URL('receipt.schema.json', root), 'utf8'));
let Ajv2020;
try {
  const module = await import('ajv/dist/2020.js');
  Ajv2020 = module.default?.default ?? module.default;
} catch {
  Ajv2020 = null;
}
const SHA = 'a'.repeat(40);
const DIGEST = 'sha256:' + 'b'.repeat(64);

test('source-bound pre-release v1 schemas declare exact fields and conditional receipts', () => {
  assert.equal(request.$schema, 'https://json-schema.org/draft/2020-12/schema');
  assert.ok(request.required.includes('sourceSha'));
  assert.equal(request.properties.sourceSha.pattern, '^[a-f0-9]{40}$');
  assert.ok(receipt.required.includes('executionKind'));
  assert.ok(receipt.allOf.length >= 5);
  assert.ok(receipt.properties.hostAttestation.required.includes('signatureRef'));
});

test('request accepts a pinned 40-character SHA, never an absent or fabricated short label', {
  skip: !Ajv2020 && 'Optional Ajv Draft 2020-12 validator unavailable',
}, () => {
  const validate = new Ajv2020({strict: false, validateFormats: false}).compile(request);
  const envelope = {
    schemaVersion: 'pet-collaboration.v1',
    kind: 'request', requestId: 'req.one', conversationId: 'conversation.one',
    tenantId: 'tenant.one', actorPetId: 'junction.openai-codex', recipientPetId: 'junction.mariadb',
    capabilityId: 'query-review', sourceSha: SHA, authorityRef: 'host.grant.01',
    requestedEffect: 'read',
    createdAt: '2026-11-12T15:00:00Z', expiresAt: '2026-11-12T15:03:00Z', depth: 0,
    context: {ref: 'ctx.one', digest: DIGEST, dataClass: 'synthetic'},
    budget: {maxTokens: 500, maxDepth: 2},
  };
  assert.equal(validate(envelope), true, JSON.stringify(validate.errors));
  assert.equal(validate({...envelope, sourceSha: undefined}), false);
  assert.equal(validate({...envelope, sourceSha: 'main'}), false);
});

test('completed model/tool receipts require detached host attestation and execution receipts', {
  skip: !Ajv2020 && 'Optional Ajv Draft 2020-12 validator unavailable',
}, () => {
  const validate = new Ajv2020({strict: false, validateFormats: false, allErrors: true}).compile(receipt);
  const base = {
    schemaVersion: 'pet-collaboration.v1', kind: 'receipt',
    requestId: 'req.one', tenantId: 'tenant.one',
    actorPetId: 'junction.openai-codex', recipientPetId: 'junction.mariadb',
    decisionRef: 'host.decision.01', status: 'denied', executionKind: 'none',
    sourceSha: SHA, completedAt: '2026-11-12T15:03:00Z',
    hostAuthorization: false, externalEffects: false,
  };
  assert.equal(validate(base), true, JSON.stringify(validate.errors));
  assert.equal(validate({...base, status: 'completed', executionKind: 'model', hostAuthorization: true}), false);
  const signed = {...base, status: 'completed', executionKind: 'model', hostAuthorization: true,
    outputDigest: DIGEST,
    hostAttestation: {issuer: 'chibi-host', attestationRef: 'host.attest.01', signatureRef: 'host.sig.01'}};
  assert.equal(validate(signed), false, 'a model execution must include provider receipt');
  assert.equal(validate({...signed, providerReceiptRef: 'provider.req.01'}), true, JSON.stringify(validate.errors));
  const tool = {...signed, executionKind: 'tool', externalEffects: true, toolReceiptRef: 'tool.req.01'};
  assert.equal(validate(tool), true, JSON.stringify(validate.errors));
  assert.equal(validate({...tool, toolReceiptRef: undefined}), false);
  assert.equal(validate({...base, status: 'denied', executionKind: 'none', providerReceiptRef: undefined}), true);
  assert.equal(validate({...base, status: 'denied', executionKind: 'model'}), false);
});
