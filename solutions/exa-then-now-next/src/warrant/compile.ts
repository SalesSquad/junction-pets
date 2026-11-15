import type { RuleNode } from "./graph.ts";
import {
  analyseTiers,
  extractFromAnswerLane,
  extractPremises,
  extractQuantities,
  groundedCitationQuery,
  kindHints,
  threeWay,
  triangulateQuantity,
  type Extraction,
  type FetchFn,
  type LaneResult,
  type Premise,
  type SearchFn,
  type ThreeWayStatus,
  type Triangulation,
} from "./lanes.ts";
import { isLegalTextUrl } from "./sources.ts";
import type { DecisionProvider, JudgmentReceipt } from "../decide/decide.ts";
import { chooseOutcome, quarantine, sameRule, verifyClaim } from "../decide/compilerDecisions.ts";
import { outcomeCandidates } from "./lanes.ts";

/**
 * Two-lane compilation with several premises and a three-way check:
 *   answer lane -> premises (threshold + outcome, each grounded in a retrieved sentence)
 *   -> authority lane (citation query from the primary premise's sentence)
 *   -> legal texts fetched once -> every premise triangulated
 *   -> three-way check against an optional model prior
 *   -> GROUNDED only if every premise is confirmed by legal text; otherwise NEEDS_INFO with reasons.
 */
export interface PremiseCheck {
  premise: Premise;
  triangulation: Triangulation;
  status: ThreeWayStatus;
  note: string;
  rule?: RuleNode;
}

export interface TwoLaneResult {
  question: string;
  /** The date whose law the claim relies on (the event date). Signed; the receiver checks pinned versions against it. */
  lawAsOf?: string;
  answerLane: LaneResult[];
  premises: PremiseCheck[];
  /** The primary (first outcome) premise, kept for callers of the single-premise API. */
  extraction: Extraction;
  citationQuery: string | null;
  authorityLane: LaneResult[];
  legalUrls: string[];
  triangulation: Triangulation;
  outcome: "GROUNDED" | "NEEDS_INFO";
  reasons: string[];
  rule?: RuleNode;
  /** A tiered rule the question does not settle: ask this instead of guessing. */
  clarify?: { question: string; options: string[]; sourceUrl: string };
  /** Typed judgments the compiler relied on (empty without a decision provider). */
  judgments: JudgmentReceipt[];
  /** Answer-lane passages dropped because a judge read them as instructions to the agent. */
  quarantined: Array<{ url: string; p: number }>;
  /**
   * The model prior (a drafted answer) checked against the answer lane with the truth table.
   * Verified = usable as a fast, evidence-quoted answer while the legal-text check runs; it is
   * never GROUNDED on its own. Present when both `prior` and `decisions` are given.
   */
  draft?: { text: string; verified: boolean; quote?: string; url?: string; checked: number };
}

export interface CompileOptions {
  /** Optional model prior: text a model wrote from memory (e.g. a draft answer). Its numbers are compared, never trusted. */
  prior?: (question: string) => Promise<string>;
  maxLegalPages?: number;
  now?: Date;
  /**
   * Optional typed judge (TypeSafe Jev, OpenAI Decisions). It can quarantine injected passages,
   * pick the outcome among code-found candidates and veto a verbatim match from another rule.
   * It never upgrades a premise: GROUNDED still needs every quote verbatim in a legal text.
   */
  decisions?: { provider: DecisionProvider; quarantine?: boolean; outcome?: boolean; veto?: boolean };
}

const ANSWER_OBJECTIVE = "Find pages that answer this question with the specific rule, amount or deadline that applies.";
const AUTHORITY_OBJECTIVE = "Find the official legal text (legislation, regulation or court decision) that this passage cites.";

export async function compileTwoLane(question: string, search: SearchFn, fetch: FetchFn, opts: CompileOptions = {}): Promise<TwoLaneResult> {
  const now = opts.now ?? new Date();
  const reasons: string[] = [];
  const judgments: JudgmentReceipt[] = [];
  const dec = opts.decisions;
  let answerLane = await search(question, ANSWER_OBJECTIVE);
  let quarantined: TwoLaneResult["quarantined"] = [];
  if (dec && dec.quarantine !== false) {
    const q = await quarantine(answerLane, dec.provider, { at: now });
    answerLane = q.kept;
    quarantined = q.dropped;
    judgments.push(...q.receipts);
    if (q.dropped.length) reasons.push(`quarantined ${q.dropped.length} passage(s) that address the agent: ${q.dropped.map((d) => d.url).join(", ")}`);
  }
  const premises = extractPremises(answerLane, question);
  if (dec && dec.outcome !== false) {
    const cands = outcomeCandidates(answerLane, question);
    const pick = await chooseOutcome(question, cands, dec.provider, { at: now });
    judgments.push(...pick.receipts);
    const c = cands[pick.index];
    if (c) {
      const chosen: Premise = { role: "outcome", quantity: c.quantity, sentence: c.sentence, sourceUrl: c.url, support: c.support };
      const same = premises.findIndex((p) => p.role === "outcome" && p.quantity.kind === c.quantity.kind && p.quantity.unit === c.quantity.unit && p.quantity.value === c.quantity.value);
      if (same >= 0) premises.splice(same, 1);
      const firstOutcome = premises.findIndex((p) => p.role === "outcome");
      premises.splice(firstOutcome < 0 ? premises.length : firstOutcome, 0, chosen);
    }
  }
  // Tiered outcome rules: resolve from what the question states, or ask instead of guessing.
  let pendingClarify: TwoLaneResult["clarify"];
  const ambiguous = new Set<Premise>();
  const thresholds = premises.filter((p) => p.role === "threshold").map((p) => p.quantity);
  for (const p of premises.filter((p) => p.role === "outcome")) {
    const tiers = analyseTiers(answerLane, p, question, thresholds);
    if (tiers?.resolved) p.quantity = tiers.resolved.value;
    else if (tiers?.clarify) {
      ambiguous.add(p);
      pendingClarify ??= { ...tiers.clarify, sourceUrl: tiers.sourceUrl };
    }
  }
  const primary = premises.find((p) => p.role === "outcome") ?? premises[0];
  const base = extractFromAnswerLane(answerLane, kindHints(question));
  const extraction: Extraction = primary
    ? { ...base, quantity: primary.quantity, sentence: primary.sentence, sourceUrl: primary.sourceUrl, support: primary.support }
    : base;
  const citationQuery = groundedCitationQuery(extraction);
  const empty = { question, answerLane, extraction, citationQuery, authorityLane: [], legalUrls: [], triangulation: { status: "not_found" } as Triangulation, judgments, quarantined };
  if (!citationQuery || !primary) {
    reasons.push("no answer-lane source states a decisive amount or period");
    return { ...empty, premises: [], outcome: "NEEDS_INFO", reasons };
  }

  const [authorityLane, priorText] = await Promise.all([search(citationQuery, AUTHORITY_OBJECTIVE), opts.prior ? opts.prior(question).catch(() => "") : Promise.resolve("")]);
  let draft: TwoLaneResult["draft"];
  if (dec && priorText) {
    const v = await verifyClaim(priorText, answerLane, dec.provider, { at: now });
    judgments.push(...v.receipts);
    draft = { text: priorText, verified: v.verified.length > 0, quote: v.verified[0]?.sentence, url: v.verified[0]?.url, checked: v.checked.length };
  }
  const legalUrls = authorityLane.map((r) => r.url).filter(isLegalTextUrl);
  if (!legalUrls.length) reasons.push("authority lane returned no legal text");

  const pages: Array<{ url: string; text: string }> = [];
  for (const url of legalUrls.slice(0, opts.maxLegalPages ?? 2)) {
    try {
      pages.push({ url, text: await fetch(url) });
    } catch {
      /* unreadable page: counts as not found */
    }
  }
  const prior = extractQuantities(priorText);
  const checks: PremiseCheck[] = premises.map((premise) => {
    const triangulation = triangulateQuantity(premise.quantity, pages, premise.sentence);
    const { status, note } = threeWay(premise, triangulation, prior);
    const rule: RuleNode | undefined =
      triangulation.status === "agree"
        ? {
            kind: "rule",
            id: `rule-${premise.role}-${premise.quantity.kind}`,
            instrument: extraction.instrument ?? "unidentified instrument",
            premise: premise.sentence,
            source: { url: triangulation.url, quote: triangulation.quote, retrievedAt: now.toISOString() },
            verdict: "verified",
          }
        : undefined;
    return { premise, triangulation, status, note, rule };
  });
  // Veto only: a judge can say a verbatim match is from another rule; it cannot confirm anything.
  if (dec && dec.veto !== false) {
    const agreed = checks.filter((c) => c.triangulation.status === "agree");
    const verdicts = await sameRule(
      agreed.map((c) => ({ mention: c.premise.quantity.text, explainer: c.premise.sentence, clause: c.triangulation.status === "agree" ? c.triangulation.quote : "" })),
      dec.provider,
      { at: now },
    );
    verdicts.forEach((v, i) => {
      judgments.push(...v.receipts);
      const c = agreed[i]!;
      if (!v.veto) return;
      c.status = "unverified";
      c.note = `a judge reads the legal clause as using ${c.premise.quantity.text} for another rule (p same rule = ${v.p.toFixed(2)})`;
      c.rule = undefined;
    });
  }
  // Each threshold must be confirmed; the outcome alternatives pass if at least one is confirmed.
  const confirmed = (c: PremiseCheck) => c.status.startsWith("confirmed");
  const outcomes = checks.filter((c) => c.premise.role === "outcome");
  const outcomeOk = outcomes.some(confirmed);
  for (const c of checks) {
    if (confirmed(c)) continue;
    if (c.premise.role === "outcome" && outcomeOk) continue; // an alternative the legal text did not choose
    reasons.push(`${c.premise.role}: ${c.note}`);
  }
  const confirmedOutcome = outcomes.find(confirmed);
  const primaryCheck = confirmedOutcome ?? checks.find((c) => c.premise === primary)!;
  // Ask only when no unambiguous outcome alternative was confirmed by the legal text.
  const clarify = outcomes.some((c) => confirmed(c) && !ambiguous.has(c.premise)) ? undefined : pendingClarify;
  if (clarify) reasons.unshift(`tiered rule: ${clarify.question}`);
  const outcome = !clarify && checks.filter((c) => c.premise.role === "threshold").every(confirmed) && outcomeOk ? "GROUNDED" : "NEEDS_INFO";
  return {
    question,
    answerLane,
    premises: checks,
    extraction,
    citationQuery,
    authorityLane,
    legalUrls,
    triangulation: primaryCheck.triangulation,
    outcome,
    reasons,
    rule: primaryCheck.rule,
    clarify,
    judgments,
    quarantined,
    draft,
  };
}
