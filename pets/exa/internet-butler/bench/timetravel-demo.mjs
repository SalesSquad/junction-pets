#!/usr/bin/env node
// Time-travel answer: the law as it stood on the day it mattered, with an immutable official source,
// what has changed since, and what is about to change.
//   1. find the provision      eCFR search (Exa with includeDomains ecfr.gov when a key is set)
//   2. the law on the event date and today   eCFR versioner point-in-time text
//   3. which clause fits the situation       Jev yes/no per amount-bearing clause (selection, not generation)
//   4. why it changed                         Federal Register documents amending that part, with effective dates
// Usage: node bench/timetravel-demo.mjs ["question with a YYYY-MM-DD date"]
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { typesafeJev } from "../src/decide/decide.ts";
import { lawOn } from "../src/warrant/pointInTime.ts";
import { extractQuantities } from "../src/warrant/lanes.ts";

const question = process.argv[2] ?? "I was involuntarily bumped from an oversold US domestic flight on 2021-06-10 and the airline's substitute flight got me to my destination 3 hours late. How much denied boarding compensation am I owed?";
const eventDate = question.match(/\d{4}-\d{2}-\d{2}/)?.[0];
if (!eventDate) { console.log("Give the event date as YYYY-MM-DD."); process.exit(1); }
const today = new Date().toISOString().slice(0, 10);
const UA = { "user-agent": "internet-butler-warrant/0.1" };
const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
const { TypeSafeClient } = await import("@typesafe-ai/sdk");
const jev = typesafeJev({ systemOne: (r, o) => new TypeSafeClient({ apiKey: process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY"), defaultModel: "jev-1.14.0" }).systemOne(r, o) });

console.log(`Q: ${question}\n   event date ${eventDate}, today ${today}\n`);

// 1. Find the provision (the eCFR search is itself time-aware: results carry each version's date range).
const terms = "denied boarding compensation amount";
const sr = await (await fetch(`https://www.ecfr.gov/api/search/v1/results?query=${encodeURIComponent(terms)}&date=${eventDate}&per_page=5`, { headers: UA })).json();
const hit = sr.results.find((r) => /amount/i.test(r.headings?.section ?? "")) ?? sr.results[0];
const ref = { source: "ecfr", title: Number(hit.hierarchy.title), part: hit.hierarchy.part, section: hit.hierarchy.section };
console.log(`1. Provision: ${ref.title} CFR ${ref.section} — ${(hit.headings?.section ?? "").replace(/<[^>]+>/g, "")}`);

// 2. The law on the event date, and today.
const latestIssue = (await (await fetch("https://www.ecfr.gov/api/versioner/v1/titles.json", { headers: UA })).json()).titles.find((t) => t.number === ref.title)?.latest_issue_date ?? today;
const [then, now] = await Promise.all([lawOn(ref, eventDate), lawOn(ref, latestIssue)]);
console.log(`2. Official text on ${eventDate}: ${then.url}\n   and on ${latestIssue}: ${now.url}`);

// 3. Which clause fits the situation: every clause with an amount is a candidate; Jev picks.
// Each numbered clause, prefixed with the opening of its lettered paragraph ((a) interstate, (b) foreign...).
const clauses = (t) =>
  t.split(/\s(?=\([a-z]\)\s)/).flatMap((para) => {
    const [intro, ...items] = para.split(/\s(?=\(\d+\)\s)/);
    return items.filter((c) => /\$\d/.test(c)).map((c) => `${intro.slice(0, 400)} … ${c.replace(/;\s*(and|or)?\s*$/, "")}`);
  });
const pick = async (text) => {
  const cs = clauses(text);
  const res = await Promise.all(cs.map((c) => jev.decide({ situation: question, clause: c.slice(0, 900) }, [{ kind: "yesno", name: "applies", instructions: "Does `clause` set the compensation for the passenger in `situation` (same kind of flight and the same length of delay of the substitute flight)?" }])));
  const ps = res.map((r) => r.answers[0].p ?? 0);
  const i = ps.indexOf(Math.max(...ps));
  const own = cs[i].split(" … ").at(-1); // the amount comes from the clause itself, not its paragraph intro
  return { clause: cs[i], p: ps[i], amount: extractQuantities(own).filter((q) => q.kind === "money").at(-1) };
};
const [a, b] = await Promise.all([pick(then.text), pick(now.text)]);
console.log(`3. Clause for this situation (Jev p = ${a.p.toFixed(2)}):\n   "…${a.clause.split(" … ").at(-1).slice(0, 220)}…"\n   → on ${eventDate} the cap was ${a.amount?.text}; today it is ${b.amount?.text}${a.amount?.value !== b.amount?.value ? " (a date-blind answer would be wrong)" : ""}`);

// 4. Why it changed: Federal Register documents amending this part, with effective dates.
const fr = await (await fetch(`https://www.federalregister.gov/api/v1/documents.json?conditions%5Bcfr%5D%5Btitle%5D=${ref.title}&conditions%5Bcfr%5D%5Bpart%5D=${ref.part}&per_page=10&order=newest&fields%5B%5D=title&fields%5B%5D=publication_date&fields%5B%5D=effective_on&fields%5B%5D=html_url&fields%5B%5D=type`, { headers: UA })).json();
const between = fr.results.filter((d) => d.type === "Rule" && d.effective_on && d.effective_on > eventDate);
console.log(`4. Changes to part ${ref.part} that took effect after ${eventDate}:`);
for (const d of between) console.log(`   ${d.effective_on > today ? "UPCOMING " : ""}${d.effective_on} (published ${d.publication_date}): ${d.title}\n     ${d.html_url}`);
console.log(`\nWarrant evidence: { url: "${then.url}", quote: "${a.clause.split(" … ").at(-1).slice(0, 80)}…", asOf: "${eventDate}" } — an immutable official version the receiver can re-fetch exactly.`);
