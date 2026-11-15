/** Strict subset used by the unchanged buyer-terms verifier; unsupported shapes fail closed. */
const fail=message=>{throw Object.assign(new Error(message??'Strict buyer assertion failed'),{code:'ERR_ASSERTION'});};
function ok(value,message){if(!value)fail(message);}
function equal(actual,expected,message){if(!Object.is(actual,expected))fail(message);}
function deepEqual(actual,expected,message){
  const seen=new Set();let nodes=0;
  const same=(left,right,depth=0)=>{
    if(++nodes>100000||depth>100)return false;
    if(Object.is(left,right))return true;
    if(left===null||right===null||typeof left!=='object'||typeof right!=='object')return false;
    const prototype=Object.getPrototypeOf(left);
    if(prototype!==Object.getPrototypeOf(right)||![Object.prototype,Array.prototype,null].includes(prototype)||seen.has(left))return false;
    if(Array.isArray(left)!==Array.isArray(right)||(Array.isArray(left)&&left.length!==right.length))return false;
    const a=Reflect.ownKeys(left),b=Reflect.ownKeys(right);
    if(a.some(key=>typeof key!=='string')||b.some(key=>typeof key!=='string')||a.length!==b.length)return false;
    seen.add(left);const result=a.every(key=>Object.hasOwn(right,key)&&same(left[key],right[key],depth+1));seen.delete(left);return result;
  };
  if(!same(actual,expected))fail(message);
}
export default Object.freeze(Object.assign(ok,{ok,equal,deepEqual}));
