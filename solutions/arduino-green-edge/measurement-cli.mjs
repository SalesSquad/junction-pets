#!/usr/bin/env node
import { readFile, stat } from 'node:fs/promises';
import { MAX_INPUT_BYTES, parseMeterDocument, syntheticMeterDocument, reviewMeterDocument } from './measurement.mjs';

async function main() {
  const arg = process.argv[2];
  if (!arg || arg === '--help' || process.argv.length > 3) {
    console.error('Usage: node measurement-cli.mjs positive|negative|/path/to/local-meter-record.json');
    process.exitCode = 2;
    return;
  }
  let result;
  if (['positive', 'negative'].includes(arg)) result = reviewMeterDocument(syntheticMeterDocument(arg));
  else {
    const info = await stat(arg);
    if (!info.isFile() || info.size > MAX_INPUT_BYTES) throw Error('Meter input must be a local file at most 128 KiB');
    result = parseMeterDocument(await readFile(arg, 'utf8'));
  }
  console.log(JSON.stringify(result, null, 2));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
