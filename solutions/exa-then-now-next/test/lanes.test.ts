import assert from "node:assert/strict";
import { test } from "node:test";
import { compileTwoLane } from "../src/warrant/compile.ts";
import { decideSupport, type JudgeFn } from "../src/warrant/judges.ts";
import { analyseTiers, conditionsOf, extractFromAnswerLane, extractPremises, extractQuantities, groundedCitationQuery, sameQuantity, threeWay, triangulate, type LaneResult } from "../src/warrant/lanes.ts";

const q = (t: string) => extractQuantities(t);

test("quantities normalise across notations", () => {
  const [a] = q("compensation of €250 per passenger");
  for (const t of ["EUR 250 for all flights", "250 euros", "EUR 250"]) assert.ok(q(t).some((x) => sameQuantity(x, a!)), t);
  const [d] = q("within fourteen days of delivery");
  assert.ok(q("a period of 14 days").some((x) => sameQuantity(x, d!)));
  assert.equal(q("25 % of the ticket price")[0]?.value, 25);
  assert.equal(q("until midnight of the third business day")[0]?.unit, "business_day");
  assert.equal(q("flights of 1,500 kilometres or less")[0]?.value, 1500);
  assert.equal(q("the minimum wage is $7.25 an hour")[0]?.value, 7.25);
});

const answerLane: LaneResult[] = [
  { url: "https://consumer.example/eu261", highlights: ["My flight was 3 hours late. Am I entitled to compensation? Yes. For flights of 1,500 km or less you are entitled to €250 under Regulation (EC) No 261/2004."] },
  { url: "https://claims.example/guide", highlights: ["Passengers on short flights receive EUR 250 when they arrive three hours late."] },
  { url: "https://blog.example/old", highlights: ["Long flights pay €600, medium flights €400."] },
];

test("extraction is grounded in retrieved text and follows source consensus", () => {
  const ex = extractFromAnswerLane(answerLane, { money: 2 });
  assert.equal(ex.quantity?.value, 250);
  assert.equal(ex.support, 2);
  assert.equal(ex.instrument, "Regulation (EC) No 261/2004");
  assert.ok(answerLane[0]!.highlights[0]!.replace(/\s+/g, " ").includes(ex.sentence!), "sentence is verbatim from a source");
  assert.ok(!ex.sentence!.endsWith("?"));
  const query = groundedCitationQuery(ex)!;
  assert.match(query, /€250/);
  assert.match(query, /The official text of the regulation:$/);
});

const LEGAL_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32004R0261";
const pages: Record<string, string> = {
  [LEGAL_URL]: "Article 7. Where reference is made to this Article, passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres.",
  "https://eur-lex.europa.eu/other": "Passengers shall receive compensation amounting to EUR 600 for all other flights.",
  "https://curia.europa.eu/sturgeon": "Passengers whose flights are delayed may rely on the right to compensation where they reach their final destination three hours or more after the arrival time originally scheduled by the air carrier.",
};
const fetchPage = async (url: string) => {
  if (!(url in pages)) throw new Error("404");
  return pages[url]!;
};

test("triangulation: agree, disagree and not found", async () => {
  const ex = extractFromAnswerLane(answerLane, { money: 2 });
  const agree = await triangulate(ex, [LEGAL_URL], fetchPage);
  assert.equal(agree.status, "agree");
  assert.match(agree.status === "agree" ? agree.quote : "", /EUR 250 for all flights of 1500 kilometres or less/);
  const disagree = await triangulate(ex, ["https://eur-lex.europa.eu/other"], fetchPage);
  assert.equal(disagree.status, "disagree");
  assert.equal((await triangulate(ex, ["https://eur-lex.europa.eu/missing"], fetchPage)).status, "not_found");
});

test("two-lane compile: the authority query is built from the answer lane, and a stale explainer yields NEEDS_INFO", async () => {
  const queries: string[] = [];
  const search = async (query: string) => {
    queries.push(query);
    return queries.length === 1 ? answerLane : [{ url: LEGAL_URL, highlights: ["Article 7 compensation"] }, { url: "https://curia.europa.eu/sturgeon", highlights: [] }, { url: "https://news.example/x", highlights: [] }];
  };
  const r = await compileTwoLane("How much compensation do I get if my short EU flight is 3 hours late?", search, fetchPage);
  assert.equal(r.outcome, "GROUNDED", r.reasons.join("; "));
  assert.ok(queries[1]!.includes("€250"), "authority query carries the grounded amount");
  assert.equal(r.rule?.source.url, LEGAL_URL);
  // Two premises: the amount from the regulation and the 3-hour threshold from the court's judgment.
  assert.deepEqual(r.premises.map((p) => [p.premise.role, p.premise.quantity.value, p.status]), [["threshold", 180, "confirmed"], ["outcome", 250, "confirmed"]]);
  assert.match(r.premises[0]!.premise.sentence, /three hours late/, "threshold grounded in a rule sentence, not the situation");
  assert.equal(r.premises[0]!.rule?.source.url, "https://curia.europa.eu/sturgeon");

  const stale: LaneResult[] = [{ url: "https://old.example", highlights: ["Compensation is EUR 300 for short flights."] }];
  let n = 0;
  const search2 = async () => (n++ === 0 ? stale : [{ url: LEGAL_URL, highlights: [] }]);
  const r2 = await compileTwoLane("How much compensation do I get?", search2, fetchPage);
  assert.equal(r2.outcome, "NEEDS_INFO");
  assert.match(r2.reasons.join(" "), /explainer states EUR 300; legal text states/);
});

test("two judges then the page: agreement decides; disagreement is settled by the verbatim quote", async () => {
  const yes: JudgeFn = async () => "supports";
  const no: JudgeFn = async () => "says_nothing";
  const quote = "EUR 250 for all flights of 1500 kilometres or less";
  const [quantity] = q("€250");
  const agree = await decideSupport({ premise: "EUR 250", quote, url: LEGAL_URL, quantity, judges: [yes, yes], fetch: fetchPage });
  assert.deepEqual([agree.verdict, agree.by], ["supported", "judges_agree"]);
  const split = await decideSupport({ premise: "EUR 250", quote, url: LEGAL_URL, quantity, judges: [yes, no], fetch: fetchPage });
  assert.deepEqual([split.verdict, split.by], ["supported", "page_verbatim"]);
  const fake = await decideSupport({ premise: "EUR 250", quote: "EUR 250 for every flight", url: LEGAL_URL, quantity, judges: [yes, no], fetch: fetchPage });
  assert.equal(fake.verdict, "unsupported");
});

test("regressions from the live evaluation: decimals, hour/minute equivalence, possessive months", () => {
  const ex = extractFromAnswerLane([{ url: "https://dol.example", highlights: ["The federal minimum wage for covered nonexempt employees is $7.25 per hour. Many states also have minimum wage laws."] }], { money: 2 });
  assert.equal(ex.quantity?.value, 7.25);
  const [two] = q("delayed by two hours");
  assert.ok(q("for more than 120 minutes").some((x) => sameQuantity(x, two!)));
  assert.equal(q("a deposit of no more than one month's rent").filter((x) => x.kind === "duration").length, 0);
});

test("threshold premises match the question's unit: 'delayed 7 hours' finds 'six hours', not '7 business days'", () => {
  const lane: LaneResult[] = [
    { url: "https://dot.example/refunds", highlights: ["Airlines must issue refunds within 7 business days for credit card purchases."] },
    { url: "https://dot.example/rule", highlights: ["A significant delay means a departure or arrival more than six hours later for international flights."] },
  ];
  const ps = extractPremises(lane, "Do US airlines have to refund me if my international flight is delayed 7 hours?");
  const threshold = ps.find((p) => p.role === "threshold");
  assert.equal(threshold?.quantity.text, "six hours");
});

test("three-way check: sources beat memory, memory can side with the law against a stale explainer", () => {
  const premise = { role: "outcome" as const, quantity: q("€250")[0]!, sentence: "You get €250.", sourceUrl: "https://x.example", support: 2 };
  const agree = { status: "agree" as const, quote: "EUR 250 for all flights", url: LEGAL_URL };
  assert.equal(threeWay(premise, agree, q("EUR 400")).status, "confirmed_model_disagrees");
  assert.equal(threeWay(premise, agree, []).status, "confirmed");
  const stale = { ...premise, quantity: q("€300")[0]! };
  const disagree = { status: "disagree" as const, found: q("EUR 250"), url: LEGAL_URL };
  assert.equal(threeWay(stale, disagree, q("EUR 250")).status, "conflict_model_sides_with_law");
  assert.equal(threeWay(stale, disagree, []).status, "conflict");
  assert.equal(threeWay(premise, { status: "not_found" }, q("€250")).status, "unverified_model_agrees");
});

test("binding threshold: the largest lower bound the situation meets, the smallest upper bound that covers it", () => {
  const lane: LaneResult[] = [
    { url: "https://a.example", highlights: ["Passengers are entitled to meals when a short flight is delayed two hours or more."] },
    { url: "https://b.example", highlights: ["Compensation of £220 is due when the flight arrives three hours or more late."] },
  ];
  const ps = extractPremises(lane, "How much compensation do I get in the UK for a short flight delayed 3 hours?");
  assert.equal(ps.find((p) => p.role === "threshold")?.quantity.value, 180);
  const lane2: LaneResult[] = [{ url: "https://c.example", highlights: ["You may cancel within 14 days. Refunds are paid within 30 days."] }];
  const ps2 = extractPremises(lane2, "I bought it online 10 days ago, can I still cancel?");
  assert.equal(ps2.find((p) => p.role === "threshold")?.quantity.value, 14);
});

const NYC_TABLE = "Landlords must give you written notice if they plan on raising your rent by more than 5%. ### Required notice period | Conditions | Required notice | | --- | --- | | You've lived in the unit less than one year and you don't have lease term of one year or longer | 30 days | | You've lived in the unit more than one year but less than two years or your lease term is at least one year, but less than two years | 60 days | | You've lived in the unit for more than two years or your lease term is at least two years | 90 days |";

test("tiered rule without the deciding fact: NEEDS_INFO with a clarifying question and the tiers as options", async () => {
  const question = "How much notice must my New York landlord give before a big rent increase?";
  const search = async (q: string) => (q === question ? [{ url: "https://www.nyc.gov/rent", highlights: [NYC_TABLE] }] : [{ url: "https://www.nysenate.gov/legislation/laws/RPP/226-C", highlights: [] }]);
  const pages: Record<string, string> = { "https://www.nysenate.gov/legislation/laws/RPP/226-C": "If the tenant has occupied the unit for more than two years, the landlord shall provide at least ninety days notice." };
  const r = await compileTwoLane(question, search, async (u) => pages[u] ?? "");
  assert.equal(r.outcome, "NEEDS_INFO");
  assert.match(r.clarify?.question ?? "", /How long have you lived in the unit/);
  assert.equal(r.clarify?.options.length, 3);
  assert.match(r.clarify?.options[2] ?? "", /more than two years.*→ 90 days/);
  // The person answers; the stated "3 years" satisfies "more than two years" and selects 90 days.
  const answered = `${question} I have lived there for 3 years.`;
  const ps = extractPremises([{ url: "https://www.nyc.gov/rent", highlights: [NYC_TABLE] }], answered);
  const outcome = ps.find((p) => p.role === "outcome")!;
  const tiers = analyseTiers([{ url: "https://www.nyc.gov/rent", highlights: [NYC_TABLE] }], outcome, answered);
  assert.deepEqual([tiers?.resolved?.value.value, tiers?.resolved?.by], [90, "condition"]);
});

test("tiers resolved from the question without asking: a stated distance selects EUR 250", () => {
  const art7 = "Passengers shall receive compensation amounting to: (a) EUR 250 for all flights of 1500 kilometres or less; (b) EUR 400 for all intra-Community flights of more than 1500 kilometres, and for all other flights between 1500 and 3500 kilometres; (c) EUR 600 for all flights not falling under (a) or (b).";
  const lane = [{ url: "https://eur-lex.europa.eu/x", highlights: [art7] }];
  const withDistance = "How much compensation do I get if my 1,500 km flight arrives 3 hours late?";
  const p = extractPremises(lane, withDistance).find((x) => x.role === "outcome")!;
  const t = analyseTiers(lane, p, withDistance);
  assert.deepEqual([t?.resolved?.value.value, t?.resolved?.by], [250, "condition"]);
  assert.equal(conditionsOf("for all flights of 1500 kilometres or less")[0]?.op, "<=");
  const vague = "How much compensation do I get for my delayed EU flight?";
  const p2 = extractPremises(lane, vague).find((x) => x.role === "outcome")!;
  assert.match(analyseTiers(lane, p2, vague)?.clarify?.question ?? "", /How long is the flight/);
});

test("role-aware triangulation: the right number in the wrong clause does not confirm a premise", async () => {
  const { triangulateQuantity, roleOverlap } = await import("../src/warrant/lanes.ts");
  const law = [{ url: LEGAL_URL, text: [
    "Article 5. In case of cancellation of a flight, the passengers concerned shall be offered assistance by the operating air carrier.",
    "Article 6. When an operating air carrier reasonably expects a flight to be delayed for two hours or more, passengers shall be offered meals and refreshments.",
    "Article 7. Passengers shall receive compensation amounting to EUR 250 for all flights of 1500 kilometres or less.",
    "Article 8. Passengers shall be offered the choice between reimbursement of the cost of the ticket and re-routing to their final destination.",
    "Article 9. Passengers shall be offered free of charge hotel accommodation where a stay of one or more nights becomes necessary.",
    "Article 10. If an operating air carrier places a passenger in a class higher than that for which the ticket was purchased, it may not request any supplementary payment.",
  ].join(" ") }];
  const [two] = q("two hours");
  const wrongRole = triangulateQuantity(two!, law, "Passengers are entitled to compensation when the flight arrives two hours late.");
  assert.equal(wrongRole.status, "misplaced");
  const rightRole = triangulateQuantity(two!, law, "Passengers must be offered meals and refreshments when a flight is delayed two hours.");
  assert.equal(rightRole.status, "agree");
  const [amount] = q("€250");
  assert.equal(triangulateQuantity(amount!, law, "You are entitled to compensation of €250 for flights up to 1,500 km.").status, "agree");
  assert.ok(roleOverlap("compensation for flights", "compensation amounting to EUR 250 for all flights") >= 2);
});

test("contrastive role check: a better-matching clause with another value turns a match into a conflict", async () => {
  const { triangulateQuantity } = await import("../src/warrant/lanes.ts");
  const law = [{ url: LEGAL_URL, text: "Passengers shall be offered meals and refreshments where the flight is delayed by two hours or more. Passengers shall have the right to compensation where they reach their final destination three hours or more after the scheduled arrival time. Member States shall lay down rules on penalties." }];
  const r = triangulateQuantity(q("two hours")[0]!, law, "Passengers are entitled to compensation if they reach their destination two hours late.");
  assert.equal(r.status, "misplaced");
  assert.equal(r.status === "misplaced" ? r.competing?.quantity.value : 0, 180);
});
