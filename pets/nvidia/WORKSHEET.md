# Offline synthetic rendering comparison

Independent educational companion exercise; no NVIDIA endorsement or official
benchmark. No GPU run or measured performance is claimed. All example timings
are invented **authored estimates**, not observations. No provider-specific
performance or compatibility claim is made; the existing NVIDIA Developer link
is navigation only, not evidence for these numbers.

Run from the repository root:

```js
import {compare} from './pets/nvidia/comparability.mjs';
const baseline = {
  workload:'synthetic-room-v1', kind:'gaussian-splat', sceneCount:1,
  objectCount:1000, inputDigest:'a'.repeat(64), width:640, height:480,
  precision:'fp32', quality:'exact-reference-v1', hardware:'fictional-gpu-A',
  software:'fictional-renderer-v1', timingScope:'render-only-synchronized',
  warmup:0, repeats:3, unit:'ms', timings:[10,12,14],
  evidence:'authored-estimate', provenance:'worksheet author'
};
const candidate = {...baseline, hardware:'fictional-gpu-B', timings:[5,6,7]};
console.log(compare(baseline,candidate));
// comparable:true, ratio:2, basis:'authored-estimate',
// provenance:'unverified', measuredPerformanceVerified:false
```

The ratio is baseline mean time / candidate mean time, equivalent to the ratio
of sums with equal repeat counts. Here 12 / 6 = 2 is **estimate arithmetic**,
never a measured speedup. A ratio below 1 means the candidate's supplied time
is larger. There is no statistical significance or correctness conclusion.

Use one row per configuration. Record scene identity/version, scene and object
counts (objects mean splats for this exercise), input SHA-256 digest, pixel
resolution, precision, exact quality/output criterion, hardware and software
versions, timing scope including synchronization and transfers, excluded warmup
count, repeats and one elapsed millisecond value per repeat. Hardware can differ
for a hardware comparison; all other protocol/workload fields must match.
Software comparisons need a separately reviewed protocol, not this strict slice.

`3d-render` and `gaussian-splat`, and fp16/fp32/fp64 are worksheet vocabulary,
not assertions that any device supports them. All identity and provenance
strings are caller declarations. Matching strings do not establish actual
quality equivalence, execution, digest authenticity or hardware identity.

`authored-estimate` and `supplied-measurement` cannot be mixed. Supplied
measurements remain unverified even with a provenance note. No field can mark
evidence verified or assert speedup. Unknown fields, missing fields, nulls,
invalid numbers, seconds/FPS, sparse samples, nonpositive times, subnormal times
and overflow are rejected. Explicit zero warmup is valid; zero counts,
dimensions and repeats are invalid. This conservative slice requires both
counts and digest; it does not infer missing inputs or convert units.

Next step: review the declared quality criterion and measurement protocol with
the human owner before collecting any separately authorized evidence. This
offline checker never authorizes collection or invokes a GPU/provider.
