import assert from 'node:assert/strict';
import buyerAssert from '../assert.mjs';
buyerAssert.ok(true);buyerAssert.equal(7,7);buyerAssert.deepEqual({b:2,a:[1,{value:false}]},{a:[1,{value:false}],b:2});
for(const operation of [()=>buyerAssert.ok(false),()=>buyerAssert.equal(0,-0),()=>buyerAssert.deepEqual([1,2],[2,1]),
  ()=>buyerAssert.deepEqual({volume:1000},{volume:999}),()=>buyerAssert.deepEqual({value:undefined},{}),
  ()=>buyerAssert.deepEqual(Object.assign(Object.create(null),{value:1}),{value:1}),()=>buyerAssert.deepEqual(new Map(),{})]){
  assert.throws(operation,{code:'ERR_ASSERTION'});
}
console.log(JSON.stringify({check:'strict-browser-buyer-assert-subset',outcome:'PASS',mismatchRefusals:7,keyOrderIndependent:true,prototypeMismatchRefused:true}));
