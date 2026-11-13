import test from 'node:test';
import assert from 'node:assert/strict';
import {checkExperimentCard} from '../pets/aalto-university/experiment-card.mjs';

const card = () => ({claimType:'designed-experiment', hypothesis:'A blue label reduces fictional puzzle sorting time.', outcome:{metric:'sorting time',unit:'seconds',window:'one synthetic puzzle'}, control:{comparison:'grey label',allocation:'randomized'}, confounds:['Practice may change sorting time.'], decision:{preregistered:true,minimumDifference:0,direction:'decrease',rule:'Compare group means after the fixed sample; no optional stopping.'}, uncertainty:['No observations collected; effect and generalization unknown.'], sample:{treatment:20,control:20}});

test('complete invented plan is a design, never a causal finding or authorization', () => {
  assert.deepEqual(checkExperimentCard(card()), {status:'complete-plan',claimType:'designed-experiment',causalFinding:false,authorization:false,issues:[]});
});
for (const kind of ['association','hypothetical-causal']) test(`preserves ${kind} without promoting it to experiment`, () => {
  const input=card(); input.claimType=kind;
  const result=checkExperimentCard(input);
  assert.equal(result.status,'claim-only'); assert.equal(result.claimType,kind); assert.equal(result.causalFinding,false);
});
for (const key of Object.keys(card())) test(`missing ${key} fails closed`, () => {
  const input=card(); delete input[key]; assert.equal(checkExperimentCard(input).status,'rejected');
});
for (const value of [null,0,-1,1.5,NaN,Infinity,'20',Number.MAX_SAFE_INTEGER+1]) test(`invalid sample ${String(value)}`, () => {
  const input=card(); input.sample.control=value; assert.equal(checkExperimentCard(input).status,'rejected');
});
test('zero threshold is distinct from missing or null', () => {
  assert.equal(checkExperimentCard(card()).status,'complete-plan');
  for (const value of [null,undefined]) { const input=card(); input.decision.minimumDifference=value; assert.equal(checkExperimentCard(input).status,'rejected'); }
});
for (const [key,value] of [['confounds',[]],['uncertainty',[]],['hypothesis',' '],['control',null],['outcome',{}]]) test(`incomplete ${key}`, () => {
  const input=card(); input[key]=value; assert.equal(checkExperimentCard(input).status,'rejected');
});
test('no supplied verdict, significance or causal guarantee accepted', () => {
  for (const key of ['PASS','status','significant','pValue','causalGuarantee']) {
    const input=card(); input[key]=true; assert.equal(checkExperimentCard(input).status,'rejected');
  }
  for (const value of [false,null,'yes']) { const input=card(); input.decision.preregistered=value; assert.equal(checkExperimentCard(input).status,'rejected'); }
});
test('unknown nested keys and enum values rejected', () => {
  for (const key of ['outcome','control','decision','sample']) { const input=card(); input[key].extra=1; assert.equal(checkExperimentCard(input).status,'rejected'); }
  for (const value of ['causal-finding','PASS',null]) {const input=card();input.claimType=value;assert.equal(checkExperimentCard(input).status,'rejected');}
  const input=card(); input.control.allocation='assumed'; assert.equal(checkExperimentCard(input).status,'rejected');
});
test('rejects exotic objects, symbols, accessors and hooks without invoking them', () => {
  let calls=0;
  const getter=card(); Object.defineProperty(getter.outcome,'metric',{get(){calls++;throw Error('getter');},enumerable:true});
  const hook=card();hook.toJSON=()=>{calls++;throw Error('hook');};
  const exotic=card();Object.setPrototypeOf(exotic.sample,{valueOf(){calls++;}});
  const symbol=card();symbol[Symbol('extra')]=1;
  for (const input of [getter,hook,exotic,symbol,new Date(),null,[],42]) assert.equal(checkExperimentCard(input).status,'rejected');
  assert.equal(calls,0);
});
test('arrays reject holes, accessors, extra properties and subclass prototypes', () => {
  let calls=0;
  const arrays=[new Array(1),Object.assign(['x'],{extra:1}),Object.defineProperty(['x'],'0',{get(){calls++;throw Error('getter');}}),new (class extends Array {})('x')];
  for (const confounds of arrays) { const input=card();input.confounds=confounds;assert.equal(checkExperimentCard(input).status,'rejected'); }
  assert.equal(calls,0);
});
test('deterministic and does not mutate frozen input', () => {
  const input=card(); for(const value of Object.values(input)) if(value && typeof value==='object') Object.freeze(value); Object.freeze(input);
  assert.deepEqual(checkExperimentCard(input),checkExperimentCard(input));
});
