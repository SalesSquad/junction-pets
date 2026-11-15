#!/usr/bin/env node
// Offline simulation: fuse two arms' rankings (reciprocal rank fusion, k=60), dedupe by URL,
// take the top 5, and score with the consensus judge labels already collected.
import { readFileSync, readdirSync } from "node:fs";
const here = new URL(".", import.meta.url);
const { run, keys } = JSON.parse(readFileSync(new URL("judge/keymap.json", here), "utf8"));
const runData = JSON.parse(readFileSync(new URL(`results/${run}`, here), "utf8"));
const H = new Map(), O = new Map();
for (const f of readdirSync(new URL("judge/", here)).filter((f) => /^labels\d+\.json$/.test(f))) for (const l of JSON.parse(readFileSync(new URL(`judge/${f}`, here), "utf8"))) H.set(l.item, l);
for (const l of JSON.parse(readFileSync(new URL("judge/openai_labels.json", here), "utf8"))) O.set(l.item, l);
const cons = (h, o) => ({ yes: h?.states_rule === "yes" && o?.states_rule === "yes", legal: h?.source_type === "legal_text" && o?.source_type === "legal_text", match: h?.jurisdiction_match !== false && o?.jurisdiction_match !== false });
const label = new Map(); // errand|url -> consensus label (any arm that returned it)
keys.forEach((key, item) => { const [e, arm, rank] = key.split("|"); const row = runData.rows.find((r) => r.errand === e && r.arm === arm && !r.error); const url = row?.top[Number(rank)]?.url; if (url) label.set(`${e}|${url}`, cons(H.get(item), O.get(item))); });
const ranked = (e, arm) => runData.rows.find((r) => r.errand === e && r.arm === arm && !r.error)?.top.map((t) => t.url) ?? null;
const fuse = (a, b) => { const s = new Map(); for (const list of [a, b]) list.forEach((u, i) => s.set(u, (s.get(u) ?? 0) + 1 / (60 + i + 1))); return [...s].sort((x, y) => y[1] - x[1]).map(([u]) => u).slice(0, 5); };
const errands = [...new Set(keys.map((k) => k.split("|")[0]))];
const lists = {
  keywords: (e) => ranked(e, "keywords"), question: (e) => ranked(e, "question"), citation: (e) => ranked(e, "citation"), auto_en: (e) => ranked(e, "auto_en"),
  "question+citation": (e) => { const a = ranked(e, "question"), b = ranked(e, "citation"); return a && b ? fuse(a, b) : null; },
  "question+auto_en": (e) => { const a = ranked(e, "question"), b = ranked(e, "auto_en"); return a && b ? fuse(a, b) : null; },
  "keywords+citation": (e) => { const a = ranked(e, "keywords"), b = ranked(e, "citation"); return a && b ? fuse(a, b) : null; },
};
const metric = (e, urls) => { const ls = urls.map((u) => label.get(`${e}|${u}`)).filter(Boolean); const yes = ls.filter((l) => l.yes && l.match); return { anyYes: yes.length > 0 ? 1 : 0, legalYes: yes.filter((l) => l.legal).length, anyLegalYes: yes.some((l) => l.legal) ? 1 : 0, top1: ls[0]?.yes && ls[0]?.match ? 1 : 0, both: yes.length > 0 && yes.some((l) => l.legal) ? 1 : 0 }; };
console.log(`consensus labels; errands with all arms: ${errands.length}\n`);
console.log("| Arm | any result states rule | legal texts stating rule (mean) | ≥1 legal text states rule | top-1 states rule |\n|---|---|---|---|---|");
for (const [name, f] of Object.entries(lists)) {
  const ms = errands.map((e) => { const u = f(e); return u ? metric(e, u) : null; }).filter(Boolean);
  const avg = (k) => (ms.reduce((s, m) => s + m[k], 0) / ms.length).toFixed(2);
  console.log(`| ${name} (n=${ms.length}) | ${avg("anyYes")} | ${avg("legalYes")} | ${avg("anyLegalYes")} | ${avg("top1")} |`);
}
