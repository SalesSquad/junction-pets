// Nemotron 3.5 Super VL drafts a county action plan by calling SAMA's own tools; code then gates
// every sentence (src/planner/gate.mjs). The model never sees a number it was not given by a tool,
// and no sentence with a number that is not in a tool output can survive the gate.
// Output is English: the model card does not name Finnish. A person decides; this is a draft.
import { createHash } from 'node:crypto';
import { TOOL_SCHEMAS, ACTION_IDS } from './tools.mjs';
import { allowedFrom, gateSentence, numberCheck } from './gate.mjs';

export const LABEL = 'Draft for a planner, drafted by Nemotron 3.5 Super VL; numbers checked';
export const SENTENCE_FIELDS = ['action', 'rationale', 'owner_role', 'indicator'];

const PROMPT_HEAD = `You draft cancer-care action plans for Finnish wellbeing services counties. The reader is a public-health planner in the county, who decides what to do with your draft. You work only from four tools. They return public aggregate statistics, model scenarios under stated assumptions, published evidence, and the national cancer strategy implementation roadmap 2026-2031.

How to work:
1. Call get_county_brief for the county. Call get_portfolio with budget_meur 6, equity_weight 3 and the county_id, unless the user names other settings.
2. Choose three different actions for this county from these action ids: ${ACTION_IDS.join(', ')}. Prefer the actions that the brief and the portfolio recommend for this county, its screening actions, and the first step recommended for every county.
3. For each chosen action call get_evidence and get_roadmap_measure.
4. Then answer with one JSON object and nothing else (no markdown, no comments):
{"county_id": "<id>", "actions": [{"action_id": "<id>", "action": "<sentence>", "rationale": "<sentence>", "owner_role": "<sentence>", "indicator": "<sentence>", "roadmap_measure": "<measure id>"}, ... three actions ...], "evidence_does_not_support": "<sentence>"}
`;
const PROMPT_TAIL = `

Rules:
- Write in English. Every number you write must be copied exactly, digit for digit, from a tool output. Never round, convert, add, subtract or otherwise compute a number. If you cannot copy a number exactly, write the sentence without it.
- Model results are scenarios under stated assumptions. Never present them as certain, proven or guaranteed effects, and never say that something caused an outcome.
- Do not give advice about individual patients (symptoms, diagnosis, treatment choice, drugs or doses, prognosis). Do not rank, compare or name hospitals, clinics or clinicians. Do not produce patient-level data. Do not write plans for places the tools do not know. In any of these cases answer only {"refusal": "<one sentence>"}.`;
// v1: the prompt of the full run. v2: field formats only (written after v1 kept 0/69 indicator lines; gate unchanged).
export const FIELD_RULES = {
  v1: `   - action: one sentence on what the county would do.
   - rationale: one sentence on why this county, using its numbers from get_county_brief or get_portfolio.
   - owner_role: one sentence naming the accountable owner role, as get_evidence or get_roadmap_measure gives it.
   - indicator: one sentence naming the indicator to monitor, as get_evidence or the roadmap measure gives it.
   - roadmap_measure: the measure id that get_roadmap_measure returns as primaryMeasure.id, for example 3.1.2.
   - evidence_does_not_support: one sentence on what the evidence for these actions does not support, from what_remains_unknown or the roadmap gap text.`,
  v2: `   - action: one sentence that proposes the action, starting with "Proposed:" and keeping the wording of the get_evidence action field.
   - rationale: one sentence on why this county, using its numbers from get_county_brief or get_portfolio.
   - owner_role: one sentence of the form "Accountable owner: <the accountable_owner that get_evidence returns>."
   - indicator: one sentence of the form "Indicator to monitor: <the indicator_to_monitor title that get_evidence returns>."
   - roadmap_measure: the measure id that get_roadmap_measure returns as primaryMeasure.id, for example 3.1.2.
   - evidence_does_not_support: one sentence that names one of the three actions and states one specific limit of its evidence, keeping the wording of that action's what_remains_unknown field.`,
};
export const PROMPTS = Object.fromEntries(Object.entries(FIELD_RULES).map(([v, rules]) => [v, PROMPT_HEAD + rules + PROMPT_TAIL]));
export const SYSTEM_PROMPT = PROMPTS.v1;

const sha = (s) => createHash('sha256').update(s).digest('hex');
export const SYSTEM_PROMPT_SHA256 = sha(SYSTEM_PROMPT);
export const PROMPT_SHA256 = Object.fromEntries(Object.entries(PROMPTS).map(([v, p]) => [v, sha(p)]));

export function parseFinal(text) {
  let s = String(text ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
  s = s.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  const a = s.indexOf('{'); const b = s.lastIndexOf('}');
  if (a < 0 || b <= a) return { kind: 'invalid', error: 'no JSON object in the answer' };
  let obj;
  try { obj = JSON.parse(s.slice(a, b + 1)); } catch (e) { return { kind: 'invalid', error: `JSON parse error: ${e.message.slice(0, 120)}` }; }
  if (obj && typeof obj.refusal === 'string' && !obj.actions) return { kind: 'refusal', obj };
  return { kind: 'plan', obj };
}

// Code guard (added after off-limits prompt 08 produced an unrequested Satakunta plan): a plan may
// only be for the single known county that the request names, by id (HVA06) or by name
// (Satakunta). A request that names no known county, or several, can never yield a plan.
export function requestedCounty(message, knownCounties) {
  let text = ` ${String(message ?? '')} `;
  const found = new Set();
  for (const m of text.matchAll(/\bHVA\d{2}\b/g)) if (knownCounties.some((c) => c.county_id === m[0])) found.add(m[0]);
  const names = knownCounties.map((c) => ({ id: c.county_id, short: c.name.replace(/ wellbeing services county$/, '').replace(/^City of /, '') }))
    .sort((a, b) => b.short.length - a.short.length);
  for (const n of names) {
    const re = new RegExp(`(^|[^\\p{L}])${n.short.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?=$|[^\\p{L}])`, 'iu');
    if (re.test(text)) { found.add(n.id); text = text.replace(re, '$1 '); }
  }
  return found.size === 1 ? [...found][0] : null;
}

// Structural check only (no content judgement): three distinct known actions, all fields strings.
export function validatePlan(obj, countyId, knownCountyIds) {
  const errors = [];
  if (!obj || typeof obj !== 'object') return ['answer is not an object'];
  if (!knownCountyIds.includes(obj.county_id)) errors.push(`county_id ${JSON.stringify(obj.county_id)} is not a known county`);
  else if (countyId && obj.county_id !== countyId) errors.push(`county_id must be ${countyId}`);
  if (!Array.isArray(obj.actions) || obj.actions.length !== 3) errors.push('actions must be an array of exactly three objects');
  else {
    const ids = obj.actions.map((a) => a?.action_id);
    if (new Set(ids).size !== 3) errors.push('the three action_id values must differ');
    obj.actions.forEach((a, i) => {
      if (!ACTION_IDS.includes(a?.action_id)) errors.push(`actions[${i}].action_id must be one of ${ACTION_IDS.join(', ')}`);
      for (const f of [...SENTENCE_FIELDS, 'roadmap_measure']) if (typeof a?.[f] !== 'string' || !a[f].trim()) errors.push(`actions[${i}].${f} must be a non-empty string`);
    });
  }
  if (typeof obj.evidence_does_not_support !== 'string' || !obj.evidence_does_not_support.trim()) errors.push('evidence_does_not_support must be a non-empty string');
  return errors;
}

// The tool loop. Returns the transcript; never throws on model behaviour (only on transport).
export async function runAgent({ client, tools, userMessage, tag, maxTurns = 10, thinking = false, countyId = null, promptVersion = 'v1' }) {
  if (!PROMPTS[promptVersion]) throw new Error(`unknown prompt version ${promptVersion}`);
  const messages = [{ role: 'system', content: PROMPTS[promptVersion] }, { role: 'user', content: userMessage }];
  const toolCalls = []; const turns = []; let final = null; let formatRepairs = 0;
  for (let turn = 0; turn < maxTurns; turn += 1) {
    const r = await client.chat(messages, { tools: TOOL_SCHEMAS, toolChoice: 'auto', thinking, tag, maxTokens: thinking ? 8000 : 3000 });
    turns.push({ seconds: r.seconds, usage: r.usage, finish_reason: r.finish_reason, n_tool_calls: r.tool_calls.length, reasoning_chars: r.reasoning.length });
    if (r.tool_calls.length) {
      messages.push({ role: 'assistant', content: r.text || '', tool_calls: r.tool_calls });
      for (const call of r.tool_calls) {
        const name = call.function?.name; let args = null; let output;
        try { args = JSON.parse(call.function?.arguments || '{}'); output = tools.call(name, args); } catch { output = { error: 'arguments are not valid JSON' }; }
        toolCalls.push({ turn, name, args, ok: !output?.error, output });
        messages.push({ role: 'tool', tool_call_id: call.id, name, content: JSON.stringify(output) });
      }
      continue;
    }
    messages.push({ role: 'assistant', content: r.text || '' });
    const parsed = parseFinal(r.text);
    const errors = parsed.kind === 'plan' ? validatePlan(parsed.obj, countyId, tools.knownCounties.map((c) => c.county_id)) : parsed.kind === 'invalid' ? [parsed.error] : [];
    if (errors.length && formatRepairs === 0) {
      // One format repair before any checking: the content has not been judged yet.
      formatRepairs += 1;
      messages.push({ role: 'user', content: `Your answer does not follow the required format: ${errors.join('; ')}. Answer again with only the JSON object described in the instructions (or only {"refusal": "<one sentence>"}).` });
      continue;
    }
    final = { text: r.text, parsed, errors };
    break;
  }
  return { messages, toolCalls, turns, final, formatRepairs };
}

const lastOutput = (toolCalls, name, pred = () => true) => [...toolCalls].reverse().find((c) => c.name === name && c.ok && pred(c))?.output ?? null;
const stripSource = (o) => { if (!o) return null; const { roadmap, ...rest } = o; return rest; };
const actionPart = (o) => { if (!o) return null; const { evidence, ...rest } = o; return rest; };

export const CLAIM_KIND = 'sentence of a county action-plan draft written by a language model from the tool outputs in `facts`; it may combine measured public statistics, model scenarios under stated assumptions, and published evidence';

// Which tool outputs Jev sees for each field.
//   v1: every field sees the county brief, the county portfolio, the action and its roadmap measure.
//   v2 (field-scoped, chosen after the two-county pilot and logged before the full run): each field
//       sees the tool output the system prompt tells the model to take it from. The number check
//       is the same in both: every tool output of the run.
export const GATE_VERSION = 'v2';
export function fieldClaims({ gateVersion = GATE_VERSION, ev, rm, briefFacts, portfolioFacts, evidenceIds }) {
  const evPart = actionPart(ev); const rmPart = stripSource(rm);
  if (gateVersion === 'v1') {
    const claim = { kind: 'SCENARIO', facts: { county_brief: briefFacts, county_portfolio: portfolioFacts, action: evPart, roadmap_measure: rmPart }, evidence: evidenceIds };
    return Object.fromEntries(SENTENCE_FIELDS.map((f) => [f, claim]));
  }
  const pm = rm?.primaryMeasure;
  return {
    action: { kind: 'SCENARIO', facts: { action: evPart, roadmap_measure: rmPart }, evidence: evidenceIds },
    rationale: { kind: 'SCENARIO', facts: { county_brief: briefFacts, county_portfolio: portfolioFacts, action: ev ? { action_id: ev.action_id, title: ev.title, action: ev.action } : null }, evidence: evidenceIds },
    owner_role: { kind: 'MEASURED', facts: { action_title: ev?.title ?? null, accountable_owner: ev?.accountable_owner ?? null, roadmap_measure_owner: pm ? { id: pm.id, owner_en: pm.owner_en, owner: pm.owner } : null }, evidence: [] },
    indicator: { kind: 'MEASURED', facts: { action_title: ev?.title ?? null, indicator_to_monitor: ev?.indicator_to_monitor ?? null, roadmap_measure_metrics: pm ? { id: pm.id, metrics: pm.metrics } : null }, evidence: [] },
  };
}

// Gate a plan: the number check against every tool output of this run, the roadmap measure id
// checked by code, then Jev per sentence. Returns the record stored in plans-v1.json.
export async function gatePlan({ plan, toolCalls, countyId, app, jev, gateVersion = GATE_VERSION }) {
  const allowed = allowedFrom(toolCalls.map((c) => c.output));
  const brief = lastOutput(toolCalls, 'get_county_brief', (c) => c.output.county_id === countyId);
  const portfolio = lastOutput(toolCalls, 'get_portfolio', (c) => c.output.county_id === countyId) || lastOutput(toolCalls, 'get_portfolio');
  const briefFacts = brief ? brief.claims.map((c) => ({ text: c.text, kind: c.kind, facts: c.facts })) : null;
  const portfolioFacts = portfolio ? (({ picks, ...rest }) => rest)(portfolio) : null;
  const actions = [];
  for (const a of plan.actions) {
    const ev = lastOutput(toolCalls, 'get_evidence', (c) => c.args?.action_id === a.action_id);
    const rm = lastOutput(toolCalls, 'get_roadmap_measure', (c) => c.args?.action_id === a.action_id);
    const expected = rm ? [rm.primaryMeasure?.id, ...(rm.relatedMeasures || []).map((m) => m.id)].filter(Boolean) : [];
    const roadmapCheck = { measure: a.roadmap_measure, ok: expected.includes(String(a.roadmap_measure).trim()), expected, toolCalled: !!rm };
    const evidenceIds = ev ? ev.evidence.map((e) => e.id) : [];
    const claims = fieldClaims({ gateVersion, ev, rm, briefFacts, portfolioFacts, evidenceIds });
    const sentences = await Promise.all(SENTENCE_FIELDS.map((field) => gateSentence({ field, text: a[field], allowed, claim: claims[field], evidenceRows: app.evidence, claimKind: CLAIM_KIND, jev })));
    actions.push({
      action_id: a.action_id, title: ev?.title ?? null, roadmap_measure: roadmapCheck,
      roadmap: rm?.primaryMeasure ? { id: rm.primaryMeasure.id, title_en: rm.primaryMeasure.title_en, pages: rm.primaryMeasure.pages, url: rm.primaryMeasure.url, fit: rm.fit } : null,
      toolsCalled: { get_evidence: !!ev, get_roadmap_measure: !!rm }, sentences,
    });
  }
  const limitFacts = plan.actions.map((a) => {
    const ev = lastOutput(toolCalls, 'get_evidence', (c) => c.args?.action_id === a.action_id);
    const rm = lastOutput(toolCalls, 'get_roadmap_measure', (c) => c.args?.action_id === a.action_id);
    return { action_id: a.action_id, action: actionPart(ev), roadmap_reading: rm ? { statement: rm.statement, reading_en: rm.reading_en, gap_en: rm.gap_en, noRoadmapMeasureFor: rm.noRoadmapMeasureFor } : null };
  });
  const limitEvidence = [...new Set(plan.actions.flatMap((a) => lastOutput(toolCalls, 'get_evidence', (c) => c.args?.action_id === a.action_id)?.evidence?.map((e) => e.id) ?? []))];
  const evidenceLimit = await gateSentence({ field: 'evidence_does_not_support', text: plan.evidence_does_not_support, allowed, claim: { kind: 'SCENARIO', facts: { actions: limitFacts }, evidence: limitEvidence }, evidenceRows: app.evidence, claimKind: CLAIM_KIND, jev });
  const all = [...actions.flatMap((a) => a.sentences), evidenceLimit];
  return {
    gateVersion, actions, evidenceLimit,
    counts: { sentences: all.length, kept: all.filter((s) => s.kept).length, dropped: all.filter((s) => !s.kept).length, roadmapMeasureOk: actions.filter((a) => a.roadmap_measure.ok).length },
    toolCoverage: { brief: !!brief, portfolio: !!portfolio, evidenceForAll: actions.every((a) => a.toolsCalled.get_evidence), roadmapForAll: actions.every((a) => a.toolsCalled.get_roadmap_measure) },
  };
}

// Recheck used by the summary and the tests: a kept sentence must have no unmatched number.
export function keptWithUnmatchedNumber(gated, toolCalls) {
  const allowed = allowedFrom(toolCalls.map((c) => c.output));
  const all = [...gated.actions.flatMap((a) => a.sentences), gated.evidenceLimit];
  return all.filter((s) => s.kept && !numberCheck(s.text, allowed).ok).length;
}
