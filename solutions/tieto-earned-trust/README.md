# Earned Trust — a native review desk

A working reference for Tieto's **Earned Trust in AI Code** challenge. Its unit of
review is a requirement, a claim and the evidence that earns a human decision.
The independently authored application is not a Tieto-endorsed product.

## Start the demo

```sh
./tools/earned-trust/macos/script/build_and_run.sh --verify
```

Run on a Mac with the installed Swift toolchain. For the Codex Run button, open
`tools/earned-trust/macos/` as the package directory. The local Apple Silicon
preview was built and exercised; Developer ID signing and notarization are not
part of this reference delivery.

1. Open **Metadata generics without crashes** (#2283): one frozen experiment
   fails on the official base and passes on the supplied patch. Inspect the
   missing resolver and AD0001/CS8785 base diagnostics.
2. Open **Counterexample: a green build**: both generated-code compilations pass,
   but that does not prove the fix. The unsupported claim needs more evidence.
3. Open #2297 **Change map**: 237 changed paths become 15 other files and 222
   generated snapshots, all retained for inspection.
4. Record a clearly labeled demonstration review and export its JSON. The record
   binds the evidence and rationale; it is not an authenticated repository approval.

[Two-minute walkthrough](../../tools/earned-trust/docs/WALKTHROUGH.md) ·
[Concept card](../../tools/earned-trust/docs/CONCEPT.md) ·
[Actual delivery evidence](../../tools/earned-trust/docs/DELIVERY.md) ·
[Integration record](../../tools/earned-trust/docs/INTEGRATION.md).

## Challenge fit

The [official brief](https://hackjunction.app/participate/45/challenges/351)
asks for a concept and reference implementation, evidence traceable to one
requirement, visible refusal, named human accountability and a short decision log.
The current source snapshot is indexed in
[the Tieto research entry](../../pets/tieto/CHALLENGE_RESEARCH.md).

The differentiating observation is real: a successful compilation can coexist
with a crashed generator and an absent resolver. The application exposes that
failure rather than inferring correctness from build success. File grouping
addresses review scale; it is not a measured review-time saving.

## Acceptance and limits

The recorded #2283 comparison used SDK 9.0.100, net8.0 and Linux. It is one
compiler-compatibility experiment. The other three supplied changes retain
inspection-only status. Full upstream regression, original Windows/.NET 10,
real engineer acceptance, incident/revert outcomes and review-time savings are
not established by this reference.

Minimal integration check:

```sh
node scripts/solution-workspace.mjs brief tieto-earned-trust
python3 tools/earned-trust/packet/build_packets.py \
  --repository /absolute/path/to/your/public-messagepack-copy \
  --output /tmp/tieto-review-packets
python3 tools/earned-trust/packet/attach_differential.py \
  --receipt tools/earned-trust/verification/evidence/run-003/differential.json \
  --packet /tmp/tieto-review-packets/2283/packet.json \
  --control-packet /tmp/tieto-review-packets/2283-control/packet.json
```

Keep the official MessagePack copy separate from this portfolio. The retained
receipt includes the original executed harness files needed by the strict adapter.
The source remains at its established `tools/earned-trust/` path; this workspace
provides discovery and handoff without duplicating the implementation.
