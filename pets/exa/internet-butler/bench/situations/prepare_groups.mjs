#!/usr/bin/env node
// TimeLaw-Situations, step 1 (Mac): choice groups. A group is one provision on one date with two or more
// amount-bearing clauses (tiers). Each group becomes a multiple-choice item once a generator writes a
// person's situation for one target clause; the correct answer is known by construction.
// Sources: the AmountAtlas (US eCFR, every section version) plus the UK/EU registry provisions on several dates.
// Usage: node --experimental-strip-types bench/situations/prepare_groups.mjs [--max=600] [--out=bench/situations/groups.jsonl]
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { amountClauses, REGISTRY } from "../../src/timetravel/timetravel.ts";
import { lawOn } from "../../src/warrant/pointInTime.ts";

const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const max = Number(arg("max", "600"));
const out = arg("out", "bench/situations/groups.jsonl");
const own = (c) => c.split(" … ").at(-1);
let seed = 7;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);

const groups = [];
// US: the atlas, grouped by section and version date.
const atlas = existsSync("bench/atlas/out/atlas.jsonl") ? readFileSync("bench/atlas/out/atlas.jsonl", "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];
const by = new Map();
for (const r of atlas) {
  const k = `${r.title}|${r.part}|${r.section}|${r.date}`;
  if (!by.has(k)) by.set(k, { ref: { source: "ecfr", title: r.title, part: r.part, section: r.section }, date: r.date, url: r.url, clauses: [] });
  const g = by.get(k);
  if (!g.clauses.includes(r.clause)) g.clauses.push(r.clause);
}
// One version per section per year keeps the set varied rather than dominated by long tables.
const seen = new Set();
for (const g of [...by.values()].sort(() => rand() - 0.5)) {
  const distinct = new Set(g.clauses.map(own)).size;
  const key = `${JSON.stringify(g.ref)}|${g.date.slice(0, 4)}`;
  if (distinct < 2 || g.clauses.length > 24 || seen.has(key)) continue;
  seen.add(key);
  groups.push({ gid: `us-${g.ref.title}-${g.ref.section}-${g.date}`, jurisdiction: "US", ...g });
}
// UK and EU: registry provisions (and their families) on a spread of dates.
const DATES = ["2016-06-01", "2018-06-01", "2020-06-01", "2022-06-01", "2023-06-01", "2024-06-01", "2025-06-01", "2026-06-01"];
for (const k of REGISTRY.filter((x) => x.ref.source !== "ecfr")) {
  for (const d of DATES) {
    const refs = [k.ref, ...(k.also ?? [])];
    const clauses = [];
    let url = "";
    for (const ref of refs) {
      try {
        const law = await lawOn(ref, d);
        url ||= law.url;
        for (const c of amountClauses(law.text)) clauses.push(c);
      } catch {
        /* not in force on that date */
      }
    }
    if (new Set(clauses.map(own)).size >= 2) groups.push({ gid: `${k.jurisdiction.toLowerCase()}-${(k.ref.path ?? k.ref.celex).replace(/\W+/g, "-")}-${d}`, jurisdiction: k.jurisdiction, ref: k.ref, also: k.also, date: d, url, title: k.title, clauses });
  }
}
const picked = groups.sort(() => rand() - 0.5).slice(0, max);
writeFileSync(out, picked.map((g) => JSON.stringify(g)).join("\n") + "\n");
console.log(JSON.stringify({ atlasRows: atlas.length, groups: groups.length, written: picked.length, us: picked.filter((g) => g.jurisdiction === "US").length, uk: picked.filter((g) => g.jurisdiction === "UK").length, eu: picked.filter((g) => g.jurisdiction === "EU").length, clauses: picked.reduce((n, g) => n + g.clauses.length, 0) }));
