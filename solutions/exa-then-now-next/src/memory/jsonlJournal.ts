import { appendFile, readFile } from "node:fs/promises";
import type { JournalStore, Op } from "./evidenceMemory.ts";

/** Durable append-only journal as JSON Lines (Node). One op per line; never rewritten. */
export class JsonlJournal implements JournalStore {
  private readonly path: string;
  constructor(path: string) {
    this.path = path;
  }
  async load(): Promise<Op[]> {
    try {
      return (await readFile(this.path, "utf8")).split("\n").filter(Boolean).map((l) => JSON.parse(l) as Op);
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
      throw err;
    }
  }
  async append(op: Op): Promise<void> {
    await appendFile(this.path, `${JSON.stringify(op)}\n`, { encoding: "utf8", flag: "a" });
  }
}
