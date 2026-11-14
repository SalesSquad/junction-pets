#!/usr/bin/env node
import {readFile, stat} from 'node:fs/promises';
import {resolve} from 'node:path';
import {compareAndRecord, planNext, recordFailure, recordPolicy, recordRun, reviewCase, summarize} from './registry.mjs';

function options(args) {
  const result = {};
  while (args.length) {
    const name = args.shift();
    if (!/^--[a-z-]+$/.test(name) || !args.length || args[0].startsWith('--') || result[name]) throw new Error(`invalid or duplicate option: ${name}`);
    result[name] = args.shift();
  }
  return result;
}

async function inputJson(path) {
  if (!path) throw new Error('missing JSON input');
  const details = await stat(path);
  if (!details.isFile() || details.size > 1024 * 1024) throw new Error('expected regular JSON file <= 1 MiB');
  return JSON.parse(await readFile(path, 'utf8'));
}

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  if (!command || ['help', '--help'].includes(command)) {
  process.stdout.write(`Usage: node services/experiment-registry/cli.mjs COMMAND [OPTIONS]\n\nCommands:\n  record-policy  --input frozen-policy.json [--root ops/experiments]\n  record-run     --input run.json [--baseline RUN_ID --policy frozen-policy.json] [--root ops/experiments]\n  record-failure --input failure.json [--root ops/experiments]\n  review-case    --input review.json [--root ops/experiments]\n  plan-next      --input plan.json [--root ops/experiments]\n  compare        --baseline RUN_ID --candidate RUN_ID --policy policy.json [--root ops/experiments]\n  summary        [--root ops/experiments]\n\nModel admission: 0 = eligible for independent review only (NOT deployment), 2 = rejected/incomparable/uncompared.\n`);
    return;
  }
  const opts = options(rest);
  const allowed = command === 'compare' ? ['--root', '--baseline', '--candidate', '--policy'] : command === 'record-run' ? ['--root', '--input', '--baseline', '--policy'] : command === 'summary' ? ['--root'] : ['--root', '--input'];
  if (Object.keys(opts).some(key => !allowed.includes(key))) throw new Error('unsupported option for command');
  const root = resolve(opts['--root'] || 'ops/experiments');
  let result;
  switch (command) {
    case 'record-policy': result = await recordPolicy(root, await inputJson(opts['--input'])); break;
    case 'record-run': {
      if (Boolean(opts['--baseline']) !== Boolean(opts['--policy'])) throw new Error('baseline and frozen policy must be provided together');
      const run = await inputJson(opts['--input']);
      result = {saved: await recordRun(root, run)};
      if (opts['--baseline']) {
        result.comparison = await compareAndRecord(root, opts['--baseline'], run.runId, await inputJson(opts['--policy']));
        if (result.comparison.decision.status !== 'candidate-eligible-for-review') process.exitCode = 2;
      } else if (run.kind === 'model-evaluation') {
        // Retain bootstrap/baseline evidence, but fail closed: ingestion alone
        // never signals that an unevaluated checkpoint has passed the gate.
        result.admission = {status: 'not-compared', reason: 'baseline-and-frozen-policy-required', eligibleForReview: false, releaseAuthorized: false};
        process.exitCode = 2;
      }
      break;
    }
    case 'record-failure': result = await recordFailure(root, await inputJson(opts['--input'])); break;
    case 'review-case': result = await reviewCase(root, await inputJson(opts['--input'])); break;
    case 'plan-next': result = await planNext(root, await inputJson(opts['--input'])); break;
    case 'compare': {
      if (!opts['--baseline'] || !opts['--candidate']) throw new Error('baseline and candidate required');
      result = await compareAndRecord(root, opts['--baseline'], opts['--candidate'], await inputJson(opts['--policy']));
      if (result.decision.status !== 'candidate-eligible-for-review') process.exitCode = 2;
      break;
    }
    case 'summary': result = await summarize(root); break;
    default: throw new Error('unknown command');
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch(error => {
  process.stderr.write(`experiment-registry: ${error.message}\n`);
  process.exitCode = 1;
});
