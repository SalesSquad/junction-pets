#!/usr/bin/env node
// Warrant end to end: compile -> sign -> receiver verifies -> person revokes -> receiver rejects.
// Usage: node bench/warrant-demo.mjs ["question"]        live (Exa keyless MCP or an API key)
//        node bench/warrant-demo.mjs --offline           SYNTHETIC fixture (no network)
//        add --judge to use a typed judge (OpenAI Decisions gpt-6-luna; the receiver replays with
//        TypeSafe Jev when TYPESAFE_API_KEY is set, otherwise with Luna)
import { exaMcpFetch, exaMcpSearch } from "../relay/exa-mcp.mjs";
import { buildArtifact, generateDeviceKey, verifyArtifact } from "../src/warrant/artifact.ts";
import { compileTwoLane } from "../src/warrant/compile.ts";
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { openaiDecisions, typesafeJev } from "../src/decide/decide.ts";

const offline = process.argv.includes("--offline");
const useJudge = process.argv.includes("--judge");
const keyFrom = (f, n) => { try { return readFileSync(f, "utf8").match(new RegExp(`^${n}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
const oaKey = process.env.OPENAI_API_KEY || keyFrom(`${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY");
const senderJudge = useJudge && oaKey ? openaiDecisions({ apiKey: oaKey }) : undefined;
let receiverJudge = senderJudge;
if (useJudge && process.env.TYPESAFE_API_KEY) {
  const { TypeSafeClient } = await import("@typesafe-ai/sdk");
  const ts = new TypeSafeClient({ apiKey: process.env.TYPESAFE_API_KEY, defaultModel: "jev-1.14.0" });
  receiverJudge = typesafeJev({ systemOne: (r) => ts.systemOne(r) });
}
if (useJudge && !senderJudge) console.log("--judge needs OPENAI_API_KEY (or ~/.config/openai/factory-decisions.env); continuing without a judge.\n");
const question = process.argv.slice(2).find((a) => !a.startsWith("--")) ?? "How much compensation do I get if my 1,500 km EU flight arrives 3 hours late?";

const LEGAL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32004R0261";
const CURIA = "https://curia.europa.eu/sturgeon";
const fixture = {
  answer: [
    { url: "https://consumer.example/eu261", highlights: ["For flights of 1,500 km or less you are entitled to €250 under Regulation (EC) No 261/2004."] },
    { url: "https://claims.example/guide", highlights: ["Passengers on short flights receive EUR 250 when they arrive three hours late."] },
  ],
  pages: {
    [LEGAL]: "Passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres.",
    [CURIA]: "Passengers whose flights are delayed may rely on the right to compensation where they reach their final destination three hours or more after the arrival time originally scheduled by the air carrier.",
  },
};
let calls = 0;
const search = offline
  ? async () => (calls++ === 0 ? fixture.answer : [{ url: LEGAL, highlights: [] }, { url: CURIA, highlights: [] }])
  : async (q, objective) => exaMcpSearch({ query: q, objective, numResults: 5 });
const fetchPage = offline ? async (u) => fixture.pages[u] ?? "" : async (u) => exaMcpFetch({ urls: [u] });

const label = offline ? "SYNTHETIC" : "LIVE";
console.log(`[${label}] ${question}\n`);
const r = await compileTwoLane(question, search, fetchPage, senderJudge ? { decisions: { provider: senderJudge } } : {});
console.log("1. Compile (answer lane -> premises -> authority lane -> triangulation)");
for (const p of r.premises) console.log(`   ${p.premise.role.padEnd(9)} ${p.premise.quantity.text.padEnd(12)} ${p.status.padEnd(26)} ${p.triangulation.status === "agree" ? p.triangulation.url : p.note}`);
if (r.clarify) console.log(`   clarifying question: ${r.clarify.question}\n   options: ${r.clarify.options.join(" | ")}`);
console.log(`   -> ${r.outcome}${r.reasons.length ? ` (${r.reasons.join("; ")})` : ""}`);
if (senderJudge) console.log(`   typed judgments (${senderJudge.id}): ${r.judgments.length} receipts; quarantined ${r.quarantined.length} passage(s)`);
console.log("");

const key = await generateDeviceKey();
const mandate = { subject: "person-7f3a", recipient: "claims.airline.example", purpose: "One compensation claim for one flight", notBefore: new Date(Date.now() - 60_000).toISOString(), expiresAt: new Date(Date.now() + 30 * 864e5).toISOString(), jti: `mandate-${Date.now()}` };
const git = (c) => { try { return execSync(`git ${c}`, { cwd: new URL("..", import.meta.url), encoding: "utf8" }).trim(); } catch { return ""; } };
const compiler = { name: "internet-butler-warrant", version: "0.1.0", commit: git("rev-parse HEAD") || "unknown", dirty: git("status --porcelain") !== "" };
const artifact = await buildArtifact(r, mandate, key, new Date(), compiler);
console.log(`2. Sign on the device (${key.alg}); compiler ${compiler.commit.slice(0, 7)}${compiler.dirty ? " (dirty)" : ""}; transcript Merkle root ${artifact.transcript.root.slice(0, 16)}… over ${artifact.transcript.size} retrieved results\n`);

const revoked = new Set();
const policy = { recipient: "claims.airline.example", revoked, fetch: fetchPage, judge: receiverJudge };
const d1 = await verifyArtifact(artifact, policy);
console.log(`3. Receiver verifies: ${d1.decision}${d1.reasons.length ? ` — ${d1.reasons.join("; ")}` : ""}${d1.question ? ` — asks: ${d1.question}` : ""}\n   checked: ${d1.checked.join(", ")}\n`);

revoked.add(mandate.jti);
const d2 = await verifyArtifact(artifact, policy);
console.log(`4. The person revokes the mandate; receiver verifies again: ${d2.decision} — ${d2.reasons.join("; ")}`);
