import type { Capability, GrantMode } from "./types.ts";

/**
 * Permission council: every egress call and every side-effecting action passes `check()`.
 * Decisions are written to an append-only, hash-chained receipt log, so a revoked grant
 * provably blocks the next call and the log shows it.
 */

export type ReceiptKind = "grant" | "revoke" | "allowed" | "denied" | "approval_requested" | "approved" | "rejected";

export interface Receipt {
  seq: number;
  at: string;
  kind: ReceiptKind;
  capability: Capability;
  subject: string;
  /** Names of the fields that left the device (egress only). Values are never stored. */
  fields?: string[];
  bytes?: number;
  payloadHash?: string;
  prevHash: string;
  hash: string;
}

export interface CouncilStore {
  loadGrants(): Promise<Partial<Record<Capability, GrantMode>>>;
  saveGrants(grants: Record<Capability, GrantMode>): Promise<void>;
  loadReceipts(): Promise<Receipt[]>;
  appendReceipt(receipt: Receipt): Promise<void>;
}

export const DEFAULT_GRANTS: Record<Capability, GrantMode> = {
  "exa.search": "allow",
  "exa.contents": "allow",
  "typesafe.judge": "allow",
  // The hosted writer gets the question and the public sources, never the user's document.
  "writer.hosted": "allow",
  // Sending on the user's behalf always needs an explicit click, whatever a model says.
  "action.send": "ask",
};

const GENESIS = "0".repeat(64);

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Stable JSON: keys sorted, so the same receipt always hashes the same way. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
}

export class Council {
  private grants: Record<Capability, GrantMode> = { ...DEFAULT_GRANTS };
  private receipts: Receipt[] = [];
  private listeners = new Set<() => void>();
  private queue: Promise<unknown> = Promise.resolve();

  private readonly store: CouncilStore;
  private readonly now: () => Date;

  constructor(store: CouncilStore, now: () => Date = () => new Date()) {
    this.store = store;
    this.now = now;
  }

  async init(): Promise<void> {
    this.grants = { ...DEFAULT_GRANTS, ...(await this.store.loadGrants()) };
    this.receipts = await this.store.loadReceipts();
  }

  onChange(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  getGrants(): Readonly<Record<Capability, GrantMode>> {
    return this.grants;
  }

  getReceipts(): readonly Receipt[] {
    return this.receipts;
  }

  async setGrant(capability: Capability, mode: GrantMode): Promise<Receipt> {
    this.grants = { ...this.grants, [capability]: mode };
    await this.store.saveGrants(this.grants);
    return this.append({ kind: mode === "deny" ? "revoke" : "grant", capability, subject: `mode=${mode}` });
  }

  /**
   * Decide an egress call. `allow` passes; `ask` and `deny` block egress (egress has no
   * interactive prompt in this app, so anything but `allow` stops it).
   */
  async checkEgress(
    capability: Capability,
    subject: string,
    payload: unknown,
  ): Promise<{ allowed: boolean; receipt: Receipt }> {
    const body = canonicalJson(payload);
    const fields = payload && typeof payload === "object" ? Object.keys(payload as object).sort() : [];
    const payloadHash = await sha256Hex(body);
    const allowed = this.grants[capability] === "allow";
    const receipt = await this.append({
      kind: allowed ? "allowed" : "denied",
      capability,
      subject: allowed ? subject : `${subject} (grant is ${this.grants[capability]})`,
      fields,
      bytes: new TextEncoder().encode(body).length,
      payloadHash,
    });
    return { allowed, receipt };
  }

  /**
   * Decide a side-effecting action. `deny` blocks; `ask` requires `userApproved`, which must
   * come from an explicit user gesture, never from a model's reading of the user's words.
   */
  async checkAction(
    capability: Capability,
    subject: string,
    userApproved: boolean,
    payload?: unknown,
  ): Promise<{ allowed: boolean; receipt: Receipt }> {
    const mode = this.grants[capability];
    // The receipt binds the decision to the exact payload, so what was approved is provably what was sent.
    const payloadHash = payload === undefined ? undefined : await sha256Hex(canonicalJson(payload));
    if (mode === "deny") {
      return { allowed: false, receipt: await this.append({ kind: "denied", capability, subject: `${subject} (revoked)`, payloadHash }) };
    }
    if (mode === "ask" && !userApproved) {
      return { allowed: false, receipt: await this.append({ kind: "approval_requested", capability, subject, payloadHash }) };
    }
    return { allowed: true, receipt: await this.append({ kind: "approved", capability, subject, payloadHash }) };
  }

  async recordRejected(capability: Capability, subject: string): Promise<Receipt> {
    return this.append({ kind: "rejected", capability, subject });
  }

  /** Recompute every hash; returns the first broken sequence number, or null when intact. */
  async verifyChain(): Promise<number | null> {
    let prev = GENESIS;
    for (const r of this.receipts) {
      const { hash, ...rest } = r;
      if (rest.prevHash !== prev) return r.seq;
      if ((await sha256Hex(canonicalJson(rest))) !== hash) return r.seq;
      prev = hash;
    }
    return null;
  }

  private append(entry: Omit<Receipt, "seq" | "at" | "prevHash" | "hash">): Promise<Receipt> {
    // Serialize appends so concurrent checks cannot fork the chain.
    const next = this.queue.then(async () => {
      const last = this.receipts.at(-1);
      const unsigned = {
        ...entry,
        seq: (last?.seq ?? 0) + 1,
        at: this.now().toISOString(),
        prevHash: last?.hash ?? GENESIS,
      };
      const receipt: Receipt = { ...unsigned, hash: await sha256Hex(canonicalJson(unsigned)) };
      await this.store.appendReceipt(receipt);
      this.receipts = [...this.receipts, receipt];
      this.listeners.forEach((fn) => fn());
      return receipt;
    });
    this.queue = next.catch(() => undefined);
    return next;
  }
}

/** In-memory store for tests and for browsers without IndexedDB. */
export class MemoryCouncilStore implements CouncilStore {
  grants: Partial<Record<Capability, GrantMode>> = {};
  receipts: Receipt[] = [];
  async loadGrants() {
    return { ...this.grants };
  }
  async saveGrants(grants: Record<Capability, GrantMode>) {
    this.grants = { ...grants };
  }
  async loadReceipts() {
    return [...this.receipts];
  }
  async appendReceipt(receipt: Receipt) {
    this.receipts.push(receipt);
  }
}
