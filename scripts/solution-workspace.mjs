import {readFile, readdir, mkdir, writeFile, access} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';

const root = fileURLToPath(new URL('../', import.meta.url));
const slugPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const shaPattern = /^[a-f0-9]{40}$/;
const text = (value) => typeof value === 'string' && value.trim().length > 0;
const readJson = async (file) => JSON.parse(await readFile(file, 'utf8'));

export async function agentCatalog(repo) {
  const agents = [];
  for (const entry of await readdir(path.join(repo, 'pets'), {withFileTypes: true})) {
    if (entry.isDirectory()) agents.push(await readJson(path.join(repo, 'pets', entry.name, 'pet.json')));
  }
  return agents;
}

export function validateSolution(value, agents, expectedId = value?.id) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected solution object');
  const fields = ['schemaVersion', 'id', 'title', 'objective', 'baseCommit', 'challengeSlugs', 'agentIds', 'stage', 'ownedPaths', 'capabilityUses'];
  if (Object.keys(value).some((key) => !fields.includes(key)) || fields.some((key) => !(key in value))) throw new Error('Unexpected or missing solution fields');
  if (value.schemaVersion !== 1 || typeof value.id !== 'string' || !slugPattern.test(value.id) || value.id !== expectedId) throw new Error('Invalid solution identity');
  if (!text(value.title) || !text(value.objective) || !shaPattern.test(value.baseCommit)) throw new Error('Title, objective and exact base commit are required');
  if (!['idea', 'building', 'demo', 'submitted', 'paused'].includes(value.stage)) throw new Error('Invalid stage');
  for (const key of ['challengeSlugs', 'agentIds', 'ownedPaths', 'capabilityUses']) if (!Array.isArray(value[key])) throw new Error(`${key} must be an array`);
  for (const key of ['challengeSlugs', 'agentIds']) if (new Set(value[key]).size !== value[key].length) throw new Error(`Duplicate ${key}`);
  const knownChallenges = new Set(agents.map((agent) => agent.company.slug));
  if (value.challengeSlugs.some((slug) => !knownChallenges.has(slug))) throw new Error('Unknown challenge/company');
  const knownAgents = new Map(agents.map((agent) => [agent.id, agent]));
  if (value.agentIds.some((id) => !knownAgents.has(id))) throw new Error('Unknown agent');
  if (value.ownedPaths.length !== 1 || value.ownedPaths[0] !== `solutions/${value.id}/`) throw new Error('Scaffold ownership must remain within this solution');
  const seen = new Set();
  for (const use of value.capabilityUses) {
    if (!use || Object.keys(use).sort().join(',') !== 'agentId,capabilityId,purpose,status' || !text(use.purpose) || use.status !== 'planned') throw new Error('Capability uses are planned references, not execution receipts');
    if (!value.agentIds.includes(use.agentId) || !knownAgents.get(use.agentId)?.capabilities.some((capability) => capability.id === use.capabilityId)) throw new Error('Unknown or unselected agent capability');
    const key = `${use.agentId}/${use.capabilityId}`;
    if (seen.has(key)) throw new Error('Duplicate capability use');
    seen.add(key);
  }
  return value;
}

export async function checkSolutions(repo) {
  const agents = await agentCatalog(repo);
  const solutions = [];
  for (const entry of await readdir(path.join(repo, 'solutions'), {withFileTypes: true})) {
    if (!entry.isDirectory()) continue;
    const solution = validateSolution(await readJson(path.join(repo, 'solutions', entry.name, 'solution.json')), agents, entry.name);
    for (const name of ['README.md', 'ARCHITECTURE.md', 'PROGRESS.md', 'AGENTS.md']) await access(path.join(repo, 'solutions', entry.name, name));
    solutions.push(solution);
  }
  return solutions.sort((a, b) => a.id.localeCompare(b.id));
}

export async function createSolution(repo, {id, challenge, agent, baseCommit}) {
  if (!slugPattern.test(id ?? '')) throw new Error('Use a lowercase solution slug');
  const agents = await agentCatalog(repo);
  const selected = agents.find((item) => item.company.slug === agent);
  if (!selected) throw new Error('Unknown agent company slug');
  const solution = validateSolution({schemaVersion: 1, id, title: id, objective: 'Define one user problem and an observable demo outcome.', baseCommit, challengeSlugs: challenge ? [challenge] : [], agentIds: [selected.id], stage: 'idea', ownedPaths: [`solutions/${id}/`], capabilityUses: []}, agents);
  const directory = path.join(repo, 'solutions', id);
  await mkdir(directory); // Exclusive creation: existing work is never overwritten.
  const files = {
    'solution.json': JSON.stringify(solution, null, 2) + '\n',
    'README.md': `# ${id}\n\n## Product brief\n\nUser and problem: TODO\n\nDemo outcome: TODO\n\nChallenge fit and exact judging clauses: TODO${challenge ? ` — start at [company research](../../pets/${challenge}/CHALLENGE_RESEARCH.md)` : ' — no competition selected yet'}\n\nNon-goals for this slice: TODO\n\n## Start a developer\n\nRead [the workspace guide](../../docs/SOLUTION_WORKSPACES.md), [local instructions](AGENTS.md), [architecture](ARCHITECTURE.md) and [progress](PROGRESS.md). Resolve current GitHub source and path ownership before writing.\n\n## Acceptance\n\n- One user-visible outcome and its reproducible command: TODO\n- Decisive test and expected result: TODO\n- Demo/submission material: TODO\n`,
    'AGENTS.md': `# ${id} developer scope\n\nRoot [AGENTS.md](../../AGENTS.md) applies. This is developer guidance, not a runtime agent profile.\n\nDefault owned path: \`solutions/${id}/\`. Put solution-specific code, assets, fixtures and docs here. Reuse existing \`apps/\`, \`services/\` and \`pets/\` through their contracts; get explicit integrator ownership before changing those paths. Do not duplicate pending PR implementations.\n\nBefore editing: fill the next task in PROGRESS.md with exact source SHA, owner, paths and acceptance command; inspect current PRs and surviving work. Separate cloud worktrees do not share the local pet lease.\n\nBefore handoff: commit, push a task branch, open/update a draft PR, bind checks and independent review to its final HEAD, and update PROGRESS.md. Deployment, merging and runtime calls follow existing authority.\n`,
    'ARCHITECTURE.md': `# ${id} architecture\n\n## Components\n\n| Component | Existing source or new owned path | Interface | State |\n| --- | --- | --- | --- |\n| Product UI/service/data | TODO | TODO | planned |\n| Agent | \`pets/${agent}/\` | Existing declared capabilities | content only; execution separately qualified |\n\n## Reuse and dependencies\n\nRecord source SHA, PR/base/dependencies, contract, integration owner and next action for each reused pending implementation. Keep source in its existing location.\n\n## Capability composition\n\nList planned agent capability references in solution.json. That list grants no execution authority. Reuse [existing collaboration contracts](../../docs/INTER_PET_COLLABORATION.md); Chibi owns production identity, consent, memory and model/tool dispatch. Record measured provider/host evidence separately.\n\n## Knowledge and learning\n\nKeep challenge/product findings here with sources. Propose reusable expertise updates to the owning pet/service through a separate bounded PR and evaluation; never silently merge private user memories.\n`,
    'PROGRESS.md': `# ${id} continuation\n\nStage: idea; scaffold only. No worker, runtime, demo or submission is established.\n\n## Next task\n\n- Work ID: junction.solution.${id}.first-slice\n- Base SHA: ${baseCommit}\n- Owner and task/PR URL: unassigned\n- Owned paths: solutions/${id}/\n- Objective: replace the brief TODOs with one demonstrable vertical slice\n- Acceptance command and expected result: TODO before implementation\n- Blocker: product slice has not been specified\n- Next action: assigned developer reads the challenge and defines the smallest user-visible slice\n\n## Evidence\n\nRecord exact tested SHA, commands, observed output, executor and evidence links. Separate planned, synthetic, actual provider, hardware and submitted evidence. At handoff preserve the next executable task here and in the PR.\n`
  };
  for (const [name, content] of Object.entries(files)) await writeFile(path.join(directory, name), content, {flag: 'wx'});
  return solution;
}

export async function briefSolution(repo, id) {
  if (!slugPattern.test(id ?? '')) throw new Error('Invalid solution slug');
  const agents = await agentCatalog(repo);
  const solution = validateSolution(await readJson(path.join(repo, 'solutions', id, 'solution.json')), agents, id);
  return {solution, readFirst: ['START_HERE.md', 'AGENTS.md', 'docs/SOLUTION_WORKSPACES.md', `solutions/${id}/AGENTS.md`, `solutions/${id}/README.md`, `solutions/${id}/ARCHITECTURE.md`, `solutions/${id}/PROGRESS.md`, ...solution.challengeSlugs.map((slug) => `pets/${slug}/CHALLENGE_RESEARCH.md`)], execution: 'developer handoff only; no worker or runtime is started'};
}

async function main() {
  const [command, id, ...rest] = process.argv.slice(2);
  if (command === 'check' || command === 'list') {
    if (id !== undefined) throw new Error('check/list take no arguments');
    console.log(JSON.stringify({solutions: await checkSolutions(root), runtimeExecuted: false}, null, 2));
  } else if (command === 'brief') {
    if (rest.length) throw new Error('brief takes one solution slug');
    console.log(JSON.stringify(await briefSolution(root, id), null, 2));
  } else if (command === 'new') {
    const options = {};
    for (let i = 0; i < rest.length; i += 2) {
      if (!['--challenge', '--agent'].includes(rest[i]) || !rest[i + 1] || options[rest[i]]) throw new Error('Expected --agent company [--challenge company]');
      options[rest[i]] = rest[i + 1];
    }
    const baseCommit = execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim();
    console.log(JSON.stringify(await createSolution(root, {id, challenge: options['--challenge'], agent: options['--agent'], baseCommit}), null, 2));
  } else throw new Error('Usage: node scripts/solution-workspace.mjs new <solution> --agent <company> [--challenge <company>] | list | check | brief <solution>');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch((error) => {console.error(error.message); process.exitCode = 1;});
