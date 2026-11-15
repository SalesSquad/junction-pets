import assert from "node:assert/strict";
import { test } from "node:test";
import { evaluate, haversineKm, type WarrantGraph, type WarrantNode } from "../src/warrant/graph.ts";
import { applicationDate, citationQueries } from "../src/warrant/queries.ts";
import { challengeIndices, commit, detectionProbability, prove, verifyInclusion, type TranscriptLeaf } from "../src/warrant/transcript.ts";

const now = "2026-11-14T05:00:00Z";
const EURLEX_261 = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32004R0261";
const EURLEX_2202 = "https://eur-lex.europa.eu/eli/reg/2026/2202/oj/eng";
const distance = Math.round(haversineKm([60.3172, 24.9633], [52.3667, 13.5033]));

/** EU flight delay, Helsinki -> Berlin, 4 hours late. Quotes are the texts the compiler anchors to. */
function eu261(overrides: Partial<Record<string, Partial<WarrantNode>>> = {}, eventDate = "2026-11-06"): WarrantGraph {
  const nodes: WarrantNode[] = [
    { kind: "rule", id: "r261", instrument: "Regulation (EC) No 261/2004", premise: "Art. 7(1)(a): EUR 250 for flights of 1 500 km or less (arrival delay of 3 h or more per CJEU case law)", source: { url: EURLEX_261, quote: "EUR 250 for all flights of 1500 kilometres or less", retrievedAt: now }, validFrom: "2005-02-17", verdict: "verified" },
    { kind: "temporal", id: "t2202", rule: "r261", statement: "Regulation (EU) 2026/2202 replaces the regime and applies from 23 October 2027", source: { url: EURLEX_2202, quote: "It shall apply from 23 October 2027.", retrievedAt: now }, supersededFrom: "2027-10-23", verdict: "verified" },
    { kind: "fact", id: "from", statement: "Departure airport", attestation: "user", value: "HEL", verdict: "verified" },
    { kind: "fact", id: "to", statement: "Arrival airport", attestation: "user", value: "BER", verdict: "verified" },
    { kind: "fact", id: "delayH", statement: "Arrival delay in hours", attestation: "user", value: 4, verdict: "verified" },
    { kind: "computation", id: "dist", statement: "Great-circle distance HEL-BER (km)", fn: "haversineKm", inputs: ["from", "to"], claimed: distance, verdict: "unverified" },
    { kind: "computation", id: "short", statement: "Distance is 1 500 km or less", fn: "lte", inputs: ["dist", 1500], claimed: true, verdict: "unverified" },
    { kind: "computation", id: "late", statement: "Arrival delay is 3 hours or more", fn: "gte", inputs: ["delayH", 3], claimed: true, verdict: "unverified" },
    { kind: "rebuttal", id: "extra", against: "r261", statement: "The carrier is exempt only if it proves extraordinary circumstances (Art. 5(3)); the burden of proof is the carrier's", source: { url: EURLEX_261, quote: "extraordinary circumstances which could not have been avoided even if all reasonable measures had been taken", retrievedAt: now }, status: "allocated", verdict: "verified" },
    { kind: "claim", id: "claim", statement: "The passenger is owed EUR 250 by the operating carrier", rule: "r261", requires: ["from", "to", "delayH", "short", "late"], amount: { value: 250, currency: "EUR" } },
  ];
  return {
    errand: "My flight Helsinki-Berlin landed 4 hours late",
    eventDate,
    nodes: nodes.map((n) => ({ ...n, ...(overrides[n.id] ?? {}) }) as WarrantNode),
  };
}

test("EU261 warrant: accepted, with the exemption's burden of proof allocated to the carrier", () => {
  assert.ok(distance > 1000 && distance < 1500, `distance ${distance}`);
  const e = evaluate(eu261());
  assert.equal(e.decision, "ACCEPT", JSON.stringify(e.reasons));
  assert.equal(e.allocatedToReceiver.length, 1);
});

test("temporal guard: the same claim for a flight after 23 Oct 2027 is rejected under the old rule", () => {
  const e = evaluate(eu261({}, "2027-11-01"));
  assert.equal(e.decision, "REJECT");
  assert.ok(e.reasons.some((r) => r.node === "t2202"));
});

test("a sender's wrong computation is caught by the receiver's recomputation", () => {
  const e = evaluate(eu261({ dist: { claimed: 900 } as Partial<WarrantNode> }));
  assert.equal(e.decision, "REJECT");
  assert.ok(e.reasons.some((r) => r.node === "dist"));
});

test("an unresolved exception yields a precise question instead of a decision", () => {
  const e = evaluate(eu261({ extra: { status: "open" } as Partial<WarrantNode> }));
  assert.equal(e.decision, "NEEDS_INFO");
  assert.match(e.openQuestions[0] ?? "", /extraordinary circumstances/);
});

test("a rule quote that failed re-verification rejects the claim", () => {
  const e = evaluate(eu261({ r261: { verdict: "failed" } as Partial<WarrantNode> }));
  assert.equal(e.decision, "REJECT");
});

test("transcript commitment: inclusion proofs verify, tampered leaves do not, challenges avoid revealed leaves", async () => {
  const leaves: TranscriptLeaf[] = Array.from({ length: 7 }, (_, i) => ({ query: `q${i % 3}`, url: `https://src.example/${i}`, contentHash: `h${i}`, rank: i % 5 }));
  const c = await commit(leaves);
  for (let i = 0; i < leaves.length; i++) assert.equal(await verifyInclusion(c.root, leaves[i]!, prove(c, i)), true);
  assert.equal(await verifyInclusion(c.root, { ...leaves[3]!, contentHash: "swapped" }, prove(c, 3)), false);
  const revealed = new Set([0, 2]);
  const picks = await challengeIndices(c.root, "receiver-nonce", c.size, 3, revealed);
  assert.equal(picks.length, 3);
  assert.ok(picks.every((i) => !revealed.has(i)));
  assert.deepEqual(picks, await challengeIndices(c.root, "receiver-nonce", c.size, 3, revealed), "deterministic for a nonce");
  assert.ok(Math.abs(detectionProbability(0.2, 10) - 0.8926) < 0.001);
});

test("citation-completion templates and application-date extraction", () => {
  const q = citationQueries({ premise: "Passengers are entitled to EUR 250.", instrument: "Regulation (EC) No 261/2004", sourceKind: "regulation", exemptionLead: "An air carrier is not obliged to pay compensation" });
  assert.match(q.support, /The official text of the regulation:$/);
  assert.match(q.rebuttal, /judgment:$/);
  assert.match(q.temporal, /apply from:$/);
  assert.equal(applicationDate("Article 30. It shall apply from 23 October 2027."), "2027-10-23");
  assert.equal(applicationDate("no date here"), null);
});
