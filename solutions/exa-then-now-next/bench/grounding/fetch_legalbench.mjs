#!/usr/bin/env node
// LegalBench tasks as claim + document rows for bench/grounding/run.mjs (label 1 = supported).
//   sara_entailment           US tax statute + facts -> assertion (Entailment / Contradiction), MIT
//   contract_nli_* (all)      NDA excerpt -> fixed ContractNLI hypothesis (Yes / No), CC BY 4.0;
//                             hypothesis texts from the official ContractNLI release (data/raw/contract-nli)
//   privacy_policy_entailment policy excerpt -> description (Correct / Incorrect), CC BY-NC 3.0, sampled
// Source: Hugging Face datasets server (nguha/legalbench). Writes bench/grounding/data/legalbench-*.jsonl.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const here = new URL(".", import.meta.url);
const API = "https://datasets-server.huggingface.co";
const get = async (u) => { for (let i = 0; i < 4; i++) { const r = await fetch(u); if (r.ok) return r.json(); await new Promise((s) => setTimeout(s, 1500 * (i + 1))); } throw new Error(`GET ${u} failed`); };
async function rows(config, max = Infinity) {
  const out = [];
  for (let offset = 0; offset < max; offset += 100) {
    const d = await get(`${API}/rows?dataset=nguha/legalbench&config=${encodeURIComponent(config)}&split=test&offset=${offset}&length=100`);
    out.push(...d.rows.map((r) => r.row));
    if (out.length >= d.num_rows_total || !d.rows.length) break;
  }
  return out;
}
const write = (name, xs) => { writeFileSync(new URL(`data/${name}.jsonl`, here), xs.map((x) => JSON.stringify(x)).join("\n") + "\n"); console.log(`${name}: ${xs.length} rows, ${xs.filter((x) => x.label === 1).length} supported`); };

const only = process.argv.find((a) => a.startsWith("--only="))?.slice(7);
// 1. SARA statutory entailment
if (!only || only === "sara") {
const sara = await rows("sara_entailment");
write("legalbench-sara", sara.map((r) => ({ id: `sara-${r.index}`, dataset: "sara_entailment", case: r["case id"], doc: `${r.statute.trim()}\n\nFacts: ${r.description.trim()}`, claim: r.question.trim(), label: r.answer === "Entailment" ? 1 : 0 })));
}

// 2. ContractNLI configs, hypothesis text matched by the task's short description
if (!only || only === "cnli") {
const cnliFile = new URL("data/raw/contract-nli/contract-nli/test.json", here);
if (!existsSync(cnliFile)) throw new Error("download and unzip https://stanfordnlp.github.io/contract-nli/resources/contract-nli.zip into bench/grounding/data/raw/contract-nli first");
const labels = JSON.parse(readFileSync(cnliFile, "utf8")).labels;
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
const hyp = new Map(Object.values(labels).map((v) => [slug(v.short_description), v.hypothesis]));
const splits = await get(`${API}/splits?dataset=nguha/legalbench`);
const cnliConfigs = [...new Set(splits.splits.map((s) => s.config).filter((c) => c.startsWith("contract_nli_")))];
const cnli = [];
for (const c of cnliConfigs) {
  const key = slug(c.replace(/^contract_nli_/, ""));
  const h = hyp.get(key) ?? [...hyp].find(([k]) => k.replace(/_/g, "") === key.replace(/_/g, ""))?.[1];
  if (!h) { console.log(`no hypothesis for ${c}`); continue; }
  for (const r of await rows(c)) cnli.push({ id: `${c}-${r.index}`, dataset: c.replace(/^contract_nli_/, "cnli_"), doc: r.text.trim(), claim: h, label: r.answer === "Yes" ? 1 : 0 });
}
write("legalbench-contractnli", cnli);
}

// 3. Privacy policy entailment: stratified sample (150 per label)
if (!only || only === "privacy") {
const pp = await rows("privacy_policy_entailment", 1200); // a stratified sample needs only the first rows
const pick = (lab) => pp.filter((r) => r.answer === lab).slice(0, 150);
write("legalbench-privacy", [...pick("Correct"), ...pick("Incorrect")].map((r) => ({ id: `pp-${r.index}`, dataset: "privacy_policy", doc: r.text.trim(), claim: r.description.trim(), label: r.answer === "Correct" ? 1 : 0 })));
}
