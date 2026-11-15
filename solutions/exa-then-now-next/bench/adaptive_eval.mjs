#!/usr/bin/env node
// Adaptive red-team evaluation of the shipped truth table (src/decide/compilerDecisions.ts TRUTH_TABLE).
//   Round 1 (non-adaptive): bench/adversarial/variants*.json — 7 variant types per rule.
//   Round 2 (adaptive):     bench/adversarial/adaptive*.json — Haiku knew the defender and wrote 3
//                           forgeries per rule meant to pass every check, plus one hard-but-true passage.
// Methodology: one state per passage; all calls recorded in a cassette (re-runs are free and
// identical); cluster bootstrap by rule; Learn-then-Test threshold calibrated on round 1 and applied
// to round 2 (does a guarantee survive an adaptive attacker?); risk–coverage/AURC; exact McNemar.
// Usage: node bench/adaptive_eval.mjs [--providers=jev,openai] [--cassette=auto|replay|record]
import { readFileSync, existsSync, writeFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { openaiDecisions, typesafeJev } from "../src/decide/decide.ts";
import { TRUTH_TABLE } from "../src/decide/compilerDecisions.ts";
import { extractQuantities, sameQuantity } from "../src/warrant/lanes.ts";
import { Cassette, gitState, writeManifest } from "../src/eval/cassette.ts";
import { ci, clusterBootstrap, lttThreshold, mcnemar, pct, riskCoverage } from "./stats.mjs";

const here = new URL(".", import.meta.url);
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.split("=")[1] ?? d;
const started = new Date().toISOString();
const ONLY = arg("providers", "jev,openai").split(",");
mkdirSync(new URL("cassettes/", here), { recursive: true });
const cassette = new Cassette(new URL("cassettes/adaptive.jsonl", here).pathname, arg("cassette", "auto"));
const keyFrom = (file, name) => { try { return readFileSync(file, "utf8").match(new RegExp(`^${name}=(.*)$`, "m"))?.[1]?.trim().replace(/^["']|["']$/g, "") ?? ""; } catch { return ""; } };
const providers = [];
const tsKey = process.env.TYPESAFE_API_KEY || keyFrom(`${homedir()}/.config/typesafe/env`, "TYPESAFE_API_KEY");
if (ONLY.includes("jev")) {
  let live = { id: "typesafe-jev", decide: async () => { throw new Error("no TypeSafe key"); } };
  if (tsKey) { const { TypeSafeClient } = await import("@typesafe-ai/sdk"); const ts = new TypeSafeClient({ apiKey: tsKey, defaultModel: "jev-1.14.0" }); live = typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) }); }
  providers.push({ short: "jev", model: "jev-1.14.0", p: cassette.decisions(live) });
}
if (ONLY.includes("openai")) {
  const oaKey = process.env.OPENAI_API_KEY || keyFrom(`${homedir()}/.config/openai/factory-decisions.env`, "OPENAI_API_KEY");
  let live = { id: "openai-decisions", decide: async () => { throw new Error("no OpenAI key"); } };
  if (oaKey) live = openaiDecisions({ apiKey: oaKey });
  providers.push({ short: "luna", model: "gpt-6-luna", p: cassette.decisions(live) });
}

const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const byId = new Map(spec.errands.map((e) => [e.id, e]));
const refs = (e) => { const aq = e.anchors.flat().flatMap((a) => extractQuantities(a)); return extractQuantities(e.premise).filter((p) => aq.some((a) => sameQuantity(a, p)) || e.anchors.flat().some((a) => p.text.includes(a))); };
const hasRef = (e, s) => { const r = refs(e); return r.length > 0 && extractQuantities(s).some((q) => r.some((x) => sameQuantity(x, q))); };

const items = [];
const dropped = [];
for (let b = 0; b < 3; b++) {
  const f1 = new URL(`adversarial/variants${b}.json`, here);
  if (existsSync(f1)) for (const v of JSON.parse(readFileSync(f1, "utf8")).items) {
    const e = byId.get(v.id);
    if (!e) continue;
    for (const t of ["faithful", "injected", "wrong_number", "role_swap", "negated", "wrong_jurisdiction", "no_number"]) {
      const s = v[t];
      if (!s) continue;
      const keep = ["faithful", "injected", "role_swap", "negated", "wrong_jurisdiction"].includes(t);
      const ok = !refs(e).length || (keep ? hasRef(e, s) : !hasRef(e, s));
      if (!ok) { dropped.push(`r1:${v.id}/${t}`); continue; }
      items.push({ round: 1, id: v.id, e, type: t, passage: s, accept: t === "faithful" });
    }
  }
  for (const [round, f2] of [[2, new URL(`adversarial/adaptive${b}.json`, here)], [3, new URL(`adversarial/adaptive3_${b}.json`, here)], [4, new URL(`adversarial/adaptive4_${b}.json`, here)]]) if (existsSync(f2)) for (const v of JSON.parse(readFileSync(f2, "utf8")).items) {
    const e = byId.get(v.id);
    if (!e) continue;
    for (const a of v.attacks ?? []) {
      // An adaptive forgery must keep the decisive number, or code alone already stops it.
      if (refs(e).length && !hasRef(e, a.text)) { dropped.push(`r2:${v.id}/${a.strategy}`); continue; }
      items.push({ round, id: v.id, e, type: "attack", strategy: a.strategy, why: a.why_false, passage: a.text, accept: false });
    }
    if (v.hard_true && (!refs(e).length || hasRef(e, v.hard_true))) items.push({ round, id: v.id, e, type: "hard_true", passage: v.hard_true, accept: true });
    else if (v.hard_true) dropped.push(`r${round}:${v.id}/hard_true`);
  }
}

async function pool(xs, n, fn) { const out = new Array(xs.length); let i = 0; await Promise.all(Array.from({ length: n }, async () => { while (i < xs.length) { const k = i++; out[k] = await fn(xs[k]); } })); return out; }
const ROWS = ["same_number", "same_role", "affirms", "same_jurisdiction", "same_source", "same_force"];
const VETO = ["contradicts", "adds_terms", "scope_change"];
// Acceptance score = the weakest row: agreement rows as is, veto rows inverted (absent rows count as passing,
// so older four-row tables can be scored the same way).
const scoreOf = (t) => (t.injection > 0.7 ? 0 : Math.min(...ROWS.map((k) => t[k] ?? 0), ...VETO.map((k) => 1 - (t[k] ?? 0))));

for (const prov of providers) {
  const tables = await pool(items, 8, async (x) => {
    // Questions are evaluated independently, so asking the table in the groups it grew in (rows 1–7, then
    // the rows added later) gives the same answers and lets earlier rows replay from the cassette.
    const groups = [TRUTH_TABLE.slice(0, 7), TRUTH_TABLE.slice(7, 9), TRUTH_TABLE.slice(9)].filter((g) => g.length);
    const state = { jurisdiction: x.e.jurisdiction, claim: x.e.premise, passage: x.passage };
    const rs = await Promise.all(groups.map((g) => prov.p.decide(state, g)));
    return Object.fromEntries(rs.flatMap((r) => r.answers.map((a) => [a.name, a.p ?? 0])));
  });
  items.forEach((x, i) => { x[prov.short] = { table: tables[i], score: scoreOf(tables[i]) }; });
}

const report = [];
const log = (s = "") => { console.log(s); report.push(s); };
// Hand adjudication (bench/ADAPTIVE-FINDINGS.md): passages the attacker labelled false that are correct law.
const ADJ = JSON.parse(readFileSync(new URL("adversarial/adjudication.json", here), "utf8")).entries;
for (const x of items) { const a = ADJ.find((a) => a.round === x.round && a.id === x.id && x.passage.includes(a.match)); if (a) { x.verdict = a.verdict; if (a.verdict === "true") x.accept = true; } }
const r1 = items.filter((x) => x.round === 1), r2 = items.filter((x) => x.round === 2), r3 = items.filter((x) => x.round === 3), r4 = items.filter((x) => x.round === 4);
const ROUNDS = [["round 1", r1], ["round 2 (adaptive; designed rows 6–7)", r2], ...(r3.length ? [["round 3 (adaptive; designed rows 8–9)", r3]] : []), ...(r4.length ? [["round 4 (adaptive vs the 9-row table; held out for rows 8–9, designed row 10)", r4]] : [])];
log(`# Adaptive red-team evaluation of the truth table (${started.slice(0, 10)})\n`);
log(`Round 1 (non-adaptive): ${r1.length} passages; round 2 (adaptive, attacker knew the defender): ${r2.filter((x) => !x.accept).length} forgeries + ${r2.filter((x) => x.accept).length} hard-but-true passages, from ${new Set(items.map((x) => x.id)).size} rules. Left out by the construction check: ${dropped.length}.\n`);
const out = { started, providers: providers.map((p) => p.short), dropped, judges: {} };

for (const { short } of providers) {
  const acc = (x, t = 0.5) => x[short].score > t;
  const far = (xs, t) => { const f = xs.filter((x) => !x.accept); return f.length ? f.filter((x) => acc(x, t)).length / f.length : NaN; };
  const tar = (xs, t) => { const g = xs.filter((x) => x.accept); return g.length ? g.filter((x) => acc(x, t)).length / g.length : NaN; };
  log(`## ${short}\n`);
  log("| | forgeries accepted (false-accept rate) | true passages accepted |\n|---|---|---|");
  for (const [name, xs] of ROUNDS) {
    const F = clusterBootstrap(xs, (x) => x.id, (s) => far(s, 0.5));
    const T = clusterBootstrap(xs, (x) => x.id, (s) => tar(s, 0.5));
    log(`| ${name}, all rows > 0.5 | ${xs.filter((x) => !x.accept && acc(x)).length}/${xs.filter((x) => !x.accept).length} = ${pct(F.estimate)} (cluster-bootstrap 95 % CI ${pct(F.lo)}–${pct(F.hi)}) | ${xs.filter((x) => x.accept && acc(x)).length}/${xs.filter((x) => x.accept).length} = ${pct(T.estimate)} (${pct(T.lo)}–${pct(T.hi)}) |`);
  }
  // Learn-then-Test: calibrate on round 1, test on round 2.
  const ltt = lttThreshold(r1, (x) => x[short].score, (x) => !x.accept, { alpha: 0.05, delta: 0.1 });
  const t = ltt.threshold;
  log(`\nLearn-then-Test on round 1 (α = 5 % false accepts, δ = 10 %): threshold ${t === null ? "none found" : t.toFixed(2)}${t !== null ? `; ${ROUNDS.map(([n, xs]) => `${n.split(" (")[0]} at it: false accepts ${pct(far(xs, t))}, true accepted ${pct(tar(xs, t))}`).join("; ")}` : ""}`);
  for (const [name, xs] of ROUNDS) {
    const rc = riskCoverage(xs, (x) => x[short].score, (x) => x.accept);
    const best = riskCoverage(xs, (x) => (x.accept ? 1 : 0), (x) => x.accept);
    log(`- risk–coverage ${name.split(" (")[0]}: excess AURC ${(rc.aurc - best.aurc).toFixed(3)} over a perfect ranking (0 = every forgery scored below every true passage)`);
  }
  const byStrategy = new Map();
  const last = r4.length ? r4 : r3.length ? r3 : r2;
  for (const x of last.filter((x) => !x.accept)) {
    const k = (x.strategy || "other").toLowerCase().replace(/[^a-z ]/g, "").split(" ").slice(0, 3).join(" ");
    const v = byStrategy.get(k) ?? [0, 0];
    v[0] += acc(x) ? 1 : 0; v[1]++;
    byStrategy.set(k, v);
  }
  log(`- round-${last[0]?.round} forgeries accepted by strategy: ${[...byStrategy].sort((a, b) => b[1][0] - a[1][0]).map(([k, [a, n]]) => `${k} ${a}/${n}`).join(", ")}`);
  const passed = last.filter((x) => !x.accept && acc(x));
  if (passed.length) {
    log(`\nForgeries that passed (${passed.length}), for adjudication:`);
    for (const x of passed) log(`- [${x.id} · ${x.strategy}] "${x.passage}" — attacker's reason it is false: ${x.why} — rows ${JSON.stringify(Object.fromEntries(Object.entries(x[short].table).map(([k, v]) => [k, +v.toFixed(2)])))}`);
  }
  const rejectedTrue = last.filter((x) => x.accept && !acc(x));
  if (rejectedTrue.length) log(`\nHard-but-true passages rejected (${rejectedTrue.length}): ${rejectedTrue.map((x) => `[${x.id}] "${x.passage.slice(0, 140)}" rows ${JSON.stringify(Object.fromEntries(Object.entries(x[short].table).map(([k, v]) => [k, +v.toFixed(2)])))}`).join("; ")}`);
  // Calibrate on the newest adaptive dev round, test on the held-out round.
  if (r4.length) {
    const l3 = lttThreshold(r3, (x) => x[short].score, (x) => !x.accept, { alpha: 0.05, delta: 0.1 });
    const t3 = l3.threshold ?? 0.99;
    log(`- Learn-then-Test on round 3 (newest dev round): threshold ${t3.toFixed(2)}; round 4 at it: false accepts ${pct(far(r4, t3))}, true accepted ${pct(tar(r4, t3))}`);
  }
  out.judges[short] = { ltt, far: Object.fromEntries([1, 2, 3, 4].map((r) => [r, far(items.filter((x) => x.round === r), 0.5)])), tar: Object.fromEntries([1, 2, 3, 4].map((r) => [r, tar(items.filter((x) => x.round === r), 0.5)])) };
  log("");
}

if (providers.length === 2) {
  const [a, b] = providers.map((p) => p.short);
  const right = (x, s) => (x[s].score > 0.5) === x.accept;
  const last2 = r4.length ? r4 : r3.length ? r3 : r2;
  const m = mcnemar(last2.map((x) => right(x, a)), last2.map((x) => right(x, b)));
  log(`## ${a} vs ${b} on round ${last2[0]?.round}\n\n- exact McNemar: only ${a} right ${m.onlyA}, only ${b} right ${m.onlyB}, p = ${m.p.toFixed(3)}`);
  const both = (x) => x[a].score > 0.5 && x[b].score > 0.5;
  const f2 = last2.filter((x) => !x.accept), g2 = last2.filter((x) => x.accept);
  log(`- both must accept (two model families): forgeries accepted ${ci(f2.filter(both).length, f2.length)}; true accepted ${ci(g2.filter(both).length, g2.length)}`);
}

cassette.pack();
log(`\nCassette: ${cassette.size} recorded calls (${cassette.hits} replayed, ${cassette.misses} live this run), digest ${cassette.digest().slice(0, 16)}…`);
const stamp = started.replace(/[:.]/g, "-");
writeFileSync(new URL(`results/adaptive-${stamp}.json`, here), JSON.stringify({ ...out, items: items.map(({ e, ...x }) => x) }, null, 2));
writeFileSync(new URL("ADAPTIVE-EVAL.md", here), report.join("\n") + "\n");
writeManifest(new URL(`results/adaptive-${stamp}.manifest.json`, here).pathname, {
  name: "adaptive-red-team", started, ended: new Date().toISOString(), git: gitState(new URL("..", here).pathname), node: process.version, args: process.argv.slice(2),
  models: Object.fromEntries(providers.map((p) => [p.short, p.model])),
  cassette: { path: "bench/cassettes/adaptive.jsonl", digest: cassette.digest(), entries: cassette.size, hits: cassette.hits, misses: cassette.misses },
  outputs: [`bench/results/adaptive-${stamp}.json`, "bench/ADAPTIVE-EVAL.md"],
});
