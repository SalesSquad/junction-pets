#!/usr/bin/env node
// Date-blind study, step 2: ask Exa /answer each dated question and classify the answer:
//   correct    states the amount in force on the date
//   date-blind states the latest amount instead (the trap)
//   next       states the amount of the following edition
//   other      another amount, or none
// With --ours, the same questions are answered by our deterministic point-in-time lookup (eCFR versioner on the
// date → amount clauses → the clause with the same wording), which needs no model because the clause is given.
// Resumable: finished ids are skipped. Spend goes to the shared ledger (bench/results/exa-spend.jsonl).
// Usage: node --experimental-strip-types bench/exa_study/run_answers.mjs bench/exa_study/questions.jsonl [--limit=N] [--ours] [--concurrency=5]
import { appendFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

const file = process.argv[2];
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const limit = Number(arg("limit", "100000"));
const conc = Number(arg("concurrency", "5"));
const ours = process.argv.includes("--ours");
const budget = Number(process.env.EXA_BUDGET_USD ?? 30);
const ledger = new URL("../results/exa-spend.jsonl", import.meta.url);
const spent = () => (existsSync(ledger) ? readFileSync(ledger, "utf8").split("\n").filter(Boolean).reduce((a, l) => a + (JSON.parse(l).usd ?? 0), 0) : 0);
const outFile = file.replace(/\.jsonl$/, ours ? ".ours.jsonl" : ".exa.jsonl");
const done = new Map(existsSync(outFile) ? readFileSync(outFile, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.id, j]; }) : []);
const qs = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).slice(0, limit);
const num = (t) => String(t).replace(/[^\d.]/g, "").replace(/\.$/, "").replace(/\.00$/, "");
const amountsIn = (text) => [...String(text).matchAll(/\$\s?(\d[\d,]*(?:\.\d+)?)(\s?(?:million|billion))?/gi)].map((m) => (m[2] ? String(Number(m[1].replace(/,/g, "")) * (/b/i.test(m[2]) ? 1e9 : 1e6)) : num(m[1])));
const classify = (answer, q) => {
  const xs = amountsIn(answer);
  return xs.includes(num(q.gold)) ? "correct" : xs.includes(num(q.latest)) ? "date-blind" : xs.includes(num(q.next)) ? "next" : xs.length ? "other" : "none";
};

let next = 0;
if (ours) {
  const { lawOn } = await import("../../src/warrant/pointInTime.ts");
  const { amountClauses, template } = await import("../../src/timetravel/timetravel.ts");
  const { extractQuantities } = await import("../../src/warrant/lanes.ts");
  const memo = new Map();
  for (const q of qs) {
    if (done.has(q.id)) continue;
    const key = `${q.title}|${q.section}|${q.date}`;
    let cs = memo.get(key);
    if (!cs) {
      try {
        const law = await lawOn({ source: "ecfr", title: q.title, part: q.part, section: q.section }, q.date);
        cs = amountClauses(law.text).map((c) => c.split(" … ").at(-1));
      } catch (e) {
        cs = { error: e.message.slice(0, 80) };
      }
      memo.set(key, cs);
      await new Promise((r) => setTimeout(r, 400)); // about two requests a second: eCFR rate-limits
    }
    let outcome = "no-text", answer = null;
    if (Array.isArray(cs)) {
      const c = cs.find((x) => template(x) === q.template);
      answer = c ? extractQuantities(c).filter((x) => x.kind === "money").map((x) => x.text) : null;
      outcome = !c ? "clause-not-found" : answer.map(num).includes(num(q.gold)) ? "correct" : answer.map(num).includes(num(q.latest)) ? "date-blind" : "other";
    }
    const row = { id: q.id, date: q.date, gold: q.gold, latest: q.latest, outcome, answer, error: cs.error };
    done.set(q.id, row);
    appendFileSync(outFile, JSON.stringify(row) + "\n");
    if (done.size % 100 === 0) console.error(`${done.size}/${qs.length}`);
  }
} else {
  const key = process.env.EXA_API_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.exa", "-w"], { encoding: "utf8" }).trim();
  await Promise.all(Array.from({ length: conc }, async () => {
    while (next < qs.length) {
      const q = qs[next++];
      if (done.has(q.id)) continue;
      if (spent() >= budget) { console.error("Exa budget reached; stopping"); return; }
      let j = {};
      for (let i = 0; i < 3; i++) {
        const res = await fetch("https://api.exa.ai/answer", { method: "POST", headers: { "x-api-key": key, "content-type": "application/json" }, body: JSON.stringify({ query: q.question, text: false }) }).catch(() => null);
        j = res ? await res.json().catch(() => ({})) : {};
        if (res?.ok) break;
        await new Promise((r) => setTimeout(r, 1500 * 2 ** i));
      }
      const answer = typeof j.answer === "string" ? j.answer : JSON.stringify(j.answer ?? j.error ?? "");
      appendFileSync(ledger, JSON.stringify({ at: new Date().toISOString(), tag: "dateblind-study", cmd: "answer", usd: j.costDollars?.total ?? 0, q: q.id }) + "\n");
      const row = { id: q.id, date: q.date, title: q.title, gold: q.gold, latest: q.latest, outcome: classify(answer, q), answer: answer.slice(0, 500), citations: (j.citations ?? []).map((c) => c.url).slice(0, 4) };
      done.set(q.id, row);
      appendFileSync(outFile, JSON.stringify(row) + "\n");
      if (done.size % 100 === 0) console.error(`${done.size}/${qs.length} spent $${spent().toFixed(2)}`);
    }
  }));
}
const rows = qs.map((q) => done.get(q.id)).filter(Boolean);
const count = (f) => rows.filter(f).length;
const pct = (n) => `${n}/${rows.length} (${((100 * n) / Math.max(1, rows.length)).toFixed(1)} %)`;
const byYear = {};
for (const r of rows) { const y = r.date.slice(0, 4); byYear[y] ??= { n: 0, correct: 0, dateBlind: 0 }; byYear[y].n++; byYear[y].correct += r.outcome === "correct"; byYear[y].dateBlind += r.outcome === "date-blind"; }
const summary = { system: ours ? "ours (eCFR point-in-time lookup)" : "Exa /answer", questions: rows.length, correct: pct(count((r) => r.outcome === "correct")), dateBlind: pct(count((r) => r.outcome === "date-blind")), nextEdition: pct(count((r) => r.outcome === "next")), other: pct(count((r) => !["correct", "date-blind", "next"].includes(r.outcome))), byYear, exaSpentUsd: Number(spent().toFixed(3)) };
console.log(JSON.stringify(summary, null, 1));
writeFileSync(outFile.replace(/\.jsonl$/, ".summary.json"), JSON.stringify(summary, null, 1));
