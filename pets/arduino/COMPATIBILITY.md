# Fictional pin and power review

`compatibility.mjs` exports `reviewCompatibility(data)`. `example.json` is invented,
redacted teaching data, not specifications for any Arduino or real component.
No new provider facts, source retrieval or source-review date are claimed.

The input has exactly `board` and `sensors`. Their required keys and nested pin
keys are shown in the example; unknown keys are rejected. Records may use the
ordinary Object prototype or null prototype. Arrays must be dense ordinary
arrays with only indexed enumerable data properties and their length. Accessors,
hooks, symbols, functions, cycles, unsupported prototypes and nonfinite numbers
are rejected without calling input methods or getters. JavaScript Proxies are
outside the documented plain-data contract; do not pass executable objects.
Use parsed JSON for the supported interchange path.

All electrical values are integer **millivolts** (`voltageMv`, positive) or
**milliamps** (`*Ma`, nonnegative), at most 1,000,000,000. No implicit conversions,
alternative units or fractional values. `pinCount` must equal the nonempty pin
array length. Arrays have at most 100 entries, nesting at most 10, records at most
20 keys. IDs are 1–40 ASCII letters, digits or hyphens. Board pin IDs and sensor
IDs must be unique. Modes are exactly `input`, `output`, `analog-input`, expressed
from the board's perspective. Board mode lists contain no duplicates. A pin can
be allocated only once across all sensors; shared buses are outside this slice.

Each sensor declares a single required voltage, a common-ground boolean and
supply current **excluding** its separately declared signal-pin current. The
board's `powerLimitMa` covers supply plus signal current; `pinLimitMa` caps each
signal; `totalPinLimitMa` caps their sum. These are fictional modeling conventions,
not assumptions about real electrical behavior. Voltage must exactly match and
each requested mode must appear in that board pin's declared modes.

Only the three limit fields may be null: each null produces an explicit unknown
and `needs-review`. Missing fields are `invalid`; zero is a known limit or known
zero demand. False ground, unknown/duplicate pin, voltage/mode mismatch and any
exceeded limit yield `needs-review`. Malformed/unsupported data yields `invalid`
with no calculated totals. Only no issues yields `consistent` (with declarations).
Neither result authorizes action or certifies physical safety.

Worked example: supply = 8 + 6 = 14 mA, signal = 1 + 2 = 3 mA;
total = 17 mA against declared 30 mA. Signal total 3 ≤ 6 and each pin ≤ 4.
Both sensors declare 3000 mV, ground and distinct supported pins. Result:
`consistent`, totals `{supplyMa:14, signalMa:3}`, authorization and safety
certification both false. Setting power limit to 16 yields `power-oversubscribed`;
setting it to null yields `unknown-powerLimitMa`; deleting it yields `invalid`.

Try offline from repository root:

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {reviewCompatibility} from "./pets/arduino/compatibility.mjs"; console.log(reviewCompatibility(JSON.parse(readFileSync("pets/arduino/example.json", "utf8"))));'
node --test tests/pet-arduino.test.mjs
```

Unknowns include whether any declarations are true, real revisions/ratings/wiring,
transients, tolerances, thermal behavior and actual behavior. This first slice
does not model firmware, buses, alternate supplies or real hardware. No device
access, energizing instruction, firmware flashing or physical test is provided.
Next: independently review these semantics and use exact official documentation
for a separately authorized, exact-board desk review before extending the model.
