#!/usr/bin/env node
// TimeLaw: a time-aware legal claim benchmark built from official point-in-time texts.
// For each provision, the official text is fetched as it stood on several dates (eCFR versioner,
// legislation.gov.uk point-in-time). Sentences are aligned across dates by their template (all numbers
// replaced by a placeholder); a slot whose numbers change over time yields claims. A claim (a clause
// as worded on date A) is TRUE on date D exactly when the official text on D has the same template
// with the same numbers, and FALSE when it has the same template with different numbers. Dates where
// the template is absent are left out (undetermined). Gold comes from the official text only.
// Writes bench/timelaw/data/texts.json (text per provision and date) and timelaw.jsonl (claims).
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";

const here = new URL(".", import.meta.url);
mkdirSync(new URL("data/", here), { recursive: true });
const UA = { "user-agent": "warrant-research/0.1 (time-aware legal claim benchmark; polite, cached)", "accept-encoding": "gzip" };
const cacheFile = new URL("data/texts.json", here);
const cache = existsSync(cacheFile) ? JSON.parse(readFileSync(cacheFile, "utf8")) : {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const today = new Date().toISOString().slice(0, 10);

const PROVISIONS = [
  { id: "us-14cfr250.5", name: "14 CFR 250.5 (denied boarding compensation)", jurisdiction: "US", source: "ecfr", title: 14, part: 250, section: "250.5" },
  { id: "us-29cfr541.600", name: "29 CFR 541.600 (salary level for the white-collar overtime exemption)", jurisdiction: "US", source: "ecfr", title: 29, part: 541, section: "541.600" },
  { id: "us-12cfr1026.52", name: "12 CFR 1026.52 (credit card penalty fee limits)", jurisdiction: "US", source: "ecfr", title: 12, part: 1026, section: "1026.52" },
  { id: "us-16cfr1.98", name: "16 CFR 1.98 (FTC civil penalty amounts)", jurisdiction: "US", source: "ecfr", title: 16, part: 1, section: "1.98" },
  { id: "us-29cfr579.1", name: "29 CFR 579.1 (child labor civil money penalties)", jurisdiction: "US", source: "ecfr", title: 29, part: 579, section: "579.1" },
  { id: "uk-smp-reg6", name: "Statutory Maternity Pay (General) Regulations 1986, regulation 6 (weekly rate)", jurisdiction: "UK", source: "ukleg", path: "uksi/1986/1960/regulation/6" },
  { id: "uk-spp-reg2", name: "Statutory Paternity Pay and Statutory Adoption Pay (Weekly Rates) Regulations 2002, regulation 2", jurisdiction: "UK", source: "ukleg", path: "uksi/2002/2818/regulation/2" },
  { id: "uk-era-s227", name: "Employment Rights Act 1996, section 227 (maximum amount of a week's pay)", jurisdiction: "UK", source: "ukleg", path: "ukpga/1996/18/section/227" },
  { id: "uk-nmw-reg4", name: "National Minimum Wage Regulations 2015, regulation 4", jurisdiction: "UK", source: "ukleg", path: "uksi/2015/621/regulation/4" },
  { id: "uk-nmw-reg4a", name: "National Minimum Wage Regulations 2015, regulation 4A", jurisdiction: "UK", source: "ukleg", path: "uksi/2015/621/regulation/4A" },
  { id: "uk-ssp-s157", name: "Social Security Contributions and Benefits Act 1992, section 157 (statutory sick pay rate)", jurisdiction: "UK", source: "ukleg", path: "ukpga/1992/4/section/157" },
];

const stripXml = (xml) =>
  xml.replace(/<(CommentaryRef|FootnoteRef)[^>]*\/>/g, "").replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#163;|&pound;/g, "£").replace(/&#x2019;|&#8217;/g, "’").replace(/&[a-z#0-9]+;/gi, " ").replace(/\s+/g, " ").trim();

async function get(url) {
  for (let i = 0; i < 4; i++) {
    const r = await fetch(url, { headers: UA });
    if (r.ok) return r.text();
    if (r.status === 404) return null;
    await sleep(2000 * (i + 1));
  }
  throw new Error(`GET ${url} failed`);
}

async function textAt(p, date) {
  const key = `${p.id}@${date}`;
  if (key in cache) return cache[key];
  let text = null;
  if (p.source === "ecfr") {
    const xml = await get(`https://www.ecfr.gov/api/versioner/v1/full/${date}/title-${p.title}.xml?part=${p.part}&section=${p.section}`);
    text = xml ? stripXml(xml) : null;
  } else {
    const xml = await get(`https://www.legislation.gov.uk/${p.path}/${date}/data.xml`);
    const body = xml?.match(/<(Body|Schedules)[\s>][\s\S]*<\/(Body|Schedules)>/)?.[0];
    text = body ? stripXml(body) : null;
  }
  cache[key] = text;
  writeFileSync(cacheFile, JSON.stringify(cache));
  await sleep(700); // polite
  return text;
}

async function datesFor(p) {
  if (p.source === "ecfr") {
    const v = JSON.parse(await get(`https://www.ecfr.gov/api/versioner/v1/versions/title-${p.title}.json?part=${p.part}&section=${p.section}`));
    return [...new Set(v.content_versions.map((x) => x.date))].sort();
  }
  // UK rates change on 1 April (October before 2016): probe the day after each.
  const ds = [];
  for (let y = 2015; y <= Number(today.slice(0, 4)); y++) for (const md of ["-04-02", "-10-02"]) if (`${y}${md}` <= today) ds.push(`${y}${md}`);
  return [...ds, today];
}

// Clauses: split sentences, then at ";" so a claim is one clause, not a whole paragraph.
const clauses = (t) =>
  t.split(/(?<=[.;:])\s+(?=[(A-Z0-9£$])|\s(?=\(\d+\)\s|\([a-z]\)\s|\([ivx]+\)\s)/)
    .map((s) => s.trim().replace(/[;:,]$/, "").replace(/\s+and$|\s+or$/, "").trim())
    .filter((s) => s.length > 25 && s.length < 700);
const NUM = /£?\$?\d[\d,]*(?:\.\d+)?%?/g;
const template = (s) => s.replace(NUM, "#").replace(/\s+/g, " ").toLowerCase();

const items = [];
const provisionsOut = [];
for (const p of PROVISIONS) {
  const dates = await datesFor(p);
  const byDate = {};
  for (const d of dates) {
    const t = await textAt(p, d);
    if (t) byDate[d] = t;
  }
  // slot (template) -> date -> clause
  const slots = new Map();
  for (const [d, t] of Object.entries(byDate)) for (const c of clauses(t)) {
    if (!/\d/.test(c)) continue;
    // Editorial notes and Federal Register citations change with every amendment but state no rule.
    if (/Link to an amendment|\bFR \d|\[\d+ FR|published at|effective date note/i.test(c)) continue;
    const k = template(c);
    if (!slots.has(k)) slots.set(k, {});
    slots.get(k)[d] ??= c;
  }
  let made = 0;
  const latest = Object.keys(byDate).sort().at(-1);
  for (const [k, perDate] of slots) {
    const dates = Object.keys(perDate).sort();
    const nums = Object.fromEntries(dates.map((d) => [d, (perDate[d].match(NUM) ?? []).join("|")]));
    const values = [];
    for (const d of dates) if (!values.includes(nums[d])) values.push(nums[d]); // in order of first appearance
    if (values.length < 2) continue; // never changes: not a temporal slot
    const clauseOf = (v) => perDate[dates.find((d) => nums[d] === v)];
    for (const d of dates) {
      const vi = values.indexOf(nums[d]);
      // The true clause, the value before it (stale) and the value after it (premature).
      const variants = [[vi, "true"], [vi - 1, "stale"], [vi + 1, "premature"]].filter(([i]) => i >= 0 && i < values.length);
      for (const [i, kind] of variants) {
        const v = values[i];
        items.push({ id: `${p.id}|s${made}|${d}|${kind}`, provision: p.id, name: p.name, jurisdiction: p.jurisdiction, slot: made, claim: clauseOf(v), worded_on: dates.find((x) => nums[x] === v), date: d, label: kind === "true" ? 1 : 0, kind, latest: d === latest });
      }
    }
    made++;
  }
  provisionsOut.push({ id: p.id, dates: Object.keys(byDate), temporalSlots: made });
  console.log(`${p.id}: ${Object.keys(byDate).length} dates with text, ${slots.size} numeric clauses, ${made} change over time`);
}
writeFileSync(new URL("data/timelaw.jsonl", here), items.map((x) => JSON.stringify(x)).join("\n") + "\n");
writeFileSync(new URL("data/provisions.json", here), JSON.stringify(provisionsOut, null, 1));
console.log(`claims: ${items.length} (${items.filter((x) => x.label === 1).length} true, ${items.filter((x) => x.label === 0).length} false; ${items.filter((x) => x.latest).length} on today's date)`);
