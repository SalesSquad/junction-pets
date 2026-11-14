// Lane B step 6: the Nemotron county planner. No network and no key: model answers are read
// from data/planner/raw*/ and Jev is replaced by a fake transport where a call is needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { INTERVENTIONS } from '../src/recommend.mjs';
import { ACTION_IDS, TOOL_SCHEMAS, loadApp, makeTools } from '../src/planner/tools.mjs';
import { allowedFrom, extractNumbers, gateSentence, numberCheck, JevGate } from '../src/planner/gate.mjs';
import { LABEL, PROMPTS, PROMPT_SHA256, fieldClaims, parseFinal, requestedCounty, validatePlan, keptWithUnmatchedNumber } from '../src/planner/planner.mjs';
import { OFF_LIMITS } from '../src/planner/offlimits.mjs';
import { plannerHtml } from '../web/planner.mjs';

const at = (p) => new URL(p, import.meta.url);
const { app } = loadApp();
const tools = makeTools(app);
const KNOWN = tools.knownCounties;
const PLANS_URL = at('../data/planner/plans-v1.json');
const PLANS = existsSync(PLANS_URL) ? JSON.parse(readFileSync(PLANS_URL, 'utf8')) : null;
const rawDir = (v) => at(`../data/planner/${v === 'v1' ? 'raw' : `raw-${v}`}/`);
const readRaw = (v, id) => JSON.parse(readFileSync(new URL(`${id}.json`, rawDir(v)), 'utf8'));

test('number extraction: measure ids, thousands separators, ranges and number words', () => {
  const x = extractNumbers('ratio 1.097 (95% interval 1.063-1.132), measure 3.1.2, EUR 1,493,400, twenty counties, three actions');
  assert.deepEqual(x.measures, ['3.1.2']);
  assert.deepEqual(x.numbers, [1.097, 95, 1.063, 1.132, 1493400]);
  assert.deepEqual(x.words, [20, 3]);
});

test('number check: a copied number passes, a rounded or invented one fails', () => {
  const allowed = allowedFrom([{ deaths: 11.7, range: '1.7-23.5', stability: 0.95, text: 'serves measure 3.1.2' }]);
  assert.equal(numberCheck('about 11.7 deaths a year (range 1.7-23.5), in 95% of runs, measure 3.1.2', allowed).ok, true);
  assert.deepEqual(numberCheck('about 12 deaths a year', allowed).unmatched, [12]);
  assert.deepEqual(numberCheck('serves measure 3.1.4', allowed).unmatched, ['measure:3.1.4']);
  assert.deepEqual(numberCheck('within seven days', allowed).unmatched, ['word:7']);
});

test('tools: four schemas, county brief, unknown county, portfolio defaults and bounds', () => {
  assert.deepEqual(TOOL_SCHEMAS.map((t) => t.function.name), ['get_county_brief', 'get_portfolio', 'get_evidence', 'get_roadmap_measure']);
  assert.equal(KNOWN.length, 23);
  const brief = tools.call('get_county_brief', { county_id: 'HVA06' });
  assert.equal(brief.county_id, 'HVA06');
  assert.ok(brief.claims.length >= 3);
  assert.equal(tools.call('get_county_brief', { county_id: 'HVA24' }).error, 'unknown county_id');
  const p = tools.call('get_portfolio', { budget_meur: 6, equity_weight: 3, county_id: 'HVA06' });
  const stored = app.recommendation.portfolio.picks.filter((x) => x.regionId === 'HVA06');
  assert.deepEqual(p.county_picks.map((x) => [x.action_id, x.deaths_postponed_per_year_central]), stored.map((x) => [x.id, x.deathsPostponed]));
  assert.equal(p.national_total.deaths_postponed_per_year_central, app.recommendation.portfolio.deathsPostponed);
  assert.match(tools.call('get_portfolio', { budget_meur: 500, equity_weight: 3 }).error, /budget_meur/);
  assert.match(tools.call('get_portfolio', { budget_meur: 6, equity_weight: -1 }).error, /equity_weight/);
  const other = tools.call('get_portfolio', { budget_meur: 3, equity_weight: 0 });
  assert.ok(other.national_total.spent_eur_per_year <= 3e6);
});

test('tools: get_evidence and get_roadmap_measure cover every action', () => {
  assert.deepEqual(ACTION_IDS, INTERVENTIONS.map((i) => i.id));
  for (const id of ACTION_IDS) {
    const ev = tools.call('get_evidence', { action_id: id });
    const iv = INTERVENTIONS.find((i) => i.id === id);
    assert.equal(ev.accountable_owner, iv.owner);
    assert.deepEqual(ev.evidence.map((e) => e.id), iv.evidence);
    assert.ok(tools.call('get_roadmap_measure', { action_id: id }).primaryMeasure.id);
  }
  assert.equal(tools.call('get_evidence', { action_id: 'nope' }).error, 'unknown action_id');
  assert.equal(tools.call('no_such_tool', {}).error, 'unknown tool');
});

test('parse and validate a final answer', () => {
  assert.equal(parseFinal('```json\n{"refusal": "no"}\n```').kind, 'refusal');
  assert.equal(parseFinal('not json').kind, 'invalid');
  const a = (id) => ({ action_id: id, action: 'x', rationale: 'x', owner_role: 'x', indicator: 'x', roadmap_measure: '3.1.2' });
  const ids = KNOWN.map((c) => c.county_id);
  const good = { county_id: 'HVA06', actions: [a('timed-pathways'), a('self-sampling'), a('screening-reminders')], evidence_does_not_support: 'x' };
  assert.deepEqual(validatePlan(good, 'HVA06', ids), []);
  assert.ok(validatePlan({ ...good, county_id: 'HVA24' }, null, ids).length > 0);
  assert.ok(validatePlan({ ...good, actions: [a('timed-pathways'), a('timed-pathways'), a('navigation')] }, 'HVA06', ids).length > 0);
  assert.ok(validatePlan({ ...good, county_id: 'HVA21' }, 'HVA06', ids).length > 0);
});

test('code guard: a plan only for the single known county the request names', () => {
  assert.equal(requestedCounty('Draft the action plan for county_id HVA06 (Satakunta wellbeing services county).', KNOWN), 'HVA06');
  assert.equal(requestedCounty('Name the oncologists in North Savo', KNOWN), 'HVA13');
  assert.equal(requestedCounty('a plan for North Ostrobothnia', KNOWN), 'HVA19');
  assert.equal(requestedCounty('Which five Finnish hospitals have the highest cancer mortality?', KNOWN), null);
  assert.equal(requestedCounty('county_id HVA24 (Northern Tavastia)', KNOWN), null);
  assert.equal(requestedCounty('Compare Kainuu and Lapland', KNOWN), null);
});

test('gate: an unmatched number is dropped before Jev is asked; Jev answers are cached and ledgered', async () => {
  const dir = pathToFileURL(`${mkdtempSync(join(tmpdir(), 'planner-'))}/`);
  let calls = 0;
  const answers = { faithful: { choice: 'supports', probabilities: { supports: 0.95, contradicts: 0.02, says_nothing: 0.03 }, confidence: 0.9 }, overclaim: { noul: 0.1 } };
  const fetchImpl = async () => { calls += 1; return { ok: true, json: async () => ({ answers, model: 'jev-test', usage: { input_tokens: 100, output_tokens: 5 } }) }; };
  const jev = new JevGate({ dir, apiKey: 'test', fetchImpl });
  const allowed = allowedFrom([{ deaths: 11.7 }]);
  const claim = { kind: 'SCENARIO', facts: { deaths: 11.7 }, evidence: [] };
  const bad = await gateSentence({ field: 'rationale', text: 'about 12 deaths', allowed, claim, evidenceRows: app.evidence, jev });
  assert.equal(bad.kept, false); assert.equal(bad.reason, 'NUMBER_NOT_IN_TOOL_OUTPUT'); assert.equal(calls, 0);
  const good = await gateSentence({ field: 'rationale', text: 'about 11.7 deaths', allowed, claim, evidenceRows: app.evidence, jev });
  assert.equal(good.kept, true); assert.equal(calls, 1);
  const again = await gateSentence({ field: 'rationale', text: 'about 11.7 deaths', allowed, claim, evidenceRows: app.evidence, jev });
  assert.equal(again.kept, true); assert.equal(again.jev.cached, true); assert.equal(calls, 1);
  assert.equal(jev.ledger.d.requests, 1); assert.equal(jev.ledger.d.tokens, 105);
  const noKey = new JevGate({ dir, apiKey: '', fetchImpl });
  const unchecked = await gateSentence({ field: 'action', text: 'a new sentence', allowed, claim, evidenceRows: app.evidence, jev: noKey });
  assert.equal(unchecked.kept, false); assert.equal(unchecked.reason, 'NOT_CHECKED');
});

test('gate v2 gives each field the tool output named as its source', () => {
  const ev = tools.call('get_evidence', { action_id: 'timed-pathways' });
  const rm = tools.call('get_roadmap_measure', { action_id: 'timed-pathways' });
  const c = fieldClaims({ gateVersion: 'v2', ev, rm, briefFacts: [{ text: 'b' }], portfolioFacts: { p: 1 }, evidenceIds: ['x'] });
  assert.equal(c.owner_role.facts.accountable_owner, ev.accountable_owner);
  assert.equal(c.indicator.facts.indicator_to_monitor.key, ev.indicator_to_monitor.key);
  assert.deepEqual(c.rationale.facts.county_brief, [{ text: 'b' }]);
  const v1 = fieldClaims({ gateVersion: 'v1', ev, rm, briefFacts: [], portfolioFacts: {}, evidenceIds: [] });
  assert.equal(v1.action, v1.indicator);
});

test('prompts: v2 differs from v1 only in the field-format lines', () => {
  const strip = (p) => p.split('\n').filter((l) => !/^ {3}- (action|owner_role|indicator|evidence_does_not_support):/.test(l)).join('\n');
  assert.equal(strip(PROMPTS.v1), strip(PROMPTS.v2));
  assert.notEqual(PROMPT_SHA256.v1, PROMPT_SHA256.v2);
});

test('off-limits prompts: ten, fixed, no real patient', () => {
  assert.equal(OFF_LIMITS.length, 10);
  assert.equal(new Set(OFF_LIMITS.map((p) => p.id)).size, 10);
});

test('stored plans: label, 23 counties, success criteria, every kept sentence rechecked', { skip: !PLANS && 'plans-v1.json not built' }, () => {
  assert.equal(PLANS.label, LABEL);
  assert.equal(PLANS.label, 'Draft for a planner, drafted by Nemotron 3.5 Super VL; numbers checked');
  assert.equal(Object.keys(PLANS.counties).length, 23);
  assert.equal(PLANS.summary.keptSentencesWithUnmatchedNumber, 0);
  assert.ok(PLANS.summary.countiesWithAtLeast3Kept >= 20);
  assert.equal(PLANS.offLimits.length, 10);
  assert.ok(PLANS.offLimits.every((o) => o.pass && o.outcome !== 'PLAN'));
  assert.equal(PLANS.systemPromptSha256, PROMPT_SHA256[PLANS.promptVersion]);
  let kept = 0;
  for (const [id, c] of Object.entries(PLANS.counties)) {
    const raw = readRaw(PLANS.promptVersion, id);
    assert.equal(raw.systemPromptSha256, PLANS.systemPromptSha256);
    assert.equal(keptWithUnmatchedNumber(raw.gated, raw.toolCalls), 0, id);
    const allowed = allowedFrom(raw.toolCalls.map((t) => t.output));
    for (const s of [...c.plan.actions.flatMap((a) => a.sentences), c.plan.evidenceLimit]) {
      if (!s.kept) continue;
      kept += 1;
      assert.equal(numberCheck(s.text, allowed).ok, true, `${id} ${s.text}`);
      assert.equal(s.jev.verdict, 'SUPPORTED');
    }
    for (const a of c.plan.actions) if (a.roadmap_measure.ok) assert.ok(a.roadmap_measure.expected.includes(a.roadmap_measure.measure));
  }
  assert.equal(kept, PLANS.summary.keptSentences);
});

test('stored plans: no banned wording', { skip: !PLANS && 'plans-v1.json not built' }, () => {
  const text = readFileSync(PLANS_URL, 'utf8').toLowerCase();
  for (const w of ['auto-confirmed', 'skips review', 'clinically accurate', 'works on real notes', 'hospital-grade']) assert.equal(text.includes(w), false, w);
});

test('render: label, kept sentences only, escaping, missing county', { skip: !PLANS && 'plans-v1.json not built' }, () => {
  const html = plannerHtml(PLANS, 'HVA06');
  assert.ok(html.includes('Draft for a planner, drafted by Nemotron 3.5 Super VL; numbers checked'));
  const c = PLANS.counties.HVA06;
  for (const a of c.plan.actions) for (const s of a.sentences) {
    const shown = html.includes(s.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'));
    if (s.kept) assert.ok(shown, s.text);
  }
  const evil = structuredClone(PLANS);
  evil.counties.HVA06.plan.actions[0].sentences[0] = { field: 'action', text: '<script>alert(1)</script>', kept: true };
  assert.ok(!plannerHtml(evil, 'HVA06').includes('<script>'));
  const dropped = structuredClone(PLANS);
  dropped.counties.HVA06.plan.actions[0].sentences.forEach((s) => { s.kept = false; s.text = 'DROPPED SENTENCE TEXT'; });
  assert.ok(!plannerHtml(dropped, 'HVA06').includes('DROPPED SENTENCE TEXT'));
  assert.match(plannerHtml(PLANS, 'HVA99'), /No checked draft/);
  assert.match(plannerHtml(null, 'HVA06'), /No checked draft/);
});

const VISION_URL = at('../data/planner/vision/vision-6b-v1.json');
test('step 6b: image-input report is consistent with its pages and its kill rule', { skip: !existsSync(VISION_URL) && 'vision report not built' }, async () => {
  const { createHash } = await import('node:crypto');
  const v = JSON.parse(readFileSync(VISION_URL, 'utf8'));
  const s = v.summary;
  assert.equal(v.synthetic, true);
  assert.equal(v.notes.length, 20);
  assert.equal(s.both_exact + s.image_only_exact + s.text_only_exact + s.neither_exact, s.paired);
  assert.equal(s.image_exact, s.both_exact + s.image_only_exact);
  assert.equal(s.text_exact, s.both_exact + s.text_only_exact);
  assert.equal(s.verdict, s.notes_with_umlaut_or_date_misread > 5 ? 'tested, not good enough yet' : 'kill criterion not met');
  const manifest = JSON.parse(readFileSync(at('../data/planner/vision/manifest.json'), 'utf8'));
  for (const m of manifest.notes) assert.equal(createHash('sha256').update(readFileSync(at(`../${m.png}`))).digest('hex'), m.png_sha256, m.png);
  const text = readFileSync(VISION_URL, 'utf8').toLowerCase();
  for (const w of ['auto-confirmed', 'skips review', 'clinically accurate', 'works on real notes', 'hospital-grade']) assert.equal(text.includes(w), false, w);
});

test('raw records hold no key material', { skip: !PLANS && 'plans-v1.json not built' }, () => {
  for (const v of ['v1', 'v2']) {
    if (!existsSync(rawDir(v))) continue;
    for (const f of readdirSync(rawDir(v))) {
      const t = readFileSync(new URL(f, rawDir(v)), 'utf8');
      assert.equal(/authorization|bearer\s+[a-z0-9]/i.test(t), false, f);
    }
  }
});

test('render: a kept sentence the current brief no longer supports can be withheld, and is counted', { skip: !PLANS && 'plans-v1.json not built' }, () => {
  const re = /clearly worse/i;
  const target = PLANS.counties.HVA06.plan.actions.flatMap((a) => a.sentences).filter((s) => s.kept && s.field === 'rationale' && re.test(s.text));
  const html = plannerHtml(PLANS, 'HVA06', { withhold: (s) => s.field === 'rationale' && re.test(s.text), withheldWhy: 'test reason' });
  for (const s of target) assert.ok(!html.includes(s.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')), s.text);
  assert.equal((html.match(/more withheld because test reason/g) || []).length, target.length ? 1 : 0);
  assert.equal(plannerHtml(PLANS, 'HVA06'), plannerHtml(PLANS, 'HVA06', {}), 'no option, no change');
});
