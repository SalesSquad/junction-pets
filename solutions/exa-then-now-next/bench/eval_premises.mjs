#!/usr/bin/env node
// Offline evaluation of multi-premise extraction and the explainer-vs-model leg of the three-way check
// on real Exa answer-lane data (run2). The legal-text leg needs live fetches (bench/run3.mjs).
import { readFileSync, readdirSync } from "node:fs";
import { analyseTiers, extractPremises, extractQuantities, sameQuantity } from "../src/warrant/lanes.ts";
const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const run = JSON.parse(readFileSync(new URL(`results/${readdirSync(new URL("results/", here)).filter((f) => f.startsWith("run2-")).sort().at(-1)}`, here), "utf8"));
const auto = Object.fromEntries([0, 1, 2].flatMap((i) => JSON.parse(readFileSync(new URL(`haiku/qw_out${i}.json`, here), "utf8"))).map((x) => [x.id, x]));
const refs = (e) => { const aq = e.anchors.flat().flatMap((a) => extractQuantities(a)); return extractQuantities(e.premise).filter((p) => aq.some((a) => sameQuantity(a, p)) || e.anchors.flat().some((a) => p.text.includes(a))); };
let n = 0, covered = 0, outcomeOk = 0, flagged = 0, flaggedWrong = 0, wrongTotal = 0, clarifications = 0, resolvedTiers = 0;
const tierLog = [];
console.log("| errand | reference | premises (role: value) | covered | model prior vs explainer |\n|---|---|---|---|---|");
for (const e of spec.errands) {
  const row = run.rows.find((r) => r.errand === e.id && r.arm === "question" && !r.error);
  const ref = refs(e);
  if (!row || !ref.length) continue;
  n++;
  const ps = extractPremises(row.top.map((t) => ({ url: t.url, title: t.title, highlights: t.highlights })), e.question);
  const cov = ps.some((p) => ref.some((r) => sameQuantity(r, p.quantity)));
  const out = ps.find((p) => p.role === "outcome");
  const outOk = !!out && ref.some((r) => sameQuantity(r, out.quantity));
  if (cov) covered++;
  if (outOk) outcomeOk++;
  // Three-way, explainer vs model leg: does the model's number (same unit) disagree with any extracted premise?
  const prior = extractQuantities(auto[e.id].cite_en);
  const disagreements = ps.filter((p) => { const su = prior.filter((x) => x.kind === p.quantity.kind && x.unit === p.quantity.unit); return su.length && !su.some((x) => sameQuantity(x, p.quantity)); });
  const lane = row.top.map((t) => ({ url: t.url, title: t.title, highlights: t.highlights }));
  const known = ps.filter((p) => p.role === "threshold").map((p) => p.quantity);
  for (const p of ps.filter((p) => p.role === "outcome")) {
    const ta = analyseTiers(lane, p, e.question, known);
    if (ta?.resolved) { resolvedTiers++; tierLog.push(`${e.id}: tiers ${ta.tiers.map((x) => x.value.text).join("/")} resolved to ${ta.resolved.value.text} by ${ta.resolved.by}`); }
    if (ta?.clarify) { clarifications++; tierLog.push(`${e.id}: ASK "${ta.clarify.question}" options: ${ta.clarify.options.map((o) => o.slice(-40)).join(" | ")}`); break; }
  }
  const anyWrong = !cov;
  if (anyWrong) wrongTotal++;
  if (disagreements.length) { flagged++; if (anyWrong) flaggedWrong++; }
  console.log(`| ${e.id} | ${ref.map((q) => q.text).join(", ")} | ${ps.map((p) => `${p.role[0]}: ${p.quantity.text}`).join("; ") || "—"} | ${cov ? "✓" : "✗"} | ${disagreements.length ? `flag: ${disagreements.map((p) => p.quantity.text).join(", ")}` : "agree/none"} |`);
}
console.log(`\nerrands ${n}: reference covered by some premise ${covered}/${n}; primary outcome correct ${outcomeOk}/${n}`);
console.log(`tiers: ${resolvedTiers} resolved from the question, ${clarifications} errands would ask a clarifying question`);
for (const l of tierLog) console.log(`  - ${l}`);
console.log(`model-vs-explainer flags ${flagged}/${n}; of the ${wrongTotal} errands where extraction missed the reference, ${flaggedWrong} were flagged`);
