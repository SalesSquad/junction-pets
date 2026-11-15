# Offline scribe demo (CPU)

"Gemma reads, code counts" on a laptop without a network: Gemma 3 270M (`unsloth/gemma-3-270m-it`, revision pinned in
`scribe/v2/config.py`) with the PEFT LoRA adapter `scribe/v3/artifacts/C-270m-all-v2data/adapter` runs in one
persistent CPU process. The frozen date resolver (`scribe/v3/resolve.py`, arm A' when the hashes in
`data/scribe/v4/resolver/freeze.json` match, otherwise arm A) then dates every relative phrase. The screen shows the
note, the highlighted date phrases, what Gemma wrote, the dates code computed, and that a person confirms every event.
Trained and tested on SYNTHETIC notes only. Research demo, not a medical device.

| File | What it is |
| --- | --- |
| `engine.py` | Model loading (CPU, float32, LoRA merged, greedy, 134 new tokens at most) and the pure post-processing (`serve/client.py` `decode_output` plus the resolver) |
| `worker.py` | The persistent process: JSON lines on stdin and stdout, model loaded once, exits when stdin closes |
| `precompute.py` | `select` the 20 demo notes, `run` them through the worker (fallback outputs plus the CPU-vs-CUDA comparison), `compare-val` all 310 validation notes |
| `tests/` | `test_engine.py` (no model; `SAMA_SCRIBE_SLOW=1` also loads it) and `scribe-route.test.mjs` (the web route against a fake worker) |

## Run

```sh
npm start                                  # POST /api/scribe starts the worker on first use
SAMA_SCRIBE_PRELOAD=1 npm start            # load the model with the server (first request then takes seconds, not tens)
SAMA_SCRIBE_LIVE=0 npm start               # precomputed outputs only

curl -s -X POST localhost:4179/api/scribe -H 'Content-Type: application/json' -d '{"demo_id":"demo-01"}'
curl -s -X POST localhost:4179/api/scribe -H 'Content-Type: application/json' \
  -d '{"note_text":"Lähete lähetettiin kolme viikkoa sitten.","note_date":"2025-03-10"}'
```

A request names a demo note (`demo_id`, the server reads its text from `data/scribe/demo/demo-notes.json`) or sends
`note_text` (at most 6,000 characters) and `note_date`. `"mode": "precomputed"` skips the model. When the live process
cannot answer, a demo note falls back to `data/scribe/demo/demo-outputs.json` (`served: "precomputed"`, with the
reason); free text gets 503. `web/scribe-demo.mjs` `scribeDemoHtml(response)` renders a response.

Two-reader rule: a result is pre-filled for one-click confirmation only when Gemma's answer (after the code resolver)
has no flag and equals Nemotron 3.5 Super VL's stored v3 answer for the same SYNTHETIC validation note
(`data/scribe/nemotron/val-v3.jsonl`; `engine.apply_second_reader`, mirrored by `applySecondReader` in
`web/scribe-demo.mjs`). The page never calls a hosted model, so free text and the 3 notes rewritten by code have no
second answer and need editing. A person confirms every event either way.

The base model must already be in the local Hugging Face cache (the worker sets `HF_HUB_OFFLINE=1` and never downloads).

## Rebuild the demo data

```sh
scribe/.venv/bin/python serve/demo/precompute.py select       # data/scribe/demo/demo-notes.json
scribe/.venv/bin/python serve/demo/precompute.py run          # demo-outputs.json, cpu-vs-cuda.json
scribe/.venv/bin/python serve/demo/precompute.py second-reader  # two-reader rule from stored answers (run also does it)
scribe/.venv/bin/python serve/demo/precompute.py compare-val  # cpu-vs-cuda-val310.json
node --test serve/demo/tests/ && python3 -m unittest discover -s serve/demo/tests
```

Each step appends one line to `runs/laneC-step7.jsonl`. Measured numbers live in the JSON files, not here.
