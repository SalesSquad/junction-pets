/** Deterministic WAL-recovery trade fixtures. All orders/approvals are fictional. */
import {createHash} from 'node:crypto';

const sha=x=>createHash('sha256').update(x).digest('hex');
const suppliers=['farm-a','farm-b','farm-c'];
export function flightApplicationNames(schema){
  if(typeof schema!=='string'||!/^j26_[a-f0-9]{20}$/.test(schema))
    throw new Error('Expected exact run-owned j26_20-hex schema for WAL flight correlation.');
  const marker=`j26wal_${schema.slice(4)}_`;
  return Array.from({length:8},(_,i)=>`${marker}wal_flight_${i}`);
}
export function payment(orderId,idempotencyKey,amountCents,allocations,seed=20261114) {
  return {kind:'pay',terms:{orderId,idempotencyKey,totalCents:amountCents,
    buyerAccount:'demo:buyer:wallet',allocations,
    verifiedQuoteBodyDigest:sha(`SYNTHETIC_QUOTE_ONLY:${seed}:${orderId}`),
    approvedProposalDigest:sha(`SYNTHETIC_APPROVAL_ONLY:${seed}:${orderId}`)}};
}
export function refund(orderId,idempotencyKey) {
  return {kind:'refund',terms:{orderId,idempotencyKey}};
}
export function createWalWorkload({requests=10000,seed=20261114}={}) {
  if(!Number.isSafeInteger(requests)||requests<200||requests>10000||requests%2!==0)
    throw new RangeError('Requests must be an even integer between 200 and 10000.');
  if(!Number.isSafeInteger(seed)||seed<0||seed>2**32-1)
    throw new RangeError('Seed must be an unsigned 32-bit integer.');
  const n=requests/2,pays=[],refunds=[];
  for(let i=0;i<n;i++) {
    const id=`wal_case_${String(i).padStart(5,'0')}`;
    const variant=Math.imul((i+1)^(seed>>>0),0x9e3779b1)>>>0;
    const main=suppliers[variant%3];
    const secondary=suppliers[(variant+1)%3];
    const split=variant%4===0;
    const allocations=split
      ? [{supplierId:main,amountCents:60},{supplierId:secondary,amountCents:40}]
      : [{supplierId:main,amountCents:100}];
    pays.push(payment(id,`wal_pay_key_${String(i).padStart(5,'0')}`,100,allocations,seed));
    refunds.push(refund(id,`wal_ref_key_${String(i).padStart(5,'0')}`));
  }
  const planDigest=sha(JSON.stringify({requests,seed,pays,refunds}));
  return {requests,seed,orders:n,pays,refunds,planDigest};
}
