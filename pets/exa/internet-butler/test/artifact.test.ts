import assert from "node:assert/strict";
import { test } from "node:test";
import { buildArtifact, generateDeviceKey, verifyArtifact, type WarrantArtifact } from "../src/warrant/artifact.ts";
import { compileTwoLane } from "../src/warrant/compile.ts";

const LEGAL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32004R0261";
const CURIA = "https://curia.europa.eu/sturgeon";
const pages: Record<string, string> = {
  [LEGAL]: "Article 7. Where reference is made to this Article, passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres.",
  [CURIA]: "Passengers whose flights are delayed may rely on the right to compensation where they reach their final destination three hours or more after the arrival time originally scheduled by the air carrier.",
};
const answerLane = [
  { url: "https://consumer.example/eu261", highlights: ["For flights of 1,500 km or less you are entitled to €250 under Regulation (EC) No 261/2004."] },
  { url: "https://claims.example/guide", highlights: ["Passengers on short flights receive EUR 250 when they arrive three hours late."] },
];
const fetchPage = async (u: string) => pages[u] ?? "";
const NOW = new Date("2026-11-14T10:00:00Z");
const mandate = { subject: "person-7f3a", recipient: "claims.airline.example", purpose: "EU261 compensation claim for one flight", notBefore: "2026-11-14T00:00:00Z", expiresAt: "2026-12-14T00:00:00Z", jti: "mandate-001" };

async function issue(): Promise<WarrantArtifact> {
  let n = 0;
  const search = async () => (n++ === 0 ? answerLane : [{ url: LEGAL, highlights: [] }, { url: CURIA, highlights: [] }]);
  const r = await compileTwoLane("How much compensation do I get if my short EU flight is 3 hours late?", search, fetchPage, { now: NOW });
  assert.equal(r.outcome, "GROUNDED", r.reasons.join("; "));
  return buildArtifact(r, mandate, await generateDeviceKey(), NOW);
}
const policy = (over: Partial<Parameters<typeof verifyArtifact>[1]> = {}) => ({ recipient: "claims.airline.example", revoked: new Set<string>(), fetch: fetchPage, now: NOW, ...over });

test("receiver accepts a genuine warrant after re-fetching every quote", async () => {
  const a = await issue();
  assert.ok(a.transcript.size >= 4 && /^[0-9a-f]{64}$/.test(a.transcript.root));
  const d = await verifyArtifact(a, policy());
  assert.equal(d.decision, "ACCEPT", d.reasons.join("; "));
  assert.ok(d.checked.includes("signature") && d.checked.includes("mandate"));
});

test("any alteration breaks the signature", async () => {
  const a = await issue();
  const tampered = structuredClone(a);
  tampered.evidence.find((e) => e.role === "outcome")!.quantity.value = 600;
  assert.equal((await verifyArtifact(tampered, policy())).decision, "REJECT");
});

test("mandate scope, expiry and revocation are enforced by the receiver", async () => {
  const a = await issue();
  assert.match((await verifyArtifact(a, policy({ recipient: "other.example" }))).reasons[0]!, /mandate is for/);
  assert.match((await verifyArtifact(a, policy({ now: new Date("2027-01-01T00:00:00Z") }))).reasons.join(" "), /expired/);
  assert.match((await verifyArtifact(a, policy({ revoked: new Set(["mandate-001"]) }))).reasons.join(" "), /revoked/);
});

test("a source that changed after issuing makes the receiver reject, naming the premise", async () => {
  const a = await issue();
  const changed = async (u: string) => (u === LEGAL ? "Article 7 was amended. Passengers shall receive EUR 300." : fetchPage(u));
  const d = await verifyArtifact(a, policy({ fetch: changed }));
  assert.equal(d.decision, "REJECT");
  assert.match(d.reasons.join(" "), /outcome €250: quote not found/);
});

test("receiver can require a trusted, clean compiler build (CRACI provenance)", async () => {
  let n = 0;
  const search = async () => (n++ === 0 ? answerLane : [{ url: LEGAL, highlights: [] }, { url: CURIA, highlights: [] }]);
  const r = await compileTwoLane("How much compensation do I get if my short EU flight is 3 hours late?", search, fetchPage, { now: NOW });
  const key = await generateDeviceKey();
  const clean = await buildArtifact(r, mandate, key, NOW, { name: "internet-butler-warrant", version: "0.1.0", commit: "abc123", dirty: false, sbomSha256: "f".repeat(64) });
  assert.equal((await verifyArtifact(clean, policy({ trustedCompilers: new Set(["abc123"]) }))).decision, "ACCEPT");
  assert.match((await verifyArtifact(clean, policy({ trustedCompilers: new Set(["other"]) }))).reasons[0]!, /not a trusted build/);
  const dirty = await buildArtifact(r, mandate, key, NOW, { name: "internet-butler-warrant", version: "0.1.0", commit: "abc123", dirty: true });
  assert.match((await verifyArtifact(dirty, policy({ trustedCompilers: new Set(["abc123"]) }))).reasons[0]!, /dirty tree/);
});
