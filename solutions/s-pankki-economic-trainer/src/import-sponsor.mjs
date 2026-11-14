// Stream the event sponsor's large synthetic CSV without loading all customers.
// Usage: node src/import-sponsor.mjs source.csv CUSTOMER_ID ./data/sample.json
import {createReadStream} from 'node:fs';
import {open, mkdir} from 'node:fs/promises';
import {createInterface} from 'node:readline';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const columns = ['customer_id', 'bank_account_id', 'tx_date', 'tx_timestamp', 'category', 'tx_amount_eur', 'balance_after_eur', 'transaction_type', 'merchant_id', 'mcc_code'];

export function parseCsvLine(line) {
  const fields = [];
  let field = '', quoted = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {field += '"'; i++;}
      else if (quoted) quoted = false;
      else if (!field) quoted = true;
      else throw new Error('Malformed CSV quoting');
    } else if (char === ',' && !quoted) {fields.push(field); field = '';}
    else field += char;
  }
  if (quoted) throw new Error('CSV embedded newlines are unsupported');
  fields.push(field);
  return fields;
}

export async function selectCustomer(inputPath, customerId, maxRows = 10000) {
  if (typeof customerId !== 'string' || !customerId.trim()) throw new Error('Select one synthetic customer ID');
  const rows = [];
  let header, first = true, lineNumber = 0;
  const lines = createInterface({input: createReadStream(inputPath, {encoding: 'utf8'}), crlfDelay: Infinity});
  for await (const raw of lines) {
    lineNumber++;
    if (first) {
      const trimmed = raw.replace(/^\uFEFF/, '');
      if (trimmed.startsWith('version https://git-lfs.github.com/spec/v1')) throw new Error('Git LFS pointer: download the real sponsor CSV');
      header = parseCsvLine(trimmed);
      for (const name of columns) if (!header.includes(name)) throw new Error(`Sponsor CSV missing required field ${name}`);
      first = false;
      continue;
    }
    if (!raw.trim()) continue;
    const cells = parseCsvLine(raw);
    if (cells.length !== header.length) throw new Error(`Column mismatch at source row ${lineNumber}`);
    const match = Object.fromEntries(header.map((name, index) => [name, cells[index]]));
    if (match.customer_id !== customerId) continue;
    rows.push(Object.fromEntries([...columns.map(key => [key, match[key]]), ['sourceLine', lineNumber]]));
    if (rows.length > maxRows) throw new Error(`More than ${maxRows} transactions for one customer; use a smaller sample/export`);
  }
  if (!rows.length) throw new Error('No rows for that customer; no export written');
  return rows;
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  const [input, customerId, output] = process.argv.slice(2);
  if (!input || !customerId || !output) {
    process.stderr.write('Usage: node src/import-sponsor.mjs SOURCE.csv CUSTOMER_ID ./data/export.json\n');
    process.exitCode = 2;
  } else {
    try {
      const rows = await selectCustomer(input, customerId);
      await mkdir(dirname(resolve(output)), {recursive: true});
      const file = await open(output, 'wx', 0o600); // never overwrite an earlier export
      try { await file.writeFile(`${JSON.stringify(rows, null, 2)}\n`); }
      finally { await file.close(); }
      process.stdout.write(`Exported ${rows.length} synthetic rows to specified local file. Do not commit exported data.\n`);
    } catch (error) {
      process.stderr.write(`Import refused: ${error.message}\n`);
      process.exitCode = 1;
    }
  }
}
