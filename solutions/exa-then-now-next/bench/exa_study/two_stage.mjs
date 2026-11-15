#!/usr/bin/env node
// Discovery study, stage 2: Exa found a CFR part; which section of it sets the amount?
//
// Stage 1 is already measured (rewrite_discovery_given.jsonl): the right PART is in Exa's top 5 for 53.0 % of
// situations, the right SECTION for 25.7 % (11 % as the first result). Here the candidates are every
// amount-bearing section of the parts in that top 5, in the edition of the event year, and typed judges pick
// one with choice questions: rounds of at most 12 options, the winners meet in a final.
// Candidate tables exist only for CFR titles 12, 14, 16, 20, 29 and 49 (CFR-Annual focused, from GovInfo):
// parts Exa returned in other titles contribute no candidates, and the summary reports how many.
// No Exa call is made: this measures what the official structure plus judges add after the search.
// The index is built by two_stage_index.py.
//
// Usage: node --experimental-strip-types bench/exa_study/two_stage.mjs [--arm=rewriteParts|rawParts|both] [--judges=nemotron,jev]
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { logprobDecisions, typesafeJev } from "../../src/decide/decide.ts";

const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const arm = arg("arm", "rewriteParts");
const names = arg("judges", "nemotron,jev").split(",");
const { items, parts, coveredTitles } = JSON.parse(readFileSync("bench/exa_study/two_stage_index.json", "utf8"));
const nemoKey = process.env.VERDA_INFERENCE_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.verda-dc", "-w"], { encoding: "utf8" }).trim();
const JUDGES = {
  nemotron: () => logprobDecisions({ id: "nemotron", baseUrl: "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1", apiKey: nemoKey, model: "nemotron-3.5-super-vl", timeoutMs: 30000 }),
  jev: async () => {
    const key = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
    const { TypeSafeClient } = await import("@typesafe-ai/sdk");
    const ts = new TypeSafeClient({ apiKey: key, defaultModel: "jev-1.14.0" });
    return typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) });
  },
};
const judges = [];
for (const n of names) judges.push(await JUDGES[n]());

const QUESTION = "Which option is the regulation section that sets the amount, rate, limit or penalty for the case the person describes in `situation`?";
const LETTERS = "ABCDEFGHIJKL";
const text = (s) => `§ ${s.section} ${s.subject} — ${s.sample.replace(/\s+/g, " ").slice(0, 220)}`;
const retry = async (fn) => { for (let i = 0; ; i++) { try { return await fn(); } catch (e) { if (i >= 3) throw e; await new Promise((r) => setTimeout(r, 1500 * 2 ** i)); } } };
/** One round: mean probability per option over the judges. */
async function round(situation, cands) {
  const q = [{ kind: "choice", name: "section", instructions: QUESTION, options: Object.fromEntries(cands.map((c, i) => [LETTERS[i], text(c)])) }];
  const ps = cands.map(() => 0);
  let answered = 0;
  for (const j of judges) {
    try {
      const a = (await retry(() => j.decide({ situation }, q))).answers[0];
      cands.forEach((_, i) => { ps[i] += a.probabilities?.[LETTERS[i]] ?? (a.choice === LETTERS[i] ? 1 : 0); });
      answered++;
    } catch { /* this judge abstains in this round */ }
  }
  return ps.map((p) => p / Math.max(1, answered));
}
async function pick(situation, cands) {
  let pool = cands, p = 1;
  while (pool.length > 1) {
    const groups = [];
    for (let i = 0; i < pool.length; i += LETTERS.length) groups.push(pool.slice(i, i + LETTERS.length));
    const winners = [];
    for (const g of groups) {
      if (g.length === 1) { winners.push(g[0]); continue; }
      const ps = await round(situation, g);
      const best = ps.indexOf(Math.max(...ps));
      winners.push(g[best]);
      if (groups.length === 1) p = ps[best];
    }
    pool = winners;
  }
  return { section: pool[0], p };
}

const outFile = `bench/exa_study/two_stage.${arm}.${names.join("+")}.v2.jsonl`;
const done = new Map(existsSync(outFile) ? readFileSync(outFile, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.key, j]; }) : []);
let next = 0;
await Promise.all(Array.from({ length: 5 }, async () => {
  while (next < items.length) {
    const it = items[next++];
    if (done.has(it.key)) continue;
    const tps = arm === "both" ? [...it.rewriteParts, ...it.rawParts.filter((x) => !it.rewriteParts.some((y) => y[0] === x[0] && y[1] === x[1]))] : it[arm];
    const cands = tps.flatMap(([t, p]) => (parts[`${t}|${p}|${it.gold.year}`] ?? []).map((s) => ({ ...s, title: t, part: p })));
    const isGold = (c) => c && c.title === it.gold.title && c.part === it.gold.part && c.section === it.gold.section;
    let chosen = null, p = 0;
    if (cands.length) ({ section: chosen, p } = await pick(it.question, cands));
    const uncovered = tps.filter(([t]) => !coveredTitles.includes(t)).length;
    const row = { key: it.key, lang: it.lang, candidates: cands.length, parts: tps.length, uncoveredParts: uncovered, goldAmong: cands.some(isGold), hit: isGold(chosen), p, rewriteRank: it.rewriteRank ?? null, chosen: chosen ? `${chosen.title} CFR ${chosen.section}` : null, gold: `${it.gold.title} CFR ${it.gold.section}`, rewriteSection: it.rewriteSection, agentSection: it.agentSection, searchSection: it.searchSection };
    done.set(it.key, row);
    appendFileSync(outFile, JSON.stringify(row) + "\n");
    if (done.size % 50 === 0) console.error(`${done.size}/${items.length}`);
  }
}));
const rows = items.map((it) => done.get(it.key)).filter(Boolean);
const pct = (rs, f) => `${rs.filter(f).length}/${rs.length} (${((100 * rs.filter(f).length) / Math.max(1, rs.length)).toFixed(1)} %)`;
const block = (rs) => ({
  n: rs.length,
  twoStageSectionTop1: pct(rs, (r) => r.hit),
  givenPartFound: pct(rs.filter((r) => r.goldAmong), (r) => r.hit),
  confident: (() => { const c = rs.filter((r) => r.p >= 0.8); return { share: pct(rs, (r) => r.p >= 0.8), right: pct(c, (r) => r.hit) }; })(),
  searchOnlySectionTop5: pct(rs, (r) => r.rewriteSection),
  searchOnlySectionTop1: pct(rs, (r) => r.rewriteRank === 1),
  noCandidates: pct(rs, (r) => r.candidates === 0),
  agentSectionTop1: pct(rs, (r) => r.agentSection),
  twoStageOrAgent: pct(rs, (r) => r.hit || r.agentSection),
});
// Items whose top-5 parts are all in titles that have candidate tables: the fair view of stage 2.
const covered = (rs) => rs.filter((r) => r.uncoveredParts === 0);
const summary = { arm, judges: names, coveredTitles, allPartsInCoveredTitles: block(covered(rows)), medianCandidates: rows.map((r) => r.candidates).sort((a, b) => a - b)[Math.floor(rows.length / 2)], ...block(rows), byLanguage: Object.fromEntries(["English", "Finnish", "German"].map((l) => [l, block(rows.filter((r) => r.lang === l))])) };
console.log(JSON.stringify(summary, null, 1));
writeFileSync(outFile.replace(".jsonl", ".summary.json"), JSON.stringify(summary, null, 1));
