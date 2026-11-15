import assert from "node:assert/strict";
import { test } from "node:test";
import { nextSteps, templatePlan, type StepSearch } from "../src/timetravel/nextSteps.ts";
import type { DecisionProvider } from "../src/decide/decide.ts";

const judge = (yes: RegExp): DecisionProvider => ({ id: "fake", decide: async (state: any, qs) => ({ provider: "fake", model: "m", usage: { inputTokens: 0, cachedTokens: 0 }, ms: 0, answers: qs.map((q) => ({ name: q.name, kind: "yesno" as const, p: yes.test(String(state.document)) ? 0.9 : 0.1 })) }) });

test("next steps: a writer's plan, a date-bounded news search, and only documents the judge accepts", async () => {
  const seen: Array<{ s: StepSearch; opts: any }> = [];
  const search = async (s: StepSearch, opts: any) => {
    seen.push({ s, opts });
    if (s.kind === "where") return [{ url: "https://www.finnair.com/claims", title: "Compensation claims | Finnair", highlights: ["Submit your claim with this form."] }, { url: "https://blog.example/how-to", title: "A blog", highlights: ["We explain claims."] }];
    if (s.kind === "deadline") return [{ url: "https://www.kkv.fi/lento", title: "Lentomatkustajan oikeudet", highlights: ["Vaatimus on esitettävä kolmen vuoden kuluessa."] }];
    return [{ url: "https://yle.fi/a/1", title: "Lakko pysäytti lentoja", publishedDate: "2019-06-10T08:00:00.000Z", highlights: ["Lakko perui lentoja Helsinki-Vantaalla maanantaina."] }, { url: "javascript:alert(1)", title: "bad", highlights: ["x"] }];
  };
  const plan = async () => ({ counterparty: "Finnair", country: "Finland", searches: [{ kind: "where", query: "Finnair korvaushakemus lomake peruttu lento" }, { kind: "deadline", query: "lentokorvaus vanhentumisaika Suomi EU261" }, { kind: "day", query: "lakko Helsinki-Vantaa 10. kesäkuuta 2019" }] });
  const r = await nextSteps({ question: "Finnair cancelled my flight from Helsinki to Rome", eventDate: "2019-06-10", today: "2026-11-15", right: "Regulation (EC) No 261/2004, Art. 7 — flight compensation (EU)" }, { plan, search, judge: judge(/finnair\.com|kolmen vuoden|Lakko/) });
  assert.equal(r.planned, "writer");
  assert.equal(r.counterparty, "Finnair");
  assert.deepEqual(r.steps.map((s) => [s.kind, s.url]), [["where", "https://www.finnair.com/claims"], ["deadline", "https://www.kkv.fi/lento"], ["day", "https://yle.fi/a/1"]]);
  assert.equal(r.steps[2]!.published, "2019-06-10");
  // The day search is news only, from two days before to four days after the event.
  const dayCall = seen.find((x) => x.s.kind === "day")!;
  assert.deepEqual(dayCall.opts, { news: true, from: "2019-06-08", to: "2019-06-14" });
  assert.deepEqual(seen.find((x) => x.s.kind === "where")!.opts, { news: false });
});

test("next steps: no writer or a malformed plan falls back to the template; a recent event is not searched past today", async () => {
  const t = templatePlan("My flight was cancelled", "2026-11-14", "Regulation (EC) No 261/2004, Art. 7 — flight compensation (EU)");
  assert.deepEqual(t.searches.map((s) => s.kind), ["where", "deadline", "day"]);
  // Nothing was disrupted in a pay question: no search for what happened that day.
  assert.deepEqual(templatePlan("I was paid £10 an hour in June 2023", "2023-06-15", "National Minimum Wage Regulations 2015").searches.map((s) => s.kind), ["where", "deadline"]);
  let to = "";
  const search = async (s: StepSearch, opts: any) => { if (s.kind === "day") to = opts.to; return []; };
  const r = await nextSteps({ question: "My flight was cancelled", eventDate: "2026-11-14", today: "2026-11-15" }, { plan: async () => ({ searches: [{ kind: "where", query: "x" }] }), search, judge: judge(/./) });
  assert.equal(r.planned, "template");
  assert.equal(to, "2026-11-15");
  assert.deepEqual(r.steps, []);
});
