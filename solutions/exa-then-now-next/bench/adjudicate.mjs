#!/usr/bin/env node
// Apply hand adjudication (bench/adversarial/adjudication.json) to the latest adaptive run, report false
// accepts by severity, and measure a CANDIDATE row (legal force: duty / right / prohibition / advice)
// on every round. The candidate is designed from round 4, so its round-4 number is a development
// result; an honest number needs a round 5.
// Usage: node bench/adjudicate.mjs
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { openaiDecisions, typesafeJev } from "../src/decide/decide.ts";
import { Cassette } from "../src/eval/cassette.ts";
import { clusterBootstrap, pct } from "./stats.mjs";

const here = new URL(".", import.meta.url);
const f = readdirSync(new URL("results/", here)).filter((x) => x.startsWith("adaptive-") && x.endsWith("Z.json")).sort().at(-1);
const items = JSON.parse(readFileSync(new URL(`results/${f}`, here), "utf8")).items;
const adj = JSON.parse(readFileSync(new URL("adversarial/adjudication.json", here), "utf8")).entries;
for (const x of items) {
  const a = adj.find((a) => a.round === x.round && a.id === x.id && x.passage.includes(a.match));
  if (!a) continue;
  x.verdict = a.verdict;
  if (a.verdict === "true") x.accept = true;
}

const ROWS = ["same_number", "same_role", "affirms", "same_jurisdiction", "same_source"];
const VETO = ["contradicts", "adds_terms", "scope_change"];
const ok = (t, extra = []) => t.injection <= 0.7 && [...ROWS, ...extra].every((k) => (t[k] ?? 0) > 0.5) && VETO.every((k) => (t[k] ?? 0) <= 0.5);

// Candidate row, asked separately through the cassette (questions are evaluated independently).
const FORCE = { kind: "yesno", name: "same_force", instructions: "Does `passage` give the rule the same legal force as `claim`: a binding duty stays a duty, a right stays a right, a prohibition stays a prohibition, rather than becoming advice, a recommendation, a mere permission or a new obligation?", yes: "the same kind of legal force, even if worded differently (shall, must, is required, is liable, is entitled)", no: "the passage turns it into advice, a recommendation or guidance, or turns a right into a duty or a duty into an option" };
const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
const cassette = new Cassette(new URL("cassettes/adaptive.jsonl", here).pathname, "auto");
const { TypeSafeClient } = await import("@typesafe-ai/sdk");
const judges = {
  jev: cassette.decisions(typesafeJev({ systemOne: (r, o) => new TypeSafeClient({ apiKey: process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY"), defaultModel: "jev-1.14.0" }).systemOne(r, o) })),
  luna: cassette.decisions(openaiDecisions({ apiKey: process.env.OPENAI_API_KEY || keyFrom(`${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY") })),
};
const spec = new Map(JSON.parse(readFileSync(new URL("errands.json", here), "utf8")).errands.map((e) => [e.id, e]));
async function pool(xs, n, fn) { let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < xs.length) { const k = i++; await fn(xs[k]); } })); }
for (const [short, p] of Object.entries(judges)) {
  await pool(items, 8, async (x) => {
    const e = spec.get(x.id);
    const r = await p.decide({ jurisdiction: e.jurisdiction, claim: e.premise, passage: x.passage }, [FORCE]);
    x[short].table.same_force = r.answers[0].p ?? 0;
  });
}
cassette.pack();

const lines = [`# Adjudicated results and a candidate "legal force" row (${new Date().toISOString().slice(0, 10)})`, "", `Source run: \`bench/results/${f}\`. Adjudication: \`bench/adversarial/adjudication.json\` (${adj.length} entries; ${adj.filter((a) => a.verdict === "true").length} attacker label errors relabelled as correct law).`, ""];
lines.push("| judge | round | forgeries accepted (all) | of which material | true accepted | with candidate row: forgeries / true |", "|---|---|---|---|---|---|");
for (const short of Object.keys(judges)) {
  for (const r of [1, 2, 3, 4]) {
    const xs = items.filter((x) => x.round === r);
    const forged = xs.filter((x) => !x.accept), good = xs.filter((x) => x.accept);
    const acc = forged.filter((x) => ok(x[short].table));
    const mat = acc.filter((x) => x.verdict === "false-material" || !x.verdict);
    const accC = forged.filter((x) => ok(x[short].table, ["same_force"]));
    const goodC = good.filter((x) => ok(x[short].table, ["same_force"]));
    const ci = clusterBootstrap(xs, (x) => x.id, (s) => { const f = s.filter((x) => !x.accept); return f.filter((x) => ok(x[short].table)).length / f.length; });
    lines.push(`| ${short} | ${r}${r === 4 ? " (held out)" : ""} | ${acc.length}/${forged.length} = ${pct(acc.length / forged.length)} (CI ${pct(ci.lo)}–${pct(ci.hi)}) | ${mat.length} | ${good.filter((x) => ok(x[short].table)).length}/${good.length} | ${accC.length}/${forged.length} / ${goodC.length}/${good.length}${r === 4 ? " (dev)" : ""} |`);
  }
}
const both = (x, extra = []) => ok(x.jev.table, extra) && ok(x.luna.table, extra);
const r4 = items.filter((x) => x.round === 4);
lines.push("", `Both judges must accept, round 4: forgeries ${r4.filter((x) => !x.accept && both(x)).length}/${r4.filter((x) => !x.accept).length} (material ${r4.filter((x) => !x.accept && both(x) && x.verdict !== "false-minor").length}), true ${r4.filter((x) => x.accept && both(x)).length}/${r4.filter((x) => x.accept).length}; with the candidate row: forgeries ${r4.filter((x) => !x.accept && both(x, ["same_force"])).length}, true ${r4.filter((x) => x.accept && both(x, ["same_force"])).length}.`);
const unadj = items.filter((x) => x.round >= 3 && !x.accept && !x.verdict && (ok(x.jev.table) || ok(x.luna.table)));
lines.push("", `Accepted forgeries in rounds 3–4 without an adjudication entry: ${unadj.length}${unadj.length ? ` (${unadj.map((x) => `r${x.round}:${x.id}`).join(", ")})` : ""}.`);
console.log(lines.join("\n"));
writeFileSync(new URL("ADJUDICATED-EVAL.md", here), lines.join("\n") + "\n");
