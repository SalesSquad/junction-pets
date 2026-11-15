// Cost-aware cascade (WS3). Haiku with all guidance modules answers first and gets
// one lint-driven repair turn. The request escalates to Sonnet with routed modules
// only when (a) lint issues remain after repair, (b) personal or special-category
// data is involved, or (c) a high-risk proposal is on the table. The decision and
// its reasons are deterministic and returned with the answer.
import { readFileSync } from 'node:fs';
import { RESPONSE_SCHEMA_V2 } from '../../solutions/aiven-decision-bridge/bridge.mjs';
import { lintResponse } from '../../solutions/aiven-decision-bridge/lint.mjs';
import { MODULES, systemFor } from '../../pets/aiven/modules/router.mjs';
import { composeTurn } from './untrusted.mjs';

const ALL = ['core', ...Object.keys(MODULES)].map(n => readFileSync(new URL(`../../pets/aiven/modules/${n}.md`, import.meta.url), 'utf8')).join('\n\n');
const SENSITIVE = /\b(patient|health|clinic|diagnos|henkilötunnus|hetu|personal data|gdpr|registry|salary|bank account|iban|social security)\b/i;

export function escalationReasons(response, request, issuesAfterRepair) {
  const reasons = [];
  if (issuesAfterRepair.length) reasons.push('lint issues remain after repair');
  const cls = response?.governance?.data_classification;
  if (SENSITIVE.test(request) || cls === 'personal' || cls === 'special_category') reasons.push('personal or special-category data');
  if ((response?.action_proposals ?? []).some(p => p.risk === 'high')) reasons.push('high-risk proposal');
  return reasons;
}

// `claude(model, prompt, system, schema)` is injected so hosts and tests choose the transport.
export async function answerWithCascade({ request, attachments = [], claude, small = 'haiku', large = 'sonnet' }) {
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
  const reasons = escalationReasons(a.data, request, issues);
  if (!reasons.length) return { response: a.data, route, reasons, cost };
  const big = await claude(large, prompt, systemFor(request).system, RESPONSE_SCHEMA_V2); cost += big.cost ?? 0;
  if (!big.data) return { response: a.data, route: `${route} (escalation failed)`, reasons, cost };
  return { response: big.data, route: large, reasons, cost };
}
