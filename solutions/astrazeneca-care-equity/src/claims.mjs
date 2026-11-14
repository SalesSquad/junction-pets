// Deterministic, source-bound sentences for a county brief. No language model writes
// these: every number is read from the analysis, and every sentence names its sources,
// so a claim check can compare the sentence with the evidence it cites.
import { INTERVENTIONS } from './recommend.mjs';

const pct = (x) => `${Number(x).toFixed(1)}%`;
const STAGE_TEXT = { detection: 'early detection (screening participation)', primary_care: 'first contact and primary care access', referral: 'referral into specialist care' };

export function buildBrief(app, regionId) {
  const a = app.analysis;
  const region = a.regions.find((r) => r.regionId === regionId);
  if (!region) return null;
  const src = (key) => ({ label: `THL Sotkanet: ${a.indicators[key].titleFi}`, url: a.indicators[key].sourceUrl });
  const statfin = { label: 'Statistics Finland: causes of death 13u5 and 11az, population 14wx', url: app.provenance.sources.statfin.url };
  const claims = [];
  const add = (id, kind, text, evidence = [], sources = [], support = '') => claims.push({ id: `${regionId}-${id}`, kind, text, evidence, sources, support });

  if (region.allCancer) {
    const m = region.allCancer; const w = a.mortality.all_cancers.window;
    const direction = m.smr > 1 ? 'above' : 'below';
    add('mortality', 'MEASURED',
      `In ${w[0]}-${w[w.length - 1]}, age-standardised cancer mortality in ${region.name} was ${Math.abs((m.smr - 1) * 100).toFixed(1)}% ${direction} the national level (ratio ${m.smr}, 95% interval ${m.low}-${m.high}), about ${Math.abs(m.excessDeathsPerYear)} ${m.smr > 1 ? 'more' : 'fewer'} deaths a year than its age structure predicts.`,
      [], [statfin], `Shrunk standardised mortality ratio ${m.smr} (${m.low}-${m.high}); excess deaths per year ${m.excessDeathsPerYear}; probability the ratio is above 1: ${m.pAboveOne}.`);
  }
  for (const stage of ['detection', 'primary_care', 'referral']) {
    for (const key of region.stages[stage].flagged) {
      const ind = a.indicators[key]; const row = ind.rows.find((r) => r.regionId === regionId);
      add(`flag-${key}`, 'MEASURED',
        `${ind.title}: ${region.name} is at ${row.level} (three-year mean to ${ind.year}) against ${ind.national} nationally${ind.target ? ` and a target of ${ind.target}` : ''}.`,
        ind.target ? ['fi-strategy-goal2-screening'] : [], [src(key)], `County three-year mean ${row.level}; national value ${ind.national}; probability the county is worse than the national value ${row.pWorse}.`);
    }
  }
  add('locate', 'MEASURED', region.gapEmergesAt
    ? `Among the stages that public data can measure, the earliest one where ${region.name} is clearly worse than the country is ${STAGE_TEXT[region.gapEmergesAt]}.`
    : `No measured pathway stage shows ${region.name} clearly worse than the country; if outcomes differ, the cause is not locatable from public data.`,
    [], [], `gapEmergesAt=${region.gapEmergesAt}; weakest measured stage=${region.weakestMeasuredStage}.`);
  add('blind-spot', 'MEASURED',
    'Time from referral to diagnosis and from diagnosis to first treatment is not published by county for any cancer, so the Goal 3 indicator "patients access treatment within the established target times" cannot be checked from open data.',
    ['fi-strategy-goal3', 'fi-strategy-3-1-no-national-pathways'], [], a.dataGaps.map((g) => g.missing).join('; '));

  const picks = app.recommendation.portfolio.picks.filter((p) => p.regionId === regionId);
  for (const pick of picks) {
    const iv = INTERVENTIONS.find((i) => i.id === pick.id);
    add(`action-${pick.id}`, 'SCENARIO',
      `Recommended: ${iv.title.toLowerCase()}. Under the stated assumptions this postpones about ${pick.deathsPostponed} deaths a year in ${region.name} (range ${pick.low}-${pick.high}) for an assumed EUR ${pick.cost.toLocaleString('en-GB')} a year; it stayed in the portfolio in ${Math.round(pick.stability * 100)}% of sensitivity runs.`,
      iv.evidence, [], `Scenario output of the optimiser at budget EUR ${app.recommendation.budget}; evidence rows: ${iv.evidence.join(', ')}.`);
  }
  for (const d of app.recommendation.detection.filter((x) => x.regionId === regionId)) {
    const iv = INTERVENTIONS.find((i) => i.id === d.id);
    add(`detect-${d.programme}`, 'SCENARIO',
      `${a.indicators[d.programme].title}: ${pct(d.level)} against the 80% target. ${iv.title} is expected to add ${d.gainLow}-${d.gainHigh} percentage points, closing about ${Math.round(d.shareOfGapClosed * 100)}% of the gap.`,
      iv.evidence, [src(d.programme)], `Target gap ${d.targetGap} points; modelled gain ${d.gainPoints} points.`);
  }
  const tp = INTERVENTIONS.find((i) => i.id === 'pathway-timestamps');
  add('enable', 'MEASURED', `First step for every county: ${tp.action}`, tp.evidence, [], tp.mechanism);
  return { title: `Cancer pathway brief: ${region.name}`, regionId, snapshotSha256: app.provenance.snapshotSha256, humanApproval: 'REQUIRED_NOT_GRANTED', claims };
}
