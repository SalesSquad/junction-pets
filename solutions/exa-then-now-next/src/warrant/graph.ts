/**
 * Warrant Compiler: an errand as a Toulmin-typed argument graph.
 *
 * The language model only maps errand facts and source quotes onto nodes. The decision is
 * computed here, by code, from node verdicts:
 *   ACCEPT      every required node verified, the rule in force at the event date, no open rebuttal
 *   NEEDS_INFO  an exception is open (neither resolved nor allocated to the receiver)
 *   REJECT      a required node failed, or the rule was not in force at the event date
 */

export type Verdict = "verified" | "failed" | "unverified";

export interface SourceAnchor {
  url: string;
  /** Verbatim text that must appear in the source when re-fetched. */
  quote: string;
  retrievedAt: string;
  contentHash?: string;
}

export interface RuleNode {
  kind: "rule";
  id: string;
  instrument: string;
  premise: string;
  source: SourceAnchor;
  /** ISO dates; the rule governs events on or after validFrom and before validUntil. */
  validFrom?: string;
  validUntil?: string;
  verdict: Verdict;
}

export interface FactNode {
  kind: "fact";
  id: string;
  statement: string;
  attestation: "user" | "public";
  value?: string | number | boolean;
  source?: SourceAnchor;
  verdict: Verdict;
}

export interface ComputationNode {
  kind: "computation";
  id: string;
  statement: string;
  fn: ComputationFn;
  /** Node ids or literals the function reads. */
  inputs: Array<string | number>;
  /** The value the sender claims; the receiver recomputes it. */
  claimed: number | boolean;
  verdict: Verdict;
}

export interface RebuttalNode {
  kind: "rebuttal";
  id: string;
  against: string;
  statement: string;
  source: SourceAnchor;
  /** resolved: shown inapplicable; allocated: burden of proof sits with the receiver; open: unknown. */
  status: "resolved" | "allocated" | "open";
  resolution?: string;
  verdict: Verdict;
}

export interface TemporalGuardNode {
  kind: "temporal";
  id: string;
  /** The rule whose validity this guard establishes. */
  rule: string;
  statement: string;
  source: SourceAnchor;
  /** The rule stops governing events on or after this date (e.g. a successor applies from it). */
  supersededFrom: string;
  verdict: Verdict;
}

export interface ClaimNode {
  kind: "claim";
  id: string;
  statement: string;
  rule: string;
  /** Facts and computations that must all verify (computations must also evaluate to true or the claimed number). */
  requires: string[];
  amount?: { value: number; currency: string };
}

export type WarrantNode = RuleNode | FactNode | ComputationNode | RebuttalNode | TemporalGuardNode | ClaimNode;

export interface WarrantGraph {
  errand: string;
  /** Date of the event the claim is about (not today). */
  eventDate: string;
  nodes: WarrantNode[];
}

export type ComputationFn = "haversineKm" | "lte" | "gte";

export type Decision = "ACCEPT" | "NEEDS_INFO" | "REJECT";

export interface Evaluation {
  decision: Decision;
  reasons: Array<{ node: string; reason: string }>;
  openQuestions: string[];
  allocatedToReceiver: string[];
}

// ---- deterministic computations (the receiver re-runs these) ----

const AIRPORTS: Record<string, [number, number]> = {
  // Coordinates are for demonstration; a production compiler cites a public airport dataset.
  HEL: [60.3172, 24.9633],
  BER: [52.3667, 13.5033],
};

export function haversineKm(a: [number, number], b: [number, number]): number {
  const R = 6371.0088;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b[0] - a[0]);
  const dLon = toRad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function compute(node: ComputationNode, values: Map<string, number | boolean | string>): number | boolean {
  const arg = (x: string | number) => (typeof x === "number" ? x : values.has(x) ? values.get(x) : x);
  switch (node.fn) {
    case "haversineKm": {
      const [from, to] = node.inputs.map((x) => String(arg(x)));
      const a = AIRPORTS[from ?? ""];
      const b = AIRPORTS[to ?? ""];
      if (!a || !b) throw new Error(`unknown airport in ${node.id}`);
      return Math.round(haversineKm(a, b));
    }
    case "lte":
      return Number(arg(node.inputs[0]!)) <= Number(arg(node.inputs[1]!));
    case "gte":
      return Number(arg(node.inputs[0]!)) >= Number(arg(node.inputs[1]!));
  }
}

// ---- evaluation ----

export function evaluate(graph: WarrantGraph): Evaluation {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const reasons: Evaluation["reasons"] = [];
  const openQuestions: string[] = [];
  const allocatedToReceiver: string[] = [];
  const values = new Map<string, number | boolean | string>();

  for (const n of graph.nodes) if (n.kind === "fact" && n.value !== undefined) values.set(n.id, n.value);
  // Computations in declaration order; each may read earlier results.
  for (const n of graph.nodes) {
    if (n.kind !== "computation") continue;
    let actual: number | boolean;
    try {
      actual = compute(n, values);
    } catch (err) {
      reasons.push({ node: n.id, reason: `computation failed: ${(err as Error).message}` });
      continue;
    }
    values.set(n.id, actual);
    const agrees = typeof n.claimed === "number" ? Math.abs(Number(actual) - n.claimed) <= Math.max(1, Math.abs(n.claimed) * 0.01) : actual === n.claimed;
    if (!agrees) reasons.push({ node: n.id, reason: `recomputed ${String(actual)}, sender claimed ${String(n.claimed)}` });
  }

  const claim = graph.nodes.find((n): n is ClaimNode => n.kind === "claim");
  if (!claim) return { decision: "REJECT", reasons: [{ node: "-", reason: "no claim node" }], openQuestions, allocatedToReceiver };

  const rule = byId.get(claim.rule);
  if (rule?.kind !== "rule") reasons.push({ node: claim.rule, reason: "claim does not reference a rule" });
  else {
    if (rule.verdict !== "verified") reasons.push({ node: rule.id, reason: `rule source ${rule.verdict}` });
    if (rule.validFrom && graph.eventDate < rule.validFrom) reasons.push({ node: rule.id, reason: `rule not yet in force on ${graph.eventDate}` });
    if (rule.validUntil && graph.eventDate >= rule.validUntil) reasons.push({ node: rule.id, reason: `rule no longer in force on ${graph.eventDate}` });
    for (const g of graph.nodes) {
      if (g.kind !== "temporal" || g.rule !== rule.id) continue;
      if (g.verdict !== "verified") reasons.push({ node: g.id, reason: `temporal guard source ${g.verdict}` });
      else if (graph.eventDate >= g.supersededFrom) reasons.push({ node: g.id, reason: `rule superseded from ${g.supersededFrom}` });
    }
  }

  for (const id of claim.requires) {
    const n = byId.get(id);
    if (!n) reasons.push({ node: id, reason: "required node missing" });
    else if (n.kind === "fact" && n.verdict !== "verified") reasons.push({ node: id, reason: `fact ${n.verdict}` });
    else if (n.kind === "computation" && values.get(id) === false) reasons.push({ node: id, reason: "condition does not hold" });
  }

  for (const n of graph.nodes) {
    if (n.kind !== "rebuttal") continue;
    if (n.verdict === "failed") reasons.push({ node: n.id, reason: "rebuttal source failed verification" });
    else if (n.status === "open") openQuestions.push(n.statement);
    else if (n.status === "allocated") allocatedToReceiver.push(n.statement);
  }

  const decision: Decision = reasons.length ? "REJECT" : openQuestions.length ? "NEEDS_INFO" : "ACCEPT";
  return { decision, reasons, openQuestions, allocatedToReceiver };
}
