import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { sha256Hex } from "../src/lib/council.ts";
import { EvidenceMemory, Hlc, MemoryJournal, type ClaimRecord } from "../src/memory/evidenceMemory.ts";
import { JsonlJournal } from "../src/memory/jsonlJournal.ts";

const QUOTE = "EUR 250 for all flights of 1500 kilometres or less";
const rec = async (over: Partial<Omit<ClaimRecord, "revision" | "hlc">> = {}): Promise<Omit<ClaimRecord, "revision" | "hlc">> => ({
  id: "eu261-outcome-250",
  tenant: "person-7f3a",
  status: "verified",
  role: "outcome",
  statement: "Passengers on flights of 1,500 km or less are entitled to €250 compensation.",
  quantity: { kind: "money", value: 250, unit: "EUR", text: "€250" },
  instrument: "Regulation (EC) No 261/2004",
  jurisdiction: "EU",
  source: { url: "https://eur-lex.europa.eu/eli/reg/2004/261/oj/eng", quote: QUOTE, quoteSha256: await sha256Hex(QUOTE), retrievedAt: "2026-11-14T05:00:00Z" },
  validFrom: "2005-02-17",
  validUntil: "2027-10-23",
  provenance: { question: "How much compensation for a 3-hour delay on a 1,500 km flight?" },
  ...over,
});

test("verified claims are recalled only inside their validity window and for their tenant", async () => {
  const m = new EvidenceMemory("mbp");
  assert.equal((await m.write(await rec(), 0)).outcome, "committed");
  const hit = await m.query("person-7f3a", "flight delay compensation 1500 km", { at: "2026-11-14" });
  assert.equal(hit[0]?.record.quantity.value, 250);
  assert.equal((await m.query("person-7f3a", "flight compensation", { at: "2027-11-01" })).length, 0, "superseded from 23 Oct 2027");
  assert.equal((await m.query("someone-else", "flight compensation", { at: "2026-11-14" })).length, 0, "tenant isolation");
});

test("typed write outcomes: rejected without a quote, duplicate, conflict on a stale revision", async () => {
  const m = new EvidenceMemory("mbp");
  const noQuote = await rec({ source: undefined });
  assert.equal((await m.write(noQuote, 0)).outcome, "rejected");
  const badHash = await rec();
  badHash.source!.quoteSha256 = "0".repeat(64);
  assert.equal((await m.write(badHash, 0)).outcome, "rejected");
  await m.write(await rec(), 0);
  assert.equal((await m.write(await rec(), 1)).outcome, "duplicate");
  assert.equal((await m.write(await rec({ statement: "changed" }), 0)).outcome, "conflict");
  assert.equal((await m.write(await rec({ statement: "changed" }), 1)).outcome, "committed");
  assert.equal(m.get("person-7f3a", "eu261-outcome-250")?.revision, 2);
});

test("a changed source marks its claims needs_recheck; they are not recalled until re-verified", async () => {
  const m = new EvidenceMemory("mbp");
  await m.write(await rec(), 0);
  assert.deepEqual(await m.sourceChanged("https://eur-lex.europa.eu/eli/reg/2004/261/oj/eng"), ["eu261-outcome-250"]);
  assert.equal((await m.query("person-7f3a", "flight compensation", { at: "2026-11-14" })).length, 0);
  await m.setStatus("person-7f3a", "eu261-outcome-250", "verified", "re-triangulated");
  assert.equal((await m.query("person-7f3a", "flight compensation", { at: "2026-11-14" })).length, 1);
});

test("journal replay reproduces state, survives restarts as JSON Lines, and detects tampering", async () => {
  const dir = await mkdtemp(join(tmpdir(), "evmem-"));
  const path = join(dir, "journal.jsonl");
  const a = new EvidenceMemory("mbp", new JsonlJournal(path));
  await a.write(await rec(), 0);
  await a.setStatus("person-7f3a", "eu261-outcome-250", "retired", "test");
  const b = new EvidenceMemory("mini", new JsonlJournal(path));
  assert.equal(await b.replay(), 2);
  assert.equal(b.get("person-7f3a", "eu261-outcome-250")?.status, "retired");
  const lines = (await readFile(path, "utf8")).split("\n");
  await writeFile(path, lines[0]!.replace("€250", "€600") + "\n" + lines.slice(1).join("\n"));
  await assert.rejects(new EvidenceMemory("x", new JsonlJournal(path)).replay(), /tampered/);
});

test("hybrid logical clock stays monotonic when the wall clock steps back", () => {
  let t = 1000;
  const h = new Hlc("n1", () => t);
  const a = h.tick();
  t = 900;
  const b = h.tick();
  assert.ok(b > a);
  h.observe(Hlc.format(5000, 3, "n2"));
  t = 1000;
  assert.ok(h.tick() > Hlc.format(5000, 3, "n2"));
});

test("dense ranking can be fused with BM25 (RRF)", async () => {
  const m = new EvidenceMemory("mbp", new MemoryJournal());
  await m.write(await rec(), 0);
  await m.write(await rec({ id: "rail", statement: "Rail passengers get 25 % of the ticket price for 60 to 119 minutes delay.", quantity: { kind: "percent", value: 25, unit: "%", text: "25 %" } }), 0);
  const dense = async (s: string) => [/rail|train/i.test(s) ? 1 : 0, /flight|air/i.test(s) ? 1 : 0];
  const r = await m.query("person-7f3a", "my train was late", { at: "2026-11-14", dense });
  assert.equal(r[0]?.record.id, "rail");
});

test("compileWithMemory: first answer from the web and stored; repeat answered from memory; source change forces the web again", async () => {
  const { compileWithMemory } = await import("../src/memory/withMemory.ts");
  const LEGAL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32004R0261";
  const CURIA = "https://curia.europa.eu/juris/sturgeon";
  const pages: Record<string, string> = {
    [LEGAL]: "Passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres.",
    [CURIA]: "Passengers whose flights are delayed may rely on the right to compensation where they reach their final destination three hours or more after the arrival time originally scheduled by the air carrier.",
  };
  let searches = 0;
  const search = async (q: string) => {
    searches++;
    return /official legal text|official text/i.test(q) || searches % 2 === 0
      ? [{ url: LEGAL, highlights: [] }, { url: CURIA, highlights: [] }]
      : [{ url: "https://claims.example", highlights: ["For flights of 1,500 km or less you are entitled to €250 under Regulation (EC) No 261/2004.", "Passengers on short flights receive EUR 250 when they arrive three hours late."] }];
  };
  const m = new EvidenceMemory("mbp");
  const ctx = { tenant: "person-7f3a", at: "2026-11-14", jurisdiction: "EU", validUntil: "2027-10-23" };
  const q = "How much compensation do I get if my 1,500 km EU flight arrives 3 hours late?";
  const first = await compileWithMemory(q, m, ctx, search, async (u) => pages[u] ?? "");
  assert.equal(first.source, "web");
  assert.ok(first.source === "web" && first.stored >= 2, JSON.stringify(first.source === "web" && first.result.reasons));
  const before = searches;
  const second = await compileWithMemory(q, m, ctx, search, async (u) => pages[u] ?? "");
  assert.equal(second.source, "memory");
  assert.equal(searches, before, "no web search when memory answers");
  await m.sourceChanged(LEGAL);
  const third = await compileWithMemory(q, m, ctx, search, async (u) => pages[u] ?? "");
  assert.equal(third.source, "web");
});

test("URL watch: a record whose quote left the live page needs re-verification", async () => {
  const { EvidenceMemory } = await import("../src/memory/evidenceMemory.ts");
  const { sha256Hex } = await import("../src/lib/council.ts");
  const m = new EvidenceMemory("dev");
  const q1 = "Passengers shall receive EUR 250.";
  const q2 = "The period is 14 days.";
  const base = { tenant: "t", status: "verified" as const, role: "outcome" as const, statement: "EUR 250", quantity: { kind: "money" as const, value: 250, unit: "EUR", text: "EUR 250" }, provenance: { question: "q" } };
  await m.write({ ...base, id: "a", source: { url: "https://law.example/1", quote: q1, quoteSha256: await sha256Hex(q1), retrievedAt: "2026-11-01" } }, 0);
  await m.write({ ...base, id: "b", source: { url: "https://law.example/2", quote: q2, quoteSha256: await sha256Hex(q2), retrievedAt: "2026-11-01" } }, 0);
  const r = await m.recheckSources(async (u) => (u.endsWith("/1") ? "<nav>Home</nav> Passengers   shall receive EUR 250." : "The period is 30 days."));
  assert.deepEqual(r, { checked: 2, changed: ["b"], unreachable: [] });
  assert.equal(m.get("t", "a")?.status, "verified");
  assert.equal(m.get("t", "b")?.status, "needs_recheck");
});
