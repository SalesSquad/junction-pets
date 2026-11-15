/**
 * Independent action authority for agent errands, after BankMatch ADR-002 and Kättely.
 *
 *  evidence.read   search and read public sources
 *  claim.propose   compile a claim into a versioned proposal
 *  claim.approve   a person approves one proposal digest for one executor (device-signed proof)
 *  claim.execute   submit the approved proposal to the receiver
 *  mandate.revoke  withdraw a grant
 *
 * None implies another. Unmapped tools fail closed. Approval binds to the proposal digest, so any
 * change after approval invalidates it. Everything is rechecked at execution. Retries with the same
 * idempotency key return the original attempt and receipt; an unknown outcome stays unknown.
 * Every write appends a receipt to a hash-chained ledger.
 */
import { canonicalJson, sha256Hex } from "../lib/council.ts";

export type Action = "evidence.read" | "claim.propose" | "claim.approve" | "claim.execute" | "mandate.revoke";

export interface OperationSpec {
  action: Action;
  effect: "none" | "local" | "external";
  reversal: "not_applicable" | "reversible" | "irreversible";
  risk: "low" | "medium" | "high";
  idempotent: boolean;
  /** Output contains third-party text that must be treated as data, never as instructions. */
  untrustedContent: boolean;
}

/** The tool-to-action contract. It maps tools; it grants nothing. */
export const OPERATIONS: Readonly<Record<string, OperationSpec>> = Object.freeze({
  "exa.search": { action: "evidence.read", effect: "external", reversal: "not_applicable", risk: "low", idempotent: true, untrustedContent: true },
  "exa.contents": { action: "evidence.read", effect: "external", reversal: "not_applicable", risk: "low", idempotent: true, untrustedContent: true },
  "typesafe.judge": { action: "evidence.read", effect: "external", reversal: "not_applicable", risk: "low", idempotent: true, untrustedContent: false },
  "warrant.compile": { action: "claim.propose", effect: "local", reversal: "reversible", risk: "low", idempotent: true, untrustedContent: true },
  "warrant.approve": { action: "claim.approve", effect: "local", reversal: "reversible", risk: "medium", idempotent: true, untrustedContent: false },
  "warrant.send": { action: "claim.execute", effect: "external", reversal: "irreversible", risk: "high", idempotent: true, untrustedContent: false },
  "mandate.revoke": { action: "mandate.revoke", effect: "local", reversal: "irreversible", risk: "low", idempotent: true, untrustedContent: false },
});

export class AuthorityError extends Error {}

/** Fail closed: a tool without an explicit mapping cannot be dispatched. */
export function actionFor(tool: string): OperationSpec {
  const op = OPERATIONS[tool];
  if (!op) throw new AuthorityError(`tool "${tool}" has no action mapping; refused before dispatch`);
  return op;
}

// ---------- records ----------

/** RFC 9396-style authorization detail: what, for whom, why. */
export interface AuthorizationDetail {
  type: "warrant_claim";
  actions: Action[];
  locations: string[]; // the audience: receivers this grant may submit to
  purpose: string;
}

export interface AgentGrant {
  jti: string;
  principal: string; // pseudonymous person reference
  authorization_details: AuthorizationDetail[];
  notBefore: string;
  expiresAt: string;
  limits: { maxExecutions: number };
}

export interface Proposal {
  id: string;
  version: number;
  receiver: string;
  /** The claim's content (e.g. the signed Warrant artifact or its core). */
  body: unknown;
  createdAt: string;
  expiresAt: string;
}

export interface Authorization {
  proposalId: string;
  proposalDigest: string;
  executor: string;
  approvedAt: string;
  expiresAt: string;
  /** Device-signed approval over the digest; stands in for a WebAuthn assertion with user verification. */
  proof: { alg: "Ed25519" | "ECDSA-P256"; publicKey: JsonWebKey; signature: string; userVerified: boolean };
}

export type AttemptStatus = "accepted" | "rejected" | "unknown";

export interface ExecutionAttempt {
  idempotencyKey: string;
  proposalDigest: string;
  authorizationDigest: string;
  status: AttemptStatus;
  receiverReference?: string;
  receiptSeq: number;
}

export interface LedgerReceipt {
  seq: number;
  at: string;
  kind: "proposed" | "approved" | "executed" | "denied" | "revoked";
  subject: string;
  digest?: string;
  prevHash: string;
  hash: string;
}

// ---------- helpers ----------

const b64u = (b: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const enc = (s: string) => new TextEncoder().encode(s);
const signAlg = (alg: Authorization["proof"]["alg"]) => (alg === "Ed25519" ? { name: "Ed25519" } : { name: "ECDSA", hash: "SHA-256" });
const keyAlg = (alg: Authorization["proof"]["alg"]) => (alg === "Ed25519" ? { name: "Ed25519" } : { name: "ECDSA", namedCurve: "P-256" });

export const proposalDigest = (p: Proposal) => sha256Hex(canonicalJson(p));
const approvalMessage = (a: Omit<Authorization, "proof">) => canonicalJson(a);

// ---------- the authority ----------

export interface SendFn {
  (proposal: Proposal, idempotencyKey: string): Promise<{ status: AttemptStatus; reference?: string }>;
}

export class Authority {
  private receipts: LedgerReceipt[] = [];
  private attempts = new Map<string, ExecutionAttempt>();
  private executions = new Map<string, number>(); // grant jti -> count
  private revoked = new Set<string>();
  private readonly now: () => Date;

  constructor(now: () => Date = () => new Date()) {
    this.now = now;
  }

  ledger(): readonly LedgerReceipt[] {
    return this.receipts;
  }

  private async append(kind: LedgerReceipt["kind"], subject: string, digest?: string): Promise<LedgerReceipt> {
    const last = this.receipts.at(-1);
    const unsigned = { seq: (last?.seq ?? 0) + 1, at: this.now().toISOString(), kind, subject, digest, prevHash: last?.hash ?? "0".repeat(64) };
    const r = { ...unsigned, hash: await sha256Hex(canonicalJson(unsigned)) };
    this.receipts.push(r);
    return r;
  }

  /** Check that the grant permits `action` towards `receiver` right now. Returns the reason when it does not. */
  check(grant: AgentGrant, action: Action, receiver?: string): string | null {
    const t = this.now();
    if (this.revoked.has(grant.jti)) return `grant ${grant.jti} is revoked`;
    if (t < new Date(grant.notBefore)) return "grant not yet valid";
    if (t >= new Date(grant.expiresAt)) return "grant expired";
    const detail = grant.authorization_details.find((d) => d.actions.includes(action) && (!receiver || d.locations.includes(receiver)));
    if (!detail) return `grant does not include ${action}${receiver ? ` for ${receiver}` : ""}`;
    return null;
  }

  async propose(grant: AgentGrant, p: Proposal): Promise<{ proposal: Proposal; digest: string }> {
    const why = this.check(grant, "claim.propose", p.receiver);
    if (why) {
      await this.append("denied", `propose ${p.id}: ${why}`);
      throw new AuthorityError(why);
    }
    const digest = await proposalDigest(p);
    await this.append("proposed", `${p.id} v${p.version} for ${p.receiver}`, digest);
    return { proposal: p, digest };
  }

  /** The person approves exactly this proposal version for this executor; the device key signs the digest. */
  async approve(grant: AgentGrant, p: Proposal, device: { keyPair: CryptoKeyPair; alg: Authorization["proof"]["alg"] }, userVerified: boolean, ttlMinutes = 60): Promise<Authorization> {
    const why = this.check(grant, "claim.approve", p.receiver) ?? (userVerified ? null : "approval requires user verification");
    if (why) {
      await this.append("denied", `approve ${p.id}: ${why}`);
      throw new AuthorityError(why);
    }
    const t = this.now();
    const core = { proposalId: p.id, proposalDigest: await proposalDigest(p), executor: p.receiver, approvedAt: t.toISOString(), expiresAt: new Date(t.getTime() + ttlMinutes * 60_000).toISOString() };
    const signature = b64u(await crypto.subtle.sign(signAlg(device.alg), device.keyPair.privateKey, enc(approvalMessage(core))));
    const publicKey = await crypto.subtle.exportKey("jwk", device.keyPair.publicKey);
    await this.append("approved", `${p.id} v${p.version}`, core.proposalDigest);
    return { ...core, proof: { alg: device.alg, publicKey, signature, userVerified } };
  }

  /** Everything is rechecked at submission time; any mismatch fails before the receiver is contacted. */
  async execute(grant: AgentGrant, p: Proposal, auth: Authorization, idempotencyKey: string, send: SendFn): Promise<ExecutionAttempt> {
    const prior = this.attempts.get(idempotencyKey);
    if (prior) {
      if (prior.proposalDigest !== (await proposalDigest(p))) throw new AuthorityError("idempotency key reused for different proposal terms");
      return prior; // a retry returns the original attempt; nothing is sent twice
    }
    const digest = await proposalDigest(p);
    const reasons = [
      this.check(grant, "claim.execute", p.receiver),
      auth.proposalDigest !== digest ? "proposal changed after approval; approval no longer applies" : null,
      auth.executor !== p.receiver ? "approval is for another executor" : null,
      this.now() >= new Date(auth.expiresAt) ? "approval expired" : null,
      this.now() >= new Date(p.expiresAt) ? "proposal expired" : null,
      (this.executions.get(grant.jti) ?? 0) >= grant.limits.maxExecutions ? "grant execution limit reached" : null,
      !auth.proof.userVerified ? "approval lacks user verification" : null,
      (await this.verifyApproval(auth)) ? null : "approval proof does not verify",
    ].filter((x): x is string => !!x);
    if (reasons.length) {
      await this.append("denied", `execute ${p.id}: ${reasons.join("; ")}`, digest);
      throw new AuthorityError(reasons.join("; "));
    }
    let outcome: { status: AttemptStatus; reference?: string };
    try {
      outcome = await send(p, idempotencyKey);
    } catch {
      outcome = { status: "unknown" }; // a timeout after submission is not a failure we can assume
    }
    this.executions.set(grant.jti, (this.executions.get(grant.jti) ?? 0) + 1);
    const receipt = await this.append("executed", `${p.id} -> ${p.receiver}: ${outcome.status}${outcome.reference ? ` (${outcome.reference})` : ""}`, digest);
    const attempt: ExecutionAttempt = { idempotencyKey, proposalDigest: digest, authorizationDigest: await sha256Hex(canonicalJson(auth)), status: outcome.status, receiverReference: outcome.reference, receiptSeq: receipt.seq };
    this.attempts.set(idempotencyKey, attempt);
    return attempt;
  }

  async revoke(grant: AgentGrant): Promise<LedgerReceipt> {
    this.revoked.add(grant.jti);
    return this.append("revoked", `grant ${grant.jti}`);
  }

  private async verifyApproval(auth: Authorization): Promise<boolean> {
    try {
      const { proof, ...core } = auth;
      const key = await crypto.subtle.importKey("jwk", proof.publicKey, keyAlg(proof.alg), false, ["verify"]);
      return await crypto.subtle.verify(signAlg(proof.alg), key, unb64u(proof.signature), enc(approvalMessage(core)));
    } catch {
      return false;
    }
  }
}
