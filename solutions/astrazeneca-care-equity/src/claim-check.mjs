// Claim check: does each sentence of a county brief say what its data and evidence say?
//
// Code owns the workflow. The sentences and their facts are rebuilt on the server from
// app.json, so a browser cannot submit its own text or evidence. A TypeSafe System One
// model (Jev) answers two narrow, independent questions per sentence in one request:
//   faithful  (Choice): is everything in the sentence stated in `facts` and `evidence`?
//   overclaim (Noul):   does it present a measured difference or a scenario as a proven
//                       cause or a guaranteed result?
// Code turns the calibrated answers into SUPPORTED / NOT_SUPPORTED / UNCLEAR; anything
// that is not a confident pass goes to a human. The key stays on the server
// (TYPESAFE_API_KEY); without it the check reports NOT_CONFIGURED instead of guessing.
import { readFileSync } from 'node:fs';
import { buildBrief } from './claims.mjs';

export const AUTO_ACCEPT = 0.8;
export const OVERCLAIM_AT = 0.5;
const ENDPOINT = process.env.TYPESAFE_ENDPOINT || 'https://api.typesafe.ai';
const MODEL = process.env.TYPESAFE_MODEL || 'jev-latest';

export const QUESTIONS = {
  faithful: {
    type: 'choice',
    instructions: 'The sentence in `claim` was written for a public-health brief. `facts` holds the statistics computed for this county and `evidence` lists published findings the sentence may cite. Judge whether everything the sentence states is given in `facts` or `evidence`, with the same numbers, the same place and the same direction.',
    criteria: {
      supports: 'Every number, place, period and direction in the sentence matches `facts` or `evidence`. Wording may differ; content does not.',
      contradicts: 'The sentence conflicts with `facts` or `evidence`: a different number, another county or period, or the opposite direction (for example above instead of below, more instead of fewer).',
      says_nothing: 'The sentence states something that `facts` and `evidence` do not contain.',
    },
  },
  overclaim: {
    type: 'noul',
    instructions: 'The sentence in `claim` presents something as a proven cause, a certain effect or a guaranteed result, although `facts` describe only a measured difference or a model scenario under assumptions.',
  },
};

export function buildState(claim, evidenceRows) {
  const byId = new Map(evidenceRows.map((r) => [r.id, r]));
  return {
    claim: claim.text,
    claim_kind: claim.kind === 'SCENARIO' ? 'model scenario with stated assumptions and a range' : 'measured public statistic',
    facts: claim.facts ?? {},
    evidence: (claim.evidence || []).map((id) => byId.get(id)).filter(Boolean).map((r) => ({ id: r.id, finding: r.claim, unit: r.unit, caveat: r.notes || null })),
  };
}

export function verdictFrom(answers, { autoAccept = AUTO_ACCEPT, overclaimAt = OVERCLAIM_AT } = {}) {
  const f = answers?.faithful; const p = f?.probabilities || {};
  const overclaim = answers?.overclaim?.noul ?? null;
  let verdict = 'UNCLEAR';
  if (f?.choice === 'supports' && (p.supports ?? 0) >= autoAccept && overclaim != null && overclaim < overclaimAt) verdict = 'SUPPORTED';
  else if ((f?.choice === 'contradicts' && (p.contradicts ?? 0) >= 0.5) || (overclaim != null && overclaim >= overclaimAt)) verdict = 'NOT_SUPPORTED';
  return { verdict, probability: p.supports ?? null, confidence: f?.confidence ?? null, overclaim, needsHumanReview: verdict !== 'SUPPORTED' };
}

export async function judgeClaim(claim, evidenceRows, { apiKey = process.env.TYPESAFE_API_KEY, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(`${ENDPOINT}/v1/systemone`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ model: MODEL, state: buildState(claim, evidenceRows), questions: QUESTIONS }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`typesafe http ${res.status}`);
  const json = await res.json();
  return { ...verdictFrom(json.answers), model: json.model, usage: json.usage };
}

// claims: [{id}] from the browser. Text, facts and evidence always come from the server-side rebuild.
export async function verifyClaims(claims, {
  apiKey = process.env.TYPESAFE_API_KEY, fetchImpl = globalThis.fetch,
  app = JSON.parse(readFileSync(new URL('../web/data/app.json', import.meta.url), 'utf8')), concurrency = 6,
} = {}) {
  const wanted = (Array.isArray(claims) ? claims : []).slice(0, 40);
  const briefs = new Map();
  const resolved = wanted.map((c) => {
    const regionId = String(c?.id || '').split('-')[0];
    if (!briefs.has(regionId)) briefs.set(regionId, buildBrief(app, regionId));
    return { requested: c, server: briefs.get(regionId)?.claims.find((x) => x.id === c.id) };
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
        const out = await judgeClaim(server, app.evidence, { apiKey, fetchImpl });
        model = out.model ?? model;
        usage.input_tokens += out.usage?.input_tokens ?? 0; usage.output_tokens += out.usage?.output_tokens ?? 0;
        const { model: _m, usage: _u, ...verdict } = out;
        results[i] = { ...base[i], ...verdict };
      } catch (err) {
        failures += 1;
        results[i] = { ...base[i], verdict: 'UNCLEAR', needsHumanReview: true, reason: 'SERVICE_ERROR' };
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, resolved.length) }, worker));
  return { status: failures === resolved.length && resolved.length ? 'SERVICE_ERROR' : 'CHECKED', model, autoAccept: AUTO_ACCEPT, usage, results };
}
