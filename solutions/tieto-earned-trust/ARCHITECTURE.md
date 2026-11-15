# Earned Trust architecture

| Component | Source | Responsibility |
| --- | --- | --- |
| Native Mac application | `tools/earned-trust/macos/` | Requirement/claim/evidence UI, file grouping, provenance, bounded import and local decision export |
| TrustCore | `tools/earned-trust/macos/Sources/TrustCore/` | Strict packet parsing, file integrity, claim evaluation and local decision binding |
| Packet contract | `tools/earned-trust/contract/PACKET.md` | Explicit evidence kinds, exact source identities, outcomes, limitations and file groups |
| Source inventory | `tools/earned-trust/packet/build_packets.py` | Inspect four pinned public MessagePack changes through an explicitly selected separate repository |
| Frozen experiment | `tools/earned-trust/verification/` | Reproduce #2283 on exactly pinned base/head with identical inputs and toolchain overlay |
| Evidence adapter | `tools/earned-trust/packet/attach_differential.py` | Validate actual raw observations, the complete frozen manifest and local artifact hashes |
| Tieto subject companion | `pets/tieto/` | Existing guidance/discovery; no live invocation is established by this workspace |

## Source and reuse

The application/experiment source is from standalone commit
`b014b7f27d21ff72be5cdac951021d7a3e361af4`, with delivery documentation at
`1dc07eb92eb19d017e78bf5e6bcab788c3665759`. All 46 native files are imported
unchanged. The original four AI fixes belong to the public organizer repository;
we authored the review concept, application and frozen verification experiment.
The original upstream license and notices are retained alongside the source.

The earlier synthetic trust-ledger PR #78 is a related reference, with no dependency
on its merge. Existing pet, plugin, shared contract and private Chibi code is not
copied or changed. Portfolio PR Recovery remains the main-branch integration owner.

## Trust boundaries

Imported packets are untrusted data. Bounded paths, file sizes and strict fields
are validated; local hashes establish byte integrity, not runner or reviewer
authentication. Evidence files are read as text, never commands. The application
executes no imported code and performs no model call, repository write or merge.

A real fail→pass check can support a fix. Pass→pass supports preservation of a
stated invariant, not the existence of a fix. Structural grouping stays inspection
only. A local named declaration records a person's stated judgment; no identity
provider or signed approval is fabricated. Actual host identity, consent, memory
and model dispatch remain the separate Chibi host's responsibility.
