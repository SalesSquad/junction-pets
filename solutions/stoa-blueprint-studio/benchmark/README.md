# Stoa M335 — isolated drawing benchmark

Work `J26-PF-STOA-M335-M3-20261114`, base
`79d998af372c26cb05907ad9a4aa8e0662caeaf8`. Only this new directory is owned.
M1–M2/parser/grounding engine and old tests are unchanged.

Pin update 17 Nov 2026: the engine (`src/dxf.mjs`, `src/grounding.mjs`) was changed on purpose
in #200, #325 and #346, so the source pin in `run.mjs` now names `36fda81d34c3d3104f7f6f78b9c7f97648bb7b05` (#346). Earlier
reports remain bound to the original base above.

**NO_REAL_HELDOUT_SOURCE.** One bounded ZIP-tail GET on 2026-11-14 failed with
curl exit 6 (sponsor hostname DNS resolution). No retry, archive download,
drawing selection, original drawing SHA or real score exists. The committed
`holdout-source-v1.json` records this and deliberately refuses evaluation.
GitHub's hostname also failed resolution during main readback; local HEAD was
verified against the supplied base. No official heldout protocol was confirmed:
Nov14 catalog `junction.stoa → stoa → M335`, latestClarification null; Nov13
heldout question unresolved. M335 weights accuracy, verifiable region,
creativity and low inference cost equally at 25%. We do not invent a composite
judging score, creativity grade or baseline performance.

## Run (Node 20+, built-ins only)

From repository root:

```sh
node --test solutions/stoa-blueprint-studio/benchmark/*.test.mjs
node solutions/stoa-blueprint-studio/benchmark/fetch-holdout.mjs --inspect
node solutions/stoa-blueprint-studio/benchmark/fetch-holdout.mjs \
  --manifest solutions/stoa-blueprint-studio/benchmark/holdout-source-v1.json \
  --output /private/tmp/stoa-distinct-floor.dxf
node solutions/stoa-blueprint-studio/benchmark/run.mjs \
  --drawing /private/tmp/stoa-distinct-floor.dxf \
  --suite solutions/stoa-blueprint-studio/benchmark/holdout-source-v1.json \
  --output /private/tmp/stoa-heldout-result.json
```

The last two commands currently fail closed. Discovery is a future **explicit**
invocation, not an automatic retry. `--inspect` requests a 64 KiB footer and at
most one central-directory range smaller than 1 MiB, listing distinct Swiss
floor candidates and LICENSE.md metadata. It never extracts drawings. To admit
one, separately review its exact archive path, original SHA256 and license,
and replace the unavailable-source manifest with reviewed source metadata and
reference questions. The extractor requires a previously pinned original hash;
it does not trust an observed download as a reference or auto-create labels.
With an admitted manifest, it rechecks the directory, reads LICENSE.md and the
exact selected drawing with at most two requests per entry, checks CC BY 4.0,
length, CRC, bounded decompression, hash and ASCII content, then logs filename
and SHA. No redirects, retries, full ZIPs, provider inference or services.

All drawing/report outputs must be directly under `/private/tmp`, created with
`wx` and mode 0600; existing outputs and symlinks are never overwritten.
Archive-controlled paths are never used as filesystem destinations. Range
responses must be HTTP 206 with matching Content-Range and exact bounded body.
ZIP64, multidisk, encryption, suspicious flags, duplicate paths, unsupported
compression, unsafe names and excessive expansion fail closed. Inspection and
extractor mechanics have synthetic tests; successful live range transport has
**not** been verified in this environment.

## Admitted suite contract

`schemaVersion: 1`, `evidenceType`, `source`, `questions`. Real manually audited
exposed-drawing labels must use
`SELF_AUDITED_DRAWING_NOT_SPONSOR_HELDOUT`; synthetic fixtures use
`SYNTHETIC_MECHANICS_ONLY`. Neither means official independently withheld labels.
The source object requires `filename`, full `archivePath`, original `sha256`,
`license: "CC BY 4.0"` and `attribution`. At least one supported question and one
unanswerable question are required. Every question has a unique `id`, `question`,
`reference: {method, sourceLocator}` describing manual source inspection, and
`expected: {status, answer, regions}`. Supported answers are exact strings and
must include full source entity objects (ID, type, layer and exact coordinates,
text/points/closed flag as applicable). Abstentions use null answer and no
regions. References are authored before execution, independently of engine
answers. The test file demonstrates this using separately written DXF groups
and entity objects. No sponsor drawing bytes belong in Git.

The prior floor `site1102_bldg2242_floor10281.dxf`, SHA256
`4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d`,
is rejected by filename and hash because its Q&A is already exposed in old tests.
No question derived for a second exposed floor may be presented as a published
sponsor question without a real question source reference. Independent label
correctness remains a human audit responsibility; hash matching proves bytes,
not semantic truth. This run reports no scored real evaluation.

## Report semantics

Reports bind exact drawing/suite hashes, pinned application file hashes,
benchmark file hashes, local HEAD, Node/platform, time, full question results
and original coordinates for resolved citations. Application files must match
Git blobs at the base SHA. Source geometry/IDs in references must match the
parser exactly; fabricated references and drawing SHA mismatch abort execution.
The unchanged engine returns IDs; the runner resolves them to original source
geometry, never fabricates bounding boxes. Wrong/unknown/duplicate citations
receive no extra credit and remain in the precision denominator.

Accuracy = exact status+answer matches / all questions, including missing
responses; abstentions count correct only for expected negatives and require
empty evidence. Grounded accuracy additionally requires all and only expected
citations. Region precision/recall are micro averages over individual source
entities; a point label is a source point, not a room polygon or IoU. Null
precision means no predictions, never a perfect score. Coverage and abstention
rate use all questions. `missingResponses` remains explicit. Latency measures
only each engine call (warm process; no network/ingest), with per-question and
mean milliseconds. External inference calls are zero; CPU cost is not estimated.
Baseline is explicitly **no comparable baseline**. This is a local deterministic
evaluation, not independent sponsor scoring, E2E qualification or production.

Swiss Dwellings v3.0.0 / Archilyse AG contributors, CC BY 4.0,
[doi:10.5281/zenodo.7788422](https://doi.org/10.5281/zenodo.7788422);
sponsor-rendered derivatives. Preserve full source attribution when admitting
an actual floor. Preview usage is noncommercial competition, local-only; no
redistribution of drawings. All fetching is restricted to the existing public
Stoa preview archive. No cash spend, deployments, merges or FINAL L9 claims.

## This task's targeted observation (2026-11-14)

`node --test solutions/stoa-blueprint-studio/benchmark/*.test.mjs`: **13 passed,
0 failed, 0 skipped** on local Node (no server started). Controlled synthetic
fixture SHA256:
`e394d4a506a3ae6654ca9a86bd746246ed6b92ba88d58702b4995f5a76abf440`.
Two authored cases: 2/2 exact answers/abstentions, 2/2 grounded, region precision
1 and recall 1 over two expected text points, coverage 0.5, abstention 0.5;
observed mean engine-call latency about 0.068 ms in the CLI test (warm local
microbenchmark, not a general performance claim). Substituting one wrong label
citation yields region precision/recall 0.5 while textual accuracy remains 1;
this demonstrates why both measures are reported. **Real drawing raw SHA:
unavailable. Real benchmark: not run.** No old E1 suite was rerun.

## Source-verified second floor, independently self-audited (later 14 Nov 2026)

The above `holdout-source-v1.json` records the initial Mini DNS failure and remains unchanged; a subsequent independent MBP bounded-range fetch proved the sponsor ZIP was reachable, and the newly implemented extractor verified a **second, distinct real drawing**, `site1000_bldg2082_floor9385.dxf`, original SHA-256 `5e064c774b7034a91c5710220564b0b3a3afd551e9679ffc3d533a161fddc3b5` (276,833 bytes), with original Swiss Dwellings CC BY 4.0 license SHA-256 `da883c8a96459fc869fb08734e54fe514e173440e253953bbf0a0ea373d61ba5`. Its raw DXF remains private under `/private/tmp` and is **not in Git**.

`holdout-source-v2-self-audited.json` freezes two count questions (four `Küche` and five `Korridor` source TEXT entities) and two deliberate unanswerable questions, with nine original source-text coordinates. Their reference labels and handles were checked by a separate raw DXF group-code scan **before** invoking the existing question engine. A live local evaluation using the new `run.mjs` returned **4/4 status+answer correct, 4/4 grounded correct, 9/9 cited source regions, 2/2 correct abstentions**; immutable private report SHA-256 `473c5e869a3b6826a1a79ceca5a380e9ffccd3aeb727e4991aed5de6da32289e`. This is explicitly `SELF_AUDITED_DRAWING_NOT_SPONSOR_HELDOUT`, **not independent sponsor labels, a blinded benchmark, or evidence of cross-format accuracy**. The next qualification dependency is independent human-adjudicated, unseen drawings/questions with source-region ground truth.

Reproduce locally with the private original at `/private/tmp/stoa-distinct-floor-verified-20261114.dxf` (or a freshly verified copy): `node solutions/stoa-blueprint-studio/benchmark/run.mjs --drawing /private/tmp/stoa-distinct-floor-verified-20261114.dxf --suite solutions/stoa-blueprint-studio/benchmark/holdout-source-v2-self-audited.json --output /private/tmp/stoa-replay-new-receipt.json`. Outputs are create-only. Never publish the sponsor drawing or represent the self-audit as independent held-out testing.
