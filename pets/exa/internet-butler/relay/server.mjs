#!/usr/bin/env node
// Thin, stateless relay. It holds the API keys so the browser never sees them, forwards
// only the endpoints the app needs, stores nothing and logs no request bodies.
import { createServer } from "node:http";
import { appendFileSync, readFileSync, existsSync } from "node:fs";
import { createHmac, timingSafeEqual } from "node:crypto";
import { TypeSafeClient } from "@typesafe-ai/sdk";
import { exaMcpSearch } from "./exa-mcp.mjs";
import { homedir } from "node:os";
import { IMAGES_HEADER, localDecisions, logprobDecisions, openaiDecisions, typesafeJev } from "../src/decide/decide.ts";
import { amendmentsAfter, thenNowNext, OFFICIAL_DOMAINS, REGISTRY } from "../src/timetravel/timetravel.ts";
import { announcedChanges, GOV_DOMAINS } from "../src/timetravel/announced.ts";
import { nextSteps } from "../src/timetravel/nextSteps.ts";
import { monthDate, relativeDate, spokenDate } from "../src/ui/voice.ts";
import { isPointInTimeUrl, officialFetch } from "../src/warrant/pointInTime.ts";
import { image } from "@typesafe-ai/sdk";

loadDotEnv(new URL("../.env.local", import.meta.url));

const PORT = Number(process.env.RELAY_PORT ?? 8787);
const HOST = process.env.RELAY_HOST ?? "127.0.0.1";
const EXA_KEY = process.env.EXA_API_KEY || "";
const TS_KEY = process.env.TYPESAFE_API_KEY || readKeyFile(process.env.TYPESAFE_ENV_FILE || `${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY");
const TS_MODEL = process.env.TYPESAFE_MODEL || "jev-1.14.0";
// Without a key, fall back to Exa's keyless MCP tier (rate-limited). Set EXA_MCP_FALLBACK=0 to disable.
const EXA_MCP = !EXA_KEY && process.env.EXA_MCP_FALLBACK !== "0";
const EXA_MODE = EXA_KEY ? "api" : EXA_MCP ? "mcp-keyless" : undefined;
const MAX_BODY = 256 * 1024;
// /api/decide may carry images (TypeSafe allows 16 MiB per image, 32 MiB per request; resize to <= 1568 px first).
const MAX_IMAGE_BODY = 24 * 1024 * 1024;
const QUESTION_TYPES = new Set(["noul", "choice", "score", "box"]);

const typesafe = TS_KEY ? new TypeSafeClient({ apiKey: TS_KEY, defaultModel: TS_MODEL }) : null;
// OpenAI Decisions API (gpt-6-luna). Key from the environment or a key file outside the repo.
const OPENAI_KEY = process.env.OPENAI_API_KEY || readKeyFile(process.env.OPENAI_ENV_FILE || `${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY");
const DECIDERS = {
  openai: OPENAI_KEY ? openaiDecisions({ apiKey: OPENAI_KEY, model: process.env.OPENAI_DECISIONS_MODEL || "gpt-6-luna" }) : null,
  // Images go to the SDK as image(Blob) so it uploads them as multipart; the adapter adds the images header.
  typesafe: typesafe ? typesafeJev({ systemOne: (r, o) => typesafe.systemOne(r, o), model: TS_MODEL, toAsset: (a) => image(new Blob([Buffer.from(a.dataBase64, "base64")], { type: a.format === "png" ? "image/png" : "image/jpeg" })) }) : null,
};
// Third judge of the clause panel: NVIDIA Nemotron on an OpenAI-compatible endpoint, read through token
// log-probabilities (one or two output tokens, no reasoning). Optional; it has 6 s to answer, then abstains.
const NEMOTRON_KEY = process.env.VERDA_INFERENCE_KEY || "";
const NEMOTRON = NEMOTRON_KEY
  ? logprobDecisions({ id: process.env.NEMOTRON_MODEL || "nemotron-3.5-super-vl", baseUrl: process.env.NEMOTRON_BASE_URL || "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1", apiKey: NEMOTRON_KEY, model: process.env.NEMOTRON_MODEL || "nemotron-3.5-super-vl", timeoutMs: 6000 })
  : null;
// On-device judge: Gemma 4 E2B with our clause-judge LoRA behind gemma/serve_mlx_decide.py on 127.0.0.1.
// Role "advisor" (default): its vote is shown next to the panel's but not counted. Role "panel": it votes.
// It is also the only judge in private mode, where the situation goes to no hosted service.
const LOCAL_JUDGE_URL = (process.env.LOCAL_JUDGE_URL || "").replace(/\/$/, "");
const LOCAL_JUDGE_ROLE = process.env.LOCAL_JUDGE_ROLE === "panel" ? "panel" : "advisor";
const LOCAL_OK = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(LOCAL_JUDGE_URL);
// Next to the hosted panel it gets 6 s and is then left out; alone (private mode) it gets the time it needs.
const LOCAL_JUDGE = LOCAL_OK ? localDecisions({ baseUrl: LOCAL_JUDGE_URL, id: "gemma-on-device", timeoutMs: 6000 }) : null;
const LOCAL_JUDGE_ALONE = LOCAL_OK ? localDecisions({ baseUrl: LOCAL_JUDGE_URL, id: "gemma-on-device", timeoutMs: 30000 }) : null;
// On-device semantic catalog (bench/catalog/serve_catalog.py): EmbeddingGemma over amount-bearing CFR provisions.
// One more source of provision candidates next to the registry and Exa, and the only search in private mode.
const CATALOG_URL = (process.env.CATALOG_URL || "").replace(/\/$/, "");
const CATALOG_OK = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(CATALOG_URL);
const catalogSearch = CATALOG_OK
  ? async (question, date) => {
      const r = await fetch(`${CATALOG_URL}/search`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ query: question.slice(0, 4000), k: 5, ...(date ? { year: Number(date.slice(0, 4)) } : {}) }), signal: AbortSignal.timeout(4000) });
      if (!r.ok) throw new Error(`catalog ${r.status}`);
      const j = await r.json();
      return [
        ...(j.registry ?? []).map((x) => ({ kind: "registry", ref: x.ref, also: x.also?.length ? x.also : undefined, title: x.title, about: x.about, score: x.score })),
        ...(j.results ?? []).map((x) => ({ kind: "cfr", ref: { source: "ecfr", title: Number(x.title), part: String(x.part), section: String(x.section) }, title: `${x.title} CFR ${x.section} — ${x.subject}`, about: String(x.text ?? "").slice(0, 300), score: x.score })),
      ];
    }
  : undefined;
/** A provision reference from the browser (a catalog hit the person picked): only the three known shapes, rebuilt field by field. */
function cleanRef(r) {
  if (!r || typeof r !== "object") return null;
  if (r.source === "ecfr" && Number.isInteger(Number(r.title)) && Number(r.title) >= 1 && Number(r.title) <= 50 && /^[0-9A-Za-z]{1,6}$/.test(String(r.part)) && /^[0-9A-Za-z.-]{1,24}$/.test(String(r.section))) return { source: "ecfr", title: Number(r.title), part: String(r.part), section: String(r.section) };
  if (r.source === "ukleg" && /^[a-z]{2,6}\/\d{4}\/\d{1,5}\/(section|regulation|article)\/[0-9A-Za-z]{1,6}$/.test(String(r.path))) return { source: "ukleg", path: String(r.path) };
  if (r.source === "eurlex" && /^[0-9A-Z]{6,14}$/.test(String(r.celex)) && /^[0-9A-Za-z]{1,6}$/.test(String(r.article ?? ""))) return { source: "eurlex", celex: String(r.celex), article: String(r.article) };
  return null;
}
const DECISION_KINDS = new Set(["yesno", "choice", "score", "box"]);
// Official point-in-time texts never change for past dates: cache them in memory.
const officialCache = new Map();
// Announced-change searches cost Exa credit: one search per provision per day, and every call goes to the spend ledger.
const announcedCache = new Map();
const SPEND_LEDGER = new URL("../bench/results/exa-spend.jsonl", import.meta.url);
/** What this agent is, for other agents: one endpoint to ask, whom it asks in turn, and what stays with the human. */
const AGENT_CARD = {
  name: "Internet Butler — Then · Now · Next",
  description: "Answers what a person was owed on the day it happened, from the official text as of that date; shows today's rule, what changed it and what is announced; finds where to send the claim and the time limit on the live web; prepares a claim the person approves.",
  ask: { method: "POST", path: "/api/agent/ask", input: { question: "plain words, any language", date: "YYYY-MM-DD (optional: read from the question, else today)", private: "true keeps the question on this machine (on-device judge and catalog only)", steps: "false skips the Exa next-step search" }, output: "covered, answer, then, now, changed, evidence {url, quote, asOf}, agreed, reviewNeeded, asked[], nextSteps[], needsHuman[]" },
  alsoOffers: [
    { method: "POST", path: "/api/catalog/search", for: "find a right by meaning, on the device" },
    { method: "POST", path: "/api/announced", for: "announced, not-yet-in-force changes to a provision (Exa on government sites)" },
    { method: "POST", path: "/api/next-steps", for: "where to send a claim, the time limit, what was reported that day (Exa)" },
  ],
  asksInTurn: [
    { agent: "Exa", for: "finding provisions on official domains, announced changes, next steps, news bounded to the event date" },
    { agent: "TypeSafe Jev", for: "typed judgments with probabilities (provision, clause, source checks)" },
    { agent: "OpenAI Luna (Decisions API)", for: "second clause judge" },
    { agent: "NVIDIA Nemotron on Verda", for: "third clause judge, search planner, writer" },
    { agent: "Google Gemma 4 E2B with our LoRA, and EmbeddingGemma", for: "on-device judge and on-device catalog (private mode)" },
  ],
  human: "Nothing is sent to a counterparty without the person's approval. When the judges do not all agree the answer is marked reviewNeeded.",
};
const stepsCache = new Map();
/** One JSON object from the writer model (Nemotron, no reasoning tokens); null when it is not configured or does not answer. */
async function nemotronJson(prompt, maxTokens = 500, timeoutMs = 12000) {
  if (!NEMOTRON_KEY) return null;
  const r = await fetch(`${process.env.NEMOTRON_BASE_URL || "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1"}/chat/completions`, { method: "POST", headers: { authorization: `Bearer ${NEMOTRON_KEY}`, "content-type": "application/json" }, body: JSON.stringify({ model: process.env.NEMOTRON_MODEL || "nemotron-3.5-super-vl", temperature: 0, max_tokens: maxTokens, reasoning_effort: "none", messages: [{ role: "user", content: prompt }] }), signal: AbortSignal.timeout(timeoutMs) });
  if (!r.ok) return null;
  const m = String((await r.json()).choices?.[0]?.message?.content ?? "").match(/\{[^]*\}/);
  try { return m ? JSON.parse(m[0]) : null; } catch { return null; }
}
const EXA_BUDGET_USD = Number(process.env.EXA_BUDGET_USD ?? 30);
const exaSpent = () => { try { return readFileSync(SPEND_LEDGER, "utf8").split("\n").filter(Boolean).reduce((a, l) => a + (JSON.parse(l).usd ?? 0), 0); } catch { return 0; } };
function logExaSpend(tag, usd) {
  try { if (existsSync(SPEND_LEDGER)) appendFileSync(SPEND_LEDGER, JSON.stringify({ at: new Date().toISOString(), tag, cmd: "search", usd }) + "\n"); } catch { /* the ledger is bookkeeping, not a dependency */ }
}
const official = officialFetch(fetch);
async function officialCached(url) {
  if (!officialCache.has(url)) officialCache.set(url, await official(url));
  return officialCache.get(url);
}
// Exa Monitors webhook secret: returned once by Exa when a monitor is created; kept only in memory.
let monitorSecret = "";

/** Server-sent events for monitor webhooks (Exa Monitors -> relay -> open browser tabs). */
const sseClients = new Set();

export function createRelay() {
  return createServer(async (req, res) => {
    const started = Date.now();
    const url = new URL(req.url ?? "/", "http://relay");
    // Method, path, status and latency only: no bodies, no queries, no keys.
    res.once("finish", () => console.log(`${req.method} ${url.pathname} ${res.statusCode} ${Date.now() - started}ms`));
    try {
      if (req.method === "GET" && url.pathname === "/api/agent/card") return send(res, 200, AGENT_CARD);
      if (req.method === "GET" && url.pathname === "/api/knowledge") {
        // What has been collected for this agent to retrieve from: stored knowledge with counts, and the live sources.
        let catalog = null;
        if (CATALOG_OK) { try { catalog = await (await fetch(`${CATALOG_URL}/health`, { signal: AbortSignal.timeout(1500) })).json(); } catch { /* the catalog service is optional */ } }
        return send(res, 200, {
          agent: "Exa companion · Internet Butler",
          collected: [
            { id: "rights", title: "Built-in rights", count: REGISTRY.length, unit: "rights", detail: "US, UK and EU provisions with their families, each with a description the agent can match in any language", items: REGISTRY.map((k) => ({ title: k.title, jurisdiction: k.jurisdiction })) },
            { id: "catalog", title: "Semantic catalog (EmbeddingGemma, on this device)", count: catalog?.rows ?? 5924, unit: "provisions", detail: "Every amount-bearing provision of six CFR titles (12, 14, 16, 20, 29, 49) across the 1996–2026 editions, as 768-dimension vectors. This is what \"Find a right by meaning\" searches.", running: !!catalog },
            { id: "cfr-annual", title: "CFR-Annual (GovInfo annual editions)", count: 346588, unit: "amount clauses", detail: "107,383 section-years and 3,029 recorded changes of an amount, each with its source edition" },
            { id: "uk-eu", title: "UK and EU rates", count: 3312, unit: "dated clauses", detail: "27 provisions read twice a year from 2004 to 2026 (wages, statutory pay, delay compensation), 292 changes" },
            { id: "situations", title: "TimeLaw-Situations", count: 26019, unit: "situations", detail: "People's messages in English, Finnish and German whose right clause is known, with adversarial rewrites; other model families checked the labels. Trains and tests the judges." },
            { id: "studies", title: "Exa studies", count: 2326, unit: "questions", detail: "1,126 dated questions (does the answer use the date?) and 1,200 situations (is the provision found, by language), with agent, rewrite and two-stage arms" },
            { id: "judge", title: "On-device judge", count: 10500, unit: "training items", detail: "Gemma 4 E2B with our LoRA: 88.8 % on the verified test set", running: !!LOCAL_JUDGE },
          ],
          live: [
            { title: "Official texts as of a date", detail: "eCFR versioner (US), legislation.gov.uk (UK), EUR-Lex CELLAR (EU): fetched for the event date and for today, pinned in the answer" },
            { title: "Exa", detail: "provisions on official domains, announced changes on government sites, the counterparty's claim page, the time limit, news bounded to the event date, and the general butler's sources" },
          ],
        });
      }
      if (req.method === "GET" && url.pathname === "/api/health") {
        return send(res, 200, { exa: !!EXA_MODE, exaMode: EXA_MODE, typesafe: !!typesafe, model: typesafe ? TS_MODEL : undefined, decisions: Object.keys(DECIDERS).filter((k) => DECIDERS[k]), panel: [DECIDERS.typesafe, DECIDERS.openai, NEMOTRON, LOCAL_JUDGE_ROLE === "panel" ? LOCAL_JUDGE : null].filter(Boolean).map((j) => j.id), ...(LOCAL_JUDGE ? { onDevice: { id: LOCAL_JUDGE.id, role: LOCAL_JUDGE_ROLE } } : {}), ...(CATALOG_OK ? { catalog: true } : {}), ...(NEMOTRON_KEY ? { writer: true } : {}), monitor: !!monitorSecret });
      }
      if (req.method === "GET" && url.pathname === "/api/events") {
        res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive" });
        res.write(": connected\n\n");
        sseClients.add(res);
        req.on("close", () => sseClients.delete(res));
        return;
      }
      if (req.method !== "POST") return send(res, 404, { error: "not found" });
      const { json: body, raw } = await readJson(req, url.pathname === "/api/decide" ? MAX_IMAGE_BODY : MAX_BODY);

      if (url.pathname === "/api/exa/search") {
        if (!EXA_MODE) return send(res, 503, { error: "EXA_API_KEY not configured" });
        const query = str(body.query, 1, 2000);
        const type = ["auto", "lite", "deep"].includes(body.type) ? body.type : "auto";
        const numResults = clampInt(body.numResults, 1, 10, 8);
        if (!EXA_KEY) {
          const objective = typeof body.objective === "string" && body.objective.trim() ? str(body.objective, 1, 4096) : query;
          return send(res, 200, { results: await exaMcpSearch({ query, objective, numResults }), via: "mcp-keyless" });
        }
        const data = await exa("/search", { query, type, numResults, contents: { highlights: true } });
        return send(res, 200, {
          results: (data.results ?? []).map((r, i) => ({
            id: r.id ?? `r${i}`,
            title: r.title ?? r.url,
            url: r.url,
            publishedDate: r.publishedDate ?? undefined,
            highlights: Array.isArray(r.highlights) ? r.highlights : [],
          })),
          costDollars: data.costDollars,
        });
      }

      if (url.pathname === "/api/exa/contents") {
        if (!EXA_KEY) return send(res, 503, { error: "EXA_API_KEY not configured" });
        const urls = Array.isArray(body.urls) ? body.urls.slice(0, 10).map((u) => str(u, 8, 2048)) : [];
        if (!urls.length) return send(res, 400, { error: "urls required" });
        // snapshotAsOf: the newest stored version at or before that time (receiver-side "was it there then?").
        const snapshotAsOf = typeof body.snapshotAsOf === "string" && /^\d{4}-\d{2}-\d{2}(T[\d:.]+Z?)?$/.test(body.snapshotAsOf) ? body.snapshotAsOf : undefined;
        // maxAgeHours: 0 = fetch live (receivers and source rechecks); cannot be combined with snapshotAsOf.
        const maxAgeHours = !snapshotAsOf && Number.isInteger(body.maxAgeHours) && body.maxAgeHours >= -1 && body.maxAgeHours <= 720 ? body.maxAgeHours : undefined;
        const data = await exa("/contents", { urls, text: true, ...(snapshotAsOf ? { snapshotAsOf } : {}), ...(maxAgeHours !== undefined ? { maxAgeHours } : {}) });
        return send(res, 200, { results: (data.results ?? []).map((r) => ({ url: r.url, title: r.title, text: r.text })) });
      }

      if (url.pathname === "/api/timetravel") {
        // Then · Now · Next: the law on the event date, today, and the changes between (src/timetravel).
        const question = str(body.question, 5, 2000);
        const eventDate = typeof body.eventDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(body.eventDate) ? body.eventDate : null;
        if (!eventDate) return send(res, 400, { error: "eventDate YYYY-MM-DD required" });
        // A provision the person picked from the on-device catalog search: discovery is skipped.
        const given = body.ref ? cleanRef(body.ref) : null;
        if (body.ref && !given) return send(res, 400, { error: "ref: not a known provision reference" });
        const known = given ? REGISTRY.find((k) => JSON.stringify(k.ref) === JSON.stringify(given)) : undefined;
        const pinned = given ? { ref: given, title: known?.title ?? (typeof body.title === "string" ? body.title.slice(0, 200) : "") } : {};
        if (body.private === true) {
          // Private mode: the situation goes to no hosted service. The provision is found by keywords, tiers are
          // ruled out by code, and the on-device judge picks among the rest. Only the public law is fetched.
          if (!LOCAL_JUDGE) return send(res, 503, { error: "private mode needs the on-device judge (start gemma/serve_mlx_decide.py and set LOCAL_JUDGE_URL)" });
          const r = await thenNowNext({ question, eventDate, ...pinned }, { judge: LOCAL_JUDGE_ALONE, provisionJudge: null, catalogSearch });
          // One judge of measured but lower accuracy: the person always reads the clause before a claim.
          const agreement = { ...(r.agreement ?? { votes: [], abstained: [] }), agreed: false, note: "on-device judge only" };
          return send(res, 200, { ...r, agreement, judge: LOCAL_JUDGE.id, judges: [LOCAL_JUDGE.id], private: true, officialDomains: OFFICIAL_DOMAINS });
        }
        const judge = DECIDERS.typesafe ?? DECIDERS.openai;
        if (!judge) return send(res, 503, { error: "no decision provider configured (TYPESAFE_API_KEY or OPENAI_API_KEY)" });
        const exaSearch = EXA_KEY
          ? async (q, includeDomains) => (await exa("/search", { query: q, type: "auto", numResults: 5, includeDomains })).results ?? []
          : EXA_MCP
            ? async (q) => exaMcpSearch({ query: `${q} site:ecfr.gov OR site:legislation.gov.uk OR site:eur-lex.europa.eu`, objective: "Find the official legal provision (statute or regulation text) that sets this amount or deadline.", numResults: 5 })
            : undefined;
        // Clause panel: every configured judge reads all tiers at once; the answer is "agreed" only if all pick the same.
        const second = DECIDERS.typesafe && DECIDERS.openai ? DECIDERS.openai : undefined;
        const panel = [...(NEMOTRON ? [NEMOTRON] : []), ...(LOCAL_JUDGE && LOCAL_JUDGE_ROLE === "panel" ? [LOCAL_JUDGE] : [])];
        const advisors = LOCAL_JUDGE && LOCAL_JUDGE_ROLE === "advisor" ? [LOCAL_JUDGE] : [];
        const r = await thenNowNext({ question, eventDate, ...pinned }, { judge, exaSearch, second, panel, advisors, catalogSearch });
        // The signing rule was measured with three judges. With fewer configured, the answer is never "agreed".
        const missing = [!DECIDERS.typesafe && "jev", !DECIDERS.openai && "luna", !NEMOTRON && !(LOCAL_JUDGE && LOCAL_JUDGE_ROLE === "panel") && "a third judge"].filter(Boolean).map((n) => `${n} (not configured)`);
        const agreement = r.agreement && missing.length ? { ...r.agreement, agreed: false, abstained: [...r.agreement.abstained, ...missing], note: "fewer than three panel judges configured" } : r.agreement;
        return send(res, 200, { ...r, agreement, judge: judge.id, judges: [judge, second, ...panel].filter(Boolean).map((j) => j.id), officialDomains: OFFICIAL_DOMAINS });
      }

      if (url.pathname === "/api/agent/ask") {
        // One call for another agent (for example a partner companion): a question in plain words in, the dated
        // answer with its official source, who was asked for what, and what still needs a human, out.
        const question = str(body.question, 5, 2000);
        const today = new Date().toISOString().slice(0, 10);
        const date = typeof body.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(body.date) ? body.date : (spokenDate(question) ?? monthDate(question) ?? relativeDate(question, today) ?? today);
        const self = async (path, payload) => {
          const r = await fetch(`http://127.0.0.1:${req.socket.localPort}${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
          return { ok: r.ok, json: await r.json().catch(() => ({})) };
        };
        const priv = body.private === true;
        const tt = await self("/api/timetravel", { question, eventDate: date, ...(priv ? { private: true } : {}) });
        if (!tt.ok) return send(res, 200, { covered: false, date, reason: String(tt.json.error ?? "not covered").slice(0, 200), suggestion: "Not a dated amount or period the butler can pin to an official text. Search the live web (POST /api/exa/search) or use the app's general butler." });
        const r = tt.json;
        const steps = priv || body.steps === false ? null : await self("/api/next-steps", { question, eventDate: date, right: r.provision.title }).then((x) => (x.ok ? x.json : null)).catch(() => null);
        const NAMES = { "typesafe-jev": "TypeSafe Jev", "openai-decisions": "OpenAI Luna", "nemotron-3.5-super-vl": "NVIDIA Nemotron", "gemma-on-device": "Google Gemma (on device)" };
        const asked = [
          { agent: r.provision.via === "exa" ? "Exa" : r.provision.via === "catalog" ? "EmbeddingGemma catalog (on device)" : "built-in list", did: `found the provision (${r.provision.title})` },
          { agent: "official source", did: `text as of ${r.then.date}`, url: r.then.url },
          { agent: "code", did: [r.computed ? "computed the flight distance" : "", `ruled out ${r.ruledOut ?? 0} tier(s)`].filter(Boolean).join("; ") },
          ...(r.agreement?.votes ?? []).map((v) => ({ agent: NAMES[v.judge] ?? v.judge, did: `voted (p ${Number(v.p).toFixed(2)})${v.tied ? ", tied" : ""}` })),
          ...(r.agreement?.advisory ?? []).map((v) => ({ agent: NAMES[v.judge] ?? v.judge, did: "advised (not counted)" })),
          ...(steps ? [{ agent: "Exa", did: `found ${steps.steps.length} next step(s)` }] : []),
        ];
        return send(res, 200, {
          covered: true,
          date,
          answer: `On ${r.then.date}: ${r.then.amount?.text ?? "see the quoted clause"}${r.changed && r.now.amount ? ` (today: ${r.now.amount.text})` : ""} — ${r.provision.title}`,
          then: { date: r.then.date, amount: r.then.amount?.text ?? null, url: r.then.url },
          now: { date: r.now.date, amount: r.now.amount?.text ?? null, url: r.now.url },
          changed: r.changed,
          evidence: r.evidence,
          computed: r.computed ?? null,
          agreed: !!r.agreement?.agreed,
          reviewNeeded: !r.agreement?.agreed,
          asked,
          nextSteps: steps?.steps ?? [],
          needsHuman: ["read the quoted clause if reviewNeeded", "approve before anything is sent to the counterparty"],
        });
      }

      if (url.pathname === "/api/write") {
        // Hosted writer for the general butler: a JSON draft from the question and public sources. No document text
        // is accepted here by contract (the browser's council sends only the errand and source highlights).
        if (!NEMOTRON_KEY) return send(res, 503, { error: "no hosted writer configured (VERDA_INFERENCE_KEY)" });
        const system = str(body.system, 10, 2000), user = str(body.user, 10, 24000);
        return send(res, 200, { json: await nemotronJson(`${system}\n\n${user}`, 1100, 25000) });
      }

      if (url.pathname === "/api/next-steps") {
        // "Work out what needs to happen": where to send the claim, the time limit, and what was reported on the
        // day, found on the live web with Exa (three searches), planned by a writer model and checked by a judge.
        if (!EXA_KEY) return send(res, 503, { error: "next steps need EXA_API_KEY" });
        const judge = DECIDERS.typesafe ?? DECIDERS.openai;
        if (!judge) return send(res, 503, { error: "no decision provider configured" });
        const question = str(body.question, 5, 2000);
        const eventDate = typeof body.eventDate === "string" && /^\d{4}-\d{2}-\d{2}$/.test(body.eventDate) ? body.eventDate : null;
        if (!eventDate) return send(res, 400, { error: "eventDate YYYY-MM-DD required" });
        const right = typeof body.right === "string" ? body.right.slice(0, 200) : "";
        const today = new Date().toISOString().slice(0, 10);
        const key = `${eventDate}|${right}|${question}`;
        if (!stepsCache.has(key)) {
          if (stepsCache.size >= 300 || exaSpent() >= EXA_BUDGET_USD) return send(res, 429, { error: "Exa budget or the cap for next-step searches is reached" });
          const search = async (s, o) => {
            const data = await exa("/search", { query: s.query, type: "auto", numResults: 5, ...(o.news ? { category: "news", startPublishedDate: `${o.from}T00:00:00.000Z`, endPublishedDate: `${o.to}T23:59:59.000Z` } : {}), contents: { highlights: { query: s.need, numSentences: 3, highlightsPerUrl: 2 } } });
            logExaSpend(`next-steps:${s.kind}`, data.costDollars?.total ?? 0);
            return (data.results ?? []).map((r) => ({ url: r.url, title: r.title, publishedDate: r.publishedDate, highlights: r.highlights }));
          };
          const run = nextSteps({ question, eventDate, today, right }, { plan: NEMOTRON_KEY ? async (prompt) => (await nemotronJson(prompt)) ?? (await nemotronJson(prompt)) : undefined, search, judge });
          stepsCache.set(key, run);
          run.catch(() => stepsCache.delete(key));
        }
        return send(res, 200, { ...(await stepsCache.get(key)), today });
      }

      if (url.pathname === "/api/catalog/search") {
        // "Spotlight" for rights: the on-device catalog, searched by meaning in any language. Nothing leaves the machine.
        if (!catalogSearch) return send(res, 503, { error: "the on-device catalog is not running (npm run catalog:local)" });
        const query = str(body.query, 2, 2000);
        const date = typeof body.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(body.date) ? body.date : undefined;
        const hits = await catalogSearch(query, date);
        // Built-in rights first when they match by meaning; then the nearest CFR provisions.
        const reg = hits.filter((h) => h.kind === "registry" && h.score >= 0.35).slice(0, 2);
        const cfr = hits.filter((h) => h.kind !== "registry").slice(0, 5);
        return send(res, 200, { hits: [...reg, ...cfr].map((h) => ({ kind: h.kind, ref: h.ref, title: h.title, about: h.about, score: h.score })) });
      }

      if (url.pathname === "/api/announced") {
        // "Next" beyond the official feeds: changes that are announced or published but not yet in force, found
        // with Exa on government domains. Code keeps only documents that state a future date; a judge confirms
        // the document is about this provision. A warning with a source, never cited by a Warrant.
        if (!EXA_KEY) return send(res, 503, { error: "announced changes need EXA_API_KEY" });
        const judge = DECIDERS.typesafe ?? DECIDERS.openai;
        if (!judge) return send(res, 503, { error: "no decision provider configured" });
        const title = str(body.title, 3, 300);
        const known = REGISTRY.find((k) => k.title === title);
        const source = body.ref?.source;
        const jurisdiction = known?.jurisdiction ?? (source === "ecfr" ? "US" : source === "ukleg" ? "UK" : source === "eurlex" ? "EU" : "");
        const today = new Date().toISOString().slice(0, 10);
        const key = `${title}|${today}`;
        if (!announcedCache.has(key)) {
          // One paid search run per provision per day: yesterday's entries go, the day has a cap, and the shared
          // Exa budget (the ledger scripts/exa.mjs keeps) is respected.
          for (const k of announcedCache.keys()) if (!k.endsWith(`|${today}`)) announcedCache.delete(k);
          if (announcedCache.size >= 200 || exaSpent() >= EXA_BUDGET_USD) return send(res, 429, { error: "Exa budget or the daily cap for announced-change searches is reached" });
          let ok = 0, failed = 0;
          const search = async (query, o) => {
            try {
              const data = await exa("/search", { query, type: "auto", numResults: 5, includeDomains: o.includeDomains, startPublishedDate: o.startPublishedDate, contents: { highlights: { query: o.highlightQuery, numSentences: 3, highlightsPerUrl: 3 } } });
              logExaSpend("announced", data.costDollars?.total ?? 0);
              ok++;
              return (data.results ?? []).map((r) => ({ url: r.url, title: r.title, publishedDate: r.publishedDate, highlights: r.highlights }));
            } catch (err) {
              failed++;
              throw err;
            }
          };
          // The promise is cached, so requests that arrive while a search runs wait for it instead of paying again.
          const run = announcedChanges({ title, about: known?.about, jurisdiction, today }, { search, judge, max: 3 }).then((found) => {
            if (!ok) throw Object.assign(new Error("announced-change search failed (Exa did not answer); try again"), { statusCode: 502 });
            // Keep only an answer the searches support: a complete run, or a hit. An empty list from a half-failed run is not "nothing found".
            if (failed && !found.length) announcedCache.delete(key);
            return { announced: found, ...(failed ? { incomplete: true } : {}) };
          });
          announcedCache.set(key, run);
          run.catch(() => announcedCache.delete(key));
        }
        return send(res, 200, { ...(await announcedCache.get(key)), searched: GOV_DOMAINS[jurisdiction] ?? [], today });
      }

      if (url.pathname === "/api/official") {
        // Receiver-side re-check: only official point-in-time URLs, returned as plain official text.
        const target = typeof body.url === "string" ? body.url : "";
        if (!isPointInTimeUrl(target)) return send(res, 400, { error: "only official point-in-time URLs (eCFR versioner, legislation.gov.uk dated data.xml, EUR-Lex CELLAR)" });
        return send(res, 200, { url: target, text: await officialCached(target) });
      }

      if (url.pathname === "/api/radar/check") {
        // Watched situations: any amending instrument in force after `since`, or published and coming.
        const watches = Array.isArray(body.watches) ? body.watches.slice(0, 20) : [];
        const today = new Date().toISOString().slice(0, 10);
        const out = [];
        for (const w of watches) {
          if (!w?.ref?.source || typeof w.since !== "string") continue;
          try {
            const cs = await amendmentsAfter(w.ref, w.since, today);
            out.push({ label: w.label, changes: cs.filter((c) => !c.upcoming), upcoming: cs.filter((c) => c.upcoming) });
          } catch (err) {
            out.push({ label: w.label, error: String(err.message).slice(0, 120) });
          }
        }
        return send(res, 200, { checked: out.length, results: out });
      }

      if (url.pathname === "/api/radar/monitor") {
        // An Exa Monitor that watches official change sources for a topic and posts to our signed webhook.
        if (!EXA_KEY) return send(res, 503, { error: "EXA_API_KEY not configured" });
        const hook = typeof body.webhookUrl === "string" && body.webhookUrl.startsWith("https://") ? body.webhookUrl : process.env.EXA_WEBHOOK_URL;
        if (!hook) return send(res, 400, { error: "a public HTTPS webhook URL is required (EXA_WEBHOOK_URL)" });
        const topic = str(body.topic, 3, 300);
        const m = await exa("/monitors", {
          name: `Then·Now·Next radar: ${topic}`.slice(0, 100),
          search: { query: `new rule or regulation amending ${topic}`, numResults: 5, includeDomains: ["federalregister.gov", "legislation.gov.uk", "eur-lex.europa.eu", "gov.uk"] },
          trigger: { type: "interval", period: "1d" },
          webhook: { url: `${hook.replace(/\/$/, "")}/api/webhooks/exa`, events: ["monitor.run.completed"] },
        });
        if (m.webhookSecret) monitorSecret = m.webhookSecret; // never returned to the browser
        return send(res, 200, { id: m.id, topic, verified: !!monitorSecret });
      }

      if (url.pathname === "/api/decide") {
        // Typed decisions (src/decide/decide.ts): {provider: "openai"|"typesafe", state, questions[]}.
        const decider = DECIDERS[body.provider];
        if (!decider) return send(res, 503, { error: `decision provider ${String(body.provider)} not configured` });
        const qs = body.questions;
        if (!Array.isArray(qs) || !qs.length || qs.length > 400) return send(res, 400, { error: "1-400 questions" });
        for (const q of qs) {
          if (!q || !DECISION_KINDS.has(q.kind) || typeof q.name !== "string" || typeof q.instructions !== "string") return send(res, 400, { error: "invalid question" });
        }
        if (body.state == null) return send(res, 400, { error: "state required" });
        const assets = body.assets && typeof body.assets === "object" ? body.assets : undefined;
        if (assets) {
          for (const a of Object.values(assets)) {
            if (!a || !["png", "jpg"].includes(a.format) || typeof a.dataBase64 !== "string") return send(res, 400, { error: "assets: {format: png|jpg, dataBase64}" });
          }
        }
        return send(res, 200, await decider.decide(body.state, qs, assets));
      }

      if (url.pathname === "/api/typesafe/judge") {
        if (!typesafe) return send(res, 503, { error: "TYPESAFE_API_KEY not configured" });
        const questions = body.questions;
        if (!questions || typeof questions !== "object" || Array.isArray(questions)) return send(res, 400, { error: "questions object required" });
        const names = Object.keys(questions);
        if (!names.length || names.length > 64) return send(res, 400, { error: "1-64 questions" });
        for (const n of names) {
          if (!QUESTION_TYPES.has(questions[n]?.type)) return send(res, 400, { error: `question ${n}: unsupported type` });
        }
        if (body.state == null) return send(res, 400, { error: "state required" });
        // Box questions need TypeSafe's images opt-in header ("dreamer-ready", not for production).
        const wantsImages = names.some((n) => questions[n].type === "box");
        const result = await typesafe.systemOne({ state: body.state, questions }, wantsImages ? { headers: { ...IMAGES_HEADER } } : undefined);
        return send(res, 200, { model: result.model, answers: result.answers, usage: result.usage });
      }

      if (url.pathname === "/api/webhooks/exa") {
        // Forward monitor deliveries to open tabs; never persisted. With EXA_WEBHOOK_SECRET set,
        // unsigned or tampered deliveries are rejected.
        const secret = process.env.EXA_WEBHOOK_SECRET || monitorSecret || "";
        const verified = secret ? verifyExaSignature(req.headers["exa-signature"], raw, secret) : false;
        if (secret && !verified) return send(res, 401, { error: "invalid Exa-Signature" });
        const event = `data: ${JSON.stringify({ at: new Date().toISOString(), verified, payload: body })}\n\n`;
        sseClients.forEach((c) => c.write(event));
        return send(res, 202, { delivered: sseClients.size });
      }

      return send(res, 404, { error: "not found" });
    } catch (err) {
      const status = err?.statusCode ?? err?.status ?? 502;
      return send(res, status >= 400 && status < 600 ? status : 502, { error: String(err?.message ?? err).slice(0, 300) });
    }
  });
}

async function exa(path, payload) {
  const r = await fetch(`https://api.exa.ai${path}`, {
    method: "POST",
    headers: { "x-api-key": EXA_KEY, "content-type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(25_000),
  });
  if (!r.ok) {
    const e = new Error(`Exa ${path} HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
    e.statusCode = 502;
    throw e;
  }
  return r.json();
}

function send(res, status, obj) {
  if (res.headersSent) return;
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(JSON.stringify(obj));
}

function readJson(req, limit = MAX_BODY) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (c) => {
      size += c.length;
      if (size > limit) {
        const e = new Error("body too large");
        e.statusCode = 413;
        reject(e);
        req.destroy();
      } else chunks.push(c);
    });
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve({ json: raw ? JSON.parse(raw) : {}, raw });
      } catch {
        const e = new Error("invalid JSON");
        e.statusCode = 400;
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

/** Exa-Signature: t=<timestamp>,v1=<hex HMAC-SHA256 of "<t>.<raw body>">, compared in constant time. */
export function verifyExaSignature(header, raw, secret) {
  if (typeof header !== "string") return false;
  const parts = Object.fromEntries(header.split(",").map((kv) => kv.trim().split("=", 2)));
  if (!parts.t || !parts.v1) return false;
  const expected = createHmac("sha256", secret).update(`${parts.t}.${raw}`).digest("hex");
  const a = Buffer.from(expected, "hex");
  const b = Buffer.from(parts.v1, "hex");
  return a.length === b.length && timingSafeEqual(a, b);
}

function str(v, min, max) {
  if (typeof v !== "string" || v.trim().length < min || v.length > max) {
    const e = new Error(`invalid string (length ${min}-${max})`);
    e.statusCode = 400;
    throw e;
  }
  return v.trim();
}

function clampInt(v, min, max, fallback) {
  const n = Number.isInteger(v) ? v : fallback;
  return Math.min(max, Math.max(min, n));
}

function readKeyFile(path, name) {
  try {
    const m = readFileSync(path, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"));
    return m ? m[1].trim().replace(/^["']|["']$/g, "") : "";
  } catch {
    return "";
  }
}

function loadDotEnv(fileUrl) {
  if (!existsSync(fileUrl)) return;
  for (const line of readFileSync(fileUrl, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  createRelay().listen(PORT, HOST, () => {
    console.log(`relay on http://${HOST}:${PORT}  exa=${EXA_MODE ?? "missing"}  typesafe=${typesafe ? TS_MODEL : "missing"}`);
  });
}
