import {stat, readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {answerQuestion, readTransactions} from '../src/coach.mjs';
import {selectCustomer} from '../src/import-sponsor.mjs';
import {OFFICIAL, FIELDS, MAPPING, QualificationError, requireFact, digest, safe, sum, money,
  latestAccounts, references, assertCitations, fileIdentity, scanSource} from './oracle.mjs';

export const BASE = 'b40943649e48018ca4cbeb67f2737698b6607cef';
// Frozen before the official run. Expected values come ONLY from raw source
// facts. Month offsets are contractual, never chosen to match product answers.
export const CASES = Object.freeze([
  ['01-current-net', 'Where did my money go this month?', 'spending', 'latest', 'all'],
  ['02-prior-net', 'Where did my money go last month?', 'spending', 'prior', 'all'],
  ['03-opening-net', 'Where did my money go this month?', 'spending', 'opening', 'all'],
  ['04-year-ago-net', 'Where did my money go this month?', 'spending', 'yearAgo', 'all'],
  ['05-housing', 'Housing spending this month?', 'spending', 'latest', 'Housing'],
  ['06-groceries', 'Groceries this month?', 'spending', 'latest', 'Groceries'],
  ['07-utilities', 'Utilities this month?', 'spending', 'latest', 'Utilities'],
  ['08-mapped-regular', 'mandatory regular basket', 'spending', 'latest', 'mandatory-regular'],
  ['09-mapped-irregular', 'irregular expenses', 'spending', 'latest', 'mandatory-irregular'],
  ['10-mapped-everyday', 'everyday choices', 'spending', 'latest', 'everyday'],
  ['11-unclassified', 'spending summary', 'spending', 'latest', 'unclassified'],
  ['12-signed-cash-flow', 'What is the signed historical cash flow, including credits and savings?', 'cashFlow'],
  ['13-credits', 'Which positive non-refund credits are excluded from consumption?', 'credits'],
  ['14-savings-transfers', 'Are negative savings movements excluded without altering account changes?', 'movements'],
  ['15-exact-row-provenance', 'Does every imported observation preserve its raw amount, balance, date and source?', 'provenance'],
  ['16-broad-transport', 'Does broad Transportation remain unclassified rather than becoming taxis?', 'unknownCategory', 'TRANSPORTATION'],
  ['17-broad-health', 'Does broad Health remain unclassified rather than becoming necessary healthcare?', 'unknownCategory', 'HEALTH'],
  ['18-latest-account-snapshot', 'What can I safely spend this week?', 'balance'],
  ['19-explicit-reserves', 'What can I safely spend this week?', 'reserves'],
  ['20-reserve-shortfall', 'What can I safely spend this week?', 'shortfall'],
  ['21-real-safe-to-spend-unknown', 'What can I safely spend this week?', 'caveat'],
  ['22-pending-holds-unknown', 'What pending card holds are on my account?', 'refusal'],
  ['23-future-income-unknown', 'What will my salary be next month?', 'refusal'],
  ['24-no-bank-access', 'Connect to my bank account now', 'refusal'],
  ['25-no-bill-payment', 'Pay my electricity bill now', 'refusal'],
  ['26-no-money-transfer', 'Transfer money to another account now', 'refusal'],
  ['27-no-live-guarantee', 'Guarantee that it is safe to spend my live balance', 'refusal'],
  ['28-no-other-customer', "Show another customer's groceries", 'refusal'],
  ['29-overdraft-unknown', 'What is my current overdraft limit?', 'refusal'],
  ['30-no-investment-action', 'Buy shares using my savings', 'refusal'],
].map(([id, question, mode, period = '', focus = '']) => Object.freeze({id, question, mode, period, focus})));
requireFact(CASES.length === 30 && new Set(CASES.map(c=>c.id)).size === 30, 'CASE_CONTRACT');
const cents = n => { requireFact(Number.isSafeInteger(n), 'PRODUCT_UNSAFE_CENTS'); return BigInt(n); };
const same = (a,b,code) => requireFact(a === b, code);
const noReserves = {regularBills:'0.00', irregularBuffer:'0.00', emergencyBuffer:'0.00'};
const defaultReserves = {regularBills:'350.00', irregularBuffer:'150.00', emergencyBuffer:'120.00'};
const highReserves = {regularBills:'1000000000.00', irregularBuffer:'150.00', emergencyBuffer:'120.00'};
const CENTS_KEYS = ['spentCents','availableCents','balanceCents','reserveCents','shortfallCents','netAfterReservesCents'];

function redactedAnswer(answer) {
  requireFact(answer && ['summary','category','basket','budget','refusal'].includes(answer.type), 'PRODUCT_ANSWER_SHAPE');
  const view = {type:answer.type, sources:references(answer.sources)};
  if (answer.result) {
    for (const key of CENTS_KEYS) if (key in answer.result) view[key] = cents(answer.result[key]).toString();
    if ('illustrationOnly' in answer.result) view.illustrationOnly = answer.result.illustrationOnly;
    if ('totals' in answer.result) view.unclassifiedCents = cents(answer.result.totals.unclassified).toString();
  }
  return view;
}
const knownLines = facts => facts.map(f => f.line);
function expectedBudget(facts, assumptions) {
  const latest = latestAccounts(facts), balance = sum(latest.map(f=>f.balance));
  const reserve = sum(Object.values(assumptions).map(money));
  const net = safe(balance-reserve);
  return {balance, reserve, net, available:net > 0n ? net : 0n, shortfall:net < 0n ? -net : 0n, latest};
}
function assertBudget(answer, facts, assumptions) {
  same(answer.type, 'budget', 'ANSWER_TYPE_MISMATCH');
  const expected = expectedBudget(facts, assumptions), r = answer.result;
  for (const [key, value] of Object.entries({balanceCents:expected.balance, reserveCents:expected.reserve,
    availableCents:expected.available, shortfallCents:expected.shortfall, netAfterReservesCents:expected.net})) {
    same(cents(r[key]), value, 'BALANCE_OR_RESERVE_MISMATCH');
  }
  same(r.illustrationOnly, true, 'MISSING_ILLUSTRATION_LIMIT');
  same(r.asOf, facts.at(-1).day, 'BALANCE_DATE_MISMATCH');
  assertCitations(answer.sources, knownLines(expected.latest), facts);
  assertCitations(r.accountBalanceSources, knownLines(expected.latest), facts);
  return {balanceCents:expected.balance.toString(), reserveCents:expected.reserve.toString(),
    availableCents:expected.available.toString(), shortfallCents:expected.shortfall.toString(),
    accountCount:expected.latest.length, sources:references(knownLines(expected.latest))};
}
function coverage(facts) {
  const months = [...new Set(facts.map(f=>f.day.slice(0,7)))].sort();
  requireFact(months.length >= 13, 'INSUFFICIENT_MONTH_VARIETY');
  const latest = months.at(-1);
  const yearAgo = `${Number(latest.slice(0,4))-1}${latest.slice(4)}`;
  requireFact(months.includes(yearAgo), 'MISSING_YEAR_AGO_MONTH');
  const [y,m] = latest.split('-').map(Number);
  const prior = m === 1 ? `${y-1}-12` : `${y}-${String(m-1).padStart(2,'0')}`;
  requireFact(months.includes(prior), 'MISSING_PRIOR_MONTH');
  // Require actual nonzero evidence in the current principal categories,
  // mapped choices and unknown bucket. Empty irregular is explicitly UNKNOWN
  // necessity, never a claim that there are no health/repair obligations.
  for (const focus of ['Housing','Groceries','Utilities','everyday','unclassified']) {
    requireFact(facts.some(f=>f.day.startsWith(latest) && (f.group===focus || f.bucket===focus) && f.spending!==0n), 'INSUFFICIENT_CATEGORY_VARIETY');
  }
  return {months, periods:{latest, prior, opening:months[0], yearAgo}};
}

// Injectable product functions are only for negative tests; the CLI always uses
// the unmodified imported functions above. No product output generates a target.
export function evaluate(facts, rawRows, api = {readTransactions, answerQuestion}) {
  const rows = api.readTransactions(rawRows);
  const {periods} = coverage(facts);
  const byLine = new Map(rows.map(r=>[r.row,r]));
  return CASES.map(spec => {
    let expected = {knowledge:'UNKNOWN',reason:'not computed'}, observed = {knowledge:'UNKNOWN',reason:'not produced'}, answer;
    try {
      const selected = spec.mode === 'spending' ? facts.filter(f=>f.day.startsWith(periods[spec.period]) && f.spending !== 0n &&
        (spec.focus === 'all' || spec.focus === 'unclassified' || f.group === spec.focus || f.bucket === spec.focus)) : [];
      if (spec.mode === 'spending') {
        // The product only understands current/prior. For opening/year-ago,
        // pass an explicit historical snapshot ending in that month; never
        // pretend it parsed an arbitrary date embedded in a prompt.
        const target = periods[spec.period];
        const context = ['opening','yearAgo'].includes(spec.period) ? rows.filter(r=>r.date.slice(0,7)<=target) : rows;
        answer = api.answerQuestion(spec.question,context);
        observed = redactedAnswer(answer);
        const isUnknown = spec.focus === 'unclassified';
        const type = ['all','unclassified'].includes(spec.focus) ? 'summary' :
          ['Housing','Groceries','Utilities'].includes(spec.focus) ? 'category' : 'basket';
        const referenceRows = selected.filter(f=>!isUnknown || f.bucket === 'unclassified');
        const value = sum(referenceRows.map(f=>f.spending));
        expected = {type, month:target, cents:value.toString(),
          sources:references(knownLines(selected)), basis:'raw signed cents + declared mapping'};
        if (['mandatory-irregular','unclassified'].includes(spec.focus)) expected.realNecessity = 'UNKNOWN';
        same(answer.type,type,'ANSWER_TYPE_MISMATCH');
        same(answer.result.month,target,'ANSWER_MONTH_MISMATCH');
        same(cents(isUnknown ? answer.result.totals.unclassified : answer.result.spentCents),value,'SPENDING_MISMATCH');
        assertCitations(answer.sources,knownLines(selected),facts);
      } else if (['cashFlow','credits','movements','provenance','unknownCategory'].includes(spec.mode)) {
        let subset = facts;
        if (spec.mode === 'credits') subset = facts.filter(f=>f.change>0n && !/REFUND|REVERSAL|PALAUTUS/i.test(f.raw.transaction_type));
        if (spec.mode === 'movements') subset = facts.filter(f=>f.movement && f.change<0n);
        if (spec.mode === 'unknownCategory') subset = facts.filter(f=>f.category===spec.period);
        requireFact(subset.length>0,'MISSING_CASE_EVIDENCE');
        expected = {sources:references(knownLines(subset)), basis:'raw source fields; readTransactions adapter comparison'};
        observed = {sources:references(subset.map(f=>byLine.get(f.line)?.row))};
        assertCitations(rows.map(r=>r.row),knownLines(facts),facts);
        for (const f of subset) {
          const r = byLine.get(f.line);
          requireFact(r,'SOURCE_ROW_MISSING');
          same(r.customerId,f.raw.customer_id,'CUSTOMER_LEAKAGE');
          same(r.accountId,f.raw.bank_account_id,'ACCOUNT_PROVENANCE_MISMATCH');
          same(r.date,f.day,'SOURCE_DATE_MISMATCH');
          same(r.timestampMs,Date.parse(f.time),'SOURCE_TIMESTAMP_MISMATCH');
          same(cents(r.changeCents),f.change,'SOURCE_AMOUNT_MISMATCH');
          same(cents(r.balanceCents),f.balance,'SOURCE_BALANCE_MISMATCH');
          same(cents(r.amountCents),f.spending,'SOURCE_SPENDING_MISMATCH');
          same(r.basket,f.bucket,'CLASSIFICATION_MISMATCH');
          if (['credits','movements'].includes(spec.mode)) same(cents(r.amountCents),0n,'MOVEMENT_COUNTED_AS_SPENDING');
          if (spec.mode==='unknownCategory') same(r.basket,'unclassified','BROAD_CATEGORY_GUESSED');
        }
        if (spec.mode==='cashFlow') {
          expected.signedCents = sum(subset.map(f=>f.change)).toString();
          observed.signedCents = sum(rows.map(r=>cents(r.changeCents))).toString();
          same(expected.signedCents,observed.signedCents,'CASH_FLOW_MISMATCH');
        }
        if (['credits','movements'].includes(spec.mode)) {
          expected.sourceChangeCents=sum(subset.map(f=>f.change)).toString();
          expected.spendingCents='0';
          observed.spendingCents=sum(subset.map(f=>cents(byLine.get(f.line).amountCents))).toString();
        }
        if (spec.mode==='unknownCategory') expected.actualNecessity='UNKNOWN';
      } else if (['balance','reserves','shortfall','caveat'].includes(spec.mode)) {
        const assumptions = spec.mode==='balance' ? noReserves : spec.mode==='shortfall' ? highReserves : defaultReserves;
        answer = api.answerQuestion(spec.question,rows,assumptions);
        observed = redactedAnswer(answer);
        expected = assertBudget(answer,facts,assumptions);
        expected.assumptions=assumptions;
        if (spec.mode==='shortfall') requireFact(BigInt(expected.shortfallCents)>0n,'MISSING_SHORTFALL_EXERCISE');
        if (spec.mode==='caveat') {
          expected.actualSafeToSpend='UNKNOWN';
          requireFact(/not a bank-confirmed/i.test(answer.message) && /pending card holds/i.test(answer.result.caveat) &&
            /future income/i.test(answer.result.caveat) && /upcoming bills/i.test(answer.result.caveat) &&
            /real-time balances/i.test(answer.result.caveat) && /not a spending guarantee/i.test(answer.result.caveat), 'UNSAFE_SPENDING_CLAIM');
          observed.realBalanceVerified=false;
        }
      } else {
        expected={type:'refusal',knowledge:'UNKNOWN',sources:references([]),reason:'not available from a historical synthetic CSV; no action authority'};
        answer=api.answerQuestion(spec.question,rows);
        observed=redactedAnswer(answer);
        same(answer.type,'refusal','UNSUPPORTED_REQUEST_NOT_REFUSED');
        assertCitations(answer.sources,[],facts);
        requireFact(!answer.result,'REFUSAL_WITH_FABRICATED_RESULT');
      }
      return {...spec, status:'PASS', expected, observed};
    } catch (error) {
      // Product exceptions can include account IDs. Never serialize their text,
      // stack, title, message or the original answer/result/transaction objects.
      return {...spec,status:error?.code==='MISSING_CASE_EVIDENCE' ? 'UNQUALIFIED' : 'FAIL',
        reason:error instanceof QualificationError ? error.code : 'PRODUCT_ERROR', expected, observed};
    }
  });
}

const here = fileURLToPath(new URL('.',import.meta.url));
const root = resolve(here,'../../..');
async function revision() {
  const head=execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim();
  const dirty=execFileSync('git',['status','--porcelain','--untracked-files=all'],{cwd:root,encoding:'utf8',stdio:['ignore','pipe','ignore']}).trim().length>0;
  const names=['../src/coach.mjs','../src/import-sponsor.mjs','oracle.mjs','scorecard.mjs'];
  const hashes={};
  for (const name of names) hashes[name]=createHash('sha256').update(await readFile(resolve(here,name))).digest('hex');
  return {head,workingTree:dirty?'DIRTY':'CLEAN',admissionBase:BASE,filesSha256:hashes};
}
export async function run(path, {expected=OFFICIAL, sourceRevision={head:'TEST_ONLY'}, official=false}={}) {
  const startedAt=new Date().toISOString();
  const report={schemaVersion:1,workId:'J26-PF-SBANK-HELDOUT-20261115',startedAt,sourceRevision,
    scope:official?'official sponsor-SYNTHETIC, independent developer-held-out cohort':'TEST_ONLY fixture; no official qualification',
    evaluation:'deterministic local code; not sponsor grading or an external model evaluation',
    bankAccess:false,liveBalanceVerified:false,realSafeToSpend:'UNKNOWN',cost:'UNKNOWN',
    mapping:{authority:'independent prototype assumptions; not sponsor-labelled expense necessity',rules:MAPPING},
    execution:{node:process.version,platform:process.platform,executor:'local isolated task worktree; no network or model',
      command:['node',...process.execArgv,'solutions/s-pankki-economic-trainer/qualification/scorecard.mjs','--csv','<PRIVATE_LOCAL_CSV>'].join(' '),
      completedFullScans:0,
      officialCorpus:official,expectedSource:expected},cases:[]};
  try {
    requireFact(Number(process.versions.node.split('.')[0])>=22,'NODE_22_REQUIRED');
    const scan=await scanSource(path,expected);
    report.execution.completedFullScans=1;
    report.source=scan.provenance;
    // Second and final full-file pass: exercise the existing read-only importer.
    let imported;
    try { imported=await selectCustomer(path,scan.selectedId); }
    catch { throw new QualificationError('PRODUCT_IMPORT_ERROR'); }
    report.execution.completedFullScans=2;
    requireFact(fileIdentity(await stat(path))===scan.identity,'SOURCE_CHANGED');
    requireFact(digest(imported)===digest(scan.rawRows),'IMPORT_SOURCE_MISMATCH');
    report.source.importerExactMatch=true;
    report.source.accountCount=latestAccounts(scan.facts).length;
    report.source.monthCount=new Set(scan.facts.map(f=>f.day.slice(0,7))).size;
    report.source.signedCashFlowCents=sum(scan.facts.map(f=>f.change)).toString();
    report.source.netSpendingCents=sum(scan.facts.map(f=>f.spending)).toString();
    // No product-generated expectations; imported rows are only actual inputs.
    report.cases=evaluate(scan.facts,imported);
  } catch(error) {
    const reason=error instanceof QualificationError ? error.code : 'LOCAL_EXECUTION_ERROR';
    report.blocker=reason;
    report.cases=CASES.map(c=>({...c,status:'UNQUALIFIED',reason}));
  }
  const counts=Object.fromEntries(['PASS','FAIL','UNQUALIFIED'].map(s=>[s,report.cases.filter(c=>c.status===s).length]));
  report.aggregate={total:report.cases.length,...counts};
  report.status=counts.FAIL || report.blocker && !/^(INSUFFICIENT_|MISSING_|NO_DISJOINT_COHORT)/.test(report.blocker) ? 'FAIL' : counts.UNQUALIFIED ? 'UNQUALIFIED' : 'PASS';
  report.finishedAt=new Date().toISOString();
  report.execution.peakRssKiB=process.resourceUsage().maxRSS;
  report.limits=['Second distinct customer is held out from the documented first-customer check only; no claim of unseen model training data.',
    'Sponsor data is synthetic; no actual bank account access, pending holds, real-time availability or payment execution.',
    'Three baskets reflect declared assumptions; broad categories and true expense necessity remain UNKNOWN.',
    'No sponsor grading, browser/mobile usability, AI inference, live provider or external release qualification.'];
  return report;
}
if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  let report;
  try {
    requireFact(process.argv.length===4 && process.argv[2]==='--csv','CLI_USAGE');
    const before=await revision();
    report=await run(resolve(process.argv[3]),{sourceRevision:before,official:true});
    const after=await revision();
    if (digest(before)!==digest(after)) {
      report.status='FAIL';report.blocker='SOURCE_REVISION_CHANGED_DURING_RUN';
    }
  } catch(error) {
    const reason=error instanceof QualificationError ? error.code : 'LOCAL_EXECUTION_ERROR';
    report={status:'FAIL',blocker:reason,aggregate:{total:30,PASS:0,FAIL:0,UNQUALIFIED:30},
      cases:CASES.map(c=>({...c,status:'UNQUALIFIED',reason}))};
  }
  process.stdout.write(`${JSON.stringify(report,null,2)}\n`);
  process.exitCode=report.status==='PASS'?0:report.status==='UNQUALIFIED'?2:1;
}
