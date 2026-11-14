#!/usr/bin/env node
import { preview, reviewPreview } from './provider.mjs';
import { fakeHost, request, CASES } from './replay.mjs';
const [scenario = 'lead', ...flags] = process.argv.slice(2);
if (!CASES.includes(scenario) || flags.some(f => f !== '--human-reviewed') || flags.length > 1) {
  console.error('Usage: node provider/cli.mjs <' + CASES.join('|') + '> [--human-reviewed]');
  process.exitCode = 2;
} else {
  const result = await preview({ ...request(), host: fakeHost(scenario), limits: { timeoutMs: 50 } });
  console.log(JSON.stringify(flags.includes('--human-reviewed') ? reviewPreview(result, { approved: true, evidenceDigest: result.evidenceDigest }) : result, null, 2));
}
