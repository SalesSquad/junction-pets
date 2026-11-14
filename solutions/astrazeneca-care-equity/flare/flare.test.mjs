// Comparability gate panel (web/flare.mjs). SYNTHETIC data. Run from the solution folder:
//   node --test flare/flare.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { flareGateHtml } from '../web/flare.mjs';

const GATE_URL = new URL('../data/flare/gate-v1.json', import.meta.url);
const GATE = existsSync(GATE_URL) ? JSON.parse(readFileSync(GATE_URL, 'utf8')) : null;
const FORBIDDEN = ['auto-confirmed', 'skips review', 'clinically accurate', 'works on real notes'];
const strip = (h) => h.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

test('no gate file renders a labelled empty state', () => {
  const h = flareGateHtml(null);
  assert.match(h, /chip synthetic/);
  assert.match(h, /No comparability-gate result is stored/);
});

test('renders the stored gate with labels, both arms and kept raw values', { skip: !GATE }, () => {
  const h = flareGateHtml(GATE);
  const t = strip(h);
  assert.match(h, /data-kind="SYNTHETIC"/);
  assert.match(t, /placeholder \(OECD\/EU-reported target\)/);
  assert.match(t, /placeholder thresholds/);
  assert.match(t, /six months/);
  assert.match(t, /FLARE-ready, not run in FLARE/); // the median-bias column
  assert.match(t, /If dates came from the raw scribe/);
  assert.match(t, /With the code resolver/);
  for (const p of FORBIDDEN) assert.ok(!t.toLowerCase().includes(p), p);
  const bad = (h.match(/data-gate="not-comparable"/g) || []).length;
  assert.equal(bad, GATE.summary.raw.not_comparable + GATE.summary.resolver.not_comparable);
  // every "not comparable" verdict sits in a row whose share is visible (shown once, in the second column)
  for (const m of h.matchAll(/<tr><th>[^<]*<\/th>([^]*?)<\/tr>/g)) {
    if (m[1].includes('not-comparable')) assert.match(m[1], /^<td><span class="n">([\d.]+%|suppressed)/);
  }
  assert.equal((h.match(/<tr><th>HVA/g) || []).length, 23);
});

test('every number from the gate sits inside a chipped data-kind block', { skip: !GATE }, () => {
  const h = flareGateHtml(GATE);
  const blocks = [...h.matchAll(/<(p|div|figure)[^>]*data-kind="([A-Z]+)"[^>]*>([^]*?)<\/\1>/g)];
  assert.ok(blocks.length >= 5);
  for (const [, , kind, inner] of blocks) {
    if (inner.includes('class="n"')) assert.ok(inner.includes(`chip ${kind.toLowerCase()}`), kind);
  }
});

test('real-data chip shows areas from the source, never a SYNTHETIC county code', { skip: !GATE }, () => {
  const h = flareGateHtml(GATE);
  const real = h.match(/<div class="real-data" data-kind="PUBLISHED">([^]*?)<\/div>/)[1];
  assert.match(real, /chip published/);
  assert.match(strip(real), /Can this area see its cancer stage\?/);
  assert.ok(!/HVA\d/.test(real));
  assert.match(strip(real), /Pirkanmaa wellbeing services county: 72% .* yes/);
  assert.match(strip(real), /Whole country: 42% .* no/);
});

test('fallback wording when FLARE did not run, and escaping', () => {
  const g = {
    title: '<script>x</script>', lede: 'a & b', counties: [{ county: 'HVA01', rtt: { share_within: 0.5, n: 10 }, completeness: { complete_share: 1, open_share: 0 },
      scribe: { raw: { comparable: false, median_bias_days: -5, missed_share: 0.2, events: 10, intervals: 6 }, resolver: { comparable: true, median_bias_days: 0, missed_share: 0, events: 10, intervals: 6 } } }],
    clock: { threshold_days: 42, threshold_label: 'placeholder (OECD/EU-reported target)' }, rule: { label: 'placeholder thresholds' },
    summary: { raw: { not_comparable: 1, of: 1 }, resolver: { not_comparable: 0, of: 1 } }, national: {}, flare: { ran: false },
  };
  const h = flareGateHtml(g);
  assert.match(h, /FLARE-ready, not run in FLARE: every column was computed in plain Python/);
  assert.ok(!h.includes('<script>'));
  assert.match(h, /<td><span class="n">50.0%<\/span>[^]*?<\/td><td>[^]*?<\/td><td><span class="missing-label" data-gate="not-comparable">/);
});
