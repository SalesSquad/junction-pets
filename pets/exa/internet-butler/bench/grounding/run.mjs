#!/usr/bin/env node
// Grounding benchmark harness: claim + document -> supported or not, on public gold-labelled data.
// Input: JSONL rows {id, dataset, doc, claim, label} with label 1 = supported, 0 = not supported
// (written by bench/grounding/fetch_*.mjs). Verifiers:
//   code      every number in the claim appears in the document (normalised); says nothing about the rest
//   single    one yes/no question, "is every part of the claim supported by the document?" (the usual baseline)
//   table     a general truth table: supported, numbers, names, conditions, contradiction, extra content
//   table+code  the table, with the code check as a veto
// For each judge (Jev, Luna). Metrics: balanced accuracy per dataset (the LLM-AggreFact convention) and
// overall; risk–coverage when the judge may abstain in the 0.3–0.7 band; cost and latency.
// All calls go through a cassette: re-runs and re-scoring are free.
// Usage: node bench/grounding/run.mjs --data=bench/grounding/data/<file>.jsonl [--limit=N] [--providers=jev,openai]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { basename } from "node:path";
import { openaiDecisions, typesafeJev } from "../../src/decide/decide.ts";
import { Cassette, gitState, writeManifest } from "../../src/eval/cassette.ts";
import { extractQuantities, sameQuantity } from "../../src/warrant/lanes.ts";
import { pct } from "../stats.mjs";

const here = new URL(".", import.meta.url);
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.split("=")[1] ?? d;
const DATA = arg("data", "");
if (!DATA) { console.error("--data=<jsonl> required"); process.exit(1); }
const LIMIT = Number(arg("limit", "0"));
const ONLY = arg("providers", "jev,openai").split(",");
const started = new Date().toISOString();
mkdirSync(new URL("cassettes/", here), { recursive: true });
const cassette = new Cassette(new URL(`cassettes/${basename(DATA, ".jsonl")}.jsonl`, here).pathname, arg("cassette", "auto"));
const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
const judges = {};
if (ONLY.includes("jev")) {
  const { TypeSafeClient } = await import("@typesafe-ai/sdk");
  const key = process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY");
  const ts = new TypeSafeClient({ apiKey: key, defaultModel: "jev-1.14.0" });
  judges.jev = { model: "jev-1.14.0", price: 0.042, p: cassette.decisions(typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) })) };
}
if (ONLY.includes("openai")) {
  const key = process.env.OPENAI_API_KEY || keyFrom(`${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY");
  judges.luna = { model: "gpt-6-luna", price: 0.1, p: cassette.decisions(openaiDecisions({ apiKey: key })) };
}

let rows = readFileSync(DATA, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
if (LIMIT) {
  // Stratified by dataset and label so a small run is still balanced.
  const groups = new Map();
  for (const r of rows) { const k = `${r.dataset}|${r.label}`; groups.set(k, [...(groups.get(k) ?? []), r]); }
  const per = Math.max(1, Math.floor(LIMIT / groups.size));
  rows = [...groups.values()].flatMap((g) => g.slice(0, per));
}

// ---- verifiers ----
const SINGLE = [{ kind: "yesno", name: "supported", instructions: "Is every part of `claim` supported by `document`?", yes: "everything the claim states is stated or directly implied by the document", no: "some part of the claim is missing from, or contradicted by, the document" }];
const TABLE = [
  ...SINGLE,
  { kind: "yesno", name: "numbers_match", instructions: "Do all numbers, amounts, dates and periods in `claim` match what `document` says about the same things?", yes: "they match, or the claim has none" },
  { kind: "yesno", name: "names_match", instructions: "Are the people, organisations, places, laws and other named things in `claim` the ones `document` says, in the same roles?", yes: "they match, or the claim names none" },
  { kind: "yesno", name: "contradicts", instructions: "Does `document` contradict any part of `claim`?" },
  { kind: "yesno", name: "adds", instructions: "Does `claim` add a condition, cause, consequence, scope or detail that `document` does not support?", no: "everything in the claim, including its qualifiers, is in the document" },
];
const norm = (s) => s.normalize("NFKC").toLowerCase();
function codeCheck(doc, claim) {
  const qs = extractQuantities(claim);
  if (!qs.length) {
    // Bare numbers (years, counts) not covered by the quantity extractor: require them verbatim.
    const nums = claim.match(/\b\d[\d,.]*\b/g) ?? [];
    const d = norm(doc);
    return nums.every((n) => d.includes(n.replace(/[.,]$/, "")));
  }
  const dq = extractQuantities(doc);
  return qs.every((q) => dq.some((x) => sameQuantity(x, q)));
}
const tableOk = (t) => t.supported > 0.5 && t.numbers_match > 0.5 && t.names_match > 0.5 && t.contradicts <= 0.5 && t.adds <= 0.5;
const tableScore = (t) => Math.min(t.supported, t.numbers_match, t.names_match, 1 - t.contradicts, 1 - t.adds);

async function pool(xs, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < xs.length) { const k = i++; await fn(xs[k], k); } })); }
const usage = {};
for (const [name, j] of Object.entries(judges)) {
  usage[name] = { tokens: 0, ms: [] };
  await pool(rows, 8, async (r) => {
    // The single question is the first row of the table, so one request answers both designs.
    const res = await j.p.decide({ document: r.doc, claim: r.claim }, TABLE);
    usage[name].tokens += res.usage.inputTokens;
    usage[name].ms.push(res.ms);
    r[name] = Object.fromEntries(res.answers.map((a) => [a.name, a.p ?? 0]));
  });
}
for (const r of rows) r.code = codeCheck(r.doc, r.claim);
cassette.pack();

// ---- metrics ----
const bacc = (xs, pred) => {
  const pos = xs.filter((x) => x.label === 1), neg = xs.filter((x) => x.label === 0);
  const tpr = pos.length ? pos.filter(pred).length / pos.length : NaN;
  const tnr = neg.length ? neg.filter((x) => !pred(x)).length / neg.length : NaN;
  return pos.length && neg.length ? (tpr + tnr) / 2 : NaN;
};
const verifiers = { code: (x) => x.code };
for (const name of Object.keys(judges)) {
  verifiers[`${name}:single`] = (x) => x[name].supported > 0.5;
  verifiers[`${name}:table`] = (x) => tableOk(x[name]);
  verifiers[`${name}:table+code`] = (x) => tableOk(x[name]) && x.code;
}
if (judges.jev && judges.luna) verifiers["jev+luna:single (mean p)"] = (x) => (x.jev.supported + x.luna.supported) / 2 > 0.5;

const datasets = [...new Set(rows.map((r) => r.dataset))];
const lines = [`# Grounding benchmark: ${basename(DATA)} (${started.slice(0, 10)})`, "", `${rows.length} claims from ${datasets.length} dataset(s); label balance ${rows.filter((r) => r.label === 1).length} supported / ${rows.filter((r) => r.label === 0).length} not. Metric: balanced accuracy (mean of the two class recalls).`, ""];
lines.push(`| verifier | overall | ${datasets.join(" | ")} |`, `|---|---|${datasets.map(() => "---").join("|")}|`);
for (const [v, pred] of Object.entries(verifiers)) {
  lines.push(`| ${v} | ${pct(bacc(rows, pred))} | ${datasets.map((d) => pct(bacc(rows.filter((r) => r.dataset === d), pred))).join(" | ")} |`);
}
// Selective prediction: answer only outside the unsure band; report accuracy on answered and coverage.
lines.push("", "Abstaining in the 0.3–0.7 band (single question) or on any table row in it:", "");
for (const name of Object.keys(judges)) {
  for (const [design, score] of [["single", (x) => x[name].supported], ["table", (x) => tableScore(x[name])]]) {
    const answered = rows.filter((x) => { const s = score(x); return s < 0.3 || s > 0.7; });
    const right = answered.filter((x) => (score(x) > 0.5) === (x.label === 1)).length;
    lines.push(`- ${name}:${design}: answers ${pct(answered.length / rows.length)} of claims, balanced accuracy on those ${pct(bacc(answered, (x) => score(x) > 0.5))} (plain accuracy ${pct(right / (answered.length || 1))})`);
  }
}
lines.push("", "Cost and latency:", "");
for (const [name, u] of Object.entries(usage)) {
  const m = u.ms.slice().sort((a, b) => a - b);
  lines.push(`- ${name}: ${u.tokens} input tokens ≈ $${((u.tokens / 1e6) * judges[name].price).toFixed(4)} for ${rows.length} claims (6 questions each); p50 ${m[Math.floor(m.length / 2)]} ms, p95 ${m[Math.floor(m.length * 0.95)]} ms`);
}
lines.push("", `Cassette: ${cassette.size} calls (${cassette.hits} replayed, ${cassette.misses} live).`);
console.log(lines.join("\n"));
const stem = basename(DATA, ".jsonl");
mkdirSync(new URL("results/", here), { recursive: true });
writeFileSync(new URL(`results/${stem}.md`, here), lines.join("\n") + "\n");
writeFileSync(new URL(`results/${stem}.json`, here), JSON.stringify(rows.map(({ doc, ...r }) => r), null, 1));
writeManifest(new URL(`results/${stem}.manifest.json`, here).pathname, { name: `grounding:${stem}`, started, ended: new Date().toISOString(), git: gitState(new URL("../..", here).pathname), node: process.version, args: process.argv.slice(2), models: Object.fromEntries(Object.entries(judges).map(([k, j]) => [k, j.model])), cassette: { path: cassette.path, digest: cassette.digest(), entries: cassette.size, hits: cassette.hits, misses: cassette.misses }, outputs: [`bench/grounding/results/${stem}.md`] });
