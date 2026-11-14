#!/usr/bin/env node
/**
 * CRACI Immune: source-pinned, synthetic counterfactual supply-chain tournament.
 * Never executes untrusted packages, installs a malicious dependency, or changes
 * the source checkout. CRACI's real SBOM/network evidence is separate.
 */
import {strict as assert} from 'node:assert';
import {createHash} from 'node:crypto';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {performance} from 'node:perf_hooks';

const SCENARIOS = [
  'clean', 'signed-update', 'registry-drift', 'integrity-drift',
  'unexpected-script', 'egress', 'transitive-drift', 'unreachable-decoy',
];
const MODES = ['baseline', 'transitive', 'shifted'];
const sha = value => createHash('sha256').update(value).digest('hex');
const rng = initial => {
  let x = (initial >>> 0) || 0x9e3779b9;
  return () => {
    x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
    return (x >>> 0) / 0x100000000;
  };
};
const pick = (next, list) => list[Math.floor(next() * list.length)];

function parseArgs(argv) {
  const config = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--seed', '--cases', '--epoch', '--lockfile', '--output'].includes(argv[i]) || !argv[i + 1])
      throw new Error('Unexpected or incomplete argument');
    config[argv[i].slice(2)] = argv[i + 1];
  }
  for (const key of ['seed', 'cases', 'epoch']) {
    if (!/^\d{1,9}$/.test(config[key] || '')) throw new Error(`Invalid ${key}`);
    config[key] = Number(config[key]);
  }
  if (config.seed < 1 || config.seed > 999999999 || config.cases < 32 || config.cases > 1000000 ||
      config.epoch < 1 || config.epoch > 12 || !config.lockfile || !config.output)
    throw new Error('Invalid bounded tournament configuration');
  return config;
}

function makeWorld(next, names, scenario, mode) {
  const n = 9 + Math.floor(next() * 7);
  const nodes = [{name: 'app', locked: true, optional: false, metadata: {}}];
  const edges = [];
  for (let i = 1; i <= n; i++) {
    const name = `${names[(i - 1) % names.length]}#${i}`;
    nodes.push({
      name, locked: true, optional: next() < 0.42,
      metadata: {registry: 'registry.npmjs.org', integrity: `sha512-pin-${i}`,
        scripts: false, egress: []},
    });
    const parent = mode === 'baseline' && i <= 3 ? 0 : i <= 3 ? 0 : Math.floor(next() * i);
    edges.push([parent, i]);
  }
  // An unused/disconnected package is not by itself a compromised built artifact.
  nodes.push({name: 'unused-package', locked: false, optional: true,
    metadata: {registry: 'registry.npmjs.org', integrity: 'sha512-unused', scripts: false, egress: []}});
  const index = scenario === 'unreachable-decoy' ? nodes.length - 1 :
    mode === 'baseline' ? 1 + Math.floor(next() * 3) :
    mode === 'transitive' ? 4 + Math.floor(next() * (n - 3)) :
    1 + Math.floor(next() * n);
  const target = nodes[index];
  if (scenario === 'registry-drift' || scenario === 'transitive-drift' || scenario === 'unreachable-decoy')
    target.metadata.registry = 'packages.test.example'; // synthetic string, never contacted
  if (scenario === 'integrity-drift') target.metadata.integrity = 'sha512-unpinned';
  if (scenario === 'unexpected-script') target.metadata.scripts = true;
  if (scenario === 'egress') target.metadata.egress = ['https://example.com/immune-probe'];
  // The signed-update scenario has a newly reviewed *pin*; it is not a drift.
  if (scenario === 'signed-update') target.metadata.integrity = `sha512-pin-${index}`;
  const changed = !['clean', 'signed-update'].includes(scenario);
  const allowRollback = changed && next() < (mode === 'shifted' ? 0.52 : 0.83);
  target.locked = allowRollback;
  return {nodes, edges, scenario, mode};
}

function reachable(world) {
  const reached = new Set([0]), queue = [0];
  for (let cursor = 0; cursor < queue.length; cursor++) {
    const source = queue[cursor];
    for (const [from, to] of world.edges) if (from === source && !reached.has(to)) {
      reached.add(to); queue.push(to);
    }
  }
  return reached;
}

function anomalous(node) {
  if (!node.metadata.registry) return false;
  const expected = /^.+#(\d+)$/.exec(node.name)?.[1];
  if (node.metadata.registry !== 'registry.npmjs.org' ||
      (expected && node.metadata.integrity !== `sha512-pin-${expected}`) ||
      node.metadata.scripts || node.metadata.egress.length) return true;
  return false;
}

function threats(world) {
  const live = reachable(world);
  return [...live].filter(i => i !== 0 && anomalous(world.nodes[i]));
}

function apply(world, actions) {
  const nodes = world.nodes.map(node => ({...node, metadata: {...node.metadata, egress: [...(node.metadata.egress || [])]}}));
  const edges = world.edges.map(edge => [...edge]);
  for (const action of actions) {
    if (action.kind === 'rollback') {
      const node = nodes[action.node], suffix = /^.+#(\d+)$/.exec(node.name)?.[1];
      node.metadata = {registry: 'registry.npmjs.org', integrity: `sha512-pin-${suffix}`,
        scripts: false, egress: []};
    } else if (action.kind === 'deny-egress') {
      nodes[action.node].metadata.egress = [];
    } else if (action.kind === 'quarantine-edge') {
      const at = edges.findIndex(([a,b]) => a === action.from && b === action.node);
      if (at !== -1) edges.splice(at,1);
    } else throw new Error('Unknown action');
  }
  return {...world, nodes, edges};
}

function candidates(world, bad) {
  const possible = [];
  for (const i of bad) {
    const node = world.nodes[i];
    if (node.locked) possible.push({kind:'rollback', node:i, cost:1});
    if (node.metadata.egress.length && node.metadata.registry === 'registry.npmjs.org' &&
        !node.metadata.scripts && /^sha512-pin-\d+$/.test(node.metadata.integrity))
      possible.push({kind:'deny-egress', node:i, cost:1});
    if (node.optional) {
      for (const [from,to] of world.edges) if (to === i)
        possible.push({kind:'quarantine-edge', from, node:i, cost:3});
    }
  }
  return possible;
}

// Exact bounded search: smallest defensible patch that leaves no tainted path.
// If only unsafe removal of a required dependency could work, abstain.
function minimalRepair(world, bad) {
  if (!bad.length) return {actions:[], cost:0, abstain:false};
  const actions = candidates(world, bad);
  if (actions.length > 14) throw new Error('Candidate cap exceeded');
  let best = null;
  for (let mask = 1; mask < (1 << actions.length); mask++) {
    const selected = actions.filter((_,i) => Boolean(mask & (1 << i)));
    const cost = selected.reduce((sum,action) => sum + action.cost, 0);
    if (best && cost >= best.cost) continue;
    if (!threats(apply(world,selected)).length) best = {actions:selected,cost,abstain:false};
  }
  return best || {actions:[],cost:null,abstain:true};
}

export async function tournament(config) {
  const started = performance.now(), lockBytes = await readFile(resolve(config.lockfile));
  const lock = JSON.parse(lockBytes.toString('utf8'));
  const names = Object.keys(lock.packages || {}).filter(name => name.startsWith('node_modules/'))
    .map(name => name.slice('node_modules/'.length)).slice(0,256);
  if (names.length < 7) throw new Error('Expected real locked project dependencies');
  const next = rng(config.seed), mode = MODES[Math.min(2,Math.floor((config.epoch - 1) / 4))];
  const results = Object.fromEntries(SCENARIOS.map(name=>[name,{count:0,threats:0,naiveAlerts:0,
    graphAlerts:0, falsePositives:0, falseNegatives:0,autoRepairs:0,abstentions:0,repairCost:0}]));
  let uniqueWorlds = createHash('sha256');
  for (let i=0; i < config.cases; i++) {
    // Deliberately make controlled negatives ~25% of the corpus.
    const scenario=SCENARIOS[i%SCENARIOS.length];
    const world=makeWorld(next,names,scenario,mode), bad=threats(world);
    // Independent oracle: the injected mutation is reachable in the fixture,
    // except for the intentionally disconnected negative control.
    const truth=!['clean','signed-update','unreachable-decoy'].includes(scenario);
    const alert=bad.length>0;
    const naive=world.nodes.some(anomalous); // ignores provenance reachability
    const stats=results[scenario];
    stats.count++; stats.threats+=Number(truth); stats.naiveAlerts+=Number(naive);
    stats.graphAlerts+=Number(alert); stats.falsePositives+=Number(alert && !truth);
    stats.falseNegatives+=Number(!alert && truth);
    if (truth) {
      const patch=minimalRepair(world,bad);
      if (patch.abstain) stats.abstentions++;
      else {assert.equal(threats(apply(world,patch.actions)).length,0);
        stats.autoRepairs++;stats.repairCost+=patch.cost;}
    }
    uniqueWorlds.update(`${config.epoch}:${config.seed}:${i}:${scenario}:${world.nodes.length}:${JSON.stringify(world.edges)}\n`);
  }
  const overall=Object.values(results).reduce((total,v)=>{
    for (const key of Object.keys(total)) total[key]+=(v[key]||0);return total;
  },{count:0,threats:0,naiveAlerts:0,graphAlerts:0,falsePositives:0,falseNegatives:0,autoRepairs:0,abstentions:0,repairCost:0});
  assert.equal(overall.count,config.cases);
  assert(overall.threats > 0 && overall.threats < overall.count);
  assert.equal(overall.falseNegatives,0,'Synthetic oracle uncovered a missed reachable deviation');
  assert.equal(overall.falsePositives,0,'Synthetic negative control was flagged');
  assert.equal(overall.autoRepairs+overall.abstentions,overall.threats);
  return {schemaVersion:1,workId:'CRACI-IMMUNE-20261114',actualCostEur:null,
    claim:'Synthetic provenance graph/counterfactual repair benchmark; not real attack blocking',
    sourceCommit:process.env.CRACI_SOURCE_SHA||null,executor:process.env.GITHUB_RUNNER_NAME||null,
    epoch:config.epoch,seed:config.seed,mode,cases:config.cases,
    sourceLockfileSha256:sha(lockBytes),realLockfilePackages:names.length,
    corpusDigestSha256:uniqueWorlds.digest('hex'),metrics:{...overall,
      naiveFalsePositives: overall.naiveAlerts - overall.threats,
      missUpper95IfZero: overall.threats ? Number((3/overall.threats).toFixed(7)) : null},
    byScenario:results,
    durationMs:Math.round(performance.now()-started),
    limits:['Synthetic mutations are never installed or fetched',
      'Real CRACI SBOM/egress observations must be inspected independently',
      'A compromised original signed pin cannot be detected by this synthetic oracle',
      'Unsafe/unprovable changes abstain rather than patching source automatically']};
}

async function main() {
  const config=parseArgs(process.argv.slice(2)), report=await tournament(config);
  const destination=resolve(config.output);
  await mkdir(dirname(destination),{recursive:true});
  await writeFile(destination,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({epoch:report.epoch,seed:report.seed,cases:report.cases,
    metrics:report.metrics,corpusDigestSha256:report.corpusDigestSha256,
    sourceLockfileSha256:report.sourceLockfileSha256,durationMs:report.durationMs}));
}
if (process.argv[1] && import.meta.url === new URL('file://'+resolve(process.argv[1])).href)
  main().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
