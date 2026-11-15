#!/usr/bin/env node
// Jev (TypeSafe) pointwise P(yes) for the Finnish groups of one split. The owner asked for TypeSafe, DeepSeek or
// Haiku instead of Nemotron in Finnish. Same judge call and question as bench/situations/tournament.mjs; cached
// per (judge, situation, clause) in OUT, so a rerun makes no repeat calls. Jev only: no Luna calls.
// Key: TYPESAFE_API_KEY, else ~/.config/typesafe/env; never printed.
// Usage: node --experimental-strip-types bench/situations/listwise/teachers/fi_jev.mjs bench/datasets/out/training/valid.jsonl runs/teachers/valid_fi.jev.jsonl
import { readFileSync, existsSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { CLAUSE_QUESTION } from "../../../../src/timetravel/timetravel.ts";
import { typesafeJev } from "../../../../src/decide/decide.ts";

const [file, out] = process.argv.slice(2);
const tsKey = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
const { TypeSafeClient } = await import("@typesafe-ai/sdk");
const ts = new TypeSafeClient({ apiKey: tsKey, defaultModel: "jev-1.14.0" });
const jev = typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) });
const items = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).filter((x) => x.lang === "Finnish");
const cache = new Set(existsSync(out) ? readFileSync(out, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l).k) : []);
const jobs = [];
for (const it of items) for (const c of it.clauses) {
  const k = `jev|${it.question}|${c}`;
  if (!cache.has(k)) { cache.add(k); jobs.push([k, it.question, c]); }
}
console.log(JSON.stringify({ items: items.length, todo: jobs.length }));
let next = 0, done = 0;
await Promise.all(Array.from({ length: 6 }, async () => {
  while (next < jobs.length) {
    const [k, situation, clause] = jobs[next++];
    const t0 = Date.now();
    let r;
    for (let i = 0; i < 4; i++) {
      try { r = await jev.decide({ situation, clause }, [CLAUSE_QUESTION]); break; } catch (e) { if (i === 3) throw e; await new Promise((s) => setTimeout(s, 1000 * 2 ** i)); }
    }
    appendFileSync(out, JSON.stringify({ k, p: r.answers[0]?.p ?? 0, ms: Date.now() - t0, tokens: r.usage?.inputTokens ?? 0 }) + "\n");
    if (++done % 100 === 0) console.log(JSON.stringify({ done }));
  }
}));
console.log(JSON.stringify({ done: "all", calls: done }));
