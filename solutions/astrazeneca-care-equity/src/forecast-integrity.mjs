// A saved prediction file is not evidence of a valid temporal evaluation.
// Historical artifacts remain on disk; only eligible forecasts enter the app.
function validSplit(split) {
  const ints = values => Array.isArray(values) && values.length && values.every(Number.isInteger)
    && values.every((v, i) => !i || v > values[i - 1]);
  if (!split || split.protocol !== 'target-year-disjoint-v1' || !ints(split.trainOrigins)
      || Math.max(...split.trainOrigins) > 2020 || split.trainLabelsThrough !== 2021
      || JSON.stringify(split.validationOrigins) !== '[2021]'
      || JSON.stringify(split.testOrigins) !== '[2023]'
      || JSON.stringify(split.horizons) !== '[1,2]') return false;
  const targets = (origins, cap = Infinity) => [...new Set(origins.flatMap(y => [y + 1, y + 2]).filter(y => y <= cap))].sort((a, b) => a - b);
  return ['train', 'validation', 'test'].every(group => {
    const expected = targets(split[group + 'Origins'], group === 'train' ? 2021 : Infinity);
    return expected.length && JSON.stringify(split.targetYears?.[group]) === JSON.stringify(expected);
  });
}

export function auditForecast(forecast, { sha256, historicalAudit = null } = {}) {
  if (!forecast) return { status: 'UNAVAILABLE', reasons: ['No saved forecast.'], indicators: {}, forecast: null };
  const reasons = [];
  const contract = forecast.evaluation;
  const matchesHistory = Boolean(historicalAudit && sha256 && historicalAudit.artifactSha256 === sha256);
  if (matchesHistory) reasons.push(...historicalAudit.reasons);
  const split = contract?.split;
  const periods = split?.targetYears;
  const groups = ['train', 'validation', 'test'];
  const validYears = periods && groups.every(k => Array.isArray(periods[k]) && periods[k].length && periods[k].every(Number.isInteger));
  const overlap = validYears && groups.some((a, i) => groups.slice(i + 1).some(b => periods[a].some(y => periods[b].includes(y))));
  const ordered = validYears && Math.max(...periods.train) < Math.min(...periods.validation)
    && Math.max(...periods.validation) < Math.min(...periods.test);
  if (!contract || !validSplit(split) || !validYears || overlap || !ordered
      || !/^[a-f0-9]{64}$/.test(contract?.panelSha256 || '')) {
    reasons.push('A source-bound evaluation with disjoint train, validation and test target years is required.');
  }
  const indicators = {};
  const allowed = {};
  for (const [key, rows] of Object.entries(forecast.forecasts || {})) {
    const item = contract?.indicators?.[key];
    const historical = historicalAudit?.indicators?.[key];
    const problems = [];
    if (matchesHistory && historical?.reason) problems.push(historical.reason);
    const method = forecast.metrics?.[key]?.chosen;
    if (!item || item.chosen !== method || !method) problems.push('No verified method selection for this indicator.');
    const horizons = ['h1', 'h2'].filter(h => item?.horizons?.[h]?.status === 'ELIGIBLE'
      && Number.isInteger(item.horizons[h].validationN) && item.horizons[h].validationN > 0
      && Number.isInteger(item.horizons[h].testN) && item.horizons[h].testN > 0
      && (method !== 'transformer' && method !== 'ridge'
        || Number.isInteger(item.horizons[h].trainingN) && item.horizons[h].trainingN > 0));
    if (!horizons.length) problems.push('No horizon has sufficient training, validation and test evidence.');
    const clean = {};
    if (!reasons.length && !problems.length) {
      for (const [county, row] of Object.entries(rows)) {
        const copy = { lastYear: row.lastYear, lastValue: row.lastValue, pWorse: {}, pBelowThreshold: row.pBelowThreshold ? {} : null };
        for (const h of horizons) {
          const q = row[h];
          const values = q && ['q05', 'q25', 'q50', 'q75', 'q95'].map(k => q[k]);
          if (!values || !values.every(Number.isFinite) || values.some((v, i) => i && v < values[i - 1])
              || values[0] >= values[4] || !Number.isInteger(q.year) || q.year !== row.lastYear + Number(h.slice(1))) continue;
          copy[h] = q;
          // Quantile interpolation is descriptive, not calibrated risk evidence.
          // Do not publish model probabilities as decision-ready warnings.
        }
        if (copy.h1 || copy.h2) clean[county] = copy;
      }
    }
    if (Object.keys(clean).length) allowed[key] = clean;
    indicators[key] = { status: Object.keys(clean).length ? 'ELIGIBLE' : 'WITHHELD', reasons: problems, eligibleHorizons: horizons };
  }
  const accepted = Object.keys(allowed).length;
  return {
    status: accepted ? (accepted === Object.keys(indicators).length ? 'ELIGIBLE' : 'PARTIAL') : 'WITHHELD',
    artifactSha256: sha256, reasons, indicators,
    note: 'Eligibility checks evidence structure, not clinical usefulness or independent scientific approval.',
    forecast: accepted ? { ...forecast, forecasts: allowed, metrics: Object.fromEntries(Object.keys(allowed).map(k => [k, forecast.metrics[k]])) } : null,
  };
}
