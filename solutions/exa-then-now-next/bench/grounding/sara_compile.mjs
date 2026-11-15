#!/usr/bin/env node
// SARA (LegalBench sara_entailment): "Haiku compiles, Jev executes, code decides".
// Haiku sees the statute excerpt and the assertion only (never the facts or the label) and writes a
// program: elements that are either `fact` questions (yes/no, answered by a judge over the case facts)
// or `given` conditions decided from the statute and the assertion alone (e.g. which tax year the
// assertion is about), plus a boolean formula. Assertions that need arithmetic are marked unhandled.
// Compared with the single-question baseline from run.mjs on the same rows.
// Usage: node bench/grounding/sara_compile.mjs [--providers=jev,openai]
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { openaiDecisions, typesafeJev } from "../../src/decide/decide.ts";
import { Cassette } from "../../src/eval/cassette.ts";
import { ci, mcnemar, pct } from "../stats.mjs";

const here = new URL(".", import.meta.url);
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.split("=")[1] ?? d;
const ONLY = arg("providers", "jev,openai").split(",");
const rows = readFileSync(new URL("data/legalbench-sara.jsonl", here), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
for (const r of rows) { const [statute, facts] = r.doc.split("\n\nFacts: "); r.statute = statute; r.facts = facts; }
const base = new Map(JSON.parse(readFileSync(new URL("results/legalbench-sara.json", here), "utf8")).map((r) => [r.id, r]));
const cassette = new Cassette(new URL("cassettes/sara-compiled.jsonl", here).pathname, arg("cassette", "auto"));
const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
async function pool(xs, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < xs.length) { const k = i++; await fn(xs[k]); } })); }

// ---- compile (Haiku via the Anthropic API; key read at run time from the Keychain, never printed) ----
const anthropicKey = () => process.env.ANTHROPIC_API_KEY || execFileSync("security", ["find-generic-password", "-a", "anthropic", "-s", "com.mikaelervamaa.haiku-background-intelligence", "-w"], { encoding: "utf8" }).trim();
const PROMPT = `You compile US tax-statute assertions into small decision programs. Each item has a statute excerpt and an assertion about a person (e.g. "Section 7703(a)(2) applies to Alice for the year 2018"). You do NOT see the case facts; a fast reader will answer yes/no questions about them later.

For each item return:
- elements: 1 to 5 conditions under which the assertion is true according to the excerpt. Each element is either
  {"name": snake_case, "kind": "fact", "question": a yes/no question about the case facts, self-contained, referring to \`facts\`, naming the person and the year}
  or {"name": snake_case, "kind": "given", "value": true|false, "why": short reason} for a condition decided by the statute and the assertion alone (e.g. whether the assertion's tax year falls in a period the excerpt names).
- formula: a boolean formula over the element names using AND, OR, NOT and parentheses, true exactly when the assertion holds.
- handled: false if deciding needs arithmetic on amounts (e.g. a tax amount), multi-step calculation, or law outside the excerpt; true otherwise.
Phrase fact questions positively and concretely ("Was Alice legally separated from Bob under a decree of divorce at any time during 2018?"). Do not ask the reader to compute.
Answer with JSON only: {"programs":[{"id": "...", "elements": [...], "formula": "...", "handled": true|false}]}, one per item, same order.`;

async function compileBatch(batch) {
  return cassette.wrap("anthropic.sara-compile", { model: "claude-haiku-5-5", prompt: PROMPT, items: batch.map((r) => ({ id: r.id, statute: r.statute, assertion: r.claim })) }, async () => {
    const key = anthropicKey();
    for (let i = 0; i < 4; i++) {
      const res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01" }, body: JSON.stringify({ model: "claude-haiku-5-5", max_tokens: 16000, messages: [{ role: "user", content: `${PROMPT}\n\n${JSON.stringify(batch.map((r) => ({ id: r.id, statute: r.statute, assertion: r.claim })))}` }] }) });
      if (res.ok) {
        const d = await res.json();
        const text = d.content.filter((c) => c.type === "text").map((c) => c.text).join("");
        try { return JSON.parse(text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1)).programs; } catch { continue; }
      }
      await new Promise((s) => setTimeout(s, 3000 * (i + 1)));
    }
    throw new Error("compile failed");
  });
}
const batches = Array.from({ length: Math.ceil(rows.length / 8) }, (_, i) => rows.slice(i * 8, i * 8 + 8));
await pool(batches, 4, async (b) => { const ps = await compileBatch(b); b.forEach((r, i) => (r.program = ps.find((p) => p.id === r.id) ?? ps[i])); });

// ---- execute ----
function evaluate(formula, p) {
  const tokens = formula.match(/\(|\)|AND|OR|NOT|[A-Za-z_0-9]+/g) ?? [];
  let i = 0;
  const atom = () => { const t = tokens[i++]; if (t === "(") { const v = or(); i++; return v; } if (t === "NOT") return 1 - atom(); if (t === "true") return 1; if (t === "false") return 0; if (!(t in p)) throw new Error(`unknown element ${t}`); return p[t]; };
  const and = () => { let v = atom(); while (tokens[i] === "AND") { i++; v = Math.min(v, atom()); } return v; };
  const or = () => { let v = and(); while (tokens[i] === "OR") { i++; v = Math.max(v, and()); } return v; };
  return or();
}
const judges = {};
if (ONLY.includes("jev")) { const { TypeSafeClient } = await import("@typesafe-ai/sdk"); const ts = new TypeSafeClient({ apiKey: process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY"), defaultModel: "jev-1.14.0" }); judges.jev = cassette.decisions(typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) })); }
if (ONLY.includes("openai")) judges.luna = cassette.decisions(openaiDecisions({ apiKey: process.env.OPENAI_API_KEY || keyFrom(`${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY") }));
let broken = 0;
for (const [name, j] of Object.entries(judges)) {
  await pool(rows, 8, async (r) => {
    const prog = r.program;
    if (!prog?.elements?.length) { r[`${name}_compiled`] = null; return; }
    const facts = prog.elements.filter((e) => e.kind === "fact");
    const p = Object.fromEntries(prog.elements.filter((e) => e.kind === "given").map((e) => [e.name, e.value ? 1 : 0]));
    if (facts.length) {
      const res = await j.decide({ facts: r.facts }, facts.map((e) => ({ kind: "yesno", name: e.name, instructions: e.question })));
      res.answers.forEach((a) => (p[a.name] = a.p ?? 0));
    }
    try { r[`${name}_compiled`] = evaluate(prog.formula, p); } catch { r[`${name}_compiled`] = null; broken++; }
  });
}
cassette.pack();

const bacc = (xs, f) => { const p = xs.filter((x) => x.label === 1), n = xs.filter((x) => x.label === 0); return p.length && n.length ? (p.filter(f).length / p.length + n.filter((x) => !f(x)).length / n.length) / 2 : NaN; };
const handled = rows.filter((r) => r.program?.handled && r.jev_compiled != null);
const lines = [`# SARA: compiled statute programs vs one question (${new Date().toISOString().slice(0, 10)})`, "", `${rows.length} assertions; Haiku marked ${handled.length} as handled by a program (no arithmetic). Programs see statute + assertion only. Balanced accuracy.`, "", "| verifier | all 272 (program, else one question) | handled only | unhandled only |", "|---|---|---|---|"];
for (const name of Object.keys(judges)) {
  const single = (x) => base.get(x.id)?.[name]?.supported > 0.5;
  const combo = (x) => (x.program?.handled && x[`${name}_compiled`] != null ? x[`${name}_compiled`] > 0.5 : single(x));
  const unh = rows.filter((r) => !handled.includes(r));
  lines.push(`| ${name}: one question | ${pct(bacc(rows, single))} | ${pct(bacc(handled, single))} | ${pct(bacc(unh, single))} |`);
  lines.push(`| ${name}: compiled program | ${pct(bacc(rows, combo))} | ${pct(bacc(handled, (x) => x[`${name}_compiled`] > 0.5))} | (one question) |`);
  const m = mcnemar(rows.map((x) => combo(x) === (x.label === 1)), rows.map((x) => single(x) === (x.label === 1)));
  lines.push(`|  ↳ paired | program right & single wrong ${m.onlyA}, reverse ${m.onlyB}, exact McNemar p = ${m.p.toFixed(4)} | | |`);
}
lines.push("", `Formula errors: ${broken}. Unhandled examples: ${rows.filter((r) => !r.program?.handled).slice(0, 3).map((r) => `"${r.claim}"`).join("; ")}`);
console.log(lines.join("\n"));
writeFileSync(new URL("results/sara-compiled.md", here), lines.join("\n") + "\n");
writeFileSync(new URL("results/sara-compiled.json", here), JSON.stringify(rows.map(({ doc, statute, facts, ...r }) => r), null, 1));
