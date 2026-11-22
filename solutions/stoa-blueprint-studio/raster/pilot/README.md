# Offline raster room annotation pilot

Run from the Stoa solution directory with Node 20+, Tesseract with English language data,
and Poppler for PDF. Process locally supplied files whose use has been authorized. The pilot
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
citation boxes independently. Expected citation boxes are derived from labelled locations in
the fixture layout, with no rotated box ground truth. The evaluator fails on wrong positive
answers, failed negative cases, unmatched scored predictions, failed scale checks or missing
required clean observations. Coverage on stress cases remains separately visible.

Observed with Tesseract 5.5.0 and Poppler 26.05.0 on the frozen synthetic suite: 13 of 22
printed values read correctly, nine unread, zero incorrect, eight of eight expected abstentions,
26 of 26 predicted boxes matched (36 expected boxes), and two of two scale cases passed.
Use [A-101](IMAGEGEN-A101.md) as a manual ImageGen stress case. Its image bytes were unavailable
to the runner, so no OCR result is claimed for that image.

For a held-out run, pass a separate JSON manifest to the evaluator. Keep authorized drawings
and manifests outside git. Use the suite as the format example. Pin file hashes, provide page
numbers, independently label values and normalized boxes, and include ambiguous or missing
labels. Label rotated cases in their actual rendered coordinate space. Archive the report with
tool versions and compare coverage, wrong answers, abstentions and citation precision/recall.
A real-document qualification run requires such a corpus and is pending.
