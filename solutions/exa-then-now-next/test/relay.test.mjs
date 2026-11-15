import assert from "node:assert/strict";
import { test } from "node:test";

// Run the relay without keys: it must report that and refuse to forward anything.
delete process.env.EXA_API_KEY;
delete process.env.TYPESAFE_API_KEY;
process.env.EXA_API_KEY = "";
process.env.TYPESAFE_API_KEY = "";
process.env.EXA_MCP_FALLBACK = "0";
process.env.OPENAI_API_KEY = "";
process.env.OPENAI_ENV_FILE = "/nonexistent/openai.env";
process.env.TYPESAFE_ENV_FILE = "/nonexistent/typesafe.env";
process.env.VERDA_INFERENCE_KEY = "";
const { createRelay } = await import("../relay/server.mjs");

test("relay without keys: health reports missing services and endpoints return 503", async () => {
  const server = createRelay().listen(0, "127.0.0.1");
  await new Promise((r) => server.once("listening", r));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    assert.deepEqual(await (await fetch(`${base}/api/health`)).json(), { exa: false, typesafe: false, decisions: [], panel: [], monitor: false });
    const post = (p, b) => fetch(`${base}${p}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) });
    // What the agent knows and what it is, for other agents: served without any key.
    const knowledge = await (await fetch(`${base}/api/knowledge`)).json();
    assert.ok(knowledge.collected.some((k) => k.id === "catalog" && k.count > 0) && knowledge.live.length === 2);
    assert.equal((await (await fetch(`${base}/api/agent/card`)).json()).ask.path, "/api/agent/ask");
    assert.equal((await post("/api/exa/search", { query: "x" })).status, 503);
    assert.equal((await post("/api/typesafe/judge", { state: "x", questions: { a: { type: "noul", instructions: "?" } } })).status, 503);
    assert.equal((await post("/api/decide", { provider: "openai", state: {}, questions: [{ kind: "yesno", name: "a", instructions: "?" }] })).status, 503);
    assert.equal((await post("/api/timetravel", { question: "bumped flight", eventDate: "2021-06-10" })).status, 503);
    assert.equal((await post("/api/announced", { title: "14 CFR 250.5 — denied boarding compensation (US)" })).status, 503);
    assert.equal((await post("/api/catalog/search", { query: "bumped flight" })).status, 503);
    // A provision reference from the browser must have one of the three known shapes.
    assert.equal((await post("/api/timetravel", { question: "bumped flight", eventDate: "2021-06-10", ref: { source: "ecfr", title: 14, part: "../250", section: "250.5" } })).status, 400);
    assert.equal((await post("/api/timetravel", { question: "bumped flight", eventDate: "2021-06-10", ref: { source: "file", path: "/etc/passwd" } })).status, 400);
    assert.equal((await post("/api/official", { url: "https://example.com/law" })).status, 400);
    assert.equal((await post("/api/radar/monitor", { topic: "denied boarding" })).status, 503);
    assert.equal((await post("/api/nope", {})).status, 404);
    const big = await fetch(`${base}/api/exa/search`, { method: "POST", body: "x".repeat(300 * 1024) }).catch(() => null);
    assert.ok(!big || big.status === 413 || big.status === 503);
  } finally {
    server.close();
  }
});

test("parses keyless MCP search blocks and keeps highlights verbatim", async () => {
  const { parseMcpResults } = await import("../relay/exa-mcp.mjs");
  const text = [
    "Title: Rent rules | Example Gov",
    "URL: https://gov.example/rent",
    "Published: 2025-05-18T02:23:53.000Z",
    "Author: Housing Office",
    "Highlights:",
    "## When rent can be increased",
    "",
    "A landlord must give 60 days' written notice.",
    "...",
    "| a | b |",
    "| --- | --- |",
    "",
    "---",
    "",
    "Title: Tenant guide",
    "URL: https://tenants.example/guide",
    "Published: N/A",
    "Author: N/A",
    "Highlights:",
    "Notice periods depend on the lease term.",
  ].join("\n");
  const r = parseMcpResults(text);
  assert.equal(r.length, 2);
  assert.equal(r[0].url, "https://gov.example/rent");
  assert.equal(r[0].publishedDate, "2025-05-18T02:23:53.000Z");
  assert.equal(r[0].highlights.length, 2);
  assert.match(r[0].highlights[0], /60 days' written notice\.$/);
  assert.equal(r[1].publishedDate, undefined);
  assert.equal(r[1].highlights[0], "Notice periods depend on the lease term.");
});

test("Exa webhook signatures: valid accepted, tampered rejected", async () => {
  const { verifyExaSignature } = await import("../relay/server.mjs");
  const { createHmac } = await import("node:crypto");
  const raw = JSON.stringify({ monitorId: "m1", items: [] });
  const sig = createHmac("sha256", "s3cret").update(`1700000000.${raw}`).digest("hex");
  assert.equal(verifyExaSignature(`t=1700000000,v1=${sig}`, raw, "s3cret"), true);
  assert.equal(verifyExaSignature(`t=1700000000,v1=${sig}`, raw + " ", "s3cret"), false);
  assert.equal(verifyExaSignature(undefined, raw, "s3cret"), false);
});
