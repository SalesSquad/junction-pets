import assert from "node:assert/strict";
import { test } from "node:test";
import { amendmentsAfter, amountClauses, asTwoLane, codeFits, factsOf, findProvision, fitOf, refFromUrl, thenNowNext, wantOf } from "../src/timetravel/timetravel.ts";
import { officialFetch } from "../src/warrant/pointInTime.ts";
import { buildArtifact, generateDeviceKey, verifyArtifact } from "../src/warrant/artifact.ts";
import type { DecisionProvider } from "../src/decide/decide.ts";

test("official URLs become references", () => {
  assert.deepEqual(refFromUrl("https://www.ecfr.gov/current/title-14/chapter-II/subchapter-A/part-250/section-250.5"), { source: "ecfr", title: 14, part: "250", section: "250.5" });
  assert.deepEqual(refFromUrl("https://www.legislation.gov.uk/uksi/2015/621/regulation/4/made"), { source: "ukleg", path: "uksi/2015/621/regulation/4" });
  assert.deepEqual(refFromUrl("https://www.legislation.gov.uk/ukpga/1996/18/section/227"), { source: "ukleg", path: "ukpga/1996/18/section/227" });
  assert.deepEqual(refFromUrl("https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32004R0261"), { source: "eurlex", celex: "32004R0261" });
  assert.equal(refFromUrl("https://www.example.com/law"), null);
});

const ecfrText = (cap2: string, cap3: string) =>
  `§ 250.5 Amount of denied boarding compensation. (a) A carrier shall pay compensation in interstate air transportation to passengers who are denied boarding involuntarily as follows: (1) No compensation is required if the carrier offers alternate transportation planned to arrive not later than one hour after the planned arrival; (2) Compensation shall be at least 200 percent of the fare, or ${cap2}, whichever is lower, if the alternate transportation arrives more than one hour but less than two hours after the planned arrival; and (3) Compensation shall be at least 400 percent of the fare, or ${cap3}, whichever is lower, if the alternate transportation arrives more than two hours after the planned arrival.`;

test("amount-bearing clauses keep their paragraph context", () => {
  const cs = amountClauses(ecfrText("$775", "$1,550"));
  // The zero tier ("(1) No compensation is required if …") is an answer too.
  assert.equal(cs.length, 3);
  assert.ok(cs[0]!.endsWith("(1) No compensation is required if the carrier offers alternate transportation planned to arrive not later than one hour after the planned arrival"));
  assert.ok(cs[2]!.startsWith("(a) A carrier shall pay compensation in interstate air transportation"));
  assert.ok(cs[2]!.endsWith("more than two hours after the planned arrival."));
});

test("outline: compound enumerators, residual tiers and stated facts rule clauses out by code", () => {
  const text = "§ 579.1 Purpose. (a) Penalties as follows: (1)(i) Any person who violates the child labor provisions shall be subject to a civil penalty not to exceed: (A) $14,050 for each employee; or (B) $63,855 for a death. (ii) Other: (A) $1,000.";
  const cs = amountClauses(text);
  assert.equal(cs.length, 3);
  assert.ok(/\(1\) … \(i\) Any person who violates the child labor provisions[^…]* … \(A\) \$14,050 for each employee$/.test(cs[0]!), cs[0]!);
  const eu = "Article 7 Right to compensation 1. Passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres; (c) EUR 600 for all flights not falling under (a) or (b).";
  const ec = amountClauses(eu);
  assert.equal(ec.length, 3);
  assert.deepEqual(ec.map((c) => fitOf(c, factsOf("a flight of about 1.100 km"))), ["all", "fail", "free"]);
  assert.deepEqual(ec.map((c) => fitOf(c, factsOf("a flight of 2,000 km"))), ["fail", "all", "free"]);
  assert.deepEqual(ec.map((c) => fitOf(c, factsOf("an extra-EU flight of 5,800 km"))), ["fail", "fit", "free"]);
  // "does not offer alternate transportation … less than two hours" holds when it is two hours or more.
  const neg = "(a) A carrier shall pay: (1) $1,075 if the carrier offers alternate transportation planned to arrive more than one hour but less than two hours after; and (2) $2,150 if the carrier does not offer alternate transportation planned to arrive less than two hours after.";
  assert.deepEqual(amountClauses(neg).map((c) => fitOf(c, factsOf("arrived 3 hours late"))), ["fail", "all"]);
  assert.deepEqual(amountClauses(neg).map((c) => fitOf(c, factsOf("arrived 90 minutes late"))), ["all", "fail"]);
  assert.equal(wantOf("How long does the company have to respond?"), "duration");
  assert.equal(factsOf("I was 19 years old").age, 19);
});

test("UK effects feed: only effects on the provision, with in-force dates and upcoming flag", async () => {
  const effect = (prov: string, title: string, num: string, date: string) =>
    `<ukm:Effect AffectingURI="http://www.legislation.gov.uk/id/uksi/2026/${num}" AffectedProvisions="${prov}" Type="sum substituted"><ukm:AffectingTitle>${title}</ukm:AffectingTitle><ukm:InForceDates><ukm:InForce Date="${date}"/></ukm:InForceDates></ukm:Effect>`;
  const feed = `<feed>${effect("reg. 4", "The NMW (Amendment) Regulations 2027", "900", "2027-04-01")}${effect("reg. 4A(1)", "Other rates", "901", "2026-04-01")}${effect("reg. 4", "The NMW (Amendment) Regulations 2026", "357", "2026-04-01")}</feed>`;
  const f = async () => new Response(feed);
  const cs = await amendmentsAfter({ source: "ukleg", path: "uksi/2015/621/regulation/4" }, "2023-06-15", "2026-11-14", f as never);
  assert.deepEqual(cs.map((c) => [c.effective, c.upcoming, c.url]), [["2027-04-01", true, "https://www.legislation.gov.uk/uksi/2026/900"], ["2026-04-01", false, "https://www.legislation.gov.uk/uksi/2026/357"]]);
});

test("a strong registry match needs no network", async () => {
  const r = await findProvision("I was bumped from an oversold US domestic flight", { fetch: (async () => { throw new Error("offline"); }) as never });
  assert.equal(r.via, "registry");
  assert.deepEqual(r.ref, { source: "ecfr", title: 14, part: 250, section: "250.5" });
});

// Fake official endpoints: two versions of 14 CFR 250.5, one amending rule, and the eCFR title index.
const fakeFetch = async (url: string) => {
  if (url.includes("titles.json")) return new Response(JSON.stringify({ titles: [{ number: 14, latest_issue_date: "2026-11-10" }] }));
  if (url.includes("/full/2021-06-10/")) return new Response(`<SECTION>${ecfrText("$775", "$1,550")}</SECTION>`);
  if (url.includes("/full/2026-11-10/")) return new Response(`<SECTION>${ecfrText("$1,075", "$2,150")}</SECTION>`);
  if (url.includes("federalregister.gov")) return new Response(JSON.stringify({ results: [{ title: "Periodic Revisions to Denied Boarding Compensation", effective_on: "2025-01-22", html_url: "https://www.federalregister.gov/d/2024-23588" }, { title: "Future revision", effective_on: "2027-01-22", html_url: "https://www.federalregister.gov/d/2026-1" }] }));
  return new Response("not found", { status: 404 });
};
const judge: DecisionProvider = {
  id: "fake",
  decide: async (state: any, qs) => ({ provider: "fake", model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q) => ({ name: q.name, kind: q.kind, p: /more than two hours/.test(state.clause) ? 0.9 : 0.1 })) }),
};

test("Then · Now · Next: the cap on the event date, today, and the rules in between", async () => {
  const r = await thenNowNext({ question: "Bumped from an oversold US domestic flight on 2021-06-10, 3 hours late", eventDate: "2021-06-10", today: "2026-11-14" }, { judge, fetch: fakeFetch as never });
  assert.equal(r.then.amount?.text, "$1,550");
  assert.equal(r.now.amount?.text, "$2,150");
  assert.equal(r.changed, true);
  assert.deepEqual(r.changes.map((c) => c.effective), ["2025-01-22"]);
  assert.deepEqual(r.upcoming.map((c) => c.effective), ["2027-01-22"]);
  assert.equal(r.evidence.url, "https://www.ecfr.gov/api/versioner/v1/full/2021-06-10/title-14.xml?part=250&section=250.5");
  assert.ok(r.receipts.every((x) => x.purpose === "then-now-clause"));
});

test("the warrant pins the official version; the receiver re-checks it, and a tampered quote fails", async () => {
  const r = await thenNowNext({ question: "Bumped from an oversold US domestic flight on 2021-06-10, 3 hours late", eventDate: "2021-06-10", today: "2026-11-14" }, { judge, fetch: fakeFetch as never });
  const key = await generateDeviceKey();
  const mandate = { subject: "p", recipient: "claims.airline.example", purpose: "one denied-boarding claim", notBefore: new Date(Date.now() - 6e4).toISOString(), expiresAt: new Date(Date.now() + 864e5).toISOString(), jti: "m-tt" };
  const a = await buildArtifact(asTwoLane(r), mandate, key);
  const policy = { recipient: "claims.airline.example", revoked: new Set<string>(), fetch: officialFetch(fakeFetch as never) };
  const ok = await verifyArtifact(a, policy);
  assert.equal(ok.decision, "ACCEPT", ok.reasons.join("; "));
  assert.ok(ok.checked.includes("outcome $1,550"));
  // The receiver would see today's amount if it fetched the live page instead of the pinned version.
  const live = await verifyArtifact(a, { ...policy, fetch: async () => ecfrText("$1,075", "$2,150") });
  assert.equal(live.decision, "REJECT");
});

test("date substitution: a genuine official text of a later date does not prove the law on the event date", async () => {
  const r = await thenNowNext({ question: "Bumped from an oversold US domestic flight on 2021-06-10, 3 hours late", eventDate: "2021-06-10", today: "2026-11-14" }, { judge, fetch: fakeFetch as never });
  const key = await generateDeviceKey();
  const mandate = { subject: "p", recipient: "claims.airline.example", purpose: "one denied-boarding claim", notBefore: new Date(Date.now() - 6e4).toISOString(), expiresAt: new Date(Date.now() + 864e5).toISOString(), jti: "m-swap" };
  const policy = { recipient: "claims.airline.example", revoked: new Set<string>(), fetch: officialFetch(fakeFetch as never) };
  // The attacker keeps the 2021 event but pins the 2026 version, where the quote really says $2,150.
  const swapped = { ...r, then: { ...r.then, amount: r.now.amount, url: r.now.url }, evidence: { url: r.now.url, quote: r.evidence.quote.replace("$1,550", "$2,150"), asOf: r.eventDate } };
  const v = await verifyArtifact(await buildArtifact(asTwoLane(swapped), mandate, key), policy);
  assert.equal(v.decision, "REJECT");
  assert.ok(v.reasons.some((x) => /dated 2026-11-10, but the claim relies on the law as of 2021-06-10/.test(x)), v.reasons.join("; "));
  // Dropping the signed date does not help: the claim text still names it, and the signature covers both.
  const a = await buildArtifact({ ...asTwoLane(swapped), lawAsOf: undefined }, { ...mandate, jti: "m-swap-2" }, key);
  assert.equal((await verifyArtifact(a, policy)).decision, "REJECT");
});

test("red team: code facts are conservative (compound durations, miles, birth years, conflicting values)", () => {
  const neg = "(a) A carrier shall pay: (1) $1,075 if the carrier offers alternate transportation planned to arrive more than one hour but less than two hours after; and (2) $2,150 if the carrier does not offer alternate transportation planned to arrive less than two hours after.";
  const eu = "Article 7 1. Passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres; (c) EUR 600 for all flights not falling under (a) or (b).";
  const nmw = "4A 1 The hourly rate of the national minimum wage is— a £9.18 for a worker who is aged 21 years or over (but is not yet aged 23 years ); b £6.83 for a worker who is aged 18 years or over (but is not yet aged 21 years); c £4.81 for a worker who is aged under 18 years";
  const fits = (text: string, q: string) => codeFits(q, amountClauses(text));
  assert.deepEqual(fits(neg, "the substitute arrived 1 hour and 45 minutes late"), ["all", "fail"]);
  assert.deepEqual(fits(neg, "it arrived two and a half hours late"), ["fail", "all"]);
  assert.deepEqual(fits(eu, "my intra-EU flight of 1,100 miles was cancelled"), ["fail", "all", "fail"]);
  // A distractor distance must not let code rule out the residual tier (a long extra-EU flight would lose its answer).
  assert.deepEqual(fits(eu, "I drove 30 km to the airport; my flight of 4,200 km to New York was cancelled"), ["free", "free", "free"]);
  assert.deepEqual(fits(nmw, "I was born in 2003 and worked in the UK on 2022-07-01"), ["fail", "all", "fail"]);
  assert.deepEqual(fits(nmw, "I was born in 2004 and worked in the UK on 2022-07-01"), ["fail", "free", "free"]);
});

test("red team: a widened quote cannot carry a sibling tier's amount", async () => {
  const r = await thenNowNext({ question: "Bumped from an oversold US domestic flight on 2021-06-10, 3 hours late", eventDate: "2021-06-10", today: "2026-11-14" }, { judge, fetch: fakeFetch as never });
  const text = ecfrText("$775", "$1,550");
  const quote = text.slice(text.indexOf("(2) Compensation"));
  const focus = text.slice(text.indexOf("(3) Compensation"));
  const key = await generateDeviceKey();
  const mandate = { subject: "p", recipient: "claims.airline.example", purpose: "one claim", notBefore: new Date(Date.now() - 6e4).toISOString(), expiresAt: new Date(Date.now() + 864e5).toISOString(), jti: "m-sib" };
  const policy = { recipient: "claims.airline.example", revoked: new Set<string>(), fetch: officialFetch(fakeFetch as never) };
  const claim = (amount: string, value: number) => ({ ...r, then: { ...r.then, amount: { kind: "money" as const, value, unit: "USD", text: amount } }, evidence: { ...r.evidence, quote, focus } });
  assert.equal((await verifyArtifact(await buildArtifact(asTwoLane(claim("$1,550", 1550)), mandate, key), policy)).decision, "ACCEPT");
  const lie = await verifyArtifact(await buildArtifact(asTwoLane(claim("$775", 775)), { ...mandate, jti: "m-sib-2" }, key), policy);
  assert.equal(lie.decision, "REJECT", lie.reasons.join("; "));
});

test("red team: an EU act is not the law before the year it was adopted", async () => {
  const { eurlexUrlOn } = await import("../src/warrant/pointInTime.ts");
  await assert.rejects(eurlexUrlOn("32007R1371", "2004-01-15", (async () => { throw new Error("offline"); }) as never), /404 not in force/);
  assert.equal(await eurlexUrlOn("32007R1371", "2015-06-01", (async () => { throw new Error("offline"); }) as never), "http://publications.europa.eu/resource/celex/32007R1371");
});

test("red team: ages are ages (\"under 18 years old\" is a bound; \"aged 21 years\" is not a duration)", () => {
  const nmw = "4A 1 The hourly rate of the national minimum wage is— a £6.95 for a worker who is aged 21 years or over (but is not yet aged 25 years); b £5.55 for a worker who is aged 18 years or over (but is not yet aged 21 years); c £4.00 for a worker who is aged under 18 years";
  const fits = (q: string) => codeFits(q, amountClauses(nmw));
  assert.deepEqual(fits("I was under 18 years old at the time"), ["fail", "fail", "all"]);
  assert.deepEqual(fits("i was 22 and had been there over a year"), ["all", "fail", "fail"]);
  assert.deepEqual(fits("I was over 21"), ["free", "fail", "fail"]);
});

test("red team: a negated age bound is not an age (\"I was 22 … I wasn't under 18\")", () => {
  const nmw = "4A 1 The hourly rate of the national minimum wage is— a £6.95 for a worker who is aged 21 years or over (but is not yet aged 25 years); b £5.55 for a worker who is aged 18 years or over (but is not yet aged 21 years); c £4.00 for a worker who is aged under 18 years";
  assert.deepEqual(codeFits("I was 22 years old at the time. I wasn't an apprentice and I wasn't under 18.", amountClauses(nmw)), ["all", "fail", "fail"]);
  assert.deepEqual(codeFits("i wasnt an apprntice, and def not under 18", amountClauses(nmw)).every((f) => f === "free"), true);
  // A repealed list item is dropped instead of merging into the next one.
  const cs = amountClauses("4A 1 The hourly rate is— a . . . . . . . . b £10.00 for a worker who is aged 18 years or over (but is not yet aged 21 years); c £7.55 for a worker who is aged under 18 years");
  assert.ok(cs[0]!.endsWith("b £10.00 for a worker who is aged 18 years or over (but is not yet aged 21 years)"), cs[0]!);
});

test("panel: judges answer one choice question over the live tiers; signing needs agreement", async () => {
  const { chooseClause } = await import("../src/timetravel/timetravel.ts");
  const clauses = amountClauses(ecfrText("$775", "$1,550"));
  // A judge with choice support: probabilities per letter; `favour` matches the clause it prefers.
  const choiceJudge = (id: string, favour: RegExp): DecisionProvider => ({
    id,
    decide: async (state: any, qs) => ({ provider: id, model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q: any) => {
      if (q.kind === "yesno") return { name: q.name, kind: "yesno", p: favour.test(state.clause) ? 0.9 : 0.1 };
      const labels = Object.keys(q.options);
      const probabilities = Object.fromEntries(labels.map((l) => [l, favour.test(q.options[l]) ? 0.8 : 0.2 / Math.max(1, labels.length - 1)]));
      return { name: q.name, kind: "choice", choice: labels.find((l) => favour.test(q.options[l])), probabilities };
    }) }),
  });
  const three = [choiceJudge("a", /more than two hours/), choiceJudge("b", /more than two hours/), choiceJudge("c", /more than two hours/)];
  // No figure in the message: all three tiers are live and each judge gets one choice question.
  const ok = await chooseClause("Bumped from an oversold US domestic flight and rerouted, I got there much later", clauses, three);
  assert.ok(clauses[ok.index]!.endsWith("more than two hours after the planned arrival."));
  assert.equal(ok.agreed, true);
  assert.equal(ok.ruledOut, 0);
  assert.deepEqual(ok.votes.map((v) => v.mode), ["choice", "choice", "choice"]);
  // One dissenting judge: the mean still picks the clause, but it is not signed without asking.
  const split = await chooseClause("Bumped from an oversold US domestic flight and rerouted, I got there much later", clauses, [three[0]!, three[1]!, choiceJudge("d", /No compensation/)]);
  assert.ok(clauses[split.index]!.endsWith("more than two hours after the planned arrival."));
  assert.equal(split.agreed, false);
  // "3 hours late": code leaves one tier. A judge with choice support still reads all three tiers and votes;
  // a judge without it is asked yes/no about the surviving tier.
  const one = await chooseClause("Bumped from an oversold US domestic flight, 3 hours late", clauses, [three[0]!, judge]);
  assert.equal(one.ruledOut, 2);
  assert.deepEqual(one.votes.map((v) => v.mode), ["choice", "yesno"]);
  assert.equal(one.agreed, true);
  // A judge that prefers a tier code ruled out cannot change the pick, but the choice is then not "agreed".
  const against = await chooseClause("Bumped from an oversold US domestic flight, 3 hours late", clauses, [three[0]!, choiceJudge("e", /No compensation/)]);
  assert.ok(clauses[against.index]!.endsWith("more than two hours after the planned arrival."));
  assert.notEqual(against.votes[1]!.index, against.index);
  assert.equal(against.agreed, false);
  // A judge without choice support is asked one yes/no per clause.
  const mixed = await chooseClause("Bumped from an oversold US domestic flight and rerouted, I got there much later", clauses, [judge, three[0]!]);
  assert.deepEqual(mixed.votes.map((v) => v.mode), ["yesno", "choice"]);
  assert.equal(mixed.agreed, true);
  // A judge whose endpoint is down abstains: the others still choose, but the choice is not "agreed".
  const down: DecisionProvider = { id: "down", decide: async () => { throw new Error("timeout"); } };
  const partial = await chooseClause("Bumped from an oversold US domestic flight and rerouted, I got there much later", clauses, [three[0]!, three[1]!, down]);
  assert.ok(clauses[partial.index]!.endsWith("more than two hours after the planned arrival."));
  assert.deepEqual(partial.abstained, ["down"]);
  assert.equal(partial.votes.length, 2);
  assert.equal(partial.agreed, false);
  // No judge answers and code left one tier: that tier stands on code alone, for the person to review.
  const codeOnly = await chooseClause("Bumped from an oversold US domestic flight, 3 hours late", clauses, [down]);
  assert.ok(clauses[codeOnly.index]!.endsWith("more than two hours after the planned arrival."));
  assert.equal(codeOnly.agreed, false);
  assert.deepEqual(codeOnly.abstained, ["down"]);
  // No judge answers and several tiers are live: the failure reaches the caller.
  await assert.rejects(chooseClause("Bumped from an oversold US domestic flight and rerouted, I got there much later", clauses, [down]), /timeout/);
  // An advisor's vote is reported but changes neither the pick nor the agreement; a failing advisor is ignored.
  const advised = await chooseClause("Bumped from an oversold US domestic flight and rerouted, I got there much later", clauses, three, undefined, [choiceJudge("on-device", /No compensation/), down]);
  assert.equal(advised.agreed, true);
  assert.ok(clauses[advised.index]!.endsWith("more than two hours after the planned arrival."));
  assert.deepEqual(advised.advisory.map((v) => v.judge), ["on-device"]);
  assert.notEqual(advised.advisory[0]!.index, advised.index);
});

test("private mode: the provision is matched on the device only; the question reaches no search or judge", async () => {
  const { findProvision } = await import("../src/timetravel/timetravel.ts");
  let calls = 0;
  const spyFetch = (async () => { calls++; throw new Error("network must not be used"); }) as unknown as typeof fetch;
  const spySearch = async () => { calls++; return []; };
  const found = await findProvision("My EU flight of 1,200 km was cancelled without notice. How much compensation under EU261?", { offline: true, fetch: spyFetch, exaSearch: spySearch, judge: { id: "spy", decide: async () => { calls++; throw new Error("judge must not be asked"); } } });
  assert.equal(found.via, "registry");
  assert.match(found.title, /261\/2004/);
  await assert.rejects(findProvision("What is the weather in Helsinki tomorrow?", { offline: true, fetch: spyFetch, exaSearch: spySearch }), /on this device/);
  // Short keywords match whole words only: the Finnish "ilmoitusta" does not contain the country "us".
  const fi = await findProvision("Lentoni Helsingistä Roomaan peruttiin ilman ilmoitusta. Paljonko EU-korvaus on?", { offline: true, fetch: spyFetch });
  assert.match(fi.title, /261\/2004/);
  assert.equal(calls, 0);
});

test("panel: a tie, a refusal, an empty log-probability answer or a lone judge never count as agreement", async () => {
  const { chooseClause } = await import("../src/timetravel/timetravel.ts");
  const { logprobDecisions } = await import("../src/decide/decide.ts");
  const clauses = amountClauses(ecfrText("$775", "$1,550"));
  const situation = "Bumped from an oversold US domestic flight and rerouted, I got there much later";
  const fixed = (id: string, ps: number[]): DecisionProvider => ({
    id,
    decide: async (_s, qs) => ({ provider: id, model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q: any) => { const labels: string[] = Object.keys(q.options); return { name: q.name, kind: "choice" as const, choice: labels[ps.indexOf(Math.max(...ps))]!, probabilities: Object.fromEntries(labels.map((l, i) => [l, ps[i] ?? 0])) }; }) }),
  });
  // Two judges prefer the second tier; the third has an exact tie between the second and third.
  const tie = await chooseClause(situation, clauses, [fixed("a", [0.1, 0.6, 0.3]), fixed("b", [0.1, 0.6, 0.3]), fixed("c", [0.04, 0.48, 0.48])]);
  assert.equal(tie.index, 1);
  assert.equal(tie.votes[2]!.tied, true);
  assert.equal(tie.agreed, false);
  // A judge that refuses the choice question and then every yes/no question abstains.
  const refuser: DecisionProvider = { id: "refuser", decide: async (_s, qs) => ({ provider: "refuser", model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q: any) => ({ name: q.name, kind: q.kind, refused: true })) }) };
  const refused = await chooseClause(situation, clauses, [fixed("a", [0.1, 0.6, 0.3]), fixed("b", [0.1, 0.6, 0.3]), refuser]);
  assert.deepEqual(refused.abstained, ["refuser"]);
  assert.equal(refused.agreed, false);
  // An endpoint that returns no log-probabilities gives no answer (not a uniform "A").
  const empty = logprobDecisions({ id: "empty", baseUrl: "http://x", apiKey: "k", model: "m", fetch: (async () => new Response(JSON.stringify({ choices: [{ logprobs: null }] }), { status: 200 })) as any });
  await assert.rejects(empty.decide({ situation }, [{ kind: "choice", name: "tier", instructions: "?", options: { A: "x", B: "y" } }]), /no option letter/);
  const withEmpty = await chooseClause(situation, clauses, [fixed("a", [0.1, 0.6, 0.3]), fixed("b", [0.1, 0.6, 0.3]), empty]);
  assert.deepEqual(withEmpty.abstained, ["empty"]);
  assert.equal(withEmpty.agreed, false);
  // Letter variants count: "B)" carries the answer.
  const variant = logprobDecisions({ id: "v", baseUrl: "http://x", apiKey: "k", model: "m", fetch: (async () => new Response(JSON.stringify({ choices: [{ logprobs: { content: [{ top_logprobs: [{ token: " B)", logprob: Math.log(0.9) }, { token: "A", logprob: Math.log(0.1) }] }] } }] }), { status: 200 })) as any });
  assert.equal((await variant.decide({ situation }, [{ kind: "choice", name: "tier", instructions: "?", options: { A: "x", B: "y" } }])).answers[0]!.choice, "B");
  // One judge alone is not agreement.
  assert.equal((await chooseClause(situation, clauses, [fixed("a", [0.1, 0.6, 0.3])])).agreed, false);
  // The stated facts contradict every tier: a pick is returned, never as agreed, and all tiers count as ruled out.
  const two = ["(1) $100 if the delay was more than 2 hours but less than 4 hours", "(2) $200 if the delay was more than 4 hours but less than 6 hours"];
  const { codeFits } = await import("../src/timetravel/timetravel.ts");
  const sit = "My delay was 30 minutes";
  if (codeFits(sit, two).every((f) => f === "fail")) {
    const none = await chooseClause(sit, two, [fixed("a", [0.7, 0.3]), fixed("b", [0.7, 0.3])]);
    assert.equal(none.agreed, false);
    assert.equal(none.ruledOut, 2);
  }
});

test("the on-device catalog: a candidate for the judge, and the fallback search in private mode", async () => {
  const { findProvision } = await import("../src/timetravel/timetravel.ts");
  const catalog = async () => [{ ref: { source: "ecfr" as const, title: 29, part: "570", section: "570.140" }, title: "29 CFR 570.140 — General.", about: "civil money penalties for child labor violations", score: 0.56 }];
  // Private mode, no keyword match: the catalog's first hit, found without any network call or judge.
  let calls = 0;
  const spyFetch = (async () => { calls++; throw new Error("network must not be used"); }) as unknown as typeof fetch;
  const found = await findProvision("Työnantajani antoi 15-vuotiaan käyttää lihaleikkuria. Mikä on seuraamusmaksu?", { offline: true, catalogSearch: catalog, fetch: spyFetch });
  assert.equal(found.via, "catalog");
  assert.deepEqual(found.ref, { source: "ecfr", title: 29, part: "570", section: "570.140" });
  assert.equal(calls, 0);
  // A clear keyword match in the registry comes before the CFR catalog in private mode.
  const eu = await findProvision("My EU flight was cancelled, how much under EU261?", { offline: true, catalogSearch: catalog, fetch: spyFetch });
  assert.equal(eu.via, "registry");
  // A built-in right matched by meaning wins without any keyword (a Finnish paraphrase), unless the CFR hit is clearly ahead.
  const semantic = (regScore: number, cfrScore: number) => async () => [
    { kind: "registry" as const, ref: { source: "eurlex" as const, celex: "32004R0261", article: "7" }, title: "Regulation (EC) No 261/2004, Art. 7 — flight compensation (EU)", about: "Fixed compensation an airline owes passengers", score: regScore },
    { kind: "cfr" as const, ref: { source: "ecfr" as const, title: 14, part: "250", section: "250.5" }, title: "14 CFR 250.5 — Amount of denied boarding compensation", about: "", score: cfrScore },
  ];
  const fi = "Koneeni lähtö Helsingistä Roomaan mitätöitiin viime hetkellä. Mihin hyvitykseen minulla on oikeus?";
  assert.match((await findProvision(fi, { offline: true, catalogSearch: semantic(0.52, 0.41), fetch: spyFetch })).title, /261\/2004/);
  assert.equal((await findProvision(fi, { offline: true, catalogSearch: semantic(0.38, 0.55), fetch: spyFetch })).via, "catalog");
  // Nothing close enough on the device: an error, not a guess.
  await assert.rejects(findProvision("Millainen sää Helsingissä on huomenna?", { offline: true, catalogSearch: semantic(0.21, 0.24), fetch: spyFetch }), /on this device/);
  // A weak match on both sides (an unusual paraphrase): still an error, never an answer from an unrelated provision.
  await assert.rejects(findProvision("Koneeni lähtö mitätöitiin viime hetkellä, mihin hyvitykseen minulla on oikeus?", { offline: true, catalogSearch: semantic(0.32, 0.37), fetch: spyFetch }), /on this device/);
  // With a judge, the catalog's candidates are judged next to the registry's; here the judge prefers the catalog's.
  const prefers: DecisionProvider = { id: "j", decide: async (state: any, qs) => ({ provider: "j", model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q) => ({ name: q.name, kind: "yesno" as const, p: /570\.140/.test(String(state.provision)) ? 0.95 : 0.05 })) }) };
  const judged = await findProvision("A teenager was told to operate a meat slicer at work; what penalty applies?", { catalogSearch: catalog, judge: prefers, fetch: spyFetch });
  assert.equal(judged.via, "catalog");
});

test("a special-status tier needs the status to be stated: no apprenticeship in the message, no apprentice rate", async () => {
  const { codeFits } = await import("../src/timetravel/timetravel.ts");
  const clauses = [
    "4 The single hourly rate of the national minimum wage for the purposes of section 1(3) of the Act (“the national living wage rate”) is £12.71 .",
    "4A 1 The hourly rate of the national minimum wage is— … a £10.85 for a worker who is aged 18 years or over (but is not yet aged 21 years)",
    "4A 1 The hourly rate of the national minimum wage is— … d £8.00 for a worker to whom the apprenticeship rate applies, as determined in accordance with regulation 5.",
  ];
  assert.equal(codeFits("I was 22 years old and working in the UK. Which hourly minimum wage applied to me?", clauses)[2], "fail");
  // Said, misspelt or denied: the tier stays for the judges.
  for (const said of ["I was an apprentice aged 22", "i wasnt an apprntice", "Olin oppisopimuksella", "Ich war Azubi"]) assert.notEqual(codeFits(said, clauses)[2], "fail", said);
  // It is never ruled out when it is the only tier.
  assert.notEqual(codeFits("I worked in the UK", [clauses[2]!])[0], "fail");
});

test("Regulation 261/2004 Art. 7(1)(b) is two alternatives: a long flight within the EU is in (b), one out of the EU is not", async () => {
  const { codeFits, wantOf } = await import("../src/timetravel/timetravel.ts");
  const art7 = [
    "1. Where reference is made to this Article, passengers shall receive compensation amounting to: … (a) EUR 250 for all flights of 1500 kilometres or less",
    "1. Where reference is made to this Article, passengers shall receive compensation amounting to: … (b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres",
    "1. Where reference is made to this Article, passengers shall receive compensation amounting to: … (c) EUR 600 for all flights not falling under (a) or (b)",
  ];
  const live = (s: string) => codeFits(s, art7).map((f, i) => (f === "fail" ? "" : "abc"[i])).join("");
  assert.equal(live("My flight was cancelled (the flight distance Stockholm to Tenerife is about 4380 km; both airports are within the EU/EEA, so it is an intra-Community flight)"), "b");
  assert.equal(live("My flight was cancelled (the flight distance Helsinki to New York is about 6610 km; not an intra-Community flight)"), "c");
  assert.equal(live("My flight of 1,900 km was cancelled"), "b");
  assert.equal(live("My flight of 1,200 km was cancelled"), "a");
  // A long flight with nothing said about the EU: (b) and (c) both stay for the judges.
  assert.equal(live("My flight of 4,400 km was cancelled"), "bc");
  // "Can I return it?" asks for a period, not an amount.
  assert.equal(wantOf("Can I return a laptop I bought online 10 days ago?"), "duration");
  assert.equal(wantOf("How much compensation am I owed?"), "amount");
});

test("built-in rights: a named jurisdiction or the wrong kind of journey rules a right out", async () => {
  const { jurisdictionCue, ruledOutBy, REGISTRY } = await import("../src/timetravel/timetravel.ts");
  const by = (celex: string) => REGISTRY.find((k) => (k.ref as { celex?: string }).celex === celex)!;
  const nmw = REGISTRY.find((k) => k.jurisdiction === "UK" && /Minimum Wage/.test(k.title))!;
  assert.equal(jurisdictionCue("What's the federal minimum wage for tipped workers?"), "US");
  assert.equal(jurisdictionCue("Frankfurt to New York in June, I paid $50 and €30"), undefined);
  assert.equal(jurisdictionCue("I was paid £9.50 an hour"), "UK");
  assert.equal(ruledOutBy("What's the federal minimum wage for tipped workers?", nmw), true);
  assert.equal(ruledOutBy("I was paid £9.50 an hour at 24", nmw), false);
  assert.equal(ruledOutBy("Mein Zug von Berlin nach München hatte 2 Stunden Verspätung", by("32004R0261")), true);
  assert.equal(ruledOutBy("Mein Zug von Berlin nach München hatte 2 Stunden Verspätung", by("32021R0782")), false);
  assert.equal(ruledOutBy("My train to Paris and then my flight were both delayed", by("32004R0261")), false);
  assert.equal(ruledOutBy("My flight to Paris was delayed 4 hours", by("32021R0782")), true);
});
