// Offline data validation only. Caller declarations do not authenticate evidence.
const fields = ['workload','kind','sceneCount','objectCount','inputDigest','width','height',
  'precision','quality','hardware','software','timingScope','warmup','repeats','unit',
  'timings','evidence','provenance'];
const textFields = ['workload','quality','hardware','software','timingScope','provenance'];
const equalFields = fields.filter(k => !['hardware','timings','provenance'].includes(k));
function validated(r) {
  if (!r || Object.getPrototypeOf(r)!==Object.prototype ||
      Reflect.ownKeys(r).length!==fields.length ||
      fields.some(k => !Object.hasOwn(r,k) || !('value' in Object.getOwnPropertyDescriptor(r,k)))) return false;
  // Snapshot own data values; subsequent validation never reads caller properties.
  const data = {};
  for (const key of fields) data[key] = Object.getOwnPropertyDescriptor(r,key).value;
  r = data;
  if (textFields.some(k => typeof r[k]!=='string' || !r[k].trim() || r[k].length>300)) return false;
  if (!['3d-render','gaussian-splat'].includes(r.kind) || !['fp16','fp32','fp64'].includes(r.precision) ||
      !['authored-estimate','supplied-measurement'].includes(r.evidence) || r.unit!=='ms' ||
      typeof r.inputDigest!=='string' || !/^[a-f0-9]{64}$/.test(r.inputDigest)) return false;
  for (const k of ['sceneCount','objectCount','width','height','repeats','warmup'])
    if (!Number.isSafeInteger(r[k]) || r[k] < (k==='warmup'?0:1)) return false;
  const timings = r.timings;
  if (!Array.isArray(timings) || Object.getPrototypeOf(timings)!==Array.prototype || r.repeats>10000) return false;
  const length = Object.getOwnPropertyDescriptor(timings,'length');
  if (!length || !('value' in length) || length.value!==r.repeats ||
      Reflect.ownKeys(timings).length!==r.repeats+1) return false;
  let sum=0;
  for(let i=0;i<r.repeats;i++) {
    const sample = Object.getOwnPropertyDescriptor(timings,String(i));
    if (!sample || !('value' in sample)) return false;
    const value=sample.value;
    if (typeof value!=='number' || !Number.isFinite(value) || value<2.2250738585072014e-308) return false;
    sum+=value;
  }
  if (!Number.isFinite(sum)) return false;
  return {data:r,sum};
}
export function compare(baseline, candidate) {
  const reject = reason => ({comparable:false, reason, ratio:null, measuredPerformanceVerified:false});
  const first=validated(baseline), second=validated(candidate);
  if (!first || !second) return reject('invalid-row');
  baseline=first.data; candidate=second.data;
  for(const key of equalFields) if(baseline[key]!==candidate[key]) return reject(`mismatch:${key}`);
  const ratio = first.sum / second.sum;
  if (!Number.isFinite(ratio) || ratio<=0) return reject('invalid-ratio');
  return {comparable:true, ratio, basis:baseline.evidence, provenance:'unverified', measuredPerformanceVerified:false};
}
