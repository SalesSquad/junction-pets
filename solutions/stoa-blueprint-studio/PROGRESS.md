# Stoa Atlas — Verified delivery ledger

Status: **local implementation + source-bound focused verification; branch/PR status tracked separately**.

## Verified

- Sponsor Stoa `Make Blueprints Talk` brief from Junction challenge research and Space `page_57e6862bd6988191b1fb3aa3258f0e6d`: 25% accuracy, 25% highlighted source evidence, 25% creativity, 25% inference cost.
- Sponsor Supabase dataset preview ZIP HTTP 206 range readable: 501,564,891 bytes, 924 files (123 PDFs, 66 DXFs, 14 IFCs, 306 PNGs, 374 JPEGs and supplementary formats), 7,990 QA entries. Full 501 MB archive intentionally not downloaded.
- Exact original sample `data/swiss_dwellings/site1102_bldg2242_floor10281.dxf`, 168,987 uncompressed bytes, SHA-256 `4070c5f19eb921bc08e2f5a23e957086f76abcca03fafbb8b62ca30c8a60b58d`; Swiss Dwellings CC BY 4.0 with attribution. Sample was read from byte ranges into a local transient `/tmp` only, never committed.
- Sponsor official Q&A verified with real DXF layer evidence: `Stanza` **9**, `Cucina` **2**, `Balcone` **2**, `Corridoio` **3**, apartments **2**. Geometric cross-check `room 5.02` polygon **15.8414 m²**, original label **15.84 m²** (difference under 2%).
- Offline 100%-deterministic supported answer paths and **abstention** path for unsupported door counts, absent room numbers, ambiguous area names, scale errors, conflicting labels, and injection language.
- Responsive front-end with SVG projection, click-to-highlight citations, evidence IDs, bounded memory upload, no external inference and source SHA provenance.

## Not yet verified / not claimed

- No inference across raster PDFs or non-DXF files, no per-question macrobenchmark over sponsor's whole dataset, no held-out geometric citation IoU, no third-party model/vision contract, no producer deployment. Sponsor licensing checked for this Swiss subset only.
- Product workspace integration PR #82 is separate and may still be open; this branch only adds owned solution files.

## Next competition-quality product upgrades

1. **Source catalog**: file/version/coordinate-frame manifest, native PDF+SVG+DWG+IFC connectors with per-file licence and page/element provenance.
2. **Symbol topology**: detect door/window clusters, scale/orientation, nested room graph, cross-floor BIM quantities; never infer object counts from primitive counts.
3. **Region evidence benchmark**: stratify official preview count/area/length/volume/text questions, ground-truth visual boxes and geometry, negative questions, exact-match/2%-tolerance plus citation IoU and cost per question.
4. **Measured vision fallback**: cheap region-first retrieval, sparse VLM for uncertain visual classes, deterministic constraints and explicit abstain; report latency and monetary budget.
5. **Competition demo**: verified real sponsor drawing imported in front of judges; query→measure→highlight under one interaction, no hidden fixture substitution, licence credit always visible.
