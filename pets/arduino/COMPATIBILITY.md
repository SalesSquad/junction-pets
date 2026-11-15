# Fictional pin and power review

`compatibility.mjs` exports `reviewCompatibility(data)`. The invented, redacted
examples are teaching data, not specifications for any Arduino or real component.
The result explains conflicts and declared current budgets; it does not authorize
an action or certify physical safety. No new provider facts, source retrieval or
source-review date are claimed.

## Choose an input format

- `example.json` retains the legacy format: exactly `board` and `sensors`, each
  with `voltageMv` for one shared supply-and-logic voltage. Its result identifies
  `inputSchema: "legacy-single-voltage"`.
- `example-v2.json` uses exactly `schemaVersion: 2`, `board` and `sensors`.
  Board and sensor records replace `voltageMv` with separate `supplyVoltageMv`
  and `logicVoltageMv`. Its result identifies `inputSchema: "split-voltage-v2"`.
  Each sensor's supply and logic declarations must independently match the board.

Both formats require all the other keys shown in their examples. Unknown keys,
unknown versions, mixed voltage fields and split fields without version 2 are
invalid. There is no implicit voltage conversion or inferred level shifter.

## Accepted data and limits

Records may use the
ordinary Object prototype or null prototype. Arrays must be dense ordinary
arrays with only indexed enumerable data properties and their length. Accessors,
hooks, symbols, functions, cycles, unsupported prototypes and nonfinite numbers
are rejected without calling input methods or getters. Node's `util.types.isProxy`
rejects transparent, trapping and revoked Proxies before reflection, at every
visited structural position. Unknown record keys are rejected before reading
property descriptors or traversing child values. Use parsed JSON for interchange.

All electrical values are integer **millivolts** (`*VoltageMv` or legacy
`voltageMv`, positive) or
**milliamps** (`*Ma`, nonnegative), at most 1,000,000,000. No implicit conversions,
alternative units or fractional values. `pinCount` must equal the nonempty pin
array length. Arrays have at most 100 entries, nesting at most 10, records at most
20 keys. A shared request budget allows at most 4096 visited values (root and
scalars included) and 8192 own properties (array length included); repeated
references consume the budget on each visit. Exhaustion yields `invalid` and no
totals. Limits bound recursive validation and copying; enumerating an already
allocated object's own keys still costs work proportional to its key count.
IDs are 1–40 ASCII letters, digits or hyphens. Board pin IDs and sensor
IDs must be unique. Modes are exactly `input`, `output`, `analog-input`, expressed
from the board's perspective. Board mode lists contain no duplicates. A pin can
be allocated only once across all sensors; shared buses are outside this slice.

Each sensor declares its voltage requirements, a common-ground boolean and
supply current **excluding** its separately declared signal-pin current. The
board's `powerLimitMa` covers supply plus signal current; `pinLimitMa` caps each
signal; `totalPinLimitMa` caps their sum. These are fictional modeling conventions,
not assumptions about real electrical behavior. Despite its retained legacy
name, `powerLimitMa` is a current limit in mA, not power in watts. Each applicable
voltage must exactly match and
each requested mode must appear in that board pin's declared modes.

## Read the review

Only the three limit fields may be null: each null produces an explicit unknown
and `needs-review`. Missing fields are `invalid`; zero is a known limit or known
zero demand. False ground, unknown/duplicate pin, voltage/mode mismatch and any
exceeded limit yield `needs-review`. Malformed/unsupported data yields `invalid`
with no calculated totals. Only no issues yields `consistent` (with declarations).

The existing `issues` strings remain available. `diagnostics` adds a field path,
actual value, expected constraint and a proposed correction for each problem.
Malformed input retains `issues: ["malformed-or-unsupported-input"]`, with a more
specific diagnostic. Unsafe values such as objects, getters or proxies are never
returned as caller objects or evaluated to produce a diagnostic.

For valid-shaped input, `budgets` shows:

- `total`: combined supply-and-signal demand, `powerLimitMa` and headroom.
- `signal`: summed signal demand, `totalPinLimitMa` and headroom.
- `pins`: each allocated pin's combined declared demand, `pinLimitMa` and headroom.

Each budget has `demandMa`, `limitMa` and `headroomMa`; pin entries also have `pin`.
Headroom is limit minus demand. Null limit means null headroom, never a made-up
zero. Negative headroom exposes oversubscription. Duplicate-pin demands are
aggregated for arithmetic but still cause a review issue. Unknown-pin budget
entries describe supplied demand only; they do not establish a board connection.
Malformed input has `totals: null` and `budgets: null`.

Supply mismatches retain `voltage-mismatch:<sensor-id>`; a split-format logic
mismatch adds `logic-voltage-mismatch:<sensor-id>`. `authorization` and
`safetyCertification` are always false, including for a consistent result.

## Worked fictional example

In `example-v2.json`, board and sensors declare 5000 mV supply and 3000 mV logic.
Each corresponding value matches; neither is treated as a substitute for the
other. Both sensors declare ground and distinct supported pins.

| Declared budget | Demand | Limit | Headroom |
| --- | --- | --- | --- |
| Supply + signal | 8 + 6 + 1 + 2 = 17 mA | 30 mA | 13 mA |
| Signal total | 1 + 2 = 3 mA | 6 mA | 3 mA |
| P0 signal | 1 mA | 4 mA | 3 mA |
| P1 signal | 2 mA | 4 mA | 2 mA |

The review is `consistent`, with `totals: {supplyMa:14, signalMa:3}`. Setting the
total current limit to 16 produces `power-oversubscribed` and headroom −1 mA;
setting it to null produces `unknown-powerLimitMa` and null headroom. Deleting
the field is invalid. These are declaration checks, not measured electrical data.

Try offline from repository root:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {reviewCompatibility} from "./pets/arduino/compatibility.mjs"; console.log(reviewCompatibility(JSON.parse(readFileSync("pets/arduino/example-v2.json", "utf8"))));'
node --test tests/pet-arduino.test.mjs
node pets/arduino/mutation-check.mjs
```

The mutation checker makes temporary source copies with selected checks disabled
and verifies that relevant tests fail. Its scoped, finite artificial faults test
the sensitivity of those assertions; mutation results are not comprehensive
correctness or real-device evidence.

Unknowns include whether any declarations are true, real revisions/ratings/wiring,
transients, tolerances, thermal behavior and actual behavior. Splitting voltage
fields does not model level shifting, signal direction, current physics, firmware,
buses, alternate supplies or real hardware. No device access, energizing
instruction, firmware flashing or physical test is provided.
Next: independently review these semantics and use exact official documentation
for a separately authorized, exact-board desk review before extending the model.
