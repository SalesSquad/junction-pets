// A bounded public glossary, never a credentialed candidate or recruiting lookup.
export const QUERIES = Object.freeze(['accessibility', 'software']);
export const VERSION = 'v1.2.0';
const SHA = /^[a-f0-9]{64}$/;
const URI = /^http:\/\/data\.europa\.eu\/esco\/skill\/[a-f0-9-]{36}$/;
const fail = reason => { throw new Error('ESCO_INVALID_CATALOG:' + reason); };
export function definitionUrl(uri) {
  if (typeof uri !== 'string' || !URI.test(uri)) fail('uri');
  const url = new URL('https://ec.europa.eu/esco/api/resource/skill');
  url.searchParams.set('uri', uri);
  url.searchParams.set('language', 'en');
  url.searchParams.set('selectedVersion', VERSION);
  return url.toString();
}
export function validateCatalog(doc) {
  if (!doc || doc.schemaVersion !== 1 || doc.versionRequested !== VERSION) fail('version');
  if (typeof doc.observedAt !== 'string' || !/^20\d\d-\d\d-\d\dT/.test(doc.observedAt)) fail('observed');
  if (!Array.isArray(doc.categories) || doc.categories.length !== QUERIES.length) fail('categories');
  const seen = new Set();
  for (const [index, category] of doc.categories.entries()) {
    if (category.query !== QUERIES[index] || !SHA.test(category.rawResponseSha256)) fail('query-or-sha');
    if (category.requestUrl !== 'https://ec.europa.eu/esco/api/search?text=' + QUERIES[index] + '&type=skill&limit=3&language=en&selectedVersion=v1.2.0') fail('source-url');
    if (!Number.isInteger(category.total) || category.total < 3 || !Array.isArray(category.results) || category.results.length !== 3) fail('rows');
    for (const term of category.results) {
      if (!term || typeof term.uri !== 'string' || !URI.test(term.uri) || seen.has(term.uri)) fail('concept-uri');
      if (typeof term.en !== 'string' || typeof term.fi !== 'string' ||
          !term.en.trim() || !term.fi.trim() || term.en.length > 200 || term.fi.length > 200) fail('labels');
      seen.add(term.uri);
    }
  }
  return true;
}
