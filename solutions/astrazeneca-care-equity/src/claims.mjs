// Deterministic, source-bound sentences for a county brief. No language model writes
// these: every number is read from the analysis. Each sentence carries `facts`, the exact
// named values it was rendered from, so a claim check can compare wording with data.
import { INTERVENTIONS } from './recommend.mjs';

const STAGE_TEXT = { detection: 'early detection (screening participation)', primary_care: 'first contact and primary care access', referral: 'referral into specialist care' };

export function buildBrief(app, regionId) {
  const a = app.analysis;
  const region = a.regions.find((r) => r.regionId === regionId);
  if (!region) return null;
  const src = (key) => ({ label: `THL Sotkanet: ${a.indicators[key].titleFi}`, url: a.indicators[key].sourceUrl });
  const statfin = { label: 'Statistics Finland: causes of death 13u5 and 11az, population 14wx', url: app.provenance.sources.statfin.url };
  const claims = [];
  const add = (id, kind, text, evidence, sources, facts) => claims.push({ id: `${regionId}-${id}`, kind, text, evidence, sources, facts });

  if (region.allCancer) {
    const m = region.allCancer; const w = a.mortality.all_cancers.window;
    const above = m.smr > 1; const pct = Math.abs((m.smr - 1) * 100).toFixed(1); const excess = Math.abs(m.excessDeathsPerYear);
    add('mortality', 'MEASURED',
      `In ${w[0]}-${w[w.length - 1]}, age-standardised cancer mortality in ${region.name} was ${pct}% ${above ? 'above' : 'below'} the national level (ratio ${m.smr}, 95% interval ${m.low}-${m.high}), about ${excess} ${above ? 'more' : 'fewer'} deaths a year than its age structure predicts.`,
      [], [statfin], {
        county: region.name, period: `${w[0]}-${w[w.length - 1]}`, measure: 'age-standardised cancer mortality ratio, county relative to Finland (1 = national level)',
        ratio: m.smr, ratio_95_percent_interval: `${m.low}-${m.high}`, percent_difference_from_national_level: Number(pct),
        direction: above ? 'above the national level' : 'below the national level',
        deaths_per_year_compared_with_expected_from_age_structure: `${excess} ${above ? 'more' : 'fewer'}`,
      });
  }
  for (const stage of ['detection', 'primary_care', 'referral']) {
    for (const key of region.stages[stage].flagged) {
      const ind = a.indicators[key]; const row = ind.rows.find((r) => r.regionId === regionId);
      add(`flag-${key}`, 'MEASURED',
        `${ind.title}: ${region.name} is at ${row.level} (three-year mean to ${ind.year}) against ${ind.national} nationally${ind.target ? ` and a target of ${ind.target}` : ''}.`,
        ind.target ? ['fi-strategy-goal2-screening'] : [], [src(key)], {
          county: region.name, indicator: ind.title, unit: ind.unit, county_three_year_mean: row.level, latest_year: ind.year,
          national_value: ind.national, ...(ind.target ? { national_target: ind.target } : {}),
          county_is_worse_than_national_value: true,
        });
    }
  }
  const flaggedStages = ['detection', 'primary_care', 'referral'].filter((s) => region.stages[s].flagged.length > 0).map((s) => STAGE_TEXT[s]);
  add('locate', 'MEASURED', region.gapEmergesAt
    ? `Among the stages that public data can measure, the earliest one where ${region.name} is clearly worse than the country is ${STAGE_TEXT[region.gapEmergesAt]}.`
    : `No measured pathway stage shows ${region.name} clearly worse than the country; if outcomes differ, the cause is not locatable from public data.`,
    [], [], {
      county: region.name, pathway_stages_measurable_from_public_data_in_order: Object.values(STAGE_TEXT),
      stages_where_county_is_clearly_worse_than_the_country: flaggedStages,
      earliest_such_stage: region.gapEmergesAt ? STAGE_TEXT[region.gapEmergesAt] : 'none',
    });
  add('blind-spot', 'MEASURED',
    'Time from referral to diagnosis and from diagnosis to first treatment is not published by county for any cancer, so the Goal 3 indicator "patients access treatment within the established target times" cannot be checked from open data.',
    ['fi-strategy-goal3', 'fi-strategy-3-1-no-national-pathways'], [], {
      statistics_not_published_by_county_for_any_cancer: ['time from referral to diagnosis', 'time from diagnosis to first treatment'],
      goal_3_indicator_that_therefore_cannot_be_checked_from_open_data: 'patients access treatment within the established target times',
    });

  for (const pick of app.recommendation.portfolio.picks.filter((p) => p.regionId === regionId)) {
    const iv = INTERVENTIONS.find((i) => i.id === pick.id);
    add(`action-${pick.id}`, 'SCENARIO',
      `Recommended: ${iv.title.toLowerCase()}. Under the stated assumptions this postpones about ${pick.deathsPostponed} deaths a year in ${region.name} (range ${pick.low}-${pick.high}) for an assumed EUR ${pick.cost.toLocaleString('en-GB')} a year; it stayed in the portfolio in ${Math.round(pick.stability * 100)}% of sensitivity runs.`,
      iv.evidence, [], {
        county: region.name, recommended_action: iv.title, nature_of_estimate: 'model scenario under stated assumptions, not a measured effect',
        deaths_postponed_per_year_central: pick.deathsPostponed, deaths_postponed_per_year_range: `${pick.low}-${pick.high}`,
        assumed_cost_eur_per_year: pick.cost, percent_of_sensitivity_runs_in_which_action_stayed_in_portfolio: Math.round(pick.stability * 100),
      });
  }
  for (const d of app.recommendation.detection.filter((x) => x.regionId === regionId)) {
    const iv = INTERVENTIONS.find((i) => i.id === d.id); const ind = a.indicators[d.programme];
    add(`detect-${d.programme}`, 'SCENARIO',
      `${ind.title}: ${d.level.toFixed(1)}% against the 80% target. ${iv.title} is expected to add ${d.gainLow}-${d.gainHigh} percentage points, closing about ${Math.round(d.shareOfGapClosed * 100)}% of the gap.`,
      iv.evidence, [src(d.programme)], {
        county: region.name, indicator: ind.title, county_participation_percent: Number(d.level.toFixed(1)), national_target_percent: 80,
        proposed_action: iv.title, expected_gain_percentage_points_range: `${d.gainLow}-${d.gainHigh}`,
        percent_of_gap_to_target_closed_at_central_estimate: Math.round(d.shareOfGapClosed * 100), nature_of_estimate: 'expected gain taken from Finnish trial evidence, a scenario',
      });
  }
  const tp = INTERVENTIONS.find((i) => i.id === 'pathway-timestamps');
  add('enable', 'MEASURED', `First step for every county: ${tp.action}`, tp.evidence, [], { recommended_first_step_for_every_county: tp.action, reason: tp.mechanism });
  return { title: `Cancer pathway brief: ${region.name}`, regionId, snapshotSha256: app.provenance.snapshotSha256, humanApproval: 'REQUIRED_NOT_GRANTED', claims };
}
