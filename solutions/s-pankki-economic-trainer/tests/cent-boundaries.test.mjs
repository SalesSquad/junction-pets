import test from 'node:test';
import assert from 'node:assert/strict';
import {answerQuestion, budgetCapacity, readTransactions, spendingSummary} from '../src/coach.mjs';

const MAX = 9007199254740991n;
const euros = cents => {
  const absolute = cents < 0n ? -cents : cents;
  return `${cents < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`;
};
const noReserves = {regularBills: '0.00', irregularBuffer: '0.00', emergencyBuffer: '0.00'};
const row = (line, {amount = 0n, balance = 0n, category = 'GROCERIES', type = 'CARD_PAYMENT', account = 'a'} = {}) => ({
  customer_id: 'synthetic-cent-boundary', bank_account_id: account,
  tx_date: '2026-11-14', tx_timestamp: '2026-11-14T12:00:00Z',
  tx_amount_eur: euros(amount), balance_after_eur: euros(balance),
  category, transaction_type: type, sourceLine: line,
});

test('two individually safe baskets must refuse an unsafe overall spending total', () => {
  const records = readTransactions([row(2, {amount: -MAX}), row(3, {amount: -1n, category: 'TAXI'})]);
  assert.equal(records[0].amountCents, Number(MAX));
  assert.equal(records[1].amountCents, 1);
  assert.throws(() => spendingSummary(records, '2026-11'), /unsafe/i);
});

test('one reserved cent beyond the minimum safe balance must refuse before clipping', () => {
  const records = readTransactions([row(2, {balance: -MAX})]);
  assert.equal(records[0].balanceCents, -Number(MAX));
  assert.throws(() => budgetCapacity(records, {...noReserves, regularBills: '0.01'}), /unsafe/i);
});

test('an overall spending total exactly at the maximum safe cent remains valid', () => {
  const result = spendingSummary(readTransactions([
    row(2, {amount: -(MAX - 1n)}), row(3, {amount: -1n, category: 'TAXI'}),
  ]), '2026-11');
  assert.equal(result.spentCents, Number(MAX));
  assert.equal(result.totals['mandatory-regular'], Number(MAX - 1n));
  assert.equal(result.totals.everyday, 1);
  assert.deepEqual(result.sources, [2, 3]);
});

test('minimum and maximum safe budget boundaries preserve exact values and provenance', () => {
  const negative = budgetCapacity(readTransactions([row(2, {balance: -MAX})]), noReserves);
  assert.equal(negative.netAfterReservesCents, -Number(MAX));
  assert.equal(negative.availableCents, 0);
  assert.equal(negative.shortfallCents, Number(MAX));
  assert.deepEqual(negative.accountBalanceSources, [2]);
  const positive = budgetCapacity(readTransactions([row(3, {balance: MAX})]), {...noReserves, regularBills: '0.01'});
  assert.equal(positive.netAfterReservesCents, Number(MAX - 1n));
  assert.equal(positive.availableCents, Number(MAX - 1n));
  assert.equal(positive.shortfallCents, 0);
  assert.deepEqual(positive.accountBalanceSources, [3]);
});

test('same-basket purchase and refund cancellation never loses a cent in an intermediate sum', () => {
  const records = readTransactions([
    row(2, {amount: -MAX}), row(3, {amount: -2n}), row(4, {amount: 2n, type: 'REFUND'}),
  ]);
  const result = spendingSummary(records, '2026-11');
  assert.equal(result.totals['mandatory-regular'], Number(MAX));
  assert.equal(result.spentCents, Number(MAX));
  assert.deepEqual(result.sources, [2, 3, 4]);
  const category = answerQuestion('Groceries this month?', records);
  const basket = answerQuestion('mandatory regular basket', records);
  assert.equal(category.result.spentCents, Number(MAX));
  assert.equal(basket.result.spentCents, Number(MAX));
  assert.deepEqual(category.sources, [2, 3, 4]);
  assert.deepEqual(basket.sources, [2, 3, 4]);
});

test('separate-basket cancellation retains the exact safe grand total', () => {
  const result = spendingSummary(readTransactions([
    row(2, {amount: -MAX}), row(3, {amount: -2n, category: 'HOUSING_REPAIR'}),
    row(4, {amount: 2n, category: 'COFFEE', type: 'REFUND'}),
  ]), '2026-11');
  assert.equal(result.totals['mandatory-regular'], Number(MAX));
  assert.equal(result.totals['mandatory-irregular'], 2);
  assert.equal(result.totals.everyday, -2);
  assert.equal(result.spentCents, Number(MAX));
});

test('multiple account balances sum exactly even when intermediate Number addition would round', () => {
  const result = budgetCapacity(readTransactions([
    row(2, {balance: MAX, account: 'a'}), row(3, {balance: 2n, account: 'b'}),
    row(4, {balance: -2n, account: 'c'}),
  ]), noReserves);
  assert.equal(result.balanceCents, Number(MAX));
  assert.equal(result.availableCents, Number(MAX));
  assert.deepEqual(result.accountBalanceSources, [2, 3, 4]);
});

test('unsafe individual basket, account aggregate and reserve aggregate remain refused', () => {
  const purchases = readTransactions([row(2, {amount: -MAX}), row(3, {amount: -1n})]);
  assert.throws(() => spendingSummary(purchases, '2026-11'), /unsafe/i);
  const accounts = readTransactions([row(2, {balance: MAX}), row(3, {balance: 1n, account: 'b'})]);
  assert.throws(() => budgetCapacity(accounts, noReserves), /unsafe/i);
  const ordinary = readTransactions([row(2, {balance: 100n})]);
  assert.throws(() => budgetCapacity(ordinary, {regularBills: euros(MAX), irregularBuffer: '0.01', emergencyBuffer: '0.00'}), /unsafe/i);
});
