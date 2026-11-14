// Selects guidance modules for one request. Core is always loaded; each module is
// added when its topic appears. The union stays far below the 20,000-character
// manifest limit, so a module can carry more depth than the monolithic AGENTS.md.
import { readFileSync } from 'node:fs';
const read = n => readFileSync(new URL(`./${n}.md`, import.meta.url), 'utf8');
export const MODULES = {
  kafka: /kafka|partition|offset|consumer|lag|topic|rebalanc|stream/i,
  'flight-recorder': /outbox|duplicate|idempot|exactly.once|replay|debezium|charge|email/i,
  'personal-data': /patient|health|personal|gdpr|henkil|pseudonym|anonym|clinic|registry|residen|region|dpo|findata|notes?\b/i,
  analytics: /rank|compar|median|mean|metric|dashboard|count|n=|wait|gap|cohort|region [a-z]|report|invoice|usage|reconcil/i,
  services: /aiven|opensearch|valkey|clickhouse|flink|gateway|price|cost|plan|operator|kubernetes|terraform|mcp|scale|service/i,
  postgres: /postgres|\bpg\b|sql|index|query|slow/i,
  peers: /peer|agent|handoff|companion|mariadb|craci|afterquery/i,
  'temporal-data': /as.?of|valid_(from|to)|timestamp|time ?zone|histor|version|wikipedia|snapshot|mariadb|mysql|benchmark|latency|credential|password|access denied|permission/i,
  'health-analytics': /patient|pathway|care|clinic|cancer|oncolog|registry|health|hospital|treatment|diagnos/i
};
export function selectModules(request) {
  const chosen = Object.entries(MODULES).filter(([, rx]) => rx.test(request)).map(([n]) => n);
  return ['core', ...(chosen.length ? chosen : ['services'])];
}
export function systemFor(request) {
  const mods = selectModules(request);
  return { modules: mods, system: mods.map(read).join('\n\n') };
}
