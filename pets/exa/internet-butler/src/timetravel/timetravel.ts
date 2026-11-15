/**
 * Then · Now · Next: the law as it stood on the day it mattered, the law today, what changed it,
 * and what is about to change — each pinned to an immutable official version.
 *
 *   find      Exa (official includeDomains) → known-rights registry → eCFR search
 *   then/now  official point-in-time text (eCFR versioner, legislation.gov.uk, EUR-Lex consolidated)
 *   clause    a typed judge picks the amount-bearing clause that fits the situation (selection, not
 *             generation); the same clause today is found by its template (numbers masked)
 *   why/next  Federal Register rules (US), legislation.gov.uk effects feed (UK), consolidated
 *             versions (EU), with effective dates; dates after today are "upcoming"
 *   warrant   asTwoLane() turns the result into a compile result the signed Warrant accepts; the
 *             receiver re-fetches the pinned point-in-time URL and checks the quote by code
 *
 * Measured basis (bench/timelaw): date-blind checking accepts 9 % of historically true claims;
 * checking against the official text of the claim's date, 620/620.
 */
import { flightNote } from "./airports.ts";
import { lawOn, type OfficialRef } from "../warrant/pointInTime.ts";
import { conditionsOf, contentStems, extractQuantities, type Quantity } from "../warrant/lanes.ts";
import type { TwoLaneResult } from "../warrant/compile.ts";
import { receiptsFor, type DecisionProvider, type JudgmentReceipt, type Question } from "../decide/decide.ts";

export type RawFetch = (url: string, init?: RequestInit) => Promise<Response>;
export type ExaSearch = (query: string, includeDomains: string[]) => Promise<Array<{ url: string; title?: string }>>;
/**
 * The on-device semantic catalog (bench/catalog: EmbeddingGemma over about 5,900 amount-bearing CFR provisions,
 * served on 127.0.0.1). It returns the nearest provisions that exist in the event's year, best first. Measured on
 * 1,200 situations: the right section is in its top 5 for 66 % (Exa on official domains: 26 %), first for 44 %.
 */
export type CatalogSearch = (question: string, date?: string) => Promise<Array<{ ref: OfficialRef; title: string; about: string; score: number; also?: OfficialRef[]; /** "registry": one of the app's built-in rights, matched by its description; otherwise a CFR provision. */ kind?: "registry" | "cfr" }>>;
/** A built-in right matched by meaning wins when it scores at least this and is not clearly behind the best CFR hit (calibrated on the simulation questions and 300 benchmark situations: 16 of 17 right, 0 of 300 misrouted). */
// A CFR hit below CATALOG_MATCH is not used: real in-catalog questions score 0.41 or more nine times in ten, and a
// Finnish paraphrase that matched nothing well (0.37) otherwise produced an answer from an unrelated provision.
const REGISTRY_MATCH = 0.4, REGISTRY_MARGIN = 0.03, CATALOG_MATCH = 0.4;

const UA = { "user-agent": "internet-butler-warrant/0.1 (then-now-next)" };

// ---------- official URLs → references ----------

export function refFromUrl(url: string): OfficialRef | null {
  let m = url.match(/ecfr\.gov\/.*title-(\d+)(?:\/.*)?\/part-(\d+)(?:\/.*)?\/section-([\d.]+[a-z0-9-]*)/i);
  if (m) return { source: "ecfr", title: Number(m[1]), part: m[2]!, section: m[3]! };
  m = url.match(/ecfr\.gov\/api\/versioner\/v1\/full\/[^/]+\/title-(\d+)\.xml\?part=(\d+)&section=([\w.-]+)/i);
  if (m) return { source: "ecfr", title: Number(m[1]), part: m[2]!, section: decodeURIComponent(m[3]!) };
  m = url.match(/legislation\.gov\.uk\/((?:ukpga|uksi|asp|ssi|wsi|nisr|nia|anaw|asc|ukla)\/\d{4}\/\d+(?:\/(?:section|regulation|article|schedule|paragraph|part)\/[\w-]+)*)/i);
  if (m) return { source: "ukleg", path: m[1]!.replace(/\/(contents|enacted|made|data\.xml)$/i, "") };
  m = url.match(/CELEX(?:%3A|:)(3\d{4}[A-Z]\d{4})/i) ?? url.match(/resource\/celex\/(3\d{4}[A-Z]\d{4})/i);
  if (m) return { source: "eurlex", celex: m[1]!.toUpperCase() };
  return null;
}

export const OFFICIAL_DOMAINS = ["ecfr.gov", "www.ecfr.gov", "legislation.gov.uk", "www.legislation.gov.uk", "eur-lex.europa.eu"];

// ---------- a small registry of well-known, amount-bearing rights (robust demo; Exa covers the rest) ----------

/** `also`: provisions of the same family whose clauses compete (e.g. adult and younger-worker wage rates). */
const RAIL_WORDS = /\b(trains?|rail(way)?|zug|z[üu]ge[n]?|bahn|juna\w*|tågs?|metro|tram)\b/i;
const AIR_WORDS = /\b(flights?|flug|fl[üu]ge|lento\w*|lennon|airlines?|airport|plane|aircraft|boarding|flew|flying)\b/i;
const AIR_ONLY = /\b(flights?|flug|lento\w*|airlines?|airport|plane|boarding)\b/i;

export interface Known { ref: OfficialRef; title: string; about: string; jurisdiction: string; keywords: string[]; also?: OfficialRef[]; /** The right is not about this: a question matching `avoid` (and not `unless`) never takes it. */ avoid?: RegExp; unless?: RegExp }
export const REGISTRY: Known[] = [
  { ref: { source: "ecfr", title: 14, part: 250, section: "250.5" }, title: "14 CFR 250.5 — denied boarding compensation (US)", about: "Money an airline must pay a passenger involuntarily bumped from an oversold flight in or from the United States, depending on how late the substitute flight arrives.", jurisdiction: "US", keywords: ["bumped", "oversold", "denied boarding", "overbook", "us", "domestic", "united states"] },
  { ref: { source: "ecfr", title: 12, part: 1026, section: "1026.52" }, title: "12 CFR 1026.52 — credit card late and penalty fees (US)", about: "The maximum late payment or penalty fee a US credit card issuer may charge (safe-harbor amounts).", jurisdiction: "US", keywords: ["credit card", "late fee", "penalty fee", "card issuer"] },
  { ref: { source: "ecfr", title: 29, part: 579, section: "579.1" }, title: "29 CFR 579.1 — child labor and FLSA civil penalties (US)", about: "Civil money penalties for child labor violations and repeated or willful minimum wage or overtime violations under the US Fair Labor Standards Act.", jurisdiction: "US", keywords: ["child labor", "child labour", "flsa penalty", "civil money penalty"] },
  { ref: { source: "ukleg", path: "uksi/2015/621/regulation/4" }, also: [{ source: "ukleg", path: "uksi/2015/621/regulation/4A" }], title: "National Minimum Wage Regulations 2015, regs. 4 and 4A — minimum hourly wage for every age and apprentices (UK)", about: "The minimum hourly pay a UK worker is entitled to: the national living wage and the lower rates for younger workers and apprentices.", jurisdiction: "UK", keywords: ["minimum wage", "living wage", "hourly rate", "per hour", "uk", "£", "apprentice"] },
  { ref: { source: "ukleg", path: "ukpga/1992/4/section/157" }, title: "Social Security Contributions and Benefits Act 1992, s. 157 — statutory sick pay (UK)", about: "The weekly rate of statutory sick pay a UK employer pays a worker off sick.", jurisdiction: "UK", keywords: ["sick pay", "ssp", "off sick", "statutory sick"] },
  { ref: { source: "ukleg", path: "uksi/1986/1960/regulation/6" }, title: "Statutory Maternity Pay (General) Regulations 1986, reg. 6 — maternity pay rate (UK)", about: "The weekly rate of statutory maternity pay in the UK.", jurisdiction: "UK", keywords: ["maternity pay", "smp", "maternity"] },
  { ref: { source: "ukleg", path: "uksi/2002/2818/regulation/2" }, title: "Statutory Paternity Pay and Statutory Adoption Pay (Weekly Rates) Regulations 2002, reg. 2 (UK)", about: "The weekly rate of statutory paternity pay (and adoption pay) in the UK.", jurisdiction: "UK", keywords: ["paternity pay", "adoption pay", "spp", "shared parental"] },
  { ref: { source: "ukleg", path: "ukpga/1996/18/section/227" }, title: "Employment Rights Act 1996, s. 227 — maximum week's pay (UK)", about: "The cap on a week's pay used to calculate statutory redundancy pay and the basic award for unfair dismissal in the UK.", jurisdiction: "UK", keywords: ["redundancy pay", "week's pay", "unfair dismissal", "basic award", "redundant"] },
  { ref: { source: "eurlex", celex: "32004R0261", article: "7" }, title: "Regulation (EC) No 261/2004, Art. 7 — flight compensation (EU)", about: "Fixed compensation an airline owes passengers in the EU for a cancelled, long-delayed or overbooked flight, by flight distance.", jurisdiction: "EU", keywords: ["eu261", "flight delay", "cancelled flight", "delayed flight", "eu", "europe", "€", "261/2004", "lento", "lennon", "peruttiin", "flug", "annulliert"], avoid: RAIL_WORDS, unless: AIR_WORDS },
  { ref: { source: "eurlex", celex: "32021R0782", article: "19" }, title: "Regulation (EU) 2021/782, Art. 19 — rail passenger compensation for delay (EU)", about: "The share of the ticket price a railway company in the EU must pay a passenger whose train arrives 60 minutes or more late (25 % from 60 minutes, 50 % from 120 minutes).", jurisdiction: "EU", keywords: ["train delay", "delayed train", "late train", "railway", "rail passenger", "2021/782", "juna myöhässä", "junan myöhästyminen", "juna myöhästyi", "zug verspätung", "zugverspätung", "verspätung zug", "zug hatte", "bahn verspätung", "train"], avoid: AIR_ONLY, unless: RAIL_WORDS },
  { ref: { source: "eurlex", celex: "32016R0679", article: "12" }, title: "Regulation (EU) 2016/679 (GDPR), Art. 12 — time to answer data requests (EU)", about: "How long a company in the EU has to answer a person's request about their personal data (access, erasure and other GDPR rights).", jurisdiction: "EU", keywords: ["gdpr", "data access", "subject access", "personal data", "data request"] },
];


/**
 * The one jurisdiction the person's own words point to, if exactly one: "federal", a dollar sign or a US state
 * mean the US; a pound sign or "UK" mean the UK; a euro sign, "EU" or Finland and Germany mean the EU.
 * Mixed or no cues: undefined (an international trip names several).
 */
export function jurisdictionCue(question: string): "US" | "UK" | "EU" | undefined {
  const q = question;
  const found = new Set<string>();
  if (/\$|\bfederal\b|\bUSA?\b|\bU\.S\.|united states|\bamerican?\b|\b(california|texas|florida|new york|illinois|washington state)\b|\byhdysvalloissa\b/i.test(q.replace(/\bus\b/g, ""))) found.add("US");
  if (/£|\bUK\b|\bU\.K\.|britain|british|england|scotland|wales|\bhmrc\b|isossa-britanniassa/i.test(q)) found.add("UK");
  if (/€|\bEU\b|\beuropean union\b|\bsuomessa\b|\bfinland\b|\bdeutschland\b|\bgermany\b|\bsaksassa\b/i.test(q)) found.add("EU");
  return found.size === 1 ? ([...found][0] as "US" | "UK" | "EU") : undefined;
}

/** A built-in right the question rules out: wrong jurisdiction named in it, or the wrong kind of journey. */
export function ruledOutBy(question: string, k: Known): boolean {
  const cue = jurisdictionCue(question);
  if (cue && cue !== k.jurisdiction) return true;
  return !!k.avoid && k.avoid.test(question) && !(k.unless && k.unless.test(question));
}

const ruledOutHit = (question: string, ref: OfficialRef) => { const k = REGISTRY.find((x) => JSON.stringify(x.ref) === JSON.stringify(ref)); return !!k && ruledOutBy(question, k); };

function registryScores(question: string): Array<{ k: Known; score: number }> {
  const q = question.toLowerCase();
  // A short word must stand alone: "us" is inside the Finnish "ilmoitusta" and "eu" inside "neuvo".
  const has = (w: string) => (w.length <= 3 && /^[a-z0-9]+$/.test(w) ? new RegExp(`(^|[^\\p{L}\\p{N}])${w}($|[^\\p{L}\\p{N}])`, "u").test(q) : q.includes(w));
  return REGISTRY.map((k) => ({ k, score: ruledOutBy(question, k) ? 0 : k.keywords.reduce((s, w) => s + (has(w) ? (w.length > 3 ? 2 : 1) : 0), 0) })).sort((a, b) => b.score - a.score);
}

const STOP = new Set(["i", "my", "me", "was", "is", "the", "a", "an", "and", "or", "of", "on", "in", "to", "for", "how", "much", "what", "am", "owed", "do", "get", "did", "from", "at", "it", "be", "with", "that", "this", "when", "can", "could", "would", "under", "per", "after", "then", "they", "their", "there", "only"]);

/** eCFR search needs every term to match, so ask several short term sets and pool the sections found. */
async function ecfrCandidates(question: string, date: string | undefined, f: RawFetch): Promise<Array<{ ref: OfficialRef; title: string }>> {
  const words = question.replace(/\d{4}-\d{2}-\d{2}/g, " ").replace(/[^A-Za-z0-9()\s]/g, " ").split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w.toLowerCase()));
  // Acronyms (FTC, FLSA, GDPR) name the agency or act, so they lead; then the longest words.
  const acronyms = [...new Set(words.filter((w) => /^[A-Z]{2,6}$/.test(w)).map((w) => w.toLowerCase()))];
  const rest = [...new Set(words.map((w) => w.toLowerCase()))].filter((w) => !acronyms.includes(w) && !/\(/.test(w)).sort((a, b) => b.length - a.length);
  const ranked = [...acronyms, ...rest].slice(0, 6);
  const queries = new Set<string>([ranked.slice(0, 3).join(" "), ranked.slice(0, 2).join(" ")]);
  for (let i = 0; i < Math.min(5, ranked.length); i++) for (let j = i + 1; j < Math.min(5, ranked.length); j++) queries.add(`${ranked[i]} ${ranked[j]}`);
  const found = new Map<string, { ref: OfficialRef; title: string; n: number }>();
  await Promise.all(
    [...queries].slice(0, 10).map(async (q) => {
      try {
        const d = (await (await f(`https://www.ecfr.gov/api/search/v1/results?query=${encodeURIComponent(q)}${date ? `&date=${date}` : ""}&per_page=5`, { headers: UA })).json()) as { results?: Array<{ hierarchy: Record<string, string | null>; headings?: Record<string, string | null> }> };
        for (const r of d.results ?? []) {
          const h = r.hierarchy;
          if (!h?.["section"]) continue;
          const k = `${h["title"]}/${h["section"]}`;
          const e = found.get(k) ?? { ref: { source: "ecfr", title: Number(h["title"]), part: h["part"]!, section: h["section"]! } as OfficialRef, title: `${h["title"]} CFR ${h["section"]} — ${(r.headings?.["section"] ?? "").replace(/<[^>]+>/g, "")}`, n: 0 };
          e.n++;
          found.set(k, e);
        }
      } catch {
        /* offline or rate-limited */
      }
    }),
  );
  return [...found.values()].sort((a, b) => b.n - a.n).slice(0, 6);
}

export interface FoundProvision { ref: OfficialRef; title: string; via: "registry" | "exa" | "ecfr-search" | "catalog"; url?: string; also?: OfficialRef[]; p?: number }

/**
 * Candidates from the registry, Exa (official domains) and eCFR search; with a judge, the one whose
 * description fits the situation best (works across languages and slang); without one, keywords.
 */
export async function findProvision(question: string, opts: { exaSearch?: ExaSearch; catalogSearch?: CatalogSearch; fetch?: RawFetch; date?: string; judge?: DecisionProvider; second?: DecisionProvider; offline?: boolean; keywordsOnly?: boolean } = {}): Promise<FoundProvision> {
  const f = opts.fetch ?? fetch;
  const scores = registryScores(question);
  const top = scores[0];
  if (opts.offline) {
    // Private mode: the question is sent to no hosted service: no hosted judge, no web search, no eCFR search
    // (which would receive the person's words). First the registry on this device, by keywords; then the semantic
    // catalog, which also runs on this device. Its first hit is taken as it is: the on-device judge, trained to
    // choose clauses, did not improve on it when asked to choose among the top five (39.5 % against 43.8 %).
    const hits = opts.catalogSearch ? await opts.catalogSearch(question, opts.date).catch(() => []) : [];
    const reg = hits.find((h) => h.kind === "registry" && !ruledOutHit(question, h.ref)), cfr = hits.find((h) => h.kind !== "registry");
    // 1. A built-in right matched by meaning (any language). 2. A clear keyword match. 3. The nearest CFR provision.
    if (reg && reg.score >= REGISTRY_MATCH && reg.score >= (cfr?.score ?? 0) - REGISTRY_MARGIN) return { ref: reg.ref, title: reg.title, via: "registry", also: reg.also, p: reg.score };
    if (top && top.score >= 2) return { ref: top.k.ref, title: top.k.title, via: "registry", also: top.k.also };
    if (cfr && cfr.score >= CATALOG_MATCH) return { ref: cfr.ref, title: cfr.title, via: "catalog", p: cfr.score };
    if (top && top.score > 0) return { ref: top.k.ref, title: top.k.title, via: "registry", also: top.k.also };
    throw new Error("no official provision found on this device for this question (private mode searches only the built-in list of rights and the on-device catalog)");
  }
  if (!opts.judge) {
    if (top && top.score >= 4) return { ref: top.k.ref, title: top.k.title, via: "registry", also: top.k.also };
    if (opts.keywordsOnly) {
      // A clear keyword match (one keyword of four letters or more) is enough here; a web result is not.
      if (top && top.score >= 2) return { ref: top.k.ref, title: top.k.title, via: "registry", also: top.k.also };
      throw new Error("no official provision found for this question");
    }
  }
  const cands: Array<FoundProvision & { about: string; bonus: number }> = scores.map(({ k, score }) => ({ ref: k.ref, title: k.title, about: k.about, via: "registry" as const, also: k.also, bonus: Math.min(0.1, score * 0.02) }));
  if (opts.exaSearch) {
    try {
      for (const r of (await opts.exaSearch(question, OFFICIAL_DOMAINS)).slice(0, 4)) {
        const ref = refFromUrl(r.url);
        if (ref && !cands.some((c) => JSON.stringify(c.ref) === JSON.stringify(ref))) cands.push({ ref, title: r.title ?? r.url, about: r.title ?? "", via: "exa", url: r.url, bonus: 0 });
      }
    } catch {
      /* fall through */
    }
  }
  // The on-device catalog adds its nearest provisions as candidates; the judge decides among all of them.
  if (opts.catalogSearch && opts.judge) {
    try {
      for (const c of (await opts.catalogSearch(question, opts.date)).filter((h) => h.kind !== "registry").slice(0, 3)) if (!cands.some((x) => JSON.stringify(x.ref) === JSON.stringify(c.ref))) cands.push({ ref: c.ref, title: c.title, about: c.about, via: "catalog", bonus: 0 });
    } catch {
      /* the catalog is optional */
    }
  }
  if (!opts.judge) {
    for (const c of await ecfrCandidates(question, opts.date, f)) if (!cands.some((x) => JSON.stringify(x.ref) === JSON.stringify(c.ref))) cands.push({ ...c, about: c.title, via: "ecfr-search", bonus: 0 });
    const e = cands.find((c) => c.via !== "registry") ?? (top && top.score > 0 ? cands[0] : undefined);
    if (!e) throw new Error("no official provision found for this question");
    return { ref: e.ref, title: e.title, via: e.via, url: e.url, also: e.also };
  }
  const q: Question[] = [{ kind: "yesno", name: "governs", instructions: "Does `provision` set the amount, rate or deadline that answers `situation` (same country or region, same kind of right)?" }];
  const judged = new Map<string, number>();
  const best = async () => {
    await Promise.all(cands.filter((c) => !judged.has(JSON.stringify(c.ref))).map(async (c) => judged.set(JSON.stringify(c.ref), (await opts.judge!.decide({ situation: question, provision: `${c.title}. ${c.about}` }, q)).answers[0]?.p ?? 0)));
    const ranked = cands.map((c) => ({ c, p: judged.get(JSON.stringify(c.ref))!, s: judged.get(JSON.stringify(c.ref))! + c.bonus })).sort((a, b) => b.s - a.s);
    // Close call between the two best: the second judge (Luna) reads both, and the two judges are averaged.
    if (opts.second && ranked.length > 1 && ranked[0]!.p >= 0.3 && ranked[0]!.s - ranked[1]!.s < 0.25 && !escalated.has(JSON.stringify(ranked[0]!.c.ref) + JSON.stringify(ranked[1]!.c.ref))) {
      escalated.add(JSON.stringify(ranked[0]!.c.ref) + JSON.stringify(ranked[1]!.c.ref));
      await Promise.all(ranked.slice(0, 2).map(async (x) => {
        const p2 = (await opts.second!.decide({ situation: question, provision: `${x.c.title}. ${x.c.about}` }, q)).answers[0]?.p ?? 0;
        x.p = (x.p + p2) / 2;
        x.s = x.p + x.c.bonus;
        judged.set(JSON.stringify(x.c.ref), x.p);
      }));
      ranked.sort((a, b) => b.s - a.s);
    }
    return ranked[0]!;
  };
  const escalated = new Set<string>();
  // Stage 1: registry (and Exa, if any). Stage 2, only when no candidate convinces the judge: eCFR search.
  let top1 = await best();
  if (top1.p < 0.5) {
    for (const c of await ecfrCandidates(question, opts.date, f)) if (!cands.some((x) => JSON.stringify(x.ref) === JSON.stringify(c.ref))) cands.push({ ...c, about: c.title, via: "ecfr-search", bonus: 0 });
    top1 = await best();
  }
  if (top1.p < 0.5) throw new Error("no official provision found for this question");
  return { ref: top1.c.ref, title: top1.c.title, via: top1.c.via, url: top1.c.url, also: top1.c.also, p: top1.p };
}

// ---------- clauses that carry amounts ----------

const NUM = /£?\$?€?\d[\d,]*(?:\.\d+)?%?/g;
export const template = (s: string) => s.replace(NUM, "#").replace(/\s+/g, " ").trim().toLowerCase();
const hasAmount = (s: string) => /[£$€]\s?\d|\b(?:EUR|GBP|USD)\s?\d|\d\s?(?:EUR|euros?|per cent|percent|%)/i.test(s);
const hasDuration = (s: string) => extractQuantities(s).some((q) => q.kind === "duration");
/** "(1) No compensation is required if …" is a tier too: the answer is nothing. */
const ZERO = /\bno (?:compensation|payment|fee|penalty) (?:is|shall be) (?:required|payable|due|imposed)\b/i;

/** What the question asks for: a sum (default) or a time limit ("how long does the company have to respond?"). */
export type Want = "amount" | "duration";
export const wantOf = (question: string): Want =>
  /\bhow long\b|\bdeadline\b|\btime limit\b|\bwithin how\b|\bhow (?:many|much) (?:days|weeks|months|time)\b|\b(?:respond|reply)\b|kuinka kauan|missä ajassa|määräaj|\bcan i (?:still )?(?:return|cancel|withdraw)\b|\breturn (?:it|a|an|the|my)\b|cooling[- ]off|right of withdrawal|withdraw from|palauttaa|peruuttamisoikeu|widerruf|zurückgeben|rückgabe/i.test(question) ? "duration" : "amount";

// Statutory outline: (a) letters, (1) numbers, (i) romans, (A) capitals, ( 1 ) italic numbers. An enumerator is
// accepted only as the next one in its sequence, so cross-references ("not falling under (a) or (b)",
// "paragraph (a) of this section") stay text.
type Kind = "letter" | "num" | "roman" | "cap" | "ital";
const LEVEL: Record<Kind, number> = { letter: 1, num: 2, roman: 3, cap: 4, ital: 5 };
const FIRST: Record<Kind, string> = { letter: "a", num: "1", roman: "i", cap: "A", ital: "1" };
const ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx"];
const nextLabel = (k: Kind, l: string) => (k === "letter" || k === "cap" ? String.fromCharCode(l.charCodeAt(0) + 1) : k === "roman" ? ROMAN[ROMAN.indexOf(l) + 1] ?? "" : String(Number(l) + 1));
interface Node { level: number; kind?: Kind; label: string; text: string; children: Node[] }

function outline(text: string): Node {
  const root: Node = { level: 0, label: "", text: "", children: [] };
  const stack: Node[] = [root];
  let pos = 0;
  const LABEL = String.raw`\((?:\s\d{1,3}\s|\d{1,3}|[a-z]{1,5}|[A-Z])\)`;
  // One enumerator or a run of them ("(1)(i) Any person …"); cross-references after "paragraph", "under" etc. stay text.
  const re = new RegExp(String.raw`(?<!\b(?:[Pp]aragraphs?|[Ss]ections?|[Ss]ubparagraphs?|[Pp]oints?|Articles?|under|in|of|to|see|with|by))\s((?:${LABEL})+)\s`, "g");
  for (const m of text.matchAll(re)) {
    const accepted: Node[] = [];
    const saved = [...stack];
    for (const [, raw0] of m[1]!.matchAll(/\((\s\d{1,3}\s|\d{1,3}|[a-z]{1,5}|[A-Z])\)/g)) {
      const raw = raw0!;
      const label = raw.trim();
      const top = stack.at(-1)!;
      let kinds: Kind[] = raw !== label ? ["ital"] : /^\d+$/.test(label) ? ["num"] : /^[A-Z]$/.test(label) ? ["cap"] : [...(ROMAN.includes(label) ? (["roman"] as Kind[]) : []), ...(label.length === 1 ? (["letter"] as Kind[]) : [])];
      if (kinds.length === 2 && top.level < 2) kinds = ["letter", "roman"];
      let node: Node | undefined;
      for (const k of kinds) {
        let i = stack.length - 1;
        while (stack[i]!.level >= LEVEL[k]) i--;
        const parent = stack[i]!;
        const prev = [...parent.children, ...accepted.filter((n) => stack.includes(n) === false && n.level === LEVEL[k])].filter((c) => c.kind === k).at(-1);
        if (label !== (prev ? nextLabel(k, prev.label) : FIRST[k])) continue;
        node = { level: LEVEL[k], kind: k, label, text: "", children: [] };
        stack.length = i + 1;
        stack.push(node);
        accepted.push(node);
        break;
      }
      if (!node) break;
    }
    if (accepted.length !== [...m[1]!.matchAll(/\(/g)].length) {
      stack.length = 0;
      stack.push(...saved);
      continue;
    }
    saved.at(-1)!.text += text.slice(pos, m.index);
    // Link the accepted run into the tree: each node under the deepest earlier node of a lower level.
    for (const n of accepted) {
      const parent = [...stack.slice(0, stack.indexOf(n))].reverse().find((x) => x.level < n.level)!;
      parent.children.push(n);
    }
    accepted.at(-1)!.text = m[1]!.slice(m[1]!.lastIndexOf("(")) + " ";
    for (const n of accepted.slice(0, -1)) n.text = m[1]!.slice(m[1]!.indexOf(`(${n.label})`), m[1]!.indexOf(`(${n.label})`) + n.label.length + 2);
    pos = m.index! + 1 + m[1]!.length + 1;
  }
  stack.at(-1)!.text += text.slice(pos);
  return root;
}

const sentences = (s: string) => s.split(/(?<=[.;:])\s+(?=[A-Z(]|\d+[A-Z]?\s+[A-Z])/);
/** A sentence that opens a list ("The hourly rate is— a £9.18 …; b £6.83 …") becomes one piece per item. */
function listItems(s: string): string[] {
  s = s.replace(/(^|\s)[a-z]{1,4}\s+(?:\.\s*){4,}(?=\s[a-z]{1,4}\s)/g, "$1"); // a repealed item ("a . . . . ") before the next one
  const m = s.match(/^(.*?(?:—|(?<=[A-Za-z])–|:-|:))\s+(.+)$/);
  if (!m || !/;\s/.test(m[2]!)) return [s];
  return m[2]!.split(/;\s+(?:and\s+|or\s+)?/).map((it) => `${m[1]!.slice(-220).trim()} … ${it.trim()}`);
}

/**
 * Amount-bearing clauses (or, with want "duration", time-limit clauses), each with its chain of enclosing
 * paragraphs ("(a) interstate … (3) $1,550", "(b) penalty fees … (ii) safe harbors … (A) $28").
 */
export function amountClauses(text: string, want: Want = "amount"): string[] {
  const has = want === "duration" ? hasDuration : (x: string) => hasAmount(x) || ZERO.test(x);
  const out: string[] = [];
  const clip = (s: string) => s.replace(/;\s*(?:and|or)?\s*$/, "").trim();
  const walk = (node: Node, chain: string[]) => {
    const own = clip(node.text);
    if (own && has(own)) {
      const pieces = own.length <= 400 && node.level > 0 ? [own] : sentences(own).flatMap(listItems);
      for (const piece of pieces) if (has(piece.split(" … ").at(-1)!)) out.push([...chain, clip(piece)].join(" … "));
    }
    // The root's text is context only when it introduces a list ("… compensation amounting to:").
    const intro = node.level === 0 ? (/[:—]\s*$/.test(own) ? sentences(own).at(-1)!.slice(-300) : "") : own.length <= 300 ? own : `${own.slice(0, 150)} … ${own.slice(-150)}`;
    for (const c of node.children) walk(c, intro ? [...chain, intro] : chain);
  };
  walk(outline(text), []);
  return out.map((c) => (c.length > 1200 ? `${c.slice(0, 1200 - c.split(" … ").at(-1)!.length - 3)} … ${c.split(" … ").at(-1)}`.slice(-1200) : c));
}

const ownPart = (clause: string) => {
  const own = clause.split(" … ").at(-1)!;
  // Drop headings that run into the rule ("PART 2 Rates … The national living wage 4 The single hourly rate …").
  const m = own.match(/\b(The|A|An|Compensation|Passengers?|Where|If|In)\b[^]*$/);
  return m && m.index! > 0 && (hasAmount(m[0]) || hasDuration(m[0]) || ZERO.test(m[0])) ? m[0] : own;
};
function amountOf(clause: string, want: Want = "amount"): Quantity | undefined {
  const own = ownPart(clause);
  const zero = want === "amount" && !hasAmount(own) ? own.match(ZERO) : null;
  if (zero) return { kind: "money", value: 0, unit: "", text: zero[0] };
  const qs = extractQuantities(own);
  if (want === "duration") return qs.find((q) => q.kind === "duration") ?? qs[0];
  return qs.find((q) => q.kind === "money") ?? qs.find((q) => q.kind === "percent") ?? qs[0];
}

// ---------- conditions: code rules out tiers the facts contradict before the judge reads anything ----------

type Op = "<" | "<=" | ">" | ">=";
interface Bound { op: Op; kind: string; unit: string; value: number }
const FLIP: Record<Op, Op> = { "<": ">=", "<=": ">", ">": "<=", ">=": "<" };
const holds = (b: Bound, x: number) => (b.op === "<" ? x < b.value : b.op === "<=" ? x <= b.value : b.op === ">" ? x > b.value : x >= b.value);

export interface Facts { quantities: Array<{ kind: string; unit: string; value: number }>; age?: number; ageMax?: number }
const WORD_N: Record<string, number> = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 };
const toN = (s: string) => WORD_N[s.toLowerCase()] ?? Number(s);
/**
 * The facts code may use to rule tiers out. Deliberately conservative (red-team findings, 14 Nov 2026):
 * - "1 hour and 45 minutes", "two and a half hours" are one duration, not two;
 * - miles are converted to kilometres;
 * - "born in 2003" gives an age range on the event date (a birthday may or may not have passed);
 * - a kind of quantity stated with two different values ("drove 30 km to the airport … a 2,400 km flight")
 *   is ignored: code cannot tell which one decides, so the judges do.
 */
export function factsOf(question: string, eventDate?: string): Facts {
  let q = question
    .replace(/\b(\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*(?:hours?|hrs?|h)\.?,?\s*(?:and\s+)?(\d+)\s*(?:minutes?|mins?)\b/gi, (_, h, m) => `${toN(h) * 60 + Number(m)} minutes`)
    .replace(/\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+and\s+a\s+half\s+hours?\b/gi, (_, h) => `${toN(h) * 60 + 30} minutes`)
    .replace(/\ban hour and a half\b/gi, "90 minutes")
    .replace(/\bhalf an hour\b/gi, "30 minutes")
    .replace(/(\d[\d,.]*)\s*(?:miles?|mi)\b/gi, (_, n) => `${Math.round(Number(n.replace(/,/g, "")) * 1.609344)} km`);
  const all = extractQuantities(q).filter((x) => x.kind === "duration" || x.kind === "distance").map((x) => ({ kind: x.kind, unit: x.unit, value: x.value }));
  const values = new Map<string, Set<number>>();
  for (const x of all) values.set(`${x.kind}|${x.unit}`, (values.get(`${x.kind}|${x.unit}`) ?? new Set()).add(x.value));
  const quantities = all.filter((x) => values.get(`${x.kind}|${x.unit}`)!.size === 1);
  // An exact age wins ("I was 22 years old … I wasn't under 18").
  const before = (at: number, n = 18) => q.slice(Math.max(0, at - n), at);
  const negated = (at: number) => /(?:\bnot|\bnever|\bno longer|n't|nt)\s+(?:\w+\s+)?$/i.test(before(at, 24));
  const boundWord = (at: number) => /\b(?:under|below|less than|younger than|over|older than|more than|at least|nearly|almost|about|around)\s+$/i.test(before(at));
  for (const m of q.matchAll(/\b(\d{1,2})[- ]years?[- ]old\b|\baged?\s+(\d{1,2})\b|\bI(?:'m| am| was)\s+(\d{1,2})\b/gi)) {
    if (!negated(m.index!) && !boundWord(m.index!)) return { quantities, age: Number(m[1] ?? m[2] ?? m[3]) };
  }
  // "under 18 years old" is a bound, not an age: under/below → at most n-1, over/at least → n or more (an age range).
  // A negated bound ("I wasn't under 18") is not used: code does not reason about negation.
  for (const b of q.matchAll(/\b(under|below|less than|younger than|over|older than|more than|at least)\s+(?:the age of\s+)?(\d{1,2})(?:[- ]years?(?:[- ]old)?)?\b/gi)) {
    if (negated(b.index!)) continue;
    const n = Number(b[2]);
    return /under|below|less|younger/i.test(b[1]!) ? { quantities, age: 0, ageMax: n - 1 } : { quantities, age: /at least/i.test(b[1]!) ? n : n + 1, ageMax: 120 };
  }
  const born = q.match(/\bborn (?:in |on )?(?:\d{1,2} \w+ |\w+ )?((?:19|20)\d{2})\b/i);
  const year = Number((eventDate ?? q.match(/\b((?:19|20)\d{2})-\d{2}-\d{2}\b/)?.[1] ?? "").slice(0, 4));
  if (born && year) return { quantities, age: year - Number(born[1]) - 1, ageMax: year - Number(born[1]) };
  return { quantities };
}

function boundsOf(segment: string): Bound[] {
  // "aged 21 years or over" is an age, handled below, not a duration to compare with how long someone worked.
  const isAge = (text: string) => { const i = segment.indexOf(text); return i >= 0 && /\b(?:aged|age of|aged under|aged over)\s*$/i.test(segment.slice(Math.max(0, i - 16), i)); };
  const out: Bound[] = conditionsOf(segment).filter((c) => !(c.q.kind === "duration" && c.q.unit === "year" && isAge(c.q.text))).map((c) => ({ op: c.op, kind: c.q.kind, unit: c.q.unit, value: c.q.value }));
  for (const q of extractQuantities(segment)) {
    const i = segment.indexOf(q.text);
    if (/\b(?:not|no) later than\s*$/i.test(segment.slice(Math.max(0, i - 20), i))) out.push({ op: "<=", kind: q.kind, unit: q.unit, value: q.value });
  }
  const age = (re: RegExp, op: Op) => { for (const m of segment.matchAll(re)) out.push({ op, kind: "age", unit: "year", value: Number(m[1]) }); };
  age(/\baged (\d+)(?: years)? or (?:over|more|above)/gi, ">=");
  age(/\baged (?:under|less than) (\d+)/gi, "<");
  age(/\b(?:not yet aged|under the age of|not attained the age of|but not) (\d+)/gi, "<");
  age(/(?<!not )\battained the age of (\d+)/gi, ">=");
  // "if the carrier does not offer alternate transportation … less than two hours after" holds when it is two hours or more.
  return /\b(?:does|do|did) not offer\b|\bfails? to offer\b/i.test(segment) ? out.map((b) => (b.kind === "age" ? b : { ...b, op: FLIP[b.op] })) : out;
}

/**
 * "fail" when every alternative of the clause has a stated condition the facts break; "fit" when one is met
 * ("all" when every alternative states conditions and the facts meet them all); "free" when nothing is stated.
 */
export function fitOf(clause: string, facts: Facts): "all" | "fit" | "free" | "fail" {
  // Alternatives: "…, and for all other flights …", "…; or (b) by three hours …". Not ", or if none," (same condition).
  const segs = ownPart(clause).split(/,\s*and\s+(?=for\b|in\b)|;\s*or\s+/);
  let fit = 0;
  let free = false;
  for (const seg of segs) {
    const relevant = boundsOf(seg).filter((b) => (b.kind === "age" ? facts.age !== undefined : facts.quantities.some((q) => q.kind === b.kind && q.unit === b.unit)));
    if (!relevant.length) { free = true; continue; }
    // An age range ("born in 2003") decides a bound only when both ends agree; otherwise it is not used.
    const ageKnown = (b: Bound) => facts.ageMax === undefined || holds(b, facts.age!) === holds(b, facts.ageMax);
    if (relevant.some((b) => b.kind === "age" && !ageKnown(b))) { free = true; continue; }
    const ok = relevant.every((b) => (b.kind === "age" ? holds(b, facts.age!) : facts.quantities.some((q) => q.kind === b.kind && q.unit === b.unit && relevant.filter((r) => r.kind === b.kind && r.unit === b.unit).every((r) => holds(r, q.value)))));
    if (ok) fit++;
  }
  return fit && fit === segs.length ? "all" : fit ? "fit" : free ? "free" : "fail";
}

/** A residual clause ("(c) EUR 600 for all flights not falling under (a) or (b)") yields to a sibling the facts fully meet. */
function residualRuledOut(clauses: string[], fits: string[]): boolean[] {
  const label = (c: string) => c.split(" … ").at(-1)!.match(/^\((\w+)\)/)?.[1];
  const ctx = (c: string) => c.split(" … ").slice(0, -1).join(" … ");
  return clauses.map((c) => {
    const m = c.split(" … ").at(-1)!.match(/\b(?:not falling (?:under|within)|other than)\s+((?:\(\w+\)(?:,\s*|\s+or\s+|\s+and\s+)?)+)/i);
    if (!m) return false;
    const refs = [...m[1]!.matchAll(/\((\w+)\)/g)].map((x) => x[1]);
    return clauses.some((o, j) => j !== clauses.indexOf(c) && ctx(o) === ctx(c) && refs.includes(label(o)) && fits[j] === "all");
  });
}

/** The yes/no question every judge answers per clause (shared with bench/situations/tournament.mjs). */
export const CLAUSE_QUESTION: Question = { kind: "yesno", name: "applies", instructions: "Does `clause` set the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)?" };

/** Code's verdict per clause before any judge: "fail" clauses are ruled out by the stated facts. */
export function codeFits(situation: string, clauses: string[]): string[] {
  const facts = factsOf(situation);
  const fits: string[] = clauses.map((c) => fitOf(c, facts));
  // "(b) … all intra-Community flights of more than 1500 kilometres, and … all other flights between 1500 and 3500
  // kilometres" (Regulation 261/2004, Art. 7(1)(b)) is two alternatives, not two conditions: a 4,400 km flight
  // within the EU is in (b), a 4,400 km flight out of the EU is not. Read as two conditions, code ruled (b) out
  // for Stockholm to Tenerife and the answer came out as EUR 600.
  const kms = facts.quantities.filter((x) => x.kind === "distance");
  if (kms.length === 1) {
    const intra = /not an intra-Community flight/i.test(situation) ? false : /intra-Community flight|intra-EU|within the EU\b|inside the EU\b/i.test(situation) ? true : undefined;
    clauses.forEach((c, i) => {
      const m = ownPart(c).match(/intra-Community flights of more than\s+([\d ,.]+?)\s*kilomet\w+,?\s+and (?:for )?all other flights between\s+([\d ,.]+?)\s+and\s+([\d ,.]+?)\s*kilomet/i);
      if (!m) return;
      const n = (x: string) => Number(x.replace(/[ ,.]/g, ""));
      const km = kms[0]!.value;
      fits[i] = km <= n(m[1]!) ? "fail" : km <= n(m[3]!) ? "all" : intra === true ? "all" : intra === false ? "fail" : "free";
    });
  }
  residualRuledOut(clauses, fits).forEach((out, i) => { if (out) fits[i] = "fail"; });
  // A rate for a special status applies only when the person states that status. A message that does not mention an
  // apprenticeship rules out the apprentice tier (unless nothing else is left): without this, "I was 22 and working
  // in the UK" flipped between the living wage and the apprenticeship rate from run to run.
  if (!APPRENTICE_SAID.test(situation)) {
    const special = clauses.map((c, i) => (APPRENTICE_CLAUSE.test(ownPart(c)) ? i : -1)).filter((i) => i >= 0);
    if (special.length && clauses.some((_, i) => !special.includes(i) && fits[i] !== "fail")) special.forEach((i) => { fits[i] = "fail"; });
  }
  return fits;
}
const APPRENTICE_CLAUSE = /\bapprentice(ship)?\b/i;
/** Words (and common misspellings) by which a person says they are, or are not, an apprentice; the negation is then left to the judges. */
const APPRENTICE_SAID = /appr\w{0,3}nti|oppisopimu|lehrling|azubi|auszubild/i;

export const TIER_QUESTION = "Which option sets the amount, rate, limit or time limit that applies to the person in `situation` (the same kind of case, party and circumstances)?";
const LETTERS = "ABCDEFGHIJKLMNOP";

export interface ClauseVote { judge: string; index: number; p: number; mode: "choice" | "yesno"; /** The judge's top option was not strictly ahead of another one it was shown: no preference, so not a vote. */ tied?: boolean }
export interface ClauseChoice {
  index: number;
  p: number;
  receipts: JudgmentReceipt[];
  ruledOut: number;
  /** Every judge picked this clause on its own (and code had not ruled it out): the condition for signing without asking. */
  agreed: boolean;
  votes: ClauseVote[];
  /** Judges that could not answer at all (endpoint down, timeout). They cast no vote, and `agreed` is then false. */
  abstained: string[];
  /** Votes of advisory judges (for example the on-device judge while it is being measured): shown, never counted. */
  advisory: ClauseVote[];
}

/**
 * Listwise panel. Every judge answers ONE choice question with all live tiers as options, so the tiers are
 * read against each other (measured on 906 situations from unseen provisions: Jev 62 % -> 74 %, Luna
 * 60 % -> 74 % against one yes/no per clause; on 1,168 verified situations all three agree in 86 % of cases
 * and are then right in 98.6 %). The probabilities are averaged; `agreed` says whether each judge alone picked the same clause.
 * A judge that cannot answer a choice question (more than 16 tiers, a refusal, no probabilities) is asked
 * one yes/no per clause instead. A judge that cannot answer at all (an error, a timeout, a refusal, no usable
 * probabilities) abstains: the others still choose the clause, but the choice is not `agreed`, because the
 * signing rule was measured with every judge voting.
 *
 * `agreed` needs all of: at least two judges voted, none abstained, each judge's top option is strictly ahead
 * of its other options (a tie is no preference), a yes/no judge said yes (p >= 0.5) to its pick, every vote
 * equals the pick, and code did not rule out every tier.
 */
export async function chooseClause(situation: string, clauses: string[], judges: DecisionProvider[], at?: Date, advisors: DecisionProvider[] = []): Promise<ClauseChoice> {
  const fits = codeFits(situation, clauses);
  const live = fits.some((x) => x !== "fail") ? clauses.map((_, i) => i).filter((i) => fits[i] !== "fail") : clauses.map((_, i) => i);
  // The stated facts contradict every tier: judges still pick the least wrong one, but that is never `agreed`.
  const vetoedAll = clauses.length > 0 && fits.every((x) => x === "fail");
  const receipts: JudgmentReceipt[] = [];
  const bestOf = (ps: number[], among: number[]) => among.reduce((b, i) => (ps[i]! > ps[b]! ? i : b), among[0]!);
  // What a judge is shown. Several live tiers: those. One live tier among siblings that code ruled out: all the
  // tiers, so the judge reads the tier against its siblings and can contradict code (then it is not `agreed`);
  // a lone yes/no on the surviving tier proved unreliable (a clearly applicable tier got p = 0.18 from one judge).
  const shown = live.length === 1 && clauses.length >= 2 && clauses.length <= LETTERS.length ? clauses.map((_, i) => i) : live;
  // Advisors answer the same choice question; their vote is reported but changes neither the pick nor `agreed`.
  const advising = Promise.all(
    advisors.map(async (judge): Promise<ClauseVote | null> => {
      if (shown.length < 2 || shown.length > LETTERS.length) return null;
      try {
        const q: Question[] = [{ kind: "choice", name: "tier", instructions: TIER_QUESTION, options: Object.fromEntries(shown.map((i, k) => [LETTERS[k]!, clauses[i]!])) }];
        const a = (await judge.decide({ situation }, q)).answers[0];
        if (!a || a.refused || !a.probabilities) return null;
        const ps = clauses.map(() => 0);
        shown.forEach((i, k) => { ps[i] = a.probabilities?.[LETTERS[k]!] ?? 0; });
        const i = bestOf(ps, shown);
        return { judge: judge.id, index: i, p: ps[i]!, mode: "choice" };
      } catch {
        return null;
      }
    }),
  );
  const all = await Promise.all(
    judges.map(async (judge) => {
      const ps = clauses.map(() => 0);
      if (shown.length >= 2 && shown.length <= LETTERS.length) {
        const q: Question[] = [{ kind: "choice", name: "tier", instructions: TIER_QUESTION, options: Object.fromEntries(shown.map((i, k) => [LETTERS[k]!, clauses[i]!])) }];
        try {
          const state = { situation };
          const r = await judge.decide(state, q);
          const a = r.answers[0];
          if (a && !a.refused && ((a.probabilities && Object.keys(a.probabilities).length) || a.choice)) {
            shown.forEach((i, k) => { ps[i] = a.probabilities?.[LETTERS[k]!] ?? (a.choice === LETTERS[k] ? 1 : 0); });
            receipts.push(...(await receiptsFor("then-now-clause", state, q, r, at)));
            return { judge: judge.id, ps, mode: "choice" as const };
          }
        } catch (e) {
          // A judge that timed out does not get one more question per clause: it abstains.
          if (e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError")) return { judge: judge.id, ps, mode: "choice" as const, failed: e };
          /* otherwise fall back to one question per clause (a judge without choice support) */
        }
      }
      try {
        const own: JudgmentReceipt[] = [];
        await Promise.all(
          live.map(async (i) => {
            const state = { situation, clause: clauses[i]! };
            const r = await judge.decide(state, [CLAUSE_QUESTION]);
            const a = r.answers[0];
            if (!a || a.refused || typeof a.p !== "number" || !Number.isFinite(a.p)) throw new Error(`${judge.id}: no answer`);
            ps[i] = a.p;
            own.push(...(await receiptsFor("then-now-clause", state, [CLAUSE_QUESTION], r, at)));
          }),
        );
        receipts.push(...own);
        return { judge: judge.id, ps, mode: "yesno" as const };
      } catch (e) {
        return { judge: judge.id, ps, mode: "yesno" as const, failed: e instanceof Error ? e : new Error(String(e)) };
      }
    }),
  );
  const answered = all.filter((j) => !("failed" in j));
  const advisory = (await advising).filter((v): v is ClauseVote => !!v);
  if (!answered.length) {
    // One live tier and no judge able to confirm it (for example a judge that only answers choice questions):
    // the tier stands on code alone and the person reviews it. With several tiers there is nothing to choose with.
    if (live.length === 1 && !vetoedAll) return { index: live[0]!, p: 0, receipts, ruledOut: clauses.length - live.length, agreed: false, votes: [], abstained: all.map((j) => j.judge), advisory };
    throw (all.find((j) => "failed" in j) as { failed: Error } | undefined)?.failed ?? new Error("no judge");
  }
  const perJudge = answered;
  const abstained = all.filter((j) => "failed" in j).map((j) => j.judge);
  const mean = clauses.map((_, i) => perJudge.reduce((s, j) => s + j.ps[i]!, 0) / Math.max(1, perJudge.length));
  // Code's veto stands: the pick is among the live tiers. A clause whose stated condition the facts meet wins a near-tie.
  const index = bestOf(mean.map((p, i) => p + (fits[i] === "fit" || fits[i] === "all" ? 0.05 : 0)), live);
  // A judge's own vote is its top option among those it was shown, which may be a tier code ruled out.
  const votes: ClauseVote[] = perJudge.map((j) => {
    const among = j.mode === "choice" ? shown : live;
    const i = bestOf(j.ps, among);
    // Exact equality on purpose (1e-9 absorbs float noise): Jev and Luna report two decimals and log-probabilities
    // are quantised, so exact ties are what occurs. A uniform or all-zero answer is a tie too.
    const tied = among.some((k) => k !== i && j.ps[k]! >= j.ps[i]! - 1e-9);
    return { judge: j.judge, index: i, p: j.ps[i]!, mode: j.mode, ...(tied ? { tied } : {}) };
  });
  // Two judges at least: one judge agreeing with itself is not agreement. A yes/no judge must say yes to its pick.
  const agreed = !vetoedAll && !abstained.length && votes.length >= 2 && votes.every((v) => !v.tied && v.index === index && (v.mode === "choice" || v.p >= 0.5));
  return { index, p: mean[index] ?? 0, receipts, ruledOut: vetoedAll ? clauses.length : clauses.length - live.length, agreed, votes, abstained, advisory };
}

/** Kept for callers of the older API: one or two judges, same panel logic. */
export async function pickClause(situation: string, clauses: string[], judge: DecisionProvider, at?: Date, second?: DecisionProvider): Promise<ClauseChoice> {
  return chooseClause(situation, clauses, second ? [judge, second] : [judge], at);
}

// ---------- what changed it, and what is coming ----------

export interface Change { effective: string; title: string; url: string; upcoming: boolean; kind?: string }

export async function amendmentsAfter(ref: OfficialRef, after: string, today: string, f: RawFetch = fetch): Promise<Change[]> {
  if (ref.source === "ecfr") {
    const url = `https://www.federalregister.gov/api/v1/documents.json?conditions%5Bcfr%5D%5Btitle%5D=${ref.title}&conditions%5Bcfr%5D%5Bpart%5D=${ref.part}&conditions%5Btype%5D%5B%5D=RULE&per_page=20&order=newest&fields%5B%5D=title&fields%5B%5D=effective_on&fields%5B%5D=html_url`;
    const d = (await (await f(url, { headers: UA })).json()) as { results?: Array<{ title: string; effective_on?: string; html_url: string }> };
    return (d.results ?? []).filter((x) => x.effective_on && x.effective_on > after).map((x) => ({ effective: x.effective_on!, title: x.title, url: x.html_url, upcoming: x.effective_on! > today }));
  }
  if (ref.source === "ukleg") {
    const [type, year, number, ...rest] = ref.path.split("/");
    const provision = rest.length >= 2 ? `${({ section: "s.", regulation: "reg.", article: "art.", schedule: "Sch.", paragraph: "para." } as Record<string, string>)[rest[0]!] ?? rest[0]} ${rest[1]}` : "";
    const feed = await (await f(`https://www.legislation.gov.uk/changes/affected/${type}/${year}/${number}/data.feed?results-count=50&sort=affecting-year-number&order=descending`, { headers: UA })).text();
    const out: Change[] = [];
    for (const e of feed.split("<ukm:Effect ").slice(1)) {
      const attr = (n: string) => e.match(new RegExp(`${n}="([^"]*)"`))?.[1] ?? "";
      const affected = attr("AffectedProvisions");
      if (provision && !new RegExp(`^${provision.replace(".", "\\.")}(\\(|\\b|$)`).test(affected)) continue;
      const date = e.match(/<ukm:InForce[^>]*Date="(\d{4}-\d{2}-\d{2})"/)?.[1];
      if (!date || date <= after) continue;
      const title = e.match(/<ukm:AffectingTitle>([^<]+)</)?.[1] ?? attr("AffectingURI");
      const url = attr("AffectingURI").replace("http://www.legislation.gov.uk/id/", "https://www.legislation.gov.uk/");
      if (!out.some((c) => c.url === url && c.effective === date)) out.push({ effective: date, title, url, upcoming: date > today, kind: attr("Type") });
    }
    return out.sort((a, b) => b.effective.localeCompare(a.effective));
  }
  const { eurlexVersions } = await import("../warrant/pointInTime.ts");
  return (await eurlexVersions(ref.celex, f))
    .filter((v) => v.date > after)
    .map((v) => ({ effective: v.date, title: `Consolidated version ${v.celex}`, url: `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:${v.celex}`, upcoming: v.date > today }));
}

/**
 * The quote pinned in the Warrant: verbatim official text the receiver can find and read. A bare list item
 * ("a £151.20", "(d) Section 5(m)(1)(A) … —$51,744") is widened back to the words that introduce it, so the
 * quote says what the amount is for.
 */
export function evidenceQuote(lawText: string, clause: string): string {
  const own = ownPart(clause);
  if (contentStems(own).size >= 3) return own;
  const at = lawText.indexOf(own);
  if (at < 0) return own;
  const end = at + own.length;
  const parent = clause.split(" … ").at(-2);
  const head = parent?.split(" … ")[0]?.slice(0, 60);
  const fromParent = head ? lawText.lastIndexOf(head, at) : -1;
  if (fromParent >= 0 && end - fromParent <= 700) return lawText.slice(fromParent, end).trim();
  // Otherwise from the start of the sentence that leads into the list.
  const before = lawText.slice(Math.max(0, at - 700), at);
  const m = [...before.matchAll(/[.;:]\s+(?=[A-Z])/g)].filter((x) => contentStems(before.slice(x.index! + x[0].length)).size >= 3).at(-1);
  return m ? (before.slice(m.index! + m[0].length) + lawText.slice(at, end)).trim() : own;
}

// ---------- Then · Now · Next ----------

export interface Moment { date: string; url: string; clause: string; amount?: Quantity; p: number }
export interface ThenNowNext {
  question: string;
  eventDate: string;
  today: string;
  provision: { ref: OfficialRef; title: string; via: string; p?: number };
  then: Moment;
  now: Moment;
  changed: boolean;
  changes: Change[];
  upcoming: Change[];
  receipts: JudgmentReceipt[];
  /** quote: verbatim official text; focus: the clause that states the amount (the end of the quote). */
  evidence: { url: string; quote: string; focus?: string; asOf: string };
  /** The event date is after today: "then" is today's text, and `upcoming` lists what takes effect before the event. */
  future?: boolean;
  note?: string;
  /** Tiers that code ruled out from the stated facts (durations, distances, ages) before the judge read them. */
  ruledOut?: number;
  /** A fact the butler computed and added to the situation (the flight distance between two named places). */
  computed?: string;
  /** How the judges voted on the clause. `agreed` is the condition for signing without asking the person. */
  agreement?: { agreed: boolean; votes: ClauseVote[]; abstained: string[]; advisory?: ClauseVote[]; note?: string };
}

/** The latest date the official source has text for (eCFR lags a few days; the others serve today). */
async function latestDate(ref: OfficialRef, today: string, f: RawFetch): Promise<string> {
  if (ref.source !== "ecfr") return today;
  try {
    const d = (await (await f("https://www.ecfr.gov/api/versioner/v1/titles.json", { headers: UA })).json()) as { titles: Array<{ number: number; latest_issue_date: string }> };
    return d.titles.find((t) => t.number === ref.title)?.latest_issue_date ?? today;
  } catch {
    return today;
  }
}

type Law = { url: string; text: string };
interface Candidate { ref: OfficialRef; law: Law; clause: string }

/** Clauses across a provision family (e.g. adult and younger-worker rates) on one date. */
async function familyClauses(refs: OfficialRef[], date: string, want: Want, f: RawFetch): Promise<{ cands: Candidate[]; found: number }> {
  const laws = await Promise.all(
    refs.map((r) =>
      lawOn(r, date, f).catch((e: Error) => {
        if (/^404\b/.test(e.message)) return null; // not in force on that date
        throw e;
      }),
    ),
  );
  const cands: Candidate[] = [];
  for (const [i, law] of laws.entries()) {
    if (!law) continue;
    let cs = amountClauses(law.text, want);
    if (!cs.length) cs = amountClauses(law.text, want === "amount" ? "duration" : "amount");
    for (const clause of cs) cands.push({ ref: refs[i]!, law, clause });
  }
  return { cands, found: laws.filter(Boolean).length };
}

export async function thenNowNext(
  input: { question: string; eventDate: string; today?: string; ref?: OfficialRef; title?: string },
  deps: {
    judge: DecisionProvider;
    fetch?: RawFetch;
    exaSearch?: ExaSearch;
    second?: DecisionProvider;
    panel?: DecisionProvider[];
    /** The on-device semantic catalog, as one more source of provision candidates (and the only search in private mode). */
    catalogSearch?: CatalogSearch;
    /** Judges whose vote is shown but not counted (the on-device judge while its accuracy is being measured). */
    advisors?: DecisionProvider[];
    /** Who judges the provision candidates. Default: `judge`. `null`: private mode, the question is sent nowhere and only the registry on this device is matched by keywords. */
    provisionJudge?: DecisionProvider | null;
  },
): Promise<ThenNowNext> {
  const f = deps.fetch ?? fetch;
  const today = input.today ?? new Date().toISOString().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(input.eventDate)) throw new Error("eventDate must be YYYY-MM-DD");
  const want = wantOf(input.question);
  const found: FoundProvision | { ref: OfficialRef; title: string; via: string; also?: OfficialRef[]; p?: number } = input.ref
    ? { ref: input.ref, title: input.title ?? "", via: "given", also: REGISTRY.find((k) => JSON.stringify(k.ref) === JSON.stringify(input.ref))?.also }
    : deps.provisionJudge === null
      ? await findProvision(input.question, { offline: true, catalogSearch: deps.catalogSearch, date: input.eventDate })
      : await findProvision(input.question, { exaSearch: deps.exaSearch, catalogSearch: deps.catalogSearch, fetch: f, date: input.eventDate, judge: deps.provisionJudge ?? deps.judge, second: deps.second }).catch(async (e: Error) => {
          // A judge that is unsure of every candidate still leaves the keyword route.
          if (!/no official provision/.test(e.message)) throw e;
          // Only a strong keyword match in the built-in list: never the first web result the judge has just rejected
          // (a rent question from Helsinki was answered from a Scottish tenancy act that way).
          return findProvision(input.question, { fetch: f, date: input.eventDate, keywordsOnly: true });
        });
  const refs = [found.ref, ...(found.also ?? [])];
  const nowDate = await latestDate(found.ref, today, f);
  const future = input.eventDate > today;
  const thenDate = future ? nowDate : input.eventDate;
  const [thenSet, nowSet] = await Promise.all([familyClauses(refs, thenDate, want, f), familyClauses(refs, nowDate, want, f)]);
  if (!thenSet.found) throw new Error(`${found.title || "the provision"} was not in force on ${thenDate} (the official source has no version for that date)`);
  if (!thenSet.cands.length) throw new Error(`no ${want === "duration" ? "time-limit" : "amount-bearing"} clause in ${found.title || "the provision"} on ${thenDate}`);
  const judges = [deps.judge, ...(deps.second ? [deps.second] : []), ...(deps.panel ?? [])];
  // A flight between two named places gets its distance computed, so the person need not know the kilometres.
  const computed = flightNote(input.question);
  const situation = input.question + computed;
  const pickThen = await chooseClause(situation, thenSet.cands.map((c) => c.clause), judges, undefined, deps.advisors);
  const chosen = thenSet.cands[pickThen.index]!;
  // The same clause today: same template if the wording kept, otherwise ask the judge again.
  let nowIdx = nowSet.cands.findIndex((c) => template(ownPart(c.clause)) === template(ownPart(chosen.clause)));
  let nowP = pickThen.p;
  const receipts = [...pickThen.receipts];
  if (nowIdx < 0 && nowSet.cands.length) {
    const pickNow = await chooseClause(situation, nowSet.cands.map((c) => c.clause), judges);
    nowIdx = pickNow.index;
    nowP = pickNow.p;
    receipts.push(...pickNow.receipts);
  }
  const then: Moment = { date: thenDate, url: chosen.law.url, clause: chosen.clause, amount: amountOf(chosen.clause, want), p: pickThen.p };
  const nowC = nowSet.cands[nowIdx];
  const now: Moment = { date: nowDate, url: nowC?.law.url ?? "", clause: nowC?.clause ?? "", amount: nowC ? amountOf(nowC.clause, want) : undefined, p: nowP };
  const changed = !!(then.amount && now.amount && (then.amount.value !== now.amount.value || then.amount.unit !== now.amount.unit)) || template(ownPart(chosen.clause)) !== template(ownPart(now.clause));
  let changes: Change[] = [];
  try {
    changes = await amendmentsAfter(chosen.ref, future ? nowDate : input.eventDate, today, f);
  } catch {
    /* change feeds are best-effort */
  }
  const upcoming = changes.filter((c) => c.upcoming);
  const before = upcoming.filter((c) => c.effective <= input.eventDate);
  const note = future
    ? `${input.eventDate} is in the future: this is the law as it stands on ${nowDate}.${before.length ? ` ${before.length} announced change${before.length > 1 ? "s take" : " takes"} effect before then (${before.map((c) => c.effective).join(", ")}); check the amount again on the day.` : " No announced change takes effect before then."}`
    : undefined;
  return {
    question: input.question,
    eventDate: input.eventDate,
    today,
    provision: { ref: chosen.ref, title: found.title, via: found.via, p: found.p },
    then,
    now,
    changed,
    changes: changes.filter((c) => !c.upcoming),
    upcoming,
    receipts,
    evidence: { url: chosen.law.url, quote: evidenceQuote(chosen.law.text, chosen.clause), focus: ownPart(chosen.clause), asOf: thenDate },
    ...(future ? { future, note } : {}),
    ruledOut: pickThen.ruledOut,
    ...(computed ? { computed: computed.trim().replace(/^\(|\)$/g, "") } : {}),
    agreement: { agreed: pickThen.agreed, votes: pickThen.votes, abstained: pickThen.abstained, advisory: pickThen.advisory },
  };
}

/** A compile result the signed Warrant accepts: one outcome premise, quoted from the pinned official version. */
export function asTwoLane(r: ThenNowNext): TwoLaneResult {
  const quote = r.evidence.quote;
  const quantity = r.then.amount ?? { kind: "money", value: 0, unit: "", text: "" };
  return {
    question: `${r.question} (law as of ${r.eventDate})`,
    lawAsOf: r.evidence.asOf,
    answerLane: [],
    premises: [
      {
        premise: { role: "outcome", quantity, sentence: quote, sourceUrl: r.evidence.url, support: 1 },
        triangulation: { status: "agree", quote, url: r.evidence.url, ...(r.evidence.focus && r.evidence.focus !== quote ? { focus: r.evidence.focus } : {}) },
        status: "confirmed",
        note: `official text as of ${r.eventDate}`,
      },
    ],
    extraction: { quantity, sentence: quote, sourceUrl: r.evidence.url, support: 1 } as never,
    citationQuery: null,
    authorityLane: [],
    legalUrls: [r.evidence.url],
    triangulation: { status: "agree", quote, url: r.evidence.url, ...(r.evidence.focus && r.evidence.focus !== quote ? { focus: r.evidence.focus } : {}) },
    outcome: r.then.amount ? "GROUNDED" : "NEEDS_INFO",
    reasons: [],
    judgments: r.receipts,
    quarantined: [],
  } as TwoLaneResult;
}
