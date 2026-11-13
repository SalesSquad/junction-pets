#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {runBatch} from './runner.mjs';

function fail(message) {
  throw new Error(message);
}

async function main() {
  const [action, ...args] = process.argv.slice(2);
  if (action !== 'preview') fail('Usage: node services/eval-runner/cli.mjs preview --manifest FILE --source-commit FULL_SHA [--limit 24]');
  const options = new Map();
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i], value = args[i + 1];
    if (!['--manifest', '--source-commit', '--limit'].includes(key) || !value || options.has(key)) fail('Invalid CLI options');
    options.set(key, value);
  }
  if (!options.has('--manifest') || !options.has('--source-commit')) fail('Missing required manifest or source commit');
  const manifest = JSON.parse(await readFile(resolve(options.get('--manifest')), 'utf8'));
  const maxCases = options.has('--limit') ? Number(options.get('--limit')) : 24;
  const result = await runBatch({manifest, sourceCommit: options.get('--source-commit'), maxCases});
  process.stdout.write(JSON.stringify(result) + '\n');
}

main().catch(error => {
  process.stderr.write(JSON.stringify({error: error instanceof Error ? error.message : String(error)}) + '\n');
  process.exitCode = 1;
});
