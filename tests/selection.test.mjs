import test from 'node:test';
import assert from 'node:assert/strict';
import {readSelection, resolveSelection, petHref} from '../apps/catalog/src/selection.mjs';

const pets = [{slug: 'junction-mariadb'}, {slug: 'junction-aiven'}, {slug: 'junction-arduino'}];

test('company deep links resolve exactly and never fall back to another company', () => {
  assert.deepEqual(readSelection(''), {kind: 'default', slug: 'junction-mariadb'});
  assert.equal(resolveSelection(pets, pets, readSelection('')).pet, pets[0]);
  assert.equal(resolveSelection(pets, pets, readSelection('?pet=junction-aiven')).pet, pets[1]);
  assert.deepEqual(resolveSelection(pets, pets, readSelection('?pet=junction-unknown')), {pet: null, reason: 'unknown'});
  assert.deepEqual(resolveSelection(pets, pets.slice(0, 1), readSelection('?pet=junction-aiven')), {pet: null, reason: 'filtered'});
  assert.equal(resolveSelection(pets, pets.slice(1), readSelection('')).pet, pets[1]);
  assert.deepEqual(resolveSelection(pets, [], readSelection('')), {pet: null, reason: 'empty'});
});

test('duplicate, malformed and non-canonical selectors fail closed', () => {
  for (const search of [
    '?pet=', '?pet=not-junction', '?pet=junction-aiven&pet=junction-mariadb',
    '?pet=junction-aiven&pet=', '?pet=../admin', '?pet=junction-%2Fadmin',
    '?pet=junction-%20aiven', '?pet=JUNCTION-AIVEN', '?pet=junction-aiven%00',
    `?pet=junction-${'a'.repeat(100)}`,
  ]) {
    assert.deepEqual(readSelection(search), {kind: 'invalid'}, search);
    assert.deepEqual(resolveSelection(pets, pets, readSelection(search)), {pet: null, reason: 'invalid'});
  }
});

test('shareable selections never carry an auth grant, token or stale URL fragment', () => {
  const url = new URL(petHref('https://chibi.pet/junction/index.html?token=secret&pet=junction-mariadb#private', 'junction-aiven'));
  assert.equal(url.origin, 'https://chibi.pet');
  assert.equal(url.pathname, '/junction/index.html');
  assert.equal(url.search, '?pet=junction-aiven');
  assert.equal(url.hash, '');
  assert.deepEqual(readSelection(url.search), {kind: 'explicit', slug: 'junction-aiven'});
  assert.throws(() => petHref('https://chibi.pet/junction/', '../admin'));
  assert.throws(() => petHref('http://chibi.pet/junction/', 'junction-aiven'));
  assert.match(petHref('http://localhost:5173/?pet=junction-mariadb', 'junction-aiven'), /\?pet=junction-aiven$/);
});

test('history selection is a pure, reversible URL state', () => {
  const initial = 'https://chibi.pet/junction/?pet=junction-aiven';
  const next = petHref(initial, 'junction-arduino');
  assert.equal(resolveSelection(pets, pets, readSelection(new URL(next).search)).pet, pets[2]);
  assert.equal(resolveSelection(pets, pets, readSelection(new URL(initial).search)).pet, pets[1]);
});
