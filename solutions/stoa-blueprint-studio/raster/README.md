# Raster drawing QA — measured on official Stoa preview questions

The DXF engine in `../src` answers vector drawings deterministically. Most of the sponsor
preview is raster: 4,270 of its 7,990 questions are counts on `cubicasa5k` PNG floor plans
(Finnish real-estate plans: windows, doors, WC seats, sinks, showers, saunas, bedrooms…).
This folder measures and improves answers on those questions.

## Run

```sh
# Vision model: any OpenAI-compatible endpoint; defaults to the Verda-hosted Nemotron 3.5 Super VL.
export STOA_VLM_KEY=...              # host secret store only; never in git or logs
node raster/eval.mjs --strategy per-drawing-answers --split test --dev 40 --test 40
node raster/eval.mjs --strategy ocr-rules --split dev --dev 40 --test 40   # free, no model calls
```

Drawings and `questions.jsonl` are fetched by HTTP byte range from the public preview ZIP
(CRC-checked) into `~/.cache/stoa-junction-preview` (`STOA_CACHE`). Nothing from the dataset
is committed. cubicasa5k is CC BY-NC-SA 4.0: Junction non-commercial evaluation only.

Scoring follows the preview README: counts exact, areas/lengths/volumes within 2 %.
English questions only (each has a Finnish twin). The split is self-made because the
sponsor's final protocol is unpublished: drawings sorted by salted SHA-256 of the path,
first 40 = development (all prompt/rule tuning), next 40 = held-out test (run once per strategy).

## Strategies

| Strategy | Model calls | Idea |
| --- | --- | --- |
| `per-question` | one per question, reasoning on | naive baseline |
| `per-drawing` | one per drawing, reasoning off | enumerate every counted item as a point marker |
| `per-drawing-answers` | one per drawing, reasoning on | all questions in one call + Finnish plan legend |
| `answers-marked` | `per-drawing-answers` + one cheap call | adds one marker per counted item for human verification |
| `ocr-rules` | none | Apple Vision OCR (macOS) + door/window size tags + room abbreviations |
| `cascade` | one per drawing | OCR rules when they found evidence, model for the rest |

Key engineering findings:

- Nemotron's hidden reasoning can consume the whole output budget (16k+ tokens) on a
  multi-question drawing and return nothing. `chat_template_kwargs.enable_thinking=false`
  removes it; with reasoning on, asking for answers only (no point lists) stays bounded.
- Batching all questions of a drawing into one reasoning call is both more accurate and
  ~3.5× cheaper than one call per question.
- The model mixes 0..1, 0..1000 and pixel coordinates; `normalizeCoords` maps all three.
- Finnish architectural plans tag openings with decimetre sizes: `9x21/O` (≈2.1 m high) is a
  door, `13x12` a window. Vision OCR reads them, including vertical tags (0°/90°/270° passes,
  2×2 tiles). Many preview PNGs are too small or untagged, so rules only answer when they
  found positive evidence.

## Results

See the PR description for the measured table (exact source SHA, split, model, tokens).
