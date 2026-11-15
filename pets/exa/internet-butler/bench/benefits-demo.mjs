#!/usr/bin/env node
// The whole system on one errand (SYNTHETIC statute and agency page; real cryptography):
// compile with evidence memory -> zero-knowledge income proof bound to the verified legal limit ->
// signed warrant with compiler provenance -> propose / approve / execute under action authority ->
// the receiver verifies everything -> repeat question answered from memory.
import { execSync } from "node:child_process";
import { Authority } from "../src/authority/authority.ts";
import { EvidenceMemory } from "../src/memory/evidenceMemory.ts";
import { compileWithMemory } from "../src/memory/withMemory.ts";
import { buildArtifact, generateDeviceKey, verifyArtifact } from "../src/warrant/artifact.ts";
import { eligibilityAvailable, proveEligibility, verifyEligibility } from "../relay/zk/eligibility.mjs";

const LAW = "https://www.legislation.gov.uk/synthetic/housing-allowance-act/section/12";
const law = "Section 12. The allowance is granted where the annual income of the household does not exceed EUR 40 000. Section 13. The application shall be decided within 30 days.";
const AGENCY = "https://agency.example/housing";
const RECEIVER = "benefits.agency.example";
let searches = 0;
const search = async (q) => (searches++ % 2 === 0
  ? [{ url: AGENCY, highlights: ["Households with an annual income of at most EUR 40 000 qualify for the housing allowance."] }]
  : [{ url: LAW, highlights: [] }]);
const fetchPage = async () => law;
const question = "Does my household qualify for the housing allowance with our annual income?";
const tenant = "person-7f3a";

if (!(await eligibilityAvailable())) {
  console.log("Zero-knowledge bridge unavailable (needs python3, libsodium and a Kättely checkout at KATTELY_PATH).");
  process.exit(1);
}
const memory = new EvidenceMemory("this-device");
const ctx = { tenant, at: new Date().toISOString().slice(0, 10), jurisdiction: "SYNTHETIC" };

console.log("[SYNTHETIC sources, real cryptography]\n");
const first = await compileWithMemory(question, memory, ctx, search, fetchPage);
const r = first.result;
console.log(`1. Compile from the web: ${r.outcome}; ${first.stored} verified claim(s) stored in memory`);
for (const p of r.premises) console.log(`   ${p.premise.role} ${p.premise.quantity.text}: ${p.status} — "${p.triangulation.quote ?? ""}"`);

const idx = r.premises.findIndex((p) => p.premise.quantity.unit === "EUR");
const limit = r.premises[idx].premise.quantity.value;
const device = await generateDeviceKey();
const jti = `mandate-${Date.now()}`;
const proof = await proveEligibility({ value: 31_500, threshold: limit, context: { receiver: RECEIVER, mandate: jti, claim: "housing-1" } });
console.log(`\n2. Zero-knowledge proof: household income <= EUR ${limit} (the verified legal limit); the income itself is not in the proof (${JSON.stringify(proof).length} bytes)`);

const git = (c) => { try { return execSync(`git ${c}`, { cwd: new URL("..", import.meta.url), encoding: "utf8" }).trim(); } catch { return ""; } };
const compiler = { name: "internet-butler-warrant", version: "0.1.0", commit: git("rev-parse HEAD") || "unknown", dirty: git("status --porcelain") !== "" };
const mandate = { subject: tenant, recipient: RECEIVER, purpose: "One housing allowance application", notBefore: new Date(Date.now() - 60_000).toISOString(), expiresAt: new Date(Date.now() + 30 * 864e5).toISOString(), jti };
const artifact = await buildArtifact(r, mandate, device, new Date(), compiler, [
  { statement: `household income <= EUR ${limit}`, predicate: { op: "<=", threshold: limit, unit: "EUR", premiseIndex: idx }, attestation: "self", proof },
]);
console.log(`3. Signed warrant (${device.alg}) from compiler ${compiler.commit.slice(0, 7)}${compiler.dirty ? " (dirty)" : ""}`);

const authority = new Authority();
const grant = { jti, principal: tenant, authorization_details: [{ type: "warrant_claim", actions: ["claim.propose", "claim.approve", "claim.execute"], locations: [RECEIVER], purpose: mandate.purpose }], notBefore: mandate.notBefore, expiresAt: mandate.expiresAt, limits: { maxExecutions: 1 } };
const proposalObj = { id: "housing-1", version: 1, receiver: RECEIVER, body: artifact, createdAt: new Date().toISOString(), expiresAt: mandate.expiresAt };
const { proposal } = await authority.propose(grant, proposalObj);
const approval = await authority.approve(grant, proposal, device, true);
const receiverPolicy = { recipient: RECEIVER, revoked: new Set(), fetch: fetchPage, verifyPrivateFact: verifyEligibility, trustedCompilers: compiler.dirty ? undefined : new Set([compiler.commit]) };
const attempt = await authority.execute(grant, proposal, approval, "idem-housing-1", async (p) => {
  const d = await verifyArtifact(p.body, receiverPolicy);
  console.log(`4. Receiver: ${d.decision}${d.reasons.length ? ` — ${d.reasons.join("; ")}` : ""}\n   checked: ${d.checked.join(", ")}`);
  return { status: d.decision === "ACCEPT" ? "accepted" : "rejected", reference: d.decision === "ACCEPT" ? "CASE-2026-001" : undefined };
});
const retry = await authority.execute(grant, proposal, approval, "idem-housing-1", async () => { throw new Error("must not send twice"); });
console.log(`5. Execution: ${attempt.status} (${attempt.receiverReference ?? "-"}); retry with the same key returns the same attempt: ${retry === attempt}`);
console.log(`   ledger: ${authority.ledger().map((x) => x.kind).join(" -> ")}`);

const before = searches;
const again = await compileWithMemory(question, memory, ctx, search, fetchPage);
console.log(`\n6. Same question again: answered from ${again.source}${again.source === "memory" ? ` (no web search: ${searches === before})` : ""}`);
