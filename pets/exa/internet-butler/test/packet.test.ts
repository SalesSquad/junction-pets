import { test } from "node:test";
import assert from "node:assert/strict";
import { buildPacket } from "../src/ui/packet.ts";

const r = { question: "q", eventDate: "2026-11-05", today: "2026-11-15", provision: { ref: { source: "eurlex", celex: "x" }, title: "Directive <b>2011/83</b>", via: "registry" }, then: { date: "2026-11-05", url: "https://example.eu/then", clause: "c", amount: { kind: "duration", value: 14, unit: "day", text: "14 days" }, p: 1 }, now: { date: "2026-11-15", url: "javascript:alert(1)", clause: "c", amount: { kind: "duration", value: 14, unit: "day", text: "14 days" }, p: 1 }, changed: false, changes: [], upcoming: [], receipts: [], evidence: { url: "https://example.eu/then", quote: "the consumer shall have 14 days <script>x</script>", asOf: "2026-11-05" }, agreement: { agreed: true, votes: [], abstained: [] } } as never;

test("claim packet: self-contained, escaped, no unsafe links", () => {
  const html = buildPacket({ r, question: "I bought it <img src=x onerror=1> 10 days ago", letter: "Dear shop,\nplease refund.", generated: "2026-11-15T05:00:00Z", lastDay: "2026-11-19", verdict: { periodDays: 14, elapsedDays: 10, arithmeticWithin: true, daysLeft: 4, text: "Approximate arithmetic; this does not determine a legal deadline." }, steps: [{ kind: "where", need: "where to send", title: "Claims page", url: "https://shop.example/claims", quote: "Send it here", published: "2026-10-01" }], warrantDigest: "abc123" });
  assert.ok(!/<script|<img|<b>2011/.test(html), "markup from inputs is escaped");
  assert.ok(html.includes("href=\"#\""), "a javascript: URL becomes #");
  assert.ok(!/<(link|script|img|iframe|object|embed|video|audio|source)\b|@import|url\(/i.test(html), "no tag that loads anything");
  assert.match(html, /Calendar estimate using the displayed date: <b>2026-11-19<\/b>/);
  assert.match(html, /not a verified legal deadline/);
  assert.doesNotMatch(html, /Last day:/);
  assert.match(html, /Dear shop,\nplease refund\./);
  assert.match(html, /Signed on this device: <code>abc123<\/code>/);
});
