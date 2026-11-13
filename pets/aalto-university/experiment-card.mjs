/** Offline synthetic plan checker. No data collection, inference or authorization.
 * Accept only ordinary JSON-like values; inspect descriptors before reading values.
 * Proxies are outside this data contract (JS cannot inspect them without traps).
 */
function plain(value, depth=0) {
  if(depth>12) throw Error('depth');
  if(value===null || typeof value==='string' || typeof value==='boolean') return value;
  if(typeof value==='number' && Number.isFinite(value)) return value;
  if(typeof value!=='object' || value===null) throw Error('type');
  const array=Array.isArray(value);
  if(Object.getPrototypeOf(value)!==(array?Array.prototype:Object.prototype)) throw Error('prototype');
  const descriptors=Object.getOwnPropertyDescriptors(value);
  const keys=Reflect.ownKeys(descriptors);
  if(keys.some(key=>typeof key!=='string')) throw Error('symbol');
  if(array) {
    const length=descriptors.length.value;
    if(length>100 || keys.length!==length+1) throw Error('array');
    const result=[];
    for(let i=0;i<length;i++) {
      const descriptor=descriptors[String(i)];
      if(!descriptor || !Object.hasOwn(descriptor,'value') || !descriptor.enumerable) throw Error('array-entry');
      result.push(plain(descriptor.value,depth+1));
    }
    return result;
  }
  if(keys.length>30) throw Error('keys');
  const result=Object.create(null);
  for(const key of keys) {
    const descriptor=descriptors[key];
    if(!Object.hasOwn(descriptor,'value') || !descriptor.enumerable) throw Error('accessor');
    result[key]=plain(descriptor.value,depth+1);
  }
  return result;
}
const text=value=>typeof value==='string' && value.trim().length>0 && value.length<=2000;
const texts=value=>Array.isArray(value) && value.length>0 && value.every(text);
const shape=(value,keys)=>value!==null && typeof value==='object' && !Array.isArray(value) && Object.keys(value).length===keys.length && keys.every(key=>Object.hasOwn(value,key));
const count=value=>Number.isSafeInteger(value) && value>0 && value<=1000000;

export function checkExperimentCard(input) {
  const rejected=()=>({status:'rejected',claimType:null,causalFinding:false,authorization:false,issues:['invalid-or-incomplete-card']});
  let card;
  try {card=plain(input);} catch {return rejected();}
  if(!shape(card,['claimType','hypothesis','outcome','control','confounds','decision','uncertainty','sample'])) return rejected();
  if(!['association','hypothetical-causal','designed-experiment'].includes(card.claimType) || !text(card.hypothesis)) return rejected();
  if(!shape(card.outcome,['metric','unit','window']) || !Object.values(card.outcome).every(text)) return rejected();
  if(!shape(card.control,['comparison','allocation']) || !text(card.control.comparison) || card.control.allocation!=='randomized') return rejected();
  if(!texts(card.confounds) || !texts(card.uncertainty)) return rejected();
  if(!shape(card.sample,['treatment','control']) || !Object.values(card.sample).every(count)) return rejected();
  const decision=card.decision;
  if(!shape(decision,['preregistered','minimumDifference','direction','rule']) || decision.preregistered!==true || typeof decision.minimumDifference!=='number' || decision.minimumDifference<0 || !['increase','decrease'].includes(decision.direction) || !text(decision.rule)) return rejected();
  return {status:card.claimType==='designed-experiment'?'complete-plan':'claim-only',claimType:card.claimType,causalFinding:false,authorization:false,issues:[]};
}
