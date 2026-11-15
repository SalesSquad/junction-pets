#!/usr/bin/env node
// Then · Now · Next simulations: ~20 situations, each with an independent oracle.
// Gold for every scenario is computed from the official text on the date with a hand-written pattern
// (which clause applies), never from the judge's choice: provision found? amount then? amount now?
// changed? Also latency.
// Sets: core (23 tuned-on scenarios), heldout (13 written after the fixes, never tuned on), sweep (one question
// across many dates). --repeat=N runs the set N times (stability); --warrant also signs each answer and replays
// three receivers: the pinned version (must ACCEPT), a forged amount (must REJECT), a date-blind fetch of today's
// text (must REJECT when the amount changed).
// Usage: node bench/thennow_sim.mjs [--set=core|heldout|sweep] [--only=id,id] [--repeat=N] [--warrant]
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { typesafeJev } from "../src/decide/decide.ts";
import { amountClauses, thenNowNext } from "../src/timetravel/timetravel.ts";
import { lawOn } from "../src/warrant/pointInTime.ts";
import { extractQuantities } from "../src/warrant/lanes.ts";

const here = new URL(".", import.meta.url);
const only = process.argv.find((a) => a.startsWith("--only="))?.slice(7).split(",");
const set = process.argv.find((a) => a.startsWith("--set="))?.slice(6) ?? "core";
const repeat = Number(process.argv.find((a) => a.startsWith("--repeat="))?.slice(9) ?? 1);
const withWarrant = process.argv.includes("--warrant");
const key = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)[1].trim().replace(/^["']|["']$/g, "");
const { TypeSafeClient } = await import("@typesafe-ai/sdk");
const ts = new TypeSafeClient({ apiKey: key, defaultModel: "jev-1.14.0" });
const judge = typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o) });
// Second judge for close calls (Jev's two best within 0.25): OpenAI Decisions API (Luna), if a key file exists.
const { openaiDecisions } = await import("../src/decide/decide.ts");
const openaiKey = process.argv.includes("--no-luna") ? null : (() => { try { return readFileSync(`${homedir()}/.config/openai/factory-decisions.env`, "utf8").match(/^OPENAI_API_KEY=(.*)$/m)?.[1]?.trim().replace(/^["']|["']$/g, ""); } catch { return null; } })();
const second = openaiKey ? openaiDecisions({ apiKey: openaiKey, model: "gpt-6-luna" }) : undefined;
// --local=http://127.0.0.1:8000: our own Decisions API picks the clause (Jev still chooses the provision).
const localUrl = process.argv.find((a) => a.startsWith("--local="))?.slice(8);
// --catalog=http://127.0.0.1:8791: the on-device semantic catalog as one more source of provision candidates.
const catalogUrl = process.argv.find((a) => a.startsWith("--catalog="))?.slice(10);
const catalogSearch = catalogUrl
  ? async (question, date) => ((await (await fetch(`${catalogUrl}/search`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ query: question.slice(0, 4000), k: 5, ...(date ? { year: Number(date.slice(0, 4)) } : {}) }) })).json()).results ?? []).map((x) => ({ kind: "cfr", ref: { source: "ecfr", title: Number(x.title), part: String(x.part), section: String(x.section) }, title: `${x.title} CFR ${x.section} — ${x.subject}`, about: String(x.text ?? "").slice(0, 300), score: x.score }))
  : undefined;
const { localDecisions } = await import("../src/decide/decide.ts");
const mainJudge = localUrl ? localDecisions({ baseUrl: localUrl, fallback: judge }) : judge;
// Third panel member: NVIDIA Nemotron on the Verda endpoint (letter log-probabilities), if its key is in the Keychain.
const { logprobDecisions } = await import("../src/decide/decide.ts");
const { execFileSync } = await import("node:child_process");
const nemoKey = process.argv.includes("--no-nemotron") ? null : (() => { try { return process.env.VERDA_INFERENCE_KEY || execFileSync("security", ["find-generic-password", "-s", "salesquad.junction2026.verda-dc", "-w"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim(); } catch { return null; } })();
const panel = nemoKey ? [logprobDecisions({ id: "nemotron-3.5-super-vl", baseUrl: "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1", apiKey: nemoKey, model: "nemotron-3.5-super-vl" })] : [];

const DBC = { source: "ecfr", title: 14, part: "250", section: "250.5" };
const NLW = { source: "ukleg", path: "uksi/2015/621/regulation/4" };
const NMW4A = { source: "ukleg", path: "uksi/2015/621/regulation/4A" };
const SSP = { source: "ukleg", path: "ukpga/1992/4/section/157" };
const WEEK = { source: "ukleg", path: "ukpga/1996/18/section/227" };
const SMP = { source: "ukleg", path: "uksi/1986/1960/regulation/6" };
const EU261 = { source: "eurlex", celex: "32004R0261", article: "7" };
const GDPR = { source: "eurlex", celex: "32016R0679", article: "12" };
const FTC = { source: "ecfr", title: 16, part: "1", section: "1.98" };
const CARD = { source: "ecfr", title: 12, part: "1026", section: "1026.52" };
const CHILD = { source: "ecfr", title: 29, part: "579", section: "579.1" };
const SPP = { source: "ukleg", path: "uksi/2002/2818/regulation/2" };

// gold: the provision, and the pattern that identifies the applying clause in the official text.
const domestic3h = /interstate[^]*more than two hours|interstate[^]*does not offer alternate transportation/;
const S = [
  { id: "us-dbc-2019", q: "I was bumped from an oversold US domestic flight on 2019-07-01; the substitute flight arrived 3 hours late. How much denied boarding compensation?", d: "2019-07-01", ref: DBC, gold: domestic3h },
  { id: "us-dbc-2021", q: "I was bumped from an oversold US domestic flight on 2021-06-10; the substitute flight arrived 3 hours late. How much denied boarding compensation?", d: "2021-06-10", ref: DBC, gold: domestic3h },
  { id: "us-dbc-2025", q: "I was bumped from an oversold US domestic flight on 2025-03-15; the substitute flight arrived 3 hours late. How much denied boarding compensation?", d: "2025-03-15", ref: DBC, gold: domestic3h },
  { id: "us-dbc-90min", q: "Bumped from an oversold US domestic flight on 2023-02-01; the alternate flight got me there 90 minutes later than planned. What compensation?", d: "2023-02-01", ref: DBC, gold: /interstate[^]*more than one hour but less than two hours/ },
  { id: "us-dbc-day-before", q: "I was bumped from an oversold US domestic flight on 2025-01-21 and arrived 3 hours late on the substitute flight. Compensation?", d: "2025-01-21", ref: DBC, gold: domestic3h },
  { id: "us-dbc-change-day", q: "I was bumped from an oversold US domestic flight on 2025-01-22 and arrived 3 hours late on the substitute flight. Compensation?", d: "2025-01-22", ref: DBC, gold: domestic3h },
  // 14 CFR 250.5(b) covers passengers denied boarding at a US airport, so the international case departs from New York.
  { id: "us-dbc-intl-2021", q: "Bumped from an oversold flight from New York to Paris (foreign air transportation, departing a US airport) on 2021-05-01; the substitute arrived 5 hours late. Maximum compensation?", d: "2021-05-01", ref: DBC, gold: /foreign air transportation[^]*more than four hours|foreign air transportation[^]*does not offer/ },
  // The reverse direction departs from the EU: the US rule does not apply, Regulation 261/2004 does (over 3,500 km).
  { id: "eu-dbc-paris-nyc", q: "I was denied boarding on an overbooked flight from Paris to New York (about 5,800 km) on 2021-05-01. How much compensation?", d: "2021-05-01", ref: EU261, gold: /not falling under/ },
  { id: "us-dbc-slang", q: "Got kicked off an overbooked Delta flight in Texas on 2022-08-20 and only got to Denver 4 hours later on the next plane. What do they owe me?", d: "2022-08-20", ref: DBC, gold: domestic3h },
  { id: "us-card-2019", q: "My credit card issuer charged me a late payment fee on 2019-05-01; it was my first late payment. What is the maximum safe-harbor late fee?", d: "2019-05-01", ref: CARD, gold: /\(A\)\s*\$\d+/ },
  { id: "us-ftc-offsearch", q: "What was the maximum civil penalty per violation the FTC could seek under section 5(l) of the FTC Act on 2023-03-01?", d: "2023-03-01", ref: FTC, gold: /5\(\s?l\s?\) of the FTC Act/ },
  { id: "uk-nlw-2017", q: "I am 30 and was paid £7.00 an hour in the UK on 2017-06-01. What was the national living wage then?", d: "2017-06-01", ref: NLW, gold: /national living wage/i },
  { id: "uk-nlw-day-before", q: "UK minimum wage for a 30-year-old on 2024-03-31 — what was the national living wage per hour?", d: "2024-03-31", ref: NLW, gold: /national living wage/i },
  { id: "uk-nlw-change-day", q: "UK minimum wage for a 30-year-old on 2024-04-01 — what was the national living wage per hour?", d: "2024-04-01", ref: NLW, gold: /national living wage/i },
  { id: "uk-nmw-age19", q: "I was 19 years old and worked in the UK on 2022-07-01 for £5.50 an hour. What was the minimum wage for my age?", d: "2022-07-01", ref: NMW4A, gold: /aged 18 or over|18 or over|aged 18/ },
  { id: "uk-ssp-2022", q: "I was off sick from work in the UK on 2022-09-01. What was the weekly rate of statutory sick pay?", d: "2022-09-01", ref: SSP, gold: /£/ },
  { id: "uk-week-2019", q: "I was made redundant in the UK on 2019-05-01. What was the maximum amount of a week's pay used for statutory redundancy pay?", d: "2019-05-01", ref: WEEK, gold: /£/ },
  { id: "uk-smp-2021", q: "What was the weekly rate of statutory maternity pay in the UK on 2021-06-01?", d: "2021-06-01", ref: SMP, gold: /£/ },
  { id: "eu261-1200", q: "My EU flight of 1,200 km was cancelled on 2019-03-01 without notice. How much compensation under EU261?", d: "2019-03-01", ref: EU261, gold: /1500 kilometres or less/ },
  { id: "eu261-2000", q: "My intra-EU flight of 2,000 km from Helsinki to Madrid was cancelled on 2022-05-10 at short notice. How much compensation under EU261?", d: "2022-05-10", ref: EU261, gold: /intra-Community flights of more than 1500/ },
  { id: "eu261-fi", q: "Lentoni Helsingistä Berliiniin (noin 1 100 km) peruttiin 2023-09-01 ilman ennakkoilmoitusta. Paljonko korvausta saan EU-asetuksen 261/2004 mukaan?", d: "2023-09-01", ref: EU261, gold: /1500 kilometres or less/ },
  { id: "gdpr-deadline", q: "I sent a GDPR data access request on 2024-02-01. How long does the company have to respond?", d: "2024-02-01", ref: GDPR, gold: /one month/ },
  { id: "edge-future", q: "I will be bumped from an oversold US domestic flight on 2027-06-01 and arrive 3 hours late. What compensation will apply?", d: "2027-06-01", ref: DBC, gold: domestic3h, expect: "future" },
  { id: "edge-before", q: "What was the UK national living wage on 2014-06-01?", d: "2014-06-01", ref: NLW, gold: /national living wage/i, expect: "no-provision" },
];

const HELDOUT = [
  { id: "h-us-foreign-3h", q: "I was involuntarily bumped from an oversold Chicago to London flight (foreign air transportation from a US airport) on 2023-04-10; the alternate flight arrived 3 hours after my planned arrival. What compensation cap applied?", d: "2023-04-10", ref: DBC, gold: /foreign air transportation[^]*more than one hour but less than four hours/ },
  { id: "h-us-under-1h", q: "I was bumped from an oversold US domestic flight on 2024-05-20, but the airline's alternate flight got me there only 45 minutes later than planned. How much compensation?", d: "2024-05-20", ref: DBC, gold: /interstate[^]*No compensation is required/ },
  { id: "h-eu261-extra-5800", q: "My flight from Paris to New York (about 5,800 km) with an EU airline was cancelled without notice on 2021-11-03. How much EU261 compensation?", d: "2021-11-03", ref: EU261, gold: /not falling under/ },
  { id: "h-eu261-intra-4900", q: "My flight from Helsinki to Las Palmas de Gran Canaria (about 4,900 km, within the EU) was cancelled on 2024-01-15. How much EU261 compensation?", d: "2024-01-15", ref: EU261, gold: /intra-Community flights of more than 1500/ },
  { id: "h-eu261-de", q: "Mein Flug von München nach Lissabon (ca. 1.900 km) wurde am 2022-07-14 kurzfristig annulliert. Wie viel Entschädigung steht mir nach der EU-Verordnung 261/2004 zu?", d: "2022-07-14", ref: EU261, gold: /intra-Community flights of more than 1500/ },
  { id: "h-uk-age17-2023", q: "I am 17 and worked a part-time job in the UK on 2023-08-01. What was the minimum hourly wage for my age?", d: "2023-08-01", ref: NMW4A, gold: /aged under 18/ },
  { id: "h-uk-age22-2023", q: "I was 22 years old and working in the UK on 2023-06-01. Which hourly minimum wage applied to me?", d: "2023-06-01", ref: NMW4A, gold: /aged 21 years or over/, nowRef: NLW, nowGold: /national living wage|aged 21/i },
  { id: "h-uk-apprentice-2020", q: "I was a first-year apprentice aged 19 in the UK on 2020-09-01. What was the apprenticeship minimum hourly rate?", d: "2020-09-01", ref: NMW4A, gold: /apprenticeship rate applies/ },
  { id: "h-uk-spp-2020", q: "What was the weekly rate of statutory paternity pay in the UK on 2020-06-01?", d: "2020-06-01", ref: SPP, gold: /£/ },
  { id: "h-us-card-repeat-2021", q: "My credit card issuer charged me a second late fee on 2021-03-10, within six billing cycles of an earlier late fee of the same type. What was the maximum safe-harbor fee?", d: "2021-03-10", ref: CARD, gold: /\(B\)\s*\$\d+/ },
  { id: "h-us-childlabor-2022", q: "What was the maximum civil money penalty per employee for a child labor violation under the FLSA on 2022-02-01?", d: "2022-02-01", ref: CHILD, gold: /child labor[^]*\(A\)\s*\$[\d,]+ for each employee/ },
  { id: "h-ftc-5m-2024", q: "What was the maximum civil penalty under section 5(m)(1)(A) of the FTC Act on 2024-03-01?", d: "2024-03-01", ref: FTC, gold: /5\(m\)\(1\)\(A\) of the FTC Act/ },
  { id: "h-gdpr-fi", q: "Lähetin GDPR-tietopyynnön yritykselle 2023-05-02. Missä ajassa yrityksen on vastattava?", d: "2023-05-02", ref: GDPR, gold: /one month/ },
];
const SWEEP = [
  ...["2017-06-01", "2018-06-01", "2019-06-01", "2019-11-30", "2020-06-01", "2021-06-01", "2022-06-01", "2023-06-01", "2024-06-01", "2025-01-21", "2025-01-22", "2025-06-01", "2026-06-01"].map((d) => ({ id: `sw-us-${d}`, q: `I was bumped from an oversold US domestic flight on ${d}; the substitute flight arrived 3 hours late. How much compensation?`, d, ref: DBC, gold: domestic3h })),
  ...["2016-06-01", "2017-06-01", "2018-06-01", "2019-06-01", "2020-06-01", "2021-06-01", "2022-06-01", "2023-06-01", "2024-06-01", "2025-06-01", "2026-06-01"].map((d) => ({ id: `sw-uk-${d}`, q: `I am 30 and worked in the UK on ${d}. What was the national living wage per hour?`, d, ref: NLW, gold: /national living wage|aged 2[1-5]/i })),
  ...["2006-06-01", "2012-06-01", "2018-06-01", "2024-06-01"].map((d) => ({ id: `sw-eu-${d}`, q: `My EU flight of 1,200 km was cancelled on ${d} without notice. How much EU261 compensation?`, d, ref: EU261, gold: /1500 kilometres or less/ })),
];

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const sameRef = (a, b) => a && b && a.source === b.source && (a.source === "ecfr" ? String(a.title) === String(b.title) && String(a.part) === String(b.part) && a.section === b.section : a.source === "ukleg" ? a.path === b.path : a.celex === b.celex);
async function goldAmount(ref, date, pattern) {
  try {
    const law = await lawOn(ref, date);
    const cs = amountClauses(law.text);
    const c = cs.find((x) => pattern.test(x));
    const own = c ? c.split(" … ").at(-1) : (law.text.match(new RegExp(`[^.;]*${pattern.source}[^.;]*`, "i"))?.[0] ?? "");
    if (/No compensation is required/.test(own)) return "No compensation is required";
    const qs = extractQuantities(own);
    return (qs.find((q) => q.kind === "money") ?? qs.find((q) => q.kind === "percent") ?? qs[0])?.text ?? null;
  } catch (e) {
    return `ERR:${e.message.slice(0, 40)}`;
  }
}

const SETS = { core: S, heldout: HELDOUT, sweep: SWEEP };
const scenarios = SETS[set].filter((x) => !only || only.includes(x.id));
const { buildArtifact, generateDeviceKey, verifyArtifact } = withWarrant ? await import("../src/warrant/artifact.ts") : {};
const { asTwoLane } = await import("../src/timetravel/timetravel.ts");
const { officialFetch } = await import("../src/warrant/pointInTime.ts");
const deviceKey = withWarrant ? await generateDeviceKey() : null;
async function warrantChecks(r) {
  const mandate = { subject: "sim", recipient: "claims.example", purpose: "one claim", notBefore: new Date(Date.now() - 6e4).toISOString(), expiresAt: new Date(Date.now() + 864e5).toISOString(), jti: `sim-${Math.random()}` };
  const policy = { recipient: "claims.example", revoked: new Set(), fetch: officialFetch(fetch) };
  const honest = await verifyArtifact(await buildArtifact(asTwoLane(r), mandate, deviceKey), policy);
  // A sender who signs a bigger amount than the pinned text says: digits changed in the claimed quote and quantity.
  const q = r.then.amount;
  let forged = { decision: "n/a" };
  if (q && q.value > 0) {
    const bigger = q.text.replace(/\d[\d,.]*/, (n) => String(Number(n.replace(/,/g, "")) * 2));
    const lie = { ...r, then: { ...r.then, amount: { ...q, value: q.value * 2, text: bigger } }, evidence: { ...r.evidence, quote: r.evidence.quote.replace(q.text, bigger) } };
    forged = await verifyArtifact(await buildArtifact(asTwoLane(lie), { ...mandate, jti: mandate.jti + "f" }, deviceKey), policy);
  }
  // A date-blind receiver fetches today's text instead of the pinned version.
  let blind = { decision: "n/a" };
  if (r.changed && r.now.url) {
    const live = await officialFetch(fetch)(r.now.url);
    blind = await verifyArtifact(await buildArtifact(asTwoLane(r), { ...mandate, jti: mandate.jti + "b" }, deviceKey), { ...policy, fetch: async () => live });
  }
  return { honest: honest.decision, forged: forged.decision, blind: blind.decision, honestWhy: honest.decision === "ACCEPT" ? undefined : honest.reasons.join("; ").slice(0, 120) };
}

const rows = [];
for (let rep = 0; rep < repeat; rep++)
for (const s of scenarios) {
  const today = new Date().toISOString().slice(0, 10);
  const t0 = Date.now();
  let r, err;
  try { r = await thenNowNext({ question: s.q, eventDate: s.d }, { judge: mainJudge, second, panel, catalogSearch }); } catch (e) { err = e.message; }
  const ms = Date.now() - t0;
  const goldThen = s.expect ? null : await goldAmount(s.ref, s.d, s.gold);
  const goldNow = await goldAmount(s.nowRef ?? s.ref, r?.now.date ?? today, s.nowGold ?? s.gold);
  const row = {
    id: s.id, expect: s.expect ?? "answer",
    provisionOk: r ? sameRef(r.provision.ref, s.ref) : false, via: r?.provision.via,
    then: r?.then.amount?.text ?? null, goldThen, thenOk: !s.expect && !!r && !!goldThen && r.then.amount?.text === goldThen,
    now: r?.now.amount?.text ?? null, goldNow, nowOk: !!r && !!goldNow && r.now.amount?.text === goldNow,
    p: r?.then.p, ruledOut: r?.ruledOut, agreed: r?.agreement?.agreed, votes: r?.agreement?.votes?.map((v) => `${v.judge}:${v.mode}`), future: r?.future, ms, err,
    rep,
    warrant: withWarrant && r && !err && r.then.amount?.value !== 0 ? await warrantChecks(r).catch((e) => ({ error: e.message })) : undefined,
    expectOk: s.expect === "future" ? !!r?.future : s.expect === "no-provision" ? !!err && /not in force/.test(err) : !err,
  };
  rows.push(row);
  console.log(`${repeat > 1 ? `#${rep} ` : ""}${row.id.padEnd(22)} ${row.provisionOk ? "prov✓" : "prov✗"} ${(r?.provision.via ?? "-").padEnd(11)} then ${String(row.then).padEnd(9)} gold ${String(row.goldThen).padEnd(9)} ${row.thenOk ? "✓" : s.expect ? "·" : "✗"} | now ${String(row.now).padEnd(9)} gold ${String(row.goldNow).padEnd(9)} ${row.nowOk ? "✓" : "✗"} | ${s.expect ? (row.expectOk ? "edge✓ " : "edge✗ ") : ""}${ms} ms${row.agreed === undefined ? "" : row.agreed ? " | agreed" : " | SPLIT"}${row.warrant ? ` | W ${row.warrant.honest}/${row.warrant.forged}/${row.warrant.blind}` : ""}${err ? ` | ERROR ${err.slice(0, 70)}` : ""}`);
}
const answered = rows.filter((r) => r.expect === "answer");
const byId = Object.groupBy(rows, (r) => r.id);
const W = rows.filter((r) => r.warrant && !r.warrant.error);
const summary = {
  set, repeat, judge: localUrl ? "local-decisions (provision: jev)" : "jev", secondJudge: second ? "gpt-6-luna" : null,
  panel: ["jev", ...(second ? ["gpt-6-luna"] : []), ...panel.map((p) => p.id)],
  // Counted over the same rows as rightWhenAgreed: scenarios that expect an answer (edge cases are reported under `edges`).
  agreed: `${answered.filter((r) => r.agreed).length}/${answered.filter((r) => r.agreed !== undefined).length}`,
  rightWhenAgreed: `${answered.filter((r) => r.agreed && r.thenOk).length}/${answered.filter((r) => r.agreed).length}`,
  rightWhenNotAgreed: `${answered.filter((r) => r.agreed === false && r.thenOk).length}/${answered.filter((r) => r.agreed === false).length}`,
  scenarios: rows.length,
  ...(repeat > 1 ? { stableIds: `${Object.values(byId).filter((rs) => new Set(rs.map((r) => `${r.then}|${r.now}`)).size === 1).length}/${Object.keys(byId).length}` } : {}),
  ...(withWarrant ? { warrant: { honestAccepted: `${W.filter((r) => r.warrant.honest === "ACCEPT").length}/${W.length}`, forgedRejected: `${W.filter((r) => r.warrant.forged === "REJECT").length}/${W.filter((r) => r.warrant.forged !== "n/a").length}`, dateBlindRejected: `${W.filter((r) => r.warrant.blind === "REJECT").length}/${W.filter((r) => r.warrant.blind !== "n/a").length}`, notAccepted: W.filter((r) => r.warrant.honest !== "ACCEPT").map((r) => `${r.id}: ${r.warrant.honestWhy}`) } } : {}),
  provision: `${rows.filter((r) => r.provisionOk).length}/${rows.length}`,
  then: `${answered.filter((r) => r.thenOk).length}/${answered.length}`,
  now: `${rows.filter((r) => r.nowOk).length}/${rows.length}`,
  edges: `${rows.filter((r) => r.expect !== "answer" && r.expectOk).length}/${rows.filter((r) => r.expect !== "answer").length}`,
  errors: rows.filter((r) => r.err).map((r) => `${r.id}: ${r.err.slice(0, 60)}`),
  medianMs: rows.map((r) => r.ms).sort((a, b) => a - b)[Math.floor(rows.length / 2)],
};
console.log("\n" + JSON.stringify(summary, null, 1));
mkdirSync(new URL("results/", here), { recursive: true });
writeFileSync(new URL(`results/thennow-sim-${set}-${new Date().toISOString().replace(/[:.]/g, "-")}.json`, here), JSON.stringify({ summary, rows }, null, 1));
