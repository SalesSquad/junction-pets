import { test } from "node:test";
import assert from "node:assert/strict";
import { relativeDate, spokenDate, voiceSupport } from "../src/ui/voice.ts";

test("spoken dates in English, Finnish and German become ISO dates", () => {
  const cases: Array<[string, string | undefined]> = [
    ["I was bumped on 2021-06-10 and arrived late", "2021-06-10"],
    ["I was bumped from my flight on June 10th, 2021", "2021-06-10"],
    ["it happened on the tenth of June 2021", "2021-06-10"],
    ["on 10 June 2021 my flight was cancelled", "2021-06-10"],
    ["the twenty-first of March 2019", "2019-03-21"],
    ["lentoni peruttiin 10. kesäkuuta 2021 ilman ilmoitusta", "2021-06-10"],
    ["Lento peruttiin 1.3.2019", "2019-03-01"],
    ["Mein Flug wurde am 10. Juni 2021 annulliert", "2021-06-10"],
    ["am 3. März 2019", "2019-03-03"],
    ["I may claim 2021 dollars", undefined],        // the verb "may" and a number are not a date
    ["in June 2021 I worked for £10 an hour", undefined], // no day: the date field stays with the person
    ["on February 30 2021", undefined],
  ];
  for (const [text, want] of cases) assert.equal(spokenDate(text), want, text);
});

test("voice support is reported, not assumed (no speech services in Node)", () => {
  assert.deepEqual(voiceSupport(), { dictate: false, speak: false });
});

test("relative dates count back from today", () => {
  const today = "2026-11-15";
  assert.equal(relativeDate("My flight was cancelled yesterday", today), "2026-11-14");
  assert.equal(relativeDate("Lentoni peruttiin eilen", today), "2026-11-14");
  assert.equal(relativeDate("Mein Flug wurde gestern annulliert", today), "2026-11-14");
  assert.equal(relativeDate("it was delayed last week", today), "2026-11-08");
  assert.equal(relativeDate("viime viikolla juna oli myöhässä", today), "2026-11-08");
  assert.equal(relativeDate("3 days ago I was bumped", today), "2026-11-12");
  assert.equal(relativeDate("vor 10 Tagen", today), "2026-11-05");
  assert.equal(relativeDate("I was bumped from a flight", today), undefined);
});
