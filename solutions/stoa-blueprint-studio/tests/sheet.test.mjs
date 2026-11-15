import test from 'node:test';
import assert from 'node:assert/strict';
import { toLines } from '../sheet/sheet-qa.mjs';

const w = (text, x0, y0, x1, y1) => ({ text, box: [x0, y0, x1, y1] });

test('schedule rows become one line with cells joined by " | "; distant tables stay separate', () => {
  const words = [
    w('107.A', 0.10, 0.20, 0.13, 0.21), w('LAUNDRY', 0.15, 0.20, 0.19, 0.21), w('ROOM', 0.192, 0.20, 0.21, 0.21), w('A1', 0.24, 0.20, 0.25, 0.21),
    w('128', 0.60, 0.20, 0.62, 0.21),                       // another table far to the right
    w('121.A', 0.10, 0.23, 0.13, 0.24), w('CLINIC', 0.15, 0.23, 0.19, 0.24), w('B3', 0.24, 0.23, 0.25, 0.24),
  ];
  const lines = toLines(words).map(l => l.text);
  assert.deepEqual(lines, ['107.A | LAUNDRY ROOM | A1', '128', '121.A | CLINIC | B3']);
});
