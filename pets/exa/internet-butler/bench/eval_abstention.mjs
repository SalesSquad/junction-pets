#!/usr/bin/env node
// Proofscape-style evaluation of the compiler's answer leg on real Exa data (run2):
// coverage (share answered rather than abstained/asked) and accuracy among answered, with Wilson 95 % CIs,
// plus recall per quantity kind. NEEDS_INFO is abstention: it should buy accuracy, not hide errors.
import { readFileSync, readdirSync } from "node:fs";
import { analyseTiers, extractPremises, extractQuantities, sameQuantity } from "../src/warrant/lanes.ts";
const here = new URL(".", import.meta.url);
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const run = JSON.parse(readFileSync(new URL(`results/${readdirSync(new URL("results/", here)).filter((f) => f.startsWith("run2-")).sort().at(-1)}`, here), "utf8"));
const refs = (e) => { const aq = e.anchors.flat().flatMap((a) => extractQuantities(a)); return extractQuantities(e.premise).filter((p) => aq.some((a) => sameQuantity(a, p)) || e.anchors.flat().some((a) => p.text.includes(a))); };
const wilson = (k, n, z = 1.96) => { if (!n) return [0, 1]; const p = k / n, d = 1 + z * z / n, c = p + z * z / (2 * n), m = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [(c - m) / d, (c + m) / d]; };
const pct = (x) => `${(x * 100).toFixed(0)} %`;
const rows = [];
for (const e of spec.errands) {
  const row = run.rows.find((r) => r.errand === e.id && r.arm === "question" && !r.error);
  const ref = refs(e);
  if (!row || !ref.length) continue;
  const lane = row.top.map((t) => ({ url: t.url, title: t.title, highlights: t.highlights }));
  const ps = extractPremises(lane, e.question);
  const known = ps.filter((p) => p.role === "threshold").map((p) => p.quantity);
  const outcomes = ps.filter((p) => p.role === "outcome");
  let ambiguousAll = outcomes.length > 0;
  for (const p of outcomes) {
    const t = analyseTiers(lane, p, e.question, known);
    if (t?.resolved) p.quantity = t.resolved.value;
    if (!t?.clarify) ambiguousAll = false;
  }
  const answered = ps.length > 0 && !ambiguousAll;
  const correct = answered && ps.some((p) => ref.some((r) => sameQuantity(r, p.quantity)));
  rows.push({ id: e.id, kind: ref[0].kind, answered, correct });
}
const n = rows.length, ans = rows.filter((r) => r.answered), ok = ans.filter((r) => r.correct);
const [cl, ch] = wilson(ans.length, n), [al, ah] = wilson(ok.length, ans.length);
console.log(`errands with a reference: ${n}`);
console.log(`coverage (answered): ${ans.length}/${n} = ${pct(ans.length / n)} (95 % CI ${pct(cl)}–${pct(ch)})`);
console.log(`accuracy among answered: ${ok.length}/${ans.length} = ${pct(ok.length / ans.length)} (95 % CI ${pct(al)}–${pct(ah)})`);
console.log(`abstained: ${rows.filter((r) => !r.answered).map((r) => r.id).join(", ") || "none"}`);
for (const kind of [...new Set(rows.map((r) => r.kind))]) {
  const k = rows.filter((r) => r.kind === kind), c = k.filter((r) => r.correct);
  const [l, h] = wilson(c.length, k.length);
  console.log(`  recall ${kind.padEnd(8)} ${c.length}/${k.length} (95 % CI ${pct(l)}–${pct(h)})`);
}
console.log("Caveat: n is small and the rules were developed on these errands; held-out data is required.");
