#!/usr/bin/env node
// Benchmark v2: adds model-written citation queries (English and the jurisdiction's own language)
// to the three v1 arms, and stores highlights so a judge swarm can label semantic support.
// Arms: keywords, question, citation (hand-written), auto_en (Haiku from the question only),
//       auto_native (Haiku, jurisdiction language; only where that is not English).
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { exaMcpSearch } from "../relay/exa-mcp.mjs";
import { classify, anchorHit } from "./classify.mjs";

const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const auto = Object.fromEntries(
  [0, 1, 2].flatMap((i) => JSON.parse(readFileSync(new URL(`haiku/qw_out${i}.json`, here), "utf8"))).map((x) => [x.id, x]),
);
const GAP_MS = 1200;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let seed = 20261115;
const rand = () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const shuffled = (xs) => xs.map((x) => [rand(), x]).sort((a, b) => a[0] - b[0]).map(([, x]) => x);

async function search(query) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const t0 = Date.now();
    try {
      return { results: await exaMcpSearch({ query, objective: spec.objective, numResults: spec.numResults }), ms: Date.now() - t0 };
    } catch (err) {
      if (attempt === 4) return { results: [], ms: Date.now() - t0, error: String(err.message ?? err) };
      await sleep(2000 * 2 ** attempt);
    }
  }
}

const rows = [];
for (const [i, e] of spec.errands.entries()) {
  const a = auto[e.id];
  if (!a) throw new Error(`missing auto query for ${e.id}`);
  const arms = { keywords: e.keywords, question: e.question, citation: e.citation, auto_en: a.cite_en };
  if (a.native_language && a.native_language !== "en") arms.auto_native = a.cite_native;
  for (const arm of shuffled(Object.keys(arms))) {
    const { results, ms, error } = await search(arms[arm]);
    const top = results.slice(0, 5).map((r) => ({
      url: r.url,
      title: r.title,
      ...classify(r.url),
      highlights: r.highlights.slice(0, 3).map((h) => (h.length > 900 ? `${h.slice(0, 900)}…` : h)),
    }));
    rows.push({
      errand: e.id, jurisdiction: e.jurisdiction, arm, query: arms[arm], ms, error, n: top.length,
      legalText5: top.filter((r) => r.legalText).length,
      official5: top.filter((r) => r.official).length,
      top1LegalText: !!top[0]?.legalText,
      anchor3: anchorHit(results.slice(0, 3).flatMap((r) => r.highlights), e.anchors),
      top,
    });
    process.stdout.write(`${i + 1}/${spec.errands.length} ${e.id} ${arm}: legal ${rows.at(-1).legalText5}/5 anchor ${rows.at(-1).anchor3 ? "y" : "n"} ${ms}ms${error ? " ERR " + error : ""}\n`);
    await sleep(GAP_MS);
  }
}
mkdirSync(new URL("results/", here), { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
writeFileSync(new URL(`results/run2-${stamp}.json`, here), JSON.stringify({ spec: { version: 2, objective: spec.objective, numResults: spec.numResults, via: "exa-mcp-keyless" }, at: new Date().toISOString(), rows }, null, 2));
console.log(`saved results/run2-${stamp}.json`);
