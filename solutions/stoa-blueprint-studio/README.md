# STOA / ATLAS — Grounded Blueprint Intelligence

## Review and revision workspace

The app now separates method-based evidence levels from locally declared human review, exports
canonical source-bound evidence packets, restores same-source/same-engine reviews, records
corrections with Undo/Redo, and compares DXF room/primitive revisions and IFC GUID records.
An instance scorer exposes split/merged objects even when the total count is correct.
See [the workspace guide](WORKSPACE.md) for the UI, CLI commands, source binding and explicit limits.
No real-data accuracy or physical-change qualification is implied by these new tools.

## Current reliability revision (15 Nov 2026)

The active HTTP engine now requires closed, unambiguous room boundaries and one matching area
annotation within 2%, including every contributing room in an aggregate. Open/curved boundaries,
conflicting or missing annotations, incomplete IFC totals, unsupported room-scoped counts and
missing fixture evidence abstain. A supported zero is not inferred from a missing fixture layer.

**The accuracy tables below describe the earlier engine, not this stricter revision.** Its answer
coverage and accuracy have not been remeasured on the licensed dataset. Do not reuse those figures
as current qualification. No sponsor files were downloaded or model calls made for this revision.

The local app now imports **DXF (6 MiB)** and **IFC STEP (16 MiB)**. IFC citations open original
entity/property/quantity records and SI unit definitions; they do **not** imply a projected floor
plan or spatial highlighting. IFC questions use exact quoted storey/room names. For example:

- `How many doors are there on 'Ground'?`
- `What is the net floor area of the room 'Room (101)' on 'Ground'?`
- `What is the property 'FireRating' of entity #22?` (literal stored scalar, no inferred units)

DXF HATCH support is limited to **one explicitly closed, straight polyline boundary**, retaining
native HATCH citations. Holes, curved boundaries and edge-defined HATCH paths reject import rather
than reporting a wrong area. Curved LWPOLYLINE boundaries cannot establish areas.

Citation-box scoring is now available offline: `node benchmark/regions.mjs <regions.json>`.
See [region evaluation](benchmark/REGIONS.md) and the prioritized [next capabilities](IMPROVEMENTS.md).
This supplies a scorer, **not measured sponsor citation IoU**.

## For judges (60-second summary)

**What it does.** Ask a natural-language question about a construction drawing and get an exact answer plus clickable, highlighted source geometry (polygons, text, entities) on the real drawing. When the evidence is insufficient, it abstains instead of guessing.

**Sponsor rubric (25% each).**
- Accuracy: deterministic DXF and IFC parsers; areas are accepted only when annotation and polygon geometry agree within 2%.
- Highlighted evidence: every answer returns entity IDs and source coordinates; click a citation to highlight it on the drawing.
- Creativity: proof-first answer cards, local ingest, zoom, and adversarial abstention in one interactive surface.
- Inference cost: the DXF and IFC routes use zero model calls. The model is used only for sheet context and raster plans.

**Headline numbers** (official preview questions, self-made held-out split; table below):
- DXF: 96.4% on the held-out test split (1,278 questions), 98.0% on dev, at zero model cost.
- IFC: 97.7% on the preview, 97.2% on 14 held-out models, at zero model cost.
- Construction sheets, PDF text layer plus Nemotron: 85.9% at about 16,700 tokens/question.

**Weak routes, stated plainly.** Raster PNG plans reach 63.2%, screenshot OCR about 22%, and image-only sheets 23.4%. The DXF route covers 2,358 of the 7,990 preview questions, and the split is our own because the sponsor's final protocol is unpublished.

**Demo (2 minutes).** `npm start`, open http://127.0.0.1:4315, then ask `How many rooms labelled Stanza?` and `How many doors are there?` (it refuses). Next run `node scripts/fetch-sponsor-sample.mjs /tmp/stoa-verified-sponsor-sample.dxf`, use **Import DXF / IFC**, and ask `How many rooms labelled Stanza?` (9), `What is the area of room 5.02?` (15.84 m²) and the door and window counts (21 and 13).

**Why next year's models will not obsolete it.** Exact answers come from deterministic geometry and vector routes that a better model cannot improve on. A model is called only where the source has no vector data, so stronger models raise the weak routes while the strong ones stay exact and free.

**Junction 2026 · Stoa #335 · Make Blueprints Talk**

A runnable, private-by-default blueprint question studio. Answers become clickable marks on actual **source geometry**. The first vertical slice accepts ASCII DXF technical drawings, measures named room areas only when annotation and polygon geometry agree within 2%, counts named rooms and explicit unit-outline entities, and **abstains** when evidence is insufficient.

## Run

Requirements: Node.js 20+, no `npm install`, API keys, cloud service, model endpoint or external build.

```sh
cd solutions/stoa-blueprint-studio
npm start
# open http://127.0.0.1:4315
```

The app opens an explicitly **HANDCRAFTED / NOT VERIFIED** source fixture. Ask `How many rooms labelled Stanza?` (3 source points), `What is the area of room A-101?` (13.69 m² with 3 region citations), then `How many doors are there?` (correctly refuses to invent object counts).

## Prove it against Stoa's real licensed preview

The sponsor published a [public, non-commercial challenge preview ZIP](https://fwjydgxpttajiqpfmqtj.supabase.co/storage/v1/object/public/stoa-junction-2026/junction-dataset-preview.zip). The full archive is ~478 MiB, but the following helper fetches **only one sample** with byte-range requests and checks the exact sponsor source SHA-256. The drawing is written to the user-selected local temporary path, **never to git**.

```sh
node scripts/fetch-sponsor-sample.mjs /tmp/stoa-verified-sponsor-sample.dxf
STOA_SPONSOR_DXF=/tmp/stoa-verified-sponsor-sample.dxf npm test
npm start
```

Then use **Import DXF / IFC** in the UI to select the downloaded sample and ask:

| Question | Result from actual sponsor DXF | Exact evidence |
| --- | ---: | --- |
| `How many rooms labelled Stanza?` | 9 | 9 original `ROOM_TEXT` insertion points |
| `Quanti locali con la denominazione «Stanza» ci sono in questo piano?` | 9 | Same 9 positions, language-independent label matching |
| `How many rooms labelled Cucina?` | 2 | 2 exact labels |
| `How many rooms labelled Corridoio?` | 3 | 3 exact labels |
| `How many apartments (residential units) are shown?` | 2 | 2 `UNIT_OUTLINE` source polylines |
| `What is the area of room 5.02?` | 15.84 m² | Closed `ROOM_OUTLINE` shape, room `5.02` text, `15.84 m²` text; measured 15.8414 m² |
| `How many doors (interior doors and entrance doors together) are drawn on this floor plan?` | 21 | `src/quantities.mjs`: DOOR polylines − swing arcs (one opening line per door); every door part cited |
| `How many windows are drawn on this floor plan?` | 13 | three `WINDOW` lines per window |
| `How many toilets (WC) are drawn on this floor plan?` | 3 | `FIXTURE` rectangles whose own inner symbol is a bowl without a drain |

Actual sample path inside sponsor archive: `data/swiss_dwellings/site1102_bldg2242_floor10281.dxf`.

## Historical measurements before the reliability revision (15 Nov 2026)

Self-made held-out split (salted SHA-256 of drawing path; the sponsor's final protocol is unpublished).
All tuning on development drawings; the test split was run once per method. Scoring per the
preview README: counts exact, areas within 2 %.

| Route | Split | Questions | Correct | Model cost |
| --- | --- | ---: | ---: | --- |
| Swiss Dwellings, layered DXF sibling of each PDF — previous engine | test, 35 drawings | 1,278 | 39.0 % (abstains on 60 %) | none |
| Swiss Dwellings, layered DXF — `answerDrawingV2` | test, 35 drawings | 1,278 | **96.4 %** | none |
| Swiss Dwellings, layered DXF — `answerDrawingV2` | dev, 30 drawings | 1,080 | 98.0 % | none |
| ifc_models IFC + plan PDFs rendered from them — `src/ifc-qa.mjs` | all 3 models in the preview | 1,049 | **97.7 %** (1,025/1,025 where the model ships; 24 PDFs lack their IFC) | none |
| ifc_models, 10 GB full dataset — held-out half of 26 models never used for tuning | test, 14 models | 503 | **97.2 %** | none |
| opening_design construction sheets (A-801, A-701, A700) — sheet context: PDF text layer + Nemotron, 10 parallel | full dataset | 64 | **85.9 %** (count 34/39, area 8/9, text 13/16 lenient) | ≈16,700 tokens/question |
| same sheets, image only | full dataset | 64 | 23.4 % | ≈15,200 tokens/question |
| same sheets as screenshots: text from local tiled OCR (text layer ignored) | full dataset | 64 | 21.9 % | ≈21,700 tokens/question |
| same, text from a ScreenshotContext-configured Vision pass (single full-image pass) | full dataset | 64 | 20.3 % | ≈16,900 tokens/question |
| cubicasa5k PNG — Nemotron 3.5 Super VL, one reasoning call per drawing | test, 40 drawings | 351 (English) | 63.2 % | ≈1,600 tokens/question |
| cubicasa5k PNG — same, 16-drawing subset | test | 141 | 56.0 % | ≈1,600 tokens/question |
| cubicasa5k PNG — baseline, one reasoning call per question | test, same 16 | 141 | 61.0 % | ≈5,200 tokens/question |

Reproduce: `node bench/swiss-dxf.mjs --split test` (no network after the first cached fetch,
no model), `node bench/ifc.mjs` and `raster/README.md`. The IFC reader (`src/ifc.mjs`) is a
dependency-free STEP parser: counts come from typed elements contained in each storey; areas,
lengths and volumes from stored base quantities (`NetFloorArea`, `Length`, `NetSideArea`,
`NetVolume`), otherwise the measured plan area of the space geometry. Its rules were developed on
the Esplanades model and one Molio storey, so the IFC figure is not a strictly held-out result.
The 249 free-form `ifc_bench` text questions are not attempted yet.

OCR on construction sheets rendered at 7,168 px, scored against the PDF text layer: adaptive tiled
Vision OCR recovers 45–49 % of the sheet tokens, a single full-image pass (ScreenshotContext's
configuration) 3–8 %. At that OCR quality schedule questions are no better than image-only, so the
vector source (PDF text layer, DXF, IFC) is what makes the 86–97 % routes possible. The Swiss route covers 2,358 of the 7,990 preview questions
(every Swiss PDF has a DXF of the same name). The raster result is not an accuracy gain over the
baseline on held-out drawings; its benefit is roughly a third of the tokens.

Source SHA-256: `4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d`.

Attribution: **Swiss Dwellings v3.0.0** (Matthias Standfest, Michael Franzen, Yvonne Schröder, Luis Gonzalez Medina, Yarilo Villanueva Hernandez, Jan Hendrik Buck, Yen-Ling Tan, Milena Niedzwiecka, Rachele Colmegna / Archilyse AG); [doi:10.5281/zenodo.7788422](https://doi.org/10.5281/zenodo.7788422), **CC BY 4.0**. The actual DXF was rendered as a derivative by the Stoa/Junction dataset producers, who do not imply Archilyse endorsement. Non-commercial Junction usage only; do not re-export sponsor drawings without verifying per-source licences. Source questions are from the official preview, not generated claims. The Swiss `UNIT_OUTLINE` geometries omit the DXF `closed` flag but explicitly repeat their first vertices as final vertices; the engine recognizes these complete rings while refusing genuinely open paths.

## Sponsor rubric

1. **25% accuracy**: parse vector facts; areas check both annotation and actual closed polygon; no guesses about door/window symbols.
2. **25% human-verifiable region**: every supported answer returns one or more entity IDs and source coordinates; click the citation to highlight the polygon/text on the real imported drawing.
3. **25% creativity**: a polished interactive engineering surface with proof-first answer cards, inspection states, local ingest, zoom, dynamic sheet geometry and adversarial abstention.
4. **25% low inference cost**: deterministic Node math and DXF group parser, **zero model API calls**. Expanding to fuzzy plan interpretation will require a measured CPU/GPU retrieval fallback, not an LLM per entire sheet.

## Non-goals and honest limitations

- Supports **ASCII DXF** `LWPOLYLINE`, `LINE`, `TEXT`, `MTEXT`, `ARC`, `CIRCLE` ingestion. Door, window and fixture counts rely on the measured layer conventions documented in `src/quantities.mjs`; drawings that break them abstain. No DWG decoder. Single-loop straight HATCH regions are supported; complex HATCH is rejected. IFC models are available in the app through `src/ifc-qa.mjs`; raster plans remain a separate model-based `raster/` evaluation.
- A real sponsored drawing is ingested without persisting raw bytes; only the extracted geometry is kept in this process for at most 30 minutes (3 imports maximum). No deployment or external data transfer by this app. A malicious client could forge an on-screen drawing's import content; production needs signed storage/provenance.
- Measured results cover the routes in the table above on a self-made split, not all 7,990 preview questions or the ~120,000 questions in the full corpus. The sponsor's final protocol is unpublished, so treat the figures as our own held-out measurements.
- Unit-outline counts are only accepted from explicit `UNIT_OUTLINE` layer primitives; they must be manually confirmed if a different drawing convention uses other layers.

## Focused verification

```sh
npm test
# optional separately downloaded official sample:
STOA_SPONSOR_DXF=/tmp/stoa-verified-sponsor-sample.dxf npm test
```

Do not add a broad repetitive CI/test gate; these checks focus on geometry correctness, source links, negative evidence, import input bounds, HTTP privacy and sponsor source agreement.

## Reuse after completion

Stoa remains a completed reference project. Reusable source-evidence, review and replay code now
has a standalone pilot in [Evidence Kit](../../services/evidence-kit/README.md), with independent
DXF/CSV consumers and synthetic fixtures. This does not change this app's runtime or historical
measurements.
