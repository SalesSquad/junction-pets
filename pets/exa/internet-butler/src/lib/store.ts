import { openDB, type IDBPDatabase } from "idb";
import type { OutcomeLedger } from "./butler.ts";
import { MemoryCouncilStore, type CouncilStore, type Receipt } from "./council.ts";
import type { Capability, GrantMode } from "./types.ts";

/**
 * Local-first persistence: grants, the receipt chain and learned source outcomes live in
 * IndexedDB on this device. Nothing here is synced anywhere.
 */

interface Outcome {
  domain: string;
  approved: number;
  rejected: number;
}

const DB_NAME = "internet-butler";

async function open(): Promise<IDBPDatabase | null> {
  if (typeof indexedDB === "undefined") return null;
  return openDB(DB_NAME, 1, {
    upgrade(db) {
      db.createObjectStore("kv");
      db.createObjectStore("receipts", { keyPath: "seq" });
      db.createObjectStore("outcomes", { keyPath: "domain" });
    },
  });
}

class IdbCouncilStore implements CouncilStore {
  private db: IDBPDatabase;
  constructor(db: IDBPDatabase) {
    this.db = db;
  }
  async loadGrants() {
    return ((await this.db.get("kv", "grants")) ?? {}) as Partial<Record<Capability, GrantMode>>;
  }
  async saveGrants(grants: Record<Capability, GrantMode>) {
    await this.db.put("kv", grants, "grants");
  }
  async loadReceipts() {
    return (await this.db.getAll("receipts")) as Receipt[];
  }
  async appendReceipt(receipt: Receipt) {
    // `add` (not `put`) refuses to overwrite an existing sequence number.
    await this.db.add("receipts", receipt);
  }
}

class IdbOutcomeLedger implements OutcomeLedger {
  private cache = new Map<string, Outcome>();
  private db: IDBPDatabase | null;
  constructor(db: IDBPDatabase | null) {
    this.db = db;
  }
  async init() {
    if (!this.db) return;
    for (const o of (await this.db.getAll("outcomes")) as Outcome[]) this.cache.set(o.domain, o);
  }
  /** Small, bounded ranking bonus from sources the user approved before. */
  bonus(domain: string): number {
    const o = this.cache.get(domain);
    if (!o) return 0;
    return Math.max(-0.1, Math.min(0.1, 0.02 * (o.approved - o.rejected)));
  }
  async record(domains: string[], approved: boolean) {
    for (const domain of domains) {
      const o = this.cache.get(domain) ?? { domain, approved: 0, rejected: 0 };
      const next = { ...o, approved: o.approved + (approved ? 1 : 0), rejected: o.rejected + (approved ? 0 : 1) };
      this.cache.set(domain, next);
      await this.db?.put("outcomes", next);
    }
  }
}

export async function openLocalStores(): Promise<{ councilStore: CouncilStore; outcomes: IdbOutcomeLedger; persistent: boolean }> {
  const db = await open().catch(() => null);
  const outcomes = new IdbOutcomeLedger(db);
  await outcomes.init();
  return { councilStore: db ? new IdbCouncilStore(db) : new MemoryCouncilStore(), outcomes, persistent: !!db };
}

export async function wipeLocalData(): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  await new Promise<void>((resolve) => {
    const req = indexedDB.deleteDatabase(DB_NAME);
    req.onsuccess = req.onerror = req.onblocked = () => resolve();
  });
}
