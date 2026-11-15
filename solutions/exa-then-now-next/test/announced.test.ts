import assert from "node:assert/strict";
import { test } from "node:test";
import { announcedChanges, datesIn } from "../src/timetravel/announced.ts";
import type { DecisionProvider } from "../src/decide/decide.ts";

test("dates written in prose become ISO dates", () => {
  assert.deepEqual(datesIn("It applies from 23 October 2027; the rate rises on April 1, 2027 and again in April 2028. See 2026-11-14 and 1.1.2027.").map((d) => d.iso).sort(), ["2026-11-14", "2027-01-01", "2027-04-01", "2027-10-23", "2028-04-01"]);
  assert.deepEqual(datesIn("between 2020 and 2025, section 1.98").length, 0);
});

test("announced changes: code needs a future date in the text, the judge confirms the provision", async () => {
  const search = async () => [
    { url: "https://www.gov.uk/government/news/nlw-2027", title: "National Living Wage to rise", publishedDate: "2026-10-28T00:00:00.000Z", highlights: ["The National Living Wage will rise to £13.21 an hour from 1 April 2027. Younger workers also get an increase."] },
    { url: "https://www.gov.uk/national-minimum-wage-rates", title: "Current rates", highlights: ["The rates changed on 1 April 2026."] },
    { url: "https://www.gov.uk/government/news/fuel-duty", title: "Fuel duty", highlights: ["Fuel duty will change from 1 March 2027."] },
  ];
  const judge: DecisionProvider = { id: "fake", decide: async (state: any, qs) => ({ provider: "fake", model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q) => ({ name: q.name, kind: q.kind, p: /Living Wage/.test(state.document) ? 0.93 : 0.04 })) }) };
  const out = await announcedChanges({ title: "National Minimum Wage Regulations 2015", about: "The minimum hourly pay a UK worker is entitled to.", jurisdiction: "UK", today: "2026-11-14" }, { search, judge });
  assert.equal(out.length, 1);
  assert.equal(out[0]!.effective, "2027-04-01");
  assert.equal(out[0]!.amount?.text, "£13.21");
  assert.equal(out[0]!.quote, "The National Living Wage will rise to £13.21 an hour from 1 April 2027.");
  assert.equal(out[0]!.published, "2026-10-28");
});

test("announced changes: a deadline is not the effective date, the new amount is the one after \"to\", a quote ends with its highlight", async () => {
  const yes: DecisionProvider = { id: "fake", decide: async (_s, qs) => ({ provider: "fake", model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q) => ({ name: q.name, kind: "yesno" as const, p: 0.9 })) }) };
  const run = (docs: Array<{ url: string; title?: string; highlights: string[] }>) => announcedChanges({ title: "14 CFR 250.5", about: "denied boarding compensation", jurisdiction: "US", today: "2026-11-14" }, { search: async () => docs, judge: yes });
  // The comment deadline comes first in the text and is earlier; the effective date is what is shown.
  const a = await run([{ url: "https://www.federalregister.gov/d/1", title: "Proposed rule", highlights: ["Comments must be received by January 15, 2027.", "The limit increases from $2,150 to $2,300 and the rule is effective April 1, 2027."] }]);
  assert.equal(a[0]!.effective, "2027-04-01");
  assert.equal(a[0]!.amount?.text, "$2,300");
  assert.equal(a[0]!.amountFrom, "quote");
  assert.ok(!a[0]!.quote.includes("Comments"));
  // A document whose only future date is a deadline is dropped.
  assert.equal((await run([{ url: "https://www.regulations.gov/d/2", highlights: ["The consultation closes on 1 February 2027."] }])).length, 0);
  // Two figures and no "to": no amount is claimed. A single figure in the title is labelled as coming from the title.
  const b = await run([{ url: "https://www.transportation.gov/d/3", title: "Limit raised to $2,300", highlights: ["Carriers paid $775 or $1,550 before; the new rule takes effect on 1 April 2027"] }]);
  assert.equal(b[0]!.amount?.text, "$2,300");
  assert.equal(b[0]!.amountFrom, "title");
  // The quote stops where its highlight stops, and a long sentence still shows its date.
  const long = `${"The Department reviewed many submissions and ".repeat(12)}the amount applies from 1 April 2027`;
  const c = await run([{ url: "https://www.transportation.gov/d/4", highlights: [long, "Unrelated next highlight about something else."] }]);
  assert.ok(c[0]!.quote.includes("1 April 2027"));
  assert.ok(!c[0]!.quote.includes("Unrelated"));
});
