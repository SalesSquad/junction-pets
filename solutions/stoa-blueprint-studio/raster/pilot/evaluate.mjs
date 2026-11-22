import {open} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {scoreRegions} from '../../benchmark/regions.mjs';
import {scan} from './scan.mjs';
import {checkScale, roomAnnotation} from './reading.mjs';

export async function evaluate(path, options = {}) {
  const handle = await open(path,'r');
  const buffer = Buffer.alloc(256_001);
  let length;
  try {
    if (!(await handle.stat()).isFile()) throw new Error('Expected a regular manifest file.');
    length = (await handle.read(buffer,0,buffer.length)).bytesRead;
  } finally { await handle.close(); }
  if (length === buffer.length) throw new Error('Manifest exceeds input limit.');
  const suite = JSON.parse(buffer.toString('utf8',0,length));
  if (!Array.isArray(suite.documents) || suite.documents.length > 32) throw new Error('Invalid manifest.');
  const rows = [], regions = [], scales = [];
  for (const document of suite.documents) {
    const page = await scan(resolve(dirname(path),document.file),document.page,options);
    if (page.sourceSha256 !== document.sha256) throw new Error('Fixture source digest mismatch.');
    if (!Array.isArray(document.queries) || document.queries.length > 50) throw new Error('Too many queries.');
    for (const query of document.queries) {
      if (typeof query.room !== 'string' || !(query.value === null ||
          (Number.isFinite(query.value) && query.value > 0))) throw new Error('Invalid expected annotation.');
      const result = roomAnnotation(page,query.room);
      const id = document.file + ':' + query.room;
      rows.push({id, required:query.required === true, expected:query.value, observed:result.value ?? null,
        correct:query.value === (result.value ?? null), reason:result.reason ?? null});
      if (query.boxes) {
        const expected = query.boxes.map(box => ({sourceSha256:page.sourceSha256,page:page.page,
          box:box.map((value,i) => value*(i%2 ? page.height : page.width))}));
        regions.push({id,expected,predicted:result.citations});
      }
    }
    for (const control of document.scaleCases ?? []) {
      const result = checkScale(page,control.controls);
      scales.push({id:control.id, expected:control.status, actual:result.status,
        correct:control.status === result.status, reason:result.reason ?? null});
    }
  }
  const positives = rows.filter(row => row.expected !== null);
  const negatives = rows.filter(row => row.expected === null);
  return {corpus:suite.corpus, annotation:{expected:positives.length, correct:positives.filter(r=>r.correct).length,
    unanswered:positives.filter(r=>r.observed === null).length, wrong:positives.filter(r=>r.observed !== null && !r.correct).length},
    abstention:{expected:negatives.length, correct:negatives.filter(r=>r.correct).length},
    regions:scoreRegions(regions), scales, rows};
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const path = process.argv.slice(2).find(arg=>arg !== '--baseline') ?? fileURLToPath(new URL('./fixtures/suite.json',import.meta.url));
  const report = await evaluate(path,{retry:!process.argv.includes('--baseline')});
  console.log(JSON.stringify(report,null,2));
  if (report.annotation.wrong || report.rows.some(row=>row.required && !row.correct) || report.abstention.expected !== report.abstention.correct ||
      report.scales.some(row=>!row.correct) || report.regions.matched !== report.regions.predicted) process.exitCode = 1;
}
