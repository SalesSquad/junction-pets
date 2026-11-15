#!/usr/bin/env node
// Fill in answer-lane evidence (plain question, Exa) for errands that run2 has no data for.
// Writes bench/results/evidence-extra.json. Keyless MCP unless EXA_API_KEY is set.
import { readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { exaMcpSearch } from "../relay/exa-mcp.mjs";
const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const run = JSON.parse(readFileSync(new URL(`results/${readdirSync(new URL("results/", here)).filter((f) => f.startsWith("run2-")).sort().at(-1)}`, here), "utf8"));
const outFile = new URL("results/evidence-extra.json", here);
const out = existsSync(outFile) ? JSON.parse(readFileSync(outFile, "utf8")) : {};
const have = (id) => run.rows.some((r) => r.errand === id && !r.error && r.top?.some((t) => t.highlights?.length)) || out[id];
for (const e of spec.errands.filter((e) => !have(e.id))) {
  try {
    const top = await exaMcpSearch({ query: e.question, objective: "Find pages that answer this question with the specific rule, amount or deadline that applies.", numResults: 8 });
    out[e.id] = { at: new Date().toISOString(), top };
    console.log(`${e.id}: ${top.length} results`);
  } catch (err) {
    console.log(`${e.id}: ${String(err.message).slice(0, 120)}`);
    if (/429|rate/i.test(err.message)) break;
  }
}
writeFileSync(outFile, JSON.stringify(out, null, 2));
