import { roles, candidates, asOf } from './data.mjs';
import { rank, keywordRank } from './matcher.mjs';
export function benchmark() {
  const cases = roles.map(role => {
    const evidence = rank(role, candidates, asOf)[0];
    const keyword = keywordRank(role, candidates)[0];
    return { role: role.id, expected: [...role.relevantTopIds], evidenceTop: evidence.candidateId, evidenceCorrect: role.relevantTopIds.includes(evidence.candidateId), evidenceScore: evidence.score, keywordTop: keyword.candidateId, keywordCorrect: role.relevantTopIds.includes(keyword.candidateId), keywordHits: keyword.score };
  });
  return { label: 'SYNTHETIC / OFFLINE_DETERMINISTIC', metric: 'Prelabelled top-1 correctness (not hiring validity)', cases, evidenceCorrect: cases.filter(c => c.evidenceCorrect).length, keywordCorrect: cases.filter(c => c.keywordCorrect).length, total: cases.length };
}
if (typeof process !== 'undefined' && process.argv[1]?.endsWith('/benchmark.mjs')) console.log(JSON.stringify(benchmark(), null, 2));
