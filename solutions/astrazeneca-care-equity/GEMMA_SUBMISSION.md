# Best Use of Gemma: "Gemma reads, code counts" (SAMA Care Equity Navigator)

All paths are relative to `solutions/astrazeneca-care-equity/`. Every note is SYNTHETIC (written by a language model); nothing here is a clinical claim or a medical device (`serve/README.md`).

## Problem
Finnish county cancer-pathway delays can only be compared fairly if event dates are reliable. Many dates sit in free-text notes ("lähete lähetettiin kolme viikkoa sitten"). A scribe that misreads them manufactures fake county inequality: a county read by the raw scribe is flagged in 1.000 of 1,000 no-difference simulations, 0.003 with code-resolved dates (`DATA_COLLECTION.md` section 4; `README.md` track 1).

## What Gemma does
- Gemma 3 (instruction-tuned, ungated Unsloth mirrors `unsloth/gemma-3-270m-it`, `-1b-it`) plus a LoRA adapter reads a Finnish note and copies each date phrase and event type as JSON (`TRAINING.md`, `serve/README.md`).
- Code does the arithmetic: a frozen rule-based resolver (`scribe/v3/resolve.py`, sha256 in `data/scribe/v4/resolver/freeze.json`) turns the phrase into a date. Raw Gemma got a relative date exactly right on only 2/367 test notes (`runs/diagnose/diagnose-v1.json`); with the resolver 651/700 test notes are exact (`data/scribe/v4/resolver/reproduce-v1.json`).
- Output is a proposal only: a person confirms every event (`README.md` track 2).

## Why an open model (only what the code supports)
- Small enough to run offline: the demo runs the 270M model with the merged adapter on CPU in one persistent process, with `HF_HUB_OFFLINE=1`, and the page calls no hosted model (`serve/demo/README.md`, `serve/demo/engine.py`). Notes never leave the machine in that path.
- Fine-tunable: LoRA r16 on attention and MLP projections; the 270M adapter trains in 176 s on one A100 (`TRAINING.md` section on recommendation; `data/scribe/v2/ablation-v1.json`).
- Not measured: cost per note, CPU latency in the demo beyond `data/scribe/demo/http-timing.json`, or privacy/compliance review. No claim is made for them.

## Technical execution (numbers from files)
- Training data: 2,466 Nemotron-written notes (1,716 train) and 898 Claude Haiku-written notes, each gated by a code check and the TypeSafe Jev judge; 1,506 round-2 notes added (`data/scribe/dataset-stats.json`, `data/scribe/v2/dataset-stats.json`, `data/scribe/v3/summary-v1.json`). Claude Sonnet full-read audit: 2/60 labels wrong (`data/scribe/label-audit-v1.json`). No real patient data.
- Ablation on one A100 (`data/scribe/v2/ablation-v1.json`): 270M LoRA r16 selected; test exact match 42.0% on 500 Nemotron notes, 13.0% on 200 Haiku notes. Pooled 700 notes: product adapter `C-270m-all-v2data` 43.6% absolute-date, Gemma 3 1B 38.6% post hoc (`data/scribe/v3/student/compare-v1.json`).
- Preregistered stress set, 308 notes, frozen with sha256, each system read once (`data/scribe/v4/eval/results-v1.json`, `scribe/v4/RESULTS.md`), exact notes:
  - Gemma 3 270M + resolver A': 88/308 (held-out phrasings 0/143, standard 76/87)
  - Gemma 3 270M expression format B: 85/308 (held-out 11/143); preregistered criterion NOT met
  - Gemma 3 1B expression format C: 223/308 (held-out 95/143, standard 84/87)
  - Nemotron reader v3: 280/308, but it wrote the notes, so optimistic
- Test set (700, read before, so post hoc): 1B 684/700 (97.7%), 270M+A' 668/700, Nemotron 690/700.
- Two-reader agreement (Gemma 1B + Nemotron, thresholds chosen on validation): 684/700 test notes pre-filled, 4 wrong; stress 220/308 pre-filled, 3 wrong; Gemma confidence alone on stress would pre-fill 308 with 85 wrong (`scribe/v4/RESULTS.md`).
- Vague phrases: a frozen post-hoc Finnish rule catches 23/29 vague stress notes; A' sends 29/29 to a person; B invents a date for 17/29 (`scribe/vague/README.md`, `data/scribe/vague/results-v1.json`).
- Serving: vLLM 0.29.0 on the A100, 100 held-out notes, valid JSON 100/100 with structured outputs, p50 1.28 s, p95 1.80 s (`serve/smoke/smoke-guided.json`). CPU vs CUDA parity on 310 validation notes: 1 note exact only on CPU, 0 only on CUDA (`data/scribe/demo/cpu-vs-cuda-val310.json`).
- Provenance: commits `e56bbfb` (Gemma scribe, stress evaluation) and `11c775a` (local-reader comparison, live Nemotron second reader).

## Demo and verification (commands exist in the repo)
```sh
cd solutions/astrazeneca-care-equity
npm start                                   # web page; POST /api/scribe runs the local Gemma worker
SAMA_SCRIBE_LIVE=0 npm start                # stored outputs only, no model
curl -s -X POST localhost:4179/api/scribe -H 'Content-Type: application/json' -d '{"demo_id":"demo-01"}'
python3 -m unittest discover -s serve/demo/tests   # 19 tests, OK (1 skipped: needs the model)
python3 -m unittest discover -s scribe/vague/tests # 7 tests, OK
python3 -m pytest -q scribe/v4/tests scribe/vague/tests   # 15 passed
```
Fallback recording of the demo: `submission/fallback`.

## Honest limits
- Synthetic Finnish notes only, one language, one seed per run, no real-world validation (`serve/README.md`, `TRAINING.md`).
- The 270M reader fails on unseen phrasings (0/143 held out for the rule arm, 11/143 for the learned arm); the 1B reaches 95/143. The preregistered 270M criterion was not met.
- Reported test figures are post hoc and optimistic: the winner was picked among arms whose test results had been seen (`TRAINING.md`).
- Gemma is not the strongest reader: Nemotron beats it on the stress set; Gemma's value is the cheap local first reader plus agreement gating.
- Verda serverless deployment is planned, not executed; vLLM ran once on a rented A100 (`serve/README.md`, `serve/deploy.md`).
- No 4B result (out of GPU memory twice); not a clinical tool; Gemma Prohibited Use Policy names automated healthcare decisions, so a person confirms every event.
