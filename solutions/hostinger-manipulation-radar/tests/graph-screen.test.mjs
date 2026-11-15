import test from 'node:test';
import assert from 'node:assert/strict';
import {FEATURES, graphFeatures, graphScore} from '../public/graph/core.mjs';

const close = (actual, expected) => assert.ok(Math.abs(actual - expected) <= 1e-12,
  `expected ${expected}, observed ${actual}`);
const named = graph => Object.fromEntries(FEATURES.map((name, i) => [name, graph.x[i]]));
const tiny = edges => graphFeatures({edges}, {enforceDomain: false});
const sample = () => ({edges: Array.from({length: 100}, (_, i) =>
  [1, 2, 3].map(offset => [i, (i + offset) % 100])).flat()});
const model = overrides => ({
  schema: 'signal-desk-len-model-v1', features: [...FEATURES],
  threshold: 0.5, means: Array(12).fill(0), scales: Array(12).fill(1),
  weights: Array(12).fill(0), intercept: 0, ...overrides
});

test('hand oracle: directed degrees, zero fractions, gini, HHI and distinct-pair reciprocity', () => {
  const result = tiny([['a', 'b'], ['a', 'c'], ['b', 'a']]);
  assert.deepEqual(Object.keys(result).sort(), ['edges', 'nodes', 'x']);
  assert.equal(result.nodes, 3); assert.equal(result.edges, 3);
  assert.equal(FEATURES.length, 12); assert.equal(result.x.length, 12);
  const f = named(result);
  close(f.log_nodes, Math.log(4)); close(f.log_edges, Math.log(4));
  close(f.density, 1 / 3); close(f.zero_in_fraction, 0); close(f.zero_out_fraction, 1 / 3);
  close(f.reciprocal_fraction, 2 / 3);
  // In-degrees [1,1,1]; out-degrees [2,1,0].
  close(f.in_gini, 0); close(f.out_gini, 4 / 9);
  close(f.max_in_share, 1 / 3); close(f.max_out_share, 2 / 3);
  close(f.in_hhi, 1 / 3); close(f.out_hhi, 5 / 9);
});

test('edge reversal swaps incoming/outgoing features without changing density or reciprocity', () => {
  const edges = [['a', 'b'], ['a', 'c'], ['b', 'a']];
  const a = named(tiny(edges)), b = named(tiny(edges.map(([x, y]) => [y, x])));
  for (const [incoming, outgoing] of [
    ['zero_in_fraction', 'zero_out_fraction'], ['in_gini', 'out_gini'],
    ['max_in_share', 'max_out_share'], ['in_hhi', 'out_hhi']
  ]) { close(a[incoming], b[outgoing]); close(a[outgoing], b[incoming]); }
  close(a.density, b.density); close(a.reciprocal_fraction, b.reciprocal_fraction);
});

test('relabeling and edge ordering cannot change topology features; numeric/string IDs stay distinct', () => {
  const edges = [[1, '1'], ['1', 2], [2, 1]];
  const original = tiny(edges);
  const mapping = new Map([[1, 'renamed-alpha'], ['1', 'renamed-beta'], [2, 'renamed-gamma']]);
  const renamed = tiny(edges.map(([a, b]) => [mapping.get(a), mapping.get(b)]).reverse());
  assert.equal(original.nodes, 3); assert.equal(original.edges, 3);
  original.x.forEach((value, i) => close(value, renamed.x[i]));
  close(named(original).density, 1 / 3);
});

test('self loops count in m/n squared density but never as reciprocal distinct-pair edges', () => {
  const result = named(tiny([['a', 'a'], ['a', 'b'], ['b', 'a']]));
  close(result.density, 3 / 4); close(result.reciprocal_fraction, 2 / 3);
  close(result.in_gini, 1 / 6); close(result.out_gini, 1 / 6);
  close(result.in_hhi, 5 / 9); close(result.out_hhi, 5 / 9);
  const onlyLoops = named(tiny([['a', 'a'], ['b', 'b']]));
  close(onlyLoops.density, 1 / 2); close(onlyLoops.reciprocal_fraction, 0);
});

test('labels, text and model-score input fields are refused rather than entering features', () => {
  const graph = sample(), baseline = graphFeatures(graph);
  for (const [key, value] of [['label', 1], ['truth', 'malicious'], ['text', 'private payload'], ['modelscore', 1], ['intent', 'BOT']]) {
    assert.throws(() => graphFeatures({...graph, [key]: value}), /edge list/);
    assert.throws(() => graphScore({...graph, [key]: value}, model()), /edge list/);
  }
  // Labels used only as arbitrary vertex IDs do not become output attributes.
  const renamed = graphFeatures({edges: graph.edges.map(([a, b]) => ['private-label-' + a, 'private-label-' + b])});
  assert.deepEqual(renamed, baseline);
  assert.ok(!JSON.stringify(renamed).includes('private-label'));
});

test('duplicates, malformed edges and unsupported IDs fail closed', () => {
  for (const input of [
    null, [], {}, {edges: []}, {edges: [['a', 'b'], ['a', 'b']]},
    {edges: [['a']]}, {edges: [['a', 'b', 'extra']]}, {edges: [null]},
    {edges: [[true, 'b']]}, {edges: [[{}, 'b']]}, {edges: [['', 'b']]},
    {edges: [['x'.repeat(129), 'b']]}, {edges: [[NaN, 'b']]},
    {edges: [[Infinity, 'b']]}, {edges: [[1.25, 'b']]}, {edges: [[Number.MAX_SAFE_INTEGER + 1, 'b']]}
  ]) assert.throws(() => graphFeatures(input, {enforceDomain: false}), /edge list/);
});

test('100-node ring plus chords satisfies the declared domain; small and oversized inputs do not', () => {
  const graph = graphFeatures(sample()), f = named(graph);
  assert.equal(graph.nodes, 100); assert.equal(graph.edges, 300);
  close(f.density, 0.03); close(f.in_gini, 0); close(f.out_gini, 0);
  close(f.in_hhi, 0.01); close(f.out_hhi, 0.01); close(f.reciprocal_fraction, 0);
  assert.throws(() => graphFeatures({edges: Array.from({length: 100}, (_, i) => [i, (i + 1) % 100])}), /edge list/);
  assert.throws(() => graphFeatures({edges: Array.from({length: 99}, (_, i) =>
    [1, 2, 3].map(offset => [i, (i + offset) % 99])).flat()}), /edge list/);
  assert.throws(() => graphFeatures({edges: Array.from({length: 10609}, (_, i) => [i, i + 1])}), /edge list/);
});

test('valid logistic score has exact declared output and abstains on actor intent', () => {
  const result = graphScore(sample(), model());
  close(result.score, 0.5); assert.equal(result.review, true);
  assert.equal(result.nodes, 100); assert.equal(result.edges, 300);
  assert.equal(result.intent, 'UNKNOWN'); assert.equal(result.status, 'EXPERIMENTAL');
  assert.deepEqual(Object.keys(result).sort(), ['edges', 'intent', 'nodes', 'review', 'score', 'status']);
  close(graphScore(sample(), model({intercept: Math.log(3)})).score, 0.75);
  assert.equal(graphScore(sample(), model({threshold: 0.75})).review, false);
});

test('invalid model structure and non-finite numerical parameters are rejected', () => {
  const wrongFeatures = [...FEATURES].reverse();
  for (const candidate of [
    null, {}, model({schema: 'other'}), model({features: wrongFeatures}),
    model({threshold: NaN}), model({threshold: -1}), model({threshold: 2}),
    model({means: Array(11).fill(0)}), model({scales: Array(12).fill(0)}),
    model({scales: Array(12).fill(-1)}), model({scales: Array(12).fill(Infinity)}),
    model({weights: Array(12).fill(NaN)}), model({weights: []}), model({intercept: Infinity})
  ]) assert.throws(() => graphScore(sample(), candidate), /Model unavailable/);
});

test('finite coefficients that overflow the combined logit are rejected instead of returning NaN', () => {
  const weights = Array(12).fill(0); weights[0] = 1e308; weights[1] = -1e308;
  assert.throws(() => graphScore(sample(), model({weights})), /Model unavailable/);
});

test('upper node boundary and explicit abstention threshold stay enforced',()=>{
 const ring=n=>({edges:Array.from({length:n},(_,i)=>[i,(i+1)%n])});
 assert.equal(graphFeatures(ring(8355)).nodes,8355);
 assert.throws(()=>graphFeatures(ring(8356)),/edge list/);
 assert.equal(graphScore(sample(),model({threshold:1.000000001})).review,false);
 assert.throws(()=>graphScore(sample(),model({threshold:1.000000002})),/Model unavailable/);
 assert.throws(()=>graphFeatures({edges:[['a','b'],['a','b']]},{enforceDomain:false}),/Duplicate/);
});
