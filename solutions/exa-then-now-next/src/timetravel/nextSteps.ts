/**
 * "Work out what needs to happen": after the butler knows what the person is owed, it finds what is still
 * missing to act, on the live web, with Exa.
 *
 *   where     the counterparty's own page or contact for submitting the claim (so the claim has a real recipient)
 *   deadline  the time limit for making the claim
 *   day       what was reported on and around the event date that could matter (a strike, a storm, an outage):
 *             a news search bounded to those days, which no model has in its weights for a recent date
 *
 * plan     a writer model names the counterparty and writes one search per need, in the language of the
 *          country's official sites (a deterministic plan is used when no writer is available)
 * search   Exa, with highlights; the "day" search is restricted to news published around the event date
 * judge    a typed judge answers, per result, whether the document really serves that need for this situation
 * show     the best result per need: title, link, publication date and the sentence that says it
 *
 * Nothing here is law and nothing is sent anywhere: these are sourced next steps for the person to approve.
 */
import type { DecisionProvider, Question } from "../decide/decide.ts";

export type StepKind = "where" | "deadline" | "day";
export interface StepSearch { kind: StepKind; need: string; query: string }
export interface StepPlan { counterparty?: string | null; country?: string | null; searches: StepSearch[] }
export interface StepDoc { url: string; title?: string; publishedDate?: string; highlights?: string[] }
export type StepSearcher = (s: StepSearch, opts: { news: boolean; from?: string; to?: string }) => Promise<StepDoc[]>;
export interface StepFound { kind: StepKind; need: string; title: string; url: string; published?: string; quote: string; p: number }
export interface NextSteps { counterparty?: string; country?: string; steps: StepFound[]; searches: StepSearch[]; planned: "writer" | "template" }

const NEEDS: Record<StepKind, string> = {
  where: "where and how to submit the claim",
  deadline: "the time limit for making the claim",
  day: "what was reported that day that could matter (a strike, severe weather, an outage or closure)",
};
const JUDGE: Record<StepKind, string> = {
  where: "Is `document` a page or contact of `counterparty` itself, or of the authority that handles such claims, where the person in `situation` can submit the claim or complaint?",
  deadline: "Does `document` state how long a person has to make the claim in `situation`: a time limit or limitation period given as a number of days, months or years?",
  day: "Does `document` report an event on or around `date` (a strike, severe weather, an air traffic control or system failure, a closure) at the same place or operator as in `situation`, which could have caused the disruption described there? Answer no if `situation` is not about a disrupted journey, delivery or service.",
};

export const PLAN_PROMPT = (question: string, eventDate: string, right: string) => `A person describes a situation and wants what they are owed. Plan the web searches that bring their task as close to done as possible.

Situation: "${question}"
Date of the event: ${eventDate}
The right that applies: ${right || "(not identified)"}

Return JSON only:
{"counterparty": "<the company or body the person must contact, or null if not named>",
 "country": "<the country whose rules or office apply>",
 "searches": [
  {"kind": "where", "query": "<one line: find the counterparty's own claim form, complaint page or contact for this kind of claim>"},
  {"kind": "deadline", "query": "<one line: find the time limit or limitation period for making this claim in that country>"},
  {"kind": "day", "query": "<one line: find news of a strike, storm, outage or closure at that place on that date, naming the place, the operator and the date in words>"}
 ]}
Include the "day" search only if the situation is a disrupted journey, delivery or service (a cancelled or delayed flight or train, an outage); otherwise leave it out.
Write each query in the language of that country's official sites when that is not English. Name the company, the place and the right. No explanations.`;

/** A plan without a writer model: built from the right's title and the person's own words. */
export function templatePlan(question: string, eventDate: string, right: string): StepPlan {
  const words = question.replace(/\s+/g, " ").slice(0, 160);
  const short = (right.split(" — ")[1] ?? right).replace(/\(.*?\)/g, "").trim() || "compensation";
  return {
    counterparty: null,
    country: null,
    searches: [
      { kind: "where", need: NEEDS.where, query: `how to submit a claim for ${short}: official claim form or contact. ${words}` },
      { kind: "deadline", need: NEEDS.deadline, query: `time limit or limitation period to claim ${short}. ${words}` },
      ...(DISRUPTION.test(question) ? [{ kind: "day" as const, need: NEEDS.day, query: `strike, storm, outage or closure on ${eventDate}. ${words}` }] : []),
    ],
  };
}

/** A disrupted journey, delivery or service: only then does "what was reported that day" matter. */
const DISRUPTION = /flight|train|ferry|bus\b|cancel|delay|bumped|strike|outage|lento|lennon|juna|perut|myöhäs|flug|zug|verspät|annull|streik/i;
const day = (iso: string, add: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + add * 864e5).toISOString().slice(0, 10);
const clean = (s: string) => s.replace(/\s+/g, " ").trim();

export async function nextSteps(
  input: { question: string; eventDate: string; today: string; right?: string },
  deps: { plan?: (prompt: string) => Promise<unknown>; search: StepSearcher; judge: DecisionProvider },
): Promise<NextSteps> {
  const right = input.right ?? "";
  // 1. Plan. A writer's plan is used only if it has the three searches in a usable shape.
  let plan: StepPlan | undefined;
  let planned: NextSteps["planned"] = "template";
  if (deps.plan) {
    try {
      const raw = (await deps.plan(PLAN_PROMPT(input.question, input.eventDate, right))) as { counterparty?: unknown; country?: unknown; searches?: unknown } | null;
      const searches = Array.isArray(raw?.searches)
        ? (raw!.searches as Array<{ kind?: unknown; query?: unknown }>)
            .filter((s) => (s.kind === "where" || s.kind === "deadline" || s.kind === "day") && typeof s.query === "string" && s.query.trim().length >= 8)
            .map((s) => ({ kind: s.kind as StepKind, need: NEEDS[s.kind as StepKind], query: clean(String(s.query)).slice(0, 300) }))
        : [];
      const kinds = new Set(searches.map((s) => s.kind));
      // "where" and "deadline" are required; the writer leaves "day" out when nothing was disrupted.
      if (kinds.has("where") && kinds.has("deadline")) {
        plan = { counterparty: typeof raw?.counterparty === "string" ? clean(raw.counterparty).slice(0, 80) : null, country: typeof raw?.country === "string" ? clean(raw.country).slice(0, 60) : null, searches: (["where", "deadline", "day"] as StepKind[]).map((k) => searches.find((s) => s.kind === k)).filter((x): x is StepSearch => !!x) };
        planned = "writer";
      }
    } catch {
      /* fall back to the template */
    }
  }
  plan ??= templatePlan(input.question, input.eventDate, right);

  // 2. Search. The "day" search sees only news published from two days before to four days after the event
  //    (never after today), so what it returns was written when it happened.
  const found = await Promise.all(
    plan.searches.map(async (s) => {
      try {
        const news = s.kind === "day";
        const to = day(input.eventDate, 4) > input.today ? input.today : day(input.eventDate, 4);
        return { s, docs: (await deps.search(s, news ? { news, from: day(input.eventDate, -2), to } : { news })).slice(0, 5) };
      } catch {
        return { s, docs: [] as StepDoc[] };
      }
    }),
  );

  // 3. Judge each result against its need; keep the best per need (two for the day).
  const steps: StepFound[] = [];
  for (const { s, docs } of found) {
    const q: Question[] = [{ kind: "yesno", name: "serves", instructions: JUDGE[s.kind] }];
    const judged = await Promise.all(
      docs
        .filter((d) => /^https?:\/\//i.test(d.url) && (d.highlights?.length ?? 0) > 0)
        .map(async (d) => {
          const quote = clean(d.highlights![0]!).slice(0, 320);
          try {
            const r = await deps.judge.decide({ situation: input.question, date: input.eventDate, counterparty: plan!.counterparty ?? "the company or body concerned", document: `${d.title ?? ""}. ${clean(d.highlights!.join(" ")).slice(0, 900)} (${d.url})` }, q);
            return { d, quote, p: r.answers[0]?.p ?? 0 };
          } catch {
            return { d, quote, p: 0 };
          }
        }),
    );
    judged
      .filter((x) => x.p >= (s.kind === "day" ? 0.6 : 0.5))
      .sort((a, b) => b.p - a.p)
      .slice(0, s.kind === "day" ? 2 : 1)
      .forEach((x) => steps.push({ kind: s.kind, need: s.need, title: clean(x.d.title ?? x.d.url).slice(0, 160), url: x.d.url, published: x.d.publishedDate?.slice(0, 10), quote: x.quote, p: x.p }));
  }
  return { ...(plan.counterparty ? { counterparty: plan.counterparty } : {}), ...(plan.country ? { country: plan.country } : {}), steps, searches: plan.searches, planned };
}
