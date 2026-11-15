/**
 * Minimal OpenAI-compatible vision client (e.g. Verda-hosted Nemotron 3.5 Super VL).
 * Endpoint, model and key come only from the environment; the key is never logged.
 * One bounded retry on truncation or unparseable JSON.
 */
import { readFile } from 'node:fs/promises';

export function config(env = process.env) {
  const baseUrl = env.STOA_VLM_BASE_URL || 'https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1';
  const model = env.STOA_VLM_MODEL || 'nemotron-3.5-super-vl';
  const key = env.STOA_VLM_KEY || '';
  if (!key) throw new Error('STOA_VLM_KEY is not set.');
  return { baseUrl, model, key };
}

/** Extract the last top-level JSON object from model text (tolerates prose/fences around it). */
export function extractJson(text) {
  const s = String(text ?? '').slice(0, 20000);
  for (let end = s.lastIndexOf('}'); end >= 0; end = s.lastIndexOf('}', end - 1)) {
    for (let start = s.indexOf('{'); start >= 0 && start < end; start = s.indexOf('{', start + 1)) {
      try { return JSON.parse(s.slice(start, end + 1)); } catch { /* next candidate */ }
    }
  }
  return null;
}

/** Normalize a point/box given in 0..1, 0..1000 (per-mille) or pixel units to 0..1. */
export function normalizeCoords(values, width, height) {
  if (!Array.isArray(values) || !values.every(Number.isFinite)) return null;
  const max = Math.max(...values.map(Math.abs));
  let out;
  if (max <= 1.0001) out = values;
  else if (max <= 1000.5 && !(width > 1000 && max > 1000)) out = values.map(v => v / 1000);
  else if (width && height) out = values.map((v, i) => v / (i % 2 === 0 ? width : height));
  else return null;
  return out.map(v => Math.min(1, Math.max(0, v)));
}

export async function imageDataUrl(path) {
  const bytes = await readFile(path);
  const mime = bytes[0] === 0x89 ? 'image/png' : 'image/jpeg';
  return { url: `data:${mime};base64,${bytes.toString('base64')}`, bytes: bytes.length, ...pngSize(bytes) };
}
function pngSize(b) {
  return b[0] === 0x89 && b.length > 24 ? { width: b.readUInt32BE(16), height: b.readUInt32BE(20) } : {};
}

export async function chat({ system, text, images = [], maxTokens = 8192, temperature = 0.2, retries = 1, thinking = true }, cfg = config()) {
  const body = {
    model: cfg.model, temperature, top_p: 0.95, max_tokens: maxTokens,
    // Nemotron's chat template switch; long hidden reasoning otherwise exhausts the output budget.
    ...(thinking ? {} : { chat_template_kwargs: { enable_thinking: false } }),
    messages: [
      ...(system ? [{ role: 'system', content: system }] : []),
      { role: 'user', content: [{ type: 'text', text }, ...images.map(url => ({ type: 'image_url', image_url: { url } }))] },
    ],
  };
  const usage = { prompt: 0, completion: 0, reasoning: 0 };
  let last;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const t0 = performance.now();
    const res = await fetch(`${cfg.baseUrl}/chat/completions`, {
      method: 'POST', redirect: 'error', signal: AbortSignal.timeout(300_000),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${cfg.key}` },
      body: JSON.stringify(body),
    });
    const raw = await res.text();
    const ms = Math.round(performance.now() - t0);
    if (!res.ok) { last = { ok: false, http: res.status, error: raw.slice(0, 200).split(cfg.key).join('[REDACTED]'), ms }; continue; }
    const j = JSON.parse(raw);
    usage.prompt += j.usage?.prompt_tokens ?? 0;
    usage.completion += j.usage?.completion_tokens ?? 0;
    usage.reasoning += j.usage?.completion_tokens_details?.reasoning_tokens ?? 0;
    const content = j.choices?.[0]?.message?.content ?? '';
    const finish = j.choices?.[0]?.finish_reason;
    const json = extractJson(content);
    last = { ok: !!json && finish !== 'length', json, finish, ms, attempts: attempt + 1, content: content.slice(0, 4000) };
    if (last.ok) break;
  }
  return { ...last, usage };
}
