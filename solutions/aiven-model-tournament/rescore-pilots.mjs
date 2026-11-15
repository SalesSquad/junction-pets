// Re-applies the deterministic gates to a stored pilots-*.json (raw outputs kept), without new model calls.
import { readFileSync, writeFileSync } from 'node:fs';
import { validateResponse } from '../aiven-decision-bridge/bridge.mjs';
import { wilson } from './scoring.mjs';
const file = process.argv[2]; const o = JSON.parse(readFileSync(file, 'utf8'));
const root = new URL('../../', import.meta.url);
const hostsFor = slug => [...new Set(JSON.parse(readFileSync(new URL(`pets/${slug}/pet.json`, root))).sources.map(x => new URL(x.url).hostname.replace(/^www\./, '')))];
const cases = {}; for (const p of new Set(o.results.map(r => r.pet))) for (const c of JSON.parse(readFileSync(new URL(`pilots/cases-${p}.cal.json`, import.meta.url))).cases ?? []) cases[c.id] = c;
for (const r of o.results.filter(r => r.arm === 'shared' && !r.error)) {
  const out = o.raw.find(x => x.case === r.case && x.rep === r.rep && x.arm === r.arm)?.output; let n = 0;
  // Rescoring model proposals does not mint a trusted user intent or a pending action.
  if (validateResponse(out, undefined, { officialHosts: hostsFor(r.pet) }).length === 0) n = out.action_proposals.length;
  r.det.proposalOk = cases[r.case]?.expects_proposal ? n > 0 : true;
  r.pass = Object.values(r.det).every(Boolean) && Object.values(r.judges).every(v => v === true);
}
for (const key of Object.keys(o.summary)) { const [pet, arm] = key.split('/'); const rs = o.results.filter(r => r.pet === pet && r.arm === arm && !r.error); const k = rs.filter(r => r.pass).length; Object.assign(o.summary[key], { consensusPass: +(k / (rs.length || 1)).toFixed(3), passCI95: wilson(k, rs.length), rescored: true }); }
writeFileSync(file.replace(/\.json$/, '.rescored.json'), JSON.stringify(o, null, 2));
console.log(JSON.stringify(o.summary, null, 1));
