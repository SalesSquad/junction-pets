// Small, dependency-free statistics for evaluation runs.
//   wilson         binomial 95 % interval
//   clusterBootstrap  CI that resamples whole clusters (e.g. all variants of one rule), because items
//                  inside a cluster are correlated and a plain bootstrap would be too narrow
//   mcnemar        exact paired test of two judges on the same items
//   riskCoverage   selective prediction: error among accepted vs share accepted, and AURC
//   lttThreshold   Learn-then-Test (Angelopoulos et al. 2021) with fixed-sequence testing: the lowest
//                  acceptance threshold whose false-accept rate is <= alpha with probability >= 1 - delta,
//                  valid when calibration and future items are exchangeable

export function wilson(k, n, z = 1.96) {
  if (!n) return [0, 1];
  const p = k / n, d = 1 + (z * z) / n, c = p + (z * z) / (2 * n), m = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [(c - m) / d, (c + m) / d];
}

export const pct = (x) => `${Math.round(x * 100)} %`;
export const ci = (k, n) => { const [a, b] = wilson(k, n); return `${k}/${n} (${pct(n ? k / n : 0)}, 95 % CI ${Math.round(a * 100)}–${Math.round(b * 100)})`; };

function mulberry32(seed) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/** Percentile CI of `metric(items)` when whole clusters are resampled with replacement. */
export function clusterBootstrap(items, clusterOf, metric, { B = 2000, seed = 7, level = 0.95 } = {}) {
  const groups = new Map();
  for (const x of items) groups.set(clusterOf(x), [...(groups.get(clusterOf(x)) ?? []), x]);
  const keys = [...groups.keys()];
  const rnd = mulberry32(seed);
  const stats = [];
  for (let b = 0; b < B; b++) {
    const sample = [];
    for (let i = 0; i < keys.length; i++) sample.push(...groups.get(keys[Math.floor(rnd() * keys.length)]));
    const v = metric(sample);
    if (Number.isFinite(v)) stats.push(v);
  }
  stats.sort((a, b) => a - b);
  const q = (p) => stats[Math.min(stats.length - 1, Math.max(0, Math.floor(p * stats.length)))];
  return { estimate: metric(items), lo: q((1 - level) / 2), hi: q(1 - (1 - level) / 2), clusters: keys.length };
}

const lnChoose = (n, k) => { let s = 0; for (let i = 1; i <= k; i++) s += Math.log(n - k + i) - Math.log(i); return s; };
/** P(X <= k) for X ~ Binomial(n, p). */
export function binomCdf(k, n, p) {
  if (k < 0) return 0;
  if (k >= n) return 1;
  let s = 0;
  for (let i = 0; i <= k; i++) s += Math.exp(lnChoose(n, i) + i * Math.log(p) + (n - i) * Math.log1p(-p));
  return Math.min(1, s);
}

/** Exact two-sided McNemar test: a, b are boolean arrays (correct?) for the same items. */
export function mcnemar(a, b) {
  let onlyA = 0, onlyB = 0;
  a.forEach((x, i) => { if (x && !b[i]) onlyA++; else if (!x && b[i]) onlyB++; });
  const n = onlyA + onlyB;
  const p = n ? Math.min(1, 2 * binomCdf(Math.min(onlyA, onlyB), n, 0.5)) : 1;
  return { onlyA, onlyB, p };
}

/**
 * Selective prediction. `score` = confidence that the item should be accepted, `good` = it really
 * should. Sweeping the threshold from high to low gives (coverage, risk) points; risk = share of
 * accepted items that should not have been. AURC = mean risk over coverage (lower is better).
 */
export function riskCoverage(items, score, good) {
  const xs = items.map((x) => ({ s: score(x), g: good(x) })).sort((a, b) => b.s - a.s);
  const pts = [];
  let bad = 0;
  xs.forEach((x, i) => { if (!x.g) bad++; pts.push({ coverage: (i + 1) / xs.length, risk: bad / (i + 1), threshold: x.s }); });
  const aurc = pts.reduce((s, p) => s + p.risk, 0) / (pts.length || 1);
  return { points: pts, aurc };
}

/**
 * Learn-then-Test with fixed-sequence testing over thresholds from strict to lenient.
 * Loss = a forged item accepted. H0(t): false-accept rate(t) > alpha, tested with the exact binomial
 * p-value P(Bin(n_forged, alpha) <= accepted_forged(t)). Thresholds are tested in order and the
 * sequence stops at the first that is not rejected, so the family-wise error stays <= delta.
 */
export function lttThreshold(items, score, forged, { alpha = 0.05, delta = 0.1, grid } = {}) {
  const bad = items.filter(forged);
  const n = bad.length;
  const ts = grid ?? Array.from({ length: 99 }, (_, i) => 0.99 - i * 0.01);
  let chosen = null;
  const tested = [];
  for (const t of ts) {
    const k = bad.filter((x) => score(x) > t).length;
    const p = binomCdf(k, n, alpha);
    tested.push({ t, k, n, p });
    if (p <= delta) chosen = t;
    else break;
  }
  return { threshold: chosen, alpha, delta, nForged: n, tested };
}
