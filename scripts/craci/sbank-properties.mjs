// Independent, synthetic-only cent arithmetic and provenance campaign.
// Expected amounts are generated and calculated with BigInt, not by the product.
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const MAX = 9007199254740991n;
const SOURCE_PATH = 'solutions/s-pankki-economic-trainer/src/coach.mjs';
const BASKETS = ['mandatory-regular', 'mandatory-irregular', 'everyday', 'unclassified'];
const digest = value => createHash('sha256').update(value).digest('hex');
const encode = value => JSON.stringify(value, (_, item) => typeof item === 'bigint' ? item.toString() : item);
const positive = value => value > 0n ? value : 0n;
const safe = value => value >= -MAX && value <= MAX;

class PropertyFailure extends Error {
  constructor(field, expected, actual) {
    super(field);
    this.field = field;
    this.expected = String(expected).slice(0, 100);
    this.actual = String(actual).slice(0, 100);
  }
}
function requireValue(condition, field) {
  if (!condition) throw new PropertyFailure(field, 'true', 'false');
}
function centsEqual(actual, expected, field) {
  if (!safe(expected)) throw new Error('Harness generated an unsafe ordinary expectation');
  if (!Number.isSafeInteger(actual) || BigInt(actual) !== expected) {
    throw new PropertyFailure(field, expected, typeof actual === 'number' ? actual : typeof actual);
  }
}
function idsEqual(actual, expected, field) {
  if (!Array.isArray(actual) || actual.length !== expected.length ||
      actual.some((value, i) => value !== expected[i])) {
    throw new PropertyFailure(field, expected.join(','), Array.isArray(actual) ? actual.join(',') : typeof actual);
  }
}
function explicitRefusal(action, pattern, field) {
  let threw = false;
  try { action(); } catch (error) {
    threw = true;
    requireValue(error instanceof Error && pattern.test(error.message), `${field}.explicit-error`);
  }
  requireValue(threw, `${field}.must-refuse`);
}
function configInteger(name, fallback, minimum, maximum) {
  const raw = process.env[name] ?? String(fallback);
  if (!/^\d+$/.test(raw)) throw new Error(`invalid-${name}`);
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) throw new Error(`invalid-${name}`);
  return value;
}

// Mulberry32: seed zero is a valid, nondegenerate stream. Never use Math.random.
function randomStream(seed) {
  let state = seed >>> 0;
  return maximum => {
    state = (state + 0x6d2b79f5) >>> 0;
    let word = Math.imul(state ^ (state >>> 15), 1 | state);
    word ^= word + Math.imul(word ^ (word >>> 7), 61 | word);
    return Math.floor(((word ^ (word >>> 14)) >>> 0) / 4294967296 * maximum);
  };
}
function shuffled(values, random) {
  const copy = [...values];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = random(i + 1);
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}
function money(cents, style = 0) {
  const absolute = cents < 0n ? -cents : cents;
  const sign = cents < 0n ? '-' : '';
  const fraction = String(absolute % 100n).padStart(2, '0');
  const integer = String(absolute / 100n);
  if (style % 5 === 1) return `${sign}${integer},${fraction}`;
  if (style % 5 === 2) return `  ${sign}${integer}.${fraction}  `;
  if (style % 5 === 3) return `${sign}000${integer}.${fraction}`;
  if (style % 5 === 4 && absolute % 10n === 0n) return `${sign}${integer}.${fraction[0]}`;
  return `${sign}${integer}.${fraction}`;
}
function timestamp(epoch, style) {
  if (style % 4 === 0) return new Date(epoch).toISOString();
  if (style % 4 === 1) return new Date(epoch).toISOString().slice(0, 19).replace('T', ' ');
  const offset = style % 4 === 2 ? 120 : -300;
  return new Date(epoch + offset * 60_000).toISOString().slice(0, 19) + (offset > 0 ? '+02:00' : '-05:00');
}

// A small declared classification fixture, including aliases and a genuinely
// unknown category; no call to the product's rules constructs expected values.
const classes = [
  ['GROCERIES', 'mandatory-regular'], ['RENT', 'mandatory-regular'],
  ['ELECTRICITY', 'mandatory-regular'], ['MORTGAGE', 'mandatory-regular'],
  ['HOUSING_REPAIR', 'mandatory-irregular'], ['HOME_REPAIRS', 'mandatory-irregular'],
  ['DENTAL', 'mandatory-irregular'], ['COFFEE', 'everyday'],
  ['TAXIS', 'everyday'], ['TRANSPORT_TAXI', 'everyday'],
  ['RESTAURANT', 'everyday'], ['SHOPPING', 'everyday'],
  ['UNREVIEWED_SYNTHETIC_CATEGORY', 'unclassified'],
  ['SALARY', 'non-spending'], ['INTERNAL_TRANSFER', 'non-spending'],
];

function makeScenario(index, seed, random) {
  const largeSafeBalance = index % 61 === 0;
  const accountCount = largeSafeBalance ? 1 : 1 + random(4);
  const expected = [];
  const raw = [];
  const customer = `synthetic-${seed}-${index}`;
  for (let account = 0; account < accountCount; account++) {
    const count = 3 + random(5);
    for (let j = 0; j < count; j++) {
      const [category, declaredBasket] = classes[(index + account + j) % classes.length];
      const mode = (index + account + j) % 6;
      const magnitude = BigInt(1 + random(300_000));
      const amount = mode === 0 ? 0n : mode === 1 || mode === 4 ? magnitude : -magnitude;
      const transactionType = mode === 1 ? 'REFUND' : mode === 2 ? 'INTERNAL_TRANSFER' : mode === 5 ? 'SIIRTO' : 'CARD_PAYMENT';
      const basket = mode === 2 || mode === 5 ? 'non-spending' : declaredBasket;
      const spent = basket === 'non-spending' ? 0n : amount < 0n ? -amount : mode === 1 ? -amount : 0n;
      const epoch = Date.UTC(2026, j === 0 ? 9 : 10, j === 0 ? 31 : 1 + j, 8 + account, j * 3, index % 60);
      const balance = largeSafeBalance ? MAX - BigInt(random(100_000)) : BigInt(random(5_000_001) - 1_000_000);
      // Later times have SMALLER CSV row IDs: row order cannot act as chronology.
      const line = 1000 + account * 100 + (count - j) * 3;
      const date = new Date(epoch).toISOString().slice(0, 10);
      const accountId = `account-${account}`;
      const row = {customer_id: customer, bank_account_id: accountId, tx_date: date,
        tx_timestamp: timestamp(epoch, index + j), category,
        tx_amount_eur: money(amount, index + j), balance_after_eur: money(balance),
        transaction_type: transactionType, sourceLine: line};
      raw.push(row);
      expected.push({accountId, line, date, epoch, balance, amount, basket, spent});
      if (j === count - 1 && index % 4 === 0) {
        // Equal last timestamp and balance is allowed, with the higher row cited.
        raw.push({...row, sourceLine: line + 1});
        expected.push({...expected.at(-1), line: line + 1});
      }
    }
  }
  const reserveValues = [BigInt(random(1_000_001)), BigInt(random(500_001)), BigInt(random(500_001))];
  const assumptions = Object.fromEntries(['regularBills', 'irregularBuffer', 'emergencyBuffer']
    .map((key, i) => [key, money(reserveValues[i], index + i)]));
  const latest = [];
  for (let account = 0; account < accountCount; account++) {
    const candidates = expected.filter(row => row.accountId === `account-${account}`);
    latest.push(candidates.reduce((a, b) => b.epoch > a.epoch ||
      (b.epoch === a.epoch && b.line > a.line) ? b : a));
  }
  const balance = latest.reduce((sum, row) => sum + row.balance, 0n);
  const reserves = reserveValues.reduce((sum, value) => sum + value, 0n);
  const daily = BigInt(random(150_001));
  const oneTime = BigInt(random(2_000_001));
  const input = shuffled(raw, random);
  const permutation = shuffled(input, random);
  const parserValues = [0n, 1n, -1n, 99n, -99n, MAX, -MAX,
    MAX - BigInt(random(100_000)), -MAX + BigInt(random(100_000)),
    BigInt(random(2_000_000_001) - 1_000_000_000)];
  const parseCents = parserValues[index % parserValues.length];
  const scenario = {id: `random-${index}`, index, raw: input, permutation, expected, latest,
    balance, reserves, reserveValues, assumptions, daily, oneTime,
    parseCents, parseText: money(parseCents, index)};
  scenario.hash = digest(encode({seed, raw: input, assumptions, daily, oneTime, parseText: scenario.parseText}));
  return scenario;
}

async function run() {
  const started = performance.now();
  const seed = configInteger('CRACI_SEED', 20261114, 0, 4294967295);
  const cases = configInteger('CRACI_CASES', 2000, 2000, 20000);
  if (!process.env.SOURCE_DIR) throw new Error('missing-SOURCE_DIR');
  const sourceDir = resolve(process.env.SOURCE_DIR);
  const sourceSha = process.env.EXPECTED_SOURCE_SHA ?? '';
  if (!/^[a-f0-9]{40}$/.test(sourceSha)) throw new Error('invalid-EXPECTED_SOURCE_SHA');
  const git = args => execFileSync('git', ['-C', sourceDir, ...args],
    {encoding: 'utf8', timeout: 15_000, maxBuffer: 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe']});
  if (git(['rev-parse', 'HEAD']).trim() !== sourceSha) throw new Error('source-HEAD-mismatch');
  const code = await readFile(resolve(sourceDir, SOURCE_PATH));
  if (digest(code) !== digest(git(['show', `${sourceSha}:${SOURCE_PATH}`]))) throw new Error('source-bytes-mismatch');
  const harnessSha256 = digest(await readFile(fileURLToPath(import.meta.url)));
  const api = await import(pathToFileURL(resolve(sourceDir, SOURCE_PATH)).href);
  for (const name of ['eurosToCents', 'readTransactions', 'spendingSummary', 'budgetCapacity', 'planSpendingWindow']) {
    if (typeof api[name] !== 'function') throw new Error('missing-required-export');
  }

  const random = randomStream(seed);
  const counts = {total: 0, passed: 0, failed: 0, byFunction: {}};
  const failures = [];
  const failedScenarios = new Set();
  const hashes = new Set();
  function check(scenario, name, property, action) {
    const group = counts.byFunction[name] ??= {total: 0, passed: 0, failed: 0};
    counts.total++; group.total++;
    try { action(); counts.passed++; group.passed++; }
    catch (error) {
      counts.failed++; group.failed++; failedScenarios.add(scenario.id);
      if (failures.length < 10) failures.push({seed, caseId: scenario.id, caseIndex: scenario.index ?? null,
        fixtureSha256: scenario.hash, function: name, property,
        reason: error instanceof PropertyFailure ? 'property-mismatch' : 'unexpected-exception',
        ...(error instanceof PropertyFailure ? {field: error.field, expected: error.expected, actual: error.actual} : {})});
    }
  }
  const parsed = scenario => api.readTransactions(structuredClone(scenario.raw));
  function assertCapacity(result, scenario) {
    const net = scenario.balance - scenario.reserves;
    centsEqual(result.balanceCents, scenario.balance, 'balanceCents');
    centsEqual(result.reserveCents, scenario.reserves, 'reserveCents');
    centsEqual(result.netAfterReservesCents, net, 'netAfterReservesCents');
    centsEqual(result.availableCents, positive(net), 'availableCents');
    centsEqual(result.shortfallCents, positive(-net), 'shortfallCents');
    requireValue(result.illustrationOnly === true, 'illustrationOnly');
    idsEqual([...result.accountBalanceSources].sort((a, b) => a - b),
      scenario.latest.map(row => row.line).sort((a, b) => a - b), 'accountBalanceSources');
  }
  const invalidMoney = ['1.001', '-0.001', '1e3', 'Infinity', 'NaN', '0x10', '1_000.00',
    '--1.00', '', '1.2.3', '90071992547409.92', '-90071992547409.92'];
  for (let index = 0; index < cases; index++) {
    const scenario = makeScenario(index, seed, random);
    hashes.add(scenario.hash);
    check(scenario, 'eurosToCents', 'exact-safe-cent-parse', () =>
      centsEqual(api.eurosToCents(scenario.parseText), scenario.parseCents, 'parsedCents'));
    check(scenario, 'eurosToCents', 'invalid-or-unsafe-money-refusal', () =>
      explicitRefusal(() => api.eurosToCents(invalidMoney[index % invalidMoney.length]),
        /invalid|safe|exceed/i, 'money'));
    check(scenario, 'readTransactions', 'independent-row-money-classification-and-order', () => {
      const rows = parsed(scenario);
      const expected = [...scenario.expected].sort((a, b) => a.date.localeCompare(b.date) || a.epoch - b.epoch || a.line - b.line);
      idsEqual(rows.map(row => row.row), expected.map(row => row.line), 'ordered-source-rows');
      rows.forEach((row, i) => {
        const original = expected[i];
        centsEqual(row.changeCents, original.amount, 'row.changeCents');
        centsEqual(row.amountCents, original.spent, 'row.amountCents');
        centsEqual(row.balanceCents, original.balance, 'row.balanceCents');
        requireValue(row.basket === original.basket, 'row.basket');
        requireValue(row.timestampMs === original.epoch, 'row.timestampMs');
      });
    });
    for (const month of ['2026-10', '2026-11']) {
      check(scenario, 'spendingSummary', `independent-basket-and-total-${month}`, () => {
        const summary = api.spendingSummary(parsed(scenario), month);
        const selected = scenario.expected.filter(row => row.date.startsWith(month) && row.spent !== 0n);
        for (const basket of BASKETS) {
          const expected = selected.filter(row => row.basket === basket).reduce((sum, row) => sum + row.spent, 0n);
          centsEqual(summary.totals[basket], expected, `totals.${basket}`);
        }
        centsEqual(summary.spentCents, selected.reduce((sum, row) => sum + row.spent, 0n), 'spentCents');
        idsEqual([...summary.sources].sort((a, b) => a - b), selected.map(row => row.line).sort((a, b) => a - b), 'spending.sources');
      });
    }
    check(scenario, 'budgetCapacity', 'latest-per-account-and-reserve-clipping', () =>
      assertCapacity(api.budgetCapacity(parsed(scenario), scenario.assumptions), scenario));
    check(scenario, 'budgetCapacity', 'input-permutation-does-not-change-balance-or-citations', () =>
      assertCapacity(api.budgetCapacity(api.readTransactions(structuredClone(scenario.permutation)), scenario.assumptions), scenario));
    check(scenario, 'budgetCapacity', 'conflicting-equal-latest-timestamp-refusal', () => {
      const latest = scenario.latest[0];
      const original = scenario.raw.find(row => row.sourceLine === latest.line);
      const conflicting = {...original, sourceLine: 99_999,
        balance_after_eur: money(latest.balance === MAX ? latest.balance - 1n : latest.balance + 1n)};
      const rows = api.readTransactions(structuredClone([...scenario.raw, conflicting]));
      explicitRefusal(() => api.budgetCapacity(rows, scenario.assumptions), /ambiguous|conflict|timestamp/i, 'latest-tie');
    });
    for (const days of [7, 14, 30]) {
      check(scenario, 'planSpendingWindow', `independent-daily-plan-${days}`, () => {
        const result = api.planSpendingWindow(parsed(scenario), scenario.assumptions,
          {days, dailyFlex: money(scenario.daily), oneTime: money(scenario.oneTime)});
        const starting = positive(scenario.balance - scenario.reserves);
        const outlay = scenario.daily * BigInt(days) + scenario.oneTime;
        const net = starting - outlay;
        const expected = {dailyFlexCents: scenario.daily, oneTimeCents: scenario.oneTime,
          plannedOutlayCents: outlay, startingRoomCents: starting, netAfterPlanCents: net,
          remainingCents: positive(net), gapCents: positive(-net),
          maxDailyFlexCents: positive(starting - scenario.oneTime) / BigInt(days),
          reserveShortfallCents: positive(scenario.reserves - scenario.balance)};
        for (const [key, cents] of Object.entries(expected)) centsEqual(result[key], cents, key);
        requireValue(result.illustrationOnly === true && result.days === days, 'plan.metadata');
        requireValue(Array.isArray(result.steps) && result.steps.length === days, 'plan.steps.length');
        result.steps.forEach((step, i) => {
          const after = starting - scenario.oneTime - scenario.daily * BigInt(i + 1);
          requireValue(step.day === i + 1, 'step.day');
          centsEqual(step.remainingCents, positive(after), 'step.remainingCents');
          centsEqual(step.gapCents, positive(-after), 'step.gapCents');
        });
        idsEqual([...result.sources].sort((a, b) => a - b),
          scenario.latest.map(row => row.line).sort((a, b) => a - b), 'plan.sources');
      });
    }
  }

  // Explicit regression inputs: each input number is safe, but their aggregate
  // result is outside the Number integer contract. The engine must refuse.
  const regressionRow = (line, category, amount, balance) => ({customer_id: 'synthetic-overflow',
    bank_account_id: 'account-0', tx_date: '2026-11-14', tx_timestamp: '2026-11-14T12:00:00Z',
    category, tx_amount_eur: money(amount), balance_after_eur: money(balance),
    transaction_type: 'CARD_PAYMENT', sourceLine: line});
  const underflow = {id: 'regression-balance-minus-reserve-overflow',
    raw: [regressionRow(2, 'GROCERIES', 0n, -MAX)],
    assumptions: {regularBills: '0.01', irregularBuffer: '0.00', emergencyBuffer: '0.00'}};
  underflow.hash = digest(encode(underflow));
  check(underflow, 'budgetCapacity', 'negative-max-safe-balance-minus-one-cent', () => {
    requireValue(!safe(-MAX - 1n), 'harness.overflows');
    const rows = parsed(underflow);
    idsEqual(rows.map(row => row.row), [2], 'budget-overflow.valid-source-rows');
    centsEqual(rows[0].balanceCents, -MAX, 'budget-overflow.valid-balance');
    centsEqual(rows[0].amountCents, 0n, 'budget-overflow.valid-spending');
    centsEqual(api.eurosToCents(underflow.assumptions.regularBills), 1n, 'budget-overflow.valid-reserve');
    explicitRefusal(() => api.budgetCapacity(rows, underflow.assumptions), /safe|overflow|exceed/i, 'budget-overflow');
  });
  const overflow = {id: 'regression-two-basket-total-overflow',
    raw: [regressionRow(2, 'GROCERIES', -MAX, 0n), regressionRow(3, 'TAXI', -1n, 0n)]};
  overflow.hash = digest(encode(overflow));
  check(overflow, 'spendingSummary', 'two-individually-safe-baskets-total-max-plus-one', () => {
    requireValue(!safe(MAX + 1n), 'harness.overflows');
    const rows = parsed(overflow);
    idsEqual(rows.map(row => row.row), [2, 3], 'spending-overflow.valid-source-rows');
    centsEqual(rows[0].amountCents, MAX, 'spending-overflow.valid-first-amount');
    centsEqual(rows[1].amountCents, 1n, 'spending-overflow.valid-second-amount');
    requireValue(rows[0].basket === 'mandatory-regular' && rows[1].basket === 'everyday', 'spending-overflow.distinct-baskets');
    explicitRefusal(() => api.spendingSummary(rows, '2026-11'), /safe|overflow|exceed/i, 'spending-overflow');
  });
  if (hashes.size !== cases) throw new Error('harness-scenario-collision');
  console.log(JSON.stringify({schemaVersion: 1, status: counts.failed ? 'failed' : 'passed',
    scope: 'synthetic-BigInt-arithmetic-and-source-provenance-properties',
    sourceSha, sourceFileSha256: digest(code), harnessSha256, seed,
    generatedScenarios: cases, distinctGeneratedScenarios: hashes.size, explicitRegressionScenarios: 2,
    checks: counts, failedScenarios: failedScenarios.size, counterexamples: failures,
    omittedCounterexamples: Math.max(0, counts.failed - failures.length),
    durationMs: Math.round(performance.now() - started),
    qualification: 'No sponsor-data truth, bank connection, advice, browser or provider claim.'}));
  if (counts.failed) process.exitCode = 1;
}

await run().catch(error => {
  console.log(JSON.stringify({schemaVersion: 1, status: 'setup-or-harness-failed',
    reason: /^(invalid-|missing-|source-|harness-)/.test(error?.message ?? '')
      ? error.message.slice(0, 100) : 'unexpected-setup-or-harness-exception'}));
  process.exitCode = 1;
});
