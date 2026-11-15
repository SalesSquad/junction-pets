#!/usr/bin/env node
// Run from the repository root. Reads only; no refresh, dispatch or network calls.
import {readDevelopmentProgress} from '../ops/development-progress.mjs';

try {
  const args = process.argv.slice(2);
  let pet = null, check = false;
  for (let index = 0; index < args.length; index++) {
    if (args[index] === '--pet' && pet === null && args[index + 1] && !args[index + 1].startsWith('--')) pet = args[++index];
    else if (args[index] === '--check' && !check) check = true;
    else throw new Error('Usage: node scripts/ops-development-progress.mjs [--pet <company>] [--check]');
  }
  const {records, ...summary} = readDevelopmentProgress(process.cwd(), {pet});
  console.log(JSON.stringify(pet === null ? summary : {...summary, record: records[0]}, null, 2));
  if (check && records.some(record => record.sourceCheck.state !== 'source-matched')) process.exitCode = 1;
} catch (error) {
  console.error('DEVELOPMENT PROGRESS UNVERIFIED: ' + error.message);
  process.exitCode = 1;
}
