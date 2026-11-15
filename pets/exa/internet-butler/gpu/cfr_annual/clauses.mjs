#!/usr/bin/env node
// CFR-Annual, stage 2: amount-bearing clauses per section-year with the shipped extractor (amountClauses),
// so the dataset and the product agree on what a clause and an amount are.
// Usage: node --experimental-strip-types clauses.mjs sections-focused.jsonl.gz clauses-focused.jsonl.gz
import { createReadStream, createWriteStream } from "node:fs";
import { createGunzip, createGzip } from "node:zlib";
import { createInterface } from "node:readline";
import { createHash } from "node:crypto";
import { amountClauses, template } from "../../src/timetravel/timetravel.ts";
import { extractQuantities } from "../../src/warrant/lanes.ts";

const [inFile, outFile] = process.argv.slice(2);
const out = createGzip();
out.pipe(createWriteStream(outFile));
const rl = createInterface({ input: createReadStream(inFile).pipe(createGunzip()), crlfDelay: Infinity });
const sha1 = (s) => createHash("sha1").update(s).digest("hex").slice(0, 16);
let sections = 0, clauses = 0;
for await (const line of rl) {
  if (!line) continue;
  const s = JSON.parse(line);
  sections++;
  const cs = amountClauses(s.text);
  cs.forEach((c, i) => {
    const parts = c.split(" … ");
    const own = parts.at(-1);
    const qs = extractQuantities(own);
    const q = qs.find((x) => x.kind === "money") ?? qs.find((x) => x.kind === "percent");
    if (!q) return;
    const tpl = template(own);
    clauses++;
    out.write(JSON.stringify({
      title: s.title, year: s.year, edition: s.edition, part: s.part, section: s.section, subject: s.subject,
      clause_idx: i, context: parts.slice(0, -1).join(" … "), clause: own, amount_text: q.text, amount_value: q.value,
      unit: q.unit, kind: q.kind, n_amounts: qs.filter((x) => x.kind === "money" || x.kind === "percent").length,
      template: tpl, series_id: sha1(`${s.title}|${s.section}|${template(parts.slice(0, -1).join(" … "))}|${tpl}`), source_url: s.source_url, source_sha256: s.source_sha256,
    }) + "\n");
  });
  if (sections % 20000 === 0) console.error(`${sections} sections, ${clauses} clauses`);
}
out.end();
console.log(JSON.stringify({ sections, clauses }));
