// From measured gaps to costed, evidence-bound action proposals.
//
// Two tracks, kept apart on purpose because their evidence differs:
//   timeliness  - days removed from the symptomatic pathway, translated into a
//                 SCENARIO range of deaths postponed. Optimised under a budget
//                 with an explicit inequality-aversion weight.
//   detection   - screening participation, reported as people additionally
//                 screened and share of the 80% target gap closed. No mortality
//                 claim is made for this track.
// Every effect size points to a row in data/evidence/literature-v1.json. Every
// cost is a planning ASSUMPTION the user can change; none is a quoted price.
import { mulberry32, normalCdf, normalSampler, quantile, round, sum } from './stats.mjs';

export const ASSUMPTIONS = {
  hrPer4Weeks: { value: 1.06, low: 1.0, high: 1.13, label: 'Mortality hazard ratio per 4 weeks of delay', basis: 'Hanna 2020 measured this for delay of treatment (1.06 surgery, up to 1.13 adjuvant colorectal). Applying it to days saved before diagnosis is an assumption; the lower bound 1.00 means no effect.', evidence: ['hanna-2020-surgery-colon', 'hanna-2020-surgery-breast', 'hanna-2020-surgery-lung', 'hanna-2020-adjuvant-colorectal'] },
  symptomaticPrimaryCareShare: { value: 0.5, low: 0.3, high: 0.7, label: 'Share of cancer deaths in patients who entered through symptoms and primary care', basis: 'Planning assumption; not available from open data.', evidence: [] },
  fastRouteShare: { value: 0.45, low: 0.3, high: 0.6, label: 'Share of primary-care-route patients using private or occupational care', basis: 'Kuitunen 2026 cohort: 39 private/occupational vs 48 public primary care patients. Scaled by each county\'s private-referral share relative to the national value.', evidence: ['kuitunen-2026-route-means'] },
  routeGapDays: { value: 84, low: 51, high: 84, label: 'Mean symptom-to-treatment difference, public minus private/occupational route (days)', basis: 'Kuitunen 2026: means 207 vs 123 days (medians 127 vs 76). One cancer type (DLBCL), used as a transferable prior.', evidence: ['kuitunen-2026-route-means', 'kuitunen-2026-route-medians'] },
  routeGapClosed: { value: 0.5, low: 0.25, high: 0.75, label: 'Share of the route gap an equal fast lane closes', basis: 'Scenario parameter. No trial measures this in Finland.', evidence: [] },
  pathwayDays: { value: 17, low: 15, high: 19, label: 'Days removed from the diagnostic interval by standardised timed pathways', basis: 'Denmark, before vs after cancer patient pathways (Jensen 2015).', evidence: ['jensen-2015-cpp-interval'] },
  navigationHr: { value: 1.51, low: 1.23, high: 1.84, label: 'Rate ratio of reaching diagnosis for navigated patients already delayed over 90 days', basis: 'Freund 2014, US safety-net populations.', evidence: ['freund-2014-navigation'] },
  ldctRateRatio: { value: 0.76, low: 0.61, high: 0.94, label: 'Lung-cancer mortality rate ratio in people screened with low-dose CT', basis: 'NELSON trial, men, 10 years.', evidence: ['nelson-2020-ldct'] },
  ldctReach: { value: 0.25, low: 0.1, high: 0.4, label: 'Share of lung-cancer deaths arising in the group a targeted programme would screen', basis: 'Planning assumption (eligibility x uptake).', evidence: [] },
  selfSamplingPoints: { value: 3.0, low: 1.5, high: 4.5, label: 'Participation gained by adding HPV self-sampling to reminders (percentage points)', basis: 'Finland: 79.2% to 82.2% (Virtanen 2015).', evidence: ['virtanen-2015-attendance-steps', 'virtanen-2011-selfsampling-fi'] },
  costs: {
    label: 'Yearly cost per resident (EUR), planning assumptions',
    'timed-pathways': 1.5, 'equal-fast-lane': 3.0, navigation: 2.0, 'ldct-pilot': 4.0, 'self-sampling': 0.6, 'screening-reminders': 0.4, 'ai-mammography': 0.5,
  },
};

export const INTERVENTIONS = [
  {
    id: 'pathway-timestamps', track: 'enabling', level: 'national', stage: 'treatment',
    title: 'Record four pathway timestamps for every cancer patient',
    action: 'Add first contact, referral, diagnosis and first treatment dates, plus entry route, to the national cancer quality register and publish county-level medians quarterly.',
    owner: 'FICAN with THL and the Finnish Cancer Registry', strategyMeasure: 'Sub-objective 3.2 (national quality register) and 3.1 measure 4 (national indicators)',
    mechanism: 'The Goal 3 indicator "treatment within target times" cannot be computed from open data today. Without it no county can see where its own pathway loses time.',
    metric: 'Share of new cancer cases with all four timestamps recorded', evidence: ['fi-strategy-goal3', 'fi-strategy-3-1-no-national-pathways'],
    unknown: 'No health effect is modelled: this is the measurement that makes the other actions accountable.',
  },
  {
    id: 'timed-pathways', track: 'timeliness', level: 'county', stage: 'referral',
    title: 'Standardised, timed cancer pathways with a fast-track referral',
    action: 'Adopt national cancer-specific pathways with maximum times per step and a single fast-track referral from primary care, following the Danish and Swedish model.',
    owner: 'Wellbeing services county, coordinated nationally by FICAN', strategyMeasure: 'Sub-objective 3.1, measures 1-2',
    mechanism: 'One referral criterion and booked slots replace sequential queues between primary care, imaging and the specialist clinic.',
    metric: 'specialist_wait_over_6m', evidence: ['jensen-2015-cpp-interval', 'jensen-2017-cpp-excess-hazard', 'fi-strategy-3-1-no-national-pathways'],
    unknown: 'Danish evidence is before/after without a control group. Patients left outside the pathway waited 4 days longer, so coverage must be monitored.',
  },
  {
    id: 'equal-fast-lane', track: 'timeliness', level: 'county', stage: 'primary_care',
    title: 'The same fast lane in public primary care that occupational care already gives',
    action: 'Same-week physician assessment and direct-access diagnostics for red-flag symptoms in public health centres, regardless of employment or insurance.',
    owner: 'Wellbeing services county primary care', strategyMeasure: 'Sub-objective 3.1 (equal, timely treatment)',
    mechanism: 'In the Finnish DLBCL cohort the public route took a mean 207 days from symptom to treatment against 123 days through private or occupational care; most of the difference arises before the specialist visit.',
    metric: 'gp_wait_over_7d', evidence: ['kuitunen-2026-route-means', 'kuitunen-2026-route-medians', 'tokola-2025-dlbcl-pfs'],
    unknown: 'The route gap is observational and from one cancer type. How much of it a fast lane closes is a scenario parameter, not a measured effect.',
  },
  {
    id: 'navigation', track: 'timeliness', level: 'county', stage: 'primary_care',
    title: 'Patient navigators for people whose work-up has stalled',
    action: 'A named nurse navigator contacts every patient whose suspected-cancer work-up passes 90 days without a diagnosis, and books the missing step.',
    owner: 'Wellbeing services county cancer centre', strategyMeasure: 'Sub-objective 3.3 (support as part of the pathway)',
    mechanism: 'Targets the long tail of the pathway, where patients with fewer resources are over-represented.',
    metric: 'gp_wait_over_3m', evidence: ['freund-2014-navigation', 'zai-2025-stage-education'],
    unknown: 'Trial evidence is from the United States; transfer to Finnish primary care is untested.',
  },
  {
    id: 'ldct-pilot', track: 'timeliness', level: 'county', stage: 'detection',
    title: 'Targeted low-dose CT lung screening pilot',
    action: 'Invite current and former heavy smokers aged 50-74 to low-dose CT screening, starting where age-standardised lung cancer mortality is highest.',
    owner: 'Wellbeing services county with the national screening steering group', strategyMeasure: 'Sub-objective 2.3 (screening programmes) and the Goal 3 lung survival target',
    mechanism: 'Finnish five-year lung cancer survival is far below Sweden and Norway; screening shifts diagnoses to operable stages.',
    metric: 'smr_lung', evidence: ['nelson-2020-ldct', 'fi-strategy-goal3'],
    unknown: 'Benefit accrues over about ten years and only in the screened group. Reach in Finland is an assumption.',
  },
  {
    id: 'self-sampling', track: 'detection', level: 'county', stage: 'detection', programme: 'screen_cervix',
    title: 'HPV self-sampling kits for cervical screening non-attenders',
    action: 'Mail a self-sampling kit with the second reminder to everyone who has not attended.',
    owner: 'Wellbeing services county screening unit', strategyMeasure: 'Objective 2 target: 80% participation in every county',
    mechanism: 'Removes the appointment, travel and language barriers for the people who do not come.',
    metric: 'screen_cervix', evidence: ['virtanen-2015-attendance-steps', 'virtanen-2011-selfsampling-fi', 'arbyn-2018-selfsampling', 'fi-strategy-goal2-screening'],
    unknown: 'The Finnish gain over a reminder letter is about 3 points, far smaller than the international pooled estimate.',
  },
  {
    id: 'screening-reminders', track: 'detection', level: 'county', stage: 'detection', programme: 'screen_colorectal',
    title: 'Reminder and multilingual re-invitation for colorectal screening',
    action: 'Send a second kit with plain-language, multilingual instructions to non-responders; measure the gain as a stepped pilot.',
    owner: 'Wellbeing services county screening unit', strategyMeasure: 'Objective 2 target: 80% participation in every county',
    mechanism: 'Transfers the reminder protocol proven in Finnish cervical screening.',
    metric: 'screen_colorectal', evidence: ['virtanen-2015-attendance-steps', 'fi-strategy-goal2-screening'],
    unknown: 'No Finnish effect size exists for colorectal screening; the gain is borrowed from cervical screening and must be measured.',
  },
  {
    id: 'ai-mammography', track: 'capacity', level: 'national', stage: 'detection',
    title: 'AI-supported reading of screening mammograms',
    action: 'Replace routine double reading with AI-supported single reading plus double reading of high-risk exams.',
    owner: 'Wellbeing services county radiology with national procurement', strategyMeasure: 'Sub-objective 3.5 (sufficient personnel)',
    mechanism: 'Cuts screen-reading workload by 44% in a randomised trial, releasing radiologist time for diagnostic work-ups.',
    metric: 'screen_breast', evidence: ['masai-2025-workload'],
    unknown: 'Interval cancers were non-inferior, not reduced: this is a capacity action, not a survival claim.',
  },
];

const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
export const relativeReduction = (hr, days) => 1 - hr ** (-days / 28);

// Mean days beyond the 90-day mark for a log-normal symptom-to-treatment time (public route).
export function tailDaysBeyond(threshold, median, sigma) {
  let acc = 0; let prob = 0; const step = 1;
  for (let t = threshold; t < 2000; t += step) {
    const z0 = Math.log(t / median) / sigma; const z1 = Math.log((t + step) / median) / sigma;
    const mass = normalCdf(z1) - normalCdf(z0);
    acc += mass * (t + step / 2 - threshold); prob += mass;
  }
  return { share: prob, meanExcess: prob > 0 ? acc / prob : 0 };
}

const draw = (norm, a, kind = 'normal') => {
  if (kind === 'lognormal') {
    const sd = (Math.log(a.high) - Math.log(a.low)) / 3.92;
    return clamp(Math.exp(Math.log(a.value) + sd * norm()), Math.min(a.low, a.value) * 0.8, a.high * 1.2);
  }
  const sd = (a.high - a.low) / 3.92;
  return clamp(a.value + sd * norm(), a.low, a.high);
};

export function sampleParameters(seed, assumptions = ASSUMPTIONS) {
  const norm = normalSampler(mulberry32(seed));
  return {
    hr: Math.max(1, draw(norm, assumptions.hrPer4Weeks)),
    share: draw(norm, assumptions.symptomaticPrimaryCareShare),
    fast: draw(norm, assumptions.fastRouteShare),
    gapDays: draw(norm, assumptions.routeGapDays),
    closed: draw(norm, assumptions.routeGapClosed),
    pathwayDays: draw(norm, assumptions.pathwayDays),
    navHr: draw(norm, assumptions.navigationHr, 'lognormal'),
    ldctRr: draw(norm, assumptions.ldctRateRatio, 'lognormal'),
    ldctReach: draw(norm, assumptions.ldctReach),
  };
}

export const centralParameters = (a = ASSUMPTIONS) => ({
  hr: a.hrPer4Weeks.value, share: a.symptomaticPrimaryCareShare.value, fast: a.fastRouteShare.value, gapDays: a.routeGapDays.value,
  closed: a.routeGapClosed.value, pathwayDays: a.pathwayDays.value, navHr: a.navigationHr.value, ldctRr: a.ldctRateRatio.value, ldctReach: a.ldctReach.value,
});

// Region facts the scenario needs, taken from the analysis output.
export function regionFacts(analysis) {
  const nationalPrivate = analysis.indicators.private_referral_share?.national ?? null;
  const yearsAll = analysis.mortality.all_cancers.window.length;
  return analysis.regions.filter((r) => r.population && r.allCancer).map((r) => {
    const all = analysis.mortality.all_cancers.rows.find((x) => x.regionId === r.regionId);
    const lung = analysis.mortality.lung?.rows.find((x) => x.regionId === r.regionId);
    const ratio = nationalPrivate && r.privateReferralShare ? clamp(r.privateReferralShare / nationalPrivate, 0.5, 1.5) : 1;
    return {
      regionId: r.regionId, name: r.name, population: r.population, deathsPerYear: all.observed / yearsAll,
      lungDeathsPerYear: lung && !lung.suppressed ? lung.observed / yearsAll : 0, lungSmr: lung && !lung.suppressed ? lung.shrunk : 1,
      smr: r.allCancer.smr, privateRatio: ratio, stages: r.stages,
    };
  });
}

// Public route, first contact to treatment: mean 207 - 72 = 135 days (Kuitunen 2026). With the
// log-sd implied by that paper's mean/median ratio (0.96) the median is 135 / exp(0.96^2 / 2) = 85 days.
export const PUBLIC_WORKUP = { median: 85, sigma: 0.96, stallAfterDays: 90 };
const STALLED = tailDaysBeyond(PUBLIC_WORKUP.stallAfterDays, PUBLIC_WORKUP.median, PUBLIC_WORKUP.sigma);

// Days saved by a set of timeliness actions in one county. Actions overlap on the same
// days, so they combine with diminishing returns and can never exceed the route gap.
export function daysSaved(selected, p) {
  const parts = [];
  if (selected.has('timed-pathways')) parts.push(p.pathwayDays);
  if (selected.has('equal-fast-lane')) parts.push(p.closed * p.gapDays);
  if (selected.has('navigation')) parts.push(STALLED.share * STALLED.meanExcess * (1 - 1 / p.navHr));
  const ceiling = Math.max(p.gapDays, ...parts, 1);
  return ceiling * (1 - parts.reduce((acc, d) => acc * (1 - Math.min(d, ceiling) / ceiling), 1));
}

export function deathsPostponed(region, selected, p) {
  const publicShare = 1 - clamp(p.fast * region.privateRatio, 0.05, 0.9);
  const days = daysSaved(selected, p);
  // Timed pathways reach every primary-care-route patient; the fast lane and navigation act on the public route only.
  const daysFastRoute = selected.has('timed-pathways') ? p.pathwayDays : 0;
  let total = region.deathsPerYear * p.share * (publicShare * relativeReduction(p.hr, days) + (1 - publicShare) * relativeReduction(p.hr, daysFastRoute));
  if (selected.has('ldct-pilot')) total += region.lungDeathsPerYear * p.ldctReach * (1 - p.ldctRr);
  return { deaths: total, days };
}

export const TIMELINESS_IDS = ['timed-pathways', 'equal-fast-lane', 'navigation', 'ldct-pilot'];
export const costOf = (id, region, assumptions = ASSUMPTIONS) => assumptions.costs[id] * region.population;
export const equityWeight = (region, epsilon) => region.smr ** epsilon;

// Budgeted selection on equity-weighted marginal benefit. Marginal, because actions in the
// same county overlap; weighted, because counties with excess mortality count more.
// Plain benefit-per-euro greedy can be far from optimal when one large item does not fit after
// small ones are taken, so three constructions are compared and the best is returned:
// ratio greedy, absolute-gain greedy, and (thorough mode) ratio greedy seeded with each single item.
function construct(regions, { budget, epsilon, params, assumptions, allowed }, mode, seedPick = null) {
  const chosen = new Map(regions.map((r) => [r.regionId, new Set()]));
  const picks = [];
  let spent = 0;
  const take = (pick) => { chosen.get(pick.regionId).add(pick.id); spent += pick.cost; picks.push(pick); };
  if (seedPick) {
    const region = regions.find((r) => r.regionId === seedPick.regionId);
    const cost = costOf(seedPick.id, region, assumptions);
    if (cost > budget) return null;
    take({ regionId: seedPick.regionId, id: seedPick.id, cost, gain: deathsPostponed(region, new Set([seedPick.id]), params).deaths });
  }
  for (;;) {
    let best = null;
    for (const region of regions) {
      const current = chosen.get(region.regionId);
      const base = deathsPostponed(region, current, params).deaths;
      for (const id of allowed) {
        if (current.has(id)) continue;
        const cost = costOf(id, region, assumptions);
        if (spent + cost > budget) continue;
        const gain = deathsPostponed(region, new Set([...current, id]), params).deaths - base;
        const weighted = equityWeight(region, epsilon) * gain;
        const score = mode === 'gain' ? weighted : weighted / cost;
        if (gain > 1e-9 && (!best || score > best.score)) best = { regionId: region.regionId, id, cost, gain, score };
      }
    }
    if (!best) break;
    take(best);
  }
  const perRegion = regions.map((region) => {
    const res = deathsPostponed(region, chosen.get(region.regionId), params);
    return { regionId: region.regionId, actions: [...chosen.get(region.regionId)], deaths: res.deaths, days: res.days };
  });
  const value = sum(perRegion.map((x, i) => equityWeight(regions[i], epsilon) * x.deaths));
  return { picks, spent, deaths: sum(perRegion.map((r) => r.deaths)), perRegion, value };
}

export function optimise(regions, { budget, epsilon = 3, params = centralParameters(), assumptions = ASSUMPTIONS, allowed = TIMELINESS_IDS, thorough = false } = {}) {
  const opts = { budget, epsilon, params, assumptions, allowed };
  const candidates = [construct(regions, opts, 'ratio'), construct(regions, opts, 'gain')];
  if (thorough) for (const region of regions) for (const id of allowed) candidates.push(construct(regions, opts, 'ratio', { regionId: region.regionId, id }));
  return candidates.filter(Boolean).reduce((best, c) => (c.value > best.value + 1e-12 ? c : best));
}

// Exhaustive optimum for small instances; used by tests to bound the greedy gap.
export function optimiseExact(regions, { budget, epsilon = 3, params = centralParameters(), assumptions = ASSUMPTIONS, allowed = TIMELINESS_IDS } = {}) {
  const items = regions.flatMap((r) => allowed.map((id) => ({ r, id })));
  let best = { value: -1, mask: 0 };
  for (let mask = 0; mask < 2 ** items.length; mask += 1) {
    let cost = 0; const sets = new Map(regions.map((r) => [r.regionId, new Set()]));
    for (let i = 0; i < items.length; i += 1) if (mask & (1 << i)) { cost += costOf(items[i].id, items[i].r, assumptions); sets.get(items[i].r.regionId).add(items[i].id); }
    if (cost > budget) continue;
    const value = sum(regions.map((r) => equityWeight(r, epsilon) * deathsPostponed(r, sets.get(r.regionId), params).deaths));
    if (value > best.value) best = { value, mask };
  }
  return best;
}

export const weightedValue = (regions, result, epsilon) => sum(result.perRegion.map((x) => equityWeight(regions.find((r) => r.regionId === x.regionId), epsilon) * x.deaths));

// Concentration of benefit on high-mortality counties: share of deaths postponed that
// falls in counties whose shrunk mortality ratio is above 1.
export function equityShare(regions, result) {
  const total = sum(result.perRegion.map((x) => x.deaths));
  if (!total) return 0;
  return sum(result.perRegion.filter((x) => regions.find((r) => r.regionId === x.regionId).smr > 1).map((x) => x.deaths)) / total;
}

export function detectionTrack(analysis, assumptions = ASSUMPTIONS) {
  const out = [];
  for (const iv of INTERVENTIONS.filter((i) => i.track === 'detection')) {
    const ind = analysis.indicators[iv.programme];
    if (!ind) continue;
    const pts = assumptions.selfSamplingPoints;
    for (const row of ind.rows.filter((r) => r.missesTarget)) {
      const region = analysis.regions.find((r) => r.regionId === row.regionId);
      const gain = Math.min(pts.value, row.targetGap);
      out.push({
        id: iv.id, regionId: row.regionId, name: region.name, programme: iv.programme, level: row.level, targetGap: row.targetGap,
        gainPoints: round(gain, 2), gainLow: round(Math.min(pts.low, row.targetGap), 2), gainHigh: round(Math.min(pts.high, row.targetGap), 2),
        shareOfGapClosed: round(gain / row.targetGap, 2), cost: Math.round(assumptions.costs[iv.id] * region.population), flagged: row.flagged,
      });
    }
  }
  return out.sort((a, b) => b.targetGap - a.targetGap);
}

export function recommend(analysis, { budget = 6_000_000, epsilon = 3, draws = 300, seed = 11, assumptions = ASSUMPTIONS } = {}) {
  const regions = regionFacts(analysis);
  const central = optimise(regions, { budget, epsilon, assumptions, thorough: true });
  // Probabilistic sensitivity analysis: re-optimise under each parameter draw.
  const freq = new Map(); const totals = []; const itemGains = new Map();
  for (let d = 0; d < draws; d += 1) {
    const params = sampleParameters(seed * 1000 + d, assumptions);
    const res = optimise(regions, { budget, epsilon, params, assumptions });
    totals.push(res.deaths);
    for (const pick of res.picks) freq.set(`${pick.regionId}|${pick.id}`, (freq.get(`${pick.regionId}|${pick.id}`) || 0) + 1);
    // Value of the CENTRAL portfolio under this draw, per pick (marginal, in pick order).
    const sets = new Map(regions.map((r) => [r.regionId, new Set()]));
    for (const pick of central.picks) {
      const region = regions.find((r) => r.regionId === pick.regionId);
      const before = deathsPostponed(region, sets.get(pick.regionId), params).deaths;
      sets.get(pick.regionId).add(pick.id);
      const key = `${pick.regionId}|${pick.id}`;
      if (!itemGains.has(key)) itemGains.set(key, []);
      itemGains.get(key).push(deathsPostponed(region, sets.get(pick.regionId), params).deaths - before);
    }
  }
  totals.sort((a, b) => a - b);
  const picks = central.picks.map((pick, order) => {
    const gains = (itemGains.get(`${pick.regionId}|${pick.id}`) || []).sort((a, b) => a - b);
    const region = regions.find((r) => r.regionId === pick.regionId);
    return {
      order: order + 1, regionId: pick.regionId, name: region.name, id: pick.id, cost: Math.round(pick.cost),
      deathsPostponed: round(pick.gain, 1), low: round(quantile(gains, 0.05), 1), high: round(quantile(gains, 0.95), 1),
      costPerDeathPostponed: Math.round(pick.cost / pick.gain), stability: round((freq.get(`${pick.regionId}|${pick.id}`) || 0) / draws, 2),
      equityWeight: round(equityWeight(region, epsilon), 3), smr: region.smr,
    };
  });
  const frontier = [0, 1, 3, 6, 10].map((eps) => {
    const res = optimise(regions, { budget, epsilon: eps, assumptions, thorough: true });
    return { epsilon: eps, deathsPostponed: round(res.deaths, 1), shareInHighMortalityCounties: round(equityShare(regions, res), 3), spent: Math.round(res.spent) };
  });
  // "Same pathway for everyone": close the whole route gap everywhere, no budget limit.
  const p = centralParameters(assumptions);
  const sameLane = regions.map((region) => {
    const publicShare = 1 - clamp(p.fast * region.privateRatio, 0.05, 0.9);
    const calc = (hr, share) => region.deathsPerYear * share * publicShare * relativeReduction(hr, p.gapDays);
    return {
      regionId: region.regionId, name: region.name, publicRouteShare: round(publicShare, 2),
      deathsPostponed: round(calc(p.hr, p.share), 1), low: round(calc(assumptions.hrPer4Weeks.low, assumptions.symptomaticPrimaryCareShare.low), 1),
      high: round(calc(assumptions.hrPer4Weeks.high, assumptions.symptomaticPrimaryCareShare.high), 1),
    };
  });
  return {
    schemaVersion: 'care-equity-recommendation-v1',
    label: 'SCENARIO', budget, epsilon, draws,
    portfolio: {
      picks, spent: Math.round(central.spent), deathsPostponed: round(central.deaths, 1),
      low: round(quantile(totals, 0.05), 1), high: round(quantile(totals, 0.95), 1),
      shareInHighMortalityCounties: round(equityShare(regions, central), 3), perRegion: central.perRegion.map((r) => ({ ...r, deaths: round(r.deaths, 1), days: round(r.days, 1) })),
    },
    frontier,
    samePathway: {
      title: 'If the public route were as fast as the private and occupational route',
      routeGapDays: p.gapDays, deathsPostponed: round(sum(sameLane.map((r) => r.deathsPostponed)), 0),
      low: round(sum(sameLane.map((r) => r.low)), 0), high: round(sum(sameLane.map((r) => r.high)), 0), regions: sameLane,
      note: 'Upper-bound scenario: assumes the delay-mortality gradient measured for treatment delay applies to the days saved, and that the DLBCL route gap transfers to other cancers. The low end assumes no mortality effect at all.',
    },
    validation: {
      title: 'Check against the Danish natural experiment',
      modelHazardRatio: round(p.hr ** (-p.pathwayDays / 28), 3), observedHazardRatio: 0.86, observedLow: 0.73, observedHigh: 1.01, evidence: 'jensen-2017-cpp-excess-hazard',
      note: 'For a 17-day shorter diagnostic interval the model assumes a smaller mortality effect than Denmark observed for pathway-referred patients, and lies inside the observed interval. The model is therefore conservative relative to that study.',
    },
    detection: detectionTrack(analysis, assumptions),
    interventions: INTERVENTIONS, assumptions,
  };
}
