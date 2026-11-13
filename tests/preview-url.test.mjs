import test from 'node:test';
import assert from 'node:assert/strict';
import {localPreviewBase, previewSelectionUrl} from './preview-url.mjs';

test('browser acceptance URLs retain root and mounted catalogue paths', () => {
  for (const [input, expectedPath] of [
    ['http://127.0.0.1:4173', '/'],
    ['http://localhost:4173/junction', '/junction/'],
    ['http://127.0.0.1:4173/junction/', '/junction/'],
  ]) {
    const base = localPreviewBase(input);
    assert.equal(base.pathname, expectedPath);
    for (const query of [
      'pet=junction-aiven',
      'pet=junction-arduino',
      'pet=junction-does-not-exist',
      'pet=junction-aiven&pet=junction-mariadb',
    ]) {
      const url = previewSelectionUrl(base, query);
      assert.equal(url.pathname, expectedPath);
      assert.equal(url.search, `?${query}`);
    }
  }
});

test('browser acceptance refuses remote, authenticated and preselected preview URLs', () => {
  for (const input of [
    'https://127.0.0.1:4173/junction/',
    'http://chibi.pet/junction/',
    'http://user:secret@localhost:4173/junction/',
    'http://localhost:4173/junction/?pet=junction-aiven',
    'http://localhost:4173/junction/#fragment',
  ]) assert.throws(() => localPreviewBase(input), input);
});
