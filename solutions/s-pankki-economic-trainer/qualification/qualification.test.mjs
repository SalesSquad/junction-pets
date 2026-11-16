import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {CASES, evaluate, run} from './scorecard.mjs';
import {FIELDS, OFFICIAL, money, csvLine, clock, cohort, sourceFact, sum, latestAccounts,
  assertCitations, scanSource} from './oracle.mjs';
import {readTransactions, answerQuestion} from '../src/coach.mjs';

const stamp = day => {
  const [y,m,d]=day.split('-');
  return `${d}${['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][+m-1]}${y.slice(-2)}:12:00:00`;
};
function row(day,category,amount,type='purchase',account='FICTIONAL_ACCOUNT_A') {
  return {customer_id:'FICTIONAL_HELDOUT_ONLY',bank_account_id:account,tx_date:day,tx_timestamp:stamp(day),
    category,tx_amount_eur:amount,balance_after_eur:'1000.00',transaction_type:type,merchant_id:'',mcc_code:''};
}
function fixture() {
  const baseline={...row('2024-10-01','Salary','1000.00','salary'),customer_id:'FICTIONAL_BASELINE_ONLY'};
  const rows=[baseline];
  for (let i=0;i<24;i++) {
    const month=new Date(Date.UTC(2024,9+i,1)).toISOString().slice(0,7);
    const categories=[['Salary','1000.00','salary'],['Housing','-200.00','housing_payment'],
      ['Groceries','-50.21','purchase'],['Utilities','-20.13','utilities_payment'],
      ['Restaurants','-10.17','purchase'],['Transportation','-12.19','purchase'],
      ['Health','-7.23','purchase'],['Invest Deposit','-15.29','investment_deposit']];
    categories.forEach(([c,a,t],j)=>rows.push(row(`${month}-${String(j+1).padStart(2,'0')}`,c,a,t)));
  }
  rows.push(row('2026-09-29','Invest Withdraw','23.31','investment_withdrawal','FICTIONAL_ACCOUNT_B'));
  rows.push(row('2026-09-30','Restaurants','3.37','refund'));
  return rows.map((r,i)=>({...r,sourceLine:i+2}));
}
const quote = s => /[",\n\r]/.test(s)?`"${s.replaceAll('"','""')}"`:s;
const csv = rows => '\uFEFF'+FIELDS.join(',')+'\r\n'+rows.map(r=>FIELDS.map(k=>quote(r[k])).join(',')).join('\r\n')+'\r\n';
const spec = text => ({sha256:createHash('sha256').update(text).digest('hex'),bytes:Buffer.byteLength(text),rows:text.split('\n').length-2});
async function file(t,text) {
  const dir=await mkdtemp(join(tmpdir(),'sbank-heldout-test-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  const path=join(dir,'fictional.csv'); await writeFile(path,text,{mode:0o600}); return path;
}
const selected = () => fixture().slice(1);

// These are harness tests, NOT 30 official-data passes. The real product's
// unsupported-action failures must remain visible in the returned scorecard.
test('exact 30 fixed, substantive contracts; raw BigInt totals do not use product arithmetic',()=>{
  assert.equal(CASES.length,30); assert.equal(new Set(CASES.map(c=>c.id)).size,30);
  const raw=selected(), facts=cohort(raw), result=evaluate(facts,raw);
  assert.equal(result.length,30);
  assert.equal(result[0].expected.cents,'29656');
  assert.equal(result[1].expected.cents,'29993');
  assert.equal(result[10].expected.cents,'1942');
  assert.equal(result[7].expected.cents,'27034');
  assert.equal(result[8].expected.cents,'0');
  assert.equal(result[9].expected.cents,'680');
  assert.equal(result[17].expected.balanceCents,'200000');
  assert.equal(result[18].expected.availableCents,'138000');
  assert.equal(result[19].expected.shortfallCents,'99999827000');
  assert.equal(result[20].expected.actualSafeToSpend,'UNKNOWN');
  // Original frozen local receipt recorded five genuine action-intent failures.
  // The subsequent product guard must now refuse all five, not relabel the
  // original historical result or delete any negative acceptance criterion.
  for (const index of [24,25,26,27,28]) {
    assert.equal(result[index].status,'PASS', 'unsafe/third-party request must now be refused');
    assert.equal(result[index].observed.type,'refusal');
  }
  assert.equal(result.filter(c=>c.status==='FAIL').length,0);
});

test('streaming second-customer selection is deterministic, disjoint, complete and matches existing importer',async t=>{
  const text=csv(fixture()), path=await file(t,text);
  const scan=await scanSource(path,spec(text));
  assert.equal(scan.provenance.disjointFromFirst,true);
  assert.equal(scan.provenance.baselineRows,1);
  assert.equal(scan.rawRows.length,194);
  assert(scan.rawRows.every(r=>r.customer_id!=='FICTIONAL_BASELINE_ONLY'));
  const report=await run(path,{expected:spec(text)});
  assert.equal(report.status,'PASS');
  assert.deepEqual(report.aggregate,{total:30,PASS:30,FAIL:0,UNQUALIFIED:0});
  assert.equal(report.source.importerExactMatch,true);
  assert.equal(report.source.monthCount,24);
  const json=JSON.stringify(report);
  for (const secret of ['FICTIONAL_HELDOUT_ONLY','FICTIONAL_BASELINE_ONLY','FICTIONAL_ACCOUNT_A','FICTIONAL_ACCOUNT_B','customer_id','bank_account_id','merchant_id']) assert(!json.includes(secret));
  assert(!json.includes(':null'));
  assert.equal(report.scope,'TEST_ONLY fixture; no official qualification');
});

test('forged pinned digest hard-fails with exactly 30 unqualified cases, not official evidence',async t=>{
  const text=csv(fixture()), path=await file(t,text);
  const report=await run(path,{expected:{...spec(text),sha256:'0'.repeat(64)}});
  assert.equal(report.status,'FAIL');assert.equal(report.blocker,'SOURCE_SHA_MISMATCH');
  assert.equal(report.aggregate.UNQUALIFIED,30);assert(!report.source);
  const official=await run(path);assert.equal(official.blocker,'SOURCE_SIZE_MISMATCH');
  assert.equal(OFFICIAL.bytes,362796501);
});

test('truncated CSV, partial quotes, duplicate headers, blank records and extra fields refuse',async t=>{
  const good=csv(fixture());
  for (const bad of [good.slice(0,-2),good.replace('Groceries','"Groceries'),good.replace('mcc_code','category'),
    good+'\n',good.replace('Groceries','Groceries,extra')]) {
    const path=await file(t,bad);
    await assert.rejects(scanSource(path,spec(bad)));
  }
  for (const line of ['a,"b"junk,c','a,b"x,c','a,"b,c','a,\u0000,c']) assert.throws(()=>csvLine(line));
  assert.deepEqual(csvLine('a,"b,c","d""e",'),['a','b,c','d"e','']);
});

test('duplicate raw transactions and duplicate source citations are refused independently',()=>{
  const raw=selected();
  assert.throws(()=>cohort([...raw,{...raw[0],sourceLine:9999}]),/DUPLICATE_TRANSACTION/);
  assert.throws(()=>cohort([...raw,{...raw[0],tx_amount_eur:'1.00'}]),/DUPLICATE_SOURCE_LINE/);
  assert.throws(()=>assertCitations([3,3],[3],cohort(raw)),/INVALID_CITATIONS/);
});

test('multiple customers and no provably distinct cohort are never qualified',async t=>{
  const raw=selected();
  assert.throws(()=>cohort([...raw,{...raw[0],customer_id:'FICTIONAL_OTHER',sourceLine:9999}]),/MULTIPLE_CUSTOMERS/);
  assert.throws(()=>readTransactions([...raw,{...raw[0],customer_id:'FICTIONAL_OTHER',sourceLine:9999}]),/Multiple customers/);
  const text=csv(raw), path=await file(t,text), report=await run(path,{expected:spec(text)});
  assert.equal(report.status,'UNQUALIFIED');assert.equal(report.blocker,'NO_DISJOINT_COHORT');
  assert.equal(report.aggregate.UNQUALIFIED,30);
});

test('independent signed-cent parser rejects unsafe individual values and sums; exact cancellation survives',()=>{
  assert.equal(money('-12.09'),-1209n);assert.equal(money('0.01'),1n);
  for (const v of ['1.001','NaN','1e2','+1.00','1,02','', ' 1.00','90071992547409.92']) assert.throws(()=>money(v));
  assert.throws(()=>sum([9007199254740991n,1n]),/UNSAFE_CENTS/);
  assert.equal(sum([9007199254740991n,1n,-1n]),9007199254740991n);
  assert.equal(money('90071992547409.91'),9007199254740991n);
});

test('calendar and source timestamp are independent and bound, including leap-year and clock refusal',()=>{
  assert.equal(clock('29FEB24:23:59:59','2024-02-29'),'2024-02-29T23:59:59Z');
  for (const [s,d] of [['29FEB25:12:00:00','2025-02-29'],['30SEP26:24:00:00','2026-09-30'],
    ['30SEP25:12:00:00','2026-09-30'],['30FOO26:12:00:00','2026-09-30'],['30SEP26:12:60:00','2026-09-30']]) assert.throws(()=>clock(s,d));
});

test('latest balance uses source timestamp per account, refuses ambiguity and detects forged product balances',()=>{
  const a={...row('2026-09-30','Groceries','-1.00'),sourceLine:4,balance_after_eur:'8.00'};
  const b={...row('2026-09-29','Groceries','-1.00'),sourceLine:5,balance_after_eur:'9.00'};
  assert.equal(latestAccounts(cohort([a,b]))[0].line,4);
  assert.throws(()=>latestAccounts(cohort([a,{...a,sourceLine:9,balance_after_eur:'7.00'}])),/AMBIGUOUS_LATEST_BALANCE/);
  const raw=selected(), facts=cohort(raw);
  const results=evaluate(facts,raw,{readTransactions,answerQuestion:(q,r,a)=>{
    const answer=answerQuestion(q,r,a);
    if(answer.type==='budget') answer.result.balanceCents++;
    return answer;
  }});
  assert.equal(results[17].status,'FAIL');assert.equal(results[17].reason,'BALANCE_OR_RESERVE_MISMATCH');
});

test('forged, missing and cross-cohort citations cannot pass; raw field/account tampering is caught',()=>{
  const raw=selected(),facts=cohort(raw);
  assert.throws(()=>assertCitations([9999999],[],facts),/FOREIGN_CITATION/);
  assert.throws(()=>assertCitations([],known(facts),facts),/CITATION_MISMATCH/);
  assert.throws(()=>assertCitations([facts[1].line],[facts[0].line],facts),/CITATION_MISMATCH/);
  const injected=evaluate(facts,raw,{readTransactions,answerQuestion:(q,r,a)=>({...answerQuestion(q,r,a),sources:[9999999]})});
  assert.equal(injected[0].status,'FAIL');assert.equal(injected[0].reason,'FOREIGN_CITATION');
  const altered=evaluate(facts,raw,{answerQuestion,readTransactions:r=>readTransactions(r).map(x=>({...x,accountId:'FICTIONAL_FORGED'}))});
  assert.equal(altered[14].status,'FAIL');assert.equal(altered[14].reason,'ACCOUNT_PROVENANCE_MISMATCH');
});
const known=facts=>facts.map(f=>f.line);

test('positive refund offsets spending, ordinary credit does not, broad categories remain unknown',()=>{
  const r=(category,amount,type)=>sourceFact({...row('2026-09-30',category,amount,type),sourceLine:2});
  assert.equal(r('Restaurants','3.37','refund').spending,-337n);
  assert.equal(r('Restaurants','3.37','credit').spending,0n);
  assert.equal(r('Invest Deposit','-3.37','investment_deposit').spending,0n);
  assert.equal(r('Health','-3.37','purchase').bucket,'unclassified');
  assert.equal(r('Transportation','-3.37','purchase').bucket,'unclassified');
});

test('insufficient monthly/category variety yields unqualified, never substituted fictional evidence',()=>{
  assert.throws(()=>evaluate(cohort(selected().slice(0,8)),selected().slice(0,8)),/INSUFFICIENT_MONTH_VARIETY/);
});

test('malformed money/date in the source stream hard-fails before any cohort evidence',async t=>{
  for (const [bad,code] of [
    [csv(fixture()).replace('-50.21','-50.211'),'MALFORMED_MONEY'],
    [csv(fixture()).replace('-50.21','90071992547409.92'),'UNSAFE_CENTS'],
    [csv(fixture()).replace('2024-10-01','2024-02-30'),'MALFORMED_DATE'],
  ]) {
    const path=await file(t,bad), report=await run(path,{expected:spec(bad)});
    assert.equal(report.status,'FAIL');assert.equal(report.blocker,code);
    assert.equal(report.aggregate.UNQUALIFIED,30);assert(!report.source);
  }
});
