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

## Portable offline review desk

The complementary browser workflow lives in [`desk/index.html`](desk/index.html).
It uses HTML/CSS/ESM and browser SHA256, with no dependencies, account, network
calls, analytics or storage. Serve it using an already-installed Python 3 from
repository root (foreground process; stop with Ctrl-C):

```sh
python3 -B -m http.server 4198 --bind 127.0.0.1 --directory solutions/tieto-earned-trust/desk
```

Open `http://127.0.0.1:4198`. Modern Safari, Firefox or Chromium with Web Crypto
and JavaScript modules is required. Direct `file://` module loading is not
supported consistently; use localhost. The local server serves only the desk,
not the repository. File contents are read through the file picker, never fetched.

1. Choose the original public sample file:
   `tools/earned-trust/verification/evidence/run-003/differential.json`.
2. Read MP-2283, exact base/head, compatibility mode, reported gates and literal
   source. The requirement mapping is authored by this desk using the existing
   packet producer; it is not a field invented in the source receipt.
3. Inspect the counterexample: base build exit 0, but failed probe and missing
   resolver. All six raw assertions remain unknown because their referenced
   observation files are not imported here.
4. Enter a self-declared reviewer name, explicitly request evidence, refuse, or
   conditionally approve a demonstration, supply a rationale and acknowledge limits.
5. Export local JSON. The declaration includes exact-byte SHA256, unchanged
   evidence gates, source IDs, limits and a device-clock timestamp. No automatic
   approval or authenticated signature is produced. Clear the local review to reset.

Only the **exact retained run-003 bytes** are supported (maximum 256 KiB). The
allowlisted SHA256 is
`cb9164598c280eafdbc677c8ad68030a1579b6a0d489add6faab5d06f1052e8e`,
pinned to portfolio source `2e8d16686eecc47d0bdea104b541b1af88691739`.
Even whitespace rewrites, missing checks, changed identities or modified claims
are refused. This deliberate narrow adapter does **not** support generated
`packet.json`, other cases, arbitrary receipts or imported previous declarations.
The native packet schema remains at its existing producer/contract paths.

A matched hash identifies known bytes, not truthful results, source authenticity,
runner identity or reviewer identity. Raw logs/harness/source trees are not
reverified. Reported fail/pass is the historical Linux SDK 9.0.100 / Roslyn 4.12 /
net8.0 experiment; original SDK 8.0.402, Windows/.NET 10, serialization round trips,
full upstream regression and real engineer acceptance remain unqualified.
Conditional demonstration approval cannot promote unknown or failed gates and
is never GitHub acceptance, merge permission or release approval. Imported text
is displayed with `textContent`; reviewer markup/control characters are rejected,
and JSON exports escape HTML-sensitive characters. No secret ingestion is intended.

Focused verification (Node 22+, built-in modules only):

```sh
node --test solutions/tieto-earned-trust/review.test.mjs
node --check solutions/tieto-earned-trust/desk/review.mjs
node --check solutions/tieto-earned-trust/desk/app.mjs
node --check solutions/tieto-earned-trust/review.test.mjs
git diff --check
```

These deterministic checks cover import/decision/export policy and static UI
boundaries; they do not establish browser rendering, downloads or screen-reader
acceptance. No native/.NET experiment needs rerunning for this desk.

Actual execution results are retained in [`evidence/portable-review.json`](evidence/portable-review.json).
The managed executor denied localhost socket binding (`PermissionError: [Errno 1]
Operation not permitted`); serving and real browser import/download remain unverified.
The walkthrough requires an executor permitted to bind localhost. A separate
**authorized Mac Mini host** (outside the source-writer sandbox) subsequently
served `desk/` on loopback: HTTP 200 for `index.html`, `app.mjs`,
`review.mjs`, `style.css`, and HTTP 404 for an unknown path; temporary
server shut down. This is a transport smoke, **not** a real browser,
download, screen-reader or sponsor qualification. The coordinator also
repaired a malformed review-decision `<option>` and added the explicit
four-option parser regression before final commit.
