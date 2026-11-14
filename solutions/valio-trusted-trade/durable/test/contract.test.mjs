import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePayment,normalizeRefund,DemoLedgerError} from '../index.mjs';

const approved=Object.freeze({orderId:'orderA',idempotencyKey:'order_key_AAAA',
  buyerAccount:'demo:buyer:wallet',totalCents:100,
  allocations:[{supplierId:'farm-b',amountCents:40},{supplierId:'farm-a',amountCents:60}],
  verifiedQuoteBodyDigest:'a'.repeat(64),approvedProposalDigest:'b'.repeat(64)});

test('payment fingerprint ignores supplier input order, fixes EUR and locks exact cents',()=>{
  const a=normalizePayment(approved);
  const b=normalizePayment({...approved,allocations:[...approved.allocations].reverse()});
  assert.equal(a.intentDigest,b.intentDigest);
  assert.deepEqual(a.allocations.map(x=>x.supplierId),['farm-a','farm-b']);
  assert.equal(a.currency,'EUR');
  assert.equal(a.totalCents,100);
});
test('negative, decimal, overflow, duplicate payee and mismatched cents fail closed',()=>{
  for(const invalid of [
    {...approved,totalCents:99},
    {...approved,totalCents:100.5},
    {...approved,totalCents:Number.MAX_SAFE_INTEGER+1},
    {...approved,allocations:[{supplierId:'farm-a',amountCents:60},{supplierId:'farm-a',amountCents:40}]},
    {...approved,allocations:[{supplierId:'farm-a',amountCents:-1},{supplierId:'farm-b',amountCents:101}]},
    {...approved,buyerAccount:'not-the-buyer'},
    {...approved,verifiedQuoteBodyDigest:'unverified'},
    {...approved,externalTransfer:true}
  ])assert.throws(()=>normalizePayment(invalid),DemoLedgerError);
});
test('refund accepts only order and durable idempotency key',()=>{
  const r=normalizeRefund({orderId:'orderA',idempotencyKey:'refund_key_AAAA'});
  assert.equal(r.orderId,'orderA');assert.match(r.intentDigest,/^[a-f0-9]{64}$/);
  assert.throws(()=>normalizeRefund({orderId:'orderA',idempotencyKey:'refund_key_AAAA',amountCents:1}),DemoLedgerError);
});
test('upstream digest format is not mistaken for a verified signature',()=>{
  const x=normalizePayment(approved);
  assert.equal(typeof x.verifiedQuoteBodyDigest,'string');
  assert.equal(Object.hasOwn(x,'signatureVerified'),false);
});
