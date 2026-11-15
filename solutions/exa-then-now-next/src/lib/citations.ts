import type { Claim, Evidence } from "./types.ts";

/**
 * Deterministic first pass of the citation check (TypeSafe citation-check cookbook):
 * a quote that does not appear in its cited source is fabricated, and no model is asked.
 */

export function normalizeForMatch(s: string): string {
  return s
    .normalize("NFKC")
    .replace(/[‘’‚‛]/g, "'")
    .replace(/[“”„‟]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

export function markFabricated(claims: Claim[], evidence: Evidence[]): Claim[] {
  const byId = new Map(evidence.map((e) => [e.id, normalizeForMatch(e.highlights.join(" \n "))]));
  return claims.map((c) => {
    const source = byId.get(c.sourceId);
    const quote = normalizeForMatch(c.quote);
    if (!source || quote.length < 8 || !source.includes(quote)) {
      return { ...c, verdict: "fabricated" as const, needsReview: true };
    }
    return c;
  });
}
