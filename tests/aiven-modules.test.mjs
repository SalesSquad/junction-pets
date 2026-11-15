import test from 'node:test';
import assert from 'node:assert/strict';
import { buildManifest } from '../pets/aiven/modules/build-manifest.mjs';
import { selectModules, systemFor } from '../pets/aiven/modules/router.mjs';

test('guidance-modules manifest is complete, hashed and within the manifest limit', () => {
  const m = buildManifest();
  assert.equal(m.schema, 'chibi.companion.guidance-modules/v1');
  assert.equal(m.modules[0].id, 'core');
  assert.ok(m.modules[0].alwaysLoad);
  assert.ok(m.maxComposedChars <= 20000);
  for (const mod of m.modules) assert.match(mod.sha256, /^[0-9a-f]{64}$/);
  assert.match(m.responseSchema.sha256, /^[0-9a-f]{64}$/);
  assert.ok(m.responseSchema.json.required.includes('governance'));
});

test('router always loads core, falls back to services and is deterministic', () => {
  assert.deepEqual(selectModules('hello'), ['core', 'services']);
  assert.deepEqual(selectModules('Kafka consumer lag on partition 3'), selectModules('Kafka consumer lag on partition 3'));
  assert.ok(selectModules('patient registry with henkilötunnus').includes('personal-data'));
  assert.ok(systemFor('reset offsets on topic x').system.startsWith('# Aiven companion — core'));
});
