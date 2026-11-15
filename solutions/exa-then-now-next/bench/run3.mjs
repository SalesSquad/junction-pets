#!/usr/bin/env node
// Benchmark v3: the two-lane compiler on the pre-registered errands.
// Measures whether the grounded extraction recovers the decisive quantity in the reference premise,
// whether the authority lane returns legal text, and how triangulation resolves.
// Usage: node bench/run3.mjs [--from N] [--limit N]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { exaMcpFetch, exaMcpSearch } from "../relay/exa-mcp.mjs";
import { compileTwoLane } from "../src/warrant/compile.ts";
import { extractQuantities, sameQuantity } from "../src/warrant/lanes.ts";

const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 ? Number(process.argv[i + 1]) : d; };
const errands = spec.errands.slice(arg("--from", 0), arg("--from", 0) + arg("--limit", spec.errands.length));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let calls = 0;
const throttled = (fn) => async (...a) => { await sleep(calls++ ? 1500 : 0); return fn(...a); };
const search = throttled(async (query, objective) => exaMcpSearch({ query, objective, numResults: 5 }));
const fetchPage = throttled(async (url) => exaMcpFetch({ urls: [url] }));

// The reference quantity: every quantity in the expert premise that also appears in the anchors.
const referenceQuantities = (e) => {
  const anchorQs = e.anchors.flat().flatMap((a) => extractQuantities(a));
  const premiseQs = extractQuantities(e.premise);
  return premiseQs.filter((p) => anchorQs.some((a) => sameQuantity(a, p)) || e.anchors.flat().some((a) => p.text.includes(a)));
};

const rows = [];
for (const e of errands) {
  let r, error;
  try {
    r = await compileTwoLane(e.question, search, fetchPage);
  } catch (err) {
    error = String(err.message ?? err);
  }
  const refs = referenceQuantities(e);
  const extracted = r?.extraction.quantity;
  const correct = extracted ? refs.some((q) => sameQuantity(q, extracted)) : false;
  rows.push({
    errand: e.id, jurisdiction: e.jurisdiction, error,
    extracted: extracted?.text ?? null, reference: refs.map((q) => q.text), extractionCorrect: correct,
    support: r?.extraction.support ?? 0, instrument: r?.extraction.instrument ?? null,
    citationQuery: r?.citationQuery ?? null, legalUrls: r?.legalUrls.length ?? 0,
    triangulation: r?.triangulation.status ?? null, outcome: r?.outcome ?? null, reasons: r?.reasons ?? [],
    ruleUrl: r?.rule?.source.url ?? null, ruleQuote: r?.rule?.source.quote?.slice(0, 300) ?? null,
  });
  const x = rows.at(-1);
  console.log(`${e.id}: extracted ${x.extracted ?? "-"} (${x.extractionCorrect ? "correct" : "wrong/none"}), legal ${x.legalUrls}, triangulation ${x.triangulation ?? "-"} -> ${x.outcome ?? "ERR " + error}`);
}
mkdirSync(new URL("results/", here), { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
writeFileSync(new URL(`results/run3-${stamp}.json`, here), JSON.stringify({ at: new Date().toISOString(), via: "exa-mcp-keyless", rows }, null, 2));
const ok = rows.filter((r) => !r.error);
const share = (f) => `${ok.filter(f).length}/${ok.length}`;
console.log(`\nerrands ${rows.length}, errors ${rows.length - ok.length}`);
console.log(`extraction correct ${share((r) => r.extractionCorrect)} · legal text in authority lane ${share((r) => r.legalUrls > 0)} · triangulation agree ${share((r) => r.triangulation === "agree")} · disagree ${share((r) => r.triangulation === "disagree")} · GROUNDED ${share((r) => r.outcome === "GROUNDED")}`);
console.log(`GROUNDED with a wrong extraction (false grounding): ${share((r) => r.outcome === "GROUNDED" && !r.extractionCorrect)}`);
console.log(`saved results/run3-${stamp}.json`);
