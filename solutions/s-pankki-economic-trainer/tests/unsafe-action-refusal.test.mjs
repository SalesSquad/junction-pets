import test from 'node:test';
import assert from 'node:assert/strict';
import {readTransactions, answerQuestion} from '../src/coach.mjs';
import {syntheticRows} from '../src/demo-data.mjs';

const rows = readTransactions(syntheticRows);
const forbidden = [
  'Pay my electricity bill now',
  'Transfer money to another account now',
  'Guarantee that it is safe to spend my live balance',
  "Show another customer's groceries",
  'Buy shares using my savings',
  'Connect to my bank account now',
  'Can you send me 500 euro from my account?',
  'Please wire 400 euros to another account',
  'What is my current overdraft limit?',
  'Maksa sähkölaskuni nyt',
  'Siirrä rahaa toiselle tilille',
];
for (const q of forbidden) {
  test(`unsupported action or third-party request refuses without sources: ${q}`, () => {
    const a = answerQuestion(q, rows);
    assert.equal(a.type, 'refusal');
    assert.deepEqual(a.sources, []);
    assert.equal(a.result, undefined);
    assert.doesNotMatch(a.message, /\b[0-9]+(?:[.,][0-9]{2})?\s*€/);
  });
}

for (const [q, expected] of [
  ['How much did I pay for groceries last month?', 'category'],
  ['How much did I pay for electricity this month?', 'category'],
  ['What can I safely spend this week?', 'budget'],
  ['Where did my money go this month?', 'summary'],
]) {
  test(`ordinary historical read-only question is preserved: ${q}`, () => {
    assert.equal(answerQuestion(q, rows).type, expected);
  });
}
