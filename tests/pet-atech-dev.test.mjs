import test from 'node:test';
import assert from 'node:assert/strict';
import {checkBom} from '../pets/atech-dev/bom-checker.mjs';

const fixture = () => ({
  board: {voltage: {min: 3, max: 3, unit: 'V'}, current: {value: 100, unit: 'mA'}, interfaces: [{name: 'fictional-digital', pins: 4}]},
  parts: [{id: 'invented-sensor', quantity: 2, rating: 'known', voltage: {min: 3000, max: 5000, unit: 'mV'}, current: {value: 20, unit: 'mA'}, requirements: [{interface: 'fictional-digital', pins: 2}]}]
});

test('quantity, mixed units and exact capacity boundaries', () => {
  const input = fixture();
  const before = structuredClone(input);
  const r = checkBom(input);
  assert.equal(r.status, 'internally-consistent');
  assert.equal(r.totalCurrentMA, 40);
  assert.deepEqual(r.parts[0], {id: 'invented-sensor', rating: 'known', status: 'internally-consistent', issues: []});
  assert.deepEqual(input, before);
  input.board.current = {value: 1, unit: 'A'};
  input.parts[0].current = {value: 0, unit: 'A'};
  assert.equal(checkBom(input).totalCurrentMA, 0);
});

test('retains voltage, current and quantity-adjusted pin conflicts', () => {
  const x = fixture();
  x.parts[0].quantity = 3;
  x.parts[0].voltage.min = 2000;
  x.parts[0].voltage.max = 2999;
  x.board.current.value = 59;
  const r = checkBom(x);
  assert.equal(r.status, 'incompatible');
  assert.deepEqual(r.conflicts.map(c => c.code), ['voltage-range', 'current-capacity', 'pin-capacity']);
  assert.equal(r.parts[0].status, 'incompatible');
});

test('whole declared supply range must be accepted, including lower edge', () => {
  const x = fixture();
  x.board.voltage.min = 2;
  assert.equal(checkBom(x).conflicts[0].code, 'voltage-range');
  x.board.voltage.min = 3;
  x.board.voltage.max = 6;
  assert.equal(checkBom(x).conflicts[0].code, 'voltage-range');
});

test('unknown interface is a conflict even with zero required pins', () => {
  const x = fixture();
  x.parts[0].requirements[0] = {interface: 'absent', pins: 0};
  assert.equal(checkBom(x).conflicts[0].code, 'interface-missing');
});

test('multiple parts aggregate dedicated pins and current', () => {
  const x = fixture();
  x.parts.push({...structuredClone(x.parts[0]), id: 'invented-output'});
  const r = checkBom(x);
  assert.equal(r.totalCurrentMA, 80);
  assert.equal(r.conflicts[0].code, 'pin-capacity');
  assert.ok(r.parts.every(p => p.status === 'incompatible'));
});

test('missing, null and explicit zero specifications remain different', () => {
  for (const field of ['voltage', 'current', 'requirements']) {
    const x = fixture();
    delete x.parts[0][field];
    assert.ok(checkBom(x).parts[0].issues.includes(`missing:${field}`));
    x.parts[0][field] = null;
    assert.ok(checkBom(x).parts[0].issues.includes(`null:${field}`));
    assert.equal(checkBom(x).status, 'incomplete');
  }
  const x = fixture();
  x.parts[0].current.value = 0;
  x.parts[0].requirements[0].pins = 0;
  assert.equal(checkBom(x).status, 'internally-consistent');
});

test('unknown rating never becomes a complete review; conflicts survive unknowns', () => {
  const x = fixture();
  x.parts[0].rating = 'unknown';
  x.parts[0].voltage.min = 2000;
  x.parts[0].voltage.max = 2999;
  const r = checkBom(x);
  assert.equal(r.status, 'incomplete');
  assert.equal(r.parts[0].status, 'incomplete');
  assert.ok(r.parts[0].issues.includes('unknown:rating'));
  assert.equal(r.conflicts[0].code, 'voltage-range');
  assert.equal(r.totalCurrentMA, null);
});

test('missing board specifications cannot produce a complete review', () => {
  for (const key of ['voltage', 'current', 'interfaces']) {
    const x = fixture(); delete x.board[key];
    assert.equal(checkBom(x).status, 'incomplete');
    assert.ok(checkBom(x).issues.includes(`missing:board.${key}`));
  }
});

test('required identity, quantity and rating are structural requirements', () => {
  for (const key of ['id', 'quantity', 'rating']) {
    const x = fixture(); delete x.parts[0][key];
    assert.throws(() => checkBom(x), TypeError);
  }
});

test('rejects unknown keys at every object layer', () => {
  for (const get of [x=>x, x=>x.board, x=>x.board.voltage, x=>x.board.current, x=>x.board.interfaces[0], x=>x.parts[0], x=>x.parts[0].voltage, x=>x.parts[0].current, x=>x.parts[0].requirements[0]]) {
    const x = fixture(); get(x).unexpected = true;
    assert.throws(() => checkBom(x), TypeError);
  }
});

test('rejects duplicate part IDs, board interfaces and part requirements', () => {
  for (const get of [x=>x.parts, x=>x.board.interfaces, x=>x.parts[0].requirements]) {
    const x = fixture(); const a = get(x); a.push(structuredClone(a[0]));
    assert.throws(() => checkBom(x), TypeError);
  }
});

test('rejects invalid units, ratings and reversed ranges', () => {
  for (const mutate of [x=>x.board.voltage.unit='v', x=>x.parts[0].current.unit='mV', x=>x.parts[0].rating='approved', x=>x.parts[0].voltage.min=6000]) {
    const x=fixture(); mutate(x); assert.throws(() => checkBom(x), TypeError);
  }
});

test('rejects nonfinite, fractional, negative and unsafe numeric data', () => {
  for (const n of [NaN, Infinity, -Infinity, -1, 0.5, Number.MAX_SAFE_INTEGER+1]) {
    const x=fixture(); x.parts[0].current.value=n;
    assert.throws(() => checkBom(x), TypeError);
  }
  for (const n of [0, null, '2', -1]) {
    const x=fixture(); x.parts[0].quantity=n;
    assert.throws(() => checkBom(x), TypeError);
  }
});

test('rejects overflow during normalization, multiplication and summation', () => {
  for (const mutate of [
    x=>x.board.current={value:Number.MAX_SAFE_INTEGER,unit:'A'},
    x=>x.parts[0].current.value=Number.MAX_SAFE_INTEGER,
    x=>x.parts[0].requirements[0].pins=Number.MAX_SAFE_INTEGER,
    x=>{x.parts[0].quantity=1; x.parts[0].current.value=Number.MAX_SAFE_INTEGER; x.parts.push({...structuredClone(x.parts[0]),id:'second'});}
  ]) { const x=fixture(); mutate(x); assert.throws(() => checkBom(x), TypeError); }
});

test('rejects sparse, accessor and extra-property arrays without invoking code', () => {
  let calls=0;
  for (const mutate of [
    a=>delete a[0],
    a=>Object.defineProperty(a,'0',{get(){calls++; throw Error('getter');}}),
    a=>a.extra=true,
    a=>Object.defineProperty(a,Symbol('extra'),{value:true})
  ]) { const x=fixture(); mutate(x.parts); assert.throws(()=>checkBom(x),TypeError); }
  assert.equal(calls,0);
});

test('rejects accessors, hooks, nonenumerable and symbol keys without calling them', () => {
  let calls=0;
  for (const mutate of [
    x=>Object.defineProperty(x.board,'voltage',{get(){calls++; throw Error('getter');}}),
    x=>x.parts[0].toJSON=()=>{calls++; return {};},
    x=>Object.defineProperty(x.parts[0],'hidden',{value:1}),
    x=>x[Symbol('hidden')]=1
  ]) { const x=fixture(); mutate(x); assert.throws(()=>checkBom(x),TypeError); }
  assert.equal(calls,0);
});

test('rejects unsupported prototypes, cycles and non-JSON primitives', () => {
  for (const value of [undefined, 1n, ()=>0, new Date(), new Map(), Object.create({}), Symbol('x')]) {
    const x=fixture(); x.parts[0].current=value;
    assert.throws(()=>checkBom(x),TypeError);
  }
  const x=fixture(); x.parts[0].current=x;
  assert.throws(()=>checkBom(x),TypeError);
  const y=fixture(); Object.setPrototypeOf(y.parts, null);
  assert.throws(()=>checkBom(y),TypeError);
});

test('empty BOM is incomplete, null-prototype records are accepted', () => {
  const x=fixture(); x.parts=[];
  assert.equal(checkBom(x).status,'incomplete');
  const y=fixture(); y.board.current=Object.assign(Object.create(null),y.board.current);
  assert.equal(checkBom(y).status,'internally-consistent');
});

test('bounded depth and collection size reject oversized input', () => {
  const x=fixture(); x.parts=Array.from({length:1001},(_,i)=>({...x.parts[0],id:`p${i}`}));
  assert.throws(()=>checkBom(x),TypeError);
  const y=fixture(); let v={}; for(let i=0;i<30;i++) v={v}; y.extra=v;
  assert.throws(()=>checkBom(y),TypeError);
});
