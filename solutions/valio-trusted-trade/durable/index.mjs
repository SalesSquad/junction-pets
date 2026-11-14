/**
 * Standalone synthetic PostgreSQL settlement lab, NOT the application money rail.
 * The caller must supply a previously verified immutable trade and approval;
 * this module does NOT verify the user, mandate, signature, or sponsor identity.
 */
import { createHash, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const SCHEMA = /^j26_[a-z0-9_]{8,60}$/;
const ORDER = /^[A-Za-z0-9_-]{3,80}$/;
const KEY = /^[A-Za-z0-9_-]{10,80}$/;
const SUPPLIER = /^[a-z0-9-]{1,64}$/;
const DIGEST = /^[a-f0-9]{64}$/;
const BUYER = 'demo:buyer:wallet';

export class DemoLedgerError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
const fail = (code,message) => { throw new DemoLedgerError(code,message); };
export const buyerAccount = BUYER;
export const supplierAccount = id => `demo:supplier:${id}:wallet`;
const safeSchema = name => {
  if (typeof name !== 'string' || !SCHEMA.test(name)) fail('SCHEMA_INVALID','Lab schema must be a unique j26_ namespace.');
  return `"${name}"`;
};
const positiveCents = n => Number.isSafeInteger(n) && n > 0 && n <= 2_000_000_000_000;
const exactDigest = x => typeof x === 'string' && DIGEST.test(x);
const digest = x => createHash('sha256').update(JSON.stringify(x)).digest('hex');

export function normalizePayment(input) {
  if (!input || Object.keys(input).some(k=>![
    'orderId','idempotencyKey','buyerAccount','allocations','totalCents',
    'verifiedQuoteBodyDigest','approvedProposalDigest'
  ].includes(k))) fail('TERMS_FORBIDDEN','Unrecognized or absent server-owned terms.');
  const {orderId,idempotencyKey,buyerAccount: buyer=BUYER,allocations,totalCents,
    verifiedQuoteBodyDigest,approvedProposalDigest} = input;
  if (typeof orderId !== 'string' || !ORDER.test(orderId)) fail('ORDER_INVALID','Invalid fictional order.');
  if (typeof idempotencyKey !== 'string' || !KEY.test(idempotencyKey)) fail('KEY_INVALID','Invalid stable idempotency key.');
  if (buyer !== BUYER) fail('BUYER_INVALID','Only the fixed synthetic buyer is admitted.');
  if (!exactDigest(verifiedQuoteBodyDigest) || !exactDigest(approvedProposalDigest))
    fail('PROOF_MISSING','A verified upstream quote digest and approved upstream proposal digest are required.');
  if (!Array.isArray(allocations) || allocations.length<1 || allocations.length>16)
    fail('ALLOCATIONS_INVALID','Expected 1–16 synthetic supplier allocations.');
  const bySupplier=new Map();
  for (const a of allocations) {
    if (!a || Object.keys(a).sort().join(',')!=='amountCents,supplierId' ||
        typeof a.supplierId!=='string' || !SUPPLIER.test(a.supplierId) ||
        !positiveCents(a.amountCents) || bySupplier.has(a.supplierId))
      fail('ALLOCATIONS_INVALID','Each supplier must appear once, with positive exact cents and no extra fields.');
    bySupplier.set(a.supplierId,a.amountCents);
  }
  const sorted = [...bySupplier].sort(([a],[b])=>a.localeCompare(b))
    .map(([supplierId,amountCents])=>({supplierId,amountCents}));
  const sum=sorted.reduce((s,a)=>s+a.amountCents,0);
  if (!positiveCents(totalCents) || !Number.isSafeInteger(sum) || sum!==totalCents)
    fail('AMOUNT_MISMATCH','Supplier totals must equal the exact order amount.');
  const canonical = {orderId,buyerAccount:buyer,totalCents,currency:'EUR',
    allocations:sorted,verifiedQuoteBodyDigest,approvedProposalDigest};
  return {...canonical,idempotencyKey,intentDigest:digest(canonical)};
}

export function normalizeRefund({orderId,idempotencyKey,...extra}={}) {
  if (Object.keys(extra).length) fail('TERMS_FORBIDDEN','Refund accepts only original order and key.');
  if (typeof orderId!=='string'||!ORDER.test(orderId)) fail('ORDER_INVALID','Invalid order.');
  if (typeof idempotencyKey!=='string'||!KEY.test(idempotencyKey)) fail('KEY_INVALID','Invalid key.');
  return {orderId,idempotencyKey,intentDigest:digest({kind:'SIMULATED_REFUND',orderId})};
}

export async function createLabSchema(pool,schema) {
  const quoted=safeSchema(schema);
  const client=await pool.connect();
  try {
    // CREATE only a unique owned lab schema; never overwrite/drop an existing schema.
    await client.query('BEGIN');
    await client.query(`CREATE SCHEMA ${quoted}`);
    await client.query(`SET LOCAL search_path TO ${quoted}`);
    await client.query(await readFile(new URL('./schema.sql',import.meta.url),'utf8'));
    await client.query('COMMIT');
  } catch(error) {
    try { await client.query('ROLLBACK'); } catch { /* connection may be broken */ }
    throw error;
  } finally { client.release(); }
}

async function tx(pool,schema,operation) {
  const quoted=safeSchema(schema);
  for(let attempt=0;attempt<7;attempt++) {
    const c=await pool.connect();
    let begun=false;
    try {
      await c.query('BEGIN ISOLATION LEVEL SERIALIZABLE'); begun=true;
      await c.query(`SET LOCAL search_path TO ${quoted}`);
      const out=await operation(c);
      await c.query('COMMIT'); begun=false;
      return out;
    } catch (error) {
      if (begun) try { await c.query('ROLLBACK'); } catch { /* connection may be broken */ }
      if ((error.code==='40001'||error.code==='40P01') && attempt<6) continue;
      throw error;
    } finally { c.release(); }
  }
  fail('TX_RETRY_EXHAUSTED','Serializable retry budget exceeded.');
}

export async function seedAccounts(pool,{schema,buyerFundsCents=250_000,suppliers=[]}={}) {
  if(!Number.isSafeInteger(buyerFundsCents)||buyerFundsCents<0) fail('FUNDS_INVALID','Invalid fictional buyer balance.');
  if(!Array.isArray(suppliers)||suppliers.some(x=>typeof x!=='string'||!SUPPLIER.test(x)))
    fail('SUPPLIERS_INVALID','Supplier IDs must be simple slugs.');
  return tx(pool,schema,async c=>{
    const accounts=[[BUYER,buyerFundsCents],...[...new Set(suppliers)].sort().map(id=>[supplierAccount(id),0])];
    for (const [id,initial] of accounts) {
      await c.query('INSERT INTO wallet_accounts(account_id,opening_balance_cents,balance_cents) VALUES ($1,$2,$2) ON CONFLICT (account_id) DO NOTHING',[id,initial]);
    }
    return {createdOrExisting:accounts.length};
  });
}

async function replay(c,key,kind,intentDigest) {
  const {rows:[existing]}=await c.query('SELECT kind,intent_digest,result FROM ledger_commands WHERE idempotency_key=$1 FOR UPDATE',[key]);
  if(!existing) return null;
  if(existing.kind!==kind||existing.intent_digest!==intentDigest)
    fail('IDEMPOTENCY_CONFLICT','Idempotency key already belongs to different frozen terms.');
  return {...existing.result,idempotentReplay:true};
}

async function adjustAndJournal(c,batchId,deltas) {
  const ids=[...deltas.keys()].sort();
  const {rows}=await c.query('SELECT account_id,balance_cents FROM wallet_accounts WHERE account_id=ANY($1::text[]) ORDER BY account_id FOR UPDATE',[ids]);
  if(rows.length!==ids.length) fail('UNKNOWN_ACCOUNT','Every synthetic beneficiary must be provisioned before settlement.');
  const net=[...deltas.values()].reduce((a,b)=>a+b,0);
  if (net!==0) fail('UNBALANCED_INTENT','Sum of ledger deltas must be exactly zero.');
  for(const id of ids) {
    const amount=deltas.get(id);
    if(!Number.isSafeInteger(amount)||amount===0) fail('INVALID_DELTA','Exact nonzero cents required.');
    const result=await c.query('UPDATE wallet_accounts SET balance_cents=balance_cents+$1 WHERE account_id=$2 AND balance_cents+$1>=0 RETURNING balance_cents',[amount,id]);
    if(result.rowCount!==1) fail('INSUFFICIENT_DEMO_FUNDS','Synthetic account cannot overdraw.');
    await c.query('INSERT INTO ledger_entries(batch_id,account_id,delta_cents) VALUES ($1,$2,$3)',[batchId,id,amount]);
  }
}

export async function settleDemoPayment(pool,{schema,...raw}) {
  const p=normalizePayment(raw);
  return tx(pool,schema,async c=>{
    const repeated=await replay(c,p.idempotencyKey,'SIMULATED_PAYMENT',p.intentDigest);
    if(repeated) return repeated;
    const {rowCount:already}=await c.query('SELECT 1 FROM demo_settlements WHERE order_id=$1',[p.orderId]);
    if(already) fail('ORDER_ALREADY_SETTLED','Each fictional order may settle once.');
    const batchId=randomUUID();
    await c.query('INSERT INTO ledger_batches(batch_id,order_id,kind,intent_digest) VALUES ($1,$2,$3,$4)',[batchId,p.orderId,'SIMULATED_PAYMENT',p.intentDigest]);
    const deltas=new Map([[BUYER,-p.totalCents]]);
    for(const a of p.allocations) deltas.set(supplierAccount(a.supplierId),a.amountCents);
    await adjustAndJournal(c,batchId,deltas);
    await c.query('INSERT INTO demo_settlements(order_id,payment_batch_id,payment_digest,buyer_account,total_cents,allocations) VALUES ($1,$2,$3,$4,$5,$6::jsonb)',[p.orderId,batchId,p.intentDigest,BUYER,p.totalCents,JSON.stringify(p.allocations)]);
    const result={orderId:p.orderId,batchId,status:'SIMULATED_SETTLED',totalCents:p.totalCents,
      currency:'EUR',allocations:p.allocations,rail:'POSTGRES_SYNTHETIC_NO_BANK_OR_PSP'};
    await c.query('INSERT INTO ledger_commands(idempotency_key,kind,intent_digest,result) VALUES ($1,$2,$3,$4::jsonb)',[p.idempotencyKey,'SIMULATED_PAYMENT',p.intentDigest,JSON.stringify(result)]);
    await c.query('INSERT INTO ledger_outbox(event_id,batch_id,event_kind,payload) VALUES ($1,$2,$3,$4::jsonb)',[randomUUID(),batchId,'SIMULATED_SETTLED',JSON.stringify(result)]);
    return {...result,idempotentReplay:false};
  });
}

export async function refundDemoPayment(pool,{schema,...raw}) {
  const p=normalizeRefund(raw);
  return tx(pool,schema,async c=>{
    const repeated=await replay(c,p.idempotencyKey,'SIMULATED_REFUND',p.intentDigest);
    if(repeated) return repeated;
    const {rows:[settlement]}=await c.query('SELECT * FROM demo_settlements WHERE order_id=$1 FOR UPDATE',[p.orderId]);
    if(!settlement) fail('ORDER_NOT_SETTLED','Refund requires a settled fictional order.');
    if(settlement.refund_batch_id) fail('ORDER_ALREADY_REFUNDED','Refund already posted for this order.');
    const batchId=randomUUID();
    await c.query('INSERT INTO ledger_batches(batch_id,order_id,kind,intent_digest) VALUES ($1,$2,$3,$4)',[batchId,p.orderId,'SIMULATED_REFUND',p.intentDigest]);
    const deltas=new Map([[BUYER,Number(settlement.total_cents)]]);
    for(const a of settlement.allocations) deltas.set(supplierAccount(a.supplierId),-a.amountCents);
    await adjustAndJournal(c,batchId,deltas);
    await c.query('UPDATE demo_settlements SET refund_batch_id=$1 WHERE order_id=$2',[batchId,p.orderId]);
    const result={orderId:p.orderId,batchId,originalBatchId:settlement.payment_batch_id,
      status:'SIMULATED_REFUNDED',totalCents:Number(settlement.total_cents),currency:'EUR',
      rail:'POSTGRES_SYNTHETIC_NO_BANK_OR_PSP'};
    await c.query('INSERT INTO ledger_commands(idempotency_key,kind,intent_digest,result) VALUES ($1,$2,$3,$4::jsonb)',[p.idempotencyKey,'SIMULATED_REFUND',p.intentDigest,JSON.stringify(result)]);
    await c.query('INSERT INTO ledger_outbox(event_id,batch_id,event_kind,payload) VALUES ($1,$2,$3,$4::jsonb)',[randomUUID(),batchId,'SIMULATED_REFUNDED',JSON.stringify(result)]);
    return {...result,idempotentReplay:false};
  });
}

export async function auditLab(pool,schema) {
  return tx(pool,schema,async c=>{
    const [accounts,ledger,batches,outbox,settlements]=await Promise.all([
      c.query('SELECT account_id,opening_balance_cents,balance_cents FROM wallet_accounts ORDER BY account_id'),
      c.query('SELECT account_id,coalesce(sum(delta_cents),0)::text AS net_cents FROM ledger_entries GROUP BY account_id'),
      c.query('SELECT b.batch_id,b.kind,coalesce(sum(e.delta_cents),0)::text AS net_cents,count(e.batch_id)::int AS entries FROM ledger_batches b LEFT JOIN ledger_entries e ON e.batch_id=b.batch_id GROUP BY b.batch_id,b.kind ORDER BY b.batch_id'),
      c.query('SELECT count(*)::int AS n FROM ledger_outbox'),
      c.query('SELECT count(*)::int AS n,count(refund_batch_id)::int AS refunds FROM demo_settlements')
    ]);
    const net=new Map(ledger.rows.map(r=>[r.account_id,BigInt(r.net_cents)]));
    const balanced=batches.rows.every(b=>BigInt(b.net_cents)===0n&&b.entries>=2);
    const matching=accounts.rows.every(a=>BigInt(a.opening_balance_cents)+(net.get(a.account_id)??0n)===BigInt(a.balance_cents));
    return {balanced,matching,nonnegative:accounts.rows.every(a=>BigInt(a.balance_cents)>=0n),
      batches:batches.rowCount,outboxEvents:outbox.rows[0].n,orders:settlements.rows[0].n,
      refunds:settlements.rows[0].refunds,
      accounts:accounts.rows.map(a=>({account:a.account_id,balanceCents:Number(a.balance_cents)})),
      mode:'POSTGRES_SYNTHETIC_NO_BANK_OR_PSP'};
  });
}
