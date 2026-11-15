#!/usr/bin/env node
// Documents as evidence: can a typed judge check claims against a photo of a boarding pass?
// 20 synthetic passes with random data (rendered SVG -> PNG -> JPEG, macOS qlmanage/sips) and 8
// claims per pass, true or false by construction. Jev 1.14 answers one yes/no per claim, all claims
// about one pass in one request (one object per state). Box locates the actual-arrival field.
// Usage: node bench/image_claims.mjs [--n=20]   (needs TYPESAFE_API_KEY or ~/.config/typesafe/env)
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { typesafeJev } from "../src/decide/decide.ts";

const here = new URL(".", import.meta.url);
const N = Number(process.argv.find((a) => a.startsWith("--n="))?.slice(4) ?? 20);
const dir = new URL("results/image-claims/", here).pathname;
mkdirSync(dir, { recursive: true });
const key = process.env.TYPESAFE_API_KEY || readFileSync(`${homedir()}/.config/typesafe/env`, "utf8").match(/^TYPESAFE_API_KEY=(.*)$/m)?.[1]?.trim().replace(/^["']|["']$/g, "");
const { TypeSafeClient, image } = await import("@typesafe-ai/sdk");
const ts = new TypeSafeClient({ apiKey: key, defaultModel: "jev-1.14.0" });
// With the SDK, images must be SDK image objects (it uploads them as multipart).
const jev = typesafeJev({ systemOne: (r, o) => ts.systemOne(r, o), toAsset: (a) => image(new Blob([Buffer.from(a.dataBase64, "base64")], { type: a.format === "png" ? "image/png" : "image/jpeg" })) });

let seed = 20261114;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
const pick = (xs) => xs[Math.floor(rnd() * xs.length)];
const AIRLINES = ["NORDIC SKY AIRWAYS", "BALTIC WINGS", "AURORA AIR", "FJORD JET", "LAKELAND AIRLINES"];
const AIRPORTS = ["HEL", "BCN", "ARN", "CDG", "FRA", "AMS", "LIS", "OSL", "DUB", "VIE", "ATH", "MAD"];
const hhmm = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");

function pass() {
  const code = pick(["NS", "BW", "AU", "FJ", "LK"]);
  const num = String(100 + Math.floor(rnd() * 899));
  const from = pick(AIRPORTS);
  let to = pick(AIRPORTS);
  while (to === from) to = pick(AIRPORTS);
  const sched = 6 * 60 + Math.floor(rnd() * 14 * 12) * 5;
  const delay = pick([0, 0, 10, 45, 95, 150, 185, 240, 255, 300]);
  const seat = `${1 + Math.floor(rnd() * 32)}${pick(["A", "B", "C", "D", "E", "F"])}`;
  return { airline: pick(AIRLINES), flight: `${code} ${num}`, from, to, sched: hhmm(sched), actual: hhmm(sched + delay), delay, stamp: delay >= 15, seat, gate: `${pick(["A", "B", "C", "D"])}${1 + Math.floor(rnd() * 40)}` };
}

function svg(p) {
  const t = (x, y, size, s, extra = "") => `<text x="${x}" y="${y}" font-family="Helvetica" font-size="${size}" ${extra}>${esc(s)}</text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1200" viewBox="0 0 1200 1200"><rect width="1200" height="1200" fill="#f4f1ea"/><g transform="translate(0,200)">
  <rect x="60" y="60" width="1080" height="680" rx="24" fill="#fff" stroke="#1d2a4d" stroke-width="4"/><rect x="60" y="60" width="1080" height="110" rx="24" fill="#1d2a4d"/>
  ${t(100, 132, 44, `${p.airline} · BOARDING PASS`, 'font-weight="bold" fill="#fff"')}
  ${t(100, 240, 26, "PASSENGER", 'fill="#555"')}${t(100, 285, 38, "DOE / ALEX MR", 'fill="#111"')}
  ${t(100, 360, 26, "FLIGHT", 'fill="#555"')}${t(100, 410, 48, p.flight, 'font-weight="bold" fill="#111"')}
  ${t(420, 360, 26, "FROM → TO", 'fill="#555"')}${t(420, 410, 44, `${p.from} → ${p.to}`, 'fill="#111"')}
  ${t(100, 490, 26, "SCHEDULED ARRIVAL", 'fill="#555"')}${t(100, 535, 38, `14 NOV 2026 ${p.sched}`, 'fill="#111"')}
  ${t(520, 490, 26, "ACTUAL ARRIVAL", 'fill="#555"')}${t(520, 535, 38, `14 NOV 2026 ${p.actual}`, 'fill="#111"')}
  ${p.stamp ? `<g transform="rotate(-8 950 265)"><rect x="820" y="210" width="260" height="110" rx="10" fill="none" stroke="#c0392b" stroke-width="8"/>${t(845, 290, 56, "DELAYED", 'font-weight="bold" fill="#c0392b"')}</g>` : ""}
  ${t(820, 640, 26, "GATE", 'fill="#555"')}${t(820, 690, 48, p.gate, 'font-weight="bold" fill="#111"')}${t(960, 640, 26, "SEAT", 'fill="#555"')}${t(960, 690, 48, p.seat, 'font-weight="bold" fill="#111"')}
  </g></svg>`;
}

const swapDigits = (f) => { const [c, n] = f.split(" "); const m = n[1] === n[2] ? `${n[0]}${(Number(n[2]) + 1) % 10}${n[1]}` : `${n[0]}${n[2]}${n[1]}`; return `${c} ${m}`; };
const shift = (h, d) => { const [a, b] = h.split(":").map(Number); return hhmm(a * 60 + b + d); };
const claims = (p) => [
  { type: "flight_true", text: `The flight number is ${p.flight}.`, truth: true },
  { type: "flight_false", text: `The flight number is ${swapDigits(p.flight)}.`, truth: false },
  { type: "route_true", text: `The flight goes from ${p.from} to ${p.to}.`, truth: true },
  { type: "route_reversed", text: `The flight goes from ${p.to} to ${p.from}.`, truth: false },
  { type: "arrival_true", text: `The actual arrival time printed is ${p.actual}.`, truth: true },
  { type: "arrival_false", text: `The actual arrival time printed is ${shift(p.actual, 60)}.`, truth: false },
  { type: "stamp", text: "The pass carries a red DELAYED stamp.", truth: p.stamp },
  { type: "seat_false", text: `The seat is ${p.seat.replace(/\d+/, (d) => String(Number(d) + 3))}.`, truth: false },
];

const rows = [];
const t0 = Date.now();
let tokens = 0;
for (let i = 0; i < N; i++) {
  const p = pass();
  const base = `${dir}pass-${i}`;
  writeFileSync(`${base}.svg`, svg(p));
  execFileSync("qlmanage", ["-t", "-s", "1200", "-o", dir, `${base}.svg`], { stdio: "ignore" });
  execFileSync("sips", ["-s", "format", "jpeg", "-s", "formatOptions", "88", `${base}.svg.png`, "--out", `${base}.jpg`], { stdio: "ignore" });
  const ref = `pass-${crypto.randomUUID()}`;
  const cs = claims(p);
  const qs = [
    ...cs.map((c, k) => ({ kind: "yesno", name: `claim_${k}`, instructions: `Is \`claims[${k}]\` true according to what is printed on \`pass\`?` })),
    { kind: "box", name: "arrival_box", instructions: "the actual arrival date and time value (not its label) on `pass`" },
  ];
  const r = await jev.decide({ pass: ref, claims: cs.map((c) => c.text) }, qs, { [ref]: { format: "jpg", dataBase64: readFileSync(`${base}.jpg`).toString("base64") } });
  tokens += r.usage.inputTokens;
  const box = r.answers.at(-1).box;
  // Truth for the box: the actual-arrival value is drawn at x 520..~850, baseline y 535 (+200).
  const truthBox = { left: 520 / 1200, right: 850 / 1200, top: 702 / 1200, bottom: 742 / 1200 };
  const ix = Math.max(0, Math.min(box.right, truthBox.right) - Math.max(box.left, truthBox.left)), iy = Math.max(0, Math.min(box.bottom, truthBox.bottom) - Math.max(box.top, truthBox.top));
  const iou = (ix * iy) / ((box.right - box.left) * (box.bottom - box.top) + (truthBox.right - truthBox.left) * (truthBox.bottom - truthBox.top) - ix * iy);
  cs.forEach((c, k) => rows.push({ pass: i, ...c, p: r.answers[k].p }));
  rows.push({ pass: i, type: "arrival_box", iou, box, confidence: r.answers.at(-1).confidence, ms: r.ms });
  process.stdout.write(`pass ${i}: ${r.ms} ms, box IoU ${iou.toFixed(2)}\n`);
}

const claimRows = rows.filter((r) => r.type !== "arrival_box");
const ok = (r) => (r.p > 0.5) === r.truth;
const lines = [`# Claims against a photo of a document (${new Date().toISOString().slice(0, 10)})`, "", `${N} synthetic boarding passes, ${claimRows.length} claims (true or false by construction), jev-1.14.0 with \`TypeSafe-Danger-Zone-Images: true\`, all claims about one pass in one request.`, "", "| claim type | right | mean p(yes) |", "|---|---|---|"];
for (const t of [...new Set(claimRows.map((r) => r.type))]) {
  const xs = claimRows.filter((r) => r.type === t);
  lines.push(`| ${t} | ${xs.filter(ok).length}/${xs.length} | ${(xs.reduce((s, r) => s + r.p, 0) / xs.length).toFixed(2)} |`);
}
const brier = claimRows.reduce((s, r) => s + (r.p - (r.truth ? 1 : 0)) ** 2, 0) / claimRows.length;
const unsure = claimRows.filter((r) => r.p >= 0.3 && r.p <= 0.7);
const sure = claimRows.filter((r) => r.p < 0.3 || r.p > 0.7);
const boxes = rows.filter((r) => r.type === "arrival_box");
const msAll = boxes.map((b) => b.ms).sort((a, b) => a - b);
lines.push("", `- overall ${claimRows.filter(ok).length}/${claimRows.length} right; Brier ${brier.toFixed(3)}`);
lines.push(`- outside the 0.3–0.7 band: ${sure.filter(ok).length}/${sure.length} right; inside it (would go to a person): ${unsure.length}`);
lines.push(`- Box on the actual-arrival field: median IoU ${boxes.map((b) => b.iou).sort((a, b) => a - b)[Math.floor(boxes.length / 2)].toFixed(2)}, IoU >= 0.5 in ${boxes.filter((b) => b.iou >= 0.5).length}/${boxes.length}`);
lines.push(`- ${N} requests (9 questions each): ${((Date.now() - t0) / 1000).toFixed(1)} s total incl. rendering; request p50 ${msAll[Math.floor(msAll.length / 2)]} ms; ${tokens} input tokens ≈ $${((tokens / 1e6) * 0.042).toFixed(4)}`);
const wrong = claimRows.filter((r) => !ok(r));
if (wrong.length) lines.push(`- wrong: ${wrong.map((r) => `pass ${r.pass} ${r.type} "${r.text}" p=${r.p.toFixed(2)}`).join("; ")}`);
console.log(lines.join("\n"));
writeFileSync(new URL("IMAGE-CLAIMS-EVAL.md", here), lines.join("\n") + "\n");
writeFileSync(`${dir}rows.json`, JSON.stringify(rows, null, 2));
