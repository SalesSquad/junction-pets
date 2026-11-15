#!/usr/bin/env node
// Discovery study, arm 3: rewrite first, then search. A hosted model (Nemotron on the Verda endpoint) turns the
// person's message, in any language, into one English legal search query; Exa then searches the official
// domains exactly as in arm 1. Same 300 base messages as the Exa Agent arm, so the three arms are paired.
// Usage: node --experimental-strip-types bench/exa_study/rewrite_discovery.mjs
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { OFFICIAL_DOMAINS, refFromUrl } from "../../src/timetravel/timetravel.ts";

const budget = Number(process.env.EXA_BUDGET_USD ?? 30);
const ledger = new URL("../results/exa-spend.jsonl", import.meta.url);
const spent = () => (existsSync(ledger) ? readFileSync(ledger, "utf8").split("\n").filter(Boolean).reduce((a, l) => a + (JSON.parse(l).usd ?? 0), 0) : 0);
const exaKey = process.env.EXA_API_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.exa", "-w"], { encoding: "utf8" }).trim();
const nemoKey = process.env.VERDA_INFERENCE_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.verda-dc", "-w"], { encoding: "utf8" }).trim();
// --jurisdiction="United States federal regulations (CFR)": state the governing law instead of letting the model
// infer the country from the message's language (it wrote "Finland" for Finnish messages about US rules).
const jurisdiction = process.argv.find((a) => a.startsWith("--jurisdiction="))?.slice(15) ?? "";
const outFile = jurisdiction ? "bench/exa_study/rewrite_discovery_given.jsonl" : "bench/exa_study/rewrite_discovery.jsonl";
const done = new Map(existsSync(outFile) ? readFileSync(outFile, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.key, j]; }) : []);
const agent = readFileSync("bench/exa_study/agent_discovery.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
// Base messages only, first row wins. Attack variants keep the base message's first 80 characters, so a plain
// Map over every row returned the attack variant for 275 of the 300 keys (found in review, 14 Nov): those rows
// were re-run, and the earlier ones are kept in *.attacked.jsonl.
const byKey = new Map();
for (const l of readFileSync("bench/exa_study/all-situations.jsonl", "utf8").split("\n").filter(Boolean)) {
  const x = JSON.parse(l);
  if (x.attack) continue;
  const k = `${x.gid}|${x.question.slice(0, 80)}`;
  if (!byKey.has(k)) byKey.set(k, x);
}

export const REWRITE = (question) => `A person describes a situation. Write ONE English web search query that would find the official legal provision (statute or regulation section) that sets the money amount for it.
Name the regulated activity in legal terms, the regulator or statute if it is evident, ${jurisdiction ? `the governing law (${jurisdiction})` : "the country"}, and the kind of amount (civil penalty, fee, limit, rate, compensation). Leave out names, dates and figures. At most 25 words.

Situation: "${question}"

Answer with JSON only: {"query": "..."}`;

async function rewrite(question) {
  for (let i = 0; i < 4; i++) {
    const r = await fetch("https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1/chat/completions", { method: "POST", headers: { authorization: `Bearer ${nemoKey}`, "content-type": "application/json" }, body: JSON.stringify({ model: "nemotron-3.5-super-vl", temperature: 0, max_tokens: 120, reasoning_effort: "none", messages: [{ role: "user", content: REWRITE(question) }] }) }).catch(() => null);
    if (r?.ok) { try { return JSON.parse((await r.json()).choices[0].message.content.match(/\{[^]*\}/)[0]).query; } catch { /* retry */ } }
    await new Promise((res) => setTimeout(res, 1500 * 2 ** i));
  }
  return null;
}
const hit = (it, url) => {
  const ref = refFromUrl(url), g = it.ref;
  const m = url.match(/ecfr\.gov\/.*title-(\d+)(?:\/.*)?\/part-(\d+[A-Za-z]?)/i);
  const section = ref?.source === "ecfr" && Number(ref.title) === Number(g.title) && String(ref.section) === String(g.section);
  return { section: !!section, part: !!section || (!!m && Number(m[1]) === Number(g.title) && String(m[2]) === String(g.part)) };
};
let next = 0;
await Promise.all(Array.from({ length: 5 }, async () => {
  while (next < agent.length) {
    const a = agent[next++];
    if (done.has(a.key) || spent() >= budget) continue;
    const it = byKey.get(a.key);
    const query = await rewrite(it.question);
    let urls = [];
    if (query) {
      const res = await fetch("https://api.exa.ai/search", { method: "POST", headers: { "x-api-key": exaKey, "content-type": "application/json" }, body: JSON.stringify({ query, type: "auto", numResults: 5, includeDomains: OFFICIAL_DOMAINS }) }).catch(() => null);
      const j = res ? await res.json().catch(() => ({})) : {};
      appendFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), tag: "rewrite-discovery", cmd: "search", usd: j.costDollars?.total ?? 0, q: it.gid }) + "\n");
      urls = (j.results ?? []).map((r) => r.url);
    }
    const hs = urls.map((u) => hit(it, u));
    const row = { key: a.key, lang: a.lang, query, section: hs.some((h) => h.section), part: hs.some((h) => h.part), rank: hs.findIndex((h) => h.section) + 1 || null, agentSection: a.section, searchSection: a.searchSection, urls };
    done.set(a.key, row);
    appendFileSync(outFile, JSON.stringify(row) + "\n");
  }
}));
// Agent flags are read from the (rescored) agent file at summary time, not from the copy stored in each row.
const rows = agent.map((a) => (done.get(a.key) ? { ...done.get(a.key), agentSection: a.section, searchSection: a.searchSection } : null)).filter(Boolean);
const pct = (rs, f) => `${rs.filter(f).length}/${rs.length} (${((100 * rs.filter(f).length) / Math.max(1, rs.length)).toFixed(1)} %)`;
const block = (rs) => ({ n: rs.length, rewriteSection: pct(rs, (r) => r.section), rewritePart: pct(rs, (r) => r.part), rawSearchSection: pct(rs, (r) => r.searchSection), agentSection: pct(rs, (r) => r.agentSection), anyOfThree: pct(rs, (r) => r.section || r.searchSection || r.agentSection) });
const summary = { ...block(rows), byLanguage: Object.fromEntries(["English", "Finnish", "German"].map((l) => [l, block(rows.filter((r) => r.lang === l))])), exaSpentUsd: Number(spent().toFixed(3)) };
console.log(JSON.stringify(summary, null, 1));
writeFileSync(outFile.replace(".jsonl", ".summary.json"), JSON.stringify(summary, null, 1));
