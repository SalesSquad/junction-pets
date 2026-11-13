# Public and synthetic companion behavior capture

`public-behavior-capture.mjs` captures real responses from an already authorized
installed Claude CLI for the existing 204 repository cases across all 34
companions. It is an optional development experiment. It never changes the
canonical Chibi host runner or its authorization requirements.

The default is an offline preview. No model runs, output files, provider
connections or costs are created by preview or deterministic unit tests.

```sh
node --test services/eval-runner/public-behavior-capture.test.mjs
node services/eval-runner/public-behavior-capture.mjs \
  --source-commit FULL_40_CHARACTER_COMMIT --pet all --max-cases 34
```

Replace `FULL_40_CHARACTER_COMMIT` with the independently verified exact GitHub
commit that contains this harness. Preview validates its format and freezes the
local package data; **only execution** also requires matching local `HEAD`, a
clean working tree including untracked files, and the exact repository origin.
A preview is not proof that local files match a remote commit.

## Run a bounded pilot

Verify the existing provider account, model availability and intended budget.
Commit the harness and source first. Six Aiven cases plus six AfterQuery cases
form the first 12-response pilot:

```sh
node services/eval-runner/public-behavior-capture.mjs \
  --source-commit FULL_40_CHARACTER_COMMIT --pet aiven \
  --max-cases 6 --model haiku --max-budget-usd 0.25 --execute
node services/eval-runner/public-behavior-capture.mjs \
  --source-commit FULL_40_CHARACTER_COMMIT --pet afterquery \
  --max-cases 6 --model haiku --max-budget-usd 0.25 --execute
```

For a control, repeat each exact command with `--persona none`. This keeps the
case and rubric hashes unchanged but excludes companion instructions from the
model prompt; request and plan hashes differ. The default `--persona pet` sends
the exact frozen companion instructions. Compare responses under the same
model alias and independent rubric review before claiming the companion adds
value. The control is a separate run, never a replacement for a failed result.

Supported aliases are `haiku`, `sonnet` and `fable`. These request an alias;
they do not verify the backend version. Provider-reported `modelUsage` keys
and invocation/session ID are retained when present, without attesting them.
No automatic provider, alias or account fallback occurs.

To select one case, add its complete existing ID, for example
`--pet aiven --case junction.aiven/no-provider-connection --max-cases 1`.
`--pet all --max-cases 34` takes one case from each company before repeating a
company. `--pet all --max-cases 204` selects all definitions. Pilot failures
should be inspected and fixed before expanding to that full run.

## Reproducibility, isolation and bounds

- Inputs come only from validated repository `pet.json`, `AGENTS.md`,
  `STORY.md` and `evals.json` files. There is no CLI option to supply arbitrary
  uploaded prompts, source paths, scripts or transports. Use only the authored
  public/synthetic source; do not add personal or customer data to a case.
- The existing manifest producer supplies the case, collection, package and
  instruction hashes. Each captured request additionally binds its exact system
  prompt, model alias, persona mode and prompt bytes. Rubrics are retained for
  review, excluded from model prompts, and never graded by the responding model.
- Source and frozen plan are rechecked immediately before each invocation.
  Mutation, timeout, missing CLI, malformed response or reported budget excess
  stops the batch. Remaining case IDs are recorded as unattempted. There is no
  automatic retry. A new run gets a fresh UUID and preserves earlier records.
- Calls are sequential, at most 204 cases. Each has a 90-second default timeout
  (`--timeout-ms`, 1,000–300,000), a 100,000-byte response limit and a bounded
  process buffer. `--max-budget-usd` is per invocation (default 0.25, maximum 10).
  Preview reports the maximum requested total; CLI budget enforcement and
  reported cost are not independent billing proof. Unknown cost remains null.
- The CLI runs from a new empty temporary directory with an explicit system
  prompt, `--safe-mode`, `--restricted`, `--setting-sources ''`, `--tools ''`,
  `--strict-mcp-config`, `--no-chrome`, `--no-session-persistence` and
  `--permission-mode dontAsk`. This requests disabled customizations and no
  tools, rather than inheriting repository `CLAUDE.md`, global memory, hooks or
  MCP/browser access. Provider/admin safeguards still apply. Installed CLI
  versions must support these flags; a refusal is a failed attempt, not a reason
  to remove isolation or bypass confirmation.

## Private evidence and independent review

Execution writes one new directory beneath ignored
`dist/evals/public-behavior/<run-uuid>/`, containing:

| File | Contents |
| --- | --- |
| `plan.json` | Exact source-bound public/synthetic input, persona mode and rubrics |
| `case-NNN.json` | Exact model response, hashes, timing, reported model/cost metadata or sanitized failure code |
| `receipt.json` | Attempt/result counts, remaining cases, raw record-file digests and explicit limits |

Run directories use mode 0700; files use 0600 and exclusive creation. Output
cannot be redirected by a CLI flag, and a symlink escaping the repository is
rejected. Terminal output contains a summary and evidence path, never response
text or provider stderr. A reported budget excess retains its exact response
for review, marks the attempt failed and stops further calls. Transcripts and
internal evidence are excluded from source commits and public/plugin exports.

An independent reviewer must inspect every positive and negative criterion
against the exact response bytes. A captured response has `adjudication:null`:
it is **not a passed evaluation**. Keep failing answers and review disagreement.
The existing [`docs/BEHAVIOR_EVALS.md`](../../docs/BEHAVIOR_EVALS.md) submission
contract can represent a subsequent independent review; this capture format is
deliberately not silently accepted as an adjudicated submission.

Receipts always retain `qualifiedPasses:0`, `providerInvocationsVerified:0`,
`chibiHostVerified:false`, `signedProviderReceiptVerified:false` and
`independentAdjudicationVerified:false`. They prove only a local CLI observation
with source/input/output binding. They do not certify Chibi deployment, live
Aiven account operations, recipient adoption, saved learning, or a signed
provider execution. Injected unit-test transports are explicitly labeled
`synthetic-test-only` and never model execution.
