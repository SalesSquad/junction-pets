/** Resolve one explicit CRACI workload before allocating its matrix. */
import {appendFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export const WINDOW_END = '2026-11-15T17:00:00Z';
const SHA = /^[0-9a-f]{40}$/;
const ENGINES = ['chromium', 'firefox', 'webkit'];
const PRODUCT_PINS = Object.freeze({
  sbank: 'b2bb7f532fd496287aace73da98296306080df6c',
  hostinger: '23a029a48794ba275a0309584bf9968f7f5b665c',
  espoo: 'ccd67d64f9a94952b0cd0f0ae1a6e2c8e8901a0a',
  exa: '2ce520f55a97f2491d34fb4582de728e7f379c1b',
  cala: 'ff6b0bacb1d796a098dba6798d61f59dc977420c',
  context: '76f0405ac49f2017129ec11d891c2a2cbe7d1838',
});
const BASELINES = Object.freeze({
  'native-probe': 'd0be3abf66c86d6817f82ca5ae5598ae003b5360',
  'mariadb-runtime': 'd0be3abf66c86d6817f82ca5ae5598ae003b5360',
  'cache-proof': '98d5a524d61e431ca36acd62b268ede343fc7fe2',
  'meta-seeds': '634f1e0e6cb2de46bcf0a783532d46c23f513d11',
  'council-postgres': '672da2be99edff2fa25c0ab2703e6da88061a62f',
  'sbank-properties': PRODUCT_PINS.sbank,
});
const SPONSOR_PINS = Object.freeze({
  base: '32258fdbee4bcd653c79f51b4376b5103c6f4d27',
  '2283': '9df83c38409c8bfad0517aebffe48211eda4a5b4',
  '2234': '9007cee1163c4a274fd60c3cc20c21ae63622786',
  '2129': '083afd994c1c9a994cb2cd5aa0b6ad805a621457',
  '2297': 'a0aa5ab2de7f5a669d97e37184a89034c1de82b6',
});
const FRONTIER_PINS = Object.freeze({
  'rokoko-heldout': '0390b87a54ad5cbc98fd5d781f828be0cfa8fbe8',
  'arduino-proof-48': 'eb7ff4cb7fa6c867ced7d944385b4e0bd08d04c4',
  'valio-settlement-browser': 'd45f450a38ec6c8fb2f73b96d181454458ae3928',
  'valio-http-race': 'd45f450a38ec6c8fb2f73b96d181454458ae3928',
  'valio-funding-race': 'd45f450a38ec6c8fb2f73b96d181454458ae3928',
  'bahn-offline-sweep': 'a4396d5ead2acc3d3db5e9a456af7f48058bb358',
  'rokoko-rl-cpu': '59479b42b177c1829a2e6678adfff1fb68aef09c',
  'rokoko-rl-full': '59479b42b177c1829a2e6678adfff1fb68aef09c',
  'aalto-consent-browser': '1a02a0bb650598571b63554312c7b5e82b323c7f',
  'astra-equity-browser': 'ebff750c176838123311affed06082e8144001f5',
  'rokoko-rl-seed-sweep': '59479b42b177c1829a2e6678adfff1fb68aef09c',
  'rokoko-rl-ablations': '59479b42b177c1829a2e6678adfff1fb68aef09c',
});
export const WORKLOADS = Object.freeze([
  'portable', 'product-browser', 'sbank-sponsor', 'portfolio-browser',
  'sbank-properties', 'tieto-sponsor', 'council-postgres', 'meta-seeds',
  'new-products-browser', 'native-probe', 'cache-proof', 'mariadb-runtime', 'meta-browser',
  'rokoko-heldout', 'arduino-proof-48', 'valio-settlement-browser', 'bahn-offline-sweep', 'rokoko-rl-cpu', 'rokoko-rl-full', 'aalto-consent-browser', 'astra-equity-browser', 'rokoko-rl-seed-sweep', 'rokoko-rl-ablations', 'valio-http-race', 'valio-funding-race', 'immune-tournament', 'chaos-lab', 'rokoko-r-tournament', 'meta-r-tournament', 'meta-r-robust', 'lens-real-bop-train', 'lens-r8-meta', 'lens-r3-methods', 'lens-hb-vision',
]);

function choose(value, choices, label) {
  if (!choices.includes(value)) throw new Error(`Unsupported ${label}: ${value}`);
  return value;
}
function commit(value, label) {
  if (!SHA.test(value)) throw new Error(`${label} requires a full lowercase 40-character commit SHA`);
  return value;
}

export function resolvePlan(input, {harnessSha, now = new Date(), creditOpen, repository = 'SalesSquad/junction-pets'} = {}) {
  if (creditOpen !== 'true') throw new Error('CRACI credit window is closed');
  commit(harnessSha, 'harnessSha');
  if (repository !== 'SalesSquad/junction-pets') throw new Error('This credit exception is Junction-only');
  const when = new Date(now);
  if (!Number.isFinite(when.getTime()) || when.getTime() >= Date.parse(WINDOW_END)) throw new Error('CRACI credit deadline reached');
  const workload = choose(input.workload || 'portable', WORKLOADS, 'workload');
  const override = input.source_sha || '';
  if (override) commit(override, 'source_sha');
  const browser = choose(input.browser || 'all', ['all', ...ENGINES], 'browser');
  const shard = choose(input.shard || 'all', ['all', '0', '1', '2', '3'], 'shard');
  const toolchain = choose(input.tieto_toolchain || 'pinned', ['pinned', 'compatible'], 'Tieto toolchain');
  const revision = choose(input.sponsor_revision || 'base', ['base', '2283', '2234', '2129', '2297', 'heads', 'all'], 'sponsor revision');
  const epoch = String(input.epoch || '1');
  if (!/^(?:[1-9]|1[0-2])$/.test(epoch)) throw new Error('Immune epoch must be 1 through 12');
  const product = input.product || 'stoa';
  choose(product, ['stoa', 'valio', ...Object.keys(PRODUCT_PINS), 'all'], 'product');
  const include = [];
  const add = (cell, sha, extra = {}) => include.push({cell, source_sha: commit(sha, 'resolved source'), source_repository: repository, ...extra});
  const selectedEngines = browser === 'all' ? ENGINES : [browser];

  if (['portfolio-browser', 'new-products-browser', 'product-browser'].includes(workload)) {
    const supported = workload === 'portfolio-browser' ? ['sbank', 'hostinger', 'espoo', 'exa']
      : workload === 'new-products-browser' ? ['cala', 'context'] : ['stoa', 'valio'];
    choose(product, workload === 'product-browser' ? supported : [...supported, 'all'], `${workload} product`);
    if (override && product === 'all') throw new Error('source_sha requires one explicit product; all products have independent sources');
    if (workload === 'product-browser' && !override) throw new Error('product-browser requires source_sha');
    for (const p of product === 'all' ? supported : [product]) {
      for (const engine of selectedEngines) add(`${p}-${engine}`, override || PRODUCT_PINS[p], {product: p, browser: engine});
    }
  } else if (workload === 'tieto-sponsor') {
    if (override) throw new Error('Tieto uses sponsor_revision pins; source_sha is unsupported for this workload');
    const revisions = revision === 'all' ? ['base', '2283', '2234', '2129', '2297'] : revision === 'heads' ? ['2283', '2234', '2129', '2297'] : [revision];
    for (const rev of revisions) add(`tieto-${rev}-${toolchain}`, SPONSOR_PINS[rev], {revision: rev, source_repository: 'te-industry-tech-office/junction26-messagepack-csharp'});
  } else if (workload === 'immune-tournament') {
    if (override && override !== harnessSha) throw new Error('Immune source must match pinned harness SHA');
    for (let index = 0; index < 4; index++) {
      add(`immune-${epoch}-${index}`, harnessSha, {epoch: Number(epoch), seed: Number(epoch) * 1009 + index * 17});
    }
  } else if (workload === 'chaos-lab') {
    if (override && override !== harnessSha) throw new Error('Chaos source must match pinned harness SHA');
    for (const [index, profile] of ['provenance', 'network', 'control', 'evidence'].entries()) {
      add(`chaos-${epoch}-${profile}`, harnessSha, {epoch: Number(epoch), profile,
        seed: Number(epoch) * 10007 + index * 73});
    }
  } else if (workload === 'rokoko-r-tournament') {
    const simulator = '59479b42b177c1829a2e6678adfff1fb68aef09c';
    if (override && override !== simulator) throw new Error('R tournament requires pinned simulator SHA');
    for (let cohort = 0; cohort < 4; cohort++) {
      add(`rokoko-r-${cohort}`, simulator, {cohort});
    }
  } else if (['meta-r-tournament','meta-r-robust'].includes(workload)) {
    const meta = '634f1e0e6cb2de46bcf0a783532d46c23f513d11';
    if (override && override !== meta) throw new Error('Meta R tournament requires pinned Meta candidate model SHA');
    const robust = workload === 'meta-r-robust';
    for (let cohort = 0; cohort < (robust ? 12 : 8); cohort++) {
      add(`${robust ? 'meta-r-robust' : 'meta-r'}-${cohort}`, meta, {cohort});
    }
  } else if (workload === 'lens-real-bop-train') {
    if (override && override !== harnessSha) throw new Error('Real BOP features must match pinned harness SHA');
    for (const profile of ['all', 'color', 'spatial', 'gradient']) {
      add(`lens-real-bop-${profile}`, harnessSha, {profile});
    }
  } else if (workload === 'lens-r8-meta') {
    if (override && override !== harnessSha) throw new Error('Lens R8 requires the pinned immutable harness');
    const slice = choose(input.lane_slice || 'all', ['all', 'pilot', 'remaining'], 'R8 lane slice');
    const arms = ['color-logit','color-balanced','fusion-logit','fusion-balanced',
      'texture-tree','quality-logit','centroid-shrink','consensus-ensemble'];
    for (const [index, arm] of arms.entries()) {
      if ((slice === 'pilot' && index !== 0) || (slice === 'remaining' && index === 0)) continue;
      add(`lens-r8-${index}-${arm}`, harnessSha, {arm, iteration: index + 1});
    }
  } else if (workload === 'lens-r3-methods') {
    if (override && override !== harnessSha) throw new Error('Lens R3 requires pinned immutable harness');
    const slice = choose(input.lane_slice || 'all', ['all', 'pilot', 'remaining'], 'R3 lane slice');
    const methods = ['risk-upper', 'metadata-shield', 'hard-negative'];
    for (const [index, method] of methods.entries()) {
      if ((slice === 'pilot' && index !== 0) || (slice === 'remaining' && index === 0)) continue;
      add(`lens-r3-${index}-${method}`, harnessSha, {method, iteration: index + 1});
    }
  } else if (workload === 'lens-hb-vision') {
    if (override && override !== harnessSha) throw new Error('HB real Vision study requires exact harness source SHA');
    const slice = choose(input.lane_slice || 'all', ['all', 'pilot', 'remaining'], 'HB lane slice');
    for (const [index, model] of ['color', 'vision_prototype', 'vision_pca', 'vision_guard'].entries()) {
      if ((slice === 'pilot' && index !== 0) || (slice === 'remaining' && index === 0)) continue;
      add(`hb-vision-${index}-${model}`, harnessSha, {model});
    }
  } else if (workload === 'rokoko-rl-ablations') {
    for (const learnerSeed of [17,43]) add(`rokoko-ablation-${learnerSeed}`, override || FRONTIER_PINS[workload], {learner_seed: learnerSeed});
  } else if (workload === 'rokoko-rl-seed-sweep') {
    for (const learnerSeed of [17,23,31,43,59,67,73,89]) add(`rokoko-learner-${learnerSeed}`, override || FRONTIER_PINS[workload], {learner_seed: learnerSeed});
  } else if (['aalto-consent-browser','astra-equity-browser'].includes(workload)) {
    const clinicalProduct = workload === 'aalto-consent-browser' ? 'aalto' : 'astra';
    for (const engine of selectedEngines) add(`${clinicalProduct}-${engine}`, override || FRONTIER_PINS[workload], {browser: engine, product: clinicalProduct});
  } else if (workload === 'bahn-offline-sweep') {
    for (let seedShard = 0; seedShard < 8; seedShard++) add(`bahn-offline-${seedShard}`, override || FRONTIER_PINS[workload], {seed_shard: seedShard});
  } else if (workload === 'valio-settlement-browser') {
    for (const engine of selectedEngines) add(`valio-settlement-${engine}`, override || FRONTIER_PINS[workload], {browser: engine, product: 'valio'});
  } else if (Object.hasOwn(FRONTIER_PINS, workload)) {
    add(workload, override || FRONTIER_PINS[workload]);
  } else {
    if (workload === 'sbank-sponsor' && !override) throw new Error('sbank-sponsor requires source_sha');
    const source = override || BASELINES[workload] || harnessSha;
    if (workload === 'native-probe') {
      add('native-x64', source, {arch: 'x64', image: 'default'});
      add('native-arm64', source, {arch: 'arm64', image: 'craci-slim-arm'});
    } else if (['meta-seeds', 'sbank-properties'].includes(workload)) {
      for (const value of shard === 'all' ? [0, 1, 2, 3] : [Number(shard)]) add(`${workload}-${value}`, source, {shard: value});
    } else {
      if (workload === 'meta-browser' && !['all', 'chromium'].includes(browser)) throw new Error('The existing Meta journey supports Chromium only');
      add(workload, source);
    }
  }
  return {schemaVersion: 1, workload, harnessSha, selectedAt: when.toISOString(), windowEnd: WINDOW_END,
    sourceOverride: override || null, maxParallel: Math.min(8, include.length),
    jobCount: workload === 'cache-proof' ? 2 : include.length, matrix: {include}};
}

async function main() {
  const output = resolve(process.env.RUNNER_TEMP || '.', 'craci-plan');
  await mkdir(output, {recursive: true});
  try {
    const plan = resolvePlan(JSON.parse(process.env.CRACI_INPUTS || '{}'), {
      harnessSha: process.env.GITHUB_SHA, creditOpen: process.env.CRACI_CREDIT_WINDOW_OPEN,
      repository: process.env.GITHUB_REPOSITORY,
    });
    await writeFile(resolve(output, 'plan.json'), `${JSON.stringify(plan, null, 2)}\n`, {flag: 'wx'});
    if (process.env.GITHUB_OUTPUT) await appendFile(process.env.GITHUB_OUTPUT,
      `matrix=${JSON.stringify(plan.matrix)}\nsource_sha=${plan.matrix.include.length === 1 ? plan.matrix.include[0].source_sha : ''}\n`);
    console.log(JSON.stringify(plan));
  } catch (error) {
    await writeFile(resolve(output, 'plan-error.json'), `${JSON.stringify({result: 'rejected', reason: error.message})}\n`, {flag: 'wx'});
    throw error;
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) main().catch(error => {console.error(error.message); process.exitCode = 1;});
