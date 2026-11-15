#!/usr/bin/env node
// Discovery study: can Exa find the official provision from a person's own words?
// For each test situation (gold provision known), search Exa exactly as the product does (restricted to the
// official domains) and check the top results:
//   section   a result is the gold section (US: title + section; UK: same instrument and provision; EU: same act)
//   part      US only: a result is in the gold CFR part (right neighbourhood, wrong section)
//   pinned    a hit is a point-in-time URL (ecfr.gov/on/DATE/…, legislation.gov.uk/…/DATE)
// The registry cannot know these provisions (they are arbitrary CFR sections), so this is the path that
// decides whether the butler works beyond its ten known rights.
// Usage: node --experimental-strip-types bench/exa_study/discovery.mjs bench/datasets/out/training/test.jsonl [--limit=N] [--unique] [--n=5]
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { OFFICIAL_DOMAINS, refFromUrl } from "../../src/timetravel/timetravel.ts";

const file = process.argv[2];
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const limit = Number(arg("limit", "100000"));
const n = Number(arg("n", "5"));
const budget = Number(process.env.EXA_BUDGET_USD ?? 30);
const ledger = new URL("../results/exa-spend.jsonl", import.meta.url);
const spent = () => (existsSync(ledger) ? readFileSync(ledger, "utf8").split("\n").filter(Boolean).reduce((a, l) => a + (JSON.parse(l).usd ?? 0), 0) : 0);
const outFile = "bench/exa_study/discovery.jsonl";
const done = new Map(existsSync(outFile) ? readFileSync(outFile, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.key, j]; }) : []);
let items = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).filter((x) => !x.attack);
// --unique: one situation per provision, so a provision with many situations does not dominate.
if (process.argv.includes("--unique")) { const seen = new Set(); items = items.filter((x) => !seen.has(x.provision) && seen.add(x.provision)); }
items = items.slice(0, limit);
const key = process.env.EXA_API_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.exa", "-w"], { encoding: "utf8" }).trim();

const judgeHit = (it, url) => {
  const ref = refFromUrl(url);
  const g = it.ref;
  if (g.source === "ecfr") {
    const m = url.match(/ecfr\.gov\/.*title-(\d+)(?:\/.*)?\/part-(\d+[A-Za-z]?)/i);
    const part = m && Number(m[1]) === Number(g.title) && String(m[2]) === String(g.part);
    const section = ref?.source === "ecfr" && Number(ref.title) === Number(g.title) && String(ref.section) === String(g.section);
    return { section: !!section, part: !!part || !!section };
  }
  if (g.source === "ukleg") {
    const inst = g.path.split("/").slice(0, 3).join("/");
    return { section: ref?.source === "ukleg" && ref.path === g.path, part: url.includes(`legislation.gov.uk/${inst}`) };
  }
  return { section: ref?.source === "eurlex" && ref.celex === g.celex, part: false };
};

let next = 0;
await Promise.all(Array.from({ length: 5 }, async () => {
  while (next < items.length) {
    const it = items[next++];
    const k = `${it.gid}|${it.question.slice(0, 80)}`;
    if (done.has(k)) continue;
    if (spent() >= budget) return;
    let j = {};
    for (let i = 0; i < 3; i++) {
      const res = await fetch("https://api.exa.ai/search", { method: "POST", headers: { "x-api-key": key, "content-type": "application/json" }, body: JSON.stringify({ query: it.question, type: "auto", numResults: n, includeDomains: OFFICIAL_DOMAINS }) }).catch(() => null);
      j = res ? await res.json().catch(() => ({})) : {};
      if (res?.ok) break;
      await new Promise((r) => setTimeout(r, 1500 * 2 ** i));
    }
    appendFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), tag: "discovery-study", cmd: "search", usd: j.costDollars?.total ?? 0, q: it.gid }) + "\n");
    const urls = (j.results ?? []).map((r) => r.url);
    const hits = urls.map((u) => judgeHit(it, u));
    const row = { key: k, gid: it.gid, jurisdiction: it.jurisdiction, lang: it.lang, provision: it.provision, section: hits.some((h) => h.section), part: hits.some((h) => h.part), rank: hits.findIndex((h) => h.section) + 1 || null, pinned: urls.some((u, i) => hits[i].section && /ecfr\.gov\/on\/\d{4}-\d{2}-\d{2}|legislation\.gov\.uk\/.+\/\d{4}-\d{2}-\d{2}/.test(u)), urls };
    done.set(k, row);
    appendFileSync(outFile, JSON.stringify(row) + "\n");
    if (done.size % 100 === 0) console.error(`${done.size}/${items.length} spent $${spent().toFixed(2)}`);
  }
}));
const rows = [...done.values()];
const pct = (rs, f) => `${rs.filter(f).length}/${rs.length} (${((100 * rs.filter(f).length) / Math.max(1, rs.length)).toFixed(1)} %)`;
const by = (f) => Object.fromEntries([...new Set(rows.map(f))].map((v) => [v, { n: rows.filter((r) => f(r) === v).length, section: pct(rows.filter((r) => f(r) === v), (r) => r.section), partOrInstrument: pct(rows.filter((r) => f(r) === v), (r) => r.part) }]));
const summary = { queries: rows.length, results: n, sectionRecall: pct(rows, (r) => r.section), partOrInstrumentRecall: pct(rows, (r) => r.part), top1: pct(rows, (r) => r.rank === 1), pinnedVersionAmongHits: pct(rows.filter((r) => r.section), (r) => r.pinned), byJurisdiction: by((r) => r.jurisdiction), byLanguage: by((r) => r.lang), exaSpentUsd: Number(spent().toFixed(3)) };
console.log(JSON.stringify(summary, null, 1));
writeFileSync("bench/exa_study/discovery.summary.json", JSON.stringify(summary, null, 1));
