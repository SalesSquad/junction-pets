#!/usr/bin/env node
// TimeLaw-Situations: judge tournament. For every situation, each judge answers the same yes/no question per
// clause once (CLAUSE_QUESTION from the library, cached); every strategy is then scored from those
// probabilities, so strategies differ only in how they combine evidence.
//
// Scoring rules (after the 14 Nov review):
//   - gold is the target clause by full text; a tie at the top shares the credit (0.5 for a two-way tie);
//   - a judge that gives every clause exactly 0 has abstained: it is reported as coverage and as accuracy on
//     answered items, and it earns chance credit, not "picked clause 0";
//   - a missing judgment is an error, never a silent 0;
//   - every number comes with a 95 % interval from a bootstrap over clusters (whole provisions' clusters are
//     resampled, because situations of one provision are not independent), and pairs of strategies are
//     compared with the paired cluster bootstrap;
//   - baselines: chance, always the first clause, and word overlap (no model);
//   - the cascade margin is chosen on a tuning file (--tune=valid.jsonl) for a target escalation rate, never
//     on the file being reported.
//
// Strategies: jev, luna, mean; code+X (tiers the stated facts contradict are ruled out first); each
// --student=name:file[,name2:file2] as name, code+name and name→luna (student first, Luna on close calls).
//
// Usage: node --experimental-strip-types bench/situations/tournament.mjs test.jsonl [--student=q17:runs/q17/judgments-test.jsonl]
//          [--tier=clean] [--tune=valid.jsonl --tune-student=q17:runs/q17/judgments-valid.jsonl] [--no-cloud] [--compare=q17,jev]
import { readFileSync, writeFileSync, existsSync, appendFileSync } from "node:fs";
import { homedir } from "node:os";
import { CLAUSE_QUESTION, codeFits } from "../../src/timetravel/timetravel.ts";
import { typesafeJev, openaiDecisions } from "../../src/decide/decide.ts";

const file = process.argv[2];
const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const limit = Number(arg("limit", "100000"));
const tier = arg("tier", "");
const noCloud = process.argv.includes("--no-cloud");
const targetEscalation = Number(arg("escalate", "0.2"));
const ensembles = arg("ensemble", "").split(";").filter(Boolean);

let JUDGES = {};
if (!noCloud) {
  const tsKey = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
  const oaKey = readFileSync(`${homedir()}/.config/openai/factory-decisions.env`, "utf8").match(/^OPENAI_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
  const { TypeSafeClient } = await import("@typesafe-ai/sdk");
  const ts = new TypeSafeClient({ apiKey: tsKey, defaultModel: "jev-1.14.0" });
  JUDGES = { jev: typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) }), luna: openaiDecisions({ apiKey: oaKey, model: "gpt-6-luna" }) };
}
const readStudents = (spec) => Object.fromEntries((spec ? spec.split(",") : []).map((s) => { const [name, f] = s.includes(":") ? s.split(/:(.*)/) : ["student", s]; return [name, new Map(readFileSync(f, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); if (j.abstained) ABSTAINED.add(`${name}|${j.k}`); return [j.k, j.p]; }))]; }));
// Keys a judge did not answer (choice_judges.mjs --fill-abstain writes them as uniform probabilities): they earn
// chance credit in accuracy, and in the signing rule they are an abstention, never a vote.
const ABSTAINED = new Set();
const students = readStudents(arg("student", ""));

// Without an exported tier: "clean" needs a second reader's confirmation (v === true), as in export_training.py.
// An item only its writer recovered is "half" (the first version called it clean).
const tierOf = (x) => { const g = !!x.generatorRecovers, v = x.recovers2; return x.tier ?? (g && v === true ? "clean" : g || v ? "half" : "none"); };
const loadItems = (f) => readFileSync(f, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).filter((x) => !tier || tierOf(x) === tier).slice(0, limit);
const cacheOf = (f) => {
  const cf = f.replace(/\.jsonl$/, ".judgments.jsonl");
  return { cf, map: new Map(existsSync(cf) ? readFileSync(cf, "utf8").split("\n").filter(Boolean).map((l) => { const j = JSON.parse(l); return [j.k, j]; }) : []) };
};
async function judge(cache, name, situation, clause) {
  const k = `${name}|${situation}|${clause}`;
  if (cache.map.has(k)) return cache.map.get(k);
  if (!JUDGES[name]) throw new Error(`no cached ${name} judgment and --no-cloud is set`);
  const t0 = Date.now();
  let r;
  for (let i = 0; i < 4; i++) {
    try { r = await JUDGES[name].decide({ situation, clause }, [CLAUSE_QUESTION]); break; } catch (e) { if (i === 3) throw e; await new Promise((s) => setTimeout(s, 1000 * 2 ** i)); }
  }
  if (typeof r.answers[0]?.p !== "number") throw new Error(`${name} returned no probability`);
  const j = { k, p: r.answers[0].p, ms: Date.now() - t0, tokens: r.usage?.inputTokens ?? 0 };
  cache.map.set(k, j);
  appendFileSync(cache.cf, JSON.stringify(j) + "\n");
  return j;
}

// ---------- per-item evidence ----------
const W = (s) => new Set(s.toLowerCase().match(/[a-zäöüßå0-9]{4,}/g) ?? []);
async function evidence(f, studs) {
  const items = loadItems(f);
  const cache = cacheOf(f);
  const rows = new Array(items.length);
  let next = 0, done = 0;
  await Promise.all(Array.from({ length: 6 }, async () => {
    while (next < items.length) {
      const idx = next++;
      const it = items[idx];
      const cs = it.clauses;
      const [jev, luna] = noCloud && !cache.map.size ? [null, null] : await Promise.all(["jev", "luna"].map((j) => Promise.all(cs.map((c) => judge(cache, j, it.question, c)))));
      const S = Object.fromEntries(Object.entries(studs).map(([name, m]) => [name, cs.map((c) => { const v = m.get(`student|${it.question}|${c}`); if (v === undefined) throw new Error(`no ${name} judgment for ${it.gid}`); return v; })]));
      const q = W(it.question), df = new Map();
      cs.forEach((c) => W(c).forEach((w) => df.set(w, (df.get(w) ?? 0) + 1)));
      const lexical = cs.map((c) => [...W(c)].reduce((s, w) => s + (q.has(w) ? 1 / df.get(w) : 0), 0));
      rows[idx] = { it, J: jev?.map((x) => x.p), L: luna?.map((x) => x.p), S, lexical, fits: codeFits(it.question, cs), ms: jev ? { jev: Math.max(...jev.map((x) => x.ms)), luna: Math.max(...luna.map((x) => x.ms)) } : {} };
      if (++done % 200 === 0) console.error(`${f.split("/").at(-1)} ${done}/${items.length}`);
    }
  }));
  return rows;
}

// ---------- strategies: each returns a score per clause (argmax with shared ties is the answer) ----------
const gold = (it) => it.clauses.map((c, i) => (c === it.clauses[it.target] ? i : -1)).filter((i) => i >= 0);
const credit = (xs, it, ok = () => true) => {
  let m = -Infinity;
  xs.forEach((x, i) => { if (ok(i) && x > m) m = x; });
  const tops = xs.map((x, i) => (ok(i) && x === m ? i : -1)).filter((i) => i >= 0);
  const g = gold(it);
  return tops.filter((i) => g.includes(i)).length / Math.max(1, tops.length);
};
const liveOf = (r) => (r.fits.some((f) => f !== "fail") ? (i) => r.fits[i] !== "fail" : () => true);
const bonus = (r, xs) => xs.map((x, i) => x + (r.fits[i] === "fit" || r.fits[i] === "all" ? 0.05 : 0));
const margin = (xs, live) => { const o = xs.map((x, i) => (live(i) ? x : -Infinity)).sort((a, b) => b - a); return o.length > 1 ? o[0] - o[1] : Infinity; };
const cascade = (r, first, m) => {
  const live = liveOf(r);
  const order = first.map((_, i) => i).filter(live).sort((a, b) => first[b] - first[a]);
  const esc = order.length > 1 && first[order[0]] - first[order[1]] < m;
  const xs = first.slice();
  if (esc) for (const i of order.slice(0, 2)) xs[i] = (first[i] + r.L[i]) / 2;
  return { xs: bonus(r, xs), esc };
};
function score(rows, margins) {
  const out = [];
  for (const r of rows) {
    const live = liveOf(r), it = r.it, k = it.clauses.length;
    const ok = { chance: gold(it).length / k, first: gold(it).includes(0) ? 1 : 0, lexical: credit(r.lexical, it) };
    const esc = {};
    if (r.J) {
      const mean = r.J.map((x, i) => (x + r.L[i]) / 2);
      const lunaAbstains = r.L.every((x) => x === 0);
      Object.assign(ok, { jev: credit(r.J, it), luna: credit(r.L, it), mean: credit(mean, it), "code+jev": credit(bonus(r, r.J), it, live), "code+luna": credit(bonus(r, r.L), it, live), "code+mean": credit(bonus(r, mean), it, live) });
      const c = cascade(r, r.J, margins.jev ?? 0.25);
      ok["code+jev→luna"] = credit(c.xs, it, live); esc["code+jev→luna"] = c.esc;
      r.lunaAbstains = lunaAbstains;
    }
    for (const [name, S] of Object.entries(r.S)) {
      ok[name] = credit(S, it); ok[`code+${name}`] = credit(bonus(r, S), it, live);
      if (r.L) { const c = cascade(r, S, margins[name] ?? 0.25); ok[`code+${name}→luna`] = credit(c.xs, it, live); esc[`code+${name}→luna`] = c.esc; }
    }
    // --ensemble=a+b+c: the mean of the named sources (jev, luna or a student name), with the code filter.
    const src = (name) => (name === "jev" ? r.J : name === "luna" ? r.L : r.S[name]);
    const pickOf = (xs, ok = () => true) => { let m = -Infinity, at = -1; xs.forEach((x, i) => { if (ok(i) && x > m) { m = x; at = i; } }); return at; };
    const agree = {};
    for (const e of ensembles) {
      const parts = e.split("+").map(src);
      if (parts.some((x) => !x)) continue;
      const mean = it.clauses.map((_, i) => parts.reduce((a, x) => a + x[i], 0) / parts.length);
      ok[`mean(${e})`] = credit(mean, it); ok[`code+mean(${e})`] = credit(bonus(r, mean), it, live);
      // Signing rule, the same as chooseClause in the product: every member has a strict top option (a tie or an
      // abstention is not a vote), all tops are the same clause, and code has not ruled that clause out.
      const names = e.split("+");
      const strict = (x) => { const m = Math.max(...x); const i = x.indexOf(m); return i === x.lastIndexOf(m) ? i : -1; };
      const picks = parts.map((x, n) => (ABSTAINED.has(`${names[n]}|student|${it.question}|${it.clauses[0]}`) ? -1 : strict(x)));
      const same = picks[0] >= 0 && picks.every((x) => x === picks[0]) && live(picks[0]);
      agree[e] = { signed: same, right: same && gold(it).includes(picks[0]), noVote: picks.filter((x) => x < 0).length };
    }
    out.push({ agree, gid: it.gid, cluster: it.cluster ?? it.provision, provision: it.provision, lang: it.lang, attack: it.attack ?? null, jurisdiction: it.jurisdiction, tier: tierOf(it), n: k, ok, esc, lunaAbstains: !!r.lunaAbstains, ruledOut: k - it.clauses.filter((_, i) => live(i)).length, ms: r.ms });
  }
  return out;
}
/** The margin below which a first judge escalates, chosen so that about `rate` of the tuning items escalate. */
const tuneMargin = (rows, first, rate) => {
  const ms = rows.map((r) => margin(first(r), liveOf(r))).filter(Number.isFinite).sort((a, b) => a - b);
  return ms.length ? ms[Math.min(ms.length - 1, Math.floor(rate * ms.length))] : 0.25;
};

// ---------- run ----------
const margins = {};
const tuneFile = arg("tune", "");
if (tuneFile) {
  const tuneStudents = readStudents(arg("tune-student", ""));
  const tr = await evidence(tuneFile, tuneStudents);
  if (tr[0]?.J) margins.jev = tuneMargin(tr, (r) => r.J, targetEscalation);
  for (const name of Object.keys(tuneStudents)) margins[name] = tuneMargin(tr, (r) => r.S[name], targetEscalation);
}
const results = score(await evidence(file, students), margins);

// ---------- statistics: bootstrap over clusters ----------
let seed = 12345;
// Integer-exact: the earlier `seed * 1103515245 % 2^31` overflowed 2^53 and fell into a cycle of 10,466 states.
const rnd = () => (seed = (Math.imul(seed, 1103515245) + 12345) >>> 0) / 4294967296;
const byCluster = (rs) => { const m = new Map(); for (const r of rs) m.set(r.cluster, [...(m.get(r.cluster) ?? []), r]); return [...m.values()]; };
function interval(rs, f, B = 2000) {
  const cl = byCluster(rs);
  const point = rs.reduce((a, r) => a + f(r), 0) / Math.max(1, rs.length);
  const xs = [];
  for (let b = 0; b < B; b++) {
    let s = 0, n = 0;
    for (let i = 0; i < cl.length; i++) for (const r of cl[Math.floor(rnd() * cl.length)]) { s += f(r); n++; }
    xs.push(s / Math.max(1, n));
  }
  xs.sort((a, b) => a - b);
  return { point, lo: xs[Math.floor(0.025 * B)], hi: xs[Math.floor(0.975 * B)], pPositive: xs.filter((x) => x > 0).length / B };
}
const fmt = (v) => `${(100 * v.point).toFixed(1)} [${(100 * v.lo).toFixed(1)}, ${(100 * v.hi).toFixed(1)}]`;
const strategies = Object.keys(results[0]?.ok ?? {});
const table = (rs) => Object.fromEntries(strategies.map((s) => [s, fmt(interval(rs, (r) => r.ok[s]))]));
const slices = (key) => Object.fromEntries([...new Set(results.map(key))].map((v) => [String(v), { n: results.filter((r) => key(r) === v).length, ...table(results.filter((r) => key(r) === v)) }]));
const pct = (xs, q) => xs.slice().sort((a, b) => a - b)[Math.floor(q * (xs.length - 1))];
const compare = arg("compare", "").split(";").filter(Boolean).map((p) => p.split(","));
const answered = results.filter((r) => !r.lunaAbstains);
const summary = {
  file, items: results.length, clusters: byCluster(results).length, provisions: new Set(results.map((r) => r.provision)).size, tierFilter: tier || "all",
  note: "accuracy in %, 95 % interval from a bootstrap over clusters; ties share credit",
  all: table(results),
  byTier: slices((r) => r.tier), byLanguage: slices((r) => r.lang), byJurisdiction: slices((r) => r.jurisdiction), byAttack: slices((r) => r.attack ?? "none"),
  lexicalHard: { n: results.filter((r) => r.ok.lexical < 1).length, ...table(results.filter((r) => r.ok.lexical < 1)) },
  luna: results[0]?.ok.luna !== undefined ? { coverage: `${answered.length}/${results.length}`, accuracyWhenAnswered: fmt(interval(answered, (r) => r.ok.luna)), jevOnSameItems: fmt(interval(answered, (r) => r.ok.jev)) } : undefined,
  paired: Object.fromEntries(compare.map(([x, y]) => { const d = interval(results, (r) => r.ok[x] - r.ok[y]); return [`${x} - ${y}`, { difference: fmt(d), pPositive: d.pPositive }]; })),
  escalation: Object.fromEntries(strategies.filter((s) => s.includes("→")).map((s) => [s, { rate: `${results.filter((r) => r.esc[s]).length}/${results.length}`, margin: margins[s.replace(/^code\+|→luna$/g, "")] ?? 0.25, tunedOn: tuneFile || "default 0.25 (not tuned)" }])),
  signing: Object.fromEntries(ensembles.filter((e) => results[0]?.agree?.[e]).map((e) => {
    const signed = results.filter((r) => r.agree[e].signed);
    return [e, { rule: "all members pick the same clause and code allows it", coverage: `${signed.length}/${results.length} (${((100 * signed.length) / Math.max(1, results.length)).toFixed(1)} %)`, accuracyWhenSigned: fmt(interval(signed, (r) => (r.agree[e].right ? 1 : 0))), onCleanItems: fmt(interval(signed.filter((r) => r.tier === "clean"), (r) => (r.agree[e].right ? 1 : 0))) }];
  })),
  codeRuledOutPerItem: (results.reduce((a, r) => a + r.ruledOut, 0) / Math.max(1, results.length)).toFixed(2),
  latencyMsP50: results[0]?.ms?.jev ? { jev: pct(results.map((r) => r.ms.jev), 0.5), luna: pct(results.map((r) => r.ms.luna), 0.5) } : undefined,
};
console.log(JSON.stringify(summary, null, 1));
writeFileSync(file.replace(/\.jsonl$/, `.tournament-${new Date().toISOString().replace(/[:.]/g, "-")}.json`), JSON.stringify({ summary, results }, null, 1));
