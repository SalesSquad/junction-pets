import test from 'node:test';
import assert from 'node:assert/strict';
import { answerDrawingV2, answerQuantities, fixtureSymbols } from '../src/quantities.mjs';

// Synthetic drawing in metres that follows the layered convention (no sponsor data).
let id = 0;
const poly = (layer, pts, closed = false) => ({ id: `e${++id}`, type: 'LWPOLYLINE', layer, closed, points: pts.map(([x, y]) => ({ x, y })) });
const rect = (layer, x, y, w, h) => poly(layer, [[x, y], [x + w, y], [x + w, y + h], [x, y + h]], true);
const circle = (layer, x, y, r) => ({ id: `e${++id}`, type: 'CIRCLE', layer, x, y, radius: r });
const arc = (layer, x, y, r) => ({ id: `e${++id}`, type: 'ARC', layer, x, y, radius: r, start: 0, end: 90 });
const text = (x, y, t) => ({ id: `e${++id}`, type: 'TEXT', layer: 'ROOM_TEXT', x, y, text: t });
const ellipse = (cx, cy, rx, ry) => poly('FIXTURE', Array.from({ length: 12 }, (_, i) => [cx + rx * Math.cos(i / 2), cy + ry * Math.sin(i / 2)]), true);

const entities = [
  // two rooms of apartment A and a balcony
  rect('ROOM_OUTLINE', 0, 0, 4, 3), text(1, 1, '2.01'), text(1, 2, 'Cage d\'escalier'), text(2, 1, '12 m²'),
  rect('ROOM_OUTLINE', 4, 0, 2, 3), text(5, 1, '2.02'), text(5, 2, 'Bain'), text(5, 0.5, '6 m²'),
  rect('ROOM_OUTLINE', 0, 3, 6, 1), text(1, 3.5, '2.03'), text(3, 3.5, 'Balkon'), text(4, 3.5, '6 m²'),
  rect('UNIT_OUTLINE', 0, 0, 6, 4), text(3, 0.5, 'Whg. A'),
  // one single door (leaf + opening line + arc) and one double door (2 leaves + opening + 2 arcs)
  poly('DOOR', [[0, 0], [0.9, 0]]), poly('DOOR', [[0, 0], [0, 0.9]]), arc('DOOR', 0, 0, 0.9),
  poly('DOOR', [[2, 0], [2.6, 0]]), poly('DOOR', [[3.2, 0], [2.6, 0]]), poly('DOOR', [[2, 0], [2, 0.6]]), arc('DOOR', 2, 0, 0.6), arc('DOOR', 3.2, 0, 0.6),
  // one window = three lines
  poly('WINDOW', [[6, 1], [6, 2]]), poly('WINDOW', [[6.05, 1], [6.05, 2]]), poly('WINDOW', [[6.1, 1], [6.1, 2]]),
  // fixtures: WC (bowl, no drain), basin (bowl + small drain), bathtub, shower
  rect('FIXTURE', 4.1, 0.1, 0.38, 0.55), ellipse(4.29, 0.35, 0.12, 0.18),
  rect('FIXTURE', 4.6, 0.1, 0.5, 0.4), ellipse(4.85, 0.3, 0.18, 0.12), circle('FIXTURE', 4.85, 0.3, 0.03),
  rect('FIXTURE', 4.1, 1.0, 0.75, 1.7), circle('FIXTURE', 4.4, 1.2, 0.03),
  rect('FIXTURE', 5.0, 1.0, 0.9, 0.9), circle('FIXTURE', 5.45, 1.45, 0.04),
];
const drawing = { filename: 'synthetic.dxf', format: 'ASCII DXF', units: 6, unitsLabel: 'meters', entities };
const ask = q => answerDrawingV2(drawing, q);

test('doors: opening lines = polylines minus swing arcs (double door counts once)', () => {
  const r = ask('How many doors (interior doors and entrance doors together) are drawn on this floor plan?');
  assert.equal(r.answer, '2');
  assert.ok(r.evidence.length > 0);
});

test('windows: three lines per window', () => assert.equal(ask('Wie viele Fenster sind auf diesem Grundriss eingezeichnet?').answer, '1'));

test('fixtures are classified by their own inner symbol', () => {
  const kinds = fixtureSymbols(entities, 1).map(s => s.kind).sort();
  assert.deepEqual(kinds, ['basin', 'bathtub', 'shower', 'wc']);
  assert.equal(ask('How many toilets (WC) are drawn on this floor plan?').answer, '1');
  assert.equal(ask('Quanti lavabi sono disegnati in questa pianta?').answer, '1');
  assert.equal(ask('Combien de baignoires sont dessinées sur ce plan ?').answer, '1');
  assert.equal(ask('How many showers are drawn on this floor plan?').answer, '1');
});

test('room area comes from the smallest enclosing closed outline', () => {
  const r = ask("Qual è la superficie netta del locale 2.02 («Bain») in m²?");
  assert.equal(r.answer, '6.00 m²');
  assert.equal(r.metric.value, 6);
});

test('label questions use the quoted name, including apostrophes and words that contain other labels', () => {
  assert.equal(ask("How many rooms labelled 'Cage d'escalier' are there on this floor?").answer, '1');
  assert.equal(ask('Combien de pièces portant la désignation « Bain » y a-t-il à cet étage ?').answer, '1');
});

test('apartment and indoor totals exclude balconies', () => {
  assert.equal(ask('How many apartments (residential units) are shown on this floor plan?').answer, '1');
  assert.equal(ask('What is the net floor area of apartment A in m², summing all its rooms except balconies, loggias, terraces and other outdoor spaces?').answer, '18 m²');
  assert.equal(ask('What is the total net floor area in m² of all numbered indoor rooms on this floor (excluding balconies, loggias, terraces and other outdoor spaces, shafts and voids)?').answer, '18 m²');
});

test('unknown units or unsupported questions do not guess', () => {
  assert.equal(answerQuantities({ ...drawing, units: 0 }, 'How many windows are drawn on this floor plan?').status, 'abstained');
  assert.equal(answerQuantities(drawing, 'Who designed this building?'), null);
});
