#!/usr/bin/env node
// Split a run2 result into judge batches for the Haiku judge swarm (+ a shuffled re-judge sample).
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from "node:fs";
const here = new URL(".", import.meta.url);
const file = readdirSync(new URL("results/", here)).filter((f) => f.startsWith("run2-") && f.endsWith(".json")).sort().at(-1);
const run = JSON.parse(readFileSync(new URL(`results/${file}`, here), "utf8"));
const spec = JSON.parse(readFileSync(new URL("errands.json", here), "utf8"));
const byId = Object.fromEntries(spec.errands.map((e) => [e.id, e]));
const okRows = run.rows.filter((r) => !r.error);
const items = okRows.flatMap((r) =>
  r.top.map((t, rank) => ({
    key: `${r.errand}|${r.arm}|${rank}`,
    jurisdiction: r.jurisdiction,
    question: byId[r.errand].question,
    reference_rule: byId[r.errand].premise,
    url: t.url,
    title: t.title,
    highlights: t.highlights.join("\n…\n").slice(0, 1600),
  })),
);
// Judges see items in a shuffled order without the arm name, so they cannot favour an arm.
let seed = 7;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
const shuffled = items.map((x) => [rand(), x]).sort((a, b) => a[0] - b[0]).map(([, x]) => x);
const blind = shuffled.map(({ key, ...rest }, i) => ({ item: i, ...rest }));
const keyMap = shuffled.map((x) => x.key);
mkdirSync(new URL("judge/", here), { recursive: true });
const N = 16;
const size = Math.ceil(blind.length / N);
for (let b = 0; b < N; b++) writeFileSync(new URL(`judge/batch${b}.json`, here), JSON.stringify(blind.slice(b * size, (b + 1) * size), null, 1));
// Re-judge sample: 60 random items for inter-rater agreement.
const sample = blind.filter((_, i) => i % Math.floor(blind.length / 60) === 0).slice(0, 60);
writeFileSync(new URL("judge/rejudge.json", here), JSON.stringify(sample, null, 1));
writeFileSync(new URL("judge/keymap.json", here), JSON.stringify({ run: file, keys: keyMap }));
console.log(`${file}: ${blind.length} items -> ${N} batches of ~${size}; rejudge ${sample.length}`);
