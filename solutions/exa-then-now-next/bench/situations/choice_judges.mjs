#!/usr/bin/env node
// Listwise cloud judges: Jev and Luna answer ONE choice question per situation with every sibling clause as an
// option (their Choice primitive), instead of one yes/no per clause. Output is in the tournament's student
// cache format so `tournament.mjs --student=jevChoice:…,lunaChoice:…` scores them next to everything else.
// Usage: node --experimental-strip-types bench/situations/choice_judges.mjs test.jsonl [--judges=jev,luna]
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { typesafeJev, openaiDecisions } from "../../src/decide/decide.ts";

const file = process.argv[2];
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const LETTERS = "ABCDEFGHIJKLMNOP";
const tsKey = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
const oaKey = readFileSync(`${homedir()}/.config/openai/factory-decisions.env`, "utf8").match(/^OPENAI_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
const { TypeSafeClient } = await import("@typesafe-ai/sdk");
const ts = new TypeSafeClient({ apiKey: tsKey, defaultModel: "jev-1.14.0" });
const JUDGES = { jev: typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) }), luna: openaiDecisions({ apiKey: oaKey, model: "gpt-6-luna" }) };
const items = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).filter((it) => it.clauses.length <= LETTERS.length);
for (const name of arg("judges", "jev,luna").split(",")) {
  const out = file.replace(/\.jsonl$/, `.${name}-choice.judgments.jsonl`);
  const done = new Set(existsSync(out) ? readFileSync(out, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l).k) : []);
  const todo = items.filter((it) => !done.has(`student|${it.question}|${it.clauses[0]}`));
  let next = 0, ok = 0, n = 0, failed = 0;
  await Promise.all(Array.from({ length: 6 }, async () => {
    while (next < todo.length) {
      const it = todo[next++];
      const options = Object.fromEntries(it.clauses.map((c, i) => [LETTERS[i], c]));
      let r;
      for (let i = 0; i < 4 && !r; i++) {
        try { r = await JUDGES[name].decide({ situation: it.question }, [{ kind: "choice", name: "tier", instructions: "Which option sets the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)?", options }]); } catch (e) { if (i === 3) { failed++; } else await new Promise((s) => setTimeout(s, 1000 * 2 ** i)); }
      }
      const a = r?.answers?.[0];
      if (!a || a.refused) {
        // A refusal or a failed call is an abstention: uniform probabilities, flagged.
        failed++;
        if (process.argv.includes("--fill-abstain")) appendFileSync(out, it.clauses.map((c) => JSON.stringify({ k: `student|${it.question}|${c}`, p: 1 / it.clauses.length, abstained: true })).join("\n") + "\n");
        continue;
      }
      const p = it.clauses.map((_, i) => a.probabilities?.[LETTERS[i]] ?? (a.choice === LETTERS[i] ? 1 : 0));
      appendFileSync(out, it.clauses.map((c, i) => JSON.stringify({ k: `student|${it.question}|${c}`, p: p[i], ms: r.ms ?? 0, tokens: r.usage?.inputTokens ?? 0 })).join("\n") + "\n");
      ok += p.indexOf(Math.max(...p)) === it.target; n++;
      if (n % 200 === 0) console.error(`${name} ${n}/${todo.length}`);
    }
  }));
  console.log(JSON.stringify({ judge: `${name}-choice`, judged: n, failed, accuracyThisRun: n ? Number((ok / n).toFixed(4)) : null }));
}
