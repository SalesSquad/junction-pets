import type { ActionDraft, Claim, Draft, Evidence, Handler, LocalFacts } from "./types.ts";
import type { JevAnswers } from "./judge.ts";
import { HANDLERS } from "./judge.ts";

/**
 * Deterministic fallbacks used when no on-device model or no judgment service is
 * available. Everything produced here is labelled OFFLINE_DETERMINISTIC in the UI.
 */

const AMOUNT = /(?:[€$£]\s?\d[\d\s.,]*\d|\d[\d\s.,]*\s?(?:€|eur|euros?|usd|\$|gbp|£)|\d+(?:[.,]\d+)?\s?%)/gi;
const DATE =
  /\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s\d{4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s\d{1,2},?\s\d{4})\b/gi;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;

export function extractFactsDeterministic(errand: string, documentText: string): LocalFacts {
  const text = `${errand}\n${documentText}`;
  const uniq = (xs: string[]) => [...new Set(xs.map((x) => x.trim()))].slice(0, 8);
  return {
    amounts: uniq(text.match(AMOUNT) ?? []),
    dates: uniq(text.match(DATE) ?? []),
    // Kept on the device for the action's "to" field; never sent anywhere.
    counterpartyEmail: documentText.match(EMAIL)?.[0],
    provenance: "OFFLINE_DETERMINISTIC",
  };
}

const KEYWORDS: Array<[Handler, RegExp]> = [
  ["rent_increase", /\b(rent|landlord|lease|tenan|vuokra)/i],
  ["travel_disruption", /\b(flight|delay|cancel|train|airline|luggage|baggage|lento)/i],
  ["benefits_check", /\b(benefit|subsid|allowance|grant|refund|tax credit|tuki|etuus)/i],
  ["contract_review", /\b(contract|terms|agreement|clause|sopimus)/i],
];

export function routeDeterministic(errand: string): JevAnswers {
  const hit = KEYWORDS.find(([, re]) => re.test(errand));
  const choice: Handler = hit?.[0] ?? "general_errand";
  const probabilities = Object.fromEntries(Object.keys(HANDLERS).map((k) => [k, k === choice ? 0.75 : 0.0625]));
  return {
    handler: { type: "choice", choice, confidence: 0.75, probabilities },
    in_scope: { type: "noul", noul: 0.8 },
    needs_fresh_web: { type: "noul", noul: 0.8 },
  };
}

const PRIMARY_DOMAIN = /(\.gov(\.[a-z]{2})?|\.gouv\.|\.gob\.|\.govt\.|europa\.eu|\.int|\.mil|kela\.fi|vero\.fi|suomi\.fi|finlex\.fi)$/i;
const INJECTION = /(ignore (all |any )?(previous|prior) instructions|you are (now )?an? (ai|assistant)|system prompt|as an ai language model)/i;

export function judgeEvidenceDeterministic(evidence: Evidence[]): JevAnswers {
  const a: JevAnswers = {};
  evidence.forEach((e, i) => {
    const text = e.highlights.join(" ");
    a[`r${i}_usable`] = { type: "noul", noul: /\d/.test(text) ? 0.65 : 0.5 };
    a[`r${i}_primary`] = { type: "noul", noul: PRIMARY_DOMAIN.test(e.domain) ? 0.85 : 0.3 };
    a[`r${i}_injection`] = { type: "noul", noul: INJECTION.test(text) ? 0.95 : 0.02 };
    a[`r${i}_novel`] = { type: "noul", noul: 0.5 };
  });
  return a;
}

/** Extractive draft: every claim is a sentence copied from a source, so its quote is exact. */
export function draftDeterministic(handler: Handler, errand: string, facts: LocalFacts, evidence: Evidence[]): Draft {
  const claims: Claim[] = evidence.slice(0, 3).flatMap((e) => {
    const sentence = bestSentence(e.highlights.join("\n"));
    return sentence ? [{ text: sentence, quote: sentence, sourceId: e.id }] : [];
  });
  const cites = claims.map((c, i) => `[${i + 1}] ${evidence.find((e) => e.id === c.sourceId)?.url ?? ""}`).join("\n");
  const points = claims.map((c, i) => `- ${c.text} [${i + 1}]`).join("\n");
  return {
    summary: claims.length
      ? `What the strongest sources say about your errand (${(HANDLERS[handler].split(",")[0] ?? handler).toLowerCase()}):`
      : "No usable sources were found. Try adding the country or city to the errand.",
    claims,
    action: actionTemplate(handler, errand, facts, points, cites),
    provenance: "OFFLINE_DETERMINISTIC",
  };
}

function actionTemplate(handler: Handler, errand: string, facts: LocalFacts, points: string, cites: string): ActionDraft {
  const to = facts.counterpartyEmail;
  const body = (opening: string, ask: string) =>
    `Hello,\n\n${opening}\n\n${points || "(no sourced points yet)"}\n\n${ask}\n\nKind regards,\n\nSources:\n${cites}`;
  switch (handler) {
    case "rent_increase":
      return { kind: "email", to, subject: "Question about the proposed rent increase", body: body("Regarding the rent increase you proposed, I checked the rules that apply:", "Could you confirm the legal basis and calculation for the increase, in writing?") };
    case "travel_disruption":
      return { kind: "email", to, subject: "Compensation claim for disrupted journey", body: body("I am claiming compensation for my disrupted journey. The applicable rules state:", "Please process my claim and confirm the amount and timeline.") };
    case "benefits_check":
      return { kind: "email", to, subject: "Question about eligibility", body: body("I would like to confirm my eligibility. Based on the published rules:", "Could you confirm whether I qualify and which documents you need?") };
    case "contract_review":
      return { kind: "email", to, subject: "Questions before signing", body: body("Before signing, I would like to clarify a few points:", "Could you clarify these points before we proceed?") };
    default:
      return { kind: "email", to, subject: errand.slice(0, 80), body: body("Following up on this:", "Could you help me with the next step?") };
  }
}

/**
 * Pick the most informative sentence in a highlight, copied verbatim so its quote still
 * matches the source: skip markdown headings, table rows and questions; prefer sentences
 * with numbers (amounts, hours, deadlines).
 */
export function bestSentence(text: string): string {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("|") && !/^#{1,6}\s/.test(l) && !/^[-*]\s*$/.test(l))
    .map((l) => l.replace(/^[-*]\s+/, ""));
  const sentences = lines.flatMap((l) => l.match(/[^.!?]+[.!?]+(?=\s|$)/g) ?? [l]).map((s) => s.trim());
  const candidates = sentences.filter((s) => s.length >= 40 && s.length <= 320 && !s.endsWith("?"));
  const withNumber = candidates.find((s) => /\d/.test(s));
  return (withNumber ?? candidates[0] ?? sentences[0] ?? "").trim();
}
