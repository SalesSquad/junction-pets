# Fictional CPU/GPU protocol comparison

`compareBenchmarkProtocols(jsonText)` in `benchmark-protocol.mjs` checks declared
protocol parity before showing arithmetic over a tiny fictional example. It
does not detect hardware, read an Intel account, execute a workload, validate
output correctness or establish real performance. This independent source helper
is not an Intel tool or endorsement and is not a new hosted/MCP capability.

## Closed input contract

Input is primitive JSON text of at most 65,536 UTF-8 bytes. Ordinary `JSON.parse`
behavior applies: duplicate object members use the last value. No executable
object hooks or coercion are accepted; unknown keys and malformed data produce
`invalid` with no partial comparison. This is not canonical JSON or attestation.

The root has exactly `schemaVersion:1`, `kind:"fictional-benchmark-plan"`,
`baseline` and `candidate`. Each run has exactly a unique `id`, `device`
(`cpu` or `gpu`), `protocol`, `outputCheck` and `samples`. Device labels are
fictional classes, not identified hardware; they intentionally need not match.
Run IDs are distinct. IDs are 1–64 lowercase ASCII letters/digits/hyphens,
starting with a letter; the reserved literal `unknown` is rejected.

Every protocol field is mandatory, and every one may be explicit `null` for
unknown. Missing is invalid. Non-null values obey:

| Field | Meaning and bound |
| --- | --- |
| `workloadId` | Exact supplied workload identity label |
| `inputId` | Exact supplied input identity label |
| `outputSpecId` | Exact supplied expected-output specification label |
| `runtimeId` | Exact supplied runtime/version identity label |
| `configId` | Exact supplied configuration identity label, including precision/concurrency/threads/measurement scope |
| `batchSize` | Integer 1–1,024 |
| `warmupIterations` | Integer 0–100,000; zero is known zero, not unknown |
| `repetitions` | Integer 1–64 |
| `metric` | `latency` or `throughput` |
| `unit` | `ms` or `s` for latency; `items/s` for throughput |

The five identity fields use the ID syntax above or null. Equal labels are only
a declaration of parity: aliases, incorrect labels, actual configuration or
different underlying data cannot be discovered from this input. All controls
hidden by `configId` require separate real-world validation before benchmarking.
Matching this limited format is not sufficient experimental design by itself.

`outputCheck` is `match`, `mismatch` or null, all merely supplied declarations.
`samples` is null (unknown) or an array of 0–64 finite numbers from 0 to 1e9.
Zero is a known fictional value; an empty array is known missing samples, not an
executed zero-latency benchmark. Per-sample null, strings and nonfinite values are
invalid. A known repetition count must equal that run's sample count; unknown
counts cannot support comparison. Extra measurement/execution claims fail.

## Result semantics

Known differences in any protocol field except units, or a declared output
mismatch, yield `incomparable`. Unknown fields, missing samples or a sample-count
disagreement yield `insufficient-evidence` unless a known mismatch takes priority.
Only complete, matching declarations yield `comparable-declarations`.
No other distinction, model evaluation, hardware suitability or winner is inferred.

Sorted issues identify `protocol-mismatch:<field>`, `output-mismatch:<run>`,
`unknown:<run>.protocol.<field>`, `unknown:<run>.outputCheck`,
`unknown:<run>.samples` and `sample-count:<run>`. Invalid input returns exactly
one `malformed-or-unsupported-plan` issue and null `declaredComparison`.

`declaredComparison` is null for every blocked/invalid result. Otherwise it
contains the shared metric, normalized unit, two arithmetic sample means and
`candidateMinusBaseline`. Latency seconds convert to milliseconds; throughput
retains items/s. No cross-metric conversion, speedup ratio, statistical inference,
confidence interval, ranking or winner is computed. Floating-point arithmetic is
ordinary JavaScript arithmetic; the finite bounds prevent overflow.

Every result has `basis:"supplied-fictional-declarations"` and false flags for
`benchmarkExecuted`, `hardwareVerified`, `performanceVerified`,
`provenanceAuthenticated` and `authorization`. A returned mean is arithmetic over
invented inputs, not a measured result. The six authored model eval cases remain
unchanged and separate from these source tests.

## Offline example

`example.json` compares invented `[2,4]` milliseconds with `[0.001,0.003]`
seconds and returns means 3 and 2 milliseconds, difference -1. This is not an
Intel CPU/GPU measurement or a speed claim.

```sh
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {compareBenchmarkProtocols} from "./pets/intel/benchmark-protocol.mjs"; console.log(compareBenchmarkProtocols(readFileSync("pets/intel/example.json", "utf8")));'
node --test tests/pet-intel.test.mjs
```

The next bounded source step is an invented repeated-run/variance review with
explicit uncertainty, separately designed before any real benchmark is admitted.
