#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import { verifySubmission, SubmissionGateError } from './gate.mjs';

function usage() {
  return 'Usage: node services/submission-gate/cli.mjs --tree <proposed-export-dir> --repo <clean-pinned-git-checkout> --allowlist <reviewed-exact-files.json>';
}

async function main(argv) {
  if (argv.includes('--help') || argv.includes('-h')) {
    process.stdout.write(usage() + '\n');
    return;
  }
  const options = {};
  if (argv.length !== 6) throw new SubmissionGateError('ARGUMENTS', usage());
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!['--tree', '--repo', '--allowlist'].includes(key) ||
        options[key] || !argv[i + 1] || argv[i + 1].startsWith('--')) {
      throw new SubmissionGateError('ARGUMENTS', usage());
    }
    options[key] = argv[i + 1];
  }
  if (!options['--tree'] || !options['--repo'] || !options['--allowlist']) {
    throw new SubmissionGateError('ARGUMENTS', usage());
  }
  const input = JSON.parse(await readFile(options['--allowlist'], 'utf8'));
  const result = await verifySubmission({
    treeDir: options['--tree'],
    sourceRepo: options['--repo'],
    allowlist: input
  });
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}

main(process.argv.slice(2)).catch((error) => {
  const code = error instanceof SubmissionGateError ? error.code : 'GATE_FAILURE';
  process.stderr.write(JSON.stringify({ result: 'blocked', code, message: error.message }) + '\n');
  process.exitCode = 1;
});
