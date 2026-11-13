import {createHash} from 'node:crypto';

// These two public documents are pinned to reviewed Aiven upstream bytes.
// This module neither connects to an Aiven project nor holds Chibi authority.
export const AIVEN_DOCS_COMMIT = 'fc97657f9fabcb4e13f7385178aaf77b0d8faf65';
export const AIVEN_DOCS_REPOSITORY = 'https://github.com/aiven/aiven-docs';
export const AIVEN_DOCS_LICENSE = 'Apache-2.0';
export const AIVEN_LLM_INDEX = 'https://aiven.io/docs/llms.txt';

const RAW_ROOT = 'https://raw.githubusercontent.com/aiven/aiven-docs/' + AIVEN_DOCS_COMMIT + '/';
const MAX_DOCUMENT_BYTES = 16_384;
const MAX_INDEX_BYTES = 96_000;
const MAX_QUERY_CHARS = 256;
const MAX_TIMEOUT_MS = 5_000;
const MIN_SCORE = 5;
const OUT_OF_SCOPE_ACTIONS = new Set([
  'delete', 'deleting', 'remove', 'removing', 'drop', 'destroy', 'destroying',
  'terminate', 'terminating', 'wipe', 'purge', 'truncate', 'erase',
  'poista', 'poistaminen', 'tuhoa', 'tuhoaminen',
]);

const SOURCES = Object.freeze([
  Object.freeze({
    id: 'kafka-consumer-groups',
    title: 'Monitor an Apache Kafka consumer group',
    summary: 'Aiven guidance for observing Kafka consumer groups, including consumer lag.',
    path: 'docs/products/kafka/concepts/monitor-consumer-group.md',
    publicUrl: 'https://aiven.io/docs/products/kafka/concepts/monitor-consumer-group',
    sha256: '5719fb1d842b76527dc1e54fd84ce1e5bbecd6c7adfda65e0256238086173f1f',
    terms: Object.freeze({
      kafka: 1, consumer: 2, consumers: 2, group: 1, groups: 1,
      lag: 3, offset: 2, offsets: 2, monitor: 2, monitoring: 2,
      kuluttajaryhmä: 4, kuluttajaryhmät: 4, viive: 2,
    }),
    phrases: Object.freeze([['consumer group', 4], ['consumer lag', 4],
      ['kafka consumer', 3], ['kuluttajaryhmä', 3]]),
  }),
  Object.freeze({
    id: 'postgresql-slow-queries',
    title: 'Optimize slow PostgreSQL queries',
    summary: 'Aiven guidance for identifying and optimizing PostgreSQL slow queries, including pg_stat_statements.',
    path: 'docs/products/postgresql/howto/optimize-pg-slow-queries.md',
    publicUrl: 'https://aiven.io/docs/products/postgresql/howto/optimize-pg-slow-queries',
    sha256: 'b7189c102de0e3662a866f0f5f96c30614d2fe6543915882c7009b686cda29bd',
    terms: Object.freeze({
      postgresql: 1, postgres: 1, pg: 1, slow: 3, query: 2, queries: 2,
      performance: 2, optimize: 2, optimization: 2, index: 2, indexes: 2,
      pg_stat_statements: 5, hidas: 3, hitaat: 3, kysely: 2, kyselyt: 2,
    }),
    phrases: Object.freeze([['slow query', 4], ['slow queries', 4],
      ['pg_stat_statements', 4], ['hidas kysely', 4]]),
  }),
]);

const failure = code => ({ok: false, code});
const digestBytes = rawBytes => createHash('sha256').update(rawBytes).digest('hex');

function parseQuery(query) {
  if (typeof query !== 'string' || query.length < 3 || query.length > MAX_QUERY_CHARS ||
      /[\u0000-\u001f\u007f]/u.test(query)) return null;
  const normalized = query.normalize('NFKC').toLocaleLowerCase('en-US')
    .replace(/[^\p{L}\p{N}_]+/gu, ' ').trim().replace(/\s+/g, ' ');
  const words = normalized.match(/[\p{L}\p{N}_]+/gu) ?? [];
  if (words.length === 0 || words.length > 32) return null;
  return {normalized, tokens: new Set(words)};
}

function relevance(parsed, source) {
  let score = 0;
  const matched = new Set();
  let phraseMatched = false;
  for (const [term, weight] of Object.entries(source.terms)) {
    if (parsed.tokens.has(term)) {
      matched.add(term);
      score += weight;
    }
  }
  for (const [phrase, weight] of source.phrases) {
    if (parsed.normalized.includes(phrase)) {
      phraseMatched = true;
      score += weight;
    }
  }
  return score >= MIN_SCORE && (matched.size >= 2 || phraseMatched) ? score : 0;
}

function rank(query) {
  const parsed = parseQuery(query);
  if (!parsed) return failure('INVALID_QUERY');
  // This tool is knowledge retrieval, never an operation or workflow authority.
  // Conservative abstention on destructive intent avoids an action-like citation.
  if ([...parsed.tokens].some(token => OUT_OF_SCOPE_ACTIONS.has(token))) {
    return failure('ACTION_INTENT_OUT_OF_SCOPE');
  }
  const candidates = SOURCES.map(source => ({source, score: relevance(parsed, source)}))
    .filter(row => row.score >= MIN_SCORE)
    .sort((a, b) => b.score - a.score || a.source.id.localeCompare(b.source.id));
  return {ok: true, candidates};
}

/** Immutable expected source metadata; the bytes are NOT verified by listing them. */
export function listAivenPinnedSources() {
  return SOURCES.map(source => ({id: source.id, title: source.title,
    citationUrl: source.publicUrl, sourceCommit: AIVEN_DOCS_COMMIT,
    contentSha256: 'sha256:' + source.sha256, bytesVerifiedThisRun: false}));
}

/** Deterministic, network-free shortlist. A match is not a fetched or verified document. */
export function rankAivenDocs(query) {
  const selected = rank(query);
  if (!selected.ok) return {ok: false, code: selected.code, matches: []};
  return {
    ok: true,
    code: selected.candidates.length ? 'MATCHES_UNVERIFIED' : 'NO_RELEVANT_DOCUMENTS',
    matches: selected.candidates.map(({source, score}) => ({id: source.id, title: source.title, score})),
  };
}

async function boundedRead(response, expectedUrl, maxBytes) {
  if (!response || !Number.isInteger(response.status) ||
      response.status < 100 || response.status > 599) return failure('INVALID_RESPONSE');
  if (response.url !== expectedUrl) return failure('RESPONSE_URL_MISMATCH');
  if (response.status < 200 || response.status >= 300) {
    if (response.status >= 400 && response.status < 500) return failure('HTTP_4XX');
    if (response.status >= 500 && response.status < 600) return failure('HTTP_5XX');
    return failure('HTTP_UNEXPECTED_STATUS');
  }
  const getHeader = name => response.headers?.get?.(name);
  const mime = getHeader('content-type');
  if (typeof mime !== 'string' || !/^text\/(?:plain|markdown|x-markdown)(?:\s*;|$)/i.test(mime)) {
    return failure('UNEXPECTED_MEDIA_TYPE');
  }
  const length = getHeader('content-length');
  if (length !== null && length !== undefined && length !== '') {
    if (!/^\d+$/.test(length)) return failure('INVALID_CONTENT_LENGTH');
    if (Number(length) > maxBytes) return failure('RESPONSE_TOO_LARGE');
  }
  if (!response.body || typeof response.body.getReader !== 'function') return failure('INVALID_BODY_STREAM');
  const reader = response.body.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) return failure('INVALID_BODY_CHUNK');
      bytes += value.byteLength;
      if (bytes > maxBytes) {
        void reader.cancel().catch(() => {});
        return failure('RESPONSE_TOO_LARGE');
      }
      chunks.push(value);
    }
    if (bytes === 0) return failure('EMPTY_RESPONSE');
    const content = new Uint8Array(bytes);
    let cursor = 0;
    for (const chunk of chunks) {
      content.set(chunk, cursor);
      cursor += chunk.byteLength;
    }
    // Retain the ORIGINAL response bytes for hashing. TextDecoder strips a
    // UTF-8 BOM by default, so decoding and re-encoding changes the digest.
    return {ok: true, text: new TextDecoder('utf-8', {fatal: true}).decode(content), rawBytes: content};
  } catch {
    return failure('INVALID_BODY_STREAM');
  } finally {
    reader.releaseLock();
  }
}

/** Fixed-URL GET: no URL from a query, no credentials, no redirects, bounded stream/time. */
async function fetchBounded(url, {fetchImpl, timeoutMs, maxBytes, signal}) {
  if (typeof fetchImpl !== 'function') return failure('FETCH_UNAVAILABLE');
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > MAX_TIMEOUT_MS) {
    return failure('INVALID_TIMEOUT');
  }
  if (signal !== undefined && !(signal instanceof AbortSignal)) return failure('INVALID_ABORT_SIGNAL');
  if (signal?.aborted) return failure('CANCELLED');

  const controller = new AbortController();
  const onExternalAbort = () => controller.abort('cancelled');
  signal?.addEventListener('abort', onExternalAbort, {once: true});
  const timer = setTimeout(() => controller.abort('timeout'), timeoutMs);
  const interrupted = new Promise(resolve => {
    controller.signal.addEventListener('abort',
      () => resolve(failure(signal?.aborted ? 'CANCELLED' : 'TIMEOUT')), {once: true});
  });
  const request = Promise.resolve().then(() => fetchImpl(url, {
    method: 'GET', redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer',
    cache: 'no-store', headers: {'Accept': 'text/plain'}, signal: controller.signal,
  })).then(response => boundedRead(response, url, maxBytes), () => failure('NETWORK_ERROR'))
    .catch(() => failure('NETWORK_ERROR'));
  const result = await Promise.race([request, interrupted]);
  clearTimeout(timer);
  signal?.removeEventListener('abort', onExternalAbort);
  return signal?.aborted ? failure('CANCELLED') : result;
}

function verifiedDocument(source, score, bytes, bodySha, kind) {
  const synthetic = kind === 'synthetic-fixture';
  return {
    id: source.id, title: synthetic ? 'Synthetic fixture: ' + source.title : source.title,
    summary: synthetic ? 'Test-only fixture; no official Aiven documentation verified.' : source.summary,
    score,
    citation: {
      publisher: synthetic ? null : 'Aiven',
      url: synthetic ? null : source.publicUrl,
      title: synthetic ? 'Synthetic test fixture' : source.title,
      syntheticOnly: synthetic,
      pinnedRawSourceBytesMatched: !synthetic,
    },
    provenance: {
      kind, repository: synthetic ? null : AIVEN_DOCS_REPOSITORY,
      sourceCommit: synthetic ? null : AIVEN_DOCS_COMMIT,
      sourcePath: synthetic ? null : source.path,
      contentSha256: 'sha256:' + bodySha,
      contentBytes: bytes,
      license: synthetic ? null : AIVEN_DOCS_LICENSE,
      pinnedRawBytesSha256Matched: !synthetic,
      syntheticFixtureSha256Matched: synthetic,
    },
  };
}

async function searchSelected(query, loadSource, kind, hashes) {
  const shortlist = rank(query);
  const synthetic = kind === 'synthetic-fixture';
  const safeBase = {mode: synthetic ? 'synthetic-test-only-document-search' : 'public-read-only-document-search',
    evidenceKind: kind,
    pinnedOfficialDocsVerified: false, hostGrantVerified: false, providerInvocationVerified: false};
  if (!shortlist.ok) return {...safeBase, ok: false, code: shortlist.code, documents: [], failures: []};
  if (!shortlist.candidates.length) {
    return {...safeBase, ok: true, code: 'NO_RELEVANT_DOCUMENTS', documents: [], failures: []};
  }
  const rows = await Promise.all(shortlist.candidates.map(async ({source, score}) => {
    try {
      const loaded = await loadSource(source);
      if (!loaded?.ok) return {error: {id: source.id, code: loaded?.code ?? 'SOURCE_UNAVAILABLE'}};
      if (!(loaded.rawBytes instanceof Uint8Array) || loaded.rawBytes.byteLength === 0) {
        return {error: {id: source.id, code: 'INVALID_BODY'}};
      }
      if (loaded.rawBytes.byteLength > MAX_DOCUMENT_BYTES) {
        return {error: {id: source.id, code: 'RESPONSE_TOO_LARGE'}};
      }
      const bodySha = digestBytes(loaded.rawBytes);
      if (bodySha !== hashes[source.id]) {
        return {error: {id: source.id, code: 'SOURCE_DIGEST_MISMATCH'}};
      }
      return {document: verifiedDocument(source, score, loaded.rawBytes.byteLength, bodySha, kind)};
    } catch {
      return {error: {id: source.id, code: 'SOURCE_UNAVAILABLE'}};
    }
  }));
  const documents = rows.flatMap(row => row.document ? [row.document] : []);
  const failures = rows.flatMap(row => row.error ? [row.error] : []);
  // A test fixture may pass its OWN digest without proving any Aiven bytes.
  // It must never inherit the code/flag reserved for pinned public source data.
  const code = documents.length === 0
    ? (synthetic ? 'SYNTHETIC_FIXTURE_UNAVAILABLE' : 'DOCUMENTS_UNAVAILABLE')
    : failures.length
      ? (synthetic ? 'SYNTHETIC_FIXTURE_PARTIAL' : 'PARTIAL_VERIFIED')
      : (synthetic ? 'SYNTHETIC_FIXTURE_DIGEST_MATCHED' : 'VERIFIED_SOURCE_BYTES');
  return {...safeBase, ok: documents.length > 0, code, documents, failures,
    pinnedOfficialDocsVerified: !synthetic && code === 'VERIFIED_SOURCE_BYTES'};
}

/**
 * Official public corpus. Only two fixed raw.githubusercontent.com source URLs,
 * each at an exact reviewed commit+SHA-256. No project credentials or host grant.
 */
export async function searchAivenPublicDocs(query, {
  fetchImpl = globalThis.fetch, timeoutMs = 3000, signal,
} = {}) {
  return searchSelected(query, source => fetchBounded(RAW_ROOT + source.path,
    {fetchImpl, timeoutMs, maxBytes: MAX_DOCUMENT_BYTES, signal}),
  'pinned-public-docs', Object.fromEntries(SOURCES.map(row => [row.id, row.sha256])));
}

/**
 * Test-only fixture boundary. Optional injected fake fetch exercises the same
 * bounded raw-byte reader; no fixture can claim official source proof.
 */
export async function searchSyntheticAivenFixture(query, {
  bodies = {}, hashes = {}, fetchImpl, timeoutMs = 3000, signal,
} = {}) {
  return searchSelected(query, async source => {
    // Optional fake Response transport exercises the identical bounded reader
    // without giving the fixture any claim over official pinned source bytes.
    if (fetchImpl !== undefined) return fetchBounded(RAW_ROOT + source.path,
      {fetchImpl, timeoutMs, maxBytes: MAX_DOCUMENT_BYTES, signal});
    const body = bodies[source.id];
    if (typeof body === 'string') return {ok: true, rawBytes: new TextEncoder().encode(body)};
    if (body instanceof Uint8Array) return {ok: true, rawBytes: body};
    return failure('FIXTURE_MISSING');
  }, 'synthetic-fixture', hashes);
}

/**
 * Optional live link discovery; llms.txt is unpinned and NOT a source-of-truth.
 * Never visit links found within its body; return only hard-coded official URLs.
 */
export async function discoverAivenDocsLinks({
  fetchImpl = globalThis.fetch, timeoutMs = 3000, signal,
} = {}) {
  const loaded = await fetchBounded(AIVEN_LLM_INDEX,
    {fetchImpl, timeoutMs, maxBytes: MAX_INDEX_BYTES, signal});
  if (!loaded.ok) return {ok: false, code: loaded.code, links: [], evidenceKind: 'untrusted-index'};
  // Exact Markdown link targets only: URL prefixes, query strings and links
  // to attacker hosts must not count as official index discovery.
  const links = SOURCES.filter(source =>
    loaded.text.includes('](' + source.publicUrl + '.md)') ||
    loaded.text.includes('](' + source.publicUrl + ')'))
    .map(source => ({id: source.id, url: source.publicUrl}));
  return {ok: true, code: 'INDEX_LINKS_ADVISORY_ONLY', links,
    indexUrl: AIVEN_LLM_INDEX, evidenceKind: 'untrusted-live-index',
    indexSha256: 'sha256:' + digestBytes(loaded.rawBytes)};
}
