import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {EXPECTED_COMPANIES} from '../lib/catalog.mjs';
import {loadSpecialCapabilities,validateSpecialCapabilities,specialCapabilitiesFor} from '../lib/special-capabilities.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const entry=(over={})=>({id:'x-ray',title:'X ray',description:'A synthetic capability.',service:'services/pet-voice',pets:['nvidia'],requiresConnection:true,status:'offline-demo',...over});
const reg=(...capabilities)=>({schemaVersion:1,capabilities});

test('registry loads, every service exists and every company keeps a pet', async () => {
  const registry=await loadSpecialCapabilities(root);
  assert.equal(EXPECTED_COMPANIES.length,34);
  for (const slug of EXPECTED_COMPANIES) assert.ok(Array.isArray(specialCapabilitiesFor(registry,slug)));
});

test('only some pets have extra special capabilities; "all" reaches every pet', async () => {
  const registry=await loadSpecialCapabilities(root);
  const ids=slug=>specialCapabilitiesFor(registry,slug).map(c=>c.id);
  const forAll=registry.capabilities.filter(c=>c.pets==='all').map(c=>c.id);
  // Shared with every pet: voice plus the Aiven platform capabilities (services/aiven-platform).
  assert.deepEqual(forAll.sort(),['aiven-read-only-inspection','answer-check-repair','challenger-evaluation','replayable-event-log','typed-decision-proposals','voice']);
  assert.deepEqual(ids('nvidia').sort(),[...forAll,'drawing-evidence','visual-observation'].sort());
  assert.deepEqual(ids('stoa').sort(),[...forAll,'drawing-evidence'].sort());
  assert.deepEqual(ids('hostinger').sort(),[...forAll].sort());
  assert.ok(registry.capabilities.filter(c=>c.service==='services/aiven-platform').every(c=>c.pets==='all'));
  assert.ok(!('pets' in specialCapabilitiesFor(registry,'meta')[0]),'pet list stays out of per-pet projection');
});

test('invalid registries are refused', () => {
  assert.doesNotThrow(()=>validateSpecialCapabilities(reg(entry())));
  assert.throws(()=>validateSpecialCapabilities(reg(entry({pets:['not-a-company']}))),/Unknown pet/);
  assert.throws(()=>validateSpecialCapabilities(reg(entry({pets:[]}))),/at least one pet/);
  assert.throws(()=>validateSpecialCapabilities(reg(entry(),entry())),/Duplicate/);
  assert.throws(()=>validateSpecialCapabilities(reg(entry({status:'live'}))),/Unknown status/);
  assert.throws(()=>validateSpecialCapabilities(reg(entry({service:'../etc'}))),/services\/<name>/);
  assert.throws(()=>validateSpecialCapabilities(reg(entry({live:true}))),/Unexpected field/);
  assert.throws(()=>validateSpecialCapabilities(reg()),/Invalid special capability registry/);
});
