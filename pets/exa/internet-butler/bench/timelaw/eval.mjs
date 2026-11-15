#!/usr/bin/env node
// TimeLaw evaluation: is this clause the law on this date?
//   current     judge + code against today's official text (what date-blind retrieval does)
//   pit         judge + code against the official text as it stood on the claim's date (ours)
//   pit-code    code only: every number in the claim appears in the text on that date
//   jev-prior   Jev with no document: "on <date>, was this the law?"
//   haiku-prior Claude Haiku with no document, same question, 10 claims per call
// Gold: the official text on that date (build.mjs). All calls go through a cassette.
// Usage: node bench/timelaw/eval.mjs [--providers=jev,haiku]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { typesafeJev } from "../../src/decide/decide.ts";
import { Cassette } from "../../src/eval/cassette.ts";
import { ci, pct } from "../stats.mjs";

const here = new URL(".", import.meta.url);
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.split("=")[1] ?? d;
const ONLY = arg("providers", "jev,haiku").split(",");
const rows = readFileSync(new URL("data/timelaw.jsonl", here), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const texts = JSON.parse(readFileSync(new URL("data/texts.json", here), "utf8"));
const provisions = JSON.parse(readFileSync(new URL("data/provisions.json", here), "utf8"));
const latestDate = Object.fromEntries(provisions.map((p) => [p.id, p.dates.filter((d) => texts[`${p.id}@${d}`]).sort().at(-1)]));
const textOn = (r, d) => texts[`${r.provision}@${d}`] ?? "";
mkdirSync(new URL("cassettes/", here), { recursive: true });
const cassette = new Cassette(new URL("cassettes/timelaw.jsonl", here).pathname, arg("cassette", "auto"));

const NUM = /£?\$?\d[\d,]*(?:\.\d+)?%?/g;
const nums = (s) => (s.match(NUM) ?? []).map((n) => n.replace(/[,]$/, ""));
const codeIn = (claim, doc) => nums(claim).every((n) => doc.includes(n));

const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
async function pool(xs, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < xs.length) { const k = i++; await fn(xs[k], k); } })); }

const SUPPORTED = [{ kind: "yesno", name: "supported", instructions: "Does `document` state what `claim` says, including every amount and number in it?", yes: "the document contains this rule with the same amounts", no: "the document states different amounts, or does not contain this rule" }];
const PRIOR = [{ kind: "yesno", name: "was_law", instructions: "On `date`, was `claim` the law under `law` (with exactly these amounts)?" }];

if (ONLY.includes("jev")) {
  const { TypeSafeClient } = await import("@typesafe-ai/sdk");
  const ts = new TypeSafeClient({ apiKey: process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY"), defaultModel: "jev-1.14.0" });
  const jev = cassette.decisions(typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) }));
  await pool(rows, 8, async (r) => {
    const [cur, pit, prior] = await Promise.all([
      jev.decide({ claim: r.claim, document: textOn(r, latestDate[r.provision]) }, SUPPORTED),
      jev.decide({ claim: r.claim, document: textOn(r, r.date) }, SUPPORTED),
      jev.decide({ date: r.date, law: r.name, claim: r.claim }, PRIOR),
    ]);
    r.jev = { current: cur.answers[0].p, pit: pit.answers[0].p, prior: prior.answers[0].p };
  });
}

if (ONLY.includes("haiku")) {
  // The Anthropic key is read at run time from the login Keychain item the haiku tool uses; never printed.
  const key = process.env.ANTHROPIC_API_KEY || execFileSync("security", ["find-generic-password", "-a", "anthropic", "-s", "com.mikaelervamaa.haiku-background-intelligence", "-w"], { encoding: "utf8" }).trim();
  const ask = (batch) => cassette.wrap("anthropic.haiku-prior", { model: "claude-haiku-5-5", batch: batch.map((r) => ({ id: r.id, date: r.date, law: r.name, claim: r.claim })) }, async () => {
    const body = {
      model: "claude-haiku-5-5",
      max_tokens: 16000,
      messages: [{ role: "user", content: `From memory only, for each item decide whether, on the given date, the claim was the law under the named instrument with exactly these amounts. Answer with JSON only: {"answers":[{"id":"...","was_law":true|false,"confidence":0-100}]}, one per item, same order.\n\n${JSON.stringify(batch.map((r) => ({ id: r.id, date: r.date, law: r.name, claim: r.claim })))}` }],
    };
    for (let i = 0; i < 4; i++) {
      const res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" }, body: JSON.stringify(body) });
      if (res.ok) {
        const d = await res.json();
        const text = d.content.filter((c) => c.type === "text").map((c) => c.text).join("");
        try {
          return JSON.parse(text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1)).answers;
        } catch {
          if (i === 3) throw new Error(`unparseable Haiku answer (stop_reason ${d.stop_reason})`);
          continue;
        }
      }
      await new Promise((s) => setTimeout(s, 3000 * (i + 1)));
    }
    throw new Error("Anthropic API failed");
  });
  const batches = Array.from({ length: Math.ceil(rows.length / 10) }, (_, i) => rows.slice(i * 10, i * 10 + 10));
  await pool(batches, 4, async (b) => {
    const ans = await ask(b);
    b.forEach((r, i) => { const a = ans.find((x) => x.id === r.id) ?? ans[i]; r.haiku = a ? (a.was_law ? 1 : 0) : null; r.haikuConf = a?.confidence; });
  });
}
cassette.pack();

for (const r of rows) { r.code_current = codeIn(r.claim, textOn(r, latestDate[r.provision])); r.code_pit = codeIn(r.claim, textOn(r, r.date)); }
const methods = { "current text, code": (r) => r.code_current, "point-in-time, code": (r) => r.code_pit };
if (rows[0].jev) Object.assign(methods, {
  "current text, Jev": (r) => r.jev.current > 0.5,
  "current text, Jev + code": (r) => r.jev.current > 0.5 && r.code_current,
  "point-in-time, Jev": (r) => r.jev.pit > 0.5,
  "point-in-time, Jev + code": (r) => r.jev.pit > 0.5 && r.code_pit,
  "no document, Jev prior": (r) => r.jev.prior > 0.5,
});
if (rows[0].haiku != null) methods["no document, Haiku from memory"] = (r) => r.haiku === 1;

const acc = (xs, f) => xs.filter((r) => f(r) === (r.label === 1)).length;
const bacc = (xs, f) => { const p = xs.filter((r) => r.label === 1), n = xs.filter((r) => r.label === 0); return (p.filter(f).length / p.length + n.filter((r) => !f(r)).length / n.length) / 2; };
const hist = rows.filter((r) => !r.latest), now = rows.filter((r) => r.latest);
const lines = [`# TimeLaw: is this clause the law on this date? (${new Date().toISOString().slice(0, 10)})`, "", `${rows.length} claims from ${new Set(rows.map((r) => r.provision)).size} official provisions (eCFR versioner, legislation.gov.uk point-in-time); ${rows.filter((r) => r.label === 1).length} true, ${rows.filter((r) => r.kind === "stale").length} stale (an earlier amount), ${rows.filter((r) => r.kind === "premature").length} premature (a later amount). Gold = the official text on that date.`, ""];
lines.push("| method | balanced accuracy | accuracy | historical dates | latest date | true accepted | stale rejected | premature rejected |", "|---|---|---|---|---|---|---|---|");
for (const [m, f] of Object.entries(methods)) {
  const kind = (k, want) => { const xs = rows.filter((r) => r.kind === k); return pct(xs.filter((r) => f(r) === want).length / xs.length); };
  lines.push(`| ${m} | ${pct(bacc(rows, f))} | ${ci(acc(rows, f), rows.length)} | ${pct(acc(hist, f) / hist.length)} | ${pct(acc(now, f) / now.length)} | ${kind("true", true)} | ${kind("stale", false)} | ${kind("premature", false)} |`);
}
if (rows[0].haiku != null) {
  const byYear = new Map();
  for (const r of rows) { const y = r.date.slice(0, 4); const v = byYear.get(y) ?? [0, 0]; v[0] += (r.haiku === 1) === (r.label === 1) ? 1 : 0; v[1]++; byYear.set(y, v); }
  lines.push("", `Haiku from memory, accuracy by year: ${[...byYear].sort().map(([y, [a, n]]) => `${y} ${pct(a / n)}`).join(", ")}`);
}
console.log(lines.join("\n"));
mkdirSync(new URL("results/", here), { recursive: true });
writeFileSync(new URL("results/timelaw.md", here), lines.join("\n") + "\n");
writeFileSync(new URL("results/timelaw.json", here), JSON.stringify(rows, null, 1));
