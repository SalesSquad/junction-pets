import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {scaleFictionalRecipe} from '../pets/valio-aimo/recipe-scale.mjs';

const fixture = () => JSON.parse(readFileSync(new URL('../pets/valio-aimo/examples/fictional-recipe.json', import.meta.url), 'utf8'));
const run = value => scaleFictionalRecipe(JSON.stringify(value));
const row = patch => ({id:'fictional-ingredient-a', quantity:2, unit:'kg', targetUnit:'kg', sourceRef:'fictional-label-a', allergenState:'declared-fixture', allergenTokens:['fictional-allergen-a'], ...patch});
const recipe = ingredients => ({schemaVersion:1, fictional:true, baseServings:8, targetServings:30, ingredients});

test('invented fixture gives a visible ratio and preserves unknown product facts', () => {
  const result = run(fixture());
  assert.equal(result.ratio, 3.75);
  assert.equal(result.ingredients[0].scaledQuantity, 7500);
  assert.equal(result.ingredients[0].unit, 'g');
  assert.equal(result.ingredients[1].scaledQuantity, 0);
  assert.equal(result.ingredients[2].scaledQuantity, null);
  assert.equal(result.state, 'calculated-with-unknowns');
  assert.deepEqual(result.boundary, {productFactsVerified:false, allergenSafetyAssessed:false, nutritionAssessed:false, preparationAssessed:false, providerExecution:false});
});

test('only declared compatible mass, volume and count conversions are applied', () => {
  for (const [unit,targetUnit,quantity,expected] of [['kg','g',2,7500],['g','kg',2000,7.5],['l','ml',2,7500],['ml','l',2000,7.5],['count','count',2,7.5]]) {
    assert.equal(run(recipe([row({unit,targetUnit,quantity})])).ingredients[0].scaledQuantity, expected);
  }
});

test('fractional count is exposed, not rounded, and zero is not unknown', () => {
  const a = run(recipe([row({unit:'count',targetUnit:'count',quantity:1})]));
  assert.equal(a.ingredients[0].scaledQuantity, 3.75);
  assert.ok(a.gaps.some(x => x.code === 'fractional-count-review'));
  const b = run(recipe([row({quantity:0})]));
  assert.equal(b.ingredients[0].scaledQuantity, 0);
  assert.equal(b.ingredients[0].amountState, 'calculated');
  assert.throws(() => run(recipe([row({unit:'count',targetUnit:'count',quantity:1.5})])), /integer count/);
});

test('null quantity, units, provenance and allergens remain explicit unknowns', () => {
  const input = recipe([row({quantity:null,unit:null,targetUnit:null,sourceRef:null,allergenState:'unknown',allergenTokens:null})]);
  const result = run(input);
  assert.equal(result.ingredients[0].amountState, 'unknown');
  assert.equal(result.ingredients[0].scaledQuantity, null);
  assert.equal(result.ingredients[0].unit, null);
  assert.equal(result.ingredients[0].sourceState, 'unknown');
  assert.equal(result.ingredients[0].declaredAllergenTokens, null);
  assert.deepEqual(result.gaps.map(x => x.code), ['quantity-unknown','unit-unknown','target-unit-unknown','source-unknown','allergens-unknown']);
});

test('unit is never inferred from another ingredient or target', () => {
  const result = run(recipe([row({unit:null}),row({id:'fictional-ingredient-b',targetUnit:null})]));
  assert.deepEqual(result.ingredients.map(x => x.scaledQuantity), [null,null]);
  assert.equal(result.ingredients[0].unit, 'kg');
  assert.equal(result.ingredients[1].unit, null);
});

test('cross-dimension conversions are rejected rather than assuming density or count weight', () => {
  for (const [unit,targetUnit] of [['g','ml'],['l','kg'],['count','g'],['kg','count']]) {
    assert.throws(() => run(recipe([row({unit,targetUnit})])), /incompatible units/);
  }
});

test('fictional allergen declarations require a fictional source and never become safety facts', () => {
  assert.throws(() => run(recipe([row({sourceRef:null})])), /fictional source/);
  assert.throws(() => run(recipe([row({allergenState:'unknown',allergenTokens:[]})])), /null tokens/);
  assert.throws(() => run(recipe([row({allergenState:'verified-safe'})])), /allergenState/);
  assert.throws(() => run(recipe([row({allergenTokens:['milk']})])), /fictional token/);
  assert.throws(() => run(recipe([row({allergenTokens:['fictional-a','fictional-a']})])), /unique/);
  const result = run(recipe([row({allergenTokens:[]})]));
  assert.equal(result.ingredients[0].allergenState, 'declared-fixture');
  assert.equal(result.boundary.allergenSafetyAssessed, false);
  assert.equal(result.boundary.productFactsVerified, false);
});

test('closed schema rejects hidden facts, missing fields and duplicate ingredient IDs', () => {
  assert.throws(() => run({...recipe([row()]), safeToEat:true}), /fields/);
  assert.throws(() => run(recipe([row({protein:12})])), /fields/);
  const a = row(); delete a.quantity;
  assert.throws(() => run(recipe([a])), /fields/);
  assert.throws(() => run(recipe([row(),row()])), /unique/);
  assert.throws(() => run(recipe([row({sourceRef:'https://supplier.invalid/product'})])), /fictional token/);
  assert.throws(() => run(recipe([row({id:'fictional-a\n'})])), /fictional token/);
});

test('serving, quantity, unit and declaration bounds reject unsupported arithmetic', () => {
  for (const value of [null,0,-1,0.5,10001,'8']) {
    assert.throws(() => run({...recipe([row()]),baseServings:value}), /servings/);
    assert.throws(() => run({...recipe([row()]),targetServings:value}), /servings/);
  }
  for (const quantity of [-1,1000001,'2']) assert.throws(() => run(recipe([row({quantity})])), /quantity/);
  assert.throws(() => scaleFictionalRecipe(JSON.stringify(recipe([row()])).replace('"quantity":2','"quantity":1e309')), /quantity/);
  assert.throws(() => run(recipe([row({unit:'cup'})])), /unit/);
  assert.throws(() => run({...recipe([row()]),fictional:false}), /fictional/);
  assert.throws(() => run({...recipe([row()]),schemaVersion:2}), /schemaVersion/);
});

test('input text and collections are bounded and ordinary JSON parsing is explicit', () => {
  for (const value of [null,{},42,'','{','null','[]']) assert.throws(() => scaleFictionalRecipe(value));
  assert.throws(() => scaleFictionalRecipe(' '.repeat(32769)), /32768/);
  assert.throws(() => scaleFictionalRecipe('é'.repeat(16385)), /32768/);
  assert.throws(() => run(recipe([])), /ingredients/);
  assert.throws(() => run(recipe(Array.from({length:33},(_,i)=>row({id:`fictional-${i}`})))), /ingredients/);
  assert.throws(() => run(recipe([row({allergenTokens:Array.from({length:17},(_,i)=>`fictional-${i}`)})])), /tokens/);
  const duplicate = JSON.stringify(recipe([row()])).replace('"baseServings":8','"baseServings":1,"baseServings":8');
  assert.equal(scaleFictionalRecipe(duplicate).ratio, 3.75);
});

test('arithmetic limits avoid overflow and reject positive quantities rounded down to numeric zero', () => {
  const largest = recipe([row({quantity:1000000,unit:'kg',targetUnit:'g'})]);
  largest.baseServings=1; largest.targetServings=10000;
  assert.equal(run(largest).ingredients[0].scaledQuantity, 10000000000000);
  const tiny = recipe([row({quantity:Number.MIN_VALUE,unit:'g',targetUnit:'kg'})]);
  tiny.baseServings=10000; tiny.targetServings=1;
  assert.throws(() => run(tiny), /arithmetic range/);
});

test('same input is deterministic and output mutation cannot change a later result', () => {
  const raw = JSON.stringify(recipe([row()]));
  const first = scaleFictionalRecipe(raw);
  const expected = structuredClone(first);
  first.ingredients[0].declaredAllergenTokens.push('fictional-other');
  first.boundary.providerExecution = true;
  assert.deepEqual(scaleFictionalRecipe(raw), expected);
  assert.equal(expected.state, 'arithmetic-complete');
  assert.equal(expected.kind, 'fictional-arithmetic-only');
});
