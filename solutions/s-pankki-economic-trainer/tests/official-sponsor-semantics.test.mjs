import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTransactionTimestamp, readTransactions, spendingSummary, budgetCapacity, answerQuestion} from '../src/coach.mjs';

const row = (line, day, stamp, category, type, amount, balance) => ({
  customer_id: 'SYNTHETIC_EXAMPLE', bank_account_id: 'ACCOUNT_DEMO',
  tx_date: day, tx_timestamp: stamp, category,
  tx_amount_eur: amount, balance_after_eur: balance, transaction_type: type,
  merchant_id: '', mcc_code: '', sourceLine: line,
});

test('official DDMONYY timestamps bind to the full tx_date and survive year/month rollover', () => {
  assert.equal(parseTransactionTimestamp('30OCT25:20:49:35', '2025-10-30'), Date.UTC(2025,9,30,20,49,35));
  assert.equal(parseTransactionTimestamp('01JAN26:00:00:01', '2026-01-01'), Date.UTC(2026,0,1,0,0,1));
  assert.equal(parseTransactionTimestamp('2025-10-30 20:49:35'), Date.UTC(2025,9,30,20,49,35));
  for (const [stamp, day] of [
    ['30OCT25:20:49:35', '2024-10-30'],
    ['29NOV25:20:49:35', '2025-10-30'],
    ['31FEB26:01:02:03', '2026-02-28'],
    ['30OCT25:24:00:00', '2025-10-30'],
    ['30OCT25:20:49:35', null],
    ['30FOO25:20:49:35', '2025-10-30'],
  ]) assert.throws(() => parseTransactionTimestamp(stamp, day), /Sponsor timestamp|tx_date/);
});

const records = readTransactions([
  row(2,'2025-10-30','30OCT25:10:00:00','Salary','salary','1000.00','1000.00'),
  row(3,'2025-10-30','30OCT25:11:00:00','Housing','housing_payment','-300.00','700.00'),
  row(4,'2025-10-30','30OCT25:12:00:00','Invest Deposit','investment_deposit','-250.00','450.00'),
  row(5,'2025-10-30','30OCT25:13:00:00','Salary Sweep','salary_sweep','-50.00','400.00'),
  row(6,'2025-10-30','30OCT25:14:00:00','Groceries','purchase','-20.00','380.00'),
  row(7,'2025-10-30','30OCT25:15:00:00','Transportation','purchase','-12.00','368.00'),
  row(8,'2025-10-30','30OCT25:16:00:00','Invest Withdraw','investment_withdrawal','50.00','418.00'),
]);

test('sponsor source savings deposit and salary sweep never leak into spending baskets', () => {
  const spent = spendingSummary(records);
  assert.equal(spent.spentCents, 33200);
  assert.equal(spent.totals['mandatory-regular'], 32000); // Housing and groceries are essentials
  assert.equal(spent.totals['mandatory-irregular'], 0);
  assert.equal(spent.totals.everyday, 0);
  assert.equal(spent.totals.unclassified, 1200); // generic transportation not guessed to taxi
  assert.deepEqual(spent.sources,[3,6,7]);
  assert.deepEqual(records.filter(x => x.basket === 'non-spending').map(x=>x.row),[2,4,5,8]);
  assert.equal(records.find(x=>x.row===4).changeCents, -25000); // NOT removed from balance history
});

test('latest balance and explicit reserves include savings movements without claiming bank availability', () => {
  const room = budgetCapacity(records,{regularBills:'100.00',irregularBuffer:'0',emergencyBuffer:'0'});
  assert.equal(room.balanceCents,41800);
  assert.equal(room.availableCents,31800);
  assert.equal(room.illustrationOnly,true);
  assert.deepEqual(room.accountBalanceSources,[8]);
  const a = answerQuestion('Where did my money go?',records);
  assert.equal(a.result.spentCents,33200);
  assert.deepEqual(a.sources,[3,6,7]);
});

test('unrecognized lookalike investment transaction types are not silently excluded', () => {
  const testRows = readTransactions([
    row(2,'2025-10-30','30OCT25:10:00:00','Unmapped Category','investment_deposit_extra','-10.00','990.00'),
  ]);
  assert.equal(spendingSummary(testRows).totals.unclassified,1000);
});
