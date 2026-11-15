/** How a result was produced. Every value shown in the UI carries one. */
export type Provenance = "LIVE" | "REPLAYED" | "SYNTHETIC" | "OFFLINE_DETERMINISTIC";

/** Capabilities the permission council governs. Egress capabilities send data off the device. */
export type Capability =
  | "exa.search"
  | "exa.contents"
  | "typesafe.judge"
  | "writer.hosted"
  | "action.send";

export type GrantMode = "allow" | "ask" | "deny";

export type Handler =
  | "rent_increase"
  | "travel_disruption"
  | "benefits_check"
  | "contract_review"
  | "general_errand";

export interface Evidence {
  id: string;
  title: string;
  url: string;
  domain: string;
  publishedDate?: string;
  highlights: string[];
  provenance: Provenance;
  judgment?: EvidenceJudgment;
  rank?: number;
}

export interface EvidenceJudgment {
  usable: number;
  primary: number;
  injection: number;
  novel: number;
  provenance: Provenance;
}

export type CitationVerdict = "supported" | "contradicts" | "says_nothing" | "fabricated" | "unchecked";

export interface Claim {
  text: string;
  sourceId: string;
  quote: string;
  verdict?: CitationVerdict;
  probability?: number;
  needsReview?: boolean;
}

export interface ActionDraft {
  kind: "email" | "none";
  to?: string;
  subject?: string;
  body: string;
}

export interface Draft {
  summary: string;
  claims: Claim[];
  action: ActionDraft;
  provenance: Provenance;
}

export interface LocalFacts {
  jurisdiction?: string;
  amounts: string[];
  dates: string[];
  counterpartyEmail?: string;
  topic?: string;
  provenance: Provenance;
}

export interface TimelineEvent {
  at: string;
  step: string;
  detail: string;
  provenance: Provenance;
  status: "ok" | "blocked" | "warn" | "error";
}
