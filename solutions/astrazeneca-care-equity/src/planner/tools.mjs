// The four tools the Nemotron county planner may call. Each one is plain code over SAMA's own
// data, so every number a tool returns can be traced to app.json, the evidence table or the
// roadmap mapping. Nothing here calls a model.
//
//   get_county_brief(county_id)                          src/claims.mjs buildBrief on web/data/app.json
//   get_portfolio(budget_meur, equity_weight[, county_id]) optimiser rows (src/recommend.mjs)
//   get_evidence(action_id)                              INTERVENTIONS + data/evidence/literature-v1.json
//   get_roadmap_measure(action_id)                       src/roadmap.mjs
//
// Inputs from the model are validated here; a bad input returns { error } instead of throwing,
// so the model sees what went wrong and the run log records it.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { buildBrief } from '../claims.mjs';
import { INTERVENTIONS, optimise, regionFacts, equityShare } from '../recommend.mjs';
import { getRoadmapMeasure } from '../roadmap.mjs';

const at = (p) => new URL(p, import.meta.url);
export const APP_PATH = at('../../web/data/app.json');

export function loadApp(path = APP_PATH) {
  const buf = readFileSync(path);
  return { app: JSON.parse(buf.toString('utf8')), appSha256: createHash('sha256').update(buf).digest('hex') };
}

export const ACTION_IDS = INTERVENTIONS.map((i) => i.id);
export const DEFAULT_BUDGET_MEUR = 6;
export const DEFAULT_EQUITY_WEIGHT = 3;
const round = (x, d = 1) => Math.round(x * 10 ** d) / 10 ** d;

export const TOOL_SCHEMAS = [
  {
    type: 'function',
    function: {
      name: 'get_county_brief',
      description: 'Source-bound brief for one Finnish wellbeing services county: measured public statistics (cancer mortality ratio, flagged pathway indicators, screening participation) and model scenarios for the actions the optimiser recommends there. county_id looks like HVA06.',
      parameters: { type: 'object', additionalProperties: false, required: ['county_id'], properties: { county_id: { type: 'string', description: 'County id, for example HVA06' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_portfolio',
      description: 'Budgeted, equity-weighted action portfolio from the SAMA optimiser (a model scenario, not a measured effect). Returns the national total and, when county_id is given, the actions picked for that county and its screening actions. Default settings: budget_meur 6, equity_weight 3.',
      parameters: {
        type: 'object', additionalProperties: false, required: ['budget_meur', 'equity_weight'],
        properties: {
          budget_meur: { type: 'number', description: 'Yearly national budget in million euros, 0.5 to 60' },
          equity_weight: { type: 'number', description: 'Inequality aversion, 0 (none) to 10' },
          county_id: { type: 'string', description: 'Optional county id to return that county\'s rows' },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_evidence',
      description: 'The action as SAMA defines it (what, accountable owner, indicator to monitor, mechanism, what remains unknown) and the published evidence rows it rests on.',
      parameters: { type: 'object', additionalProperties: false, required: ['action_id'], properties: { action_id: { type: 'string', enum: ACTION_IDS } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_roadmap_measure',
      description: 'The measure of the national cancer strategy implementation roadmap 2026-2031 that the action serves, with page, owner, schedule and metric (Finnish quotes are verbatim from the roadmap PDF; English text is the SAMA team\'s reading).',
      parameters: { type: 'object', additionalProperties: false, required: ['action_id'], properties: { action_id: { type: 'string', enum: ACTION_IDS } } },
    },
  },
];

export function makeTools(app) {
  const regions = app.analysis.regions;
  const regionById = new Map(regions.map((r) => [r.regionId, r]));
  const knownCounties = regions.map((r) => ({ county_id: r.regionId, name: r.name }));
  const facts = regionFacts(app.analysis);
  const portfolioCache = new Map();
  const evidenceById = new Map(app.evidence.map((e) => [e.id, e]));

  const unknownCounty = (id) => ({ error: 'unknown county_id', county_id: id ?? null, known_counties: knownCounties });

  function get_county_brief({ county_id } = {}) {
    const id = String(county_id ?? '').trim();
    if (!regionById.has(id)) return unknownCounty(county_id);
    const brief = buildBrief(app, id);
    return { county_id: id, county_name: regionById.get(id).name, ...brief };
  }

  function portfolioAll(budgetMeur, epsilon) {
    const key = `${budgetMeur}|${epsilon}`;
    if (portfolioCache.has(key)) return portfolioCache.get(key);
    const rec = app.recommendation;
    let out;
    if (budgetMeur * 1e6 === rec.budget && epsilon === rec.epsilon) {
      out = {
        settings: 'default (stored in app.json, with sensitivity ranges)',
        picks: rec.portfolio.picks.map((p) => ({ county_id: p.regionId, action_id: p.id, cost_eur_per_year: p.cost, deaths_postponed_per_year_central: p.deathsPostponed, deaths_postponed_per_year_range: `${p.low}-${p.high}`, percent_of_sensitivity_runs_in_which_action_stayed: Math.round(p.stability * 100) })),
        total: { deaths_postponed_per_year_central: rec.portfolio.deathsPostponed, deaths_postponed_per_year_range: `${rec.portfolio.low}-${rec.portfolio.high}`, spent_eur_per_year: rec.portfolio.spent, share_of_benefit_in_counties_with_above_national_mortality: rec.portfolio.shareInHighMortalityCounties },
      };
    } else {
      const res = optimise(facts, { budget: budgetMeur * 1e6, epsilon, thorough: true });
      out = {
        settings: 'recomputed for these settings (central parameters only; sensitivity ranges and stability are not computed)',
        picks: res.picks.map((p) => ({ county_id: p.regionId, action_id: p.id, cost_eur_per_year: Math.round(p.cost), deaths_postponed_per_year_central: round(p.gain, 1) })),
        total: { deaths_postponed_per_year_central: round(res.deaths, 1), spent_eur_per_year: Math.round(res.spent), share_of_benefit_in_counties_with_above_national_mortality: round(equityShare(facts, res), 3) },
      };
    }
    portfolioCache.set(key, out);
    return out;
  }

  function get_portfolio({ budget_meur, equity_weight, county_id } = {}) {
    const b = Number(budget_meur ?? DEFAULT_BUDGET_MEUR); const e = Number(equity_weight ?? DEFAULT_EQUITY_WEIGHT);
    if (!Number.isFinite(b) || b < 0.5 || b > 60) return { error: 'budget_meur must be a number from 0.5 to 60', budget_meur: budget_meur ?? null };
    if (!Number.isFinite(e) || e < 0 || e > 10) return { error: 'equity_weight must be a number from 0 to 10', equity_weight: equity_weight ?? null };
    const all = portfolioAll(b, e);
    const base = { label: 'SCENARIO: model output under stated assumptions, not a measured effect', budget_meur: b, budget_eur_per_year: Math.round(b * 1e6), equity_weight: e, settings: all.settings, national_total: all.total, picks_in_all_counties: all.picks.length };
    if (county_id == null || county_id === '') return { ...base, picks: all.picks };
    const id = String(county_id).trim();
    if (!regionById.has(id)) return { ...base, ...unknownCounty(county_id) };
    const detection = app.recommendation.detection.filter((d) => d.regionId === id).map((d) => ({ action_id: d.id, indicator: app.analysis.indicators[d.programme]?.title ?? d.programme, county_participation_percent: round(d.level, 1), national_target_percent: 80, expected_gain_percentage_points_range: `${d.gainLow}-${d.gainHigh}`, percent_of_gap_to_target_closed_at_central_estimate: Math.round(d.shareOfGapClosed * 100), assumed_cost_eur_per_year: d.cost }));
    return {
      ...base, county_id: id, county_name: regionById.get(id).name,
      county_picks: all.picks.filter((p) => p.county_id === id),
      county_screening_actions: detection,
      note: 'Screening actions are scored on participation, not mortality; they are not part of the budgeted mortality portfolio.',
    };
  }

  function get_evidence({ action_id } = {}) {
    const iv = INTERVENTIONS.find((i) => i.id === String(action_id ?? '').trim());
    if (!iv) return { error: 'unknown action_id', action_id: action_id ?? null, known_action_ids: ACTION_IDS };
    const ind = app.analysis.indicators[iv.metric];
    return {
      action_id: iv.id, title: iv.title, action: iv.action, accountable_owner: iv.owner, track: iv.track, level: iv.level, pathway_stage: iv.stage,
      mechanism: iv.mechanism,
      indicator_to_monitor: ind ? { key: iv.metric, title: ind.title, unit: ind.unit } : { key: iv.metric, title: iv.metric },
      what_remains_unknown: iv.unknown,
      evidence: iv.evidence.map((id) => evidenceById.get(id)).filter(Boolean).map((r) => ({ id: r.id, finding: r.claim, value: r.value, unit: r.unit, citation: r.citation, verified_at_source: r.verified, caveat: r.notes || null })),
    };
  }

  function get_roadmap_measure({ action_id } = {}) {
    const out = getRoadmapMeasure(action_id);
    return out;
  }

  const impl = { get_county_brief, get_portfolio, get_evidence, get_roadmap_measure };
  return {
    knownCounties,
    impl,
    call(name, args) {
      const fn = impl[name];
      if (!fn) return { error: 'unknown tool', tool: name, known_tools: Object.keys(impl) };
      return fn(args && typeof args === 'object' ? args : {});
    },
  };
}
