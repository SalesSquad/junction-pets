import {pathToFileURL} from 'node:url';
import {analyzeCoordination} from './public/coordination.mjs';

// Independently authored mechanistic examples: no legacy generator, OOD corpus or intent labels.
// These validate the declared observable contract; they are not a blinded performance benchmark.
const origin = Date.parse('2026-11-15T12:00:00Z');
const message = 'Public research demonstration opens tomorrow with the published timetable';
function observations(n, {spacing = 2000, offset = 0, destination = 'https://fixture.test/article?id=7', target = ''} = {}) {
  return Array.from({length: n}, (_, i) => ({
    id: 'observation-' + i, account: 'participant-' + i,
    time: new Date(origin + offset + i * spacing).toISOString(), text: message,
    url: destination, amplifies: target, accountAgeDays: null, attribution: ''
  }));
}
function cases() {
  const positive = [
    ...[4, 5, 6, 8].map(n => ({id: 'pairwise-' + n, coordinated: true, events: observations(n)})),
    {id: 'boundary-60s', coordinated: true, events: observations(4, {spacing: 20000})},
    {id: 'tracking-variants', coordinated: true, events: observations(5).map((e, i) => ({...e, url: e.url + '&utm_campaign=' + i}))},
    {id: 'amplification-instead-of-url', coordinated: true, events: observations(5, {destination: '', target: 'shared-announcement'})},
    {id: 'declared-syndication-is-still-coordinated', coordinated: true, events: observations(5).map(e => ({...e, attribution: 'A declared public bulletin'}))},
    {id: 'established-accounts-can-coordinate', coordinated: true, events: observations(5).map(e => ({...e, accountAgeDays: 1200}))},
    {id: 'two-rounds', coordinated: true, events: [...observations(4), ...observations(4, {offset: 600000, destination: 'https://fixture.test/article?id=8'}).map(e => ({...e, id: 'round2-' + e.id}))]}
  ];
  const negative = [
    {id: 'empty', coordinated: false, events: []},
    ...[1, 2, 3].map(n => ({id: 'below-four-' + n, coordinated: false, events: observations(n)})),
    {id: 'single-account', coordinated: false, events: observations(12).map(e => ({...e, account: 'one-participant'}))},
    {id: 'text-without-second-trace', coordinated: false, events: observations(7, {destination: ''})},
    {id: 'different-content-identifiers', coordinated: false, events: observations(7).map((e, i) => ({...e, url: 'https://fixture.test/article?id=' + i}))},
    {id: 'shared-url-divergent-text', coordinated: false, events: observations(5).map((e, i) => ({...e, text: [
      'Bird watching report from the northern lake', 'Engine assembly notes about steel cylinder seals',
      'School meal calendar with fresh vegetable recipes', 'Train travel timetable around western regional stations',
      'Astronomy observations near the southern winter horizon'
    ][i]}))},
    {id: 'outside-coaction-window', coordinated: false, events: observations(6, {spacing: 61000})},
    {id: 'three-account-time-chain', coordinated: false, events: observations(6, {spacing: 30000})}
  ];
  return [...positive, ...negative];
}
const rate = (numerator, denominator) => ({numerator, denominator, value: denominator ? numerator / denominator : null});
export function evaluateV2() {
  const rows = cases().map(c => {
    const result = analyzeCoordination(c.events);
    return {id: c.id, coordinated: c.coordinated, predicted: result.findings.some(f => f.review),
      intentAbstained: result.findings.every(f => f.intent === 'UNKNOWN')};
  });
  const tp = rows.filter(r => r.coordinated && r.predicted).length;
  const fp = rows.filter(r => !r.coordinated && r.predicted).length;
  const tn = rows.filter(r => !r.coordinated && !r.predicted).length;
  const fn = rows.filter(r => r.coordinated && !r.predicted).length;
  return {
    mode: 'SYNTHETIC_CONTRACT_VALIDATION', policy: 'coordination-v2', cases: rows.length,
    coordination: {tp, fp, tn, fn, precision: rate(tp, tp + fp), falsePositiveRate: rate(fp, fp + tn), recall: rate(tp, tp + fn)},
    intentAbstention: rate(rows.filter(r => r.intentAbstained).length, rows.length),
    failures: rows.filter(r => r.coordinated !== r.predicted || !r.intentAbstained),
    rows,
    limitations: 'Authored mechanistic examples validate a declared observable-coordination contract, not independent field accuracy; not comparable to legacy v1 harmful-intent OOD metrics. Full abstention on intent is required, not a claim of malicious-actor detection.'
  };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) console.log(JSON.stringify(evaluateV2(), null, 2));
