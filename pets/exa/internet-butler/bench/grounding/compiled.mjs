#!/usr/bin/env node
// "Haiku compiles, Jev executes, code decides" on ContractNLI (LegalBench).
// Each hypothesis was compiled once (bench/grounding/cnli_programs.json) into 2–3 yes/no element
// questions and a boolean formula, from the hypothesis text only. Per row, a judge answers the
// elements over the excerpt; code evaluates the formula with fuzzy logic (AND = min, OR = max,
// NOT = 1 - p). Compared with the single-question baseline on the same rows (from run.mjs output),
// plus grouped cross-validated stacking (no clause type in both train and test).
// Usage: node bench/grounding/compiled.mjs [--limit=560] [--providers=jev,openai]
import { readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { openaiDecisions, typesafeJev } from "../../src/decide/decide.ts";
import { Cassette } from "../../src/eval/cassette.ts";
import { pct } from "../stats.mjs";

const here = new URL(".", import.meta.url);
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.split("=")[1] ?? d;
const LIMIT = Number(arg("limit", "560"));
const ONLY = arg("providers", "jev,openai").split(",");
const programs = new Map(JSON.parse(readFileSync(new URL("cnli_programs.json", here), "utf8")).programs.map((p) => [p.task, p]));
let rows = readFileSync(new URL("data/legalbench-contractnli.jsonl", here), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
{ // the same stratified sample as run.mjs --limit
  const groups = new Map();
  for (const r of rows) { const k = `${r.dataset}|${r.label}`; groups.set(k, [...(groups.get(k) ?? []), r]); }
  const per = Math.max(1, Math.floor(LIMIT / groups.size));
  rows = [...groups.values()].flatMap((g) => g.slice(0, per));
}
const baseline = new Map(JSON.parse(readFileSync(new URL("results/legalbench-contractnli.json", here), "utf8")).map((r) => [r.id, r]));

// Tiny boolean parser with fuzzy semantics.
function evaluate(formula, p) {
  const tokens = formula.match(/\(|\)|AND|OR|NOT|[a-z_0-9]+/g);
  let i = 0;
  const atom = () => { const t = tokens[i++]; if (t === "(") { const v = or(); i++; return v; } if (t === "NOT") return 1 - atom(); if (!(t in p)) throw new Error(`unknown element ${t}`); return p[t]; };
  const and = () => { let v = atom(); while (tokens[i] === "AND") { i++; v = Math.min(v, atom()); } return v; };
  const or = () => { let v = and(); while (tokens[i] === "OR") { i++; v = Math.max(v, and()); } return v; };
  return or();
}

const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
const cassette = new Cassette(new URL("cassettes/cnli-compiled.jsonl", here).pathname, "auto");
const judges = {};
if (ONLY.includes("jev")) { const { TypeSafeClient } = await import("@typesafe-ai/sdk"); const ts = new TypeSafeClient({ apiKey: process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY"), defaultModel: "jev-1.14.0" }); judges.jev = cassette.decisions(typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) })); }
if (ONLY.includes("openai")) judges.luna = cassette.decisions(openaiDecisions({ apiKey: process.env.OPENAI_API_KEY || keyFrom(`${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY") }));

async function pool(xs, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < xs.length) { const k = i++; await fn(xs[k]); } })); }
for (const [name, j] of Object.entries(judges)) {
  await pool(rows, 8, async (r) => {
    const prog = programs.get(r.dataset);
    const res = await j.decide({ excerpt: r.doc }, prog.questions.map((q) => ({ kind: "yesno", name: q.name, instructions: q.question.replace(/\bthe excerpt\b/gi, "`excerpt`") })));
    const p = Object.fromEntries(res.answers.map((a) => [a.name, a.p ?? 0]));
    r[`${name}_elements`] = p;
    r[`${name}_compiled`] = evaluate(prog.formula, p);
  });
}
cassette.pack();

const bacc = (xs, pred) => { const pos = xs.filter((x) => x.label === 1), neg = xs.filter((x) => x.label === 0); return (pos.filter(pred).length / pos.length + neg.filter((x) => !pred(x)).length / neg.length) / 2; };
const tasks = [...new Set(rows.map((r) => r.dataset))].sort();
const lines = [`# ContractNLI: compiled clause programs vs one question (${new Date().toISOString().slice(0, 10)})`, "", `${rows.length} rows (stratified, ${tasks.length} clause types). Programs compiled by Haiku from hypothesis text only. Balanced accuracy.`, "", `| verifier | overall | ${tasks.map((t) => t.replace("cnli_", "")).join(" | ")} |`, `|---|---|${tasks.map(() => "---").join("|")}|`];
const verifiers = {};
for (const name of Object.keys(judges)) {
  verifiers[`${name}: one question`] = (x) => baseline.get(x.id)?.[name]?.supported > 0.5;
  verifiers[`${name}: compiled program`] = (x) => x[`${name}_compiled`] > 0.5;
}
if (judges.jev && judges.luna) verifiers["jev + luna compiled (mean)"] = (x) => (x.jev_compiled + x.luna_compiled) / 2 > 0.5;
for (const [v, f] of Object.entries(verifiers)) lines.push(`| ${v} | ${pct(bacc(rows, f))} | ${tasks.map((t) => pct(bacc(rows.filter((r) => r.dataset === t), f))).join(" | ")} |`);
for (const name of Object.keys(judges)) {
  const answered = rows.filter((x) => x[`${name}_compiled`] < 0.3 || x[`${name}_compiled`] > 0.7);
  lines.push("", `- ${name} compiled, abstaining in 0.3–0.7: answers ${pct(answered.length / rows.length)}, balanced accuracy on those ${pct(bacc(answered, (x) => x[`${name}_compiled`] > 0.5))}`);
}
console.log(lines.join("\n"));
writeFileSync(new URL("results/cnli-compiled.md", here), lines.join("\n") + "\n");
writeFileSync(new URL("results/cnli-compiled.json", here), JSON.stringify(rows.map(({ doc, ...r }) => ({ ...r, base: baseline.get(r.id) && { jev: baseline.get(r.id).jev, luna: baseline.get(r.id).luna } })), null, 1));
