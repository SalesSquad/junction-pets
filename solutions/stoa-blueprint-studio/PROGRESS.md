# Review workspace delivery — 15 Nov 2026

Parent: reliability PR #325, source `36e252231c8ca094bce3db2c7031e93cc560ff7e`.
Task branch: `codex/stoa-review-and-revisions`; only `solutions/stoa-blueprint-studio/**`.

Delivered: method-based evidence levels; canonical source/engine-bound packet export and CLI
verification; source-bound human confirmations/corrections with idempotent operations, revision
conflicts, Undo/Redo and same-source/same-engine packet restore; DXF room/primitive and IFC GUID
revision comparison; split/merge-aware instance metrics with a synthetic CLI example. Imported
sources and associated reviews now expire by timer, and closing the server clears the cache.

Qualification: 62 passed, 0 failed, 1 optional licensed-source skip (63 tests total), including
80 assignment graphs compared with exhaustive independent optima. The historical benchmark CLI
test exercises fail-closed behavior because its old pinned commit is absent in this shallow
checkout; this is not a scored historical replay. Chromium checked confirmation, correction,
Undo/Redo, packet download/restore, guarded revision comparison (12 -> 15 m², +3), citation
inspection, comparison export and mobile layout without horizontal overflow or page errors.
The existing DXF/IFC browser flow also passed during development. Both downloaded JSON packets
passed CLI integrity checks and matched the final engine digest. JS syntax and whitespace checks
passed. No sponsor data, inference, deployment or merge.

Unsigned hashes prove consistency, not authenticity. Reviewer identities and source alignment are
local declarations. No physical-change verification, real-data recognition score or new sponsor
accuracy/IoU is claimed. Review state is in-memory and needs export for durable recovery. Full
instructions, budgets, API behavior, Valmet source pins and remaining limits: `WORKSPACE.md`.

---

# Stoa Atlas — Current reliability delivery

Base: `f64f6ac1322339ee2213737af9b00776ae67af0b`, isolated branch
`codex/stoa-evidence-and-ifc`. Scope: `solutions/stoa-blueprint-studio/**` only.

## Implemented in this revision

- Active V2 room areas delegate to strict geometry + annotation validation; totals require all
  contributing rooms to validate. Ambiguous apartment labels and boundaries abstain.
- Unsupported room-scoped object counts, multiple English object classes, invalid/injection-like
  questions and fixture counts without positive evidence abstain.
- IFC quantities convert area/volume SI prefixes dimensionally, honour declared quantity units,
  reject unknown units and refuse incomplete totals. Citations are no longer truncated at 400.
- Local IFC STEP upload, source hashing and inspectable entity/quantity/property/unit records in
  the browser, with exact quoted storey/room questions and exact scalar property lookup.
- Upload parser bounds size/record/entity count/nesting and rejects malformed STEP lists/strings.
- Single closed straight polyline HATCH ingestion with native source citations. Complex HATCH
  paths/holes/curves reject; curved LWPOLYLINE is excluded from trusted area measurements.
- Offline source/page-bound citation-box IoU, precision, recall and one-to-one matching.
- Regression checks target V2 and the real HTTP routes, not just the older grounding helper.

## Verification and limits

Local Node qualification: `node --test tests/*.test.mjs benchmark/*.test.mjs` — 53 passed,
0 failed, 1 optional licensed-source skip (54 total). The historical benchmark CLI test exercises
its fail-closed branch because the pinned old commit is absent in this shallow checkout; this
is not a successful historical scored CLI replay. `node --check public/app.js` and
`git diff --check` passed. Chromium browser flow passed locally; exact source is pinned in the PR. Synthetic fixtures only; the optional licensed sponsor test remains
skipped. Browser checks cover DXF count/area/citation, IFC import/area/source selection, desktop
and mobile rendering, and restoring the demo; zero page errors observed. No external inference,
licensed dataset fetch, deployment, merge or shared-file edits.

The historical tables below are evidence for the older engine. **The stricter revision's real-data
accuracy and coverage are unmeasured.** The region scorer has synthetic tests, not independent
sponsor region annotations. IFC record inspection is not 2D/3D spatial projection. DWG, general
free-form IFC questions and improved raster accuracy remain open; see `IMPROVEMENTS.md`.

---

## Historical state before this revision

# Stoa Atlas — Progress

Status: **measured on the official preview questions; numbers match the README table.**

## Current verified state

| Route | Result | Model cost |
| --- | ---: | --- |
| Swiss Dwellings DXF, `answerDrawingV2`, test split (35 drawings, 1,278 questions) | 96.4 % | none |
| Same engine, dev split (30 drawings, 1,080 questions) | 98.0 % | none |
| IFC (`src/ifc-qa.mjs`), 3 preview models, 1,049 questions | 97.7 % | none |
| IFC, held-out half of the full dataset (14 models, 503 questions) | 97.2 % | none |
| opening_design sheets, PDF text layer + Nemotron (64 questions) | 85.9 % | ≈16,700 tokens/question |
| Same sheets, image only | 23.4 % | ≈15,200 tokens/question |
| Same sheets as screenshots, local tiled OCR | 21.9 % | ≈21,700 tokens/question |
| cubicasa5k PNG, Nemotron 3.5 Super VL (351 questions) | 63.2 % | ≈1,600 tokens/question |

- Independent re-run: the coordinator ran `node bench/swiss-dxf.mjs --split test` on 2026-11-15 at 0ef075a and got 1232/1278 = 96.4%, 2 abstentions, 0 errors.
- The split is self-made (salted SHA-256 of drawing path); the sponsor's final protocol is unpublished. Tuning used development drawings only.
- Answers return entity IDs and source coordinates, and the UI highlights them on the imported drawing. Unsupported questions abstain.
- Sponsor sample `data/swiss_dwellings/site1102_bldg2242_floor10281.dxf` (SHA-256 `4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d`) is fetched by byte range into a local temp path and never committed.

## Reproduce

```sh
cd solutions/stoa-blueprint-studio
node --test tests/*.test.mjs
node bench/swiss-dxf.mjs --split test
node bench/ifc.mjs
# raster and sheet routes: see raster/README.md
```

## Open limits

- The DXF route covers 2,358 of the 7,990 preview questions (every Swiss PDF has a DXF of the same name).
- The IFC rules were developed on the Esplanades model and one Molio storey, so 97.7 % is not strictly held-out; 97.2 % is.
- The 249 free-form `ifc_bench` text questions are not attempted.
- Raster PNG (63.2 %) is not more accurate than its baseline on held-out drawings; its benefit is roughly a third of the tokens.
- OCR of screenshot sheets (about 22 %) is no better than image-only (23.4 %); the vector source is what makes the strong routes work.
- No DWG decoder and no HATCH surface extraction. No citation IoU has been measured.
- No deployment; the licence covers non-commercial Junction use only.

## Next steps

1. Measure citation IoU against ground-truth boxes.
2. Attempt the free-form `ifc_bench` text questions.
3. Improve raster and screenshot routes with region-first retrieval and sparse model calls, with deterministic constraints and abstention.
4. Add DWG and HATCH ingestion.
