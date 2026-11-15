import assert from "node:assert/strict";
import { test } from "node:test";
import { actionFor, Authority, AuthorityError, type AgentGrant, type Proposal } from "../src/authority/authority.ts";
import { generateDeviceKey } from "../src/warrant/artifact.ts";

const T0 = new Date("2026-11-14T10:00:00Z");
const grant = (actions: AgentGrant["authorization_details"][0]["actions"], over: Partial<AgentGrant> = {}): AgentGrant => ({
  jti: "grant-1",
  principal: "person-7f3a",
  authorization_details: [{ type: "warrant_claim", actions, locations: ["claims.airline.example"], purpose: "EU261 claim for one flight" }],
  notBefore: "2026-11-14T00:00:00Z",
  expiresAt: "2026-12-14T00:00:00Z",
  limits: { maxExecutions: 1 },
  ...over,
});
const proposal = (over: Partial<Proposal> = {}): Proposal => ({ id: "claim-1", version: 1, receiver: "claims.airline.example", body: { amount: { value: 250, currency: "EUR" } }, createdAt: T0.toISOString(), expiresAt: "2026-11-21T00:00:00Z", ...over });
const ALL = ["claim.propose", "claim.approve", "claim.execute"] as const;
const ok = async () => ({ status: "accepted" as const, reference: "CASE-42" });

test("unmapped tools fail closed; capabilities are independent", async () => {
  assert.throws(() => actionFor("shell.exec"), AuthorityError);
  assert.equal(actionFor("exa.search").action, "evidence.read");
  const a = new Authority(() => T0);
  await assert.rejects(a.propose(grant(["evidence.read"]), proposal()), /does not include claim.propose/);
  const g = grant(["claim.propose", "claim.approve"]);
  const { proposal: p } = await a.propose(g, proposal());
  const auth = await a.approve(g, p, await generateDeviceKey(), true);
  await assert.rejects(a.execute(g, p, auth, "k1", ok), /does not include claim.execute/);
});

test("approve then execute; a retry returns the original attempt and sends nothing twice", async () => {
  const a = new Authority(() => T0);
  const g = grant([...ALL]);
  const { proposal: p } = await a.propose(g, proposal());
  const auth = await a.approve(g, p, await generateDeviceKey(), true);
  let sends = 0;
  const send = async () => (sends++, { status: "accepted" as const, reference: "CASE-42" });
  const first = await a.execute(g, p, auth, "k1", send);
  const again = await a.execute(g, p, auth, "k1", send);
  assert.equal(first.status, "accepted");
  assert.deepEqual(again, first);
  assert.equal(sends, 1);
  assert.deepEqual(a.ledger().map((r) => r.kind), ["proposed", "approved", "executed"]);
});

test("any change to the proposal after approval invalidates the approval", async () => {
  const a = new Authority(() => T0);
  const g = grant([...ALL]);
  const { proposal: p } = await a.propose(g, proposal());
  const auth = await a.approve(g, p, await generateDeviceKey(), true);
  const changed = proposal({ body: { amount: { value: 600, currency: "EUR" } } });
  await assert.rejects(a.execute(g, changed, auth, "k2", ok), /proposal changed after approval/);
  assert.equal(a.ledger().at(-1)?.kind, "denied");
});

test("revocation, expiry, limits and missing user verification are rechecked at execution", async () => {
  const device = await generateDeviceKey();
  const a = new Authority(() => T0);
  const g = grant([...ALL]);
  const { proposal: p } = await a.propose(g, proposal());
  await assert.rejects(a.approve(g, p, device, false), /user verification/);
  const auth = await a.approve(g, p, device, true);
  await a.revoke(g);
  await assert.rejects(a.execute(g, p, auth, "k3", ok), /revoked/);

  const late = new Authority(() => new Date("2026-11-14T12:00:00Z"));
  await assert.rejects(late.execute(g, p, auth, "k4", ok), /approval expired/);

  const b = new Authority(() => T0);
  const g2 = grant([...ALL], { jti: "grant-2" });
  const auth2 = await b.approve(g2, p, device, true);
  await b.execute(g2, p, auth2, "k5", ok);
  await assert.rejects(b.execute(g2, p, auth2, "k6", ok), /execution limit/);
});

test("a forged approval proof is rejected, and a timeout after submission stays 'unknown'", async () => {
  const a = new Authority(() => T0);
  const g = grant([...ALL], { limits: { maxExecutions: 5 } });
  const { proposal: p } = await a.propose(g, proposal());
  const auth = await a.approve(g, p, await generateDeviceKey(), true);
  const forged = { ...auth, proof: { ...auth.proof, publicKey: (await crypto.subtle.exportKey("jwk", (await generateDeviceKey()).keyPair.publicKey)) } };
  await assert.rejects(a.execute(g, p, forged, "k7", ok), /proof does not verify/);
  const attempt = await a.execute(g, p, auth, "k8", async () => { throw new Error("timeout"); });
  assert.equal(attempt.status, "unknown");
});
