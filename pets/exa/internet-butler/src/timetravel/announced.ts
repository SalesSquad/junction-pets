/**
 * "Next" beyond the official feeds: changes that are announced or published but not yet in force.
 *
 * The official change feeds (Federal Register effective dates, the legislation.gov.uk effects feed, EU
 * consolidated versions) list instruments once they are made. What is coming is often public earlier and
 * elsewhere: a government announcement of next year's rate, an adopted EU regulation that applies from a
 * later date, a final rule with a future effective date. No model has these in its weights; they are on the
 * live web. So this step is where web search is load-bearing:
 *
 *   find     Exa search restricted to government and official domains, published in the last 15 months
 *   veto     code keeps only documents whose own text states a date after today (the date must be quoted)
 *   confirm  a typed judge answers: does this document announce a not-yet-in-force change to THIS provision?
 *   show     the date, the sentence that states it, any amount in that sentence, and the source link
 *
 * Nothing here is treated as law: an announced change is a warning with a source, shown apart from the
 * pinned official versions, and a Warrant never cites it.
 */
import { extractQuantities, type Quantity } from "../warrant/lanes.ts";
import type { DecisionProvider, Question } from "../decide/decide.ts";

export interface WebDoc { url: string; title?: string; publishedDate?: string; highlights?: string[]; text?: string }
export type GovSearch = (query: string, opts: { includeDomains: string[]; startPublishedDate: string; highlightQuery: string }) => Promise<WebDoc[]>;

export const GOV_DOMAINS: Record<string, string[]> = {
  US: ["federalregister.gov", "govinfo.gov", "transportation.gov", "dol.gov", "ftc.gov", "consumerfinance.gov", "ssa.gov", "cms.gov", "regulations.gov"],
  UK: ["gov.uk", "legislation.gov.uk", "parliament.uk"],
  EU: ["eur-lex.europa.eu", "europa.eu", "ec.europa.eu", "consilium.europa.eu", "europarl.europa.eu"],
};

const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
const pad = (n: number | string) => String(n).padStart(2, "0");

/** Dates written in a text, as ISO strings with the words that state them: "1 April 2027", "April 1, 2027", "April 2027", "2027-04-01", "23.10.2027". */
export function datesIn(text: string): Array<{ iso: string; text: string; index: number }> {
  const out: Array<{ iso: string; text: string; index: number }> = [];
  const M = MONTHS.join("|");
  for (const m of text.matchAll(new RegExp(String.raw`\b(\d{1,2})(?:st|nd|rd|th)?\s+(${M})\s+(\d{4})\b`, "gi"))) out.push({ iso: `${m[3]}-${pad(MONTHS.indexOf(m[2]!.toLowerCase()) + 1)}-${pad(m[1]!)}`, text: m[0], index: m.index! });
  for (const m of text.matchAll(new RegExp(String.raw`\b(${M})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b`, "gi"))) out.push({ iso: `${m[3]}-${pad(MONTHS.indexOf(m[1]!.toLowerCase()) + 1)}-${pad(m[2]!)}`, text: m[0], index: m.index! });
  for (const m of text.matchAll(new RegExp(String.raw`(?<!\d\s)\b(${M})\s+(\d{4})\b`, "gi"))) if (!out.some((d) => d.index <= m.index! && m.index! < d.index + d.text.length)) out.push({ iso: `${m[2]}-${pad(MONTHS.indexOf(m[1]!.toLowerCase()) + 1)}-01`, text: m[0], index: m.index! });
  for (const m of text.matchAll(/\b(20\d{2})-(\d{2})-(\d{2})\b/g)) out.push({ iso: m[0], text: m[0], index: m.index! });
  for (const m of text.matchAll(/\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b/g)) out.push({ iso: `${m[3]}-${pad(m[2]!)}-${pad(m[1]!)}`, text: m[0], index: m.index! });
  return out.filter((d) => /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(d.iso)).sort((a, b) => a.index - b.index);
}

export interface Announced {
  url: string;
  title: string;
  published?: string;
  /** The first date after today that the document itself states. */
  effective: string;
  /** The sentence that states that date, verbatim from the document. */
  quote: string;
  /** The new amount: the figure after "to", or the only figure, in that sentence or else in the document's title. */
  amount?: Quantity;
  /** Where `amount` was read: the quoted sentence, or the document's title (the UI says so). */
  amountFrom?: "quote" | "title";
  p: number;
}

/** The sentence that holds the date at `index`: it ends at the next full stop or line break (highlights are joined by line breaks) and always keeps the date in view. */
const sentenceAround = (text: string, index: number, len: number) => {
  const dot = text.lastIndexOf(". ", index), nl = text.lastIndexOf("\n", index);
  const start = Math.max(dot < 0 ? 0 : dot + 2, nl < 0 ? 0 : nl + 1);
  const stop = /\. |\n/g;
  stop.lastIndex = index + len;
  const e = stop.exec(text);
  const end = e ? e.index + (e[0] === "\n" ? 0 : 1) : Math.min(text.length, index + 300);
  const from = index + len - start > 420 ? index + len - 420 : start;
  return ((from > start ? "… " : "") + text.slice(from, Math.min(end, from + 420))).replace(/\s+/g, " ").trim();
};
// A future date in a sentence about comments or a consultation is a deadline, not the day a change takes effect.
const DEADLINE = /\b(comments?|consultation|submissions?|responses?|closes?|closing|deadline|hearing|expir\w+)\b/i;
const EFFECT = /\b(effective|takes? effect|appl(?:y|ies|icable)|in(?:to)? force|from|rises?|increases?)\b/i;
// "Following consultation, the rate rises to … from 1 April": a sentence that plainly speaks of taking effect is kept.
const TAKES_EFFECT = /\b(effective|takes? effect|comes? into force|in force|appl(?:y|ies) from|rises?|increases?)\b/i;
const reEsc = (t: string) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** The new amount in a sentence: the figure written after "to" ("from £12.71 to £13.21"), or the only figure; never a guess between several. */
const newAmount = (text: string): Quantity | undefined => {
  const qs = extractQuantities(text).filter((x) => x.kind === "money" || x.kind === "percent");
  return qs.find((x) => new RegExp(String.raw`\bto\s+(?:\w+\s+){0,2}` + reEsc(x.text)).test(text)) ?? (qs.length === 1 ? qs[0] : undefined);
};

export async function announcedChanges(
  input: { title: string; about?: string; jurisdiction: string; today: string },
  deps: { search: GovSearch; judge: DecisionProvider; max?: number },
): Promise<Announced[]> {
  const domains = GOV_DOMAINS[input.jurisdiction] ?? [...GOV_DOMAINS.US!, ...GOV_DOMAINS.UK!, ...GOV_DOMAINS.EU!];
  const since = new Date(Date.parse(input.today) - 456 * 864e5).toISOString().slice(0, 10);
  const subject = (input.about ?? input.title).replace(/\s+/g, " ").slice(0, 220);
  const year = Number(input.today.slice(0, 4));
  const queries = [
    `announced change to ${subject} taking effect in ${year + 1}`,
    `${input.title.split(" — ")[0]} amendment new amount applies from ${year + 1}`,
  ];
  const docs = new Map<string, WebDoc>();
  await Promise.all(
    queries.map(async (q) => {
      try {
        for (const d of await deps.search(q, { includeDomains: domains, startPublishedDate: since, highlightQuery: "the date the new amount or rule takes effect, applies from or comes into force" })) if (!docs.has(d.url)) docs.set(d.url, d);
      } catch {
        /* one failed query does not hide the other */
      }
    }),
  );
  // Code veto: the document must itself state a date after today.
  const candidates: Array<{ d: WebDoc; effective: string; quote: string }> = [];
  for (const d of docs.values()) {
    const text = [...(d.highlights ?? []), d.text ?? ""].join("\n");
    // Among the future dates the document states: drop deadlines, prefer a sentence that speaks of taking effect, then the earliest.
    const future = datesIn(text)
      .filter((x) => x.iso > input.today)
      .map((x) => ({ ...x, quote: sentenceAround(text, x.index, x.text.length) }))
      .filter((x) => !DEADLINE.test(x.quote) || TAKES_EFFECT.test(x.quote))
      .sort((a, b) => Number(EFFECT.test(b.quote)) - Number(EFFECT.test(a.quote)) || a.iso.localeCompare(b.iso))[0];
    if (future) candidates.push({ d, effective: future.iso, quote: future.quote });
  }
  const q: Question[] = [{ kind: "yesno", name: "announces", instructions: "Does `document` announce or enact a change that is not yet in force on `today` to the amount, rate or rule that `provision` sets (the same right, in the same country or region)?" }];
  const judged = await Promise.all(
    candidates.map(async (c) => {
      const r = await deps.judge.decide({ provision: `${input.title}. ${input.about ?? ""}`, today: input.today, document: `${c.d.title ?? ""}. ${c.quote}` }, q);
      return { ...c, p: r.answers[0]?.p ?? 0 };
    }),
  );
  return judged
    .filter((c) => c.p >= 0.5)
    .map((c) => ({ url: c.d.url, title: c.d.title ?? c.d.url, published: c.d.publishedDate?.slice(0, 10), effective: c.effective, quote: c.quote, ...(() => { const q = newAmount(c.quote), t = q ? undefined : newAmount(c.d.title ?? ""); return q ? { amount: q, amountFrom: "quote" as const } : t ? { amount: t, amountFrom: "title" as const } : {}; })(), p: c.p }))
    .sort((a, b) => a.effective.localeCompare(b.effective) || b.p - a.p)
    .slice(0, deps.max ?? 5);
}
