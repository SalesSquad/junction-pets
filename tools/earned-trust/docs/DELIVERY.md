# Verified delivery — 15 November 2026

This records the original standalone delivery. The owner subsequently authorized
private-repository integration on 15 November; its current source and handoff are
recorded in [INTEGRATION.md](INTEGRATION.md). The original execution identities,
results and initial approval-review rejection below remain historical evidence.

## Delivered outcome

Earned Trust is a working native macOS review desk with five bundled cases,
an actual frozen #2283 before/after experiment, an honest counterexample,
and a local review export. The application was built and exercised on the
authorized Apple Silicon Mac Mini. The implementation is independently authored
under `tools/earned-trust/` in our own copy of the public challenge repository.

The application and experiment source were committed as
`b014b7f27d21ff72be5cdac951021d7a3e361af4` on
`codex/tieto-earned-trust-macos-20261115`. The subsequent delivery commit changes
documentation and retains verification evidence; it does not change application
or experiment behavior. The downloadable package includes the exact patch series
so the work can be integrated later without depending on this temporary workspace.

## What was demonstrated

| Check | Observed outcome | Retained evidence |
| --- | --- | --- |
| Frozen #2283 probe on the common base | Analyzer AD0001, generator CS8785, resolver absent; behavioral FAIL | `../verification/evidence/run-003/base/` |
| Identical probe on official #2283 head | No diagnostics, resolver present; behavioral PASS | `../verification/evidence/run-003/head/` |
| Native application build and launch | Completed; real `.app` opened, process and window observed | `evidence/native/native-verification.json` |
| Final native core tests | 11 passed, 0 failures, at 01:37 Helsinki | `evidence/native/final-core-verification.json` |
| Packet producer boundary tests | 10 passed, 0 failures | `evidence/native/packet-tests.log` |
| Native source identity | All 46 tracked Mac files matched the committed source; zero mismatches | `evidence/native/source-manifest.json` |
| Import and export | File-picker import retained the expected packet hash; file-picker export produced the expected JSON | `evidence/native/demo-review-2283.json`; UI records in the delivery archive |

The 21 unit tests exercise evidence handling and invalid-input boundaries. They
are separate from the two actual MessagePack probe executions, whose expected
fail→pass result is recorded independently. The native test fixtures are not
presented as genuine MessagePack run evidence.

The GUI was inspected visually and through its native accessibility surface.
The following interactions completed on the built application:

1. The genuine #2283 packet displayed **READY FOR HUMAN** and the pinned source
   commits. Its base observation opened in the read-only evidence viewer.
2. **Counterexample: a green build** displayed **NEEDS EVIDENCE** and explained
   why the measured pass→pass compilation sub-check does not prove the fix.
3. #2297 displayed **INSPECTION ONLY**, with 15 source/test/documentation paths
   and 222 generated snapshots. The generated group expanded successfully.
4. **Record Review** required a name and rationale, then opened the native save
   panel. The exported demonstration decision was **Request evidence**, declared
   by **Demo Reviewer**, with an explicitly stated UI-test rationale.
5. **Import** accepted the original local #2283 packet through the native open
   panel and showed the same packet digest and readiness afterward.

The exported example has `reviewerAuthenticated: false`,
`codeChangeApproved: false`, and `remoteWritePerformed: false`. Its reviewer name
is a demonstration label, not Mikael's decision or an authenticated human review.

## Exact identities

| Artifact | SHA-256 |
| --- | --- |
| Frozen six-file experiment bundle | `96961b0d0267a9988aef04e278bcf2eba715c18a5667224f752e199619304327` |
| Actual differential receipt | `cb9164598c280eafdbc677c8ad68030a1579b6a0d489add6faab5d06f1052e8e` |
| Bundled #2283 packet | `c2aeb40f8f98978af04a04f9592a17e52d1a8f0356ce85e6544af40194bf1845` |
| Native 46-file source manifest | `819e45b5a02e4b821b612b0aa18805696636696c7a1552a4e32bc353b004e236` |
| Built `EarnedTrust-macOS.zip` | `e4274bd0c11d1cb10ad8a8184f3741f0e5d96359440874e57d04dd251a8b631e` |

The source manifest is SHA-256 over compact, sorted JSON mapping relative file
paths to SHA-256 digests. These hashes bind local bytes; they do not authenticate
an execution service or reviewer. The command-receipt helper could not bind the
Mac staging directory to a Git HEAD. The independently compared 46-file manifest
provides the explicit source binding instead; that helper limitation is retained
in the raw receipt.

## Build, packaging and independent review

The Mac used its installed Swift 6.4 toolchain and macOS SDK. The application
targets macOS 14+, has no third-party Swift dependencies, and is staged by
`macos/script/build_and_run.sh`. Its committed Codex Run configuration points to
the same script; the script itself was exercised directly, not through the Codex
Run button. The provided binary is arm64, locally ad-hoc signed by the toolchain,
without Developer ID signing or notarization. It is a development preview.

Independent review found and resolved three material issues before delivery:
an incomplete frozen manifest could be accepted, contradictory raw observations
needed stronger consistency checks, and UI wording overstated harness
verification. The producer now validates the exact six-file manifest and raw
outcomes; the UI distinguishes declared identities from verified log bytes.
Focused negative tests cover those producer boundaries. Evidence `.log` files
were also explicitly included despite the repository's broader log ignore rule.

## Remaining scope and integration blocker

The proven result is one compiler compatibility experiment: SDK 9.0.100,
.NET runtime 8.0.11, net8.0, Linux x64. The original SDK 8.0.402 build,
Windows/.NET 10 report environment, serialization round trips and full upstream
regression suite were not qualified here. The other three official changes have
source inventories but no newly claimed behavioral proof. No review-time saving
percentage was measured.

Automatic approval review rejected copying the private
`SalesSquad/junction-pets` repository. No private code was reconstructed or used
to work around that rejection. This deliverable is complete in the authorized
public-source copy; integration into the private portfolio repository awaits an
explicit owner instruction covering that destination. No task branch has been
pushed, no PR has been opened for this implementation, and nothing has been
merged, deployed or submitted to the competition.

The Mac staging project and running preview are retained for the owner at
`/Users/mikaelmini/Projects/TietoEarnedTrust-20261115-7193`. The source, evidence,
build package and patch series are preserved in the downloadable delivery.
