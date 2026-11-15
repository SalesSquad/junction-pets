// Keyless Exa access through Exa's hosted MCP server (https://mcp.exa.ai/mcp).
// Exa offers web_search_exa without an API key on a free, rate-limited tier for MCP
// clients; this relay acts as such a client so the butler can run live before keys exist.
// With EXA_API_KEY set, the relay uses the REST API instead.
import dns from "node:dns";

// Keyless MCP access requires a direct IPv4 connection (IPv6 is refused).
dns.setDefaultResultOrder("ipv4first");

const MCP_URL = process.env.EXA_MCP_URL || "https://mcp.exa.ai/mcp";
let session = null;
let rpcId = 0;

async function rpc(body, sid) {
  const r = await fetch(MCP_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      ...(sid ? { "mcp-session-id": sid } : {}),
      // With a key the same MCP endpoint runs on the account's limits instead of the keyless tier.
      ...(process.env.EXA_API_KEY ? { "x-api-key": process.env.EXA_API_KEY } : {}),
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  const text = await r.text();
  if (r.status === 429) throw httpError(429, "Exa MCP free rate limit reached; set EXA_API_KEY for full access");
  if (!r.ok) throw httpError(502, `Exa MCP HTTP ${r.status}: ${text.slice(0, 200)}`);
  const frames = text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim());
  const json = frames.length ? JSON.parse(frames.at(-1)) : text ? JSON.parse(text) : {};
  return { json, sid: r.headers.get("mcp-session-id") };
}

async function openSession() {
  const { sid } = await rpc({
    jsonrpc: "2.0",
    id: ++rpcId,
    method: "initialize",
    params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "internet-butler-relay", version: "0.1.0" } },
  });
  await rpc({ jsonrpc: "2.0", method: "notifications/initialized" }, sid);
  return sid;
}

export async function exaMcpSearch({ query, objective, numResults }) {
  for (let attempt = 0; attempt < 2; attempt++) {
    session ??= await openSession();
    const { json } = await rpc(
      { jsonrpc: "2.0", id: ++rpcId, method: "tools/call", params: { name: "web_search_exa", arguments: { query, objective, numResults } } },
      session,
    );
    if (json.error) {
      session = null; // the session may have expired; retry once with a fresh one
      if (attempt === 1) throw httpError(502, `Exa MCP error: ${json.error.message}`);
      continue;
    }
    const text = (json.result?.content ?? []).map((c) => c.text ?? "").join("\n");
    return parseMcpResults(text);
  }
  return [];
}

/** Fetch full page text through keyless web_fetch_exa (used to verify quotes against the source). */
export async function exaMcpFetch({ urls, maxCharacters = 400_000 }) {
  for (let attempt = 0; attempt < 2; attempt++) {
    session ??= await openSession();
    const { json } = await rpc(
      { jsonrpc: "2.0", id: ++rpcId, method: "tools/call", params: { name: "web_fetch_exa", arguments: { urls, maxCharacters } } },
      session,
    );
    if (json.error) {
      session = null;
      if (attempt === 1) throw httpError(502, `Exa MCP error: ${json.error.message}`);
      continue;
    }
    return (json.result?.content ?? []).map((c) => c.text ?? "").join("\n");
  }
  return "";
}

/**
 * Parse the text blocks web_search_exa returns:
 *   Title: …\nURL: …\nPublished: …\nAuthor: …\nHighlights:\n<verbatim excerpts>
 * Blocks are separated by "---" lines. Highlights stay verbatim so quotes can be matched.
 */
export function parseMcpResults(text) {
  return text
    .split(/(?=^Title: .*\nURL: )/m)
    .map((block) => block.trim().replace(/\n-{3,}$/, "").trim())
    .filter((block) => block.startsWith("Title:"))
    .map((block, i) => {
      const field = (name) => block.match(new RegExp(`^${name}: ?(.*)$`, "m"))?.[1]?.trim() ?? "";
      const body = block.split(/^Highlights:\s*$/m)[1] ?? "";
      const published = field("Published");
      return {
        id: `mcp${i}`,
        title: field("Title") || field("URL"),
        url: field("URL"),
        publishedDate: published && published !== "N/A" ? published : undefined,
        highlights: body
          .split(/\n\s*\.\.\.\s*\n/)
          .map((h) => h.trim())
          .filter(Boolean)
          .slice(0, 4)
          .map((h) => (h.length > 2400 ? `${h.slice(0, 2400)}…` : h)),
      };
    })
    .filter((r) => r.url.startsWith("http"));
}

function httpError(statusCode, message) {
  const e = new Error(message);
  e.statusCode = statusCode;
  return e;
}
