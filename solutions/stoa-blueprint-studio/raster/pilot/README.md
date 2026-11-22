# Offline raster room annotation pilot

Run from the Stoa solution directory with Node 20+, Tesseract with English language data,
Python 3 with Pillow for OCR retries, and Poppler for PDF. Process locally supplied files whose use has been authorized. The pilot
runs external parsers and belongs in an isolated local runner for unfamiliar files.

```sh
node raster/pilot/scan.mjs raster/pilot/fixtures/reference.png 102
node raster/pilot/scan.mjs raster/pilot/fixtures/reference.pdf --page-data 1
node raster/pilot/evaluate.mjs
```

The CLI returns an OCR observation or an abstention. It accepts a room identifier followed by a
nearby area line with an explicit square metre unit. Inspect both cited boxes before relying on
an observation. Page and raster hashes distinguish PDF bytes from the exact raster sent to OCR.
Coordinates are upper-left raster pixels. Missing results do not establish that a room is absent.
The layout rule is intentionally narrow and requires qualification on each new drawing convention.

The scale check accepts two operator-labelled segments bound to the raster digest. Agreement
within 2% and orthogonal controls are required. This only establishes agreement of the supplied
segments. Raster polygon extraction and physical area computation are outside the pilot.
Use known vector geometry for measured area.

The fixture geometry in `plan.svg` has known areas of 12, 16, 9 and 12 square metres.
The checked-in PNG/PDF reference files use OCR-friendly `m2`. The suite includes superscript,
rotation, noise and cropping, pins source hashes and scores expected values, abstentions and
citation boxes independently, including rotated boxes transformed from the reference layout.
The evaluator fails on wrong positive answers, failed negative cases, unmatched scored
predictions, failed scale checks or missing required clean observations.

Use `node raster/pilot/evaluate.mjs --baseline` for the original single OCR pass.
The default retries uncertain area labels in small magnified crops and checks three bounded
views of smaller pages: twice the resolution and rotations of ±2°. This is a bounded set of
corrections. Other rotation angles can still fail. Conflicting confident readings or regions
cause abstention. A retry-only result requires corroboration of the room identifier.
Citations are mapped back to the original raster. Views that are too large for full-page
retries still get the bounded crop retries.

Observed on the same synthetic inputs with Tesseract 5.5.0 and Poppler 26.05.0:

| Mode | Correct printed values | Incorrect values | Correct abstentions | Matched regions |
| --- | ---: | ---: | ---: | ---: |
| Single pass | 13/22 | 0 | 8/8 | 26/44 |
| Retry | 22/22 | 0 | 8/8 | 44/44 |

Both scale cases passed in both modes. These are development cases.
Use [A-101](IMAGEGEN-A101.md) as a manual ImageGen stress case. Its image bytes were unavailable
to the runner, so no OCR result is claimed for that image.

## Agent integration

From a pinned monorepo checkout, use `rasterAdapter(page)` and `readPrintedArea(dataset, room)`
from `evidence-kit.mjs`. Ingest authorized bytes with a meaningful filename and rights;
pass `expectedSha256` when separately known. Resolve the returned Evidence Kit references and
use the claim checks for original-page pixel boxes. Export and replay with the usual Evidence
Kit packet functions and the same page and room. The adapter invokes local OCR and can differ
across tool versions. This bridge lives alongside the Stoa reader and requires the monorepo.
The claim level is a printed-source observation awaiting region inspection.

For a held-out run, pass a separate JSON manifest to the evaluator. Keep authorized drawings
and manifests outside git. Use the suite as the format example. Pin file hashes, provide page
numbers, independently label values and normalized boxes, and include ambiguous or missing
labels. Label rotated cases in their actual rendered coordinate space. Archive the report with
tool versions and compare coverage, wrong answers, abstentions and citation precision/recall.
A real-document qualification run requires such a corpus and is pending.
