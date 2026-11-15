#!/usr/bin/env node
// UK-EU-Rates: focused point-in-time dataset of statutory amounts and time limits in UK and EU law.
// Each provision is read on two dates a year from the official point-in-time source (legislation.gov.uk,
// EUR-Lex consolidated versions via CELLAR); every row keeps the pinned URL. Chosen for tiers (age bands,
// distance and delay bands, debt-size bands, rent bands) and for amounts that change over time (wage rates,
// statutory payments, caps, UK261 moving from EUR to GBP).
// Usage: node --experimental-strip-types bench/datasets/uk_eu_rates.mjs [--from=2004] [--to=2026] [--out=bench/datasets/out/uk_eu_rates.jsonl.gz]
import { createWriteStream, mkdirSync } from "node:fs";
import { createGzip } from "node:zlib";
import { createHash } from "node:crypto";
import { lawOn } from "../../src/warrant/pointInTime.ts";
import { amountClauses, template } from "../../src/timetravel/timetravel.ts";
import { extractQuantities } from "../../src/warrant/lanes.ts";

const arg = (k, d) => process.argv.find((a) => a.startsWith(`--${k}=`))?.slice(k.length + 3) ?? d;
const from = Number(arg("from", "2004")), to = Number(arg("to", "2026"));
const outFile = arg("out", "bench/datasets/out/uk_eu_rates.jsonl.gz");
mkdirSync(outFile.replace(/\/[^/]+$/, ""), { recursive: true });

export const PROVISIONS = [
  ["UK", "uksi/1999/584/regulation/11", "National minimum wage, adult rate (1999 Regulations)"],
  ["UK", "uksi/1999/584/regulation/13", "National minimum wage, development and young worker rates (1999 Regulations)"],
  ["UK", "uksi/2015/621/regulation/4", "National living wage"],
  ["UK", "uksi/2015/621/regulation/4A", "National minimum wage, younger workers and apprentices"],
  ["UK", "ukpga/1992/4/section/157", "Statutory sick pay, weekly rate"],
  ["UK", "uksi/1986/1960/regulation/6", "Statutory maternity pay, weekly rate"],
  ["UK", "uksi/2002/2818/regulation/2", "Statutory paternity pay, weekly rate"],
  ["UK", "uksi/2002/2818/regulation/3", "Statutory adoption pay, weekly rate"],
  ["UK", "ukpga/1996/18/section/227", "Maximum amount of a week's pay (redundancy pay, basic award)"],
  ["UK", "ukpga/1996/18/section/124", "Unfair dismissal compensatory award cap"],
  ["UK", "ukpga/1996/18/section/31", "Guarantee pay daily limit"],
  ["UK", "uksi/2006/965/regulation/2", "Child benefit weekly rates"],
  ["UK", "ukpga/1998/20/section/5A", "Late payment of commercial debts, fixed sums by debt size"],
  ["UK", "ukpga/2019/4/schedule/1/paragraph/2", "Tenancy deposit cap (five or six weeks' rent)"],
  ["UK", "eur/2004/261/article/7", "UK261 flight compensation (retained Regulation 261/2004)"],
  ["UK", "ukpga/2007/3/section/35", "Income tax personal allowance"],
  ["UK", "ukpga/1994/23/schedule/1/paragraph/1", "VAT registration threshold"],
  ["EU", "32004R0261:7", "EU261 flight compensation"],
  ["EU", "32007R1371:17", "Rail passengers' compensation for delay (2007 Regulation)"],
  ["EU", "32021R0782:19", "Rail passengers' compensation for delay (2021 Regulation)"],
  ["EU", "32010R1177:19", "Sea and inland waterway passengers' compensation for delay"],
  ["EU", "32011R0181:19", "Bus and coach passengers' compensation for delay or cancellation"],
  ["EU", "32012R0531:7", "Roaming: wholesale voice charges (2012 Regulation)"],
  ["EU", "32022R0612:9", "Roaming: wholesale voice charges (2022 Regulation)"],
  ["EU", "32013R1407:3", "De minimis aid ceiling (2013 Regulation)"],
  ["EU", "32023R2831:3", "De minimis aid ceiling (2023 Regulation)"],
  ["EU", "32015R0751:3", "Interchange fee caps, consumer debit cards"],
];
const refOf = (j, id) => (j === "UK" ? { source: "ukleg", path: id } : { source: "eurlex", celex: id.split(":")[0], article: id.split(":")[1] });
const sha1 = (s) => createHash("sha1").update(s).digest("hex").slice(0, 16);
const dates = [];
for (let y = from; y <= to; y++) for (const md of ["01-15", "07-15"]) if (`${y}-${md}` <= new Date().toISOString().slice(0, 10)) dates.push(`${y}-${md}`);

const out = createGzip();
out.pipe(createWriteStream(outFile));
const jobs = PROVISIONS.flatMap(([j, id, label]) => dates.map((d) => ({ j, id, label, d })));
let next = 0, rows = 0, notInForce = 0, errors = 0;
await Promise.all(Array.from({ length: 3 }, async () => {
  while (next < jobs.length) {
    const { j, id, label, d } = jobs[next++];
    let law;
    try {
      law = await lawOn(refOf(j, id), d);
    } catch (e) {
      if (/^404/.test(e.message)) notInForce++;
      else errors++;
      continue;
    }
    for (const want of ["amount", "duration"]) {
      amountClauses(law.text, want).forEach((c, i) => {
        const parts = c.split(" … ");
        const own = parts.at(-1);
        const qs = extractQuantities(own);
        const q = want === "amount" ? qs.find((x) => x.kind === "money") ?? qs.find((x) => x.kind === "percent") : qs.find((x) => x.kind === "duration");
        if (!q) return;
        rows++;
        out.write(JSON.stringify({ jurisdiction: j, provision: id, label, date: d, url: law.url, want, clause_idx: i, context: parts.slice(0, -1).join(" … "), clause: own, amount_text: q.text, amount_value: q.value, unit: q.unit, kind: q.kind, template: template(own), series_id: sha1(`${id}|${want}|${template(parts.slice(0, -1).join(" … "))}|${template(own)}`) }) + "\n");
      });
    }
    if ((next % 100) === 0) console.error(`${next}/${jobs.length} rows ${rows}`);
  }
}));
out.end();
console.log(JSON.stringify({ provisions: PROVISIONS.length, dates: dates.length, rows, notInForce, errors }));
