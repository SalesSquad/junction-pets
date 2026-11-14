# Stress set v1 (SYNTHETIC)

Evaluation set for NVIDIA_OPTIONS.md step 8. Every note is SYNTHETIC, written by Nemotron 3.5 Super VL from an answer key; no real patient. Not for clinical use. A person confirms every extracted event.

**Do not train on this folder.** No training, augmentation or prompt-selection script may read `data/scribe/stress/`. The held-out phrasings (number words seven to twelve, "toissapäivänä") must stay out of every training split.

- `stress-v1.parquet`: the frozen set (notes that passed the code gate and the Jev gate). Its sha256 is in `stress-v1.parquet.sha256`.
- `preregistration.json`: arms, primary comparison (B against A' on held-out phrasing), success thresholds from step 8, slice and vague-phrase scoring. Written together with the parquet, before any scored system saw a note. Each system is scored once.
- `gate-summary.json`: counts by curriculum, phrase plan and reject stage.
- `rejected-v1.parquet`: written notes that failed a gate (kept for transparency; not part of the set).
- `specs.jsonl`, `specs-summary.json`: answer keys (built by `scribe/stress/specs.py`).
- `cache/`, `requests.jsonl`, `ledger.json`: writer attempts and the request ledger (Nemotron endpoint, concurrency 6).
- `jev-pairs.jsonl`, `jev-answers.jsonl`: Jev gate input and answers (policy `data/scribe/v3/judges/policy.json`).

Rebuild or inspect: `scribe/.venv/bin/python scribe/stress/pipeline.py status`. Code and tests: `scribe/stress/`.
