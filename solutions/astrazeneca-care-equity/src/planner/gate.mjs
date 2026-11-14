// The gate every planner sentence must pass, in this order. A failed sentence is dropped and
// counted, never repaired.
//   1. code: every number in the sentence (digits, number words two to ninety, roadmap measure
//      ids such as 3.1.2) must equal a number found in the tool outputs of the same run;
//   2. TypeSafe System One (Jev), reusing src/claim-check.mjs: one request with the Choice
//      `faithful` and the Noul `overclaim`; only verdict SUPPORTED is kept.
// Jev answers are cached on disk by the sha256 of the request, and every request is reserved in
// a token ledger with a hard USD cap before it is sent (the pattern of scribe/judges/core.py).
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { AUTO_ACCEPT, OVERCLAIM_AT, QUESTIONS, buildState, verdictFrom } from '../claim-check.mjs';

const WORDS = {
  two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
  thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19,
  twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90, hundred: 100, thousand: 1000,
};
const MEASURE = /\b\d+\.\d+\.\d+\b/g;
const WORD = new RegExp(`\\b(${Object.keys(WORDS).join('|')})\\b`, 'gi');

// Numbers in English text: comma = thousands separator, dot = decimal. Measure ids are taken out
// first and returned separately, so 3.1.2 is not read as 3.1 and 2.
export function extractNumbers(text) {
  const s = String(text ?? '');
  const measures = s.match(MEASURE) || [];
  const rest = s.replace(MEASURE, ' ');
  const numbers = (rest.match(/\d[\d,]*(?:\.\d+)?/g) || []).map((t) => Number(t.replace(/,/g, ''))).filter(Number.isFinite);
  const words = [...rest.matchAll(WORD)].map((m) => WORDS[m[1].toLowerCase()]);
  return { numbers, words, measures };
}

// Every number a tool returned: JSON numbers (with their absolute value, and x100 for shares
// between 0 and 1) and every number, number word and measure id inside its strings.
export function allowedFrom(outputs) {
  const nums = new Set(); const measures = new Set();
  const addNum = (v) => { nums.add(v); nums.add(Math.abs(v)); if (Math.abs(v) > 0 && Math.abs(v) < 1) nums.add(Math.round(Math.abs(v) * 100 * 1000) / 1000); };
  const walk = (node) => {
    if (node == null) return;
    if (typeof node === 'number') { if (Number.isFinite(node)) addNum(node); return; }
    if (typeof node === 'string') {
      const x = extractNumbers(node);
      x.numbers.forEach(addNum); x.words.forEach((w) => nums.add(w)); x.measures.forEach((m) => measures.add(m));
      return;
    }
    if (Array.isArray(node)) { node.forEach(walk); return; }
    if (typeof node === 'object') for (const v of Object.values(node)) walk(v);
  };
  walk(outputs);
  return { nums: [...nums], measures };
}

export function numberCheck(text, allowed) {
  const x = extractNumbers(text);
  const has = (n) => allowed.nums.some((a) => Math.abs(a - n) < 1e-9);
  const unmatched = [...x.numbers.filter((n) => !has(n)), ...x.words.filter((n) => !has(n)).map((n) => `word:${n}`), ...x.measures.filter((m) => !allowed.measures.has(m)).map((m) => `measure:${m}`)];
  return { ok: unmatched.length === 0, unmatched, counted: x.numbers.length + x.words.length + x.measures.length };
}

// ---- Jev with cache and ledger -------------------------------------------------------------------
export const JEV_USD_PER_TOKEN = 0.042 / 1e6; // owner's price, as in scribe/judges/core.py
const RESERVE_TOKENS = 20_000;
const save = (path, obj) => { const tmp = path instanceof URL ? new URL(`${path.href}.tmp`) : `${path}.tmp`; writeFileSync(tmp, `${JSON.stringify(obj, null, 1)}\n`); renameSync(tmp, path); };

export class JevLedger {
  constructor(path, maxUsd = 1.0) {
    this.path = path; this.limit = maxUsd / JEV_USD_PER_TOKEN;
    this.d = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : { requests: 0, tokens: 0, input_tokens: 0, output_tokens: 0, reserved_tokens: 0, failed_attempts: 0 };
    this.d.max_usd = maxUsd;
  }
  _save() { this.d.updated = new Date().toISOString(); this.d.cost_usd = this.d.tokens * JEV_USD_PER_TOKEN; this.d.cost_usd_counting_reservations = (this.d.tokens + this.d.reserved_tokens) * JEV_USD_PER_TOKEN; save(this.path, this.d); }
  open() {
    if (this.d.tokens + this.d.reserved_tokens + RESERVE_TOKENS > this.limit) throw new Error('BUDGET_STOP');
    this.d.reserved_tokens += RESERVE_TOKENS; this.d.requests += 1; this._save();
  }
  settle(usage) {
    this.d.input_tokens += usage.input_tokens; this.d.output_tokens += usage.output_tokens;
    this.d.tokens += usage.input_tokens + usage.output_tokens; this.d.reserved_tokens -= RESERVE_TOKENS; this._save();
  }
  fail() { this.d.failed_attempts += 1; this._save(); } // the reservation stays: a failed attempt may have been billed
}

export class JevGate {
  constructor({ dir, apiKey = process.env.TYPESAFE_API_KEY, endpoint = process.env.TYPESAFE_ENDPOINT || 'https://api.typesafe.ai', model = process.env.TYPESAFE_MODEL || 'jev-latest', maxUsd = 1.0, fetchImpl = globalThis.fetch, concurrency = 6 } = {}) {
    this.dir = dir; this.apiKey = apiKey; this.endpoint = endpoint; this.model = model; this.fetch = fetchImpl;
    mkdirSync(new URL('jev-cache/', dir), { recursive: true });
    this.ledger = new JevLedger(new URL('jev-ledger.json', dir), maxUsd);
    this.stats = { cached: 0, paid: 0, errors: 0, budget_stop: 0 };
    this.slots = concurrency; this.queue = [];
  }
  async _slot(fn) {
    if (this.slots === 0) await new Promise((r) => this.queue.push(r));
    this.slots -= 1;
    try { return await fn(); } finally { this.slots += 1; const next = this.queue.shift(); if (next) next(); }
  }
  // claim = { text, kind, facts, evidence: [evidence ids] }; evidenceRows = app.evidence
  async judge(claim, evidenceRows, claimKind) {
    const state = buildState(claim, evidenceRows);
    if (claimKind) state.claim_kind = claimKind;
    const body = { model: this.model, state, questions: QUESTIONS };
    const hash = createHash('sha256').update(JSON.stringify(body)).digest('hex');
    const cachePath = new URL(`jev-cache/${hash}.json`, this.dir);
    if (existsSync(cachePath)) {
      this.stats.cached += 1;
      const rec = JSON.parse(readFileSync(cachePath, 'utf8'));
      return { ...verdictFrom(rec.answers), model: rec.model, request_sha256: hash, cached: true };
    }
    if (!this.apiKey) { this.stats.errors += 1; return { verdict: 'UNCLEAR', error: 'NOT_CONFIGURED', request_sha256: hash, cached: false }; }
    return this._slot(async () => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try { this.ledger.open(); } catch { this.stats.budget_stop += 1; return { verdict: 'UNCLEAR', error: 'BUDGET_STOP', request_sha256: hash, cached: false }; }
        try {
          const res = await this.fetch(`${this.endpoint}/v1/systemone`, {
            method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${this.apiKey}` },
            body: JSON.stringify(body), signal: AbortSignal.timeout(60_000),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const json = await res.json();
          if (!json.answers?.faithful || !json.answers?.overclaim) throw new Error('malformed answer');
          const usage = { input_tokens: Number(json.usage?.input_tokens ?? 0), output_tokens: Number(json.usage?.output_tokens ?? 0) };
          this.ledger.settle(usage); this.stats.paid += 1;
          save(cachePath, { answers: json.answers, model: json.model ?? null, usage, ts: new Date().toISOString() });
          return { ...verdictFrom(json.answers), model: json.model ?? null, request_sha256: hash, cached: false, usage };
        } catch (err) {
          this.ledger.fail(); this.stats.errors += 1;
          if (attempt === 1) return { verdict: 'UNCLEAR', error: String(err.message || err).slice(0, 120), request_sha256: hash, cached: false };
          await new Promise((r) => setTimeout(r, 1500));
        }
      }
      return { verdict: 'UNCLEAR', error: 'unreachable', request_sha256: hash, cached: false };
    });
  }
}

// One sentence through both fences. Returns the per-sentence record stored in plans-v1.json.
export async function gateSentence({ field, text, allowed, claim, evidenceRows, claimKind, jev }) {
  const numbers = numberCheck(text, allowed);
  const rec = { field, text, numberCheck: numbers, jev: null, kept: false, reason: null };
  if (!text || typeof text !== 'string' || !text.trim()) { rec.reason = 'EMPTY'; return rec; }
  if (!numbers.ok) { rec.reason = 'NUMBER_NOT_IN_TOOL_OUTPUT'; return rec; }
  const v = await jev.judge({ ...claim, text }, evidenceRows, claimKind);
  rec.jev = { verdict: v.verdict, pSupports: v.probability ?? null, overclaim: v.overclaim ?? null, confidence: v.confidence ?? null, model: v.model ?? null, cached: v.cached, error: v.error ?? null, request_sha256: v.request_sha256 };
  if (v.verdict === 'SUPPORTED') rec.kept = true;
  else rec.reason = v.error ? 'NOT_CHECKED' : v.verdict === 'NOT_SUPPORTED' ? 'JEV_NOT_SUPPORTED' : 'JEV_UNCLEAR';
  return rec;
}

export const GATE = { autoAccept: AUTO_ACCEPT, overclaimAt: OVERCLAIM_AT, rule: 'keep only if every number equals a tool output of the same run, then Jev faithful=supports with p>=0.8 and overclaim<0.5 (src/claim-check.mjs verdictFrom = SUPPORTED); otherwise drop, never repair' };
