// Offline data validation only. Caller declarations do not authenticate evidence.
const fields = ['workload','kind','sceneCount','objectCount','inputDigest','width','height',
  'precision','quality','hardware','software','timingScope','warmup','repeats','unit',
  'timings','evidence','provenance'];
const textFields = ['workload','quality','hardware','software','timingScope','provenance'];
const equalFields = fields.filter(k => !['hardware','timings','provenance'].includes(k));
function valid(r) {
  if (!r || Object.getPrototypeOf(r)!==Object.prototype ||
      Reflect.ownKeys(r).length!==fields.length ||
      fields.some(k => !Object.hasOwn(r,k) || !('value' in Object.getOwnPropertyDescriptor(r,k)))) return false;
  if (textFields.some(k => typeof r[k]!=='string' || !r[k].trim() || r[k].length>300)) return false;
  if (!['3d-render','gaussian-splat'].includes(r.kind) || !['fp16','fp32','fp64'].includes(r.precision) ||
      !['authored-estimate','supplied-measurement'].includes(r.evidence) || r.unit!=='ms' ||
      typeof r.inputDigest!=='string' || !/^[a-f0-9]{64}$/.test(r.inputDigest)) return false;
  for (const k of ['sceneCount','objectCount','width','height','repeats','warmup'])
    if (!Number.isSafeInteger(r[k]) || r[k] < (k==='warmup'?0:1)) return false;
  if (!Array.isArray(r.timings) || r.timings.length!==r.repeats || r.repeats>10000) return false;
  for(let i=0;i<r.timings.length;i++)
    if (!Object.hasOwn(r.timings,i) || typeof r.timings[i]!=='number' ||
        !Number.isFinite(r.timings[i])) return false;
  if (r.timings.some(t => t<2.2250738585072014e-308)) return false;
  return Number.isFinite(r.timings.reduce((a,b)=>a+b,0));
}
export function compare(baseline, candidate) {
  const reject = reason => ({comparable:false, reason, ratio:null, measuredPerformanceVerified:false});
  if (!valid(baseline) || !valid(candidate)) return reject('invalid-row');
  for(const key of equalFields) if(baseline[key]!==candidate[key]) return reject(`mismatch:${key}`);
  const ratio = baseline.timings.reduce((a,b)=>a+b,0) / candidate.timings.reduce((a,b)=>a+b,0);
  if (!Number.isFinite(ratio) || ratio<=0) return reject('invalid-ratio');
  return {comparable:true, ratio, basis:baseline.evidence, provenance:'unverified', measuredPerformanceVerified:false};
}
