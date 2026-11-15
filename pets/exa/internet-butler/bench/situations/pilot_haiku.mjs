#!/usr/bin/env node
// TimeLaw-Situations pilot generator (Mac, no GPU): the same prompts as gpu/generate_situations.py, written by
// Claude Haiku instead of an open model, to check the pipeline end to end before the GPU run. Output has the
// same shape as the GPU output (generatorRecovers from a blind second call).
// Usage: node bench/situations/pilot_haiku.mjs bench/situations/groups.jsonl bench/situations/pilot.jsonl [--per-group=1] [--max=60]
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

const [groupsFile, outFile] = process.argv.slice(2);
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const perGroup = Number(arg("per-group", "1"));
const max = Number(arg("max", "60"));
const key = process.env.ANTHROPIC_API_KEY || execFileSync("security", ["find-generic-password", "-a", "anthropic", "-s", "com.mikaelervamaa.haiku-background-intelligence", "-w"], { encoding: "utf8" }).trim();
let seed = 11;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
const own = (c) => c.split(" … ").at(-1);
const fit = (c, n = 700) => { if (c.length <= n) return c; const o = own(c); return o.length >= n - 40 ? o.slice(0, n) : `${c.slice(0, n - o.length - 3).trimEnd()} … ${o}`; };
const listing = (g) => g.clauses.map((c, i) => `[${i}] ${fit(c)}`).join("\n");
const lang = () => { const r = rand(); return r < 0.6 ? "English" : r < 0.8 ? "Finnish" : "German"; };

async function ask(prompt, maxTokens = 4000) {
  for (let i = 0; i < 4; i++) {
    const res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" }, body: JSON.stringify({ model: "claude-haiku-5-5", max_tokens: maxTokens, messages: [{ role: "user", content: prompt }] }) });
    if (res.ok) {
      const d = await res.json();
      return d.content.filter((c) => c.type === "text").map((c) => c.text).join("");
    }
    await new Promise((r) => setTimeout(r, 1500 * 2 ** i));
  }
  return "";
}
const json = (t, k) => { try { return JSON.parse(t.match(/\{[^]*\}/)?.[0] ?? "null")?.[k]; } catch { return undefined; } };

const groups = readFileSync(groupsFile, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const items = [];
for (const g of groups) {
  const distinct = [...new Map(g.clauses.map((c, i) => [own(c), i])).values()];
  for (const t of distinct.sort(() => rand() - 0.5).slice(0, perGroup)) items.push({ g, target: t, lang: lang() });
}
const todo = items.slice(0, max);
const out = [];
let next = 0;
await Promise.all(Array.from({ length: 6 }, async () => {
  while (next < todo.length) {
    const it = todo[next++];
    const { g } = it;
    const message = json(await ask(`These are the amount-bearing clauses of ${g.title || JSON.stringify(g.ref)} as in force on ${g.date}:\n\n${listing(g)}\n\nWrite ONE short, realistic message (2-4 sentences, in ${it.lang}) from a person whose case is governed by clause [${it.target}] and by no other clause in the list.\nRules:\n- The person asks what amount, fee, penalty, rate or compensation applied to them.\n- State the date ${g.date} (as YYYY-MM-DD) as the day the event happened.\n- State every fact that separates clause [${it.target}] from the others (for example: how late, how far, how old, which kind of party or account, first or repeated, which statute section).\n- Do NOT state or hint at the amount. Do NOT copy the clause wording; write like a real person.\nAnswer with JSON only: {"message": "..."}`), "message");
    if (process.env.DEBUG) console.error("GEN", JSON.stringify(message)?.slice(0, 200));
    if (typeof message !== "string" || message.length < 20) continue;
    const nums = (own(g.clauses[it.target]).match(/\d[\d,.]*/g) ?? []).map((n) => n.replace(/,/g, "")).filter((n) => n.length >= 3 && !g.date.includes(n));
    if (nums.some((n) => message.replace(/,/g, "").includes(n))) continue; // states the amount: not a test
    const back = json(await ask(`Clauses of ${g.title || JSON.stringify(g.ref)} as in force on ${g.date}:\n\n${listing(g)}\n\nA person writes: "${message}"\n\nWhich single clause sets the amount that applies to this person? Answer with JSON only: {"clause": <number>}`, 3000), "clause");
    out.push({ gid: g.gid, jurisdiction: g.jurisdiction, ref: g.ref, also: g.also, date: g.date, url: g.url, lang: it.lang, question: message, target: it.target, clauses: g.clauses, generatorRecovers: back === it.target, generator: "claude-haiku-5-5" });
  }
}));
writeFileSync(outFile, out.map((x) => JSON.stringify(x)).join("\n") + "\n");
console.log(JSON.stringify({ items: out.length, selfConsistent: out.filter((x) => x.generatorRecovers).length }));
