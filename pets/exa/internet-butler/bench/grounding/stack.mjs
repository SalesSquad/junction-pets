#!/usr/bin/env node
// Learned combiner over typed judgments (stacking), evaluated with grouped cross-validation so that
// no group (a ContractNLI clause type, a SARA case) is in both training and test folds.
// Features: the six table probabilities from each judge (logit-transformed). Model: L2-regularised
// logistic regression, fitted by gradient descent; class-balanced weights. Zero API cost: reads the
// per-row probabilities that run.mjs saved.
// Usage: node bench/grounding/stack.mjs bench/grounding/results/<stem>.json [--group=dataset|case]
import { readFileSync } from "node:fs";
import { pct } from "../stats.mjs";

const file = process.argv[2];
const groupBy = process.argv.find((a) => a.startsWith("--group="))?.slice(8) ?? "dataset";
const rows = JSON.parse(readFileSync(file, "utf8")).filter((r) => r.jev && r.luna);
const NAMES = ["supported", "numbers_match", "names_match", "contradicts", "adds"];
const logit = (p) => Math.log(Math.min(1 - 1e-4, Math.max(1e-4, p)) / (1 - Math.min(1 - 1e-4, Math.max(1e-4, p))));
const feats = {
  "jev single": (r) => [logit(r.jev.supported)],
  "luna single": (r) => [logit(r.luna.supported)],
  "jev+luna single": (r) => [logit(r.jev.supported), logit(r.luna.supported)],
  "jev table": (r) => NAMES.map((n) => logit(r.jev[n])),
  "jev+luna table": (r) => [...NAMES.map((n) => logit(r.jev[n])), ...NAMES.map((n) => logit(r.luna[n]))],
};
const groupOf = (r) => (groupBy === "case" ? String(r.case ?? r.id).replace(/_(pos|neg)$/, "") : r.dataset);

function fit(X, y, { lambda = 0.1, epochs = 600, lr = 0.1 } = {}) {
  const d = X[0].length;
  const w = new Array(d + 1).fill(0);
  const pos = y.filter((v) => v === 1).length, neg = y.length - pos;
  const cw = y.map((v) => (v === 1 ? y.length / (2 * pos) : y.length / (2 * neg)));
  for (let e = 0; e < epochs; e++) {
    const g = new Array(d + 1).fill(0);
    X.forEach((x, i) => {
      const z = w[d] + x.reduce((s, v, k) => s + v * w[k], 0);
      const err = (1 / (1 + Math.exp(-z)) - y[i]) * cw[i];
      x.forEach((v, k) => (g[k] += err * v));
      g[d] += err;
    });
    for (let k = 0; k < d; k++) w[k] -= (lr * (g[k] / X.length + lambda * w[k]));
    w[d] -= (lr * g[d]) / X.length;
  }
  return (x) => 1 / (1 + Math.exp(-(w[d] + x.reduce((s, v, k) => s + v * w[k], 0))));
}

const bacc = (ys, ps) => {
  const pos = ys.map((y, i) => [y, ps[i]]).filter(([y]) => y === 1), neg = ys.map((y, i) => [y, ps[i]]).filter(([y]) => y === 0);
  return (pos.filter(([, p]) => p > 0.5).length / pos.length + neg.filter(([, p]) => p <= 0.5).length / neg.length) / 2;
};

const groups = [...new Set(rows.map(groupOf))];
const K = Math.min(10, groups.length);
const foldOf = new Map(groups.map((g, i) => [g, i % K]));
console.log(`${rows.length} rows, ${groups.length} groups (${groupBy}), ${K}-fold grouped cross-validation\n`);
console.log("| features | zero-shot (p > 0.5) | stacked (cross-validated) |\n|---|---|---|");
for (const [name, f] of Object.entries(feats)) {
  const X = rows.map(f), y = rows.map((r) => r.label);
  // Zero-shot: the first feature's own probability (single) or every table row passing (table).
  const zero = name.includes("table") ? rows.map((r) => (r.jev.supported > 0.5 && r.jev.contradicts <= 0.5 ? 1 : 0)) : X.map((x) => 1 / (1 + Math.exp(-x.reduce((a, b) => a + b, 0) / x.length)));
  const preds = new Array(rows.length);
  for (let k = 0; k < K; k++) {
    const tr = rows.map((_, i) => i).filter((i) => foldOf.get(groupOf(rows[i])) !== k);
    const te = rows.map((_, i) => i).filter((i) => foldOf.get(groupOf(rows[i])) === k);
    const m = fit(tr.map((i) => X[i]), tr.map((i) => y[i]));
    te.forEach((i) => (preds[i] = m(X[i])));
  }
  console.log(`| ${name} | ${pct(bacc(y, zero))} | ${pct(bacc(y, preds))} |`);
}
