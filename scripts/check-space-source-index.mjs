import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PAGE_ID = /^page_[0-9a-f]{32}$/;
const COMMIT_SHA = /^[0-9a-f]{40}$/;

// This offline gate checks structural source integrity. Actual PR/Space freshness
// requires an authenticated live read and must never be inferred from this file.
export function validateSpaceSources(index, map) {
  const errors = [];
  const requireValid = (condition, message) => { if (!condition) errors.push(message); };
  requireValid(index?.schemaVersion === 1, 'invalid source-index version');
  requireValid(index?.repository === 'SalesSquad/junction-pets', 'unexpected source repository');
  requireValid(COMMIT_SHA.test(index?.observedMainHead ?? ''), 'missing observed main commit');

  const agents = Array.isArray(index?.agents) ? index.agents : [];
  requireValid(agents.length === 34, `agent count: expected 34, found ${agents.length}`);
  const seenAgents = new Set();
  for (const agent of agents) {
    requireValid(typeof agent?.slug === 'string' && agent.id === `junction.${agent.slug}`, 'invalid agent identity');
    requireValid(!seenAgents.has(agent?.id), `duplicate agent ${agent?.id}`);
    seenAgents.add(agent?.id);
    for (const field of ['manifest', 'runtimeProfile', 'research', 'developerConfiguration']) {
      requireValid(typeof agent?.[field] === 'string' && agent[field].length > 0, `missing ${field}: ${agent?.id}`);
    }
  }

  const extensions = Array.isArray(index?.extensions) ? index.extensions : [];
  const seenPRs = new Set();
  for (const ext of extensions) {
    requireValid(Number.isInteger(ext?.pullRequest) && ext.pullRequest > 0, 'invalid source PR');
    requireValid(!seenPRs.has(ext?.pullRequest), `duplicate PR ${ext?.pullRequest}`);
    seenPRs.add(ext?.pullRequest);
    requireValid(['open', 'closed', 'merged'].includes(ext?.observedState), `invalid PR state #${ext?.pullRequest}`);
    requireValid(COMMIT_SHA.test(ext?.observedCommit ?? ''), `invalid source commit #${ext?.pullRequest}`);
    requireValid(typeof ext?.isMainImplementation === 'boolean', `missing main qualification #${ext?.pullRequest}`);
    if (ext?.mainIntegration) {
      const integration = ext.mainIntegration;
      requireValid(ext.isMainImplementation === true, `source #${ext.pullRequest} marked pending despite main integration`);
      requireValid(Number.isInteger(integration.viaPullRequest) && integration.viaPullRequest > 0, `missing integration PR #${ext.pullRequest}`);
      requireValid(COMMIT_SHA.test(integration.mergeCommit ?? ''), `invalid integration SHA #${ext.pullRequest}`);
    }
  }

  requireValid(map?.schema === 'junction-spaces-reconciliation/v1', 'invalid Space map schema');
  const sourcePageURLs = [];
  for (const [name, expected] of [['main_coverage', 19], ['tech_coverage', 19]]) {
    const items = Array.isArray(map?.[name]) ? map[name] : [];
    requireValid(items.length === expected, `${name}: expected ${expected}, found ${items.length}`);
    const seenUrls = new Set();
    for (const item of items) {
      const requiredPath = name === 'main_coverage' ? 'challenges' : 'tech-challenges';
      requireValid(typeof item?.source_url === 'string' && new RegExp(`^https://hackjunction\\.app/participate/45/${requiredPath}/\\d+$`).test(item.source_url), `invalid ${name} source URL`);
      requireValid(!seenUrls.has(item?.source_url), `duplicate ${name} source URL`);
      seenUrls.add(item?.source_url);
      requireValid(Array.isArray(item?.page_urls) && item.page_urls.length > 0, `unmapped ${name} source`);
      if (Array.isArray(item?.page_urls)) sourcePageURLs.push(...item.page_urls);
    }
  }

  const pages = Array.isArray(map?.card_pages) ? map.card_pages : [];
  requireValid(pages.length === 35, `canonical card count: expected 35, found ${pages.length}`);
  const seenPages = new Set();
  for (const page of pages) {
    requireValid(PAGE_ID.test(page?.page_id ?? ''), `invalid card page ID: ${page?.page_id}`);
    requireValid(!seenPages.has(page?.page_id), `duplicate card page ID: ${page?.page_id}`);
    seenPages.add(page?.page_id);
    requireValid(page?.url === `https://chatgpt.com/space/${page.page_id}`, `noncanonical card URL: ${page?.page_id}`);
    requireValid(page?.readback_verified === true, `unverified card ${page?.page_id}`);
  }
  const canonicalURLs = new Set(pages.map(page => page?.url));
  for (const url of sourcePageURLs) {
    requireValid(canonicalURLs.has(url), `source references a missing canonical Page: ${url}`);
  }
  const inventory = map?.canonical_page_inventory;
  requireValid(Boolean(inventory) && typeof inventory === 'object', 'missing live Page inventory');
  const cardGroups = [['main', 19], ['tech', 16]];
  const covered = new Set();
  for (const [kind, expected] of cardGroups) {
    const group = Array.isArray(inventory?.[kind]) ? inventory[kind] : [];
    requireValid(group.length === expected, `inventory ${kind}: expected ${expected}, found ${group.length}`);
    for (const id of group) {
      requireValid(seenPages.has(id), `inventory ${kind} missing card ${id}`);
      requireValid(!covered.has(id), `card assigned to multiple groups: ${id}`);
      covered.add(id);
    }
  }
  requireValid(covered.size === seenPages.size, 'unassigned canonical card');

  return { ok: errors.length === 0, errors, stats: {
    agents: agents.length, mainSources: map?.main_coverage?.length ?? 0,
    techSources: map?.tech_coverage?.length ?? 0, cardPages: pages.length,
    mainPages: inventory?.main?.length ?? 0, techPages: inventory?.tech?.length ?? 0,
  } };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const index = JSON.parse(readFileSync(resolve(ROOT, 'docs/AGENT_SOURCE_INDEX.json'), 'utf8'));
  const map = JSON.parse(readFileSync(resolve(ROOT, 'ops/challenge-spaces-reconciliation-20261113.json'), 'utf8'));
  const result = validateSpaceSources(index, map);
  console.log(JSON.stringify({ check: 'junction-source-index-offline', ...result }, null, 2));
  if (!result.ok) process.exitCode = 1;
}
