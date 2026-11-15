/**
 * Typed decisions: one provider-neutral interface over System One style judges.
 *
 *   OpenAI Decisions API  POST /v1/decisions   model gpt-6-luna   predicate | choice | score
 *   TypeSafe Jev          POST /v1/systemone   model jev-1.14.0   noul | choice | score
 *
 * Both return probabilities, not prose. Code asks narrow questions over explicit state, reads the
 * probabilities and owns the policy. Every answer can be kept as a JudgmentReceipt: the question,
 * the exact state it was asked over (with digests) and the answer, so a receiver can re-ask the
 * same question with its own judge instead of trusting ours.
 */
import { canonicalJson, sha256Hex } from "../lib/council.ts";

export type Question =
  | { kind: "yesno"; name: string; instructions: string; yes?: string; no?: string }
  | { kind: "choice"; name: string; instructions: string; options: Record<string, string> }
  | { kind: "score"; name: string; instructions: string; levels: string[] }
  /** TypeSafe Jev 1.14 only, needs an image. Always returns a box: pair it with a yes/no "is it there?". */
  | { kind: "box"; name: string; instructions: string };

/** An image sent with a request; its reference string appears in the state, instructions or options. */
export interface ImageAsset {
  format: "png" | "jpg";
  dataBase64: string;
}
export type Assets = Record<string, ImageAsset>;

/** Bounding box edges as fractions of the image, from the top-left corner. */
export interface Box {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface Answer {
  name: string;
  kind: Question["kind"];
  /** yesno: probability of yes. */
  p?: number;
  /** choice: selected label; score: not set. */
  choice?: string;
  /** choice: probability per label; score: probability per level index. */
  probabilities?: Record<string, number>;
  /** score: probability-weighted level index. */
  score?: number;
  /** box: where the target is. */
  box?: Box;
  confidence?: number;
  refused?: boolean;
}

export interface DecisionResult {
  provider: string;
  model: string;
  answers: Answer[];
  usage: { inputTokens: number; cachedTokens: number };
  ms: number;
}

export interface DecisionProvider {
  /** Stable provider id, e.g. "openai-decisions" or "typesafe-jev". */
  id: string;
  /** `assets` maps reference strings to images (TypeSafe; sent with the images header). */
  decide(state: unknown, questions: Question[], assets?: Assets): Promise<DecisionResult>;
}

/** TypeSafe's opt-in for images and Box questions ("dreamer-ready", not production-ready). */
export const IMAGES_HEADER = { "TypeSafe-Danger-Zone-Images": "true" } as const;
export const needsImages = (questions: Question[], assets?: Assets) => !!(assets && Object.keys(assets).length) || questions.some((q) => q.kind === "box");

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

const chunks = <T>(xs: T[], n: number) => Array.from({ length: Math.ceil(xs.length / n) }, (_, i) => xs.slice(i * n, i * n + n));

async function merge(provider: string, model: string, parts: Array<Promise<Omit<DecisionResult, "ms" | "provider">>>, t0: number): Promise<DecisionResult> {
  const done = await Promise.all(parts);
  return {
    provider,
    model: done[0]?.model ?? model,
    answers: done.flatMap((d) => d.answers),
    usage: done.reduce((u, d) => ({ inputTokens: u.inputTokens + d.usage.inputTokens, cachedTokens: u.cachedTokens + d.usage.cachedTokens }), { inputTokens: 0, cachedTokens: 0 }),
    ms: Date.now() - t0,
  };
}

// ---------- OpenAI Decisions API ----------

/** yes/no criteria are folded into the instructions: a predicate has no criteria field. */
export function toOpenAiQuestion(q: Question) {
  if (q.kind === "yesno") {
    const crit = [q.yes && `Answer yes if: ${q.yes}`, q.no && `Answer no if: ${q.no}`].filter(Boolean).join("\n");
    return { type: "predicate", name: q.name, instructions: crit ? `${q.instructions}\n${crit}` : q.instructions };
  }
  if (q.kind === "choice") return { type: "choice", name: q.name, instructions: q.instructions, choices: Object.entries(q.options).map(([value, description]) => ({ value, description })) };
  if (q.kind === "box") throw new Error("OpenAI Decisions has no Box question type");
  return { type: "score", name: q.name, instructions: q.instructions, levels: q.levels.map((description, i) => ({ label: String(i), description })) };
}

export function fromOpenAiAnswer(a: any, q: Question): Answer {
  if (a?.refusal || a?.type === "refusal") return { name: q.name, kind: q.kind, refused: true };
  if (q.kind === "yesno") return { name: q.name, kind: "yesno", p: a.probability };
  const probabilities = Object.fromEntries((a.probabilities ?? []).map((x: any) => [x.value ?? x.label, x.probability]));
  if (q.kind === "choice") return { name: q.name, kind: "choice", choice: a.choice, probabilities, confidence: a.confidence };
  return { name: q.name, kind: "score", score: a.score, probabilities, confidence: a.confidence };
}

export function openaiDecisions(opts: { apiKey: string; model?: string; baseUrl?: string; fetch?: FetchLike; maxQuestions?: number; cacheKey?: string }): DecisionProvider {
  const model = opts.model ?? "gpt-6-luna";
  const f = opts.fetch ?? fetch;
  const base = opts.baseUrl ?? "https://api.openai.com";
  return {
    id: "openai-decisions",
    async decide(state, questions, assets) {
      if (needsImages(questions, assets)) throw new Error("openai-decisions adapter: images and Box questions are not wired; use typesafe-jev");
      const t0 = Date.now();
      const input = [{ role: "user", content: [{ type: "input_json", data: state }] }];
      const parts = chunks(questions, opts.maxQuestions ?? 400).map(async (qs) => {
        const res = await f(`${base}/v1/decisions`, {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${opts.apiKey}` },
          body: JSON.stringify({ model, input, questions: qs.map(toOpenAiQuestion), ...(opts.cacheKey ? { prompt_cache_key: opts.cacheKey } : {}) }),
        });
        const body = (await res.json()) as any;
        if (!res.ok) throw new Error(`OpenAI Decisions ${res.status}: ${body?.error?.message ?? "error"}`);
        const byName = new Map((body.answers ?? []).map((a: any) => [a.name, a]));
        return {
          model: body.model ?? model,
          answers: qs.map((q) => fromOpenAiAnswer(byName.get(q.name), q)),
          usage: { inputTokens: body.usage?.input_tokens ?? 0, cachedTokens: body.usage?.input_tokens_details?.cached_tokens ?? 0 },
        };
      });
      return merge("openai-decisions", model, parts, t0);
    },
  };
}

// ---------- TypeSafe Jev ----------

export function toJevQuestion(q: Question) {
  if (q.kind === "box") return { type: "box", instructions: q.instructions };
  if (q.kind === "yesno") return { type: "noul", instructions: q.instructions, ...(q.yes || q.no ? { criteria: { true: q.yes ?? null, false: q.no ?? null } } : {}) };
  if (q.kind === "choice") return { type: "choice", instructions: q.instructions, criteria: q.options };
  return { type: "score", instructions: q.instructions, criteria: q.levels };
}

export function fromJevAnswer(a: any, q: Question): Answer {
  if (!a) return { name: q.name, kind: q.kind, refused: true };
  if (q.kind === "yesno") return { name: q.name, kind: "yesno", p: a.noul };
  if (q.kind === "box") return { name: q.name, kind: "box", box: { top: a.box.top, bottom: a.box.bottom, left: a.box.left, right: a.box.right }, confidence: a.confidence ?? undefined };
  if (q.kind === "choice") return { name: q.name, kind: "choice", choice: a.choice, probabilities: { ...a.probabilities }, confidence: a.confidence };
  return { name: q.name, kind: "score", score: a.score, probabilities: { ...a.probabilities }, confidence: a.confidence };
}

type SystemOneFn = (req: { state: unknown; questions: Record<string, unknown>; model?: string; assets?: Record<string, unknown> }, options?: { headers?: Record<string, string> }) => Promise<any>;

/**
 * `systemOne` is the SDK's client.systemOne (Node/relay) or any function with the same contract.
 * `toAsset` turns an ImageAsset into what `systemOne` sends. With the @typesafe-ai/sdk client it is
 * REQUIRED: pass `(a) => image(new Blob([bytes], { type }))`, since the SDK cannot encode plain objects.
 * Without it the asset goes as JSON base64 ({type, format, data_base64}), which only a raw HTTP
 * `systemOne` accepts. Requests with images or Box questions carry TypeSafe-Danger-Zone-Images.
 */
export function typesafeJev(opts: { systemOne: SystemOneFn; model?: string; maxQuestions?: number; toAsset?: (a: ImageAsset) => unknown }): DecisionProvider {
  const model = opts.model ?? "jev-1.14.0";
  const asset = opts.toAsset ?? ((a: ImageAsset) => ({ type: "image", format: a.format, data_base64: a.dataBase64 }));
  return {
    id: "typesafe-jev",
    async decide(state, questions, assets) {
      const t0 = Date.now();
      const images = needsImages(questions, assets);
      const parts = chunks(questions, opts.maxQuestions ?? 64).map(async (qs) => {
        const req = { state: state as any, model, questions: Object.fromEntries(qs.map((q) => [q.name, toJevQuestion(q)])), ...(assets && Object.keys(assets).length ? { assets: Object.fromEntries(Object.entries(assets).map(([k, a]) => [k, asset(a)])) } : {}) };
        const r = await opts.systemOne(req, images ? { headers: { ...IMAGES_HEADER } } : undefined);
        return { model: r.model ?? model, answers: qs.map((q) => fromJevAnswer(r.answers?.[q.name], q)), usage: { inputTokens: r.usage?.input_tokens ?? 0, cachedTokens: 0 } };
      });
      return merge("typesafe-jev", model, parts, t0);
    },
  };
}

// ---------- browser: through the relay (keys stay server-side) ----------

/**
 * Our own Decisions API on the device (gemma/serve_mlx_decide.py: Gemma 4 E2B with the clause-judge LoRA; or
 * the older gpu/serve_decide.py). The same typed contract as the hosted judges, on 127.0.0.1, so the person's
 * situation does not leave the machine.
 *   choice over a state with `situation`   -> the trained listwise judge
 *   yes/no over `situation` and `clause`   -> the older pointwise server, if that is what is running
 * Anything else goes to `fallback` (a hosted judge) or fails, and the caller treats the judge as abstaining.
 */
export function localDecisions(opts: { baseUrl: string; fetch?: FetchLike; fallback?: DecisionProvider; id?: string; timeoutMs?: number }): DecisionProvider {
  const f = opts.fetch ?? fetch;
  return {
    id: opts.id ?? "local-decisions",
    async decide(state, questions, assets) {
      const st = state as { situation?: unknown; clause?: unknown };
      const choice = typeof st?.situation === "string" && questions.length > 0 && questions.every((q) => q.kind === "choice");
      const yesno = typeof st?.situation === "string" && typeof st?.clause === "string" && questions.length > 0 && questions.every((q) => q.kind === "yesno");
      if (!choice && !yesno) {
        if (!opts.fallback) throw new Error("local judge: only a choice over {situation} or yes/no over {situation, clause}; no fallback configured");
        return opts.fallback.decide(state, questions, assets);
      }
      const t0 = Date.now();
      const payload = {
        state: choice ? { situation: st.situation } : { situation: st.situation, clause: st.clause },
        questions: questions.map((q) => (q.kind === "choice" ? { kind: q.kind, name: q.name, instructions: q.instructions, options: q.options } : { kind: q.kind, name: q.name, instructions: q.instructions })),
      };
      const res = await f(`${opts.baseUrl}/v1/decisions`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload), ...(opts.timeoutMs ? { signal: AbortSignal.timeout(opts.timeoutMs) } : {}) });
      const body = (await res.json()) as any;
      if (!res.ok || body?.error) throw new Error(body?.error ?? `local judge ${res.status}`);
      const answers: Answer[] = body.answers.map((a: any) => (a.kind === "choice" ? { name: a.name, kind: "choice", choice: a.choice, probabilities: a.probabilities, confidence: a.probabilities?.[a.choice] } : { name: a.name, kind: "yesno", p: a.p }));
      return { provider: "local", model: body.adapter ? `${body.model} + ${body.adapter}` : body.model, answers, usage: { inputTokens: 0, cachedTokens: 0 }, ms: Date.now() - t0 };
    },
  };
}

/**
 * A typed judge on any OpenAI-compatible endpoint that returns log-probabilities (vLLM, e.g. NVIDIA Nemotron
 * on a Verda container). Choice: the options are lettered and the next-token probabilities of the letters are
 * the answer. Yes/no: the probabilities of "yes" and "no". No reasoning tokens, two output tokens.
 */
/** At temperature 0 an answer token carries nearly all the probability; below this the model did not answer. */
const MIN_ANSWER_MASS = 0.5;
export function logprobDecisions(opts: { id: string; baseUrl: string; apiKey: string; model: string; fetch?: FetchLike; timeoutMs?: number }): DecisionProvider {
  const f = opts.fetch ?? fetch;
  const LETTERS = "ABCDEFGHIJKLMNOP";
  const ask = async (content: string) => {
    const res = await f(`${opts.baseUrl}/chat/completions`, { method: "POST", headers: { authorization: `Bearer ${opts.apiKey}`, "content-type": "application/json" }, body: JSON.stringify({ model: opts.model, temperature: 0, max_tokens: 2, reasoning_effort: "none", logprobs: true, top_logprobs: 20, messages: [{ role: "user", content }] }), ...(opts.timeoutMs ? { signal: AbortSignal.timeout(opts.timeoutMs) } : {}) });
    const body = (await res.json()) as any;
    if (!res.ok) throw new Error(body?.error?.message ?? `${opts.id} ${res.status}`);
    const top: Array<{ token: string; logprob: number }> = body.choices?.[0]?.logprobs?.content?.[0]?.top_logprobs ?? [];
    // Compare on the letters of the token, so "B)", "(B", "**B" and "Yes," count; case is kept, so the words "a" and "i" are not options.
    return { mass: (pred: (t: string) => boolean) => top.filter((t) => pred(t.token.replace(/[^A-Za-z]/g, ""))).reduce((a, t) => a + Math.exp(t.logprob), 0), tokens: body.usage?.prompt_tokens ?? 0 };
  };
  const show = (state: unknown) => {
    const st = state as Record<string, unknown>;
    return st && typeof st === "object" ? Object.entries(st).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join("\n") : String(state);
  };
  return {
    id: opts.id,
    async decide(state, questions) {
      const t0 = Date.now();
      let inputTokens = 0;
      const answers: Answer[] = [];
      for (const q of questions) {
        if (q.kind === "choice") {
          const labels = Object.keys(q.options);
          if (labels.length > LETTERS.length) throw new Error(`${opts.id}: at most ${LETTERS.length} options`);
          const r = await ask(`${show(state)}\noptions:\n${labels.map((l, i) => `${LETTERS[i]}) ${q.options[l]}`).join("\n")}\nquestion: ${q.instructions} Answer with one letter.`);
          inputTokens += r.tokens;
          const raw = labels.map((_, i) => r.mass((t) => t === LETTERS[i]));
          const z = raw.reduce((a, x) => a + x, 0);
          // No option letter where the answer should start (no log-probabilities, a preamble, a refusal): that is
          // no answer. Renormalising it would report a uniform distribution as a confident pick of "A".
          if (z < MIN_ANSWER_MASS) throw new Error(`${opts.id}: no option letter in the first token (mass ${z.toFixed(3)})`);
          const probabilities = Object.fromEntries(labels.map((l, i) => [l, raw[i]! / z]));
          const choice = labels[raw.indexOf(Math.max(...raw))]!;
          answers.push({ name: q.name, kind: "choice", choice, probabilities, confidence: probabilities[choice] });
        } else if (q.kind === "yesno") {
          const r = await ask(`${show(state)}\nquestion: ${q.instructions}\nAnswer yes or no.`);
          inputTokens += r.tokens;
          const yes = r.mass((t) => /^yes$/i.test(t)), no = r.mass((t) => /^no$/i.test(t));
          if (yes + no < MIN_ANSWER_MASS) throw new Error(`${opts.id}: no yes or no in the first token (mass ${(yes + no).toFixed(3)})`);
          answers.push({ name: q.name, kind: "yesno", p: yes / (yes + no) });
        } else throw new Error(`${opts.id}: ${q.kind} questions are not supported`);
      }
      return { provider: opts.id, model: opts.model, answers, usage: { inputTokens, cachedTokens: 0 }, ms: Date.now() - t0 };
    },
  };
}

export function relayDecisions(provider: "openai" | "typesafe", opts: { baseUrl?: string; fetch?: FetchLike } = {}): DecisionProvider {
  const f = opts.fetch ?? fetch;
  return {
    id: provider === "openai" ? "openai-decisions" : "typesafe-jev",
    async decide(state, questions, assets) {
      const res = await f(`${opts.baseUrl ?? ""}/api/decide`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ provider, state, questions, assets }) });
      const body = (await res.json()) as any;
      if (!res.ok) throw new Error(body?.error ?? `relay ${res.status}`);
      return body as DecisionResult;
    },
  };
}

/** Intersection over union of two boxes (1 = identical). */
export function iou(a: Box, b: Box): number {
  const ix = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const iy = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const inter = ix * iy;
  const union = (a.right - a.left) * (a.bottom - a.top) + (b.right - b.left) * (b.bottom - b.top) - inter;
  return union > 0 ? inter / union : 0;
}

// ---------- receipts and replay ----------

export interface JudgmentReceipt {
  /** What the compiler used the answer for, e.g. "outcome-selection" or "same-rule-veto". */
  purpose: string;
  provider: string;
  model: string;
  question: Question;
  questionDigest: string;
  /** The exact state the question was asked over; small by construction (sentences and quotes). */
  state: unknown;
  stateDigest: string;
  answer: Answer;
  at: string;
}

export async function receiptsFor(purpose: string, state: unknown, questions: Question[], result: DecisionResult, at = new Date()): Promise<JudgmentReceipt[]> {
  const stateDigest = await sha256Hex(canonicalJson(state));
  return Promise.all(
    questions.map(async (question, i) => ({
      purpose,
      provider: result.provider,
      model: result.model,
      question,
      questionDigest: await sha256Hex(canonicalJson(question)),
      state,
      stateDigest,
      answer: result.answers[i]!,
      at: at.toISOString(),
    })),
  );
}

export interface ReplayOutcome {
  name: string;
  purpose: string;
  original: Answer;
  replayed?: Answer;
  agree: boolean;
  note?: string;
}

/**
 * Re-ask recorded questions with the receiver's own judge. Digests are recomputed first: a receipt
 * whose state or question does not match its digest is rejected without asking anything.
 * yes/no answers agree when they fall on the same side of the decision band (yes > hi, no < lo,
 * otherwise "unsure") or differ by at most `tolerance`; choices agree on the selected label.
 */
export async function replayReceipts(receipts: JudgmentReceipt[], provider: DecisionProvider, opts: { tolerance?: number; lo?: number; hi?: number } = {}): Promise<ReplayOutcome[]> {
  const { tolerance = 0.25, lo = 0.3, hi = 0.7 } = opts;
  const band = (p: number) => (p > hi ? "yes" : p < lo ? "no" : "unsure");
  const out: ReplayOutcome[] = [];
  const groups = new Map<string, JudgmentReceipt[]>();
  for (const r of receipts) {
    const ok = (await sha256Hex(canonicalJson(r.state))) === r.stateDigest && (await sha256Hex(canonicalJson(r.question))) === r.questionDigest;
    if (!ok) {
      out.push({ name: r.question.name, purpose: r.purpose, original: r.answer, agree: false, note: "digest mismatch: state or question was altered" });
      continue;
    }
    // One request per distinct (state, question): a panel leaves several receipts for the same question, and two
    // different questions may share a name ("tier" for the then and the now clause), which providers key by.
    const key = `${r.stateDigest}:${r.questionDigest}`;
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  for (const rs of groups.values()) {
    const res = await provider.decide(rs[0]!.state, [rs[0]!.question]);
    rs.forEach((r) => {
      const a = res.answers[0]!;
      let agree = false;
      if (r.answer.kind === "yesno" && a.p != null && r.answer.p != null) agree = band(a.p) === band(r.answer.p) || Math.abs(a.p - r.answer.p) <= tolerance;
      else if (r.answer.kind === "choice") agree = a.choice === r.answer.choice;
      else if (r.answer.kind === "score" && a.score != null && r.answer.score != null) agree = Math.abs(a.score - r.answer.score) <= 1;
      else if (r.answer.kind === "box" && a.box && r.answer.box) agree = iou(a.box, r.answer.box) >= 0.5;
      out.push({ name: r.question.name, purpose: r.purpose, original: r.answer, replayed: a, agree });
    });
  }
  return out;
}
