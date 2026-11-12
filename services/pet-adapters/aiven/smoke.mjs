#!/usr/bin/env node
import {listAivenPinnedSources, rankAivenDocs, searchAivenPublicDocs} from './adapter.mjs';

// Bounded public sponsor demo: two relevant questions and one abstention.
// No raw fetched text, Chibi grant, Aiven project data or model execution.
const scenarios = [
  ['kafka-lag', 'Kafka consumer group lag'],
  ['postgres-slow-query', 'PostgreSQL slow queries indexes'],
  ['nonsense-abstention', 'glittery bicycle soup orchestra'],
];

const args = process.argv.slice(2);
if (args.some(arg => arg !== '--offline')) {
  process.stderr.write('Usage: node services/pet-adapters/aiven/smoke.mjs [--offline]\n');
  process.exit(2);
}
const offline = args.includes('--offline');
const expected = new Map(listAivenPinnedSources().map(row => [row.id, row]));
let unavailable = false;

for (const [scenario, question] of scenarios) {
  if (offline) {
    const ranked = rankAivenDocs(question);
    console.log(JSON.stringify({
      scenario, mode: 'OFFLINE_UNVERIFIED_SHORTLIST', code: ranked.code,
      citations: ranked.matches.map(match => ({
        id: match.id, url: expected.get(match.id).citationUrl,
        expectedSha256: expected.get(match.id).contentSha256,
        verifiedThisRun: false,
      })),
    }));
    continue;
  }
  const result = await searchAivenPublicDocs(question, {timeoutMs: 3000});
  console.log(JSON.stringify({
    scenario, mode: 'LIVE_PUBLIC_DOCS_READ_ONLY', code: result.code,
    citations: result.documents.map(doc => ({
      id: doc.id, url: doc.citation.url,
      sourceCommit: doc.provenance.sourceCommit,
      contentSha256: doc.provenance.contentSha256,
      digestMatched: doc.provenance.digestMatched,
    })),
    failures: result.failures,
    hostGrantVerified: false, providerInvocationVerified: false,
  }));
  if (!result.ok) unavailable = true;
}
if (unavailable) process.exitCode = 1;
