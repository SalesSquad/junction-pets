#!/usr/bin/env node
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {loadPackages} from '../lib/catalog.mjs';
import {buildCaseManifest, verifyCaseManifest, assessSubmissions} from '../lib/behavior-eval.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const defaultManifest = resolve(root, 'dist/evals/cases.json');

function parseArgs(args) {
  const options = new Map();
  for (let i = 0; i < args.length; i++) {
    const current = args[i];
    if (!current.startsWith('--') || !['source-commit', 'expected-source', 'manifest', 'submissions'].includes(current.slice(2))) throw new Error(`Unknown option: ${current}`);
    if (options.has(current.slice(2))) throw new Error(`Duplicate option: ${current}`);
    const value = args[++i];
    if (!value || value.startsWith('--')) throw new Error(`Missing value for ${current}`);
    options.set(current.slice(2), value);
  }
  return options;
}

async function readSubmissions(path) {
  const data = await readFile(path, 'utf8');
  if (path.endsWith('.jsonl')) {
    const lines = data.split(/\r?\n/).filter(line => line.trim());
    return lines.map((line, i) => {
      try {return JSON.parse(line);} catch {throw new Error(`Invalid JSONL at line ${i + 1}`);}
    });
  }
  const value = JSON.parse(data);
  if (Array.isArray(value)) return value;
  if (Array.isArray(value.submissions)) return value.submissions;
  throw new Error('JSON submissions must be an array or contain submissions[]');
}

async function main() {
  const [action, ...rest] = process.argv.slice(2);
  if (!['prepare', 'check'].includes(action)) throw new Error('Usage: node scripts/behavior-eval.mjs prepare [--source-commit FULL_SHA] | check --manifest FILE --submissions FILE [--expected-source FULL_SHA]');
  const options = parseArgs(rest);
  const packs = await loadPackages(root);
  if (action === 'prepare') {
    if ([...options.keys()].some(key => key !== 'source-commit')) throw new Error('prepare accepts only --source-commit');
    const manifest = buildCaseManifest(packs, {sourceCommit: options.get('source-commit') || null});
    await mkdir(dirname(defaultManifest), {recursive: true});
    await writeFile(defaultManifest, JSON.stringify(manifest, null, 2) + '\n', {flag: 'w'});
    console.log(JSON.stringify({action, path: 'dist/evals/cases.json', authoredCases: manifest.authoredCases, modelExecutionsVerified: 0, sourceCommit: manifest.source.commit, manifestSha256: manifest.manifestSha256, evidenceLevel: manifest.evidenceLevel}));
    return;
  }
  if (options.has('source-commit') || !options.has('submissions')) throw new Error('check requires --submissions and optionally --manifest/--expected-source');
  const path = options.get('manifest') ? resolve(options.get('manifest')) : defaultManifest;
  const manifest = JSON.parse(await readFile(path, 'utf8'));
  verifyCaseManifest(manifest, packs, {expectedSourceCommit: options.get('expected-source') || null});
  const submissions = await readSubmissions(resolve(options.get('submissions')));
  const result = assessSubmissions(manifest, submissions);
  console.log(JSON.stringify({action, authoredCases: result.authoredCases, submittedResponses: result.submittedResponses, reviewCandidates: result.reviewCandidates, reviewFailures: result.reviewFailures, modelExecutionsVerified: 0, qualifiedPasses: 0, evidenceLevel: result.evidenceLevel, sourceCommit: result.sourceCommit}));
  if (result.reviewFailures) process.exitCode = 1;
}

main().catch(error => {console.error(JSON.stringify({error: error instanceof Error ? error.message : String(error)})); process.exitCode = 1;});
