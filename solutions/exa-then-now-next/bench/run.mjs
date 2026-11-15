#!/usr/bin/env node
// Citation-completion benchmark: keywords vs question vs citation-completion queries on Exa.
// Usage: node bench/run.mjs [--limit N]   (uses the keyless MCP tier unless the relay code is changed)
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { exaMcpSearch } from "../relay/exa-mcp.mjs";
import { classify, anchorHit } from "./classify.mjs";

const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const limitArg = process.argv.indexOf("--limit");
const errands = limitArg > 0 ? spec.errands.slice(0, Number(process.argv[limitArg + 1])) : spec.errands;
const ARMS = ["keywords", "question", "citation"];
const GAP_MS = 1200;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Seeded shuffle (mulberry32) so arm order varies per errand but the run is reproducible.
let seed = 20261114;
const rand = () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const shuffled = (xs) => xs.map((x) => [rand(), x]).sort((a, b) => a[0] - b[0]).map(([, x]) => x);

async function search(query) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const t0 = Date.now();
    try {
      const results = await exaMcpSearch({ query, objective: spec.objective, numResults: spec.numResults });
      return { results, ms: Date.now() - t0 };
    } catch (err) {
      if (attempt === 4) return { results: [], ms: Date.now() - t0, error: String(err.message ?? err) };
      await sleep(2000 * 2 ** attempt);
    }
  }
}

const rows = [];
for (const [i, e] of errands.entries()) {
  for (const arm of shuffled(ARMS)) {
    const { results, ms, error } = await search(e[arm]);
    const top = results.slice(0, 5).map((r) => ({ url: r.url, title: r.title, ...classify(r.url) }));
    rows.push({
      errand: e.id, jurisdiction: e.jurisdiction, arm, ms, error,
      n: top.length,
      legalText5: top.filter((r) => r.legalText).length,
      primaryLegal5: top.filter((r) => r.primaryLegal).length,
      official5: top.filter((r) => r.official).length,
      top1Official: !!top[0]?.official,
      top1LegalText: !!top[0]?.legalText,
      anchor3: anchorHit(results.slice(0, 3).flatMap((r) => r.highlights), e.anchors),
      top,
    });
    process.stdout.write(`${i + 1}/${errands.length} ${e.id} ${arm}: legal ${rows.at(-1).legalText5}/5 official ${rows.at(-1).official5}/5 anchor ${rows.at(-1).anchor3 ? "y" : "n"} ${ms}ms${error ? " ERR " + error : ""}\n`);
    await sleep(GAP_MS);
  }
}

mkdirSync(new URL("results/", here), { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
writeFileSync(new URL(`results/run-${stamp}.json`, here), JSON.stringify({ spec: { version: spec.version, objective: spec.objective, numResults: spec.numResults, via: "exa-mcp-keyless" }, at: new Date().toISOString(), rows }, null, 2));
console.log(`saved results/run-${stamp}.json`);
