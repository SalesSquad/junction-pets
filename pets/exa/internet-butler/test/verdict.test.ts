import { test } from "node:test";
import assert from "node:assert/strict";
import { elapsedDays, timeVerdict } from "../src/timetravel/verdict.ts";

test("elapsed time is read only from phrases that say how long ago", () => {
  assert.equal(Math.round(elapsedDays("I bought it 10 days ago")!), 10);
  assert.equal(Math.round(elapsedDays("Tilasin puhelimen 10 päivää sitten")!), 10);
  assert.equal(Math.round(elapsedDays("Pesukone hajosi 14 kuukauden jälkeen")!), 426);
  assert.equal(Math.round(elapsedDays("Die Maschine ging nach 26 Monaten kaputt")!), 791);
  assert.equal(Math.round(elapsedDays("It broke after eighteen months".replace("eighteen", "two"))!), 61);
  assert.equal(elapsedDays("My flight was 3 hours late on a 2 year contract"), undefined);
  assert.equal(Math.round(elapsedDays("a week ago I ordered it")!), 7);
});

test("elapsed-time comparison is explicitly approximate, not a legal verdict", () => {
  const within = timeVerdict("I ordered it 10 days ago", { kind: "duration", value: 14, unit: "day" })!;
  assert.equal(within.arithmeticWithin, true);
  assert.equal(within.daysLeft, 4);
  assert.match(within.text, /does not determine a legal deadline or eligibility/);
  assert.doesNotMatch(within.text, /still in time/i);
  const out = timeVerdict("Maschine kaputt nach 26 Monaten", { kind: "duration", value: 2, unit: "year" })!;
  assert.equal(out.arithmeticWithin, false);
  assert.match(out.text, /does not determine a legal deadline or eligibility/);
  assert.doesNotMatch(out.text, /out of time/i);
  assert.equal(timeVerdict("10 days ago", { kind: "money", value: 400, unit: "EUR" }), undefined);
  assert.equal(timeVerdict("I ordered it", { kind: "duration", value: 14, unit: "day" }), undefined);
  assert.equal(timeVerdict("10 days ago", { kind: "duration", value: NaN, unit: "day" }), undefined);
  assert.equal(timeVerdict("10 days ago", { kind: "duration", value: 14, unit: "toString" }), undefined);
});

test("last day: days, calendar months and years from the event date", async () => {
  const { lastDay, icsEvent } = await import("../src/timetravel/verdict.ts");
  assert.equal(lastDay("2026-11-05", { kind: "duration", value: 14, unit: "day" }), "2026-11-19");
  assert.equal(lastDay("2025-01-31", { kind: "duration", value: 1, unit: "month" }), "2025-02-28"); // never overflows into the next month
  assert.equal(lastDay("2024-02-29", { kind: "duration", value: 2, unit: "year" }), "2026-02-28");
  assert.equal(lastDay("2026-11-05", { kind: "money", value: 400, unit: "EUR" }), undefined);
  assert.equal(lastDay("2026-02-30", { kind: "duration", value: 14, unit: "day" }), undefined);
  assert.equal(lastDay("2026-11-05", { kind: "duration", value: 1.5, unit: "day" }), undefined);
  const ics = icsEvent({ summary: "Last day to withdraw; keep proof", date: "2026-11-19", description: "Line1\nLine2, with comma", uid: "x@butler", stamp: "2026-11-15T05:00:00.000Z" });
  assert.match(ics, /DTSTART;VALUE=DATE:20261119\r\nDTEND;VALUE=DATE:20261120/);
  assert.match(ics, /SUMMARY:Last day to withdraw\\; keep proof/);
  assert.match(ics, /DESCRIPTION:Line1\\nLine2\\, with comma/);
  assert.match(ics, /DTSTAMP:20261115T050000Z/);
  assert.ok(ics.endsWith("END:VCALENDAR\r\n"));
  const unicode = icsEvent({ summary: "Ä".repeat(90), date: "2026-11-19", description: "A\rB\nC", uid: "x@butler", stamp: "2026-11-15T05:00:00Z" });
  assert.ok(unicode.split("\r\n").every(line => new TextEncoder().encode(line).length <= 75));
  assert.match(unicode, /DESCRIPTION:A\\nB\\nC/);
  assert.throws(() => icsEvent({ summary: "x", date: "2026-02-30", description: "x", uid: "x@butler", stamp: "2026-11-15T05:00:00Z" }));
  assert.throws(() => icsEvent({ summary: "x", date: "2026-11-19", description: "x", uid: "x\r\nBEGIN:EVIL", stamp: "2026-11-15T05:00:00Z" }));
});
