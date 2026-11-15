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
