// Offline arithmetic over an invented fixture, never product or allergen advice.
const UNITS = Object.freeze({g:['mass',1], kg:['mass',1000], ml:['volume',1], l:['volume',1000], count:['count',1]});
const ROOT_FIELDS = ['schemaVersion','fictional','baseServings','targetServings','ingredients'];
const INGREDIENT_FIELDS = ['id','quantity','unit','targetUnit','sourceRef','allergenState','allergenTokens'];
const fail = message => { throw new TypeError(`Fictional recipe: ${message}`); };

function exact(value, fields, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).length !== fields.length
      || !Object.keys(value).every(key => fields.includes(key))) fail(`${label} fields must match the contract`);
}

function token(value) {
  if (typeof value !== 'string' || value.length > 64 || value.trim() !== value
      || !/^fictional-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) fail('expected a bounded fictional token');
}

function unit(value) {
  if (value !== null && (typeof value !== 'string' || !Object.hasOwn(UNITS,value))) fail('unsupported unit');
}

/** Parse bounded JSON text. Duplicate JSON object keys follow JSON.parse's last-key-wins behavior. */
export function scaleFictionalRecipe(jsonText) {
  if (typeof jsonText !== 'string' || jsonText.length > 32768
      || new TextEncoder().encode(jsonText).length > 32768) fail('input must be JSON text of at most 32768 UTF-8 bytes');
  let input;
  try { input = JSON.parse(jsonText); } catch { fail('malformed JSON text'); }
  exact(input, ROOT_FIELDS, 'recipe');
  if (input.schemaVersion !== 1) fail('unsupported schemaVersion');
  if (input.fictional !== true) fail('fictional must be true');
  for (const n of [input.baseServings,input.targetServings]) {
    if (!Number.isInteger(n) || n < 1 || n > 10000) fail('servings must be integers from 1 to 10000');
  }
  if (!Array.isArray(input.ingredients) || input.ingredients.length < 1 || input.ingredients.length > 32) fail('ingredients must contain 1 to 32 rows');
  const ratio = input.targetServings / input.baseServings;
  const ids = new Set();
  const gaps = [];
  const ingredients = input.ingredients.map(item => {
    exact(item, INGREDIENT_FIELDS, 'ingredient');
    token(item.id);
    if (ids.has(item.id)) fail('ingredient IDs must be unique');
    ids.add(item.id);
    if (item.quantity !== null && (!Number.isFinite(item.quantity) || item.quantity < 0 || item.quantity > 1000000)) fail('quantity must be null or a finite number from 0 to 1000000');
    unit(item.unit); unit(item.targetUnit);
    if (item.unit === 'count' && item.quantity !== null && !Number.isInteger(item.quantity)) fail('input requires an integer count');
    if (item.unit !== null && item.targetUnit !== null && UNITS[item.unit][0] !== UNITS[item.targetUnit][0]) fail('incompatible units; no density or piece-weight inference');
    if (item.sourceRef !== null) token(item.sourceRef);
    if (!['unknown','declared-fixture'].includes(item.allergenState)) fail('unsupported allergenState');
    if (item.allergenState === 'unknown') {
      if (item.allergenTokens !== null) fail('unknown allergens require null tokens');
    } else {
      if (item.sourceRef === null) fail('declared fixture allergens require a fictional source');
      if (!Array.isArray(item.allergenTokens) || item.allergenTokens.length > 16) fail('declared tokens require an array of at most 16 entries');
      item.allergenTokens.forEach(token);
      if (new Set(item.allergenTokens).size !== item.allergenTokens.length) fail('allergen tokens must be unique');
    }
    const gap = code => gaps.push({ingredientId:item.id,code});
    if (item.quantity === null) gap('quantity-unknown');
    if (item.unit === null) gap('unit-unknown');
    if (item.targetUnit === null) gap('target-unit-unknown');
    if (item.sourceRef === null) gap('source-unknown');
    if (item.allergenState === 'unknown') gap('allergens-unknown');
    let scaledQuantity = null;
    if (item.quantity !== null && item.unit !== null && item.targetUnit !== null) {
      scaledQuantity = item.quantity * ratio * (UNITS[item.unit][1] / UNITS[item.targetUnit][1]);
      if (!Number.isFinite(scaledQuantity) || scaledQuantity > 10000000000000
          || (item.quantity > 0 && scaledQuantity === 0)) fail('result outside arithmetic range');
      // Normalise negative zero, but never round fractional values or infer kitchen measures.
      if (scaledQuantity === 0) scaledQuantity = 0;
      if (item.targetUnit === 'count' && !Number.isInteger(scaledQuantity)) gap('fractional-count-review');
    }
    return {
      id:item.id,
      scaledQuantity,
      unit:item.targetUnit,
      amountState:scaledQuantity === null ? 'unknown' : 'calculated',
      sourceState:item.sourceRef === null ? 'unknown' : 'declared-fictional',
      sourceRef:item.sourceRef,
      allergenState:item.allergenState,
      declaredAllergenTokens:item.allergenTokens === null ? null : [...item.allergenTokens],
    };
  });
  return {
    schemaVersion:1,
    kind:'fictional-arithmetic-only',
    state:gaps.length ? 'calculated-with-unknowns' : 'arithmetic-complete',
    ratio,
    ingredients,
    gaps,
    boundary:{productFactsVerified:false,allergenSafetyAssessed:false,nutritionAssessed:false,preparationAssessed:false,providerExecution:false},
  };
}
