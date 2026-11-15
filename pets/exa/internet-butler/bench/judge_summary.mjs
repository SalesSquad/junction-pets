#!/usr/bin/env node
// Aggregate Haiku judge labels into semantic metrics per arm, with paired sign tests and inter-rater agreement.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
const here = new URL(".", import.meta.url);
const { run, keys } = JSON.parse(readFileSync(new URL("judge/keymap.json", here), "utf8"));
const haiku = new Map();
for (let b = 0; b < 16; b++) {
  const f = new URL(`judge/labels${b}.json`, here);
  if (!existsSync(f)) { console.error(`missing labels${b}.json`); continue; }
  for (const l of JSON.parse(readFileSync(f, "utf8"))) haiku.set(l.item, l);
}
const openai = new Map();
const of = new URL("judge/openai_labels.json", here);
if (existsSync(of)) for (const l of JSON.parse(readFileSync(of, "utf8"))) openai.set(l.item, l);
const RATER = process.argv[2] ?? "consensus";
const labels = new Map();
for (const [item, h] of haiku) {
  const o = openai.get(item);
  if (RATER === "haiku") labels.set(item, h);
  else if (RATER === "openai") { if (o) labels.set(item, o); }
  else if (o) labels.set(item, {
    states_rule: h.states_rule === "yes" && o.states_rule === "yes" ? "yes" : h.states_rule === "no" && o.states_rule === "no" ? "no" : "partial",
    contradicts: !!(h.contradicts && o.contradicts),
    source_type: h.source_type === o.source_type ? h.source_type : "disagree",
    jurisdiction_match: h.jurisdiction_match !== false && o.jurisdiction_match !== false,
  });
}
const rows = new Map(); // errand|arm -> [label by rank]
keys.forEach((key, item) => {
  const [errand, arm, rank] = key.split("|");
  const l = labels.get(item);
  if (!l) return;
  const k = `${errand}|${arm}`;
  if (!rows.has(k)) rows.set(k, []);
  rows.get(k)[Number(rank)] = l;
});
const ARMS = ["keywords", "question", "citation", "auto_en", "auto_native"];
const errands = [...new Set(keys.map((k) => k.split("|")[0]))];
const yes = (l) => l && l.states_rule === "yes" && l.jurisdiction_match !== false;
const legalYes = (l) => yes(l) && l.source_type === "legal_text";
const m = {
  "Results stating the rule, top 5 (mean)": (ls) => ls.filter(yes).length,
  "Legal text stating the rule, top 5 (mean)": (ls) => ls.filter(legalYes).length,
  "At least one result states the rule (share)": (ls) => (ls.some(yes) ? 1 : 0),
  "At least one LEGAL TEXT states the rule (share)": (ls) => (ls.some(legalYes) ? 1 : 0),
  "Top result states the rule (share)": (ls) => (yes(ls[0]) ? 1 : 0),
  "Results contradicting the reference, top 5 (mean)": (ls) => ls.filter((l) => l?.contradicts).length,
};
const val = (e, a, f) => (rows.has(`${e}|${a}`) ? f(rows.get(`${e}|${a}`)) : null);
const mean = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : NaN);
const binom = (n, k) => { let c = 1; for (let i = 1; i <= k; i++) c = (c * (n - k + i)) / i; return c; };
const sign = (w, l) => { const n = w + l; if (!n) return 1; let p = 0; for (let i = 0; i <= Math.min(w, l); i++) p += binom(n, i); return Math.min(1, (2 * p) / 2 ** n); };
let md = `# Benchmark v2: semantic support (rater: ${RATER})\n\nRun: ${run} · labels: ${labels.size}/${keys.length} · judges blind to arm · Haiku swarm (Claude Code subagents) + OpenAI gpt-5.4-mini; consensus = both agree\n\n`;
const native = errands.filter((e) => rows.has(`${e}|auto_native`));
md += `| Metric | ${ARMS.map((a) => (a === "auto_native" ? `auto_native (n=${native.length})` : a)).join(" | ")} |\n|---|${ARMS.map(() => "---").join("|")}|\n`;
for (const [name, f] of Object.entries(m)) md += `| ${name} | ${ARMS.map((a) => { const xs = (a === "auto_native" ? native : errands).map((e) => val(e, a, f)).filter((x) => x !== null); return mean(xs).toFixed(2); }).join(" | ")} |\n`;
md += `\nSame metrics on the non-English subset only (${native.join(", ")}):\n\n| Metric | ${ARMS.join(" | ")} |\n|---|${ARMS.map(() => "---").join("|")}|\n`;
for (const [name, f] of Object.entries(m)) md += `| ${name} | ${ARMS.map((a) => mean(native.map((e) => val(e, a, f)).filter((x) => x !== null)).toFixed(2)).join(" | ")} |\n`;
md += `\n## Paired comparisons (wins / ties / losses, sign test p)\n\n| Metric | Comparison | W | T | L | p |\n|---|---|---|---|---|---|\n`;
const pairs = [["citation", "keywords"], ["citation", "question"], ["auto_en", "question"], ["auto_en", "keywords"], ["auto_en", "citation"], ["auto_native", "auto_en"]];
for (const [name, f] of Object.entries(m)) for (const [a, b] of pairs) {
  let w = 0, t = 0, l = 0;
  for (const e of a === "auto_native" ? native : errands) { const x = val(e, a, f), y = val(e, b, f); if (x === null || y === null) continue; x > y ? w++ : x < y ? l++ : t++; }
  md += `| ${name} | ${a} vs ${b} | ${w} | ${t} | ${l} | ${sign(w, l).toFixed(4)} |\n`;
}
// Cross-family agreement: Haiku vs OpenAI on every item both labelled.
{
  const cats = ["yes", "partial", "no"]; let n = 0, agree = 0, srcAgree = 0, yesAgree = 0; const cm = {};
  const pairs = [...haiku].filter(([i]) => openai.has(i)).map(([i, h]) => [h, openai.get(i)]);
  for (const [h, o] of pairs) { n++; if (h.states_rule === o.states_rule) agree++; if (h.source_type === o.source_type) srcAgree++; if ((h.states_rule === "yes") === (o.states_rule === "yes")) yesAgree++; cm[`${h.states_rule}>${o.states_rule}`] = (cm[`${h.states_rule}>${o.states_rule}`] ?? 0) + 1; }
  const po = agree / n; let pe = 0;
  for (const c of cats) pe += (pairs.filter(([h]) => h.states_rule === c).length / n) * (pairs.filter(([, o]) => o.states_rule === c).length / n);
  const py = yesAgree / n, hy = pairs.filter(([h]) => h.states_rule === "yes").length / n, oy = pairs.filter(([, o]) => o.states_rule === "yes").length / n;
  const pey = hy * oy + (1 - hy) * (1 - oy);
  md += `\n## Cross-family agreement (Haiku vs OpenAI, n=${n})\n\nstates_rule 3-way agreement ${(po * 100).toFixed(0)} % (kappa ${((po - pe) / (1 - pe)).toFixed(2)}); yes-vs-not agreement ${(py * 100).toFixed(0)} % (kappa ${((py - pey) / (1 - pey)).toFixed(2)}); source_type agreement ${((srcAgree / n) * 100).toFixed(0)} %.\nConfusion (haiku>openai): ${JSON.stringify(cm)}\n`;
}
writeFileSync(new URL(`REPORT-v2-${RATER}.md`, here), md);
console.log(md);
