#!/usr/bin/env node
// Offline evaluation of improvement 1 on real Exa data from run2:
// grounded extraction from the answer lane vs the quantities a model wrote from memory (Haiku auto_en).
import { readFileSync, readdirSync } from "node:fs";
import { extractFromAnswerLane, extractQuantities, kindHints, sameQuantity } from "../src/warrant/lanes.ts";
const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const run = JSON.parse(readFileSync(new URL(`results/${readdirSync(new URL("results/", here)).filter((f) => f.startsWith("run2-")).sort().at(-1)}`, here), "utf8"));
const auto = Object.fromEntries([0, 1, 2].flatMap((i) => JSON.parse(readFileSync(new URL(`haiku/qw_out${i}.json`, here), "utf8"))).map((x) => [x.id, x]));
const refs = (e) => { const aq = e.anchors.flat().flatMap((a) => extractQuantities(a)); return extractQuantities(e.premise).filter((p) => aq.some((a) => sameQuantity(a, p)) || e.anchors.flat().some((a) => p.text.includes(a))); };
let n = 0, grounded = 0, modelRight = 0, modelWrong = 0, noRef = 0;
console.log("| errand | reference | grounded extraction (support) | model memory (Haiku) |\n|---|---|---|---|");
for (const e of spec.errands) {
  const row = run.rows.find((r) => r.errand === e.id && r.arm === "question" && !r.error);
  if (!row) continue;
  const ref = refs(e);
  if (!ref.length) { noRef++; continue; }
  n++;
  const hints = kindHints(e.question);
  const kind = Object.entries(hints).sort((a, b) => b[1] - a[1])[0]?.[0];
  const ex = extractFromAnswerLane(row.top.map((t) => ({ url: t.url, title: t.title, highlights: t.highlights })), hints);
  const g = ex.quantity && ref.some((q) => sameQuantity(q, ex.quantity));
  if (g) grounded++;
  const mq = extractQuantities(auto[e.id].cite_en).filter((q) => !kind || q.kind === kind);
  const mRight = mq.some((q) => ref.some((r) => sameQuantity(r, q)));
  const mWrong = !mRight && mq.length > 0;
  if (mRight) modelRight++;
  if (mWrong) modelWrong++;
  console.log(`| ${e.id} | ${ref.map((q) => q.text).join(", ")} | ${ex.quantity?.text ?? "—"} (${ex.support}) ${g ? "✓" : "✗"} | ${mq.map((q) => q.text).join(", ") || "—"} ${mRight ? "✓" : mWrong ? "✗ wrong" : "—"} |`);
}
console.log(`\nerrands with a reference quantity: ${n} (skipped ${noRef} without one)`);
console.log(`grounded extraction correct: ${grounded}/${n} · model memory correct: ${modelRight}/${n} · model memory states a WRONG number: ${modelWrong}/${n}`);
