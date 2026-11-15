/**
 * Raster drawing QA strategies.
 *  - perQuestion: naive baseline, one model call per question, number only.
 *  - perDrawing: one call per drawing for all its questions; the model must
 *    enumerate every counted instance with a point marker (human-verifiable
 *    region) and the count is derived from the listed instances.
 */
import { chat, normalizeCoords } from './vlm.mjs';
import { ocr } from './ocr.mjs';
import { classifyTag, countByRule, ruleFor } from './rules.mjs';

const BASELINE_SYSTEM = 'You answer quantity questions about a construction drawing image. Reply with only JSON: {"answer": number|null}.';

export async function perQuestion(drawing, questions, cfg) {
  const out = [];
  for (const q of questions) {
    const r = await chat({ system: BASELINE_SYSTEM, text: q.question, images: [drawing.url], maxTokens: 8192 }, cfg);
    out.push({ q, predicted: r.json?.answer ?? null, call: meta(r) });
  }
  return out;
}

const FINNISH_PLAN_SYSTEM = `You are a construction quantity-takeoff assistant reading a floor plan image.
Finnish real-estate plans use room abbreviations: MH makuuhuone (bedroom), OH olohuone (living room),
K keittiö, KK keittokomero, TK tupakeittiö, KT keittiötila, AK avokeittiö (all kitchens), RT/RH ruokailu,
ET eteinen (hall), KH kylpyhuone, PH/PESUH pesuhuone, KPH kylpyhuone, SH suihkuhuone (bathrooms/washrooms),
S or SAUNA (sauna), WC (separate toilet room), VH vaatehuone, VAR varasto, KHH kodinhoitohuone, TKH, AH,
PARV/PARVEKE/LASITETTU PARVEKE (balcony), TER terassi. A plan sheet may show several storeys (e.g. 1. KRS, 2. KRS, KELLARI).
Symbols: a window is a thin double/triple line opening in an exterior wall; a door is a leaf with a swing arc;
a WC seat is an oval bowl with tank; a sink/wash basin is a small rounded basin (a double-bowl sink is one);
a shower is a square tray with diagonal/cross or a corner, a bathtub a long rounded rectangle.
Method: inspect the whole image systematically (left to right, top to bottom). For every count question list
EVERY counted item as an instance with its centre point x,y normalized to 0..1 of the image (origin top-left)
and a short label (room text or symbol type). Do not double count. The answer must equal the number of instances.
For a question whose answer is zero, return answer 0 and no instances. Never guess beyond what is drawn.
Reply with only JSON: {"answers":[{"id":string,"answer":number|null,"instances":[{"x":number,"y":number,"label":string}]}]}`;

export async function perDrawing(drawing, questions, cfg, { thinking = false } = {}) {
  const items = questions.map((q, i) => ({ id: `q${i + 1}`, question: q.question, unit: q.unit }));
  const r = await chat({
    system: FINNISH_PLAN_SYSTEM, maxTokens: 16384, images: [drawing.url], thinking,
    text: `Answer all questions about this one drawing:\n${JSON.stringify(items)}`,
  }, cfg);
  const byId = new Map((r.json?.answers ?? []).map(a => [a.id, a]));
  return questions.map((q, i) => {
    const a = byId.get(`q${i + 1}`);
    const instances = (Array.isArray(a?.instances) ? a.instances : [])
      .map(p => ({ point: normalizeCoords([p?.x, p?.y], drawing.width, drawing.height), label: String(p?.label ?? '').slice(0, 40) }))
      .filter(p => p.point);
    const stated = a?.answer ?? null;
    // Enumerate-then-count: for counts the listed instances are the answer (and its evidence).
    const predicted = q.type === 'count' && instances.length > 0 ? instances.length : stated;
    return { q, predicted, stated, instances, call: i === 0 ? meta(r) : { shared: true } };
  });
}

function meta(r) {
  return { ok: r.ok, http: r.http, finish: r.finish, ms: r.ms, attempts: r.attempts, usage: r.usage, error: r.error, content: r.content?.slice(0, 1500) };
}

const ANSWER_SYSTEM = `${FINNISH_PLAN_SYSTEM.split('Method:')[0]}
Think carefully, inspecting the whole image region by region, then reply with only JSON:
{"answers":[{"id":string,"answer":number|null,"where":string}]} where "where" briefly names the rooms/areas counted.`;

/** One call per drawing with reasoning enabled; answers only (no instance lists) to bound output. */
export async function perDrawingAnswers(drawing, questions, cfg) {
  const items = questions.map((q, i) => ({ id: `q${i + 1}`, question: q.question }));
  const r = await chat({ system: ANSWER_SYSTEM, maxTokens: 24576, images: [drawing.url], thinking: true,
    text: `Answer all questions about this one drawing:\n${JSON.stringify(items)}` }, cfg);
  const byId = new Map((r.json?.answers ?? []).map(a => [a.id, a]));
  return questions.map((q, i) => {
    const a = byId.get(`q${i + 1}`);
    return { q, predicted: a?.answer ?? null, stated: a?.answer ?? null, where: a?.where, call: i === 0 ? meta(r) : { shared: true } };
  });
}

const MARK_SYSTEM = `${FINNISH_PLAN_SYSTEM.split('Method:')[0]}
The counts below were already decided. For each item place exactly "answer" markers, one on the centre of
each counted room label or symbol, x,y normalized 0..1 of the image (origin top-left).
Reply with only JSON: {"marks":[{"id":string,"points":[{"x":number,"y":number,"label":string}]}]}`;

/**
 * Answer with reasoning, then ground: a cheap second call (reasoning off) places one marker
 * per counted item so a person can verify each count on the drawing in seconds.
 */
export async function answersMarked(drawing, questions, cfg) {
  const answers = await perDrawingAnswers(drawing, questions, cfg);
  const items = answers.map((a, i) => ({ id: `q${i + 1}`, question: a.q.question, answer: a.predicted }))
    .filter(it => typeof it.answer === 'number' && it.answer > 0);
  if (!items.length) return answers;
  const r = await chat({ system: MARK_SYSTEM, maxTokens: 8192, images: [drawing.url], thinking: false,
    text: JSON.stringify(items) }, cfg);
  const byId = new Map((r.json?.marks ?? []).map(m => [m.id, m.points]));
  const first = answers[0].call;
  return answers.map((a, i) => {
    const pts = (byId.get(`q${i + 1}`) ?? [])
      .map(p => ({ point: normalizeCoords([p?.x, p?.y], drawing.width, drawing.height), label: String(p?.label ?? '').slice(0, 40) }))
      .filter(p => p.point);
    const call = i === 0 ? { ...first, usage: sumUsage(first?.usage, r.usage), markCall: meta(r) } : a.call;
    return { ...a, instances: pts, call };
  });
}
const sumUsage = (a = {}, b = {}) => ({ prompt: (a.prompt ?? 0) + (b.prompt ?? 0), completion: (a.completion ?? 0) + (b.completion ?? 0), reasoning: (a.reasoning ?? 0) + (b.reasoning ?? 0) });

/**
 * Cascade: OCR rules answer when they found positive evidence (or for storeys, where the
 * default of one storey is reliable); every other question goes to one reasoning call per drawing.
 */
export async function cascade(drawing, questions, cfg) {
  const tokens = await ocr(drawing.path);
  const routed = questions.map(q => {
    const rule = ruleFor(q.question);
    if (!rule || rule === 'door' || rule === 'window') return { q };
    const res = countByRule(rule, tokens);
    return rule === 'floors' || res.evidence.length > 0 ? { q, rule, res } : { q };
  });
  const forModel = routed.filter(r => !r.rule).map(r => r.q);
  const model = forModel.length ? await perDrawingAnswers(drawing, forModel, cfg) : [];
  const byQ = new Map(model.map(a => [a.q, a]));
  const modelCall = model[0]?.call;
  return routed.map(({ q, rule, res }, i) => ({
    ...(rule ? { q, predicted: res.answer, stated: res.answer, method: `ocr:${rule}`,
      evidence: res.evidence.map(t => ({ text: t.text, box: t.box })) } : { ...byQ.get(q), method: 'model' }),
    call: i === 0 && modelCall ? modelCall : { shared: true },
  }));
}

/**
 * Hybrid: deterministic OCR rules (door/window size tags, room abbreviations, storey titles)
 * answer with exact token boxes as evidence; the vision model answers only symbol questions
 * (WC seats, sinks, showers/baths) and plans that carry no size tags at all.
 */
export async function hybrid(drawing, questions, cfg, { useModel = true } = {}) {
  const tokens = await ocr(drawing.path);
  const hasTags = tokens.some(t => classifyTag(t.text));
  const routed = questions.map(q => {
    const rule = ruleFor(q.question);
    const usable = rule && (hasTags || !['door', 'window'].includes(rule));
    return { q, rule: usable ? rule : null };
  });
  const forModel = routed.filter(r => !r.rule).map(r => r.q);
  const modelAnswers = useModel && forModel.length ? await perDrawing(drawing, forModel, cfg, { thinking: false }) : [];
  const byQ = new Map(modelAnswers.map(a => [a.q, a]));
  const modelCall = modelAnswers.find(a => a.call && !a.call.shared)?.call;
  const results = routed.map(({ q, rule }) => {
    if (rule) {
      const { answer, evidence } = countByRule(rule, tokens);
      return { q, predicted: answer, stated: answer, method: `ocr:${rule}`,
        evidence: evidence.map(t => ({ text: t.text, box: t.box })) };
    }
    const a = byQ.get(q);
    return a ? { ...a, method: 'model' } : { q, predicted: null, stated: null, method: 'none' };
  });
  // Attach the single model call (if any) to exactly one row so usage is counted once.
  return results.map((r, i) => ({ ...r, call: i === 0 && modelCall ? modelCall : { shared: true } }));
}

export const STRATEGIES = {
  'per-question': perQuestion,
  'per-drawing': (d, q, c) => perDrawing(d, q, c, { thinking: false }),
  'per-drawing-think': (d, q, c) => perDrawing(d, q, c, { thinking: true }),
  'ocr-rules': (d, q, c) => hybrid(d, q, c, { useModel: false }),
  hybrid: (d, q, c) => hybrid(d, q, c, { useModel: true }),
  'per-drawing-answers': perDrawingAnswers,
  'answers-marked': answersMarked,
  cascade,
};
