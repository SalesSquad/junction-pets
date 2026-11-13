# Synthetic retargeting metadata checker

`checkRetargeting` in `retargeting.mjs` compares invented declarations offline.
It does not read motion, retarget a rig, export a file, verify supplied facts,
authorize actions, or prove animation/export quality. No provider capability
is inferred from a format name. Both sides must declare the exact requested
format; no built-in Rokoko format-support table is asserted.

Input is a plain JSON-like record with required `source`, `target`, `mapping`,
`exportFormat` and optional finite nonnegative `sourceDistance`. Each skeleton
requires nonempty unique `bones` and `formats` arrays of case-sensitive IDs
(ASCII letter followed by at most 127 letters, digits, `_ . : -`),
`handedness` (`left`, `right`, `unknown`), `upAxis` (`X`, `Y`, `Z`, `unknown`)
and `units` (`m`, `cm`, `mm`, `unknown`). Each mapping entry has only `source`
and `target` bone IDs. Every bone on both sides must appear exactly once.
This conservative full-map policy does not infer optional or helper bones.

Unknown keys, null fields, undefined, nonfinite numbers, cycles, unsupported
prototypes, accessors, symbols, hidden properties and irregular arrays are
malformed. Validation does not invoke input methods, getters or toJSON.
Missing distance omits target distance; zero converts to zero; null is malformed.

Results: `malformed` for invalid data, `incompatible` for duplicate/missing/
nonexistent mappings, coordinate mismatch or absent format intersection,
`unknown` for explicitly unknown metadata, otherwise `compatible-declared`.
Incompatibility dominates unknown. Coordinate differences are never silently
corrected. Scale is emitted only for compatible declarations, using source
metres per unit divided by target metres per unit; overflow is malformed.

## Fictional example

```js
import {checkRetargeting} from './retargeting.mjs';
checkRetargeting({
  source: {bones:['hip','foot'], handedness:'right', upAxis:'Y', units:'cm', formats:['fictional-motion']},
  target: {bones:['root','toe'], handedness:'right', upAxis:'Y', units:'m', formats:['fictional-motion']},
  mapping: [{source:'hip',target:'root'}, {source:'foot',target:'toe'}],
  exportFormat:'fictional-motion', sourceDistance:125
});
// compatible-declared; scaleFactor 0.01; targetDistance 1.25
```

The next manual check is to verify actual rig documentation, rest poses, root
motion and a short rendered/exported test in the intended application under
separate authorization. This module cannot establish those results.
