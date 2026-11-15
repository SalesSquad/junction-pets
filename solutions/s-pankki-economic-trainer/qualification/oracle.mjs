// Independent source oracle. No imports from the product's parser or arithmetic.
import {createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {stat} from 'node:fs/promises';

export const OFFICIAL = Object.freeze({
  sha256: '49b3265d8e44e751de305a074dcffcda732bb79aa1e07b46fcca774ce76f1e63',
  bytes: 362796501, rows: 3626755,
});
export const FIELDS = Object.freeze(['customer_id', 'bank_account_id', 'tx_date', 'tx_timestamp', 'category',
  'tx_amount_eur', 'balance_after_eur', 'transaction_type', 'merchant_id', 'mcc_code']);
const MAX = 9007199254740991n;
export class QualificationError extends Error {
  constructor(code) { super(code); this.code = code; }
}
export function requireFact(ok, code) { if (!ok) throw new QualificationError(code); }
export function digest(value) { return createHash('sha256').update(JSON.stringify(value)).digest('hex'); }
export function safe(cents) {
  requireFact(typeof cents === 'bigint' && cents >= -MAX && cents <= MAX, 'UNSAFE_CENTS');
  return cents;
}
export function money(value) {
  requireFact(typeof value === 'string' && /^-?\d+(?:\.\d{1,2})?$/.test(value) && value.length <= 32, 'MALFORMED_MONEY');
  const negative = value[0] === '-';
  const [whole, part = ''] = (negative ? value.slice(1) : value).split('.');
  const cents = BigInt(whole) * 100n + BigInt(part.padEnd(2, '0'));
  return safe(negative ? -cents : cents);
}
export function dayParts(value) {
  requireFact(typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value), 'MALFORMED_DATE');
  const [y, m, d] = value.split('-').map(Number);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  requireFact(y >= 1900 && m >= 1 && m <= 12 && d >= 1 && d <= days[m - 1], 'MALFORMED_DATE');
  return [y, m, d];
}
const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
export function clock(value, day) {
  const [year, month, date] = dayParts(day);
  const m = /^(\d{2})([A-Z]{3})(\d{2}):(\d{2}):(\d{2}):(\d{2})$/.exec(value);
  requireFact(m && +m[1] === date && MONTHS.indexOf(m[2]) + 1 === month && +m[3] === year % 100 &&
    +m[4] < 24 && +m[5] < 60 && +m[6] < 60, 'MALFORMED_TIMESTAMP');
  return `${day}T${m[4]}:${m[5]}:${m[6]}Z`;
}

// Strict, line-oriented RFC-style CSV subset. Multiline fields are unsupported
// by the existing importer and refused, never skipped. A closing quote must be
// followed by a separator/end, unlike a permissive toggling-quote parser.
export function csvLine(line) {
  requireFact(line.length > 0 && line.length <= 8192 && !/[\r\n\u0000]/.test(line), 'INVALID_CSV_LINE');
  const result = [];
  let field = '', state = 'start';
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (state === 'quoted') {
      if (c !== '"') field += c;
      else if (line[i + 1] === '"') { field += '"'; i++; }
      else state = 'closed';
    } else if (c === ',') { result.push(field); field = ''; state = 'start'; }
    else if (state === 'closed') throw new QualificationError('INVALID_CSV_QUOTE');
    else if (c === '"') { requireFact(state === 'start', 'INVALID_CSV_QUOTE'); state = 'quoted'; }
    else { field += c; state = 'plain'; }
  }
  requireFact(state !== 'quoted', 'PARTIAL_CSV');
  result.push(field);
  return result;
}
export function validateRaw(row) {
  requireFact(FIELDS.every(k => typeof row[k] === 'string'), 'MISSING_FIELD');
  requireFact(row.customer_id.trim().length > 0 && row.bank_account_id.trim().length > 0, 'MISSING_ID');
  requireFact(row.category.length > 0 && row.category.length <= 80 && row.transaction_type.length > 0 &&
    row.transaction_type.length <= 60, 'INVALID_CLASSIFICATION_FIELD');
  requireFact(Number.isSafeInteger(row.sourceLine) && row.sourceLine >= 2, 'INVALID_SOURCE_LINE');
  money(row.tx_amount_eur); money(row.balance_after_eur); clock(row.tx_timestamp, row.tx_date);
}
const normal = s => s.normalize('NFKC').trim().toUpperCase().replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_|_$/g, '');
// Declared assumptions, not sponsor-labelled ground truth. Broad Health,
// Transportation, Lifestyle, Home & Tech and Travel deliberately stay unknown.
export const MAPPING = Object.freeze({
  regular: ['RENT','MORTGAGE','HOUSING','UTILITIES','ELECTRICITY','INSURANCE','GROCERIES'],
  irregular: ['HOUSING_REPAIR','HOME_REPAIRS','HEALTHCARE','DENTAL'],
  everyday: ['COFFEE','RESTAURANTS','RESTAURANT','TAXI','TAXIS','TRANSPORT_TAXI','ENTERTAINMENT','SHOPPING'],
  movements: ['SALARY','INCOME','INTERNAL_TRANSFER','TRANSFER','INVEST_DEPOSIT','INVEST_WITHDRAW','SALARY_SWEEP','OTHER_INCOME'],
});
const GROUPS = {
  Housing: ['RENT','MORTGAGE','HOUSING'], Groceries: ['GROCERIES'], Utilities: ['UTILITIES','ELECTRICITY'],
};
export function sourceFact(raw) {
  validateRaw(raw);
  const change = money(raw.tx_amount_eur), balance = money(raw.balance_after_eur);
  const category = normal(raw.category), type = normal(raw.transaction_type);
  const movement = MAPPING.movements.includes(category) || ['INVESTMENT_DEPOSIT','INVESTMENT_WITHDRAWAL','SALARY_SWEEP'].includes(type) ||
    /TRANSFER|SIIRTO/.test(type) || category.includes('TRANSFER');
  const bucket = movement ? 'non-spending' : MAPPING.regular.includes(category) ? 'mandatory-regular' :
    MAPPING.irregular.includes(category) ? 'mandatory-irregular' : MAPPING.everyday.includes(category) ? 'everyday' : 'unclassified';
  let spending = 0n;
  if (!movement) {
    if (change < 0n) spending = -change;
    else if (/REFUND|REVERSAL|PALAUTUS/.test(type)) spending = -change;
  }
  return {raw, line: raw.sourceLine, time: clock(raw.tx_timestamp, raw.tx_date), day: raw.tx_date,
    category, bucket, group: Object.keys(GROUPS).find(k => GROUPS[k].includes(category)) ?? 'other',
    change, balance, spending: safe(spending), movement};
}
export function cohort(rawRows) {
  requireFact(rawRows.length > 0 && rawRows.length <= 10000, 'COHORT_SIZE');
  requireFact(new Set(rawRows.map(r => r.customer_id)).size === 1, 'MULTIPLE_CUSTOMERS');
  requireFact(new Set(rawRows.map(r => r.sourceLine)).size === rawRows.length, 'DUPLICATE_SOURCE_LINE');
  requireFact(new Set(rawRows.map(r => digest(FIELDS.map(k => r[k])))).size === rawRows.length, 'DUPLICATE_TRANSACTION');
  return rawRows.map(sourceFact).sort((a,b) => a.time.localeCompare(b.time) || a.line - b.line);
}
export function sum(values) { return safe(values.reduce((a,b) => a + b, 0n)); }
export function latestAccounts(facts) {
  const accounts = new Map();
  for (const f of facts) {
    const key = f.raw.bank_account_id, previous = accounts.get(key);
    if (!previous || previous.time < f.time) accounts.set(key, f);
    else if (previous.time === f.time) {
      requireFact(previous.balance === f.balance, 'AMBIGUOUS_LATEST_BALANCE');
      if (f.line > previous.line) accounts.set(key, f);
    }
  }
  const latest = [...accounts.values()];
  sum(latest.map(f => f.balance));
  return latest;
}
export function references(lines) {
  requireFact(Array.isArray(lines) && lines.every(x => Number.isSafeInteger(x) && x >= 2) &&
    new Set(lines).size === lines.length, 'INVALID_CITATIONS');
  return {count: lines.length, sha256: digest([...lines].sort((a,b) => a-b))};
}
export function assertCitations(actual, expected, facts) {
  const available = new Set(facts.map(f => f.line));
  requireFact(Array.isArray(actual) && actual.every(x => available.has(x)), 'FOREIGN_CITATION');
  requireFact(JSON.stringify(references(actual)) === JSON.stringify(references(expected)), 'CITATION_MISMATCH');
}
export function fileIdentity(s) { return [s.dev, s.ino, s.size, s.mtimeMs, s.ctimeMs].join(':'); }

// One whole-file validation/hash pass, retaining only the second DISTINCT
// customer in file order. First-customer rows are counted, never retained.
export async function scanSource(path, expected = OFFICIAL) {
  const before = await stat(path);
  requireFact(before.isFile() && before.size === expected.bytes, 'SOURCE_SIZE_MISMATCH');
  const hash = createHash('sha256'), decoder = new TextDecoder('utf-8', {fatal:true});
  let bytes = 0, pending = '', line = 0, header = false, baseline = '', selected = '', baselineRows = 0, selectedRows = [];
  function consume(text) {
    line++;
    if (text.endsWith('\r')) text = text.slice(0,-1);
    if (!header) {
      const fields = csvLine(text.replace(/^\uFEFF/, ''));
      requireFact(JSON.stringify(fields) === JSON.stringify(FIELDS), 'CSV_HEADER_MISMATCH');
      header = true; return;
    }
    const fields = csvLine(text);
    requireFact(fields.length === FIELDS.length, 'CSV_COLUMN_MISMATCH');
    const row = Object.fromEntries(FIELDS.map((key, i) => [key, fields[i]]));
    row.sourceLine = line;
    validateRaw(row);
    if (!baseline) baseline = row.customer_id;
    if (row.customer_id === baseline) baselineRows++;
    else if (!selected) selected = row.customer_id;
    if (row.customer_id === selected) {
      selectedRows.push(row);
      requireFact(selectedRows.length <= 10000, 'COHORT_SIZE');
    }
  }
  try {
    for await (const chunk of createReadStream(path, {highWaterMark:65536})) {
      bytes += chunk.length; requireFact(bytes <= expected.bytes, 'SOURCE_SIZE_MISMATCH'); hash.update(chunk);
      const text = pending + decoder.decode(chunk, {stream:true});
      let from = 0, end;
      while ((end = text.indexOf('\n', from)) !== -1) { consume(text.slice(from,end)); from = end+1; }
      pending = text.slice(from);
      requireFact(pending.length <= 8192, 'CSV_LINE_TOO_LONG');
    }
    pending += decoder.decode();
  } catch (error) {
    if (error instanceof QualificationError) throw error;
    throw new QualificationError('SOURCE_READ_OR_ENCODING_ERROR');
  }
  requireFact(pending.length === 0 && header && line > 1, 'PARTIAL_CSV');
  const sha256 = hash.digest('hex');
  requireFact(bytes === expected.bytes && line - 1 === expected.rows, 'SOURCE_COUNT_MISMATCH');
  requireFact(sha256 === expected.sha256, 'SOURCE_SHA_MISMATCH');
  requireFact(fileIdentity(before) === fileIdentity(await stat(path)), 'SOURCE_CHANGED');
  requireFact(selected && selected !== baseline && baselineRows > 0 && selectedRows.length > 0, 'NO_DISJOINT_COHORT');
  const facts = cohort(selectedRows);
  latestAccounts(facts); // refuse balance ambiguity before producing answers
  return {selectedId: selected, rawRows: selectedRows, facts, identity: fileIdentity(before),
    provenance: {sha256, bytes, transactions:line-1, selectedRows:selectedRows.length, baselineRows,
      selection:'second distinct customer in source-file order; first customer excluded', disjointFromFirst:true,
      cohortSha256:digest(selectedRows.map(r => FIELDS.map(k => r[k]))),
      rowReferences:references(selectedRows.map(r=>r.sourceLine))}};
}
