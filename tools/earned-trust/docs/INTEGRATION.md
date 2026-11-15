# Portfolio integration — 15 November 2026

Work ID: `tieto-integration-20261115`.

The owner explicitly approved copying private `SalesSquad/junction-pets` and
integrating the completed reference on an owned branch with a draft PR. That
instruction resolves the original copy-authorization blocker described in
[DELIVERY.md](DELIVERY.md); it does not authorize a merge, release or submission.

## Source and ownership

- Portfolio base: `6d2efadb22678c259dfaf6817b43c883974a9eab`.
- Original application/experiment commit: `b014b7f27d21ff72be5cdac951021d7a3e361af4`.
- Complete standalone delivery commit: `1dc07eb92eb19d017e78bf5e6bcab788c3665759`.
- Integration branch: `codex/junction-tieto-earned-trust-20261115-7193`.
- Author/integration scope: `tools/earned-trust/**` and
  `solutions/tieto-earned-trust/**`, coordinated by the task's root agent.
- Dirty baseline: clean dedicated clone at the pinned portfolio base.
- Main integration remains with the existing Portfolio PR Recovery owner.

The existing Tieto companion and synthetic trust-ledger PR #78 retain their own
paths and ownership. This reference has no merge dependency on #78. The new
solution manifest links the Tieto subject agent for discovery; it makes no live
Chibi, model or companion-execution claim.

## Changes needed for relocation

1. The source-inventory producer now requires `--repository` explicitly. It must
   read an independent copy of the official MessagePack history, not the portfolio
   Git root. The official source URLs and commit identities in packets are unchanged.
2. The original upstream LICENSE and notices travel with the subtree as
   `UPSTREAM_LICENSE.txt`; the README references that copy.
3. Twelve original executed harness files (six per revision) are retained under
   `verification/evidence/run-003/{base,head}/harness/`. These were copied from
   the preserved actual run directory and verified against its manifest. They
   were not reconstructed, rerun, or substituted for historical observations.
4. A generated and completed solution workspace provides the repository's normal
   `brief tieto-earned-trust` entrypoint, architecture, demo and continuation.

All 46 native files retain their existing manifest identity
`819e45b5a02e4b821b612b0aa18805696636696c7a1552a4e32bc353b004e236`.
The six-file experiment identity remains
`96961b0d0267a9988aef04e278bcf2eba715c18a5667224f752e199619304327`;
the original differential receipt remains
`cb9164598c280eafdbc677c8ad68030a1579b6a0d489add6faab5d06f1052e8e`.

The original 11 native core tests, 10 producer tests, actual .NET comparison and
GUI observations remain bound to their original source. Their receipts are not
relabeled as new hosted runs. Integration checks and the final published HEAD
are recorded in the draft PR and solution progress record.

## Completed portable integration check

The preserved public source copy regenerated inventories with 4 / 4 / 28 / 237
changed files and 222 generated snapshots for #2297. Attaching the retained
receipt, using its recovered original harness copies, reproduced all 21 bundled
packet/evidence files byte for byte, including the genuine fail→pass packet and
the pass→pass control. Omitting `--repository` was refused before any output was
written. All 46 native files and all six frozen experiment files matched their
recorded digests. This is a deterministic reconstruction and integrity check;
the native and .NET experiments were not rerun.

The [machine-readable result](../../../solutions/tieto-earned-trust/evidence/integration-check.json)
retains the exact identities and observations.

## Baseline limitation

Before adding this solution, `node scripts/solution-workspace.mjs list` at the
portfolio base returned `Unknown challenge/company`. This is a pre-existing
whole-portfolio metadata problem. The Tieto workspace can be checked and opened
through its individual brief without changing another solution's declaration.
The task does not claim a passing whole-repository check from a targeted result.

## Continue

Open `tools/earned-trust/macos/` as the native package; its nested Codex Run action
uses the same verified build script. Read [the two-minute walkthrough](WALKTHROUGH.md).
For repository integration, use the exact PR HEAD and
[`solutions/tieto-earned-trust/PROGRESS.md`](../../../solutions/tieto-earned-trust/PROGRESS.md).
Native and .NET workloads need not be repeated for byte-preserving relocation.
