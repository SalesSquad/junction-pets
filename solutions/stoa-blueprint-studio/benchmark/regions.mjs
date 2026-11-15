/** Offline box scoring. Ground truth must be independently annotated; never derive it from predictions. */
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

function validate(r) {
  if (!r || !/^[a-f0-9]{64}$/.test(r.sourceSha256) || !Number.isInteger(r.page) || r.page < 1 ||
      !Array.isArray(r.box) || r.box.length !== 4 || !r.box.every(Number.isFinite) || r.box[2] <= r.box[0] || r.box[3] <= r.box[1]) {
    throw new Error('Each region needs sourceSha256, a 1-based page and a positive [xMin,yMin,xMax,yMax] box in the same source coordinate system.');
  }
}
export function boxIoU(a, b) {
  validate(a); validate(b);
  if (a.sourceSha256 !== b.sourceSha256 || a.page !== b.page) return 0;
  const [ax,ay,az,aw] = a.box, [bx,by,bz,bw] = b.box;
  const intersection = Math.max(0,Math.min(az,bz)-Math.max(ax,bx))*Math.max(0,Math.min(aw,bw)-Math.max(ay,by));
  return intersection / ((az-ax)*(aw-ay)+(bz-bx)*(bw-by)-intersection);
}

/** Maximum-cardinality one-to-one matching at the given IoU threshold. Duplicate predictions count against precision. */
export function scoreRegions(cases, threshold = 0.5) {
  if (!Array.isArray(cases) || cases.length > 10000 || !Number.isFinite(threshold) || threshold <= 0 || threshold > 1) throw new Error('Invalid region evaluation input.');
  let predicted = 0, expected = 0, matched = 0, iouSum = 0;
  const results = cases.map(c => {
    if (!Array.isArray(c.expected) || !Array.isArray(c.predicted) || c.expected.length > 200 || c.predicted.length > 200) throw new Error('Use at most 200 expected and predicted boxes per case.');
    c.expected.forEach(validate); c.predicted.forEach(validate);
    const scores = c.predicted.map(p => c.expected.map(e => boxIoU(p,e)));
    const owner = new Map();
    const visit = (p, seen) => {
      const choices = scores[p].map((iou,e)=>({iou,e})).filter(x=>x.iou>=threshold).sort((a,b)=>b.iou-a.iou);
      for (const {e} of choices) {
        if (seen.has(e)) continue; seen.add(e);
        if (!owner.has(e) || visit(owner.get(e),seen)) { owner.set(e,p); return true; }
      }
      return false;
    };
    c.predicted.forEach((_,p)=>visit(p,new Set()));
    const pairs = [...owner].map(([e,p])=>({expected:e,predicted:p,iou:scores[p][e]}));
    predicted += c.predicted.length; expected += c.expected.length; matched += pairs.length;
    iouSum += pairs.reduce((s,p)=>s+p.iou,0);
    return {id:c.id??null,expected:c.expected.length,predicted:c.predicted.length,matched:pairs.length,pairs};
  });
  return { threshold, expected, predicted, matched, precision:predicted?matched/predicted:null,
    recall:expected?matched/expected:null, meanMatchedIoU:matched?iouSum/matched:null,
    missingRegions:expected-matched, extraRegions:predicted-matched, cases:results,
    method:'maximum-cardinality matching at threshold; mean IoU is over selected matches, not maximum-weight matching' };
}
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const path = process.argv[2];
  if (!path) throw new Error('Usage: node benchmark/regions.mjs <independently-labelled-regions.json>');
  const raw = await readFile(path);
  if (raw.length > 8*1024*1024) throw new Error('Region evaluation JSON exceeds 8 MiB.');
  const input = JSON.parse(raw);
  console.log(JSON.stringify(scoreRegions(input.cases,input.threshold??0.5),null,2));
}
