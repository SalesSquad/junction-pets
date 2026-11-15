# Portable review milestone — implemented, local handoff

- Work: `J26-PF-TIETO-REVIEW-20261115`; owner: this isolated product writer.
- Source: `2e8d16686eecc47d0bdea104b541b1af88691739`; clean baseline.
- Branch: `codex/j26-tieto-portable-review-20261115`.
- Exclusive edits: `solutions/tieto-earned-trust/**` only.
- Scope: offline browser import, conservative evidence display, explicit human
  request/refusal/demo declaration and exact-byte SHA256 export. No native edits.
- Acceptance: `node --test solutions/tieto-earned-trust/review.test.mjs`,
  `node --check` for owned ESM files and `git diff --check`.
- No workers, dependencies, model calls, commits, pushes or PRs. Coordinator owns delivery.
- Implemented: bounded exact-byte import, immutable source IDs, full literal source,
  MP-2283 requirement mapping, pass/fail/unknown gates, compatibility disclosure,
  green-build counterexample, required human decision/rationale and local JSON export.
- Verification: 10/10 focused Node tests passed on Node v26.13.0; all three ESM
  syntax checks and `git diff --check` passed. See `evidence/portable-review.json`.
- Localhost HTTP smoke: BLOCKED, Python 3.13 `socket.bind` returned
  `PermissionError: [Errno 1] Operation not permitted` in this managed sandbox.
  No server remained running. No browser, download or assistive-technology pass claimed.
- Optional native `packet.json` import intentionally unsupported; only exact run-003
  differential bytes accepted. Neither source identity nor human identity is verified.
- Next: coordinator exercises README walkthrough in an authorized localhost browser,
  then owns commit/PR delivery. Work deliberately remains uncommitted and unpushed.
- No independent review, original .NET rerun, live GitHub refresh or release claim.
  Source/ownership admission used the work order's authenticated snapshot.
- Design lookup: configured newcomp checkout absent; no assets/dependencies imported.

---

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

## Final coordinator correction and bounded host evidence — 15 November 2026

The author-completed task source was independently read-only reviewed on the
exact pre-correction bytes with no P0/P1/P2 identified. The coordinator then
found a malformed closing `<option>` in `desk/index.html`, repaired the three
review-action options and added an explicit HTML-structure negative regression.
Ten affected Node tests, ES-module syntax and `git diff --check` passed on the
repaired source. A separate authorized Mac Mini one-shot HTTP server returned
200 for the four desk assets and 404 for a nonexistent path; it was stopped.
The original sandbox socket refusal is retained as a failed environment attempt,
not rewritten or called a browser pass. The original frozen .NET receipt is
untouched. No real browser interaction, authenticated reviewer, sponsor
acceptance, merge, deploy, purchase or submission. Final-source hashes are in
`evidence/portable-final.json`, with original author receipt retained.
