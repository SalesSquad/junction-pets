// Small, dependency-free statistics used by the equity analysis.
// Everything here is deterministic; random draws take an explicit seed.

export const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;
export const sum = (xs) => xs.reduce((a, b) => a + b, 0);
export const round = (x, d = 2) => (Number.isFinite(x) ? Math.round(x * 10 ** d) / 10 ** d : null);

export function variance(xs) {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return sum(xs.map((x) => (x - m) ** 2)) / (xs.length - 1);
}

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function normalSampler(rand) {
  return () => {
    let u = 0;
    while (u === 0) u = rand();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand());
  };
}

// Standard normal CDF (Abramowitz-Stegun 7.1.26 via erf), abs error < 1.5e-7.
export function normalCdf(z) {
  const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
  const poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))));
  const erf = 1 - poly * Math.exp(-(z * z) / 2);
  return z >= 0 ? 0.5 * (1 + erf) : 0.5 * (1 - erf);
}

export function lnGamma(x) {
  const g = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
  let y = x;
  let tmp = x + 5.5;
  tmp -= (x + 0.5) * Math.log(tmp);
  let ser = 1.000000000190015;
  for (const c of g) ser += c / ++y;
  return -tmp + Math.log((2.5066282746310005 * ser) / x);
}

// Regularised lower incomplete gamma P(a, x).
export function gammaP(a, x) {
  if (x <= 0) return 0;
  if (x < a + 1) {
    let ap = a;
    let del = 1 / a;
    let s = del;
    for (let n = 0; n < 500; n += 1) {
      ap += 1;
      del *= x / ap;
      s += del;
      if (Math.abs(del) < Math.abs(s) * 1e-12) break;
    }
    return s * Math.exp(-x + a * Math.log(x) - lnGamma(a));
  }
  let b = x + 1 - a;
  let c = 1 / 1e-300;
  let d = 1 / b;
  let h = d;
  for (let i = 1; i < 500; i += 1) {
    const an = -i * (i - a);
    b += 2;
    d = an * d + b;
    if (Math.abs(d) < 1e-300) d = 1e-300;
    c = b + an / c;
    if (Math.abs(c) < 1e-300) c = 1e-300;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < 1e-12) break;
  }
  return 1 - Math.exp(-x + a * Math.log(x) - lnGamma(a)) * h;
}

// Gamma(shape, rate) CDF and quantile.
export const gammaCdf = (x, shape, rate) => gammaP(shape, x * rate);
export function gammaQuantile(p, shape, rate) {
  let lo = 0;
  let hi = Math.max(1, (shape / rate) * 4);
  while (gammaCdf(hi, shape, rate) < p) hi *= 2;
  for (let i = 0; i < 80; i += 1) {
    const mid = (lo + hi) / 2;
    if (gammaCdf(mid, shape, rate) < p) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// Exact Poisson interval for a count through the gamma relation.
export function poissonInterval(k, conf = 0.95) {
  const a = (1 - conf) / 2;
  return {
    low: k === 0 ? 0 : gammaQuantile(a, k, 1),
    high: gammaQuantile(1 - a, k + 1, 1),
  };
}

export function smr(observed, expected, conf = 0.95) {
  const ci = poissonInterval(observed, conf);
  return { smr: observed / expected, low: ci.low / expected, high: ci.high / expected };
}

// Gamma-Poisson empirical Bayes (Marshall 1991, global moment estimator).
// Small regions are pulled towards the national ratio in proportion to their noise.
export function empiricalBayesSmr(rows) {
  const O = sum(rows.map((r) => r.observed));
  const E = sum(rows.map((r) => r.expected));
  const m = O / E;
  const eBar = E / rows.length;
  const s2 = sum(rows.map((r) => r.expected * (r.observed / r.expected - m) ** 2)) / E;
  const A = s2 - m / eBar;
  const fullShrink = !(A > 1e-9);
  const alpha = fullShrink ? null : (m * m) / A;
  const beta = fullShrink ? null : m / A;
  return {
    priorMean: m,
    priorVariance: fullShrink ? 0 : A,
    rows: rows.map((r) => {
      if (fullShrink) return { ...r, shrunk: m, low: m, high: m, pAboveOne: m > 1 ? 1 : 0, weight: 0 };
      const shape = alpha + r.observed;
      const rate = beta + r.expected;
      return {
        ...r,
        shrunk: shape / rate,
        low: gammaQuantile(0.025, shape, rate),
        high: gammaQuantile(0.975, shape, rate),
        pAboveOne: 1 - gammaCdf(1, shape, rate),
        weight: r.expected / (r.expected + beta),
      };
    }),
  };
}

// Benjamini-Hochberg: returns a boolean per input p-value (true = discovery at level q).
export function benjaminiHochberg(pValues, q = 0.1) {
  const order = pValues.map((p, i) => [p, i]).sort((a, b) => a[0] - b[0]);
  let cut = -1;
  order.forEach(([p], rank) => { if (p <= ((rank + 1) / order.length) * q) cut = rank; });
  const out = new Array(pValues.length).fill(false);
  for (let r = 0; r <= cut; r += 1) out[order[r][1]] = true;
  return out;
}

export function weightedLinearRegression(xs, ys, ws = null) {
  const w = ws ?? xs.map(() => 1);
  const W = sum(w);
  const mx = sum(xs.map((x, i) => w[i] * x)) / W;
  const my = sum(ys.map((y, i) => w[i] * y)) / W;
  const sxx = sum(xs.map((x, i) => w[i] * (x - mx) ** 2));
  const sxy = sum(xs.map((x, i) => w[i] * (x - mx) * (ys[i] - my)));
  const syy = sum(ys.map((y, i) => w[i] * (y - my) ** 2));
  const slope = sxx === 0 ? 0 : sxy / sxx;
  return { slope, intercept: my - slope * mx, r: sxx === 0 || syy === 0 ? 0 : sxy / Math.sqrt(sxx * syy) };
}

// Slope and relative index of inequality across units ranked by a socioeconomic measure.
// rows: {value, ses, population}. Ridit 0 = least advantaged, 1 = most advantaged.
// sii = modelled value at the most advantaged end minus the least advantaged end.
export function inequalityIndices(rows, { bootstrap = 400, seed = 7 } = {}) {
  const compute = (sample) => {
    const sorted = [...sample].sort((a, b) => a.ses - b.ses);
    const total = sum(sorted.map((r) => r.population));
    let acc = 0;
    const ridit = sorted.map((r) => { const mid = (acc + r.population / 2) / total; acc += r.population; return mid; });
    const fit = weightedLinearRegression(ridit, sorted.map((r) => r.value), sorted.map((r) => r.population));
    const bottom = fit.intercept;
    const top = fit.intercept + fit.slope;
    return { sii: fit.slope, rii: bottom !== 0 ? top / bottom : null, r: fit.r, bottom, top };
  };
  const point = compute(rows);
  const rand = mulberry32(seed);
  const siis = [];
  for (let b = 0; b < bootstrap; b += 1) {
    const sample = rows.map(() => rows[Math.floor(rand() * rows.length)]);
    if (new Set(sample.map((r) => r.ses)).size < 3) continue;
    siis.push(compute(sample).sii);
  }
  siis.sort((a, b) => a - b);
  const q = (p) => siis[Math.min(siis.length - 1, Math.max(0, Math.floor(p * siis.length)))];
  return { ...point, siiLow: siis.length ? q(0.025) : null, siiHigh: siis.length ? q(0.975) : null, n: rows.length };
}

// Year-to-year noise of a panel, pooled over units: Var(first difference) / 2.
export function pooledNoiseSd(seriesList) {
  const diffs = [];
  for (const s of seriesList) {
    const years = Object.keys(s).map(Number).sort((a, b) => a - b);
    for (let i = 1; i < years.length; i += 1) {
      if (years[i] - years[i - 1] === 1) diffs.push(s[years[i]] - s[years[i - 1]]);
    }
  }
  if (diffs.length < 3) return null;
  return Math.sqrt(variance(diffs) / 2);
}

export function quantile(sorted, p) {
  if (!sorted.length) return null;
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}
