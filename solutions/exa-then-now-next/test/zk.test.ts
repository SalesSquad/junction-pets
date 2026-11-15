import assert from "node:assert/strict";
import { test } from "node:test";
// @ts-expect-error -- plain ESM module without type declarations
import { eligibilityAvailable, proveEligibility, verifyEligibility } from "../relay/zk/eligibility.mjs";
import { buildArtifact, generateDeviceKey, verifyArtifact, type PrivateFact } from "../src/warrant/artifact.ts";
import { compileTwoLane, type TwoLaneResult } from "../src/warrant/compile.ts";

const available = await eligibilityAvailable();
const NOW = new Date("2026-11-14T10:00:00Z");
const mandate = { subject: "person-7f3a", recipient: "benefits.agency.example", purpose: "Housing allowance application", notBefore: "2026-11-14T00:00:00Z", expiresAt: "2026-12-14T00:00:00Z", jti: "mandate-zk-1" };
// A warrant whose only evidence is the private fact (no public premises needed for this test).
const emptyResult = { question: "Do I qualify for the housing allowance?", answerLane: [], premises: [], extraction: { support: 0, alternatives: [] }, citationQuery: null, authorityLane: [], legalUrls: [], triangulation: { status: "not_found" }, outcome: "GROUNDED", reasons: [] } as unknown as TwoLaneResult;

test("income below the threshold is proven without revealing it; the receiver verifies", { skip: !available && "python3 + Kättely + libsodium not available" }, async () => {
  const proof = await proveEligibility({ value: 31_500, threshold: 40_000, context: { receiver: mandate.recipient, mandate: mandate.jti, claim: "housing-1" } });
  assert.ok(proof && !JSON.stringify(proof).includes("31500"));
  const fact: PrivateFact = { statement: "household income <= EUR 40000", predicate: { op: "<=", threshold: 40_000, unit: "EUR" }, attestation: "self", proof };
  const a = await buildArtifact(emptyResult, mandate, await generateDeviceKey(), NOW, undefined, [fact]);
  const policy = { recipient: mandate.recipient, revoked: new Set<string>(), fetch: async () => "", now: NOW, verifyPrivateFact: verifyEligibility };
  const d = await verifyArtifact(a, policy);
  assert.ok(d.checked.some((c) => c.includes("household income <= EUR 40000")), JSON.stringify(d));
  assert.equal(d.decision === "REJECT" && d.reasons.some((r) => r.includes("private")), false);
});

test("ineligible values cannot be proven; altered thresholds and replayed proofs are rejected", { skip: !available && "python3 + Kättely + libsodium not available" }, async () => {
  assert.equal(await proveEligibility({ value: 45_000, threshold: 40_000, context: {} }), null);
  const proof = await proveEligibility({ value: 31_500, threshold: 40_000, context: { receiver: mandate.recipient, mandate: mandate.jti } });
  assert.equal(await verifyEligibility({ ...proof, threshold: 32_000 }), false);
  const replayed: PrivateFact = { statement: "household income <= EUR 40000", predicate: { op: "<=", threshold: 40_000, unit: "EUR" }, attestation: "self", proof: { ...proof, context: { receiver: "other.example", mandate: "m-x" } } };
  const a = await buildArtifact(emptyResult, mandate, await generateDeviceKey(), NOW, undefined, [replayed]);
  const d = await verifyArtifact(a, { recipient: mandate.recipient, revoked: new Set(), fetch: async () => "", now: NOW, verifyPrivateFact: verifyEligibility });
  assert.equal(d.decision, "REJECT");
  assert.match(d.reasons.join(" "), /bound to another receiver/);
});

test("benefits demo: public legal limit proven by quote, private income proven in zero knowledge -> ACCEPT", { skip: !available && "python3 + Kättely + libsodium not available" }, async () => {
  // SYNTHETIC statute text on a legal-text host URL; not a real provision.
  const LAW = "https://www.legislation.gov.uk/synthetic/housing-allowance-act/section/12";
  const law = "Section 12. The allowance is granted where the annual income of the household does not exceed EUR 40 000. Section 13. The application shall be decided within 30 days.";
  let n = 0;
  const search = async () => (n++ === 0
    ? [{ url: "https://agency.example/housing", highlights: ["Households with an annual income of at most EUR 40 000 qualify for the housing allowance."] }]
    : [{ url: LAW, highlights: [] }]);
  const r = await compileTwoLane("Does my household qualify for the housing allowance with our annual income?", search, async () => law, { now: NOW });
  assert.equal(r.outcome, "GROUNDED", r.reasons.join("; "));
  const idx = r.premises.findIndex((p) => p.premise.quantity.value === 40_000);
  assert.ok(idx >= 0, JSON.stringify(r.premises.map((p) => p.premise.quantity.text)));
  const proof = await proveEligibility({ value: 31_500, threshold: 40_000, context: { receiver: mandate.recipient, mandate: mandate.jti, claim: "housing-1" } });
  const fact: PrivateFact = { statement: "household income <= EUR 40000", predicate: { op: "<=", threshold: 40_000, unit: "EUR", premiseIndex: idx }, attestation: "self", proof };
  const policy = { recipient: mandate.recipient, revoked: new Set<string>(), fetch: async () => law, now: NOW, verifyPrivateFact: verifyEligibility };
  const ok = await verifyArtifact(await buildArtifact(r, mandate, await generateDeviceKey(), NOW, undefined, [fact]), policy);
  assert.equal(ok.decision, "ACCEPT", ok.reasons.join("; "));
  assert.ok(ok.checked.some((c) => c.startsWith("private household income")));
  const wrongLimit: PrivateFact = { ...fact, predicate: { ...fact.predicate, threshold: 60_000 }, proof: (await proveEligibility({ value: 31_500, threshold: 60_000, context: { receiver: mandate.recipient, mandate: mandate.jti } }))! };
  const bad = await verifyArtifact(await buildArtifact(r, mandate, await generateDeviceKey(), NOW, undefined, [wrongLimit]), policy);
  assert.equal(bad.decision, "REJECT");
  assert.match(bad.reasons.join(" "), /not the verified legal limit/);
});
