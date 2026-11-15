// Explicit public EU taxonomy refresh. Never send candidate, employer or private profile data.
import { writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { QUERIES, VERSION, validateCatalog } from './validation.mjs';
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const categories = [];
for (const query of QUERIES) {
  const requestUrl = 'https://ec.europa.eu/esco/api/search?text=' + query + '&type=skill&limit=3&language=en&selectedVersion=' + VERSION;
  const response = await fetch(requestUrl, {
    redirect: 'error', signal: AbortSignal.timeout(12000),
    headers: { Accept: 'application/json', 'User-Agent': 'Junction-ProofMatch-Public-ESCO/1.0' },
  });
  if (response.status !== 200 || !String(response.headers.get('content-type')).startsWith('application/json')) throw Error('ESCO_SOURCE_UNAVAILABLE');
  if (Number(response.headers.get('content-length') || 0) > 100000) throw Error('ESCO_RESPONSE_TOO_LARGE');
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length > 100000) throw Error('ESCO_RESPONSE_TOO_LARGE');
  const data = JSON.parse(bytes.toString('utf8'));
  if (data.text !== query || data.language !== 'en' || !Array.isArray(data.type) ||
      !data.type.includes('skill')) throw Error('ESCO_UNEXPECTED_RESPONSE');
  const results = data._embedded?.results;
  if (!Array.isArray(results) || results.length !== 3) throw Error('ESCO_UNEXPECTED_RESULTS');
  categories.push({
    query, requestUrl, rawResponseSha256: sha256(bytes), total: data.total,
    results: results.map(item => ({
      uri: item.uri, en: item.preferredLabel?.en, fi: item.preferredLabel?.fi,
    })),
  });
}
const catalog = { schemaVersion: 1, versionRequested: VERSION,
  observedAt: new Date().toISOString(), categories,
  notice: 'Public EU occupation/skill vocabulary only; no verified candidate proficiency, skill equivalence, ranking, hiring or sponsor endorsement.' };
validateCatalog(catalog);
const content = '// Generated from fixed public EU ESCO requests by refresh.mjs; not a client API key.\n' +
  'export const ESCO_CATALOG = Object.freeze(' + JSON.stringify(catalog).replace(/</g, '\\u003c') + ');\n';
await writeFile(fileURLToPath(new URL('./catalog.mjs', import.meta.url)), content, { encoding: 'utf8' });
console.log(JSON.stringify({ result: 'PUBLIC_ESCO_READ_ONLY', source: 'ec.europa.eu', observedAt: catalog.observedAt,
  categories: categories.map(c => ({ query: c.query, count: c.results.length, total: c.total, sha256: c.rawResponseSha256 })) }));
