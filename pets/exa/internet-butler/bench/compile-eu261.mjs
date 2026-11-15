#!/usr/bin/env node
// Live end-to-end Warrant compilation for one errand (EU flight delay, Helsinki -> Berlin, 4 h late).
// 1. citation-completion queries (support, rebuttal, temporal) on Exa
// 2. commit the whole retrieval transcript (Merkle root)
// 3. re-fetch the cited sources and match quotes verbatim
// 4. build the argument graph and let code decide
// Run: NODE_USE_ENV_PROXY=1 node bench/compile-eu261.mjs   (behind a proxy) or plain node.
import { createHash } from "node:crypto";
import { exaMcpFetch, exaMcpSearch } from "../relay/exa-mcp.mjs";
import { evaluate, haversineKm } from "../src/warrant/graph.ts";
import { applicationDate, citationQueries } from "../src/warrant/queries.ts";
import { commit, prove, verifyInclusion } from "../src/warrant/transcript.ts";

const sha = (s) => createHash("sha256").update(s).digest("hex");
const norm = (s) => s.normalize("NFKC").replace(/\s+/g, " ").toLowerCase();
const now = new Date().toISOString();
const objective = "Return the most relevant pages.";

const q = citationQueries({
  premise: "Passengers whose flight of 1,500 kilometres or less arrives three hours or more late are entitled to compensation of EUR 250 under Article 7 of Regulation (EC) No 261/2004.",
  instrument: "Regulation (EC) No 261/2004",
  sourceKind: "regulation",
  exemptionLead: "An air carrier is not obliged to pay compensation",
});

console.log("1. Citation-completion queries");
const runs = {};
for (const [kind, query] of Object.entries(q)) {
  runs[kind] = await exaMcpSearch({ query, objective, numResults: 5 });
  console.log(`   ${kind}: ${runs[kind].map((r) => new URL(r.url).hostname).join(", ")}`);
}

console.log("2. Commit the full retrieval transcript");
const leaves = Object.entries(runs).flatMap(([kind, results]) =>
  results.map((r, rank) => ({ query: q[kind], url: r.url, contentHash: sha(r.highlights.join("\n")), rank })),
);
const c = await commit(leaves);
console.log(`   ${leaves.length} leaves, Merkle root ${c.root.slice(0, 16)}…`);

// The rule source: prefer the instrument's own text (CELEX 32004R0261 / ELI reg/2004/261) over a judgment
// that quotes it; fall back to any EUR-Lex result, then to the first result.
const isInstrument = (u) => /32004R0261|eli\/reg\/2004\/261/i.test(decodeURIComponent(u));
const ruleHit = runs.support.find((r) => isInstrument(r.url)) ?? runs.support.find((r) => r.url.includes("eur-lex.europa.eu")) ?? runs.support[0];
const ruleIdx = leaves.findIndex((l) => l.url === ruleHit.url);
console.log(`   rule source leaf #${ruleIdx} inclusion proof: ${await verifyInclusion(c.root, leaves[ruleIdx], prove(c, ruleIdx))}`);

console.log("3. Re-fetch sources and match quotes verbatim");
const RULE_QUOTE = "EUR 250 for all flights of 1500 kilometres or less";
const EXEMPT_QUOTE = "extraordinary circumstances which could not have been avoided even if all reasonable measures had been taken";
const ruleText = await exaMcpFetch({ urls: [ruleHit.url] });
const ruleOk = norm(ruleText).includes(norm(RULE_QUOTE));
const exemptOk = norm(ruleText).includes(norm(EXEMPT_QUOTE));
console.log(`   ${ruleHit.url}\n   rule quote found: ${ruleOk}; exemption quote found: ${exemptOk}`);

const successor = [...runs.temporal, ...runs.support].find((r) => /eli\/reg\/2026\/2202/.test(r.url))?.url ?? "https://eur-lex.europa.eu/eli/reg/2026/2202/oj/eng";
const successorText = await exaMcpFetch({ urls: [successor] });
const applies = applicationDate(successorText);
console.log(`   successor ${successor}\n   application date found in text: ${applies}`);

console.log("4. Argument graph -> decision (code, not a model)");
const dist = Math.round(haversineKm([60.3172, 24.9633], [52.3667, 13.5033]));
const graph = {
  errand: "My flight Helsinki-Berlin on 2026-11-06 landed 4 hours late",
  eventDate: "2026-11-06",
  nodes: [
    { kind: "rule", id: "r261", instrument: "Regulation (EC) No 261/2004", premise: "Art. 7(1)(a) EUR 250 for flights of 1 500 km or less", source: { url: ruleHit.url, quote: RULE_QUOTE, retrievedAt: now }, validFrom: "2005-02-17", verdict: ruleOk ? "verified" : "failed" },
    { kind: "temporal", id: "succ", rule: "r261", statement: "Regulation (EU) 2026/2202 replaces the regime", source: { url: successor, quote: "It shall apply from 23 October 2027.", retrievedAt: now }, supersededFrom: applies ?? "0000-01-01", verdict: applies ? "verified" : "failed" },
    { kind: "fact", id: "from", statement: "Departure airport", attestation: "user", value: "HEL", verdict: "verified" },
    { kind: "fact", id: "to", statement: "Arrival airport", attestation: "user", value: "BER", verdict: "verified" },
    { kind: "fact", id: "delayH", statement: "Arrival delay (hours)", attestation: "user", value: 4, verdict: "verified" },
    { kind: "computation", id: "dist", statement: "Great-circle distance (km)", fn: "haversineKm", inputs: ["from", "to"], claimed: dist, verdict: "unverified" },
    { kind: "computation", id: "short", statement: "Distance <= 1 500 km", fn: "lte", inputs: ["dist", 1500], claimed: true, verdict: "unverified" },
    { kind: "computation", id: "late", statement: "Delay >= 3 h", fn: "gte", inputs: ["delayH", 3], claimed: true, verdict: "unverified" },
    { kind: "rebuttal", id: "extra", against: "r261", statement: "Carrier exempt only if it proves extraordinary circumstances (Art. 5(3))", source: { url: ruleHit.url, quote: EXEMPT_QUOTE, retrievedAt: now }, status: "allocated", verdict: exemptOk ? "verified" : "failed" },
    { kind: "claim", id: "claim", statement: "Passenger is owed EUR 250 by the operating carrier", rule: "r261", requires: ["from", "to", "delayH", "short", "late"], amount: { value: 250, currency: "EUR" } },
  ],
};
const e = evaluate(graph);
console.log(`   distance ${dist} km · decision ${e.decision}${e.reasons.length ? ` · reasons ${JSON.stringify(e.reasons)}` : ""}`);
if (e.allocatedToReceiver.length) console.log(`   burden on receiver: ${e.allocatedToReceiver.join("; ")}`);
const later = evaluate({ ...graph, eventDate: "2027-11-01" });
console.log(`   same claim for a flight on 2027-11-01: ${later.decision} (${later.reasons.map((r) => r.reason).join("; ")})`);
