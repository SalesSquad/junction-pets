#!/usr/bin/env node
// Exa from the command line, with a spend ledger. The key is read from the macOS Keychain for this process
// only and is never printed. Every call appends its cost to bench/results/exa-spend.jsonl; calls are refused
// once the ledger reaches the budget (EXA_BUDGET_USD, default 30).
//
//   node scripts/exa.mjs search "query" [--n=8] [--domains=a.com,b.org] [--text] [--type=auto|neural|keyword] [--since=2026-01-01]
//   node scripts/exa.mjs answer "question"
//   node scripts/exa.mjs contents https://url1 https://url2 [--chars=6000]
//   node scripts/exa.mjs code "how to do X with library Y"        (Exa MCP web_search_exa)
//   node scripts/exa.mjs mcp list | mcp <tool> '{"arg":"value"}'  (any Exa MCP tool)
//   node scripts/exa.mjs spend
import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";

const ledger = new URL("../bench/results/exa-spend.jsonl", import.meta.url);
const budget = Number(process.env.EXA_BUDGET_USD ?? 30);
const spent = () => (existsSync(ledger) ? readFileSync(ledger, "utf8").split("\n").filter(Boolean).reduce((a, l) => a + (JSON.parse(l).usd ?? 0), 0) : 0);
const [cmd, ...rest] = process.argv.slice(2);
const flags = Object.fromEntries(rest.filter((a) => a.startsWith("--")).map((a) => { const [k, v] = a.slice(2).split("="); return [k, v ?? true]; }));
const words = rest.filter((a) => !a.startsWith("--"));
const tag = process.env.EXA_TAG ?? "adhoc";

if (cmd === "spend") {
  console.log(JSON.stringify({ spentUsd: Number(spent().toFixed(4)), budgetUsd: budget }));
  process.exit(0);
}
if (spent() >= budget) {
  console.error(`Exa budget reached: ${spent().toFixed(2)} of ${budget} USD. Not calling.`);
  process.exit(2);
}
const key = process.env.EXA_API_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.exa", "-w"], { encoding: "utf8" }).trim();
if (cmd === "code" || cmd === "mcp") {
  // Exa's hosted MCP with the account key in the Authorization header (never in the URL).
  //   code "query"                      → web_search_exa (clean content, good for docs and code)
  //   mcp <tool> '{"json":"arguments"}' → any MCP tool; `mcp list` lists the tools
  const call = async (method, params, id) => {
    const r = await fetch("https://mcp.exa.ai/mcp", { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", authorization: `Bearer ${key}` }, body: JSON.stringify({ jsonrpc: "2.0", id, method, params }) });
    const t = await r.text();
    const line = t.split("\n").find((l) => l.startsWith("data:"));
    return JSON.parse(line ? line.slice(5) : t);
  };
  if (cmd === "mcp" && words[0] === "list") {
    const out = await call("tools/list", {}, 1);
    for (const t of out.result?.tools ?? []) console.log(`${t.name}: ${(t.description ?? "").split("\n")[0].slice(0, 160)}`);
    process.exit(0);
  }
  const name = cmd === "code" ? "web_search_exa" : words[0];
  const args = cmd === "code" ? { query: words.join(" "), numResults: Number(flags.n ?? 5) } : JSON.parse(words[1] ?? "{}");
  const out = await call("tools/call", { name, arguments: args }, 1);
  console.log(out.result?.content?.map((c) => c.text).join("\n").slice(0, Number(flags.chars ?? 16000)) ?? JSON.stringify(out).slice(0, 2000));
  // The MCP does not report cost; one cent per call is recorded as an estimate.
  appendFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), tag, cmd: `mcp:${name}`, usd: 0.01, estimate: true, q: JSON.stringify(args).slice(0, 120) }) + "\n");
  process.exit(0);
}
const post = async (path, body) => {
  const r = await fetch(`https://api.exa.ai${path}`, { method: "POST", headers: { "x-api-key": key, "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`Exa ${path} ${r.status}: ${JSON.stringify(j).slice(0, 300)}`);
  mkdirSync(new URL("../bench/results/", import.meta.url), { recursive: true });
  appendFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), tag, cmd, usd: j.costDollars?.total ?? 0, q: String(body.query ?? body.urls ?? "").slice(0, 120) }) + "\n");
  return j;
};
if (cmd === "search") {
  const j = await post("/search", {
    query: words.join(" "), type: flags.type ?? "auto", numResults: Number(flags.n ?? 8),
    ...(flags.domains ? { includeDomains: String(flags.domains).split(",") } : {}),
    ...(flags.since ? { startPublishedDate: `${flags.since}T00:00:00.000Z` } : {}),
    contents: flags.text ? { text: { maxCharacters: Number(flags.chars ?? 3000) } } : { highlights: { numSentences: 3, highlightsPerUrl: 3 } },
  });
  for (const r of j.results ?? []) console.log(`\n## ${r.title ?? ""}\n${r.url}${r.publishedDate ? `  (${r.publishedDate.slice(0, 10)})` : ""}\n${flags.text ? (r.text ?? "").slice(0, Number(flags.chars ?? 3000)) : (r.highlights ?? []).join(" … ")}`);
  console.log(`\n[cost $${j.costDollars?.total ?? 0}; spent $${spent().toFixed(3)} of $${budget}]`);
} else if (cmd === "answer") {
  const j = await post("/answer", { query: words.join(" "), text: false });
  console.log(typeof j.answer === "string" ? j.answer : JSON.stringify(j.answer));
  console.log("\nSources:\n" + (j.citations ?? []).map((c) => `- ${c.title ?? ""} ${c.url}`).join("\n"));
  console.log(`\n[cost $${j.costDollars?.total ?? 0}; spent $${spent().toFixed(3)} of $${budget}]`);
} else if (cmd === "contents") {
  const j = await post("/contents", { urls: words, text: { maxCharacters: Number(flags.chars ?? 6000) } });
  for (const r of j.results ?? []) console.log(`\n## ${r.title ?? ""}\n${r.url}\n${(r.text ?? "").slice(0, Number(flags.chars ?? 6000))}`);
  console.log(`\n[cost $${j.costDollars?.total ?? 0}; spent $${spent().toFixed(3)} of $${budget}]`);
} else {
  console.error("usage: exa.mjs search|answer|contents|code|spend …");
  process.exit(1);
}
