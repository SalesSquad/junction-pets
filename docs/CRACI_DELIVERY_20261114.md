# CRACI delivery and retained evidence — 14 November 2026

Work ID: `J26-CRACI-DELIVERY-20261114`. Implementation base:
`1283d38c0352055fb487f0c2d7af06f86a915f9b`. Shared workflow/source ownership:
[issue 80 comment 6874318759](https://github.com/SalesSquad/junction-pets/issues/80#issuecomment-6874318759).

The owner approved implementing the reviewed source-selection, lightweight CI,
artifact-retention and experiment-registry improvements, plus one corrected
MariaDB runtime and the existing Meta browser acceptance journey. This task
reserves at most **EUR10 of the existing credit** within the already approved
EUR1,000 campaign. No top-up, new provider, production load or deployment.
The existing stop at **2026-11-15 17:00 UTC / 19:00 Helsinki** and repository
variable `CRACI_CREDIT_WINDOW_OPEN` remain effective. Portfolio PR Recovery is
the sole integrator.

## What changed

- `craci-pilot.yml` admits only explicit `workflow_dispatch` qualifications.
  Ordinary PR and main commits no longer trigger a full suite. The full
  portable suite remains a deliberate milestone workload.
- A small CRACI admission job resolves full immutable source SHAs and a bounded
  matrix before expensive cells are allocated. An unsupported product no
  longer silently selects all products. A source override requires one product
  where the matrix contains independent implementations.
- Native and MariaDB jobs now honor `source_sha`; cache, Council and Meta seed
  jobs also use the same resolved source for checkout, expectations and receipt.
  Historical fallback pins remain available and are explicitly recorded.
  Tieto selects official sponsor pins with `sponsor_revision` and rejects an
  unrelated `source_sha` rather than silently ignoring it.
- Qualification output is captured with its original exit status. Finalization
  runs after success or failure, binds both observed checkout heads, and writes
  a bounded receipt plus an existing experiment-registry run record.
- A pinned `actions/upload-artifact` action retains only the validated staging
  directory for seven days. Artifact names include job, cell, run and attempt.
  Raw temporary trees, credentials and the whole workspace are not uploaded.
- Meta uses `apps/meta-resume-web/verify.mjs` from the selected product source,
  the locked harness Playwright and its installed Chromium executable. Its
  assertions and product implementation are unchanged.
- Development guidance and generated cloud-task wording follow the root's
  lightweight rule. The 34 environment manifests remain available command
  menus; they do not impose a mandatory full suite on every task.

## Explicit qualification

Run the existing workflow from the implementation PR branch. This is a manual
operator choice within the current credit window, not a new scheduler:

```sh
gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-delivery-20261114 \
  -f workload=mariadb-runtime \
  -f source_sha=83c45015f475471a861d663677d060e26b2692c3

gh workflow run craci-pilot.yml --repo SalesSquad/junction-pets \
  --ref codex/junction-craci-delivery-20261114 \
  -f workload=meta-browser -f browser=chromium \
  -f source_sha=01065ebcffb74ebbb801f126ae8b46dba15b3a80
```

The MariaDB candidate is [PR111](https://github.com/SalesSquad/junction-pets/pull/111).
Its actual disposable MariaDB qualification is expected to exercise 80 checks;
that expectation is not a result. The earlier run
[43564983185](https://github.com/SalesSquad/junction-pets/actions/runs/43564983185)
retains its **72 passes and 5 failures** against `d0be3ab…`; those historical
failures must never be rewritten as a candidate pass.

The Meta source is the implementation merged through
[PR108](https://github.com/SalesSquad/junction-pets/pull/108). It tests synthetic
local browser behavior: keyboard confirmation, rejected visual evidence,
refresh persistence, a 600×600 display surface, correction, capture revocation
and offline resume. Passing it does not establish physical glasses, live
capture, native WebMCP, authenticated Chibi persistence or device synchronization.

## Receipt and registry contract

`scripts/craci/run-receipt.mjs run -- <fixed command>` wraps exactly one
qualification command per cell. `finalize` runs with `if: always()` and the
actual job/qualification outcome. It verifies the requested versus observed
source and harness commits; a missing command or unverified checkout is
incomplete, never successful. The only intentional tracked source overlay is
Tieto's explicit compatible-toolchain `global.json`, recorded with its digest.

The outer receipt holds run/attempt/cell identity, command status and measured
wall time, source provenance, artifact hashes, next owner and cost fields.
Actual cost is **null when unavailable**, not zero. Local hashes and
`source-reported` evidence are not cryptographic provider attestations.

`recordRun` from `services/experiment-registry/registry.mjs` generates
`registry/runs/<id>.json` inside each safe artifact. The service's schema and
immutable/idempotent persistence rules are unchanged. The existing coordinator
downloads and verifies the artifact, imports sanitized records into
`ops/experiments/runs/`, and commits them through the task branch. CI keeps
`contents: read`; it does not receive repository-write credentials or push Git.

If the harness checkout itself fails, a small infrastructure-only receipt
records that no product source or registry import was verified. A runner that
never starts or cannot upload remains a provider/GitHub infrastructure failure;
no workflow can claim a stored execution receipt for that absent execution.

Known outputs are bounded logs, JSON/JSONL, PNG screenshots, Playwright ZIP
traces, TRX results and SHA-256 lists. Unknown files, links or over-limit output
are not published. The upload step requires the finalizer's `upload_ready`
signal and preserves any original failing job status.

## Verification and actual runs

Implementation qualification is in progress. This section will be updated
with exact committed harness, run/job IDs, artifact digests, actual findings
and registry record IDs after the two authorized runtime jobs finish.

The source planner's targeted checks cover the observed ignored-override bug,
invalid product fan-out, closed/deadline admission and immutable bounded cells.
Receipt checks use isolated synthetic Git/work roots and cover consequential
failure/provenance/publication behavior. No unchanged portfolio matrix or full
repository suite is requested by this task.

Browser dependency and browser-install durations are measured separately in
`artifacts/setup-timing.json`. Cache changes require an observed bottleneck and
the existing monitored producer/consumer provenance; no unmeasured speedup is
claimed.

The MariaDB Docker image remains digest-pinned. Its exact documented
`production.cloudfront.docker.com:443` allowance remains outside package-aware
detection; this task does not claim complete container SBOM observation. No
existing workload network policy is broadened.
