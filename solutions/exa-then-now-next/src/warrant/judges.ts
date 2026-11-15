/**
 * Two judges, then the page (benchmark v2, section 4.3).
 *
 * Two independent judges (different model families where possible) label whether a passage
 * supports a premise. If they agree, that is the verdict. If they disagree, no third model is
 * asked: the page is re-fetched and the decision rests on whether the quote, including the
 * decisive quantity, appears verbatim in it.
 */
import { extractQuantities, sameQuantity, type FetchFn, type Quantity } from "./lanes.ts";

export type SupportLabel = "supports" | "contradicts" | "says_nothing";
export type JudgeFn = (premise: string, passage: string) => Promise<SupportLabel>;

export interface SupportDecision {
  verdict: "supported" | "contradicted" | "unsupported";
  by: "judges_agree" | "page_verbatim";
  labels: [SupportLabel, SupportLabel];
  detail?: string;
}

const norm = (s: string) => s.normalize("NFKC").replace(/[‘’]/g, "'").replace(/\s+/g, " ").trim().toLowerCase();

export async function decideSupport(args: {
  premise: string;
  quote: string;
  url: string;
  quantity?: Quantity;
  judges: [JudgeFn, JudgeFn];
  fetch: FetchFn;
}): Promise<SupportDecision> {
  const labels = (await Promise.all(args.judges.map((j) => j(args.premise, args.quote)))) as [SupportLabel, SupportLabel];
  if (labels[0] === labels[1]) {
    const verdict = labels[0] === "supports" ? "supported" : labels[0] === "contradicts" ? "contradicted" : "unsupported";
    return { verdict, by: "judges_agree", labels };
  }
  let page = "";
  try {
    page = await args.fetch(args.url);
  } catch (err) {
    return { verdict: "unsupported", by: "page_verbatim", labels, detail: `page could not be re-fetched: ${(err as Error).message}` };
  }
  const quoteFound = norm(page).includes(norm(args.quote));
  const quantityOk = !args.quantity || extractQuantities(args.quote).some((q) => sameQuantity(q, args.quantity!));
  return quoteFound && quantityOk
    ? { verdict: "supported", by: "page_verbatim", labels, detail: "judges disagreed; quote and quantity found verbatim on the re-fetched page" }
    : { verdict: "unsupported", by: "page_verbatim", labels, detail: quoteFound ? "quote found but it does not state the decisive quantity" : "quote not found on the re-fetched page" };
}
