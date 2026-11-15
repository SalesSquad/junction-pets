/**
 * Warrant artifact: a proof-carrying request.
 *
 * The sender's device signs { mandate, evidence, transcript root, decision }. The receiver needs no
 * trust in the sender's software: it checks the signature, the mandate's scope, expiry and revocation,
 * re-fetches every cited legal page, matches each quote verbatim, checks that the quote states the
 * decisive quantity, and decides by code.
 */
import { pointInTimeDate } from "./pointInTime.ts";
import { canonicalJson, sha256Hex } from "../lib/council.ts";
import type { TwoLaneResult } from "./compile.ts";
import { extractQuantities, roleOverlap, sameQuantity, type Quantity, type ThreeWayStatus } from "./lanes.ts";
import { commit, type TranscriptLeaf } from "./transcript.ts";
import { replayReceipts, type Answer, type DecisionProvider, type JudgmentReceipt } from "../decide/decide.ts";

export interface Mandate {
  /** The person's device public key (JWK). Only this key can issue warrants under the mandate. */
  issuerKey: JsonWebKey;
  alg: "Ed25519" | "ECDSA-P256";
  subject: string; // pseudonymous reference to the person
  recipient: string; // who may receive and act on it (domain or address)
  purpose: string;
  notBefore: string;
  expiresAt: string;
  jti: string; // unique id, used for revocation
}

export interface EvidenceItem {
  role: "threshold" | "outcome";
  quantity: Pick<Quantity, "kind" | "value" | "unit" | "text">;
  explainer: { url: string; sentence: string };
  /** focus: when the quote includes the words introducing a list item, the item itself; the amount must be in it. */
  legal?: { url: string; quote: string; retrievedAt: string; focus?: string };
  status: ThreeWayStatus;
}

/** Which compiler build produced the warrant (CRACI-style build provenance). */
export interface CompilerProvenance {
  name: string;
  version: string;
  commit: string;
  /** True when the working tree had uncommitted changes: such builds are not reproducible. */
  dirty: boolean;
  /** SHA-256 of the build's SBOM (e.g. CRACI CycloneDX), when built in CI. */
  sbomSha256?: string;
}

/**
 * A private fact proven, not disclosed: e.g. "household income <= EUR 40 000" with a zero-knowledge
 * range proof over a Pedersen commitment (Kättely). The proof is bound to this claim's context.
 * Self-attested unless an issuer signs the same commitment.
 */
export interface PrivateFact {
  statement: string;
  /** premiseIndex binds the threshold to a verified public premise (the legal limit) in `evidence`. */
  predicate: { op: "<="; threshold: number; unit: string; premiseIndex?: number };
  attestation: "self" | "issuer";
  proof: { scheme: string; commitment: string; threshold: number; bits: number; context: Record<string, unknown>; [k: string]: unknown };
}

export interface WarrantArtifact {
  /** The date whose law the claim relies on; every pinned point-in-time source must speak for that date. */
  lawAsOf?: string;
  version: 1;
  compiler: CompilerProvenance;
  privateFacts?: PrivateFact[];
  claim: string;
  decision: "GROUNDED" | "NEEDS_INFO";
  clarify?: { question: string; options: string[] };
  evidence: EvidenceItem[];
  /** Typed judgments the compiler relied on, replayable by the receiver's own judge. */
  judgments?: JudgmentReceipt[];
  transcript: { root: string; size: number };
  mandate: Mandate;
  issuedAt: string;
  signature: string; // base64url over canonicalJson(artifact without signature)
}

// Portable base64url (browser and Node).
const b64u = (b: ArrayBuffer) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
const enc = (s: string) => new TextEncoder().encode(s);

export async function generateDeviceKey(): Promise<{ keyPair: CryptoKeyPair; alg: Mandate["alg"] }> {
  try {
    const keyPair = (await crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"])) as CryptoKeyPair;
    return { keyPair, alg: "Ed25519" };
  } catch {
    const keyPair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, ["sign", "verify"]);
    return { keyPair, alg: "ECDSA-P256" };
  }
}

const signParams = (alg: Mandate["alg"]) => (alg === "Ed25519" ? { name: "Ed25519" } : { name: "ECDSA", hash: "SHA-256" });
const importParams = (alg: Mandate["alg"]) => (alg === "Ed25519" ? { name: "Ed25519" } : { name: "ECDSA", namedCurve: "P-256" });

export async function transcriptLeaves(r: TwoLaneResult): Promise<TranscriptLeaf[]> {
  const leaf = async (query: string, rank: number, x: { url: string; highlights: string[] }): Promise<TranscriptLeaf> => ({
    query,
    url: x.url,
    contentHash: await sha256Hex(x.highlights.join("\n")),
    rank,
  });
  return Promise.all([...r.answerLane.map((x, i) => leaf(r.question, i, x)), ...r.authorityLane.map((x, i) => leaf(r.citationQuery ?? "", i, x))]);
}

export async function buildArtifact(
  r: TwoLaneResult,
  mandate: Omit<Mandate, "issuerKey" | "alg">,
  key: { keyPair: CryptoKeyPair; alg: Mandate["alg"] },
  now = new Date(),
  compiler: CompilerProvenance = { name: "internet-butler-warrant", version: "0.1.0", commit: "unknown", dirty: true },
  privateFacts?: PrivateFact[],
): Promise<WarrantArtifact> {
  const leaves = await transcriptLeaves(r);
  const c = leaves.length ? await commit(leaves) : { root: "", size: 0 };
  const unsigned: Omit<WarrantArtifact, "signature"> = {
    version: 1,
    compiler,
    privateFacts,
    claim: r.question,
    ...(r.lawAsOf ? { lawAsOf: r.lawAsOf } : {}),
    decision: r.outcome,
    clarify: r.clarify ? { question: r.clarify.question, options: r.clarify.options } : undefined,
    evidence: r.premises.map((p) => ({
      role: p.premise.role,
      quantity: { kind: p.premise.quantity.kind, value: p.premise.quantity.value, unit: p.premise.quantity.unit, text: p.premise.quantity.text },
      explainer: { url: p.premise.sourceUrl, sentence: p.premise.sentence },
      legal: p.triangulation.status === "agree" ? { url: p.triangulation.url, quote: p.triangulation.quote, retrievedAt: now.toISOString(), ...(p.triangulation.focus ? { focus: p.triangulation.focus } : {}) } : undefined,
      status: p.status,
    })),
    judgments: r.judgments?.length ? r.judgments : undefined,
    transcript: { root: c.root, size: c.size },
    mandate: { ...mandate, issuerKey: await crypto.subtle.exportKey("jwk", key.keyPair.publicKey), alg: key.alg },
    issuedAt: now.toISOString(),
  };
  const sig = await crypto.subtle.sign(signParams(key.alg), key.keyPair.privateKey, enc(canonicalJson(unsigned)));
  return { ...unsigned, signature: b64u(sig) };
}

export interface ReceiverPolicy {
  recipient: string;
  revoked: Set<string>;
  fetch: (url: string) => Promise<string>;
  now?: Date;
  /** When set, only warrants built from these clean compiler commits are accepted. */
  trustedCompilers?: Set<string>;
  /** Verifier for zero-knowledge private facts; warrants that carry private facts are rejected without one. */
  verifyPrivateFact?: (proof: PrivateFact["proof"]) => Promise<boolean>;
  /**
   * The receiver's own typed judge. Each judgment in the warrant is re-asked over its recorded state;
   * a disagreement makes the decision NEEDS_INFO (judgments are soft evidence), a digest mismatch REJECT.
   */
  judge?: DecisionProvider;
  /**
   * The page as it was at a past time (e.g. Exa /contents with snapshotAsOf = retrievedAt). When a quote
   * is gone from the live page but present in the snapshot, the source changed after compilation:
   * NEEDS_INFO with that reason, not REJECT as if the quote had been invented.
   */
  fetchAsOf?: (url: string, at: string) => Promise<string>;
}

export interface ReceiverDecision {
  decision: "ACCEPT" | "NEEDS_INFO" | "REJECT";
  reasons: string[];
  checked: string[];
  question?: string;
}

const fmt = (a: Answer) => (a.kind === "yesno" ? `p=${(a.p ?? 0).toFixed(2)}` : a.kind === "choice" ? String(a.choice) : `score ${(a.score ?? 0).toFixed(1)}`);

const norm = (s: string) => s.normalize("NFKC").replace(/[‘’]/g, "'").replace(/\s+/g, " ").trim().toLowerCase();

export async function verifyArtifact(a: WarrantArtifact, policy: ReceiverPolicy): Promise<ReceiverDecision> {
  const reasons: string[] = [];
  const checked: string[] = [];
  const now = policy.now ?? new Date();

  // 1. Signature over everything except the signature.
  const { signature, ...unsigned } = a;
  let sigOk = false;
  try {
    const pub = await crypto.subtle.importKey("jwk", a.mandate.issuerKey, importParams(a.mandate.alg), false, ["verify"]);
    sigOk = await crypto.subtle.verify(signParams(a.mandate.alg), pub, unb64u(signature), enc(canonicalJson(unsigned)));
  } catch {
    sigOk = false;
  }
  if (!sigOk) return { decision: "REJECT", reasons: ["signature does not verify: the warrant was altered or not issued by the mandate's key"], checked };
  checked.push("signature");

  // 2. Mandate scope, validity and revocation.
  if (a.mandate.recipient !== policy.recipient) reasons.push(`mandate is for ${a.mandate.recipient}, not ${policy.recipient}`);
  if (now < new Date(a.mandate.notBefore)) reasons.push("mandate not yet valid");
  if (now >= new Date(a.mandate.expiresAt)) reasons.push(`mandate expired at ${a.mandate.expiresAt}`);
  if (policy.revoked.has(a.mandate.jti)) reasons.push(`mandate ${a.mandate.jti} has been revoked`);
  if (reasons.length) return { decision: "REJECT", reasons, checked };
  checked.push("mandate");

  if (policy.trustedCompilers) {
    if (a.compiler.dirty || !policy.trustedCompilers.has(a.compiler.commit)) {
      return { decision: "REJECT", reasons: [`compiler ${a.compiler.commit}${a.compiler.dirty ? " (dirty tree)" : ""} is not a trusted build`], checked };
    }
    checked.push("compiler");
  }

  for (const f of a.privateFacts ?? []) {
    const boundHere = f.proof.context?.["receiver"] === a.mandate.recipient && f.proof.context?.["mandate"] === a.mandate.jti;
    if (f.proof.threshold !== f.predicate.threshold) reasons.push(`private fact "${f.statement}": proof threshold differs from the stated predicate`);
    else if (!boundHere) reasons.push(`private fact "${f.statement}": proof is bound to another receiver or mandate`);
    else if (!policy.verifyPrivateFact) reasons.push(`private fact "${f.statement}": no zero-knowledge verifier configured`);
    else if (!(await policy.verifyPrivateFact(f.proof))) reasons.push(`private fact "${f.statement}": zero-knowledge proof does not verify`);
    else checked.push(`private ${f.statement} (${f.attestation}-attested)`);
  }
  if (reasons.length) return { decision: "REJECT", reasons, checked };

  if (a.decision === "NEEDS_INFO") {
    return { decision: "NEEDS_INFO", reasons: ["the sender's compiler could not ground every premise"], checked, question: a.clarify?.question };
  }

  // 3. Evidence: every cited legal quote re-fetched and matched verbatim, stating its quantity in a matching clause.
  const pages = new Map<string, string>();
  const soft: string[] = [];
  for (const e of a.evidence) {
    if (!e.status.startsWith("confirmed")) continue;
    if (!e.legal) {
      reasons.push(`${e.role} ${e.quantity.text}: no legal source`);
      continue;
    }
    if (!pages.has(e.legal.url)) {
      try {
        pages.set(e.legal.url, await policy.fetch(e.legal.url));
      } catch {
        pages.set(e.legal.url, "");
      }
    }
    // A genuine official text of the wrong date is still the wrong law: the pinned version must speak for the claim's date.
    const asOf = a.lawAsOf ?? a.claim.match(/\(law as of (\d{4}-\d{2}-\d{2})\)\s*$/)?.[1];
    const pinned = pointInTimeDate(e.legal.url);
    if (asOf && pinned && (pinned.kind === "exact" ? pinned.date !== asOf : pinned.date > asOf)) {
      reasons.push(`${e.role} ${e.quantity.text}: the pinned official version is dated ${pinned.date}, but the claim relies on the law as of ${asOf}`);
      continue;
    }
    const page = pages.get(e.legal.url)!;
    if (!norm(page).includes(norm(e.legal.quote))) {
      let then = "";
      if (policy.fetchAsOf) then = await policy.fetchAsOf(e.legal.url, e.legal.retrievedAt).catch(() => "");
      if (then && norm(then).includes(norm(e.legal.quote))) soft.push(`${e.role} ${e.quantity.text}: ${e.legal.url} has changed since ${e.legal.retrievedAt}; the quote was there then but is not now`);
      else reasons.push(`${e.role} ${e.quantity.text}: quote not found on ${e.legal.url}`);
      continue;
    }
    // A widened quote also carries sibling tiers' amounts; the claimed amount must be in the clause it ends with.
    if (e.legal.focus && !norm(e.legal.quote).endsWith(norm(e.legal.focus))) {
      reasons.push(`${e.role} ${e.quantity.text}: the focus is not the end of the quoted text`);
      continue;
    }
    if (!extractQuantities(e.legal.focus ?? e.legal.quote).some((x) => sameQuantity(x, e.quantity as Quantity))) {
      reasons.push(`${e.role} ${e.quantity.text}: the quoted clause does not state this quantity`);
      continue;
    }
    if (roleOverlap(e.explainer.sentence, e.legal.quote) < 1) {
      reasons.push(`${e.role} ${e.quantity.text}: the quoted clause is about something else`);
      continue;
    }
    checked.push(`${e.role} ${e.quantity.text}`);
  }
  // A private fact's threshold must be the verified legal limit, not a number the holder chose.
  for (const f of a.privateFacts ?? []) {
    if (f.predicate.premiseIndex === undefined) continue;
    const e = a.evidence[f.predicate.premiseIndex];
    if (!e || !checked.includes(`${e.role} ${e.quantity.text}`)) reasons.push(`private fact "${f.statement}": the legal limit it relies on is not verified`);
    else if (e.quantity.value !== f.predicate.threshold || e.quantity.unit !== f.predicate.unit) reasons.push(`private fact "${f.statement}": threshold ${f.predicate.threshold} is not the verified legal limit ${e.quantity.text}`);
  }
  const needThreshold = a.evidence.filter((e) => e.role === "threshold");
  const outcomeOk = a.evidence.some((e) => e.role === "outcome" && checked.includes(`outcome ${e.quantity.text}`));
  if (!outcomeOk) reasons.push("no outcome premise verified");
  for (const e of needThreshold) if (!checked.includes(`threshold ${e.quantity.text}`) && !soft.some((x) => x.startsWith(`threshold ${e.quantity.text}:`))) reasons.push(`threshold ${e.quantity.text} not verified`);
  // A changed source explains a missing outcome; it does not make it verified.
  if (!outcomeOk && soft.some((x) => x.startsWith("outcome "))) reasons.splice(reasons.indexOf("no outcome premise verified"), 1);

  // 4. Judgments: re-asked with the receiver's own judge (a different model family where possible).
  if (policy.judge && a.judgments?.length) {
    const replays = await replayReceipts(a.judgments, policy.judge);
    const altered = replays.filter((r) => r.note?.startsWith("digest mismatch"));
    if (altered.length) reasons.push(`${altered.length} judgment receipt(s) do not match their digests`);
    const disagree = replays.filter((r) => !r.agree && !r.note);
    for (const d of disagree) soft.push(`judgment ${d.purpose}/${d.name}: sender ${fmt(d.original)}, receiver's ${policy.judge.id} ${d.replayed ? fmt(d.replayed) : "no answer"}`);
    checked.push(`judgments replayed with ${policy.judge.id}: ${replays.length - disagree.length - altered.length}/${replays.length} agree`);
  }
  if (reasons.length) return { decision: "REJECT", reasons: [...new Set(reasons)], checked };
  return soft.length ? { decision: "NEEDS_INFO", reasons: soft, checked } : { decision: "ACCEPT", reasons: [], checked };
}
