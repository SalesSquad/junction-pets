import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {analyze,POLICY} from '../public/detector.mjs';
import {corpus,SEEDS,FAMILIES} from './ood.mjs';
export const SOURCE_BASE='27fb74b999f41718237958e03404390350f75a65';
export const hash=value=>createHash('sha256').update(value).digest('hex');
export function proportion(numerator,denominator){
 if(!Number.isInteger(numerator)||!Number.isInteger(denominator)||numerator<0||denominator<numerator)throw new Error('Invalid proportion');
 if(!denominator)return {numerator,denominator,value:null,wilson95:null};
 const z=1.959963984540054,p=numerator/denominator,d=1+z*z/denominator,center=(p+z*z/(2*denominator))/d,half=z*Math.sqrt(p*(1-p)/denominator+z*z/(4*denominator*denominator))/d;
 return {numerator,denominator,value:p,wilson95:{low:numerator===0?0:Math.max(0,center-half),high:numerator===denominator?1:Math.min(1,center+half)}};
}
export function metrics(rows,method='radar'){
 let tp=0,fp=0,tn=0,fn=0;for(const r of rows){if(r.truth){if(r[method])tp++;else fn++;}else{if(r[method])fp++;else tn++;}}
 return {tp,fp,tn,fn,precision:proportion(tp,tp+fp),falsePositiveRate:proportion(fp,fp+tn),recall:proportion(tp,tp+fn)};
}
// Same deliberately naive comparator as M2, implemented locally to avoid fixture imports.
export function baseline(events){const counts=new Map();for(const e of events){const text=e.text.toLowerCase().trim();counts.set(text,(counts.get(text)||0)+1);if(/\b(shocking|urgent|exposed)\b/i.test(text))return true;}return [...counts.values()].some(n=>n>=3);}
export async function report(){
 const sourceFiles=['public/detector.mjs','stress/ood.mjs','stress/report.mjs'];
 const sources=Object.fromEntries(await Promise.all(sourceFiles.map(async path=>[path,hash(await readFile(new URL(`../${path}`,import.meta.url)))])));
 const {cases,labels}=corpus(),errors=[],rows=[];
 for(const c of cases){const findings=analyze(c.events).findings,flagged=findings.filter(f=>f.review),truth=labels[c.id].harmful,predicted=flagged.length>0;
 rows.push({id:c.id,family:c.family,truth,radar:predicted,baseline:baseline(c.events)});
 if(predicted!==truth){const family=FAMILIES.find(f=>f.id===c.family),lead=flagged[0]||findings[0];errors.push({id:c.id,family:c.family,error:truth?'false negative':'false positive',reason:truth?'Authored concealed manipulation missed; inspect timing, group fragmentation and supplied counterevidence.':'Authored legitimate activity flagged; coordination does not establish deceptive intent.',score:lead.score,status:lead.status,signals:lead.signals.filter(s=>s.points!==0).map(s=>({key:s.key,points:s.points,eventIds:s.eventIds})),counterevidence:family.counterevidence,nextReviewerAction:family.action});}
 }
 const summarize=rs=>({cases:rs.length,benign:rs.filter(r=>!r.truth).length,harmful:rs.filter(r=>r.truth).length,radar:metrics(rs),baseline:metrics(rs,'baseline')});
 const cohorts=FAMILIES.map(f=>({family:f.id,...summarize(rows.filter(r=>r.family===f.id))}));
 const total=summarize(rows),delta={};for(const key of ['precision','falsePositiveRate','recall'])delta[key]=total.radar[key].value===null||total.baseline[key].value===null?null:total.radar[key].value-total.baseline[key].value;
 return {mode:'OFFLINE_SYNTHETIC_OOD',sourceBase:SOURCE_BASE,sources,sourceSHA256:hash(JSON.stringify(sources)),generatorSHA256:sources['stress/ood.mjs'],policy:POLICY,seeds:SEEDS,prng:'Mulberry32 uint32',unit:'scenario: any group receives analyst review',limitations:'Authored synthetic OOD relative to the M2 generator, not independent external validation, licensed observations or representative data. Intent is stipulated outside detector inputs. Wilson 95% intervals describe binomial proportions only; correlated authored cases and fixed seeds do not support population inference. Rule points are not probabilities. No tuning, automated enforcement or field accuracy claim.',observationsSHA256:hash(JSON.stringify(cases)),labelsSHA256:hash(JSON.stringify(labels)),samples:cases.filter(c=>c.id.endsWith('-00')).map(c=>({id:c.id,caseSHA256:hash(JSON.stringify(c)),labelSHA256:hash(JSON.stringify(labels[c.id]))})),...total,comparison:{before:'naive repeated-message / loaded-keyword rule',after:'unchanged radar-v1 policy (not an OOD-fitted revision)',deltaAfterMinusBefore:delta},cohorts,errorFamilies:FAMILIES.map(f=>({family:f.id,falsePositives:errors.filter(e=>e.family===f.id&&e.error==='false positive').length,falseNegatives:errors.filter(e=>e.family===f.id&&e.error==='false negative').length,examples:errors.filter(e=>e.family===f.id).slice(0,3).map(e=>e.id),counterevidence:f.counterevidence,nextReviewerAction:f.action})).sort((a,b)=>(b.falsePositives+b.falseNegatives)-(a.falsePositives+a.falseNegatives)||a.family.localeCompare(b.family)),errors};
}
// The browser gets only aggregate counts and a few diagnostic IDs, never cases/truth maps.
export function aggregate(r){const {errors,samples,...safe}=r;return {...safe,errorCount:errors.length};}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)console.log(JSON.stringify(await report(),null,2));
