# Synthetic research claim card

`checkExperimentCard(input)` in `experiment-card.mjs` is a pure offline data
checker. It performs no collection, statistics, provider calls or authorization.
It cannot verify that supplied text is true, meaningful, preregistered externally,
or free from embedded significance/causality rhetoric. Human review is required.
No university endorsement or actual research finding is claimed.

All keys below are required and exclusive, including nested keys. Objects must
have Object.prototype; arrays must have Array.prototype, contiguous enumerable
data entries and no extra keys. Accessors, symbols, hooks, unsupported prototypes,
nonfinite numbers, undefined and non-JSON types are rejected without invoking
caller methods. Proxies are unsupported, not a sandbox boundary. Depth is bounded
at 12, arrays at 100 entries, objects at 30 keys, text at 2000 characters.

```js
import {checkExperimentCard} from './experiment-card.mjs';
checkExperimentCard({
  claimType: 'designed-experiment',
  hypothesis: 'A blue label reduces fictional puzzle sorting time.',
  outcome: {metric: 'sorting time', unit: 'seconds', window: 'one synthetic puzzle'},
  control: {comparison: 'grey label', allocation: 'randomized'},
  confounds: ['Practice may change sorting time.'],
  decision: {
    preregistered: true,
    minimumDifference: 0,
    direction: 'decrease',
    rule: 'Compare group means after the fixed sample; no optional stopping.'
  },
  uncertainty: ['No observations collected; effect and generalization unknown.'],
  sample: {treatment: 20, control: 20}
});
```

Text must be nonblank; confounds and uncertainty are nonempty text arrays.
Sample counts must be positive safe integers no greater than 1,000,000 per arm;
this validates counts, not statistical power. `minimumDifference` is finite and
nonnegative in the outcome unit; zero is accepted and is distinct from missing
or null. `direction` is `increase` or `decrease`; allocation is `randomized` only.
The rule is a supplied, explicitly preregistered plan, never an evaluated result.

`claimType` accepts `association`, `hypothetical-causal`, or
`designed-experiment`. Every accepted card requires the same complete planning
fields. The first two retain their classification with status `claim-only`;
the third returns `complete-plan`. Missing or malformed input returns `rejected`
with a generic issue and null classification. All outputs always have
`causalFinding: false` and `authorization: false`. Supplied PASS, p-values,
significance flags, causal guarantees and any other unknown keys are rejected.
There is no findings input or significance calculation. An association is never
promoted into a causal finding; even a complete designed experiment is only a plan.
