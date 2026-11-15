#!/usr/bin/env node
// Baseline: ask Exa /answer the same dated questions the Then · Now · Next simulations answered, and check
// whether its answer states the amount that applied on the event date (gold from the official text of that
// date, taken from the latest simulation results). Also records whether it states today's amount instead.
// Usage: sh scripts/with-exa-key.sh node bench/exa_answer_baseline.mjs [--sets=core,heldout,sweep] [--limit=N]
import { readdirSync, readFileSync, writeFileSync } from "node:fs";

const KEY = process.env.EXA_API_KEY;
if (!KEY) throw new Error("EXA_API_KEY missing (run through scripts/with-exa-key.sh)");
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const sets = arg("sets", "core,heldout,sweep").split(",");
const limit = Number(arg("limit", "999"));
const dir = new URL("results/", import.meta.url);
// The most complete run of each set (partial --only runs are skipped), newest among equals.
const latest = (set) => readdirSync(dir).filter((f) => f.startsWith(`thennow-sim-${set}-`)).sort()
  .map((f) => ({ f, n: new Set(JSON.parse(readFileSync(new URL(f, dir), "utf8")).rows.map((r) => r.id)).size }))
  .reduce((a, b) => (b.n >= (a?.n ?? 0) ? b : a), null)?.f;

// Questions come from the simulation source so the wording is identical.
const src = readFileSync(new URL("thennow_sim.mjs", import.meta.url), "utf8");
const num = (t) => (t ?? "").replace(/[^\d.]/g, "").replace(/\.(?=\d{3}\b)/g, "").replace(/\.$/, "");
const states = (answer, amountText) => {
  if (!amountText || /^ERR|null/.test(amountText)) return null;
  if (/No compensation/.test(amountText)) return /no compensation/i.test(answer);
  if (/month|day|week|year/.test(amountText)) return answer.toLowerCase().includes(amountText.toLowerCase()) || /\b(1|one) month\b/i.test(answer) && /one month/.test(amountText);
  const n = num(amountText);
  const inAnswer = [...answer.matchAll(/(?:[$£€]|EUR\s?|USD\s?|GBP\s?)\s?(\d[\d,.]*)|(\d[\d,.]*)\s?(?:EUR|euros?|USD|GBP|dollars|pounds)/gi)].map((m) => num(m[1] ?? m[2]));
  return inAnswer.includes(n);
};

const rows = [];
let cost = 0;
for (const set of sets) {
  const f = latest(set);
  if (!f) continue;
  const sim = JSON.parse(readFileSync(new URL(f, dir), "utf8"));
  const seen = new Set();
  for (const r of sim.rows) {
    if (seen.has(r.id) || r.expect !== "answer" || !r.goldThen || /^ERR/.test(r.goldThen) || rows.length >= limit) continue;
    seen.add(r.id);
    // Recover the question text: the sweep builds it from a template, the others list it literally.
    const lit = src.match(new RegExp(`id: "${r.id.replace(/[-]/g, "\\-")}", q: "((?:[^"\\\\]|\\\\.)*)"`))?.[1];
    const d = r.id.match(/\d{4}-\d{2}-\d{2}$/)?.[0];
    const q = lit ?? (r.id.startsWith("sw-us-") ? `I was bumped from an oversold US domestic flight on ${d}; the substitute flight arrived 3 hours late. How much compensation?` : r.id.startsWith("sw-uk-") ? `I am 30 and worked in the UK on ${d}. What was the national living wage per hour?` : r.id.startsWith("sw-eu-") ? `My EU flight of 1,200 km was cancelled on ${d} without notice. How much EU261 compensation?` : null);
    if (!q) continue;
    const t0 = Date.now();
    const res = await fetch("https://api.exa.ai/answer", { method: "POST", headers: { "x-api-key": KEY, "content-type": "application/json" }, body: JSON.stringify({ query: q, text: false }) });
    const j = await res.json().catch(() => ({}));
    cost += j.costDollars?.total ?? 0;
    const answer = typeof j.answer === "string" ? j.answer : JSON.stringify(j.answer ?? j.error ?? "");
    const then = states(answer, r.goldThen);
    const now = r.goldNow !== r.goldThen ? states(answer, r.goldNow) : null;
    rows.push({ set, id: r.id, q, goldThen: r.goldThen, goldNow: r.goldNow, statesThen: then, statesNowInstead: now && !then, ours: r.thenOk, answer: answer.slice(0, 600), citations: (j.citations ?? []).map((c) => c.url).slice(0, 5), ms: Date.now() - t0 });
    console.log(`${r.id.padEnd(24)} exa ${then ? "✓" : "✗"}${now && !then ? " (today's amount)" : ""} | ours ${r.thenOk ? "✓" : "✗"} | gold ${r.goldThen}`);
  }
}
const scored = rows.filter((r) => r.statesThen !== null);
const changed = scored.filter((r) => r.goldNow && r.goldNow !== r.goldThen);
const summary = {
  questions: scored.length,
  exaAnswerCorrect: `${scored.filter((r) => r.statesThen).length}/${scored.length}`,
  oursCorrect: `${scored.filter((r) => r.ours).length}/${scored.length}`,
  whereTheAmountChanged: { questions: changed.length, exaCorrect: changed.filter((r) => r.statesThen).length, exaGaveTodaysAmount: changed.filter((r) => r.statesNowInstead).length, oursCorrect: changed.filter((r) => r.ours).length },
  exaCostUsd: Number(cost.toFixed(4)),
};
console.log(JSON.stringify(summary, null, 1));
writeFileSync(new URL(`exa-answer-baseline-${new Date().toISOString().replace(/[:.]/g, "-")}.json`, dir), JSON.stringify({ summary, rows }, null, 1));
