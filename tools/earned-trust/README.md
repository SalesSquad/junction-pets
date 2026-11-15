# Earned Trust — a native review desk for AI-written changes

Junction 2026 / Tieto reference implementation. Independently authored; not
endorsed by Tieto or the upstream maintainers.

The review unit is a **requirement and its evidence**, with a deliberate human
decision at the end. The application separates a demonstrated change from
preserved behavior and from observations that still need a behavioral check.

## What is here

| Path | Responsibility |
| --- | --- |
| `macos/` | Native SwiftUI application, strict packet loader, local decision export and focused core checks |
| `contract/PACKET.md` | Shared evidence packet contract and decision semantics |
| `packet/` | Deterministic inventory of the four pinned public sponsor changes and evidence adaptation |
| `verification/` | Frozen two-assembly #2283 probe and actual base/head comparison |
| `docs/` | Concept card, walkthrough and verified delivery record |

The application reads local evidence. It never executes imported commands,
contacts a provider, modifies a repository, merges code or impersonates a human.
The verifier is a separate developer-operated command-line process.

## Run on a Mac

From `macos/`, run `./script/build_and_run.sh --verify`. The script builds with
the installed Swift toolchain, stages a real `.app` bundle and opens it. No new
Xcode installation, simulator or external Swift package is required.
This is a locally built development app, without Developer ID signing or
notarized distribution. The supplied binary is for Apple Silicon; the source
package is available for rebuilding with the installed Mac toolchain.

Use the sidebar to select a supplied change. The detail pane shows its
requirement, evidence, limitations and files. Inspect source provenance, import
a JSON packet or export a local review declaration. A declaration is bound to
the exact packet and evidence snapshot and is explicitly unauthenticated.

## Recreate the source inventory

From this repository root:

```sh
python3 tools/earned-trust/packet/build_packets.py \
  --repository /absolute/path/to/your/public-messagepack-copy \
  --output tools/earned-trust/macos/Sources/EarnedTrust/Resources/Packets
```

Use `--timestamp` with the previously recorded timestamp for byte-reproducible
packets. The generator requires the exact four official commits, verifies their
shared parent and records the actual diff. It labels this step source inspection.
Behavioral evidence is attached separately after the frozen comparison completes.
The repository argument is required: the portfolio repository is the application
home, while the four source changes belong to the separate official MessagePack
copy. To reproduce packets without replacing the bundled evidence, use a new
temporary output directory. The retained receipt can be attached from
`verification/evidence/run-003/differential.json`; its original executed harness
copies are preserved under both `base/harness/` and `head/harness/`.

## Four source changes

The organizer supplied these AI implementations; we did not author their fixes.

| Issue | Official head | Changed files |
| --- | --- | ---: |
| #2283 | `9df83c38409c8bfad0517aebffe48211eda4a5b4` | 4 |
| #2234 | `9007cee1163c4a274fd60c3cc20c21ae63622786` | 4 |
| #2129 | `083afd994c1c9a994cb2cd5aa0b6ad805a621457` | 28 |
| #2297 | `a0aa5ab2de7f5a669d97e37184a89034c1de82b6` | 237 |

All share base `32258fdbee4bcd653c79f51b4376b5103c6f4d27` in
[the public sponsor repository](https://github.com/te-industry-tech-office/junction26-messagepack-csharp).
In #2297, 222 paths are generated expected-output snapshots. The application
groups those separately from 15 other changed files. This is a measured file
classification, **not a measured percentage of review time saved**.

Five review packets are bundled: the four official changes and one adversarial
control over #2283. The control uses real pass→pass generated-code compilation
observations while retaining the original analyzer/generator crashes and missing
resolver. Its deliberately unsupported claim remains **NEEDS EVIDENCE**. It is
not a fifth organizer issue or a synthetic test result.

The actual #2283 frozen comparison demonstrates **fail→pass**: the base produces
AD0001/CS8785 and no consumer resolver; the patch produces the resolver without
diagnostics. Both used the same frozen probe under the disclosed SDK 9.0.100,
net8.0 Linux compatibility configuration. The other three changes remain source
inspection cases in this implementation. See [the delivery record](docs/DELIVERY.md)
for execution evidence and the boundaries of this result.

## Evidence boundaries

- A fix needs a genuine expected fail→pass from the same frozen experiment.
- A regression invariant can use pass→pass. It supports preservation of behavior,
  not proof of the new feature by itself.
- A structural observation stays inspection only.
- Environment failures cannot become a convenient red baseline.
- Matching log hashes prove local bytes match a declaration. They do not
  authenticate the runner, the author, the truth of outcomes or a reviewer.
- Imported documents are untrusted. Paths, sizes, links, IDs and source bindings
  are validated. No content from a packet is executable.
- No model training or live model-inference claim is made. The reference focuses
  on evidence for the supplied AI-written code and human accountability.

## Preservation and integration

This implementation was developed on an isolated branch in our own copy of the
public challenge repository. On 15 November 2026 the owner explicitly authorized
integration into private `SalesSquad/junction-pets`, on a task-owned branch and
draft PR. The native application and original experiment identities are preserved.
See [the integration record](docs/INTEGRATION.md) and the discoverable
[solution workspace](../../solutions/tieto-earned-trust/README.md).

Upstream source and fixtures retain the original [license and notices](UPSTREAM_LICENSE.txt).
Build caches, downloaded SDKs and temporary execution checkouts are not source
deliverables. See the verification receipt and delivery record for the actual
commands, outcomes and remaining limitations.
