// Plain-language Finnish county summaries: written by a language model, kept only if checked.
//
// Generation (Claude Haiku) is the one place where free text is produced, so it is fenced
// in twice before anything reaches the product:
//   1. code: every number in a sentence must occur in the source claims it cites;
//   2. TypeSafe System One (Jev): one request per sentence with two independent questions,
//      a Choice (does the sentence follow from its source claims?) and a Noul (does it
//      add a causal or guaranteed-outcome claim the sources do not make?).
// A sentence that fails either fence is dropped and counted, never repaired by hand.
// Usage: TYPESAFE_API_KEY=... node src/narratives.mjs   (reads data/narratives/raw/*.json)
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { buildBrief } from './claims.mjs';
import { verifyClaims } from './claim-check.mjs';

export const KEEP_AT = 0.8;
export const OVERCLAIM_AT = 0.5;
const ENDPOINT = process.env.TYPESAFE_ENDPOINT || 'https://api.typesafe.ai';
const MODEL = process.env.TYPESAFE_MODEL || 'jev-latest';

// Numbers as written in English source text: comma = thousands separator, dot = decimal.
export function numbersEn(text) {
  return (text.match(/\d[\d,]*(?:\.\d+)?/g) || []).map((t) => Number(t.replace(/,/g, ''))).filter(Number.isFinite);
}
// Numbers as written in Finnish: comma = decimal, (narrow) space = thousands separator.
export function numbersFi(text) {
  const out = [];
  for (const m of text.matchAll(/\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?/g)) {
    out.push(Number(m[0].replace(/[   ]/g, '').replace(',', '.')));
  }
  return out.filter(Number.isFinite);
}
export function numberCheck(sentenceFi, sourceTexts) {
  const allowed = sourceTexts.flatMap(numbersEn);
  const unmatched = numbersFi(sentenceFi).filter((n) => !allowed.some((a) => Math.abs(a - n) < 1e-9));
  return { ok: unmatched.length === 0, unmatched };
}

export const QUESTIONS = {
  faithful: {
    type: 'choice',
    instructions: 'The Finnish sentence in `sentence_fi` was written from the English statements in `source_claims`. Judge whether everything the Finnish sentence says is stated in those source statements, with the same numbers and the same direction.',
    criteria: {
      supports: 'Everything in the Finnish sentence is stated in the source statements; nothing is added, reversed or exaggerated.',
      contradicts: 'The Finnish sentence says something that conflicts with the source statements, such as a different number, the opposite direction, or a different place or period.',
      says_nothing: 'The Finnish sentence contains information that the source statements do not contain.',
    },
  },
  overclaim: {
    type: 'noul',
    instructions: 'The Finnish sentence in `sentence_fi` presents something as a cause, a proven effect or a guaranteed result, while `source_claims` only report a measured difference or a model scenario with assumptions.',
  },
};

export function decide(numbers, answers, { keepAt = KEEP_AT, overclaimAt = OVERCLAIM_AT } = {}) {
  const pSupports = answers?.faithful?.probabilities?.supports ?? null;
  const pOverclaim = answers?.overclaim?.noul ?? null;
  let reason = null;
  if (!numbers.ok) reason = 'NUMBER_NOT_IN_SOURCE';
  else if (pSupports == null || pOverclaim == null) reason = 'NOT_CHECKED';
  else if (answers.faithful.choice !== 'supports' || pSupports < keepAt) reason = 'NOT_FAITHFUL';
  else if (pOverclaim >= overclaimAt) reason = 'OVERCLAIM';
  return { keep: reason === null, reason, pSupports, pOverclaim };
}

async function askJev(state, { apiKey, fetchImpl }) {
  const res = await fetchImpl(`${ENDPOINT}/v1/systemone`, {
    method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ model: MODEL, state, questions: QUESTIONS }), signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`typesafe http ${res.status}`);
  return res.json();
}

export async function verifyNarrative(raw, brief, { apiKey, fetchImpl = globalThis.fetch } = {}) {
  const byId = new Map(brief.claims.map((c) => [c.id, c]));
  const kept = []; const rejected = []; let model = null; const usage = { input_tokens: 0, output_tokens: 0 };
  for (const s of raw.sentences || []) {
    const sources = (s.claimIds || []).map((id) => byId.get(id)).filter(Boolean);
    if (!s.fi || sources.length === 0 || sources.length !== (s.claimIds || []).length) { rejected.push({ fi: s.fi ?? null, claimIds: s.claimIds ?? [], reason: 'UNKNOWN_SOURCE_CLAIM' }); continue; }
    const numbers = numberCheck(s.fi, sources.map((c) => c.text));
    let answers = null;
    if (numbers.ok && apiKey) {
      try {
        const json = await askJev({ sentence_fi: s.fi, source_claims: sources.map((c) => ({ id: c.id, kind: c.kind, text: c.text })) }, { apiKey, fetchImpl });
        answers = json.answers; model = json.model ?? model;
        usage.input_tokens += json.usage?.input_tokens ?? 0; usage.output_tokens += json.usage?.output_tokens ?? 0;
      } catch { answers = null; }
    }
    const d = decide(numbers, answers);
    const row = { fi: s.fi, claimIds: s.claimIds, pSupports: d.pSupports, pOverclaim: d.pOverclaim };
    if (d.keep) kept.push(row); else rejected.push({ ...row, reason: d.reason, unmatchedNumbers: numbers.unmatched });
  }
  return { kept, rejected, model, usage };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const at = (p) => new URL(p, import.meta.url);
  const app = JSON.parse(readFileSync(at('../web/data/app.json'), 'utf8'));
  const apiKey = process.env.TYPESAFE_API_KEY || '';
  const rawDir = at('../data/narratives/raw/');
  const counties = {}; const totals = { generated: 0, kept: 0, rejected: {}, input_tokens: 0, output_tokens: 0 }; let model = null;
  const files = existsSync(rawDir) ? readdirSync(rawDir).filter((f) => f.endsWith('.json')).sort() : [];
  for (const f of files) {
    const raw = JSON.parse(readFileSync(new URL(f, rawDir), 'utf8'));
    const brief = buildBrief(app, raw.regionId);
    if (!brief) continue;
    const res = await verifyNarrative(raw, brief, { apiKey });
    counties[raw.regionId] = { generator: raw.generator, kept: res.kept, rejected: res.rejected };
    totals.generated += (raw.sentences || []).length; totals.kept += res.kept.length; model = res.model ?? model;
    for (const r of res.rejected) totals.rejected[r.reason] = (totals.rejected[r.reason] || 0) + 1;
    totals.input_tokens += res.usage.input_tokens; totals.output_tokens += res.usage.output_tokens;
  }
  // The English brief goes through the same service, one Choice per sentence.
  const claimCheck = {}; const claimTotals = { SUPPORTED: 0, NOT_SUPPORTED: 0, UNCLEAR: 0 }; let claimModel = null;
  if (apiKey) {
    for (const region of app.analysis.regions) {
      const brief = buildBrief(app, region.regionId);
      const out = await verifyClaims(brief.claims, { apiKey, app });
      claimModel = out.model ?? claimModel;
      claimCheck[region.regionId] = out.results.map((r) => ({ id: r.id, verdict: r.verdict, probability: r.probability ?? null, confidence: r.confidence ?? null }));
      for (const r of out.results) claimTotals[r.verdict] = (claimTotals[r.verdict] || 0) + 1;
      totals.input_tokens += out.usage?.input_tokens ?? 0; totals.output_tokens += out.usage?.output_tokens ?? 0;
    }
  }
  const out = {
    schemaVersion: 'care-equity-narratives-v1', generatedAt: new Date().toISOString(), snapshotSha256: app.provenance.snapshotSha256,
    verifier: apiKey ? { service: 'TypeSafe System One', model: model ?? claimModel, keepAt: KEEP_AT, overclaimAt: OVERCLAIM_AT } : null,
    status: apiKey ? 'CHECKED' : 'NOT_CONFIGURED', totals, counties,
    claimCheck: apiKey ? { model: claimModel, autoAccept: 0.8, totals: claimTotals, counties: claimCheck } : null,
  };
  mkdirSync(at('../data/narratives/'), { recursive: true });
  writeFileSync(at('../data/narratives/fi-v1.json'), `${JSON.stringify(out, null, 1)}\n`);
  console.log(JSON.stringify({ status: out.status, counties: Object.keys(counties).length, totals, claimTotals, model: out.verifier?.model ?? null }));
}
