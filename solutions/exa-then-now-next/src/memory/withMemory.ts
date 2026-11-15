import { compileTwoLane, type CompileOptions, type TwoLaneResult } from "../warrant/compile.ts";
import { kindHints, type FetchFn, type QuantityKind, type SearchFn } from "../warrant/lanes.ts";
import { EvidenceMemory, recordsFromCompile, type ClaimRecord } from "./evidenceMemory.ts";

export type MemoryAnswer =
  | { source: "memory"; records: ClaimRecord[] }
  | { source: "web"; result: TwoLaneResult; stored: number };

/**
 * Answer from verified, still-valid memory when it covers the question's outcome kind; otherwise
 * compile from the web and store the confirmed premises. Memory never answers with an unverified,
 * expired or needs_recheck record.
 */
export async function compileWithMemory(
  question: string,
  memory: EvidenceMemory,
  ctx: { tenant: string; at: string; jurisdiction?: string; validUntil?: string; compilerCommit?: string },
  search: SearchFn,
  fetch: FetchFn,
  opts: CompileOptions = {},
): Promise<MemoryAnswer> {
  const hints = Object.entries(kindHints(question)).sort((a, b) => b[1] - a[1]);
  const wanted = hints[0]?.[0] as QuantityKind | undefined;
  const hits = (await memory.query(ctx.tenant, question, { at: ctx.at, k: 5 })).map((h) => h.record);
  const outcome = hits.find((r) => r.role === "outcome" && (!wanted || r.quantity.kind === wanted) && (!ctx.jurisdiction || r.jurisdiction === ctx.jurisdiction));
  if (outcome) return { source: "memory", records: [outcome, ...hits.filter((r) => r.role === "threshold" && r.instrument === outcome.instrument)] };
  const result = await compileTwoLane(question, search, fetch, opts);
  let stored = 0;
  if (result.outcome === "GROUNDED") {
    for (const rec of await recordsFromCompile(result, ctx)) {
      const cur = memory.get(rec.tenant, rec.id);
      const w = await memory.write(rec, cur?.revision ?? 0);
      if (w.outcome === "committed") stored++;
    }
  }
  return { source: "web", result, stored };
}
