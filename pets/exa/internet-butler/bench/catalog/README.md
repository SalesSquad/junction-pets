# Semantic catalog on the device

Which provision sets the amount for this situation? EmbeddingGemma (300M parameters, MLX) embeds every
amount-bearing provision once; a local service embeds the person's message as written, in any language, and
returns the nearest provisions that existed in the event's year. Nothing leaves the machine.

| File | What it does |
|---|---|
| `build_catalog.py` | One row per provision (title, part, section) that carries an amount in any annual CFR edition 1996-2026 of titles 12, 14, 16, 20, 29 and 49: heading plus its most informative amount clauses, about 1,200 characters. Writes `out/catalog.jsonl`, `out/embeddings.npy` (float16, 5,924 x 768, 9 MB) and `out/manifest.json`. |
| `serve_catalog.py` | `POST /search {query, k, year}` on 127.0.0.1:8791 (`npm run catalog:local`). 10 to 25 ms per query after warm-up. The relay uses it as one more source of provision candidates and as the only search in private mode. |
| `export_registry.mjs` | Writes the app's ten built-in rights as `out/registry.json`; the service embeds their descriptions and returns them as a separately scored set, so private mode and the rights search recognise them in any language. |
| `eval_discovery.py` | The measurement below, on the items of the Exa discovery study, with a BM25 baseline and paired tests. |
| `embedder.py` | The MLX model and its ONNX (transformers.js) export behind one interface. |
| `scout_*.py` | The first checks: which runtime works, speed, memory, data facts. |

## Measured (1,200 situations, one per provision; English 668, Finnish 274, German 258)

| | Right section first | Right section in top 5 | Right part in top 5 |
|---|---|---|---|
| Exa on official domains (raw message) | 16.5 % | 25.9 % | 43.0 % |
| BM25 over the catalog text (US items) | 32.1 % | 45.5 % | 54.5 % |
| **Catalog (EmbeddingGemma)** | **43.8 %** | **66.3 %** | **74.6 %** |
| Catalog or Exa (ten candidates) | | 69.2 % | 77.9 % |

Top 5 by language, catalog against Exa: English 75.9 % / 39.1 %, German 64.3 % / 15.1 %, Finnish 44.9 % / 4.0 %.
Paired on the same items: the catalog finds the section where Exa does not in 519 cases, the reverse in 34.

## Read this before quoting the numbers

- The catalog is closed: about 5,900 provisions of six CFR titles, one of which is always the answer. Exa
  searches the open web. The comparison says what a catalog buys on its own coverage, above all across
  languages; it does not say the catalog is a better search engine.
- Every test situation was written by a language model from clauses of its gold provision, and the catalog text
  is built from the same clauses.
- "Right section" is the section the situation was written from; another section can be as reasonable.
- As a single pick the catalog is right 44 % of the time, so it gives candidates to a judge. In private mode its
  first hit is used as it is and the answer is always marked for review. Gemma 4 E2B with the clause-judge LoRA,
  asked to choose among the top five, did worse than the first hit (39.5 % against 43.8 % on 400 items).

## Rebuild

```bash
python3.12 -m venv .venv-catalog   # mlx, mlx-lm, numpy, pyarrow, transformers, sentencepiece, safetensors; mlx-embeddings and mlx-vlm with --no-deps
.venv-catalog/bin/python bench/catalog/build_catalog.py      # about 30 s on an M5 Pro; needs the CFR-Annual tables (CFR_DATA) and the model folder under out/models
.venv-catalog/bin/python bench/catalog/eval_discovery.py
npm run catalog:local
```

The model is `mlx-community/embeddinggemma-300m-bf16` (615 MB). `onnx-community/embeddinggemma-300m-ONNX` (q8)
gives query vectors that match the MLX index (cosine 0.98 to 0.99), so a browser can embed the query itself.
