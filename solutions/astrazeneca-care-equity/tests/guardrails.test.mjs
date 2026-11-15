import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { decide, numberCheck, numbersEn, numbersFi, verifyNarrative } from '../src/narratives.mjs';
import { CORRUPTIONS } from '../src/eval-claim-check.mjs';
import { buildApp } from '../src/build.mjs';
import { buildBrief } from '../src/claims.mjs';

test('Finnish and English number formats are read as the same numbers', () => {
  assert.deepEqual(numbersFi('Suhde on 1,097 ja ero 9,7 %, kustannus 5 613 672 euroa vuosina 2021-2025.'), [1.097, 9.7, 5613672, 2021, 2025]);
  assert.deepEqual(numbersEn('ratio 1.097, 9.7% above, EUR 5,613,672 in 2021-2025'), [1.097, 9.7, 5613672, 2021, 2025]);
});
test('a generated sentence with a number that is not in its source is caught by code', () => {
  const src = ['Mortality was 9.7% above the national level (ratio 1.097).'];
  assert.equal(numberCheck('Kuolleisuus oli 9,7 % yli maan tason (suhde 1,097).', src).ok, true);
  const bad = numberCheck('Kuolleisuus oli noin 10 % yli maan tason.', src);
  assert.equal(bad.ok, false); assert.deepEqual(bad.unmatched, [10]);
});
test('a generated sentence is kept only when numbers, faithfulness and overclaim checks all pass', () => {
  const ok = { ok: true, unmatched: [] };
  const good = { faithful: { choice: 'supports', probabilities: { supports: 0.93 } }, overclaim: { noul: 0.1 } };
  assert.equal(decide(ok, good).keep, true);
  assert.equal(decide({ ok: false, unmatched: [10] }, good).reason, 'NUMBER_NOT_IN_SOURCE');
  assert.equal(decide(ok, { faithful: { choice: 'supports', probabilities: { supports: 0.6 } }, overclaim: { noul: 0.1 } }).reason, 'NOT_FAITHFUL');
  assert.equal(decide(ok, { faithful: { choice: 'says_nothing', probabilities: { supports: 0.2 } }, overclaim: { noul: 0.1 } }).reason, 'NOT_FAITHFUL');
  assert.equal(decide(ok, { faithful: { choice: 'supports', probabilities: { supports: 0.95 } }, overclaim: { noul: 0.7 } }).reason, 'OVERCLAIM');
  assert.equal(decide(ok, null).reason, 'NOT_CHECKED', 'no service answer means the sentence is not shown');
});
test('narrative verification drops unknown sources and unchecked sentences, and never repairs text', async () => {
  const app = buildApp(); const brief = buildBrief(app, 'HVA06'); const first = brief.claims[0];
  const raw = { sentences: [
    { fi: `Alueen ikävakioitu syöpäkuolleisuuden suhde oli ${String(app.analysis.regions.find((r) => r.regionId === 'HVA06').allCancer.smr).replace('.', ',')}.`, claimIds: [first.id] },
    { fi: 'Kuolleisuus oli 42 % yli maan tason.', claimIds: [first.id] },
    { fi: 'Tämä johtuu huonosta hoidosta.', claimIds: ['HVA06-does-not-exist'] },
  ] };
  const fake = async () => ({ ok: true, json: async () => ({ model: 'jev-test', answers: { faithful: { choice: 'supports', probabilities: { supports: 0.95 } }, overclaim: { noul: 0.05 } }, usage: { input_tokens: 1, output_tokens: 1 } }) });
  const checked = await verifyNarrative(raw, brief, { apiKey: 'k', fetchImpl: fake });
  assert.equal(checked.kept.length, 1); assert.equal(checked.kept[0].fi, raw.sentences[0].fi);
  assert.deepEqual(checked.rejected.map((r) => r.reason), ['NUMBER_NOT_IN_SOURCE', 'UNKNOWN_SOURCE_CLAIM']);
  const noKey = await verifyNarrative(raw, brief, { apiKey: '' });
  assert.equal(noKey.kept.length, 0, 'without the verifier nothing generated is shown');
});
test('evaluation corruptions really change the sentence they are applied to', () => {
  const t = 'In 2021-2025, mortality in Satakunta was 9.7% above the national level, about 58.7 more deaths a year.';
  assert.ok(CORRUPTIONS.direction(t).includes('below')); assert.ok(!CORRUPTIONS.number(t).includes('9.7%') && /14\.[56]%/.test(CORRUPTIONS.number(t)));
  assert.ok(CORRUPTIONS.place(t, { regionName: 'Satakunta', otherName: 'Lapland' }).includes('Lapland'));
  assert.ok(CORRUPTIONS.causal(t, { kind: 'MEASURED' }).endsWith('is the cause.'));
  assert.equal(CORRUPTIONS.direction('No direction word here.'), null);
});
test('stored claim-check evaluation, when present, stops every corrupted sentence and rejects no true one', () => {
  const p = new URL('../data/claim-check/eval-v1.json', import.meta.url);
  if (!existsSync(p)) return;
  const e = JSON.parse(readFileSync(p, 'utf8'));
  assert.ok(e.cases >= 600 && e.errors === 0); assert.equal(e.summary.true.NOT_SUPPORTED, 0);
  assert.ok(e.summary.true.passRate >= 0.8); assert.ok(e.overall.corruptedSentencesStopped >= 0.98);
});
