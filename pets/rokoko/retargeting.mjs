// Offline declared-data comparison, never authorization or animation validation.
function plain(value, seen = new Set()) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (typeof value !== 'object' || seen.has(value)) throw Error('non-JSON data');
  const array = Array.isArray(value);
  if (Object.getPrototypeOf(value) !== (array ? Array.prototype : Object.prototype)) throw Error('prototype');
  seen.add(value);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (array && (keys.length !== descriptors.length.value + 1 || !keys.every(k => k === 'length' || (typeof k === 'string' && /^(0|[1-9][0-9]*)$/.test(k) && Number(k) < descriptors.length.value)))) throw Error('array shape');
  for (const key of keys) {
    if (typeof key !== 'string') throw Error('symbol');
    const d = descriptors[key];
    if (!Object.hasOwn(d,'value') || (!(array && key === 'length') && !d.enumerable)) throw Error('accessor or hidden property');
    if (!(array && key === 'length')) plain(d.value,seen);
  }
  seen.delete(value);
}
function record(v, required, optional = []) {
  if (!v || Array.isArray(v) || typeof v !== 'object' || required.some(k=>!Object.hasOwn(v,k)) || Object.keys(v).some(k=>!required.includes(k)&&!optional.includes(k))) throw Error('record keys');
}
const id = v => typeof v === 'string' && /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/.test(v);
function ids(v) { if (!Array.isArray(v) || !v.length || !v.every(id)) throw Error('IDs'); }
const meters = {m:1,cm:0.01,mm:0.001};

export function checkRetargeting(input) {
  try {
    plain(input);
    record(input,['source','target','mapping','exportFormat'],['sourceDistance']);
    for (const side of [input.source,input.target]) {
      record(side,['bones','handedness','upAxis','units','formats']);
      ids(side.bones); ids(side.formats);
      for (const [key,values] of [['handedness',['left','right','unknown']],['upAxis',['X','Y','Z','unknown']],['units',['m','cm','mm','unknown']]]) if (!values.includes(side[key])) throw Error(key);
    }
    if (!id(input.exportFormat) || !Array.isArray(input.mapping)) throw Error('mapping/format');
    if (Object.hasOwn(input,'sourceDistance') && (typeof input.sourceDistance !== 'number' || input.sourceDistance < 0)) throw Error('distance');
    for (const pair of input.mapping) {record(pair,['source','target']);if(!id(pair.source)||!id(pair.target)) throw Error('bone ID');}
    const issues = [], unknown = [];
    const {source:s,target:t} = input;
    for (const [name,side] of [['source',s],['target',t]]) for (const key of ['bones','formats']) if (new Set(side[key]).size !== side[key].length) issues.push(`${name}:duplicate-${key}`);
    const sources = new Set(), targets = new Set();
    for (const pair of input.mapping) {
      if (sources.has(pair.source) || targets.has(pair.target)) issues.push('ambiguous-mapping');
      sources.add(pair.source); targets.add(pair.target);
      if (!s.bones.includes(pair.source) || !t.bones.includes(pair.target)) issues.push('nonexistent-bone');
    }
    if (s.bones.some(b=>!sources.has(b)) || t.bones.some(b=>!targets.has(b))) issues.push('missing-mapping');
    for (const key of ['handedness','upAxis','units']) {
      if (s[key] === 'unknown' || t[key] === 'unknown') unknown.push(`unknown-${key}`);
      else if (key !== 'units' && s[key] !== t[key]) issues.push(`mismatch-${key}`);
    }
    if (!s.formats.includes(input.exportFormat) || !t.formats.includes(input.exportFormat)) issues.push('export-format-mismatch');
    const status = issues.length ? 'incompatible' : unknown.length ? 'unknown' : 'compatible-declared';
    const result = {status,issues:[...new Set([...issues,...unknown])],scope:'synthetic declarations only; no animation/export quality or authorization proof'};
    if (status === 'compatible-declared') {
      result.scaleFactor = meters[s.units] / meters[t.units];
      if (Object.hasOwn(input,'sourceDistance')) {
        const distance = input.sourceDistance * result.scaleFactor;
        if (!Number.isFinite(distance)) return {status:'malformed',issues:['conversion-overflow']};
        result.targetDistance = distance;
      }
    }
    return result;
  } catch { return {status:'malformed',issues:['invalid-plain-data-contract']}; }
}
