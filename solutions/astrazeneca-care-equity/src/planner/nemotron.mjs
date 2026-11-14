// Nemotron 3.5 Super VL client for the planner, in the request style of scribe/nemotron/common.py
// and scribe/generate.py: OpenAI-compatible POST {VERDA_INFERENCE_BASE_URL}/chat/completions,
// model "nemotron-3.5-super-vl", chat_template_kwargs.enable_thinking, four attempts with
// exponential back-off, every attempt reserved in a ledger before it is sent, concurrency capped
// (the endpoint is shared with another lane; this lane stays at 8 or less).
// The key is read from the environment only and is never logged or written. Hosted endpoints
// receive public aggregate statistics and SYNTHETIC text only.
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';

export const MODEL = 'nemotron-3.5-super-vl';
export const MAX_CONCURRENCY = 8;

const save = (path, obj) => { const tmp = path instanceof URL ? new URL(`${path.href}.tmp`) : `${path}.tmp`; writeFileSync(tmp, `${JSON.stringify(obj, null, 1)}\n`); renameSync(tmp, path); };

export class Ledger {
  constructor(path, cap) {
    this.path = path; this.cap = cap;
    this.d = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : { requests: 0 };
    this.d.cap = cap;
  }
  get requests() { return this.d.requests; }
  reserve() {
    if (this.d.requests >= this.cap) throw new Error(`CAP_REACHED ${this.cap}`);
    this.d.requests += 1; this.d.updated = new Date().toISOString(); save(this.path, this.d);
    return this.d.requests;
  }
}

export class Nemotron {
  constructor({ dir, cap = 1500, concurrency = 4, deadline = null, baseUrl = process.env.VERDA_INFERENCE_BASE_URL, apiKey = process.env.VERDA_INFERENCE_KEY, fetchImpl = globalThis.fetch, timeoutMs = 240_000 } = {}) {
    if (!baseUrl || !apiKey) throw new Error('VERDA_INFERENCE_BASE_URL and VERDA_INFERENCE_KEY must be set in the environment');
    mkdirSync(dir, { recursive: true });
    this.url = baseUrl.replace(/\/+$/, ''); this.key = apiKey; this.fetch = fetchImpl; this.timeoutMs = timeoutMs;
    this.ledger = new Ledger(new URL('ledger.json', dir), cap);
    this.requestsPath = new URL('requests.jsonl', dir);
    this.slots = Math.min(concurrency, MAX_CONCURRENCY); this.queue = [];
    this.deadline = deadline;
    this.errors = {}; this.tokens = { prompt_tokens: 0, completion_tokens: 0 }; this.sent = 0;
  }
  _record(fields) { appendFileSync(this.requestsPath, `${JSON.stringify({ ts: new Date().toISOString(), ...fields })}\n`); }
  async _slot(fn) {
    if (this.slots === 0) await new Promise((r) => this.queue.push(r));
    this.slots -= 1;
    try { return await fn(); } finally { this.slots += 1; const next = this.queue.shift(); if (next) next(); }
  }
  async chat(messages, { maxTokens = 3000, temperature = 0, thinking = false, tag = '', tools, toolChoice } = {}) {
    const body = { model: MODEL, messages, temperature, max_tokens: maxTokens, chat_template_kwargs: { enable_thinking: !!thinking } };
    if (tools) { body.tools = tools; body.tool_choice = toolChoice || 'auto'; }
    return this._slot(async () => {
      for (let attempt = 0; attempt < 4; attempt += 1) {
        if (this.deadline && Date.now() > this.deadline) throw new Error('lane deadline reached');
        const n = this.ledger.reserve(); this.sent += 1;
        const t = performance.now();
        try {
          const res = await this.fetch(`${this.url}/chat/completions`, {
            method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${this.key}` },
            body: JSON.stringify(body), signal: AbortSignal.timeout(this.timeoutMs),
          });
          if (res.status !== 200) throw new Error(`HTTP ${res.status}`);
          const json = await res.json();
          const choice = json.choices?.[0] || {}; const msg = choice.message || {}; const usage = json.usage || {};
          const seconds = Math.round(performance.now() - t) / 1000;
          this.tokens.prompt_tokens += Number(usage.prompt_tokens || 0); this.tokens.completion_tokens += Number(usage.completion_tokens || 0);
          this._record({ n, tag, attempt, status: 'ok', seconds, usage, finish_reason: choice.finish_reason ?? null });
          return { text: msg.content || '', reasoning: msg.reasoning_content || msg.reasoning || '', tool_calls: msg.tool_calls || [], usage, seconds, finish_reason: choice.finish_reason ?? null };
        } catch (err) {
          const detail = /^HTTP \d+$/.test(err.message) ? err.message : (err.name || 'Error');
          this.errors[detail] = (this.errors[detail] || 0) + 1;
          this._record({ n, tag, attempt, status: 'error', seconds: Math.round(performance.now() - t) / 1000, error: detail });
          if (attempt === 3) throw err;
          await new Promise((r) => setTimeout(r, (2 ** attempt + Math.random()) * 1000));
        }
      }
      throw new Error('unreachable');
    });
  }
}
