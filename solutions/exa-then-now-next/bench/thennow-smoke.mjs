#!/usr/bin/env node
// Live smoke test of Then · Now · Next on three jurisdictions (official endpoints + Jev).
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { typesafeJev } from "../src/decide/decide.ts";
import { thenNowNext } from "../src/timetravel/timetravel.ts";
const key = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
const { TypeSafeClient } = await import("@typesafe-ai/sdk");
const ts = new TypeSafeClient({ apiKey: key, defaultModel: "jev-1.14.0" });
const judge = typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) });
const cases = [
  ["I was bumped from an oversold US domestic flight on 2021-06-10 and the substitute flight got me there 3 hours late. How much denied boarding compensation am I owed?", "2021-06-10"],
  ["I am 25 and worked in the UK in June 2023 for £10.00 an hour. What was the national minimum wage (national living wage) per hour on 2023-06-15?", "2023-06-15"],
  ["My EU flight of 1,200 km was cancelled on 2019-03-01 without notice. How much compensation is owed under EU261?", "2019-03-01"],
];
for (const [q, d] of cases) {
  const t0 = Date.now();
  try {
    const r = await thenNowNext({ question: q, eventDate: d }, { judge });
    console.log(`\n${r.provision.title} [${r.provision.via}] in ${Date.now() - t0} ms`);
    console.log(`  THEN ${r.then.date}: ${r.then.amount?.text ?? "?"} (p ${r.then.p.toFixed(2)}) ${r.then.url}`);
    console.log(`  NOW  ${r.now.date}: ${r.now.amount?.text ?? "?"}${r.changed ? "  ← changed" : ""}`);
    console.log(`  WHY  ${r.changes.slice(0, 3).map((c) => `${c.effective} ${c.title.slice(0, 70)}`).join(" | ") || "—"}`);
    console.log(`  NEXT ${r.upcoming.map((c) => `${c.effective} ${c.title.slice(0, 70)}`).join(" | ") || "none published"}`);
    console.log(`  quote: "${r.evidence.quote.slice(0, 160)}"`);
  } catch (e) { console.log(`\n${q.slice(0, 60)}… ERROR ${e.message}`); }
}
