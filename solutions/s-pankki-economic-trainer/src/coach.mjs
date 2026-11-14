// Event-created, deterministic finance explainer for the S-Pankki challenge.
// The application never connects to a bank, initiates a payment or calls a model.

const requiredColumns = [
  'customer_id', 'bank_account_id', 'tx_date', 'tx_timestamp', 'category',
  'tx_amount_eur', 'balance_after_eur', 'transaction_type',
];

const categoryRules = new Map(Object.entries({
  RENT: ['mandatory-regular', 'Housing'],
  MORTGAGE: ['mandatory-regular', 'Housing'],
  UTILITIES: ['mandatory-regular', 'Utilities'],
  ELECTRICITY: ['mandatory-regular', 'Utilities'],
  INSURANCE: ['mandatory-regular', 'Insurance'],
  GROCERIES: ['mandatory-regular', 'Groceries'],
  HOUSING_REPAIR: ['mandatory-irregular', 'Repairs'],
  HOME_REPAIRS: ['mandatory-irregular', 'Repairs'],
  HEALTHCARE: ['mandatory-irregular', 'Healthcare'],
  DENTAL: ['mandatory-irregular', 'Healthcare'],
  COFFEE: ['everyday', 'Coffee'],
  RESTAURANTS: ['everyday', 'Dining'],
  RESTAURANT: ['everyday', 'Dining'],
  TAXI: ['everyday', 'Taxis'],
  TAXIS: ['everyday', 'Taxis'],
  TRANSPORT_TAXI: ['everyday', 'Taxis'],
  ENTERTAINMENT: ['everyday', 'Entertainment'],
  SHOPPING: ['everyday', 'Shopping'],
  SALARY: ['non-spending', 'Income'],
  INCOME: ['non-spending', 'Income'],
  INTERNAL_TRANSFER: ['non-spending', 'Transfers'],
  TRANSFER: ['non-spending', 'Transfers'],
}));

export const BASKETS = [
  {id: 'mandatory-regular', label: 'Must pay · regular', short: 'Essentials'},
  {id: 'mandatory-irregular', label: 'Must pay · irregular', short: 'Unexpected'},
  {id: 'everyday', label: 'Everyday choices', short: 'Flex spending'},
  {id: 'unclassified', label: 'Needs classification', short: 'Unclassified'},
];

const normalise = (value) => String(value ?? '').trim().normalize('NFKC')
  .toUpperCase().replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '');

// Reject floating-point arithmetic: all sums and balances use integer cents.
export function eurosToCents(value) {
  const raw = String(value ?? '').trim().replace(',', '.');
  if (!/^-?\d+(?:\.\d{1,2})?$/.test(raw)) throw new Error(`Invalid money amount: ${raw.slice(0, 28)}`);
  const negative = raw.startsWith('-');
  const [euros, fraction = ''] = raw.replace(/^-/, '').split('.');
  const cents = Number(euros) * 100 + Number(fraction.padEnd(2, '0'));
  if (!Number.isSafeInteger(cents)) throw new Error('Amount exceeds safe integer cents');
  return negative ? -cents : cents;
}

export function centsToEuros(cents, locale = 'en-FI') {
  if (!Number.isSafeInteger(cents)) throw new Error('Unsafe cent amount');
  return new Intl.NumberFormat(locale, {style: 'currency', currency: 'EUR'}).format(cents / 100);
}

function validDay(day) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return false;
  const parsed = new Date(`${day}T12:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === day;
}

export function parseTransactionTimestamp(value) {
  const raw = String(value ?? '').trim();
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/i.exec(raw);
  if (!match || !validDay(match[1]) || Number(match[2]) > 23 || Number(match[3]) > 59 || Number(match[4]) > 59) {
    throw new Error('Invalid transaction timestamp: expected YYYY-MM-DD HH:MM:SS with optional timezone');
  }
  const iso = raw.replace(' ', 'T');
  // Sponsor timestamps without timezone are interpreted as UTC for deterministic
  // chronology; never infer a missing bank timezone or local device timezone.
  const withZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(iso) ? iso : `${iso}Z`;
  const epoch = Date.parse(withZone);
  if (!Number.isFinite(epoch)) throw new Error('Invalid transaction timestamp offset');
  return epoch;
}

export function readTransactions(rows) {
  if (!Array.isArray(rows) || rows.length === 0) throw new Error('Provide at least one synthetic transaction');
  const parsed = rows.map((row, index) => {
    for (const key of requiredColumns) if (row?.[key] === undefined || row[key] === null) throw new Error(`Missing ${key} at row ${index + 1}`);
    if (!validDay(String(row.tx_date))) throw new Error(`Invalid transaction date at row ${index + 1}`);
    const customerId = String(row.customer_id);
    const accountId = String(row.bank_account_id);
    if (!customerId || !accountId) throw new Error('Missing customer or account ID');
    const timestampMs = parseTransactionTimestamp(row.tx_timestamp);
    const cents = eurosToCents(row.tx_amount_eur);
    const balanceCents = eurosToCents(row.balance_after_eur);
    const classification = categoryRules.get(normalise(row.category)) ?? ['unclassified', String(row.category).slice(0, 42)];
    const transfer = /TRANSFER|SIIRTO/i.test(String(row.transaction_type)) || normalise(row.category).includes('TRANSFER');
    const refund = /REFUND|REVERSAL|PALAUTUS/i.test(String(row.transaction_type));
    const basket = transfer ? 'non-spending' : classification[0];
    const amountCents = basket === 'non-spending' ? 0 : cents < 0 ? -cents : refund ? -cents : 0;
    return {
      row: Number(row.sourceLine) || index + 2, // CSV line number; row 1 is the header.
      customerId, accountId, date: String(row.tx_date), timestampMs,
      category: String(row.category).slice(0, 80), basket,
      group: classification[1], amountCents, changeCents: cents,
      balanceCents, transactionType: String(row.transaction_type).slice(0, 60),
      // Merchant names and user-controlled memo text are NEVER interpreted as instructions.
    };
  });
  const customerIds = new Set(parsed.map(x => x.customerId));
  if (customerIds.size !== 1) throw new Error('Multiple customers: select one synthetic customer before loading');
  if (new Set(parsed.map(x => x.row)).size !== parsed.length) throw new Error('Duplicate source CSV row: provenance would be ambiguous');
  return parsed.sort((a, b) => a.date.localeCompare(b.date) || a.timestampMs - b.timestampMs || a.row - b.row);
}

// Keep the evidence explorer bounded while guaranteeing every displayed citation
// has an actual rendered target, even if the row is older than the latest page.
export function selectEvidenceRows(rows, citedRows = [], recentLimit = 150, citationLimit = 30) {
  const recent = rows.slice(-recentLimit).reverse();
  const visible = new Set(recent.map(x => x.row));
  for (const rowId of citedRows.slice(0, citationLimit)) {
    if (visible.has(rowId)) continue;
    const original = rows.find(x => x.row === rowId);
    if (original) { recent.push(original); visible.add(rowId); }
  }
  return recent;
}

export function latestDate(rows) {
  return rows.at(-1)?.date ?? null;
}

export function currentMonth(rows) {
  return latestDate(rows)?.slice(0, 7) ?? null;
}

export function monthBefore(month) {
  const d = new Date(`${month}-01T00:00:00Z`);
  if (Number.isNaN(d.valueOf())) throw new Error('Invalid month');
  d.setUTCMonth(d.getUTCMonth() - 1);
  return d.toISOString().slice(0, 7);
}

export function spendingSummary(rows, month = currentMonth(rows)) {
  if (!/^\d{4}-\d{2}$/.test(month ?? '')) throw new Error('Missing data month');
  const subset = rows.filter(x => x.date.startsWith(month) && x.amountCents !== 0);
  const totals = Object.fromEntries(BASKETS.map(b => [b.id, 0]));
  for (const row of subset) totals[row.basket] += row.amountCents;
  for (const [key, cents] of Object.entries(totals)) if (!Number.isSafeInteger(cents)) throw new Error(`Unsafe total ${key}`);
  const spentCents = Object.values(totals).reduce((s, n) => s + n, 0);
  return {month, totals, spentCents, sources: subset.map(x => x.row), rows: subset};
}

function latestBalanceByAccount(rows) {
  const byAccount = new Map();
  for (const row of rows) {
    const group = byAccount.get(row.accountId) ?? [];
    group.push(row);
    byAccount.set(row.accountId, group);
  }
  const latest = [];
  for (const [accountId, group] of byAccount) {
    const lastTimestampMs = group.reduce((latestMs, x) => Math.max(latestMs, x.timestampMs), -Infinity);
    const candidates = group.filter(x => x.timestampMs === lastTimestampMs);
    if (new Set(candidates.map(x => x.balanceCents)).size > 1) {
      throw new Error(`Ambiguous latest balance for account ${accountId}: same timestamp, different balances`);
    }
    // Identical timestamps AND identical balances: use the greatest CSV row
    // only as a deterministic citation, not as an assertion of later time.
    const chosen = candidates.reduce((a, b) => b.row > a.row ? b : a);
    latest.push({balanceCents: chosen.balanceCents, date: chosen.date, timestampMs: chosen.timestampMs, row: chosen.row});
  }
  return latest;
}

export function budgetCapacity(rows, assumptions = {}) {
  const {regularBills = '350.00', irregularBuffer = '150.00', emergencyBuffer = '120.00'} = assumptions;
  const reserves = [regularBills, irregularBuffer, emergencyBuffer].map(v => eurosToCents(v));
  if (reserves.some(x => x < 0)) throw new Error('Reserves cannot be negative');
  const accountBalances = latestBalanceByAccount(rows);
  const balanceCents = accountBalances.reduce((sum, x) => sum + x.balanceCents, 0);
  const reserveCents = reserves.reduce((sum, x) => sum + x, 0);
  if (!Number.isSafeInteger(balanceCents) || !Number.isSafeInteger(reserveCents)) throw new Error('Unsafe total');
  return {
    illustrationOnly: true, balanceCents, reserveCents,
    netAfterReservesCents: balanceCents - reserveCents,
    availableCents: Math.max(0, balanceCents - reserveCents),
    shortfallCents: Math.max(0, reserveCents - balanceCents),
    accountBalanceSources: accountBalances.map(x => x.row),
    asOf: latestDate(rows), reserves: {regularBills: reserves[0], irregularBuffer: reserves[1], emergencyBuffer: reserves[2]},
    caveat: 'Illustrative only. The CSV snapshot does not include pending card holds, future income, upcoming bills or real-time balances; not a spending guarantee.',
  };
}

function formatMonth(month) { return new Date(`${month}-01T00:00:00Z`).toLocaleDateString('en-GB', {month: 'long', year: 'numeric', timeZone: 'UTC'}); }

export function answerQuestion(question, rows, assumptions = {}) {
  const q = String(question ?? '').trim().toLocaleLowerCase();
  if (!q) return {type: 'refusal', title: 'Choose a question', message: 'Ask about your spending, three baskets or an illustrative spending buffer.', sources: []};
  if (/safe|voinko|turvallis|spend this week|paljonko voin|rah[aä]a.*viik/.test(q)) {
    const result = budgetCapacity(rows, assumptions);
    return {type: 'budget', title: 'Your illustrative spending room', message: `${centsToEuros(result.availableCents)} after explicit reserves. This is not a bank-confirmed available balance.`, sources: result.accountBalanceSources, result};
  }
  const baseMonth = currentMonth(rows);
  const month = /last month|viime ku|edellis/.test(q) ? monthBefore(baseMonth) : baseMonth;
  const summary = spendingSummary(rows, month);
  const focus = /taxi|taks/.test(q) ? 'Taxis' : /coffee|kahvi/.test(q) ? 'Coffee' : /restaurant|ravintol|dining/.test(q) ? 'Dining' : /grocer|ruokakaup|ruokamen|päivittäistavar/.test(q) ? 'Groceries' : null;
  if (focus) {
    const relevant = summary.rows.filter(x => x.group === focus);
    const value = relevant.reduce((sum, x) => sum + x.amountCents, 0);
    return {type: 'category', title: `${focus} · ${formatMonth(month)}`, message: `${centsToEuros(value)} net spending, using ${relevant.length} matching source rows.`, sources: relevant.map(x => x.row), result: {month, focus, spentCents: value}};
  }
  if (/spend|spent|money|käyt|kulut|menot|kolme|basket|three|where|mihin|summary|yhteenveto|kuukaus/.test(q)) {
    return {type: 'summary', title: `Your spending · ${formatMonth(month)}`, message: `${centsToEuros(summary.spentCents)} net spending; ${centsToEuros(summary.totals.unclassified)} is not yet classified.`, sources: summary.sources, result: summary};
  }
  return {type: 'refusal', title: 'I need a more specific question', message: 'I can explain spending by month, taxis, coffee, groceries, the three baskets, or a reserve-based illustrative budget. I cannot initiate bank actions or invent transactions.', sources: []};
}
