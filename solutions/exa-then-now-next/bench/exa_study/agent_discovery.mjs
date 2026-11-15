#!/usr/bin/env node
// Discovery study, arm 2: Exa Agent with an output schema, on the same situations as the search arm
// (bench/exa_study/discovery.jsonl), 100 per language, US provisions. One situation per run.
// The agent must return the CFR title, part and section and the amount in force on the event date; both
// are checked by code against the dataset (section id; amount of the target clause in that edition).
// Usage: node --experimental-strip-types bench/exa_study/agent_discovery.mjs [--per-lang=100] [--effort=minimal]
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { extractQuantities } from "../../src/warrant/lanes.ts";

const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const perLang = Number(arg("per-lang", "100"));
const effort = arg("effort", "minimal");
const budget = Number(process.env.EXA_BUDGET_USD ?? 30);
const ledger = new URL("../results/exa-spend.jsonl", import.meta.url);
const spent = () => (existsSync(ledger) ? readFileSync(ledger, "utf8").split("\n").filter(Boolean).reduce((a, l) => a + (JSON.parse(l).usd ?? 0), 0) : 0);
const key = process.env.EXA_API_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.exa", "-w"], { encoding: "utf8" }).trim();
const outFile = "bench/exa_study/agent_discovery.jsonl";
const done = new Map(existsSync(outFile) ? readFileSync(outFile, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.key, j]; }) : []);

// The same items the search arm saw (one base situation per provision), US only, stratified by language.
const searchRows = new Map(readFileSync("bench/exa_study/discovery.jsonl", "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.key, j]; }));
const seen = new Set();
const items = readFileSync("bench/exa_study/all-situations.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l))
  .filter((x) => !x.attack && x.ref?.source === "ecfr" && !seen.has(x.provision) && seen.add(x.provision))
  .map((x) => ({ ...x, key: `${x.gid}|${x.question.slice(0, 80)}` })).filter((x) => searchRows.has(x.key));
let seed = 7;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const sample = ["English", "Finnish", "German"].flatMap((l) => items.filter((x) => x.lang === l).sort(() => rnd() - 0.5).slice(0, perLang));

const mcp = async (args) => {
  const r = await fetch("https://mcp.exa.ai/mcp", { method: "POST", headers: { "content-type": "application/json", accept: "application/json, text/event-stream", authorization: `Bearer ${key}` }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "agent_run", arguments: args } }) });
  const t = await r.text();
  const line = t.split("\n").find((l) => l.startsWith("data:"));
  const j = JSON.parse(line ? line.slice(5) : t);
  const text = j.result?.content?.map((c) => c.text).join("") ?? "";
  try { return JSON.parse(text); } catch { return { status: "error", raw: text.slice(0, 300) || JSON.stringify(j).slice(0, 300) }; }
};
const schema = { type: "object", required: ["cfr_title", "cfr_section"], properties: { cfr_title: { type: "integer" }, cfr_part: { type: "string" }, cfr_section: { type: "string", description: "for example 250.5" }, source_url: { type: "string" }, amount_on_date: { type: ["string", "null"], description: "the amount in force on the event date, with its currency sign" } } };
const digits = (s) => String(s ?? "").replace(/[^\d.]/g, "").replace(/\.00$/, "").replace(/\.$/, "");
// Section and part hits from the agent's structured answer. "§ 250.5(a)(2)" is section 250.5; "Part 250" and
// "14 CFR Part 250" are part 250 (the first version compared raw strings and missed 9 correct sections).
const hits = (s, ref) => {
  const sec = String(s?.cfr_section ?? "").replace(/^§+\s*/, "").replace(/\s*\(.*$/, "").trim();
  const partAns = String(s?.cfr_part ?? "").match(/part\s*(\d+[A-Za-z]?)/i)?.[1] ?? String(s?.cfr_part ?? "").match(/\d+[A-Za-z]?/)?.[0] ?? sec.split(".")[0];
  const titleOk = Number(s?.cfr_title) === Number(ref.title);
  return { section: titleOk && sec.toLowerCase() === String(ref.section).toLowerCase(), part: titleOk && (String(partAns ?? "").toLowerCase() === String(ref.part).toLowerCase() || sec.split(".")[0].toLowerCase() === String(ref.part).toLowerCase()) };
};

let next = 0;
await Promise.all(Array.from({ length: 4 }, async () => {
  while (next < sample.length) {
    const it = sample[next++];
    if (done.has(it.key)) continue;
    if (spent() >= budget) return;
    const t0 = Date.now();
    let res = await mcp({ query: `A person writes: "${it.question}" Find the official US federal regulation section (Code of Federal Regulations) that sets the money amount for this person's situation, as in force on ${it.date}, and the amount that applied on that date.`, systemPrompt: "Identify the governing CFR section. Prefer ecfr.gov and govinfo.gov. Use the law as in force on the event date, not today's text.", outputSchema: schema, effort });
    for (let i = 0; i < 20 && res.status && !["completed", "failed", "error", "cancelled"].includes(res.status) && res.id; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      res = await mcp({ runId: res.id });
    }
    const s = res.output?.structured ?? {};
    const own = it.clauses[it.target].split(" … ").at(-1);
    const goldAmount = extractQuantities(own).find((q) => q.kind === "money")?.text ?? null;
    const cost = res.costDollars?.total ?? 0;
    appendFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), tag: "agent-discovery", cmd: "agent_run", usd: cost, q: it.gid }) + "\n");
    const row = {
      key: it.key, gid: it.gid, lang: it.lang, status: res.status ?? "error", ms: Date.now() - t0, cost,
      ...hits(s, it.ref),
      amount: goldAmount ? digits(s.amount_on_date) === digits(goldAmount) : null, goldAmount, answer: s,
      pinnedUrl: /ecfr\.gov\/on\/\d{4}-\d{2}-\d{2}|govinfo\.gov/.test(String(s.source_url ?? "")),
      confidence: (res.output?.grounding ?? []).find((g) => g.field === "structured.cfr_section")?.confidence ?? null,
      searchSection: searchRows.get(it.key).section, searchPart: searchRows.get(it.key).part,
    };
    done.set(it.key, row);
    appendFileSync(outFile, JSON.stringify(row) + "\n");
    if (done.size % 25 === 0) console.error(`${done.size}/${sample.length} spent $${spent().toFixed(2)}`);
  }
}));
// Stored rows are rescored from their stored answers, so a scoring fix needs no new agent runs.
for (const x of sample) { const row = done.get(x.key); if (row) Object.assign(row, hits(row.answer, x.ref)); }
const rows = sample.map((x) => done.get(x.key)).filter(Boolean);
writeFileSync(outFile, rows.map((r) => JSON.stringify(r)).join("\n") + "\n");
const pct = (rs, f) => `${rs.filter(f).length}/${rs.length} (${((100 * rs.filter(f).length) / Math.max(1, rs.length)).toFixed(1)} %)`;
const block = (rs) => ({ n: rs.length, agentSection: pct(rs, (r) => r.section), agentPart: pct(rs, (r) => r.part), searchSection: pct(rs, (r) => r.searchSection), searchPart: pct(rs, (r) => r.searchPart), amountOnDate: pct(rs.filter((r) => r.amount !== null), (r) => r.amount), amountGivenSection: pct(rs.filter((r) => r.section && r.amount !== null), (r) => r.amount) });
const summary = { effort, ...block(rows), byLanguage: Object.fromEntries(["English", "Finnish", "German"].map((l) => [l, block(rows.filter((r) => r.lang === l))])), highConfidence: block(rows.filter((r) => r.confidence === "high")), completed: pct(rows, (r) => r.status === "completed"), medianSeconds: rows.map((r) => r.ms).sort((a, b) => a - b)[Math.floor(rows.length / 2)] / 1000, costPerRunUsd: Number((rows.reduce((a, r) => a + r.cost, 0) / Math.max(1, rows.length)).toFixed(4)), exaSpentUsd: Number(spent().toFixed(3)) };
console.log(JSON.stringify(summary, null, 1));
writeFileSync("bench/exa_study/agent_discovery.summary.json", JSON.stringify(summary, null, 1));
