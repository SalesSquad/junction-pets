import { canonicalJson, sha256Hex } from "../lib/council.ts";

/**
 * Commit-and-audit against cherry-picking.
 *
 * The sender commits to its whole retrieval transcript (every query and every returned
 * source) with a Merkle root, reveals only the evidence it uses, and must open any leaf the
 * receiver challenges. If a fraction f of leaves are undisclosed contradictions, k random
 * challenges detect at least one with probability 1 - (1 - f)^k.
 *
 * Hashing follows RFC 6962 domain separation: leaf = H(0x00 || data), node = H(0x01 || l || r).
 */

export interface TranscriptLeaf {
  query: string;
  url: string;
  /** Hash of the retrieved text (highlights or page), so an opened leaf cannot be swapped. */
  contentHash: string;
  rank: number;
}

const hex = (b: Uint8Array) => [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
const unhex = (s: string) => new Uint8Array(s.match(/../g)!.map((h) => parseInt(h, 16)));

async function h(prefix: number, ...parts: Uint8Array[]): Promise<string> {
  const total = parts.reduce((n, p) => n + p.length, 1);
  const buf = new Uint8Array(total);
  buf[0] = prefix;
  let off = 1;
  for (const p of parts) {
    buf.set(p, off);
    off += p.length;
  }
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", buf)));
}

export const leafHash = (leaf: TranscriptLeaf) => h(0x00, new TextEncoder().encode(canonicalJson(leaf)));
const nodeHash = (l: string, r: string) => h(0x01, unhex(l), unhex(r));

export interface Commitment {
  root: string;
  size: number;
  levels: string[][];
}

export async function commit(leaves: TranscriptLeaf[]): Promise<Commitment> {
  if (!leaves.length) throw new Error("empty transcript");
  let level = await Promise.all(leaves.map(leafHash));
  const levels = [level];
  while (level.length > 1) {
    const next: string[] = [];
    for (let i = 0; i < level.length; i += 2) {
      // An odd node is promoted unchanged (RFC 6962 style, no duplication).
      next.push(i + 1 < level.length ? await nodeHash(level[i]!, level[i + 1]!) : level[i]!);
    }
    levels.push(next);
    level = next;
  }
  return { root: level[0]!, size: leaves.length, levels };
}

export interface InclusionProof {
  index: number;
  path: Array<{ hash: string; side: "left" | "right" }>;
}

export function prove(c: Commitment, index: number): InclusionProof {
  const path: InclusionProof["path"] = [];
  let i = index;
  for (let d = 0; d < c.levels.length - 1; d++) {
    const level = c.levels[d]!;
    const sibling = i % 2 === 0 ? i + 1 : i - 1;
    if (sibling < level.length) path.push({ hash: level[sibling]!, side: i % 2 === 0 ? "right" : "left" });
    i = Math.floor(i / 2);
  }
  return { index, path };
}

export async function verifyInclusion(root: string, leaf: TranscriptLeaf, proof: InclusionProof): Promise<boolean> {
  let acc = await leafHash(leaf);
  for (const step of proof.path) acc = step.side === "right" ? await nodeHash(acc, step.hash) : await nodeHash(step.hash, acc);
  return acc === root;
}

/**
 * The receiver picks k leaf indices from its own nonce, after the sender has committed,
 * so the sender cannot know in advance which unused sources will be opened.
 */
export async function challengeIndices(root: string, receiverNonce: string, size: number, k: number, exclude: Set<number>): Promise<number[]> {
  const candidates = [...Array(size).keys()].filter((i) => !exclude.has(i));
  const picked: number[] = [];
  let counter = 0;
  while (picked.length < Math.min(k, candidates.length)) {
    const digest = await sha256Hex(`${root}|${receiverNonce}|${counter++}`);
    const idx = candidates[parseInt(digest.slice(0, 12), 16) % candidates.length]!;
    if (!picked.includes(idx)) picked.push(idx);
  }
  return picked;
}

/** Probability that k random challenges hit at least one undisclosed contradiction. */
export function detectionProbability(fractionContradicting: number, k: number): number {
  return 1 - (1 - fractionContradicting) ** k;
}
