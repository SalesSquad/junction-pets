# Fictional recipe arithmetic contract

`scaleFictionalRecipe(jsonText)` in [recipe-scale.mjs](recipe-scale.mjs) is a pure,
offline source helper for an invented arithmetic fixture. It is not a nutrition,
allergen, supplier, recipe-quality or food-safety validator. No actual product,
label, person, menu or company fact is assessed. It is not a registered runtime
tool, ordering API, model result or official Valio Aimo functionality.

## Input

Accept a primitive JSON string of at most 32,768 UTF-8 bytes. Use ordinary
`JSON.parse`: duplicate object keys use the last value; numeric literals use
JavaScript binary64 semantics. The helper does not claim lossless decimal or
duplicate-key validation. Malformed JSON, unsupported types, missing fields and
extra fields throw `TypeError`. No executable objects, hooks or accessors are
accepted as an input interface.

The root has exactly `schemaVersion:1`, `fictional:true`, `baseServings`,
`targetServings`, and `ingredients`. Both serving counts are integers 1–10,000.
The ingredient array contains 1–32 records, with unique `id` values and exactly:

| Field | Accepted value |
| --- | --- |
| `id` | Lowercase token beginning `fictional-`, then hyphen-separated ASCII letters/digits; at most 64 characters, no whitespace |
| `quantity` | `null` for unknown, or finite number 0–1,000,000; a known `count` input must be an integer |
| `unit`, `targetUnit` | Explicit `g`, `kg`, `ml`, `l`, `count`, or `null` for unknown |
| `sourceRef` | `null`, or the same fictional-token format; a declaration only, never a resolved source or verified label |
| `allergenState` | `unknown` or `declared-fixture`, never `verified`, `safe` or `free-from` |
| `allergenTokens` | `null` when unknown; otherwise 0–16 unique fictional tokens and a non-null fictional `sourceRef` are required |

Even an empty declared token array is only invented fixture content: it never
proves absence of an allergen. No real allergen names, product IDs, URLs, prices,
nutrition fields or safety claims belong in this input.

## Calculation and result

The visible factor is `targetServings / baseServings`. Each known amount is
`quantity × factor × unitConversion`. Only mass ↔ mass (`g`, `kg`), volume ↔
volume (`ml`, `l`) and count ↔ count are compatible. No density, piece weight,
household measure, yield, cooking duration or temperature is inferred. An
incompatible known pair throws even if quantity is unknown. An absent unit never
comes from another ingredient or the desired output unit.

Arithmetic is bounded to a finite result at most 10^13. Positive quantities that
underflow to numeric zero throw. Other binary64 rounding is retained; negative
zero normalises to zero. A fractional result for `count` is returned unchanged
and adds `fractional-count-review`; the helper never silently rounds a portion.

The output is `kind:fictional-arithmetic-only`, with the ratio, one result per
input ingredient in original order, gaps and constant false boundary flags.
`amountState` is `calculated` or `unknown`; `scaledQuantity:null` is distinct from
known zero. `unit` reports only the requested unit, possibly null. Provenance and
allergen declarations remain declared or unknown, never authenticated.

Gaps, in per-ingredient order, are `quantity-unknown`, `unit-unknown`,
`target-unit-unknown`, `source-unknown`, `allergens-unknown`, then any
`fractional-count-review`. `state:arithmetic-complete` means only that no such
gap was found. `calculated-with-unknowns` preserves one or more gaps. Neither
state qualifies actual ingredients, nutrition, allergen safety, preparation or
provider execution: all five output boundary flags are always false.

## Reproduction and ownership

[The invented example](examples/fictional-recipe.json) scales an arithmetic
fixture from 8 to 30 portions. It deliberately includes known zero, unknown
quantity and unknown source/allergen information. Run:

```sh
node --test tests/pet-valio-aimo.test.mjs
```

Stable owner: `junction-dev-valio-aimo`. Work ID:
`junction.valio-aimo.capability-proof`. Existing six authored model-evaluation
definitions remain unchanged and unexecuted. Future work may add explicit,
fictional rounding policy comparisons; that proposal is not started and must
remain distinct from real kitchen/product acceptance.
