/**
 * Two-lane retrieval for the Warrant Compiler (benchmark v2, section 4.3).
 *
 *  answer lane     the person's question as asked -> pages that state the rule plainly
 *  extraction      instrument, article and decisive quantity read from those pages (code, not model memory)
 *  authority lane  a citation-completion query built from the extracted sentence -> the legal text
 *  triangulation   the decisive quantity must re-appear in the re-fetched legal text;
 *                  a different quantity of the same kind, or none, means NEEDS_INFO
 *
 * The lanes are never fused into one list: fusion diluted both strengths in the benchmark.
 */

export interface LaneResult {
  url: string;
  title?: string;
  highlights: string[];
}

export type SearchFn = (query: string, objective: string) => Promise<LaneResult[]>;
export type FetchFn = (url: string) => Promise<string>;

// ---------- quantities ----------

export type QuantityKind = "money" | "duration" | "percent" | "distance";

export interface Quantity {
  kind: QuantityKind;
  value: number;
  unit: string; // currency code, time unit, "%", "km"
  text: string; // exactly as written in the source
}

const WORD_NUMBERS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17,
  eighteen: 18, nineteen: 19, twenty: 20, "twenty-one": 21, thirty: 30, sixty: 60, ninety: 90, a: 1, an: 1,
};
const ORDINALS: Record<string, number> = { first: 1, second: 2, third: 3, fourth: 4, fifth: 5 };
const CURRENCY: Record<string, string> = { "€": "EUR", eur: "EUR", euro: "EUR", euros: "EUR", "£": "GBP", gbp: "GBP", "$": "USD", usd: "USD", cad: "CAD", aud: "AUD" };
const TIME_UNITS: Record<string, string> = {
  minute: "minute", minutes: "minute", hour: "hour", hours: "hour", day: "day", days: "day",
  "calendar day": "day", "calendar days": "day", "business day": "business_day", "business days": "business_day",
  week: "week", weeks: "week", month: "month", months: "month", year: "year", years: "year",
};

const NUM = String.raw`(\d{1,3}(?:[ ,. ]\d{3})*(?:[.,]\d+)?|${Object.keys(WORD_NUMBERS).sort((a, b) => b.length - a.length).join("|")})`;
const parseNum = (s: string) => WORD_NUMBERS[s.toLowerCase()] ?? Number(s.replace(/[  ,](?=\d{3}\b)/g, "").replace(",", "."));

export function extractQuantities(text: string): Quantity[] {
  const out: Quantity[] = [];
  const push = (q: Quantity) => { if (Number.isFinite(q.value)) out.push(q); };
  // money: "€250", "EUR 250", "250 euros", "£220", "$400", "$7.25"
  // Thousands separators only before exactly three digits, so "£99.35 . 2" is £99.35, not "99.35 . 2".
  const AMOUNT = String.raw`(\d{1,3}(?:[ ,.\u202f\u00a0]\d{3})+(?:[.,]\d{1,2})?(?!\d)|\d+(?:[.,]\d+)?)`;
  for (const m of text.matchAll(new RegExp(String.raw`(€|£|\$|\b(?:EUR|GBP|USD|CAD|AUD)\b)\s?${AMOUNT}`, "gi")))
    push({ kind: "money", value: parseNum(m[2]!), unit: CURRENCY[m[1]!.toLowerCase()] ?? m[1]!.toUpperCase(), text: m[0] });
  for (const m of text.matchAll(new RegExp(String.raw`${AMOUNT}\s?(euros?|EUR|GBP|USD)\b`, "gi")))
    push({ kind: "money", value: parseNum(m[1]!), unit: CURRENCY[m[2]!.toLowerCase()] ?? m[2]!.toUpperCase(), text: m[0] });
  // percent: "25 %", "25%", "20 percent"
  for (const m of text.matchAll(/(\d+(?:[.,]\d+)?)\s?(%|per ?cent\b)/gi))
    push({ kind: "percent", value: parseNum(m[1]!), unit: "%", text: m[0] });
  // durations: "14 days", "fourteen days", "60 calendar days", "three hours", "120 minutes"
  for (const m of text.matchAll(new RegExp(String.raw`\b${NUM}[\s-](calendar days?|business days?|minutes?|hours?|days?|weeks?|months?|years?)\b(?!['\u2019]s)`, "gi"))) {
    const [value, unit] = normaliseDuration(parseNum(m[1]!), TIME_UNITS[m[2]!.toLowerCase()]!);
    push({ kind: "duration", value, unit, text: m[0] });
  }
  // ordinal durations: "third business day"
  for (const m of text.matchAll(/\b(first|second|third|fourth|fifth) business day\b/gi))
    push({ kind: "duration", value: ORDINALS[m[1]!.toLowerCase()]!, unit: "business_day", text: m[0] });
  // distance: "1,500 kilometres", "1500 km"
  for (const m of text.matchAll(/(\d[\d ,. ]*\d|\d)\s?(kilomet(?:re|er)s?|km)\b/gi))
    // "1.900 km" (German/Finnish thousands) is 1900 km; a distance is never written with three decimals.
    push({ kind: "distance", value: parseNum(/^\d{1,3}(?:\.\d{3})+$/.test(m[1]!.trim()) ? m[1]!.replace(/\./g, "") : m[1]!), unit: "km", text: m[0] });
  return out;
}

/** Minutes and hours compare as minutes; days and weeks as days; months, years and business days stay as they are. */
function normaliseDuration(value: number, unit: string): [number, string] {
  if (unit === "hour") return [value * 60, "minute"];
  if (unit === "week") return [value * 7, "day"];
  return [value, unit];
}

export const sameQuantity = (a: Quantity, b: Quantity) => a.kind === b.kind && a.unit === b.unit && Math.abs(a.value - b.value) < 1e-9;
const qKey = (q: Quantity) => `${q.kind}:${q.unit}:${q.value}`;

// ---------- instruments ----------

const INSTRUMENT_PATTERNS: RegExp[] = [
  /\b(?:Regulation|Directive)\s+\((?:EC|EU|EEC)\)\s+(?:No\.?\s*)?\d{1,4}\/\d{2,4}\b/g,
  /\b(?:Regulation|Directive)\s+(?:No\.?\s*)?\d{4}\/\d{1,4}\/(?:EC|EU)\b/g,
  /\b\d{1,2}\s+U\.?S\.?C\.?\s+§*\s*\d+[a-z]?\b/g,
  /\b\d{1,2}\s+CFR\s+(?:Part\s+)?\d+(?:\.\d+)?\b/g,
  /\b(?:[A-Z][A-Za-z']+\s){1,6}Act(?:,)?\s+\d{4}\b/g,
  /\b(?:Civil Code|General Obligations Law|Real Property Law)\s+(?:section\s+|§\s*)?\d+[\w.-]*\b/g,
  /\bSOR\/\d{4}-\d+\b/g,
];
const PROVISION = /\b(?:Article|Art\.|section|s\.|§)\s?\d+[a-z]?(?:\(\d+\))?(?:\([a-z]\))?/gi;

export function extractInstruments(text: string): string[] {
  return INSTRUMENT_PATTERNS.flatMap((re) => [...text.matchAll(re)].map((m) => m[0].replace(/\s+/g, " ").trim()));
}

// ---------- extraction from the answer lane ----------

export interface Extraction {
  instrument?: string;
  provision?: string;
  quantity?: Quantity;
  /** The verbatim sentence from a retrieved page that states the quantity (the grounding). */
  sentence?: string;
  sourceUrl?: string;
  /** How many answer-lane sources agree on the chosen quantity. */
  support: number;
  alternatives: Array<{ quantity: Quantity; support: number }>;
}

export const sentencesOf = (t: string) => t.replace(/\s+/g, " ").split(/(?<=[.!?])\s+(?=[A-Z0-9"\u201C(§\[])/).map((s) => s.trim()).filter(Boolean);

/**
 * Pick the instrument and the decisive quantity most sources agree on, weighting earlier ranks.
 * `preferKind` narrows to the quantity type the question asks about ("how much" -> money, "how long" -> duration).
 */
export function extractFromAnswerLane(results: LaneResult[], hints: Partial<Record<QuantityKind, number>> = {}): Extraction {
  const qScore = new Map<string, { q: Quantity; score: number; sources: Set<string>; sentence: string; url: string }>();
  const iScore = new Map<string, number>();
  results.forEach((r, rank) => {
    const w = 1 / (rank + 1);
    const text = r.highlights.join(" ");
    for (const ins of new Set(extractInstruments(`${r.title ?? ""} ${text}`))) iScore.set(ins, (iScore.get(ins) ?? 0) + w);
    for (const s of sentencesOf(text)) {
      if (s.trim().endsWith("?")) continue; // questions restate the problem, not the rule
      for (const q of extractQuantities(s)) {
        const k = qKey(q);
        const cur = qScore.get(k) ?? { q, score: 0, sources: new Set<string>(), sentence: s.trim(), url: r.url };
        if (!cur.sources.has(r.url)) cur.score += w * (1 + (hints[q.kind] ?? 0));
        cur.sources.add(r.url);
        qScore.set(k, cur);
      }
    }
  });
  const ranked = [...qScore.values()].sort((a, b) => b.score - a.score || b.sources.size - a.sources.size);
  const best = ranked[0];
  const instrument = [...iScore].sort((a, b) => b[1] - a[1])[0]?.[0];
  const provision = best ? best.sentence.match(PROVISION)?.[0] : undefined;
  return {
    instrument,
    provision,
    quantity: best?.q,
    sentence: best?.sentence,
    sourceUrl: best?.url,
    support: best?.sources.size ?? 0,
    alternatives: ranked.slice(1, 4).map((x) => ({ quantity: x.q, support: x.sources.size })),
  };
}

/**
 * Soft hints about which kind of quantity decides the question. They weight candidates; they
 * never filter, so a wrong hint costs ranking, not recall.
 */
export function kindHints(question: string): Partial<Record<QuantityKind, number>> {
  const h: Partial<Record<QuantityKind, number>> = { ...wordHints(question) };
  for (const q of extractQuantities(question)) h[q.kind] = (h[q.kind] ?? 0) + 1.5; // threshold questions: "delayed 7 hours"
  return h;
}

/** Hints from the question's wording only (what it asks for), excluding quantities it states (thresholds). */
export function wordHints(question: string): Partial<Record<QuantityKind, number>> {
  const h: Partial<Record<QuantityKind, number>> = {};
  const add = (k: QuantityKind, w: number) => (h[k] = (h[k] ?? 0) + w);
  if (/\bhow (long|fast|soon|often)\b|\bhow much (notice|time)\b|\bnotice\b|\bdeadline\b|\bcancel\b|\breturn\b|\breject\b|\bdispute\b|\bwithin\b|\bwhen\b/i.test(question)) add("duration", 2);
  if (/\bcompensation\b/i.test(question)) { add("money", 2); add("percent", 1.5); }
  if (/\bminimum wage\b|\bhow much (money|do i get|will i get|is)\b|\bfee\b|\bfine\b/i.test(question)) add("money", 2);
  if (/\braise\b|\bincrease\b|\bpercent\b|\bcap\b/i.test(question)) add("percent", 2);
  return h;
}

/** Citation-completion query grounded in the retrieved sentence, never in model memory. */
export function groundedCitationQuery(ex: Extraction): string | null {
  if (!ex.sentence) return null;
  const lead = ex.instrument && !ex.sentence.includes(ex.instrument) ? `Under ${ex.provision ? `${ex.provision} of ` : ""}${ex.instrument}, ` : "";
  const sentence = lead ? ex.sentence.charAt(0).toLowerCase() + ex.sentence.slice(1) : ex.sentence;
  const kind = ex.instrument?.match(/Regulation|Directive|Act|Code|Law|CFR|U\.?S\.?C/i)?.[0]?.toLowerCase() ?? "law";
  const kindWord = kind === "cfr" || /u\.?s\.?c/.test(kind) ? "statute" : kind;
  return `${lead}${sentence} The official text of the ${kindWord}:`;
}

// ---------- triangulation ----------

export type Triangulation =
  /** focus: the clause itself when the quote also carries the words that introduce it (the amount must be in the focus). */
  | { status: "agree"; quote: string; url: string; focus?: string }
  | { status: "disagree"; found: Quantity[]; url: string }
  /** The number appears in the legal text, but only in a clause about something else. */
  | { status: "misplaced"; quote: string; url: string; competing?: { quote: string; quantity: Quantity } }
  | { status: "not_found"; url?: string };

// ---------- role overlap ----------

const ROLE_STOP = new Set(["shall", "must", "that", "this", "with", "from", "have", "their", "which", "where", "when", "they", "them", "such", "other", "under", "into", "than", "more", "less", "were", "been", "will", "would", "also", "only", "each", "within", "after", "before", "following", "paragraph", "article", "section", "regulation", "directive", "your", "there", "what", "case"]);
const UNIT_STEMS = new Set(["minut", "hour", "day", "week", "month", "year", "busines", "calendar", "percent", "per", "cent", "euro", "kilometr", "kilomet", "pound", "dollar"]);
/** Light suffix stripping so "arrive"/"arrival", "delayed"/"delay", "passengers"/"passenger" meet. */
const stem = (w: string) => w.replace(/(ations?|ations|ions?|ival|als?|ing|ed|ies|es|s|e)$/, "");
export const contentStems = (s: string) =>
  new Set((s.toLowerCase().match(/[a-z\u00c0-\u024f]{4,}/g) ?? []).filter((w) => !ROLE_STOP.has(w)).map(stem).filter((w) => w.length >= 3 && !UNIT_STEMS.has(w)));

/** Stems that appear in at least half of the legal sentences carry no information about role. */
function genericStems(sentences: string[]): Set<string> {
  // Document frequency is only meaningful on statute-length text; short snippets keep every word.
  const stems = sentences.map(contentStems).filter((s) => s.size > 0);
  if (stems.length < 6) return new Set();
  const df = new Map<string, number>();
  for (const s of stems) for (const w of s) df.set(w, (df.get(w) ?? 0) + 1);
  return new Set([...df].filter(([, n]) => n / stems.length >= 0.5).map(([w]) => w));
}

/** Shared discriminative content stems between the explainer's clause and a legal sentence. */
export function roleOverlap(premiseSentence: string, legalSentence: string, generic: Set<string> = new Set()): number {
  const b = contentStems(legalSentence);
  return [...contentStems(premiseSentence)].filter((w) => b.has(w) && !generic.has(w)).length;
}

/**
 * Re-fetch the authority-lane legal texts (in rank order) and look for the decisive quantity.
 * agree     the same quantity appears; the verbatim sentence becomes the rule's quote
 * disagree  only other quantities of the same kind and unit appear near the instrument's terms
 * not_found no legal text could be read or none states a quantity of that kind
 */
export async function triangulate(ex: Extraction, legalUrls: string[], fetch: FetchFn, maxPages = 2): Promise<Triangulation> {
  if (!ex.quantity) return { status: "not_found" };
  let lastDisagree: Triangulation | null = null;
  for (const url of legalUrls.slice(0, maxPages)) {
    let text = "";
    try {
      text = await fetch(url);
    } catch {
      continue;
    }
    const sentences = sentencesOf(text);
    const hit = sentences.find((s) => extractQuantities(s).some((q) => sameQuantity(q, ex.quantity!)));
    if (hit) return { status: "agree", quote: hit.trim(), url };
    const sameKind = sentences.flatMap((s) => extractQuantities(s)).filter((q) => q.kind === ex.quantity!.kind && q.unit === ex.quantity!.unit);
    if (sameKind.length) lastDisagree = { status: "disagree", found: dedupe(sameKind).slice(0, 5), url };
  }
  return lastDisagree ?? { status: "not_found", url: legalUrls[0] };
}

const dedupe = (qs: Quantity[]) => [...new Map(qs.map((q) => [qKey(q), q])).values()];

// ---------- multiple premises ----------

export interface Premise {
  /** threshold: a condition the question states ("delayed 3 hours"); outcome: what the question asks for. */
  role: "threshold" | "outcome";
  quantity: Quantity;
  sentence: string;
  sourceUrl: string;
  support: number;
}

interface Candidate {
  q: Quantity;
  score: number;
  sources: Set<string>;
  sentence: string;
  url: string;
  /** Character position of the quantity in its sentence (for tier disambiguation). */
  pos: number;
  /** Occurrences inside a bound phrase ("less than one year", "3 hours or more") vs all occurrences. */
  cond: number;
  occ: number;
}

// Comparisons mark conditions; "within", "up to" and "at least" usually state the granted period or minimum (outcomes).
const BOUND_BEFORE = /(less than|under|fewer than|below|more than|over|longer than|above|exceeding)\s*$/i;
const BOUND_AFTER = /^\s*(or more|or longer|or over|or less|or fewer|or shorter|and over|or above)/i;

function candidates(results: LaneResult[]): Candidate[] {
  const byKey = new Map<string, Candidate>();
  results.forEach((r, rank) => {
    const w = 1 / (rank + 1);
    for (const s of sentencesOf(r.highlights.join(" "))) {
      if (s.endsWith("?")) continue;
      for (const q of extractQuantities(s)) {
        const k = qKey(q);
        const c = byKey.get(k) ?? { q, score: 0, sources: new Set<string>(), sentence: s, url: r.url, pos: Math.max(0, s.indexOf(q.text)), cond: 0, occ: 0 };
        const at = s.indexOf(q.text);
        c.occ++;
        if (at >= 0 && (BOUND_BEFORE.test(s.slice(Math.max(0, at - 24), at)) || BOUND_AFTER.test(s.slice(at + q.text.length, at + q.text.length + 16)))) c.cond++;
        if (!c.sources.has(r.url)) c.score += w;
        c.sources.add(r.url);
        // Ground the candidate in a sentence that states a rule, not one that restates the situation.
        if (ruleScore(s) > ruleScore(c.sentence)) {
          c.sentence = s;
          c.url = r.url;
          c.pos = Math.max(0, s.indexOf(q.text));
        }
        byKey.set(k, c);
      }
    }
  });
  return [...byKey.values()].sort((a, b) => b.score - a.score || b.sources.size - a.sources.size);
}

const RULE_CUE = /\b(entitled|must|shall|may|required|right to|or more|at least|no later than|within|up to|maximum|minimum|not exceed|receives?|are owed|is owed|qualif\w*)\b/i;
const FIRST_PERSON = /\b(I|I'm|my|me|we|our)\b/;
/** A sentence that states a general rule beats one that restates someone's situation. */
const ruleScore = (s: string) => (RULE_CUE.test(s) ? 1 : 0) - (FIRST_PERSON.test(s) ? 1 : 0);

/** Does the text right around the quantity mark it as an upper bound ("within 14 days", "up to")? */
const upperBound = (c: { sentence: string; pos: number }) =>
  /\b(within|no later than|up to|not exceed\w*|at most|less than|maximum)\W+(\w+\W+){0,3}$/i.test(c.sentence.slice(Math.max(0, c.pos - 40), c.pos));

const STOPWORDS = new Set(["what", "when", "with", "have", "does", "that", "this", "from", "into", "your", "about", "much", "many", "long", "after", "before", "they", "them", "their", "there", "would", "could", "should", "will", "must"]);

const KIND_PRIORITY: QuantityKind[] = ["duration", "money", "percent", "distance"];

/**
 * Extract every decisive quantity a claim needs, each grounded in a retrieved sentence:
 *  - one threshold per quantity the question states, matched on kind AND unit
 *    ("delayed 7 hours" looks for an hours threshold, not "7 business days");
 *  - the outcome the wording asks for (top hint; ties keep both, duration first).
 */
export function extractPremises(results: LaneResult[], question: string): Premise[] {
  const cands = rankedCandidates(results, question);
  const premises: Premise[] = [];
  const used = new Set<string>();
  const take = (c: Candidate, role: Premise["role"]) => {
    used.add(qKey(c.q));
    premises.push({ role, quantity: c.q, sentence: c.sentence, sourceUrl: c.url, support: c.sources.size });
  };
  for (const q0 of dedupe(extractQuantities(question))) {
    const same = cands.filter((c) => c.q.kind === q0.kind && c.q.unit === q0.unit && !used.has(qKey(c.q)));
    // The binding threshold is the one the stated situation actually meets: for lower bounds
    // ("3 hours or more") the largest value <= the situation, for upper bounds ("within 14 days")
    // the smallest value >= it. Fall back to consensus when none qualifies.
    const eligible = same.filter((c) => (upperBound(c) ? c.q.value >= q0.value : c.q.value <= q0.value));
    const tightest = eligible.sort((a, b) => Math.abs(q0.value - a.q.value) - Math.abs(q0.value - b.q.value) || b.score - a.score)[0];
    const c = tightest ?? same[0];
    if (c) take(c, "threshold");
  }
  const thresholdUnits = new Set(premises.map((p) => `${p.quantity.kind}:${p.quantity.unit}`));
  const hints = Object.entries(wordHints(question)) as Array<[QuantityKind, number]>;
  hints.sort((a, b) => b[1] - a[1] || KIND_PRIORITY.indexOf(a[0]) - KIND_PRIORITY.indexOf(b[0]));
  // Every kind the wording points to (max two) becomes an outcome alternative; the legal text decides
  // which one holds (compensation can be a fixed amount or a share of the price).
  // Alternatives only within a compatible group: an amount can be money or a share of the price,
  // but a percentage cannot answer "how much notice".
  const topGroup = hints[0] ? GROUP[hints[0][0]] : undefined;
  let outcomes = 0;
  for (const [kind, w] of hints) {
    if (w < 1.5 || outcomes >= 2) break;
    if (GROUP[kind] !== topGroup) continue;
    outcomes++;
    const pool = cands.filter((c) => c.q.kind === kind && !used.has(qKey(c.q)) && !thresholdUnits.has(`${c.q.kind}:${c.q.unit}`));
    // An outcome is what the rule grants, not a condition it sets: prefer values mostly seen outside bound phrases.
    const c = pool.find((c) => c.cond / c.occ < 0.5) ?? pool[0];
    if (c) take(c, "outcome");
  }
  if (!premises.some((p) => p.role === "outcome")) {
    const c = cands.find((c) => !used.has(qKey(c.q)) && !thresholdUnits.has(`${c.q.kind}:${c.q.unit}`));
    if (c) take(c, "outcome");
  }
  return premises;
}

const GROUP: Record<QuantityKind, string> = { money: "amount", percent: "amount", duration: "time", distance: "length" };

/** A quantity the answer lane mentions, with the sentence that grounds it (for judges to choose among). */
export interface PremiseCandidate {
  quantity: Quantity;
  sentence: string;
  url: string;
  support: number;
  score: number;
  /** Share of occurrences inside a bound phrase ("3 hours or more"). */
  boundShare: number;
}

/**
 * Outcome candidates for a judge to choose among: code finds them, a judge may only pick one.
 * Excludes units the question itself states (those are thresholds) and keeps the kinds the
 * question's wording points to when it points anywhere.
 */
export function outcomeCandidates(results: LaneResult[], question: string, max = 8): PremiseCandidate[] {
  const stated = new Set(extractQuantities(question).map((q) => `${q.kind}:${q.unit}`));
  const hints = Object.entries(wordHints(question)) as Array<[QuantityKind, number]>;
  hints.sort((a, b) => b[1] - a[1] || KIND_PRIORITY.indexOf(a[0]) - KIND_PRIORITY.indexOf(b[0]));
  const group = hints[0] && hints[0][1] >= 1.5 ? GROUP[hints[0][0]] : undefined;
  return rankedCandidates(results, question)
    .filter((c) => !stated.has(`${c.q.kind}:${c.q.unit}`) && (!group || GROUP[c.q.kind] === group))
    .slice(0, max)
    .map((c) => ({ quantity: c.q, sentence: c.sentence, url: c.url, support: c.sources.size, score: c.score, boundShare: c.cond / c.occ }));
}

function rankedCandidates(results: LaneResult[], question: string): Candidate[] {
  // Tiered rules ("3 hours domestic, 6 hours international"): prefer the tier whose sentence shares
  // the question's own content words.
  const qWords = new Set((question.toLowerCase().match(/[a-z\u00c0-\u024f]{4,}/g) ?? []).filter((w) => !STOPWORDS.has(w)));
  // Question words count more the closer they sit to the quantity ("International ... over 6 hours").
  const proximity = (s: string, pos: number) => {
    if (!qWords.size) return 0;
    const lower = s.toLowerCase();
    let sum = 0;
    for (const w of qWords) {
      let best = Infinity;
      for (let i = lower.indexOf(w); i >= 0; i = lower.indexOf(w, i + 1)) best = Math.min(best, Math.abs(i - pos));
      if (best < Infinity) sum += 1 / (1 + best / 15);
    }
    return sum / qWords.size;
  };
  return candidates(results)
    .map((c) => ({ ...c, score: c.score * (1 + 2 * proximity(c.sentence, c.pos)) }))
    .sort((a, b) => b.score - a.score || b.sources.size - a.sources.size);
}

/** Triangulate one quantity against already-fetched legal texts. */
export function triangulateQuantity(q: Quantity, pages: Array<{ url: string; text: string }>, roleSentence?: string): Triangulation {
  const all = pages.flatMap(({ url, text }) => sentencesOf(text).map((s) => ({ url, s })));
  const generic = genericStems(all.map((x) => x.s));
  const hits = all.filter((x) => extractQuantities(x.s).some((y) => sameQuantity(y, q)));
  if (!hits.length) {
    const same = all.flatMap((x) => extractQuantities(x.s).map((y) => ({ ...x, y }))).filter((x) => x.y.kind === q.kind && x.y.unit === q.unit);
    return same.length ? { status: "disagree", found: dedupe(same.map((x) => x.y)).slice(0, 5), url: same[0]!.url } : { status: "not_found", url: pages[0]?.url };
  }
  if (!roleSentence) return { status: "agree", quote: hits[0]!.s, url: hits[0]!.url };
  const score = (s: string) => roleOverlap(roleSentence, s, generic);
  const best = hits.map((x) => ({ ...x, o: score(x.s) })).sort((a, b) => b.o - a.o)[0]!;
  // A clause that fits the premise's role better but states a different value of the same unit
  // means the law gives another number for this role: the match is misplaced.
  const competing = all
    .map((x) => ({ ...x, other: extractQuantities(x.s).find((y) => y.kind === q.kind && y.unit === q.unit && !sameQuantity(y, q)), o: score(x.s) }))
    .filter((x) => x.other && !extractQuantities(x.s).some((y) => sameQuantity(y, q)))
    .sort((a, b) => b.o - a.o)[0];
  if (competing && competing.o > best.o) {
    return { status: "misplaced", quote: best.s, url: best.url, competing: { quote: competing.s, quantity: competing.other! } };
  }
  if (best.o >= 1) return { status: "agree", quote: best.s, url: best.url };
  return { status: "misplaced", quote: best.s, url: best.url };
}

// ---------- three-way check: model prior, explainer, legal text ----------

export type ThreeWayStatus =
  | "confirmed" // explainer = legal text (model prior absent or agrees)
  | "confirmed_model_disagrees" // explainer = legal text, model memory says otherwise: sources win, memory flagged
  | "conflict" // legal text states a different value than the explainer
  | "conflict_model_sides_with_law" // as conflict, and the model agrees with the legal text: explainer likely outdated
  | "unverified" // no legal text states a value of this kind
  | "unverified_model_agrees"; // explainer and model agree but no legal text confirms

export function threeWay(p: Premise, tri: Triangulation, prior: Quantity[]): { status: ThreeWayStatus; note: string } {
  const sameUnit = prior.filter((x) => x.kind === p.quantity.kind && x.unit === p.quantity.unit);
  const priorSame = sameUnit.some((x) => sameQuantity(x, p.quantity));
  if (tri.status === "agree") {
    return sameUnit.length && !priorSame
      ? { status: "confirmed_model_disagrees", note: `legal text and explainer state ${p.quantity.text}; model memory said ${sameUnit.map((x) => x.text).join(", ")}` }
      : { status: "confirmed", note: `legal text confirms ${p.quantity.text}` };
  }
  if (tri.status === "disagree") {
    const modelWithLaw = sameUnit.some((x) => tri.found.some((f) => sameQuantity(f, x)));
    return modelWithLaw
      ? { status: "conflict_model_sides_with_law", note: `explainer states ${p.quantity.text}; legal text and model state ${tri.found.map((f) => f.text).join(", ")}: explainer likely outdated` }
      : { status: "conflict", note: `explainer states ${p.quantity.text}; legal text states ${tri.found.map((f) => f.text).join(", ")}` };
  }
  if (tri.status === "misplaced") {
    return tri.competing
      ? { status: "conflict", note: `the legal clause matching this role states ${tri.competing.quantity.text}, not ${p.quantity.text}: "${tri.competing.quote.slice(0, 140)}"` }
      : { status: "unverified", note: `${p.quantity.text} appears in the legal text only in an unrelated clause: "${tri.quote.slice(0, 120)}"` };
  }
  return priorSame
    ? { status: "unverified_model_agrees", note: `explainer and model state ${p.quantity.text}; no legal text confirms it` }
    : { status: "unverified", note: `no legal text states ${p.quantity.text}` };
}

// ---------- tiered rules and clarifying questions ----------

export interface Tier {
  value: Quantity;
  /** The condition text attached to this tier, verbatim from the source (cleaned of table markup). */
  qualifier: string;
}

export interface TierAnalysis {
  tiers: Tier[];
  sourceUrl: string;
  resolved?: { value: Quantity; by: "stated_quantity" | "condition" };
  clarify?: { question: string; options: string[] };
}

const QUALIFIER_AFTER = /^\s*[,;:]?\s*(for|where|if|when|in the case of|on|of|after|per)\b/i;
const clean = (s: string) => s.replace(/\|/g, " ").replace(/-{3,}/g, " ").replace(/\s+/g, " ").replace(/^[\s,;:()a-z.]{0,4}\)\s*/i, "").trim().replace(/^[,;:.\s]+|[,;:.\s]+$/g, "").slice(0, 160);

function tierQualifiers(s: string, vals: Array<{ q: Quantity; start: number }>): Tier[] {
  return vals.map((v, i) => {
    const end = v.start + v.q.text.length;
    const after = s.slice(end, vals[i + 1]?.start ?? s.length);
    const before = s.slice(i ? vals[i - 1]!.start + vals[i - 1]!.q.text.length : 0, v.start);
    // A condition that precedes its value (table rows, "less than one year: 30 days") sits right before
    // it, so keep the tail of the preceding text; one that follows ("EUR 250 for flights of ...") is read forward.
    if (QUALIFIER_AFTER.test(after)) return { value: v.q, qualifier: clean(after) };
    // In a markdown table the condition is the cell right before the value: cut at the last row boundary.
    const row = Math.max(before.lastIndexOf("| |"), before.lastIndexOf("|\n|"));
    const cell = row >= 0 ? before.slice(row + 3) : before;
    const tail = cell.replace(/\|/g, " ").replace(/-{3,}/g, " ").replace(/\s+/g, " ").trim();
    const cut = tail.length > 160 ? tail.slice(tail.indexOf(" ", tail.length - 160) + 1) : tail;
    return { value: v.q, qualifier: clean(cut) };
  });
}

interface Condition { op: "<" | "<=" | ">" | ">="; q: Quantity }

/** Parse bound phrases in a qualifier: "less than one year", "more than two years", "1500 km or less", "at least 60 minutes". */
export function conditionsOf(qualifier: string): Condition[] {
  const out: Condition[] = [];
  // Ranges: "60 to 119 minutes", "1,500km to 3,500km", "between 1500 and 3500 kilometres".
  for (const m of qualifier.matchAll(/(\d[\d,.]*)\s*(?:km|kilomet\w*)?\s*(?:to|–|-|and)\s*(\d[\d,.]*)\s*(minutes?|hours?|days?|weeks?|months?|years?|km|kilomet\w*)/gi)) {
    const lo = extractQuantities(`${m[1]} ${m[3]}`)[0];
    const hi = extractQuantities(`${m[2]} ${m[3]}`)[0];
    if (lo && hi) out.push({ op: ">=", q: lo }, { op: "<=", q: hi });
  }
  for (const q of extractQuantities(qualifier)) {
    const i = qualifier.indexOf(q.text);
    const pre = qualifier.slice(Math.max(0, i - 24), i).toLowerCase();
    const post = qualifier.slice(i + q.text.length, i + q.text.length + 16).toLowerCase();
    if (/(less than|under|fewer than|below|shorter than)\s*$/.test(pre)) out.push({ op: "<", q });
    else if (/(more than|over|longer than|above|exceeding|in excess of)\s*$/.test(pre)) out.push({ op: ">", q });
    else if (/(at least|minimum of|not less than)\s*$/.test(pre) || /^\s*(or more|or longer|or over|and over|or above)/.test(post)) out.push({ op: ">=", q });
    else if (/(up to|not more than|at most|maximum of)\s*$/.test(pre) || /^\s*(or less|or fewer|or shorter|or under)/.test(post)) out.push({ op: "<=", q });
  }
  return out;
}

const holds = (c: Condition, x: Quantity) =>
  c.op === "<" ? x.value < c.q.value : c.op === "<=" ? x.value <= c.q.value : c.op === ">" ? x.value > c.q.value : x.value >= c.q.value;

function clarifyingQuestion(tiers: Tier[]): string {
  const all = tiers.map((t) => t.qualifier).join(" ").toLowerCase();
  if (/(lived|living|occup|resid|tenan|lease term)/.test(all) && /(year|month)/.test(all)) return "How long have you lived in the unit, and how long is your lease term?";
  if (/(kilomet|\d\s?km\b|distance)/.test(all)) return "How long is the flight, in kilometres?";
  if (/(domestic|international)/.test(all)) return "Is the trip domestic or international?";
  if (/(minute|hour)/.test(all)) return "How long was the delay, exactly?";
  return "Which of these describes your situation?";
}

/**
 * Detect a tiered rule around a premise (several values of the same unit in one source sentence, each
 * with its own condition) and resolve it from what the question states, or ask.
 * Resolution order: a quantity stated in the question equals one in a tier's condition; the stated
 * quantity satisfies a tier's bound conditions ("3 years" meets "more than two years"); the question's
 * wording clearly favours one tier. Otherwise a clarifying question with the tiers as options.
 */
export function analyseTiers(results: LaneResult[], premise: Premise, question: string, known: Quantity[] = []): TierAnalysis | null {
  for (const r of results) {
    for (const s of sentencesOf(r.highlights.join(" "))) {
      const qs = extractQuantities(s).filter((x) => x.kind === premise.quantity.kind && x.unit === premise.quantity.unit);
      if (!qs.some((x) => sameQuantity(x, premise.quantity))) continue;
      const seen = new Set<string>();
      const vals: Array<{ q: Quantity; start: number }> = [];
      let from = 0;
      for (const x of qs) {
        const start = s.indexOf(x.text, from);
        from = start >= 0 ? start + x.text.length : from;
        if (start < 0 || seen.has(qKey(x))) continue;
        seen.add(qKey(x));
        vals.push({ q: x, start });
      }
      if (vals.length < 2) continue;
      const tiers = tierQualifiers(s, vals.sort((a, b) => a.start - b.start));
      // Only a structured tiering counts: at least two tiers carry a condition we can evaluate.
      // Several values that merely share a sentence ("one month, extendable by two months") are not tiers.
      if (tiers.filter((t) => conditionsOf(t.qualifier).length > 0).length < 2) continue;
      const stated = [...extractQuantities(question), ...known];
      // 1. a stated quantity appears in exactly one tier's condition
      const eq = tiers.filter((t) => extractQuantities(t.qualifier).some((x) => stated.some((y) => sameQuantity(x, y))));
      if (eq.length === 1) return { tiers, sourceUrl: r.url, resolved: { value: eq[0]!.value, by: "stated_quantity" } };
      // 2. a stated quantity satisfies exactly one tier's bound conditions
      const sat = tiers.filter((t) => {
        const conds = conditionsOf(t.qualifier);
        return stated.some((x) => {
          const rel = conds.filter((c) => c.q.kind === x.kind && c.q.unit === x.unit);
          return rel.length > 0 && rel.every((c) => holds(c, x));
        });
      });
      if (sat.length === 1) return { tiers, sourceUrl: r.url, resolved: { value: sat[0]!.value, by: "condition" } };
      return { tiers, sourceUrl: r.url, clarify: { question: clarifyingQuestion(tiers), options: tiers.map((t) => `${t.qualifier} → ${t.value.text}`) } };
    }
  }
  return null;
}
