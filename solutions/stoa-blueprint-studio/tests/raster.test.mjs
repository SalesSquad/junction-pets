import test from 'node:test';
import assert from 'node:assert/strict';
import { isCorrect, parseNumber } from '../raster/score.mjs';
import { extractJson, normalizeCoords } from '../raster/vlm.mjs';
import { classifyTag, countByRule, roomCategories, ruleFor } from '../raster/rules.mjs';
import { dedupe } from '../raster/ocr.mjs';
import { split } from '../raster/dataset.mjs';

test('sponsor scoring: exact counts, 2% for quantities', () => {
  assert.equal(isCorrect({ type: 'count', answer: 3 }, 3), true);
  assert.equal(isCorrect({ type: 'count', answer: 3 }, '3 rooms'), true);
  assert.equal(isCorrect({ type: 'count', answer: 3 }, 3.4), false);
  assert.equal(isCorrect({ type: 'area', answer: 15.84 }, '16,1 m²'), true);
  assert.equal(isCorrect({ type: 'area', answer: 15.84 }, 16.3), false);
  assert.equal(isCorrect({ type: 'count', answer: 0 }, null), false);
  assert.equal(parseNumber('26,562 SF'), 26562);
  assert.equal(parseNumber('12,5'), 12.5);
});

test('model JSON is recovered from surrounding prose and fences', () => {
  assert.deepEqual(extractJson('Sure:\n```json\n{"answers":[{"id":"q1","answer":2}]}\n```'), { answers: [{ id: 'q1', answer: 2 }] });
  assert.equal(extractJson('no json here'), null);
});

test('coordinates in 0..1, per-mille or pixels normalize to 0..1', () => {
  assert.deepEqual(normalizeCoords([0.25, 0.5], 800, 600), [0.25, 0.5]);
  assert.deepEqual(normalizeCoords([250, 500], 800, 600), [0.25, 0.5]);
  assert.deepEqual(normalizeCoords([1600, 300], 3200, 1200), [0.5, 0.25]);
  assert.equal(normalizeCoords(['a', 1], 10, 10), null);
});

test('Finnish size tags: ~2 m high openings are doors, others windows', () => {
  for (const t of ['9x21/O', '8x19', 'PO/O 9x21', '10x21/V']) assert.equal(classifyTag(t), 'door', t);
  for (const t of ['13x12', '6x6', '11x16']) assert.equal(classifyTag(t), 'window', t);
  for (const t of ['1 310', '3 391', '14,2 m2', '100x200']) assert.equal(classifyTag(t), null, t);
});

test('room abbreviations map to categories only when they lead the label', () => {
  assert.deepEqual(roomCategories('MH'), ['bedroom']);
  assert.deepEqual(roomCategories('MH/TYÖH'), ['bedroom']);
  assert.deepEqual(roomCategories('S 3,8 m²'), ['sauna']);
  assert.deepEqual(roomCategories('LASITETTU PARVEKE'), ['balcony']);
  assert.deepEqual(roomCategories('SISÄÄNTULOKATOS'), []);
  assert.deepEqual(roomCategories('Uusi poistoventtiili'), []);
});

test('question routing: bathroom question is not mistaken for separate WC rooms', () => {
  assert.equal(ruleFor('How many bathrooms or washrooms (e.g. KH, KPH, PH, PESUH, SH) are on this floor plan, not counting separate WC rooms?'), 'bathroom');
  assert.equal(ruleFor('How many separate WC rooms (toilet rooms marked WC) are on this floor plan?'), 'wcRoom');
  assert.equal(ruleFor('How many toilet bowls (WC seats) are drawn on this floor plan?'), null);
  assert.equal(ruleFor('Kuinka monta ikkunaa pohjapiirustuksessa on?'), 'window');
});

test('rule counts carry token boxes as evidence; storeys default to one', () => {
  const tokens = dedupe([
    { text: 'MH', conf: 0.9, box: [0.1, 0.1, 0.12, 0.11] },
    { text: 'MH', conf: 0.8, box: [0.1005, 0.1, 0.1205, 0.11] },   // same label read twice
    { text: 'MH', conf: 0.9, box: [0.6, 0.6, 0.62, 0.61] },
  ]);
  const r = countByRule('bedroom', tokens);
  assert.equal(r.answer, 2);
  assert.equal(r.evidence.length, 2);
  assert.equal(countByRule('floors', tokens).answer, 1);
});

test('held-out split is deterministic and disjoint', () => {
  const paths = Array.from({ length: 50 }, (_, i) => `data/x/${i}.png`);
  const a = split(paths, { dev: 5, test: 10 }), b = split([...paths].reverse(), { dev: 5, test: 10 });
  assert.deepEqual(a, b);
  assert.equal(new Set([...a.dev, ...a.test]).size, 15);
});
