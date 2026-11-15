import { markFabricated } from "./citations.ts";
import type { Council, Receipt } from "./council.ts";
import { EgressBlocked, ServiceUnavailable, type Egress, type RelayHealth } from "./egress.ts";
import { SYNTHETIC_ERRAND, SYNTHETIC_EVIDENCE } from "./fixtures.ts";
import {
  actionRiskQuestions,
  applyCitationJudgments,
  applyEvidenceJudgments,
  citationQuestions,
  decideRoute,
  evidenceQuestions,
  HANDLERS,
  routeQuestions,
  type JevAnswers,
  type JevQuestions,
} from "./judge.ts";
import type { LocalModel } from "./localModel.ts";
import { draftDeterministic, extractFactsDeterministic, judgeEvidenceDeterministic, routeDeterministic } from "./offline.ts";
import type { Claim, Draft, Evidence, Handler, LocalFacts, Provenance, TimelineEvent } from "./types.ts";

export interface OutcomeLedger {
  bonus(domain: string): number;
  record(domains: string[], approved: boolean): Promise<void>;
}

export interface ButlerDeps {
  council: Council;
  egress: Egress;
  model: LocalModel;
  health: RelayHealth;
  outcomes: OutcomeLedger;
  emit: (event: TimelineEvent) => void;
}

export interface ButlerRun {
  errand: string;
  handler: Handler;
  facts: LocalFacts;
  evidence: Evidence[];
  dropped: Array<{ evidence: Evidence; reason: string }>;
  draft?: Draft;
  risk?: { sideEffect: number; blastRadius: number; provenance: Provenance };
  stoppedReason?: string;
}

const now = () => new Date().toISOString();

/** What should rank first for each errand type (Exa's MCP search takes an explicit objective). */
const SEARCH_OBJECTIVES: Record<Handler, string> = {
  rent_increase: "Find the current official rules on rent increases and notice periods that apply to this tenant; prefer government, regulator or court sources; exclude forums and advertisers.",
  travel_disruption: "Find the current official passenger-rights rules, compensation amounts and claim procedure for this disruption; prefer regulator, government and operator pages.",
  benefits_check: "Find official eligibility rules, amounts and application steps for benefits that may apply; prefer government and agency pages.",
  contract_review: "Find official consumer or tenancy rules relevant to the clauses in question; prefer government and regulator guidance.",
  general_errand: "Find current, authoritative pages that let the user complete this errand, with concrete steps, prices or deadlines.",
};

async function judge(
  deps: ButlerDeps,
  state: object,
  questions: JevQuestions,
  subject: string,
): Promise<{ answers: JevAnswers; provenance: Provenance } | { blocked: Receipt } | null> {
  if (!deps.health.typesafe || Object.keys(questions).length === 0) return null;
  try {
    const { data } = await deps.egress<{ answers: JevAnswers }>("typesafe.judge", "/api/typesafe/judge", { state, questions }, subject);
    return { answers: data.answers, provenance: "LIVE" };
  } catch (err) {
    if (err instanceof EgressBlocked) {
      deps.emit({ at: now(), step: subject, detail: `TypeSafe judgment blocked by the council (receipt #${err.receipt.seq}); nothing was sent, using on-device rules.`, provenance: "OFFLINE_DETERMINISTIC", status: "blocked" });
      return { blocked: err.receipt };
    }
    if (err instanceof ServiceUnavailable) return null;
    deps.emit({ at: now(), step: subject, detail: `Judgment failed: ${(err as Error).message}`, provenance: "LIVE", status: "error" });
    return null;
  }
}

export async function runErrand(deps: ButlerDeps, errand: string, documentText: string): Promise<ButlerRun> {
  const { emit, model } = deps;

  // 1. Read the user's own material on the device.
  const deterministic = extractFactsDeterministic(errand, documentText);
  let facts: LocalFacts = deterministic;
  if (model.ready) {
    const extracted = await model.json<{ jurisdiction?: string; topic?: string; amounts?: string[]; dates?: string[] }>(
      "You extract facts for a personal errand assistant. Use only what the text states.",
      `Errand: ${errand}\n\nUser document:\n${documentText.slice(0, 6000)}`,
      {
        type: "object",
        properties: {
          jurisdiction: { type: "string", description: "Country and city the errand concerns, if stated" },
          topic: { type: "string" },
          amounts: { type: "array", items: { type: "string" } },
          dates: { type: "array", items: { type: "string" } },
        },
      },
    );
    if (extracted) {
      facts = {
        jurisdiction: extracted.jurisdiction || undefined,
        topic: extracted.topic || undefined,
        amounts: extracted.amounts?.length ? extracted.amounts : deterministic.amounts,
        dates: extracted.dates?.length ? extracted.dates : deterministic.dates,
        counterpartyEmail: deterministic.counterpartyEmail,
        provenance: "LIVE",
      };
    }
  }
  emit({
    at: now(),
    step: "Read on device",
    detail: `${facts.amounts.length} amounts, ${facts.dates.length} dates${facts.jurisdiction ? `, place: ${facts.jurisdiction}` : ""}. The document stays on this device.`,
    provenance: facts.provenance,
    status: "ok",
  });

  // 2. Route the errand (TypeSafe Jev choice + companion checks).
  const routed = await judge(deps, { errand }, routeQuestions(), "Route errand");
  let routeAnswers = routeDeterministic(errand);
  let routeProv: Provenance = "OFFLINE_DETERMINISTIC";
  if (routed && "answers" in routed) [routeAnswers, routeProv] = [routed.answers, routed.provenance];
  const route = decideRoute(routeAnswers);
  emit({
    at: now(),
    step: "Route",
    detail: `${route.handler} (p=${route.p.toFixed(2)}, in scope ${route.inScope.toFixed(2)}, needs live web ${route.needsWeb.toFixed(2)})${route.accepted ? "" : " — low certainty, the user should confirm"}`,
    provenance: routeProv,
    status: route.accepted ? "ok" : "warn",
  });
  const run: ButlerRun = { errand, handler: route.handler, facts, evidence: [], dropped: [] };
  if (route.inScope < 0.3) {
    run.stoppedReason = "This request is outside what the butler should do.";
    return run;
  }

  // 3. Search the live web with Exa.
  let evidence: Evidence[] = [];
  if (deps.health.exa) {
    const query = [errand, facts.jurisdiction].filter(Boolean).join(" — ");
    try {
      const { data } = await deps.egress<{ results: Array<Omit<Evidence, "domain" | "provenance">> }>(
        "exa.search",
        "/api/exa/search",
        { query, objective: SEARCH_OBJECTIVES[route.handler], type: "auto", numResults: 8 },
        "Search the web",
      );
      evidence = data.results.map((r) => ({ ...r, domain: hostOf(r.url), provenance: "LIVE" as const }));
      emit({ at: now(), step: "Search (Exa)", detail: `${evidence.length} results with highlights${deps.health.exaMode === "mcp-keyless" ? " (keyless MCP tier)" : ""}`, provenance: "LIVE", status: "ok" });
    } catch (err) {
      if (err instanceof EgressBlocked) {
        emit({ at: now(), step: "Search (Exa)", detail: `Blocked by the permission council (receipt #${err.receipt.seq}). Nothing was sent.`, provenance: "LIVE", status: "blocked" });
        run.stoppedReason = "Web search is revoked in the council.";
        return run;
      }
      emit({ at: now(), step: "Search (Exa)", detail: (err as Error).message, provenance: "LIVE", status: "error" });
      run.stoppedReason = "Search failed.";
      return run;
    }
  } else if (errand.trim() === SYNTHETIC_ERRAND) {
    evidence = SYNTHETIC_EVIDENCE;
    emit({ at: now(), step: "Search", detail: "Exa key not configured: replaying the fictional sample (example.org-style sources).", provenance: "SYNTHETIC", status: "warn" });
  } else {
    emit({ at: now(), step: "Search", detail: "Exa is not configured on the relay. Add EXA_API_KEY, or run the synthetic demo.", provenance: "OFFLINE_DETERMINISTIC", status: "error" });
    run.stoppedReason = "No search provider configured.";
    return run;
  }

  // 4. Judge every result: usable, authoritative, injection, new information.
  const knownFacts = [errand, ...facts.amounts, ...facts.dates, facts.jurisdiction ?? ""].filter(Boolean);
  const judged = await judge(
    deps,
    {
      errand,
      known_facts: knownFacts,
      results: evidence.map((e) => ({ title: e.title, domain: e.domain, published: e.publishedDate ?? null, text: e.highlights.join(" … ") })),
    },
    evidenceQuestions(evidence.length),
    "Judge evidence",
  );
  let evidenceAnswers = judgeEvidenceDeterministic(evidence);
  let evidenceProv: Provenance = "OFFLINE_DETERMINISTIC";
  if (judged && "answers" in judged) [evidenceAnswers, evidenceProv] = [judged.answers, judged.provenance];
  const { kept, dropped } = applyEvidenceJudgments(evidence, evidenceAnswers, (d) => deps.outcomes.bonus(d));
  run.evidence = kept.map((e) => ({ ...e, judgment: e.judgment && { ...e.judgment, provenance: evidenceProv } }));
  run.dropped = dropped;
  emit({
    at: now(),
    step: "Judge evidence",
    detail: `${kept.length} kept, ${dropped.length} dropped${dropped.length ? ` (${dropped.map((d) => d.reason.split(" (")[0]).join(", ")})` : ""}`,
    provenance: evidenceProv,
    status: kept.length ? "ok" : "warn",
  });
  if (!kept.length) {
    run.stoppedReason = "No usable evidence.";
    return run;
  }

  // 5. Draft the answer and the action on the device.
  let draft = draftDeterministic(route.handler, errand, facts, kept);
  if (model.ready) {
    const top = kept.slice(0, 5);
    const generated = await model.json<{ summary: string; claims: Array<{ text: string; source_id: string; quote: string }>; action: { subject: string; body: string } }>(
      "You are a careful personal errand assistant. Use only the sources given. Every claim must cite one source id and copy a supporting quote verbatim from that source's text.",
      `Errand (${HANDLERS[route.handler]}): ${errand}\nKnown facts: ${knownFacts.join("; ")}\n\nSources:\n${top
        .map((e) => `id=${e.id} (${e.domain}${e.publishedDate ? `, ${e.publishedDate}` : ""}): ${e.highlights.join(" … ")}`)
        .join("\n")}\n\nWrite a short summary, 2-4 claims, and a message the user could send to move the errand forward.`,
      {
        type: "object",
        required: ["summary", "claims", "action"],
        properties: {
          summary: { type: "string" },
          claims: { type: "array", items: { type: "object", required: ["text", "source_id", "quote"], properties: { text: { type: "string" }, source_id: { type: "string" }, quote: { type: "string" } } } },
          action: { type: "object", required: ["subject", "body"], properties: { subject: { type: "string" }, body: { type: "string" } } },
        },
      },
    );
    if (generated?.claims?.length) {
      draft = {
        summary: generated.summary,
        claims: generated.claims.map((c) => ({ text: c.text, sourceId: c.source_id, quote: c.quote })),
        action: { kind: "email", to: facts.counterpartyEmail, subject: generated.action.subject, body: generated.action.body },
        provenance: "LIVE",
      };
    }
  }
  // No on-device model: a hosted writer may draft, from the question and the public sources only. The user's document
  // and the facts read from it are not sent. The council decides (capability "writer.hosted") and logs it.
  let drafter = model.ready ? "on device" : "on device (templates)";
  if (!model.ready && deps.health.writer) {
    const top = kept.slice(0, 5);
    try {
      const { data } = await deps.egress<{ json: { summary?: string; claims?: Array<{ text: string; source_id: string; quote: string }>; action?: { subject: string; body: string } } | null }>(
        "writer.hosted",
        "/api/write",
        {
          system: "You are a careful personal errand assistant. Use only the sources given. Answer the person's question directly in the summary. Every claim must cite one source id and copy a supporting quote verbatim (a contiguous span) from that source's text. Then write a short message the person could send to the right recipient to move the errand forward. Write in the language of the errand.",
          user: `Errand (${HANDLERS[route.handler]}): ${errand}\n\nSources:\n${top.map((e) => `id=${e.id} (${e.domain}${e.publishedDate ? `, ${e.publishedDate}` : ""}): ${e.highlights.join(" … ").slice(0, 1800)}`).join("\n")}\n\nReturn JSON only: {"summary": "...", "claims": [{"text": "...", "source_id": "...", "quote": "..."}], "action": {"subject": "...", "body": "..."}} with 2-4 claims.`,
        },
        "draft from the question and public sources",
      );
      const g = data.json;
      const ids = new Set(top.map((e) => e.id));
      const claims = (g?.claims ?? []).filter((c) => c && typeof c.text === "string" && typeof c.quote === "string" && ids.has(String(c.source_id)));
      if (g && claims.length) {
        draft = { summary: String(g.summary ?? ""), claims: claims.map((c) => ({ text: c.text, sourceId: String(c.source_id), quote: c.quote })), action: { kind: "email", to: facts.counterpartyEmail, subject: String(g.action?.subject ?? ""), body: String(g.action?.body ?? "") }, provenance: "LIVE" };
        drafter = "by the hosted writer (question and public sources only)";
      }
    } catch {
      /* blocked by the council or unavailable: the template draft stands */
    }
  }
  emit({ at: now(), step: `Draft ${drafter}`, detail: `${draft.claims.length} sourced claims and a message draft`, provenance: draft.provenance, status: "ok" });

  // 6. Check every citation: exact quote first, then Jev for support.
  let claims: Claim[] = markFabricated(draft.claims, kept);
  const cited = await judge(deps, { claims: claims.map((c) => ({ text: c.text, quote: c.quote })) }, citationQuestions(claims), "Check citations");
  if (cited && "answers" in cited) claims = applyCitationJudgments(claims, cited.answers);
  else claims = claims.map((c) => (c.verdict === "fabricated" ? c : c.quote === c.text ? { ...c, verdict: "supported" as const, probability: 1, needsReview: false } : { ...c, verdict: "unchecked" as const, needsReview: true }));
  const fabricated = claims.filter((c) => c.verdict === "fabricated").length;
  const review = claims.filter((c) => c.needsReview).length;
  emit({
    at: now(),
    step: "Check citations",
    detail: `${claims.length - review} verified, ${review} need review${fabricated ? `, ${fabricated} quote(s) not found in the source` : ""}`,
    provenance: cited && "answers" in cited ? "LIVE" : "OFFLINE_DETERMINISTIC",
    status: review ? "warn" : "ok",
  });
  run.draft = { ...draft, claims };

  // 7. Explain the stakes of the action (informative only; sending always needs a click).
  const risk = await judge(
    deps,
    // Context minimisation: Jev sees the action type and purpose, never the drafted text,
    // which can contain private details from the user's document.
    { action: { kind: draft.action.kind, purpose: HANDLERS[route.handler] } },
    actionRiskQuestions(),
    "Assess action risk",
  );
  if (risk && "answers" in risk) {
    const se = risk.answers.side_effect;
    const br = risk.answers.blast_radius;
    run.risk = { sideEffect: se?.type === "noul" ? se.noul : 1, blastRadius: br?.type === "score" ? br.score : 1, provenance: "LIVE" };
  } else {
    run.risk = { sideEffect: draft.action.kind === "email" ? 1 : 0, blastRadius: 1, provenance: "OFFLINE_DETERMINISTIC" };
  }
  emit({ at: now(), step: "Ready for approval", detail: "Nothing is sent until you approve it.", provenance: run.risk.provenance, status: "ok" });
  return run;
}

export async function approveAction(deps: Pick<ButlerDeps, "council" | "outcomes">, run: ButlerRun): Promise<{ allowed: boolean; receipt: Receipt; mailto?: string }> {
  const action = run.draft?.action;
  if (!action) throw new Error("Nothing to approve");
  const payload = { to: action.to ?? "", subject: action.subject ?? "", body: action.body };
  const { allowed, receipt } = await deps.council.checkAction("action.send", `Send "${action.subject ?? "message"}"`, true, payload);
  if (!allowed) return { allowed, receipt };
  await deps.outcomes.record(citedDomains(run), true);
  const mailto = `mailto:${encodeURIComponent(action.to ?? "")}?subject=${encodeURIComponent(action.subject ?? "")}&body=${encodeURIComponent(action.body)}`;
  return { allowed, receipt, mailto };
}

export async function rejectAction(deps: Pick<ButlerDeps, "council" | "outcomes">, run: ButlerRun): Promise<Receipt> {
  await deps.outcomes.record(citedDomains(run), false);
  return deps.council.recordRejected("action.send", `Rejected "${run.draft?.action.subject ?? "message"}"`);
}

function citedDomains(run: ButlerRun): string[] {
  const ids = new Set(run.draft?.claims.map((c) => c.sourceId));
  return [...new Set(run.evidence.filter((e) => ids.has(e.id)).map((e) => e.domain))];
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
