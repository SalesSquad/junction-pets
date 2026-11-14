// Claim check: does each sentence of a county brief follow from the evidence it cites?
//
// Code owns the workflow. The sentences are rebuilt on the server from app.json, so a
// browser cannot submit its own text or its own evidence. A TypeSafe System One model
// (Jev) then answers one narrow Choice question per sentence and returns a calibrated
// distribution; code turns that into SUPPORTED / NOT_SUPPORTED / UNCLEAR. Anything
// that is not a confident "supports" goes to a human. The key stays on the server
// (TYPESAFE_API_KEY); without it the check reports NOT_CONFIGURED instead of guessing.
import { readFileSync } from 'node:fs';
import { buildBrief } from './claims.mjs';

export const AUTO_ACCEPT = 0.8;
const ENDPOINT = process.env.TYPESAFE_ENDPOINT || 'https://api.typesafe.ai';
const MODEL = process.env.TYPESAFE_MODEL || 'jev-latest';

export const QUESTION = {
  type: 'choice',
  instructions: [
    'A public-health brief contains the sentence in `claim`.',
    '`evidence` lists the published findings the sentence cites and `computed` gives the statistics it was generated from.',
    'Judge only whether `evidence` and `computed` together back the sentence, including its numbers and its direction (higher or lower, better or worse).',
  ].join(' '),
  criteria: {
    supports: 'The evidence and computed statistics state or directly imply what the sentence says, with matching numbers and direction.',
    contradicts: 'The evidence or computed statistics say something that conflicts with the sentence: a different number, the opposite direction, or a stronger claim than the evidence allows (for example a causal or guaranteed effect where the evidence is observational or a scenario).',
    says_nothing: 'The evidence and computed statistics do not address what the sentence says, or are too thin to tell.',
  },
};

export function buildState(claim, evidenceRows) {
  const byId = new Map(evidenceRows.map((r) => [r.id, r]));
  return {
    claim: claim.text,
    claim_kind: claim.kind === 'SCENARIO' ? 'model scenario with stated assumptions and a range' : 'measured public statistic',
    evidence: claim.evidence.map((id) => byId.get(id)).filter(Boolean).map((r) => ({ id: r.id, finding: r.claim, unit: r.unit, citation: r.citation, caveat: r.notes || null })),
    computed: claim.support || null,
  };
}

export function verdictFrom(answer, autoAccept = AUTO_ACCEPT) {
  const p = answer?.probabilities || {};
  const choice = answer?.choice;
  const confidence = answer?.confidence ?? null;
  let verdict = 'UNCLEAR';
  if (choice === 'supports' && (p.supports ?? 0) >= autoAccept) verdict = 'SUPPORTED';
  else if (choice === 'contradicts' && (p.contradicts ?? 0) >= 0.5) verdict = 'NOT_SUPPORTED';
  return { verdict, probability: p.supports ?? null, confidence, probabilities: p, needsHumanReview: verdict !== 'SUPPORTED' };
}

async function ask(state, { apiKey, fetchImpl }) {
  const res = await fetchImpl(`${ENDPOINT}/v1/systemone`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ model: MODEL, state: JSON.stringify(state), questions: { support: QUESTION } }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`typesafe http ${res.status}`);
  const json = await res.json();
  return { answer: json.answers?.support, model: json.model, usage: json.usage };
}

// claims: [{id}] from the browser. Text, evidence and support always come from the server-side rebuild.
export async function verifyClaims(claims, {
  apiKey = process.env.TYPESAFE_API_KEY, fetchImpl = globalThis.fetch,
  app = JSON.parse(readFileSync(new URL('../web/data/app.json', import.meta.url), 'utf8')), concurrency = 6,
} = {}) {
  const wanted = (Array.isArray(claims) ? claims : []).slice(0, 40);
  const briefs = new Map();
  const resolved = wanted.map((c) => {
    const regionId = String(c?.id || '').split('-')[0];
    if (!briefs.has(regionId)) briefs.set(regionId, buildBrief(app, regionId));
    const server = briefs.get(regionId)?.claims.find((x) => x.id === c.id);
    return { requested: c, server };
  });
  const base = resolved.map(({ requested, server }) => ({
    id: requested?.id ?? null,
    known: !!server,
    textMatchesServer: server ? requested.text == null || requested.text === server.text : false,
    evidenceBound: server ? server.evidence.every((id) => app.evidence.some((r) => r.id === id && r.verified)) : false,
  }));
  if (!apiKey) return { status: 'NOT_CONFIGURED', reason: 'TYPESAFE_API_KEY is not set on the server', results: base.map((b) => ({ ...b, verdict: null })) };
  const results = new Array(resolved.length);
  let cursor = 0; let failures = 0; let model = null; const usage = { input_tokens: 0, output_tokens: 0 };
  const worker = async () => {
    for (;;) {
      const i = cursor; cursor += 1;
      if (i >= resolved.length) return;
      const { server } = resolved[i];
      if (!server) { results[i] = { ...base[i], verdict: 'UNCLEAR', needsHumanReview: true, reason: 'UNKNOWN_CLAIM' }; continue; }
      try {
        const out = await ask(buildState(server, app.evidence), { apiKey, fetchImpl });
        model = out.model ?? model;
        usage.input_tokens += out.usage?.input_tokens ?? 0; usage.output_tokens += out.usage?.output_tokens ?? 0;
        results[i] = { ...base[i], ...verdictFrom(out.answer) };
      } catch (err) {
        failures += 1;
        results[i] = { ...base[i], verdict: 'UNCLEAR', needsHumanReview: true, reason: 'SERVICE_ERROR' };
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, resolved.length) }, worker));
  return { status: failures === resolved.length && resolved.length ? 'SERVICE_ERROR' : 'CHECKED', model, autoAccept: AUTO_ACCEPT, usage, results };
}
