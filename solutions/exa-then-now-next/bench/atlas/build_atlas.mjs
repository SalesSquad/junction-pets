#!/usr/bin/env node
// AmountAtlas: every money amount in selected eCFR titles, in every version since 2017, and each change with
// the date it took effect. Built only from the official eCFR versioner (no model, no web search), so every
// row is reproducible from its pinned point-in-time URL.
//
//   for each part:   latest text → sections that state a money amount
//   for each section: its version dates (versions API) → the text on each date → amount-bearing clauses
//   changes:         consecutive versions, clauses matched by template (numbers masked) → old → new amount
//
// Usage: node --experimental-strip-types bench/atlas/build_atlas.mjs [--titles=12,14,16] [--parts=16:1,14:250]
//        [--concurrency=4] [--out=bench/atlas/out]
import { mkdirSync, writeFileSync, appendFileSync, existsSync, readFileSync } from "node:fs";
import { amountClauses, template } from "../../src/timetravel/timetravel.ts";
import { extractQuantities } from "../../src/warrant/lanes.ts";
import { officialFetch } from "../../src/warrant/pointInTime.ts";
const official = officialFetch((u, i) => limitedFetch(u, i));

const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const titles = arg("titles", "16").split(",").map(Number);
const onlyParts = arg("parts", "") ? new Set(arg("parts", "").split(",")) : null;
const concurrency = Number(arg("concurrency", "4"));
const out = arg("out", "bench/atlas/out");
mkdirSync(out, { recursive: true });
const UA = { "user-agent": "amount-atlas/0.1 (research; point-in-time official texts)" };
const BASE = "https://www.ecfr.gov/api/versioner/v1";

// eCFR rate-limits hard: one shared gate spaces every request (default 3 per second) and honours Retry-After.
const rps = Number(arg("rps", "3"));
let gate = Promise.resolve();
const slot = () => (gate = gate.then(() => new Promise((r) => setTimeout(r, 1000 / rps))));
const limitedFetch = async (url, init) => {
  for (let i = 0; ; i++) {
    await slot();
    const r = await fetch(url, init);
    if ((r.status !== 429 && r.status < 500) || i >= 8) return r;
    const wait = Number(r.headers.get("retry-after")) * 1000 || Math.min(60_000, 2000 * 2 ** i);
    await new Promise((res) => setTimeout(res, wait));
  }
};
async function get(url, kind = "text") {
  const r = await limitedFetch(url, { headers: UA });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return kind === "json" ? await r.json() : await r.text();
}
async function pool(items, n, fn) {
  const results = [];
  let next = 0;
  await Promise.all(Array.from({ length: n }, async () => { while (next < items.length) { const i = next++; results[i] = await fn(items[i], i); } }));
  return results;
}
const textOf = (xml) => xml.replace(/<(HEAD|P|FP|HD|EXTRACT|GPOTABLE|ROW|ENT)[^>]*>/g, " ").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#x2014;|&mdash;/g, "—").replace(/&#[^;]+;|&[a-z]+;/g, " ").replace(/\s+/g, " ").trim();
const sectionsOf = (xml) => [...xml.matchAll(/<DIV8 N="([^"]+)" TYPE="SECTION"[^>]*>([^]*?)<\/DIV8>/g)].map((m) => ({ id: m[1].replace(/^§\s*/, ""), text: textOf(m[2]) }));
const moneyIn = (t) => /\$\s?\d/.test(t);

const titlesJson = await get(`${BASE}/titles.json`, "json");
const latest = Object.fromEntries(titlesJson.titles.map((t) => [t.number, t.latest_issue_date]));
const rowsFile = `${out}/atlas.jsonl`;
const changesFile = `${out}/changes.jsonl`;
const doneFile = `${out}/done.txt`;
const done = new Set(existsSync(doneFile) ? readFileSync(doneFile, "utf8").split("\n").filter(Boolean) : []);

let nSections = 0, nRows = 0, nChanges = 0;
for (const title of titles) {
  const date = latest[title];
  const structure = await get(`${BASE}/structure/${date}/title-${title}.json`, "json");
  const parts = [];
  (function walk(n) { if (n.type === "part" && !n.reserved) parts.push(n.identifier); for (const c of n.children ?? []) walk(c); })(structure);
  const wanted = parts.filter((p) => !onlyParts || onlyParts.has(`${title}:${p}`));
  console.log(`title ${title}: ${wanted.length} parts (latest ${date})`);
  await pool(wanted, concurrency, async (part) => {
    const key = `${title}:${part}`;
    if (done.has(key)) return;
    const xml = await get(`${BASE}/full/${date}/title-${title}.xml?part=${encodeURIComponent(part)}`);
    if (!xml) return;
    const withMoney = sectionsOf(xml).filter((s) => moneyIn(s.text)).map((s) => s.id);
    if (withMoney.length) {
      const versions = (await get(`${BASE}/versions/title-${title}.json?part=${encodeURIComponent(part)}`, "json"))?.content_versions ?? [];
      for (const sec of withMoney) {
        const dates = [...new Set(versions.filter((v) => v.identifier === sec && v.substantive !== false && !v.removed).map((v) => v.date))].sort();
        if (!dates.length) dates.push(date);
        const byDate = await pool(dates, 2, async (d) => {
          // The same text extraction the Warrant receiver uses, so atlas quotes verify verbatim.
          let text = null;
          for (let i = 0; i < 4 && text === null; i++) text = await official(`${BASE}/full/${d}/title-${title}.xml?part=${part}&section=${sec}`).catch((e) => (/^404/.test(e.message) ? "" : (new Promise((r) => setTimeout(r, 800 * 2 ** i)).then(() => null))));
          if (!text) return { d, clauses: [] };
          return { d, clauses: amountClauses(text) };
        });
        nSections++;
        let prev = null;
        for (const v of byDate) {
          const url = `${BASE}/full/${v.d}/title-${title}.xml?part=${part}&section=${sec}`;
          for (const c of v.clauses) {
            const own = c.split(" … ").at(-1);
            const q = extractQuantities(own).find((x) => x.kind === "money");
            if (!q) continue;
            appendFileSync(rowsFile, JSON.stringify({ title, part, section: sec, date: v.d, url, amount: q.text, value: q.value, unit: q.unit, template: template(own), clause: c }) + "\n");
            nRows++;
          }
          if (prev) {
            const old = new Map(prev.clauses.map((c) => [template(c.split(" … ").at(-1)), c]));
            for (const c of v.clauses) {
              const t = template(c.split(" … ").at(-1));
              const o = old.get(t);
              if (!o) continue;
              const a = extractQuantities(o.split(" … ").at(-1)).filter((x) => x.kind === "money").map((x) => x.text);
              const b = extractQuantities(c.split(" … ").at(-1)).filter((x) => x.kind === "money").map((x) => x.text);
              if (a.join("|") !== b.join("|")) {
                appendFileSync(changesFile, JSON.stringify({ title, part, section: sec, from: prev.d, effective: v.d, old: a, new: b, template: t, clause: c }) + "\n");
                nChanges++;
              }
            }
          }
          prev = v;
        }
      }
    }
    appendFileSync(doneFile, key + "\n");
  });
  console.log(`title ${title} done: sections ${nSections}, rows ${nRows}, changes ${nChanges}`);
}
writeFileSync(`${out}/summary.json`, JSON.stringify({ titles, sections: nSections, rows: nRows, changes: nChanges, builtAt: new Date().toISOString() }, null, 1));
console.log(JSON.stringify({ sections: nSections, rows: nRows, changes: nChanges }));
