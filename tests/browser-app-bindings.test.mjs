import test from 'node:test';
import assert from 'node:assert/strict';
import {validateAppBindings} from '../lib/browser-apps.mjs';

const pets = [{slug:'junction-s-pankki',id:'junction.s-pankki'}, {slug:'junction-meta',id:'junction.meta'}];
const solutions = [{id:'banker',agentIds:['junction.s-pankki']}];
const catalog = petSlug => ({schemaVersion:1,apps:[{petSlug,solution:'banker'}]});
test('Banker belongs to the existing S-Pankki pet and multiple apps may share it', () => {
  const value = catalog('junction-s-pankki');
  value.apps.push({...value.apps[0]});
  assert.equal(validateAppBindings(value,pets,solutions).length,2);
});
test('nonexistent Banker pet is rejected instead of silently losing its app', () => {
  assert.throws(() => validateAppBindings(catalog('junction-banker'),pets,solutions), /Unknown app pet/);
});
test('known but unrelated pet and missing solution are rejected', () => {
  assert.throws(() => validateAppBindings(catalog('junction-meta'),pets,solutions), /not selected/);
  assert.throws(() => validateAppBindings(catalog('junction-s-pankki'),pets,[]), /Unknown app solution/);
});
