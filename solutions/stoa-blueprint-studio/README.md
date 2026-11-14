# STOA / ATLAS — Grounded Blueprint Intelligence

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

Then use **Import real DXF** in the UI to select the downloaded sample and ask:

| Question | Result from actual sponsor DXF | Exact evidence |
| --- | ---: | --- |
| `How many rooms labelled Stanza?` | 9 | 9 original `ROOM_TEXT` insertion points |
| `Quanti locali con la denominazione «Stanza» ci sono in questo piano?` | 9 | Same 9 positions, language-independent label matching |
| `How many rooms labelled Cucina?` | 2 | 2 exact labels |
| `How many rooms labelled Corridoio?` | 3 | 3 exact labels |
| `How many apartments (residential units) are shown?` | 2 | 2 `UNIT_OUTLINE` source polylines |
| `What is the area of room 5.02?` | 15.84 m² | Closed `ROOM_OUTLINE` shape, room `5.02` text, `15.84 m²` text; measured 15.8414 m² |
| `How many doors are there?` | **Abstain** | Source uses multiple door primitives; simple entity count would mislead |

Actual sample path inside sponsor archive: `data/swiss_dwellings/site1102_bldg2242_floor10281.dxf`.

Source SHA-256: `4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d`.

Attribution: **Swiss Dwellings v3.0.0** (Matthias Standfest, Michael Franzen, Yvonne Schröder, Luis Gonzalez Medina, Yarilo Villanueva Hernandez, Jan Hendrik Buck, Yen-Ling Tan, Milena Niedzwiecka, Rachele Colmegna / Archilyse AG); [doi:10.5281/zenodo.7788422](https://doi.org/10.5281/zenodo.7788422), **CC BY 4.0**. The actual DXF was rendered as a derivative by the Stoa/Junction dataset producers, who do not imply Archilyse endorsement. Non-commercial Junction usage only; do not re-export sponsor drawings without verifying per-source licences. Source questions are from the official preview, not generated claims.

## Sponsor rubric

1. **25% accuracy**: parse vector facts; areas check both annotation and actual closed polygon; no guesses about door/window symbols.
2. **25% human-verifiable region**: every supported answer returns one or more entity IDs and source coordinates; click the citation to highlight the polygon/text on the real imported drawing.
3. **25% creativity**: a polished interactive engineering surface with proof-first answer cards, inspection states, local ingest, zoom, dynamic sheet geometry and adversarial abstention.
4. **25% low inference cost**: deterministic Node math and DXF group parser, **zero model API calls**. Expanding to fuzzy plan interpretation will require a measured CPU/GPU retrieval fallback, not an LLM per entire sheet.

## Non-goals and honest limitations

- Supports **ASCII DXF** `LWPOLYLINE`, `LINE`, `TEXT`, `MTEXT`, `ARC`, `CIRCLE` ingestion. No PDF raster OCR, DWG decoder, IFC/3D, HATCH surface extraction, dimension rotation, multilingual semantic translation, or automatic doors/windows instance segmentation yet.
- A real sponsored drawing is ingested without persisting raw bytes; only the extracted geometry is kept in this process for at most 30 minutes (3 imports maximum). No deployment or external data transfer by this app. A malicious client could forge an on-screen drawing's import content; production needs signed storage/provenance.
- This is **one measured source proof**, not a benchmark of all 7,990 preview questions or the ~120,000 questions in the full corpus. Avoid broad sponsor accuracy claims until a held-out sample, geometry citations, and licensing controls are reviewed.
- Unit-outline counts are only accepted from explicit `UNIT_OUTLINE` layer primitives; they must be manually confirmed if a different drawing convention uses other layers.

## Focused verification

```sh
npm test
# optional separately downloaded official sample:
STOA_SPONSOR_DXF=/tmp/stoa-verified-sponsor-sample.dxf npm test
```

Do not add a broad repetitive CI/test gate; these checks focus on geometry correctness, source links, negative evidence, import input bounds, HTTP privacy and sponsor source agreement.
