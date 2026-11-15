/**
 * The claim packet: everything the person needs to act, in one printable page (Print → Save as PDF).
 * The official text as it stood on the event date and today, with the links to the exact versions; the
 * time-limit verdict and last day; where to send it and what to know; the claim letter; the Warrant's digest
 * when the claim was signed. Self-contained (no scripts, no external requests), every value escaped.
 * Nothing here is sent anywhere; it is a file on the person's device.
 */
import type { ThenNowNext } from "../timetravel/timetravel.ts";
import type { Verdict } from "../timetravel/verdict.ts";

export interface PacketInput {
  r: ThenNowNext;
  question: string;
  letter?: string;
  verdict?: Verdict;
  lastDay?: string;
  steps?: Array<{ kind: string; need: string; title: string; url: string; published?: string; quote: string }>;
  warrantDigest?: string;
  generated: string; // ISO timestamp, supplied by the caller (no clock in here)
}

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
const safe = (u: string) => (/^https?:\/\//i.test(u) ? u : "#");
const link = (u: string, text = u) => `<a href="${esc(safe(u))}">${esc(text)}</a>`;

export function buildPacket(i: PacketInput): string {
  const { r } = i;
  const moment = (label: string, m: ThenNowNext["then"], quote?: string) => `<section><h2>${esc(label)} — ${esc(m.date)}</h2><p class="big">${esc(m.amount?.text ?? "see the clause")}</p>${quote ? `<blockquote>${esc(quote)}</blockquote>` : ""}<p class="src">Official text as of ${esc(m.date)}: ${link(m.url)}</p></section>`;
  const agree = r.agreement?.agreed ? "Three independent judges chose the same clause and code did not rule it out." : "The judges did not all agree: read the quoted clause yourself before acting.";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim packet — ${esc(r.provision.title.slice(0, 80))}</title>
<style>
 :root{color-scheme:light}
 body{font:15px/1.5 -apple-system,system-ui,"Segoe UI",sans-serif;color:#17181c;max-width:760px;margin:24px auto;padding:0 20px}
 h1{font-size:24px;margin:0 0 4px} h2{font-size:16px;margin:22px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px}
 .meta,.src{color:#555;font-size:13px} .big{font-size:26px;font-weight:700;margin:4px 0}
 blockquote{margin:8px 0;padding:8px 12px;border-left:3px solid #999;background:#f6f6f6;font-size:14px}
 pre{white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:6px;font:13px/1.5 ui-monospace,Menlo,monospace}
 .ok{color:#116b2d}.warn{color:#9a5b00}
 a{color:#1a47c8;word-break:break-all}
 @media print{body{margin:0}a{color:inherit}}
</style></head><body>
<h1>Claim packet</h1>
<p class="meta">${esc(r.provision.title)}<br>Prepared ${esc(i.generated.slice(0, 10))} for an event on ${esc(r.eventDate)}. Prepared by the Internet Butler; not legal advice.</p>
<h2>Your situation (as you wrote it)</h2><p>${esc(i.question)}</p>
${moment("What the law said then", r.then, r.evidence.quote)}
${moment("What the law says now", r.now)}
<p class="${r.changed ? "warn" : "ok"}">${r.changed ? `Changed since ${esc(r.eventDate)}: use the amount for the event date, not today's.` : `Unchanged since ${esc(r.eventDate)}.`}</p>
<p class="meta">${esc(agree)}</p>
${i.verdict ? `<h2>Time limit</h2><p class="${i.verdict.within ? "ok" : "warn"}">${esc(i.verdict.text)}${i.lastDay && i.verdict.within ? ` Last day: <b>${esc(i.lastDay)}</b>.` : ""}</p>` : ""}
${i.steps?.length ? `<h2>Where to send it and what to know</h2><ul>${i.steps.map((s) => `<li><b>${esc(s.need)}</b>: ${link(s.url, s.title)}${s.published ? ` <span class="meta">(${esc(s.published)})</span>` : ""}<br><span class="meta">“${esc(s.quote.slice(0, 260))}”</span></li>`).join("")}</ul>` : ""}
${i.letter ? `<h2>The claim, ready to send</h2><pre>${esc(i.letter)}</pre>` : ""}
${i.warrantDigest ? `<h2>Signed Warrant</h2><p class="meta">Signed on this device: <code>${esc(i.warrantDigest)}</code><br>A receiver can re-fetch the pinned official versions above and verify it.</p>` : ""}
<p class="meta">Nothing in this packet was sent anywhere. Review the amounts against the linked official text before you act.</p>
</body></html>
`;
}
