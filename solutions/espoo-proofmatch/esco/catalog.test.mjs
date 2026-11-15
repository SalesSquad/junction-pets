import test from 'node:test';
import assert from 'node:assert/strict';
import { ESCO_CATALOG } from './catalog.mjs';
import { validateCatalog, definitionUrl } from './validation.mjs';
const copy = () => structuredClone(ESCO_CATALOG);
test('real public snapshot validates and has six distinct bilingual skill concepts', () => {
  assert.equal(validateCatalog(copy()), true);
  assert.equal(new Set(ESCO_CATALOG.categories.flatMap(c => c.results.map(v => v.uri))).size, 6);
});
test('source URL is constructed from a strict EU-only concept URI', () => {
  const uri = ESCO_CATALOG.categories[0].results[0].uri;
  const result = new URL(definitionUrl(uri));
  assert.equal(result.hostname, 'ec.europa.eu');
  assert.equal(result.searchParams.get('uri'), uri);
  assert.throws(() => definitionUrl('https://evil.example/redirect'), /ESCO_INVALID_CATALOG/);
});
test('reject duplicate identities and unexpected source/version', () => {
  const a = copy(); a.categories[1].results[0].uri = a.categories[0].results[0].uri;
  assert.throws(() => validateCatalog(a), /concept-uri/);
  const b = copy(); b.versionRequested = 'v1.0.9';
  assert.throws(() => validateCatalog(b), /version/);
  const c = copy(); c.categories[0].requestUrl = 'https://evil.example/';
  assert.throws(() => validateCatalog(c), /source-url/);
});
test('reject missing Finnish translations and unsafe identifiers', () => {
  const a = copy(); a.categories[0].results[0].fi = '';
  assert.throws(() => validateCatalog(a), /labels/);
  const b = copy(); b.categories[0].results[0].uri = 'javascript:alert(1)';
  assert.throws(() => validateCatalog(b), /concept-uri/);
});
test('snapshot cannot claim hiring or candidate validation', () => {
  assert.match(ESCO_CATALOG.notice, /no verified candidate proficiency/i);
  assert.equal(JSON.stringify(ESCO_CATALOG).includes('candidateId'), false);
  assert.equal(JSON.stringify(ESCO_CATALOG).includes('email'), false);
});
