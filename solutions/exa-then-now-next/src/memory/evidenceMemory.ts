/**
 * Evidence memory for agents: verified claims, not text chunks.
 *
 *  ECRE (valmet-truth-engine): versioned records with revision, parents and status;
 *                              proposals are never counted as verified facts.
 *  JUURI:                      append-only operation journal with hybrid logical clocks (HLC),
 *                              tombstones instead of deletes, deterministic replay.
 *  SAMPO:                      tenant-scoped hybrid retrieval (BM25 + optional dense, RRF) and typed
 *                              write outcomes (committed / duplicate / conflict / rejected / unknown).
 *  reality-twin:               a record is usable only inside its validity window.
 *  Exa Monitors:               a changed source marks its records needs_recheck until re-verified.
 *
 * Adapters for the real SAMPO and JUURI engines can implement JournalStore and the query interface.
 */
import { canonicalJson, sha256Hex } from "../lib/council.ts";
import type { TwoLaneResult } from "../warrant/compile.ts";
import type { Quantity } from "../warrant/lanes.ts";

export type MemoryStatus = "proposed" | "verified" | "needs_recheck" | "retired" | "superseded";

export interface ClaimRecord {
  id: string;
  tenant: string;
  revision: number;
  status: MemoryStatus;
  role: "threshold" | "outcome";
  statement: string;
  quantity: Pick<Quantity, "kind" | "value" | "unit" | "text">;
  instrument?: string;
  jurisdiction?: string;
  source?: { url: string; quote: string; quoteSha256: string; retrievedAt: string };
  validFrom?: string;
  validUntil?: string;
  provenance: { question: string; compilerCommit?: string; transcriptRoot?: string };
  hlc: string;
}

export interface Op {
  opId: string;
  hlc: string;
  tenant: string;
  kind: "upsert" | "set_status";
  claimId: string;
  baseRevision: number;
  record?: Omit<ClaimRecord, "revision" | "hlc">;
  status?: MemoryStatus;
  reason?: string;
  prevHash: string;
  hash: string;
}

export interface JournalStore {
  load(): Promise<Op[]>;
  append(op: Op): Promise<void>;
}

export class MemoryJournal implements JournalStore {
  ops: Op[] = [];
  async load() {
    return [...this.ops];
  }
  async append(op: Op) {
    this.ops.push(op);
  }
}

export type WriteOutcome =
  | { outcome: "committed"; record: ClaimRecord }
  | { outcome: "duplicate"; record: ClaimRecord }
  | { outcome: "conflict"; current: ClaimRecord }
  | { outcome: "rejected"; reason: string }
  | { outcome: "unknown"; reason: string };

// ---------- hybrid logical clock ----------

export class Hlc {
  private wall = 0;
  private counter = 0;
  private readonly node: string;
  private readonly clock: () => number;
  constructor(node: string, clock: () => number = () => Date.now()) {
    this.node = node;
    this.clock = clock;
  }
  /** Monotonic even if the wall clock steps backwards. */
  tick(): string {
    const now = this.clock();
    if (now > this.wall) {
      this.wall = now;
      this.counter = 0;
    } else this.counter++;
    return Hlc.format(this.wall, this.counter, this.node);
  }
  observe(remote: string) {
    const [w, c] = remote.split(".").map(Number) as [number, number];
    if (w > this.wall || (w === this.wall && c >= this.counter)) {
      this.wall = w;
      this.counter = c;
    }
  }
  static format(wall: number, counter: number, node: string) {
    return `${String(wall).padStart(15, "0")}.${String(counter).padStart(6, "0")}.${node}`;
  }
}

// ---------- retrieval ----------

const tokens = (s: string) => (s.toLowerCase().normalize("NFKC").match(/[\p{L}\p{N}]{2,}/gu) ?? []);

function bm25(query: string, docs: Array<{ id: string; text: string }>, k1 = 1.2, b = 0.75): Map<string, number> {
  const q = [...new Set(tokens(query))];
  const toks = docs.map((d) => tokens(d.text));
  const avg = toks.reduce((s, t) => s + t.length, 0) / Math.max(1, toks.length);
  const df = new Map<string, number>();
  for (const t of toks) for (const w of new Set(t)) df.set(w, (df.get(w) ?? 0) + 1);
  const scores = new Map<string, number>();
  docs.forEach((d, i) => {
    const t = toks[i]!;
    let s = 0;
    for (const w of q) {
      const f = t.filter((x) => x === w).length;
      if (!f) continue;
      const idf = Math.log(1 + (docs.length - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5));
      s += (idf * f * (k1 + 1)) / (f + k1 * (1 - b + (b * t.length) / avg));
    }
    if (s > 0) scores.set(d.id, s);
  });
  return scores;
}

export type DenseFn = (text: string) => Promise<number[]>;
const cosine = (a: number[], b: number[]) => {
  let d = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    d += a[i]! * b[i]!;
    na += a[i]! ** 2;
    nb += b[i]! ** 2;
  }
  return na && nb ? d / Math.sqrt(na * nb) : 0;
};

export interface QueryOptions {
  /** Only records usable on this date are returned (validity window, verified status). */
  at: string;
  k?: number;
  includeUnusable?: boolean;
  dense?: DenseFn;
}

// ---------- the memory ----------

export class EvidenceMemory {
  private records = new Map<string, ClaimRecord>(); // tenant|id -> current revision
  private lastHash = "0".repeat(64);
  private readonly hlc: Hlc;
  private readonly journal: JournalStore;

  constructor(node: string, journal: JournalStore = new MemoryJournal(), clock?: () => number) {
    this.hlc = new Hlc(node, clock);
    this.journal = journal;
  }

  /** Rebuild state from the journal; throws if the hash chain was altered. */
  async replay(): Promise<number> {
    this.records.clear();
    this.lastHash = "0".repeat(64);
    const ops = await this.journal.load();
    for (const op of ops) {
      const { hash, ...rest } = op;
      if (rest.prevHash !== this.lastHash || (await sha256Hex(canonicalJson(rest))) !== hash) throw new Error(`journal tampered at op ${op.opId}`);
      this.apply(op);
      this.lastHash = hash;
      this.hlc.observe(op.hlc);
    }
    return ops.length;
  }

  get(tenant: string, id: string): ClaimRecord | undefined {
    return this.records.get(`${tenant}|${id}`);
  }

  private apply(op: Op) {
    const key = `${op.tenant}|${op.claimId}`;
    const cur = this.records.get(key);
    if (op.kind === "upsert" && op.record) this.records.set(key, { ...op.record, revision: (cur?.revision ?? 0) + 1, hlc: op.hlc });
    if (op.kind === "set_status" && cur && op.status) this.records.set(key, { ...cur, status: op.status, revision: cur.revision + 1, hlc: op.hlc });
  }

  private async commit(partial: Omit<Op, "opId" | "hlc" | "prevHash" | "hash">): Promise<Op> {
    const hlc = this.hlc.tick();
    const unsigned = { ...partial, hlc, opId: `${partial.tenant}:${partial.claimId}:${hlc}`, prevHash: this.lastHash };
    const op: Op = { ...unsigned, hash: await sha256Hex(canonicalJson(unsigned)) };
    await this.journal.append(op);
    this.apply(op);
    this.lastHash = op.hash;
    return op;
  }

  /** Optimistic write: pass the revision you read (0 for new). Verified records need a source quote. */
  async write(record: Omit<ClaimRecord, "revision" | "hlc">, baseRevision: number): Promise<WriteOutcome> {
    if (record.status === "verified" && (!record.source?.quote || !record.source.url)) return { outcome: "rejected", reason: "a verified claim needs a source URL and a verbatim quote" };
    if (record.source && record.source.quoteSha256 !== (await sha256Hex(record.source.quote))) return { outcome: "rejected", reason: "quote hash does not match the quote" };
    const cur = this.get(record.tenant, record.id);
    if ((cur?.revision ?? 0) !== baseRevision) return { outcome: "conflict", current: cur! };
    if (cur && canonicalJson({ ...cur, revision: 0, hlc: "" }) === canonicalJson({ ...record, revision: 0, hlc: "" })) return { outcome: "duplicate", record: cur };
    try {
      await this.commit({ tenant: record.tenant, kind: "upsert", claimId: record.id, baseRevision, record });
    } catch (err) {
      return { outcome: "unknown", reason: (err as Error).message };
    }
    return { outcome: "committed", record: this.get(record.tenant, record.id)! };
  }

  async setStatus(tenant: string, id: string, status: MemoryStatus, reason: string): Promise<WriteOutcome> {
    const cur = this.get(tenant, id);
    if (!cur) return { outcome: "rejected", reason: "no such claim" };
    await this.commit({ tenant, kind: "set_status", claimId: id, baseRevision: cur.revision, status, reason });
    return { outcome: "committed", record: this.get(tenant, id)! };
  }

  /** Exa Monitors (or any change signal): every record citing this URL needs re-verification. */
  async sourceChanged(url: string): Promise<string[]> {
    const hit = [...this.records.values()].filter((r) => r.source?.url === url && r.status === "verified");
    for (const r of hit) await this.setStatus(r.tenant, r.id, "needs_recheck", `source changed: ${url}`);
    return hit.map((r) => r.id);
  }

  /**
   * URL watch. Exa Monitors watch queries, not URLs, so re-fetch every cited page live
   * (Exa /contents with maxAgeHours: 0) and mark records whose quote is gone as needs_recheck.
   * Comparing the quote rather than a page hash ignores layout and navigation churn.
   */
  async recheckSources(fetchLive: (url: string) => Promise<string>): Promise<{ checked: number; changed: string[]; unreachable: string[] }> {
    const norm = (s: string) => s.normalize("NFKC").replace(/[‘’]/g, "'").replace(/\s+/g, " ").trim().toLowerCase();
    const byUrl = new Map<string, ClaimRecord[]>();
    for (const r of this.records.values()) if (r.status === "verified" && r.source) byUrl.set(r.source.url, [...(byUrl.get(r.source.url) ?? []), r]);
    const changed: string[] = [];
    const unreachable: string[] = [];
    for (const [url, rs] of byUrl) {
      let page = "";
      try {
        page = norm(await fetchLive(url));
      } catch {
        unreachable.push(url);
        continue;
      }
      for (const r of rs) {
        if (page.includes(norm(r.source!.quote))) continue;
        await this.setStatus(r.tenant, r.id, "needs_recheck", `quote no longer on ${url}`);
        changed.push(r.id);
      }
    }
    return { checked: byUrl.size, changed, unreachable };
  }

  usable(r: ClaimRecord, at: string): boolean {
    return r.status === "verified" && (!r.validFrom || at >= r.validFrom) && (!r.validUntil || at < r.validUntil);
  }

  /** Tenant-scoped hybrid retrieval: BM25 over statement + quote + instrument, optional dense ranking, fused by RRF. */
  async query(tenant: string, text: string, opts: QueryOptions): Promise<Array<{ record: ClaimRecord; score: number }>> {
    const pool = [...this.records.values()].filter((r) => r.tenant === tenant && (opts.includeUnusable || this.usable(r, opts.at)));
    const docs = pool.map((r) => ({ id: r.id, text: `${r.statement} ${r.source?.quote ?? ""} ${r.instrument ?? ""} ${r.jurisdiction ?? ""}` }));
    const lexical = [...bm25(text, docs)].sort((a, b) => b[1] - a[1]).map(([id]) => id);
    let dense: string[] = [];
    if (opts.dense) {
      const qv = await opts.dense(text);
      const scored = await Promise.all(docs.map(async (d) => [d.id, cosine(qv, await opts.dense!(d.text))] as const));
      dense = scored.filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1]).map(([id]) => id);
    }
    const rrf = new Map<string, number>();
    for (const list of [lexical, dense]) list.forEach((id, i) => rrf.set(id, (rrf.get(id) ?? 0) + 1 / (60 + i + 1)));
    return [...rrf]
      .sort((a, b) => b[1] - a[1])
      .slice(0, opts.k ?? 5)
      .map(([id, score]) => ({ record: pool.find((r) => r.id === id)!, score }));
  }
}

/** Turn the confirmed premises of a compilation into verified memory records. */
export async function recordsFromCompile(
  r: TwoLaneResult,
  ctx: { tenant: string; jurisdiction?: string; validFrom?: string; validUntil?: string; compilerCommit?: string; transcriptRoot?: string },
): Promise<Array<Omit<ClaimRecord, "revision" | "hlc">>> {
  const out: Array<Omit<ClaimRecord, "revision" | "hlc">> = [];
  for (const c of r.premises) {
    if (!c.status.startsWith("confirmed") || c.triangulation.status !== "agree") continue;
    const q = c.premise.quantity;
    const id = await sha256Hex(canonicalJson({ tenant: ctx.tenant, jurisdiction: ctx.jurisdiction ?? "", instrument: r.extraction.instrument ?? "", role: c.premise.role, kind: q.kind, unit: q.unit, value: q.value }));
    out.push({
      id: id.slice(0, 32),
      tenant: ctx.tenant,
      status: "verified",
      role: c.premise.role,
      statement: c.premise.sentence,
      quantity: { kind: q.kind, value: q.value, unit: q.unit, text: q.text },
      instrument: r.extraction.instrument,
      jurisdiction: ctx.jurisdiction,
      source: { url: c.triangulation.url, quote: c.triangulation.quote, quoteSha256: await sha256Hex(c.triangulation.quote), retrievedAt: c.rule?.source.retrievedAt ?? new Date().toISOString() },
      validFrom: ctx.validFrom,
      validUntil: ctx.validUntil,
      provenance: { question: r.question, compilerCommit: ctx.compilerCommit, transcriptRoot: ctx.transcriptRoot },
    });
  }
  return out;
}
