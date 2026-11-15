#!/usr/bin/env node
// Summarise a benchmark run: per-arm means and paired sign tests (citation vs each other arm).
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
const here = new URL(".", import.meta.url);
const file = process.argv[2] ?? `results/${readdirSync(new URL("results/", here)).filter((f) => f.endsWith(".json")).sort().at(-1)}`;
const { rows, at, spec } = JSON.parse(readFileSync(new URL(file, here), "utf8"));
const ARMS = ["keywords", "question", "citation"];
const ok = rows.filter((r) => !r.error);
const errands = [...new Set(rows.map((r) => r.errand))];
const complete = errands.filter((e) => ARMS.every((a) => ok.some((r) => r.errand === e && r.arm === a)));
const get = (e, a) => ok.find((r) => r.errand === e && r.arm === a);
const mean = (xs) => xs.reduce((s, x) => s + x, 0) / (xs.length || 1);
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : 0; };
const binom = (n, k) => { let c = 1; for (let i = 1; i <= k; i++) c = (c * (n - k + i)) / i; return c; };
const signTest = (w, l) => { const n = w + l; if (!n) return 1; const k = Math.min(w, l); let p = 0; for (let i = 0; i <= k; i++) p += binom(n, i); return Math.min(1, (2 * p) / 2 ** n); };

const metrics = [
  ["legalText5", "Legal-text sources in top 5 (mean)", (r) => r.legalText5],
  ["primaryLegal5", "Official legal databases in top 5 (mean)", (r) => r.primaryLegal5],
  ["official5", "Official sources in top 5 (mean)", (r) => r.official5],
  ["top1LegalText", "Top result is legal text (share)", (r) => (r.top1LegalText ? 1 : 0)],
  ["top1Official", "Top result is official (share)", (r) => (r.top1Official ? 1 : 0)],
  ["anchor3", "Key fact verbatim in top-3 highlights (share)", (r) => (r.anchor3 ? 1 : 0)],
];
let md = `# Citation-completion benchmark\n\nRun: ${at} · via ${spec.via} · objective "${spec.objective}" · top ${spec.numResults}\n\n`;
md += `Errands: ${errands.length} (complete in all three arms: ${complete.length}) · errors: ${rows.filter((r) => r.error).length}\n\n`;
md += `| Metric | Keywords | Question | Citation-completion |\n|---|---|---|---|\n`;
for (const [, label, f] of metrics) md += `| ${label} | ${ARMS.map((a) => mean(complete.map((e) => f(get(e, a)))).toFixed(2)).join(" | ")} |\n`;
md += `| Median latency (ms) | ${ARMS.map((a) => median(complete.map((e) => get(e, a).ms))).join(" | ")} |\n\n`;
md += `## Paired comparison (per errand): citation-completion vs each arm\n\n| Metric | vs | Wins | Ties | Losses | Sign test p (two-sided) |\n|---|---|---|---|---|---|\n`;
for (const [, label, f] of metrics) for (const other of ["keywords", "question"]) {
  let w = 0, t = 0, l = 0;
  for (const e of complete) { const d = f(get(e, "citation")) - f(get(e, other)); d > 0 ? w++ : d < 0 ? l++ : t++; }
  md += `| ${label} | ${other} | ${w} | ${t} | ${l} | ${signTest(w, l).toFixed(4)} |\n`;
}
md += `\n## Per errand: legal-text sources in top 5 (K / Q / C)\n\n| Errand | Jurisdiction | K | Q | C |\n|---|---|---|---|---|\n`;
for (const e of complete) md += `| ${e} | ${get(e, "citation").jurisdiction} | ${ARMS.map((a) => get(e, a).legalText5).join(" | ")} |\n`;
const out = new URL("REPORT.md", here);
writeFileSync(out, md);
console.log(md);
