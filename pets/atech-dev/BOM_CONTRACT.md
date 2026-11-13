# Fictional BOM checker, first slice

`checkBom(input)` in `bom-checker.mjs` performs an offline synthetic consistency
review. It verifies supplied declarations against each other; it cannot verify
that those declarations are true. It is neither authorization nor electrical
safety certification. It gives no instruction to power hardware. No real product
or hardware specifications, provider calls, live accounts or devices are used.

## Exact input

Only plain JSON-like data is accepted: records with Object.prototype or null
prototype, dense ordinary arrays, finite numbers, strings, booleans and null.
Schema fields below further restrict these types. Own enumerable data properties
only; no accessors, symbols, functions, toJSON hooks, cycles, unsupported
prototypes, sparse arrays or extra array properties. Proxies are outside the
contract: JavaScript cannot inspect a Proxy without invoking its traps. Callers
must supply ordinary data, not executable objects. No caller methods are called.
Depth is at most 20, visited values at most 20,000 and each array at most 1,000.
All unknown keys are rejected, including at nested levels.

Top level has exactly `board` and `parts`. Board permits `voltage`, `current`,
`interfaces`. Every part requires `id`, `quantity`, `rating` and permits
`voltage`, `current`, `requirements`. IDs and interface names match
`[a-z][a-z0-9-]{0,63}`. Part IDs, board interface names and each part's requirement
names must be unique. Quantities are positive safe integers.

- Voltage is exactly `{min, max, unit}` with nonnegative safe integer endpoints,
  min <= max and unit `V` or `mV`.
- Current is exactly `{value, unit}` with nonnegative safe integer value and
  unit `A` or `mA`. Board current is its declared total capacity; part current
  is its declared per-instance maximum demand.
- Board interfaces are `[{name, pins}]`; requirements are `[{interface, pins}]`.
  Pins are nonnegative safe integers. Pins represent dedicated capacity consumed
  per instance, not shared buses, wiring identities or alternate pin functions.
- Rating is exactly `known` or `unknown`. It is a supplied assertion, not a
  source verification. Missing or null rating/ID/quantity is malformed.

Missing board or part specifications and explicit null specifications produce
different `missing:*` / `null:*` incomplete issues. Unknown ratings produce an
`unknown:rating` issue. Explicit zero current, pins or voltage endpoints remain
known numeric declarations. Empty requirements declare no interface demand;
empty parts is incomplete. Malformed supplied specifications throw TypeError
even when their rating is unknown. No default ratings or silent unit conversion
guesses are used. Integer V/A values normalize to mV/mA; fractional quantities
must be expressed in the smaller supported unit. Unsafe normalization, products
or sums throw before a review result is returned.

## Result and interpretation

The complete board voltage range must fit within each declared part range.
Current and dedicated pins are summed across quantities and parts. Missing
interfaces conflict even if their requested pin count is zero. Exact capacity
and voltage boundaries are accepted. Known conflicts are retained even if
another specification is incomplete; partial sums can prove an excess, but
cannot prove that capacity suffices.

`status` is `incomplete` if any required specification/rating is unavailable,
otherwise `incompatible` if conflicts exist, otherwise `internally-consistent`.
`parts` carries each ID, supplied rating, review status and local incomplete
issues. Board incomplete issues also prevent every part from receiving a
complete status. `conflicts` retains voltage, current, interface and pin findings
with affected part IDs. `totalCurrentMA` is null for incomplete reviews, otherwise
the exact integer total (including zero). This does not cover transients,
polarity, thermal limits, component authenticity, signal behavior or safety.

Run `node --test tests/pet-atech-dev.test.mjs`. Tests use invented, redacted data.
The six authored behavioral eval definitions remain unchanged and unexecuted.
The generated skills-only plugin contains companion instructions, not this
executable module; no MCP tool or host integration is added by this slice.

Next company action: independently review the dedicated-pin and current-budget
assumptions and final test receipts before root integrates this bounded slice.
