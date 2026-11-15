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
- Batching all questions of a drawing into one reasoning call costs about a third of the tokens
  of one call per question; on held-out drawings its accuracy is on par, not better (see Results).
- The model mixes 0..1, 0..1000 and pixel coordinates; `normalizeCoords` maps all three.
- Finnish architectural plans tag openings with decimetre sizes: `9x21/O` (≈2.1 m high) is a
  door, `13x12` a window. Vision OCR reads them, including vertical tags (0°/90°/270° passes,
  2×2 tiles). Many preview PNGs are too small or untagged, so rules only answer when they
  found positive evidence.

## Results (cubicasa5k, English questions, Nemotron 3.5 Super VL on Verda)

| Strategy | Split | Questions | Correct | Tokens / question |
| --- | --- | ---: | ---: | ---: |
| `per-question` (baseline) | dev, 8 drawings | 72 | 45.8 % | 5,516 |
| `per-drawing` (reasoning off) | dev, 8 | 72 | 29.2 % | 252 |
| `per-drawing-answers` | dev, 8 | 72 | 69.4 % | 1,563 |
| `per-drawing-answers` | dev, 40 | 358 | 63.7 % | 1,502 |
| `per-drawing-answers` + 2048 px upscale | dev, 40 | 358 | 62.3 % | 1,749 |
| `cascade` (OCR rules first) | dev, 40 | 358 | 60.9 % | 1,677 |
| `ocr-rules` (no model; symbol questions unanswered) | dev, 40 | 358 | 24.3 % | 0 |
| `per-drawing-answers` | **test, 40** | 351 | **63.2 %** | 1,593 |
| `per-drawing-answers` | test, 16-drawing subset | 141 | 56.0 % | ≈1,600 |
| `per-question` (baseline) | test, same 16 | 141 | 61.0 % | 5,168 |

The dev-8 gain did not hold on held-out drawings: accuracy is on par with (on 16 drawings,
slightly below) the per-question baseline, at about a third of the tokens. Weakest classes on
dev-40: windows 6/40 and doors 5/31 (dense symbols undercounted); strongest: balconies 9/9,
storeys 38/40, bathrooms 16/18, kitchens 25/28. Next step for symbols: a small detector trained on
public CubiCasa5K annotations, excluding every image that appears in the Stoa dataset.
