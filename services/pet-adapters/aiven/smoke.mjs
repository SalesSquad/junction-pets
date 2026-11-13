#!/usr/bin/env node
import {listAivenPinnedSources, rankAivenDocs, searchAivenPublicDocs} from './adapter.mjs';
import {
  qualifiesLivePinnedResult, qualifiesNoDocuments, qualifiesOfflineShortlist,
} from './smoke-gates.mjs';

// Bounded public sponsor demo; no private Chibi data, model call or host grant.
// Live anonymous network reads are explicitly opt-in and never run in CI.
const scenarios = [
  {scenario: 'kafka-lag', question: 'Kafka consumer group lag', expectedId: 'kafka-consumer-groups'},
  {scenario: 'postgres-slow-query', question: 'PostgreSQL slow queries indexes', expectedId: 'postgresql-slow-queries'},
  {scenario: 'nonsense-abstention', question: 'glittery bicycle soup orchestra', expectedId: null},
];
const args = process.argv.slice(2);
if (args.length > 1 || args.some(arg => arg !== '--offline' && arg !== '--live')) {
  process.stderr.write('Usage: node services/pet-adapters/aiven/smoke.mjs [--offline | --live]\n');
  process.exit(2);
}
const live = args[0] === '--live';
const expected = new Map(listAivenPinnedSources().map(row => [row.id, row]));
let passedAll = true;

for (const {scenario, question, expectedId} of scenarios) {
  if (!live) {
    const ranked = rankAivenDocs(question);
    const smokeGatePassed = qualifiesOfflineShortlist(ranked, expectedId);
    console.log(JSON.stringify({
      scenario, mode: 'OFFLINE_UNVERIFIED_SHORTLIST', code: ranked.code,
      smokeGatePassed, citations: ranked.matches.map(match => ({
        id: match.id, url: expected.get(match.id)?.citationUrl ?? null,
        expectedSha256: expected.get(match.id)?.contentSha256 ?? null,
        verifiedThisRun: false,
      })),
    }));
    if (!smokeGatePassed) passedAll = false;
    continue;
  }
  const result = await searchAivenPublicDocs(question, {timeoutMs: 5000});
  const smokeGatePassed = expectedId === null
    ? qualifiesNoDocuments(result)
    : qualifiesLivePinnedResult(result, expected.get(expectedId));
  console.log(JSON.stringify({
    scenario, mode: 'LIVE_PUBLIC_DOCS_READ_ONLY', code: result.code,
    smokeGatePassed, citations: result.documents.map(doc => ({
      id: doc.id, url: doc.citation.url,
      sourceCommit: doc.provenance.sourceCommit,
      contentSha256: doc.provenance.contentSha256,
      pinnedRawBytesSha256Matched: doc.provenance.pinnedRawBytesSha256Matched,
    })),
    failures: result.failures,
    hostGrantVerified: false, providerInvocationVerified: false,
  }));
  if (!smokeGatePassed) passedAll = false;
}
if (!passedAll) process.exitCode = 1;
