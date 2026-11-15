# Earned Trust continuation

Stage: demonstrated native reference; private repository integration in progress.
This is not a production release or a competition submission.

## Current task

- Work ID: `tieto-integration-20261115`.
- Base SHA: `6d2efadb22678c259dfaf6817b43c883974a9eab`.
- Branch: `codex/junction-tieto-earned-trust-20261115-7193`.
- Owner: root task coordinator; stable subject lane `junction-dev-tieto`.
- Dirty baseline: clean dedicated clone at the exact base.
- Owned paths: `tools/earned-trust/**`, `solutions/tieto-earned-trust/**`.
- Objective: preserve the completed native reference, real #2283 proof and demo
  in the private portfolio, with a reviewable draft PR and a usable entrypoint.
- Final commit and PR: recorded in the draft PR's source-bound handoff.
- Main integration owner: existing Portfolio PR Recovery; no merge authorized
  by this source-import task.

## Evidence

Original execution remains bound to standalone application source `b014b7f` and
complete delivery source `1dc07eb`: one actual fail→pass comparison, 11 native
core checks, 10 producer checks, and observed native GUI import/export.
[Delivery record](../../tools/earned-trust/docs/DELIVERY.md) and raw receipts
retain the exact commands, source versions and limits.

The 46 native files retain canonical manifest
`819e45b5a02e4b821b612b0aa18805696636696c7a1552a4e32bc353b004e236`.
The six original experiment files and the unchanged receipt remain bound to the
same frozen experiment. Twelve actual executed harness copies are now included
so the retained receipt can be validated without temporary executor directories.

Integration acceptance: compare native and frozen identities; regenerate source
inventories from the separate public copy into temporary output, attach the
retained receipt, and compare the resulting packet bytes; validate this solution's
individual brief. Results and final remote byte readback belong in the PR.

Completed portable check: all 46 native and six frozen source identities match;
the source inventories remain 4 / 4 / 28 / 237 with 222 generated snapshots;
all 21 reconstructed packet/evidence files match the bundled originals. The
required public repository argument refuses omission before writing. See
[`evidence/integration-check.json`](evidence/integration-check.json). No native
or .NET workload was rerun for this byte-preserving import.

## Known baseline issue

The existing whole-portfolio `solution-workspace.mjs list` command returned
`Unknown challenge/company` before this solution was created. Preserve that
baseline failure and inspect the existing manifest owner separately. Do not claim
a whole-repository pass from this solution's targeted validation.

## Next action

After the scoped PR is reviewed, the existing portfolio integrator can integrate
it through its authorized merge workflow. For the challenge, use the two-minute
walkthrough with a real named engineer, record their actual decision and measure
review time against a plain diff. That human evaluation is the next new evidence;
repeating unchanged native or .NET runs does not supply it.
