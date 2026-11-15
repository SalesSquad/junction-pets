// Cost-aware cascade (WS3). Haiku with all guidance modules answers first and gets
// one lint-driven repair turn. By default the request escalates to Sonnet with routed
// modules only when lint issues remain after repair, or when the caller marks the
// request as tool-heavy (live inspection that must enumerate and read many items,
// where Sonnet measured 0.975 vs Haiku 0.75-0.91).
// Measured on round3 (30 unread cases, opus+sonnet consensus): escalating on
// personal data or high-risk proposals sent 72 % of requests to Sonnet for no quality
// gain (cascade 75 %, Haiku+repair 77 %, Sonnet 77 %), so those triggers are opt-in.
import { readFileSync } from 'node:fs';
import { RESPONSE_SCHEMA_V2 } from '../../solutions/aiven-decision-bridge/bridge.mjs';
import { lintResponse } from '../../solutions/aiven-decision-bridge/lint.mjs';
import { MODULES, systemFor } from '../../pets/aiven/modules/router.mjs';
import { composeTurn } from './untrusted.mjs';

const ALL = ['core', ...Object.keys(MODULES)].map(n => readFileSync(new URL(`../../pets/aiven/modules/${n}.md`, import.meta.url), 'utf8')).join('\n\n');
const SENSITIVE = /\b(patient|health|clinic|diagnos|henkilötunnus|hetu|personal data|gdpr|registry|salary|bank account|iban|social security)\b/i;

export function escalationReasons(response, request, issuesAfterRepair, { escalateSensitive = false, toolHeavy = false } = {}) {
  const reasons = [];
  if (issuesAfterRepair.length) reasons.push('lint issues remain after repair');
  if (toolHeavy) reasons.push('tool-heavy request');
  if (escalateSensitive) {
    const cls = response?.governance?.data_classification;
    if (SENSITIVE.test(request) || cls === 'personal' || cls === 'special_category') reasons.push('personal or special-category data');
    if ((response?.action_proposals ?? []).some(p => p.risk === 'high')) reasons.push('high-risk proposal');
  }
  return reasons;
}

// `claude(model, prompt, system, schema)` is injected so hosts and tests choose the transport.
export async function answerWithCascade({ request, attachments = [], claude, small = 'haiku', large = 'sonnet', escalateSensitive = false, toolHeavy = false }) {
  const prompt = composeTurn(request, attachments);
  let cost = 0, route = small;
  let a = await claude(small, prompt, ALL, RESPONSE_SCHEMA_V2); cost += a.cost ?? 0;
  if (!a.data) return { error: a.error ?? 'no structured output', route, cost };
  let issues = lintResponse(a.data, request, attachments);
  if (issues.length) {
    const fix = await claude(small, `${prompt}\n\n---\nYour previous typed response was:\n${JSON.stringify(a.data)}\n\nAutomatic checks found these issues:\n${issues.map(i => '- ' + i).join('\n')}\n\nReturn a corrected, complete typed response.`, ALL, RESPONSE_SCHEMA_V2);
    cost += fix.cost ?? 0;
    if (fix.data) { a = fix; route = `${small}+repair`; issues = lintResponse(a.data, request, attachments); }
  }
  const reasons = escalationReasons(a.data, request, issues, { escalateSensitive, toolHeavy });
  if (!reasons.length) return { response: a.data, route, reasons, cost };
  const big = await claude(large, prompt, systemFor(request).system, RESPONSE_SCHEMA_V2); cost += big.cost ?? 0;
  if (!big.data) return { response: a.data, route: `${route} (escalation failed)`, reasons, cost };
  return { response: big.data, route: large, reasons, cost };
}
