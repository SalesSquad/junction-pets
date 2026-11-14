import test from 'node:test';
import assert from 'node:assert/strict';
import {createWalWorkload,payment,refund} from '../plan.mjs';

test('10k is 5000 unique payment intents plus 5000 distinct refunds, never a repeated green tuple',()=>{
  const p=createWalWorkload({requests:10000,seed:20261114});
  assert.equal(p.orders,5000);assert.equal(p.pays.length,5000);assert.equal(p.refunds.length,5000);
  assert.equal(new Set(p.pays.map(x=>x.terms.orderId)).size,5000);
  assert.equal(new Set([...p.pays,...p.refunds].map(x=>x.terms.idempotencyKey)).size,10000);
  for(const t of p.pays){
    assert.equal(t.terms.totalCents,100);
    assert.equal(t.terms.allocations.reduce((s,a)=>s+a.amountCents,0),100);
    assert.match(t.terms.verifiedQuoteBodyDigest,/^[a-f0-9]{64}$/);
    assert.match(t.terms.approvedProposalDigest,/^[a-f0-9]{64}$/);
  }
});
test('workload seed controls exact fixture plan and digest',()=>{
  const a=createWalWorkload({requests:200,seed:1});
  const b=createWalWorkload({requests:200,seed:1});
  const c=createWalWorkload({requests:200,seed:2});
  assert.deepEqual(a,b);assert.notEqual(a.planDigest,c.planDigest);
});
test('bounded request/seed validation refuses unsafe or ambiguous load',()=>{
  for(const bad of [0,199,201,10001,Infinity,NaN])
    assert.throws(()=>createWalWorkload({requests:bad}),RangeError);
  assert.throws(()=>createWalWorkload({requests:200,seed:-1}),RangeError);
  assert.equal(payment('wal_test','key_test_01234',1,[{supplierId:'farm-a',amountCents:1}]).kind,'pay');
  assert.equal(refund('wal_test','refund_key_01234').kind,'refund');
});
