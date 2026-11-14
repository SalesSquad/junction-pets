import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const hash=value=>createHash('sha256').update(value).digest('hex');
import {pathToFileURL} from 'node:url';
import {analyze,POLICY} from './public/detector.mjs';
import {development} from './public/scenarios.mjs';
import {heldOut} from './fixtures/held-out.mjs';
// Deliberately naive: flags a repeated message (>=3) OR a loaded keyword.
export function baseline(events) {const counts=new Map();for(const e of events){const t=e.text.toLowerCase().trim();counts.set(t,(counts.get(t)||0)+1);if(/\b(shocking|urgent|exposed)\b/i.test(t))return true;}return [...counts.values()].some(n=>n>=3);}
export function metrics(rows) {let tp=0,fp=0,tn=0,fn=0;for(const {truth,predicted} of rows){if(truth){if(predicted)tp++;else fn++;}else{if(predicted)fp++;else tn++;}}const rate=(n,d)=>({numerator:n,denominator:d,value:d?n/d:null});return {tp,fp,tn,fn,precision:rate(tp,tp+fp),falsePositiveRate:rate(fp,fp+tn),recall:rate(tp,tp+fn)};}
export async function benchmark() {
 const result={mode:'SYNTHETIC',unit:'scenario-level: at least one finding flagged',sourceBase:'b7a51ee7acc3b1923fa0506b31a0f2eafb56f402',detectorSHA256:hash(await readFile(new URL('./public/detector.mjs',import.meta.url))),policy:POLICY,limitations:'Tiny authored synthetic cases share a generator. Held-out parameters/labels are separate, not independently collected or statistically representative. Threshold fixed at 65; no held-out fitting. No production efficacy claim.',splits:{}};
 for(const [name,cases,file] of [['development',development,'development-labels.json'],['heldOut',heldOut,'held-out-labels.json']]) {
 const labels=JSON.parse(await readFile(new URL(`./fixtures/${file}`,import.meta.url),'utf8'));const rows=cases.map(c=>({id:c.id,truth:labels[c.id],radar:analyze(c.events).findings.some(f=>f.review),baseline:baseline(c.events)}));if(rows.some(r=>typeof r.truth!=='boolean'))throw new Error('Missing truth label');
 result.splits[name]={cases:rows.length,observationsSHA256:hash(JSON.stringify(cases)),labelsSHA256:hash(JSON.stringify(labels)),radar:metrics(rows.map(r=>({truth:r.truth,predicted:r.radar}))),baseline:metrics(rows.map(r=>({truth:r.truth,predicted:r.baseline}))),errors:rows.filter(r=>r.radar!==r.truth).map(r=>({id:r.id,error:r.truth?'false negative':'false positive'}))};
 }return result;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)console.log(JSON.stringify(await benchmark(),null,2));
