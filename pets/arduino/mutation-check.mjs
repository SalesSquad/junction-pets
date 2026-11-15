// Offline test sensitivity only. Mutations run in disposable copies, never here.
import {createHash} from 'node:crypto';
import {mkdtemp, mkdir, readFile, writeFile, copyFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const modulePath = join(root, 'pets/arduino/compatibility.mjs');
const testPath = join(root, 'tests/pet-arduino.test.mjs');
const digest = text => createHash('sha256').update(text).digest('hex');
const timeoutMs = 15_000;

// Exact source substitutions prevent a silently missed or widened mutation.
const faults = [
  {id: 'duplicate-pin', needle: 'if (allocated.has(p.pin))',
    test: 'duplicate pin regression reports conflict and aggregates its declared demand'},
  {id: 'supply-voltage', needle: 'if (s[supplyKey] !== b[supplyKey])',
    test: 'supply voltage regression reports the exact field and declared mismatch'},
  {id: 'logic-voltage', needle: 'if (split && s.logicVoltageMv !== b.logicVoltageMv)',
    test: 'logic voltage regression cannot be masked by matching supply voltage'},
  {id: 'per-pin-current', needle: 'if (b.pinLimitMa !== null && p.currentMa > b.pinLimitMa)',
    test: 'per-pin current regression reports demand and limit for that pin'},
  {id: 'total-current', needle: 'if (b.powerLimitMa !== null && supplyMa + signalMa > b.powerLimitMa)',
    test: 'total current regression counts signal demand in the supply budget'},
  {id: 'aggregate-signal-current', needle: 'if (b.totalPinLimitMa !== null && signalMa > b.totalPinLimitMa)',
    test: 'aggregate signal current regression retains its independent budget'},
];

function run(args) {
  const result = spawnSync(process.execPath, args, {encoding: 'utf8', timeout: timeoutMs, maxBuffer: 2 * 1024 * 1024});
  if (result.error || result.signal) throw Error(`Child did not finish normally: ${result.error?.code ?? result.signal}`);
  return {exitCode: result.status, output: result.stdout + result.stderr};
}

const source = await readFile(modulePath, 'utf8');
const tests = await readFile(testPath, 'utf8');
const scratch = await mkdtemp(join(tmpdir(), 'junction-arduino-mutations-'));
const summaries = [];
try {
  await mkdir(join(scratch, 'tests'));
  await mkdir(join(scratch, 'pets/arduino'), {recursive: true});
  await mkdir(join(scratch, 'mutants'));
  await copyFile(join(root, 'pets/arduino/example.json'), join(scratch, 'pets/arduino/example.json'));
  await copyFile(join(root, 'pets/arduino/example-v2.json'), join(scratch, 'pets/arduino/example-v2.json'));
  const importNeedle = "from '../pets/arduino/compatibility.mjs'";
  if (tests.split(importNeedle).length !== 2) throw Error('Expected one checker import in company tests');
  const copiedTest = join(scratch, 'tests/pet-arduino.test.mjs');
  const copiedModule = join(scratch, 'mutants/checker.mjs');
  await writeFile(copiedTest, tests.replace(importNeedle, "from '../mutants/checker.mjs'"));
  await writeFile(copiedModule, source);
  const baseline = run(['--test', '--test-reporter=tap', copiedTest]);
  process.stdout.write(`BASELINE\n${baseline.output}`);
  if (baseline.exitCode !== 0 || !/# fail 0\b/.test(baseline.output)) throw Error('Baseline company suite must pass before mutation testing');
  for (const fault of faults) {
    if (source.split(fault.needle).length !== 2) throw Error(`Mutation ${fault.id} expected one exact guard`);
    const mutated = source.replace(fault.needle, 'if (false)');
    await writeFile(copiedModule, mutated);
    const syntax = run(['--check', copiedModule]);
    if (syntax.exitCode !== 0) throw Error(`Mutation ${fault.id} is not valid JavaScript`);
    const escapedName = fault.test.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const result = run(['--test', '--test-reporter=tap', `--test-name-pattern=^${escapedName}$`, copiedTest]);
    process.stdout.write(`MUTANT ${fault.id}\n${result.output}`);
    // A loader/parse crash, timeout or unexpected test failure is not a kill.
    const namedFailure = new RegExp(`not ok \\d+ - ${escapedName}(?:\\r?\\n|$)`);
    const killed = result.exitCode === 1 && namedFailure.test(result.output)
      && /code: 'ERR_ASSERTION'/.test(result.output) && /# fail 1\b/.test(result.output)
      && !/ERR_MODULE_NOT_FOUND|SyntaxError|ERR_TEST_FAILURE/.test(result.output);
    summaries.push({id: fault.id, test: fault.test, moduleSha256: digest(mutated), exitCode: result.exitCode, killed});
    if (!killed) throw Error(`Mutation ${fault.id} survived or failed for a non-assertion reason`);
  }
  process.stdout.write(JSON.stringify({sourceSha256: digest(source), testsSha256: digest(tests), node: process.version,
    timeoutMs, attempted: summaries.length, killed: summaries.filter(x => x.killed).length, mutations: summaries}, null, 2) + '\n');
} finally {
  await rm(scratch, {recursive: true, force: true});
}
