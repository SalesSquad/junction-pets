# Independent R3 source review

Work ID `META-LENS-ADAPTER-R3-20261114`. Execution source:
`745f2e6597b8d4e398551c37071b9ec662f2aea8`.

The core author, disjoint fresh-data/runtime author, coordinator and independent
read-only reviewer were separate workers. The reviewer changed no source, ran no
training, and did not inspect new calibration/test outcomes before the protocol
and source freeze. Execution receipts identify checks actually performed by the
coordinator; this review is not hosted or signed qualification.

## Findings closed before actual new evaluation

1. **Metadata bridge leakage.** Filtering rows with fewer than two images,
   no English title or unknown category before family grouping could drop a
   connecting record. All valid raw product IDs and aliases now contribute to
   the global graph; acquisition eligibility is applied after exclusion.
   Regression tests ingest actual synthetic raw ABO-format rows.
2. **Ablation loader mismatch.** Replacing `confirmation_candidate` with the
   ablation violated the primary guard. A separate checked `load_ablation`
   preserves the primary selection and uses the same checkpoint validator.
3. **Identity rounding drift.** Re-normalizing identity features could change
   a near tie without learning. Evaluation uses exactly the frozen score matrix
   for identity. Runtime preserves input float32 values and uses the same raw
   matrix multiplication; unit normalization is required rather than repeated.
4. **Selection provenance.** Before fresh scoring, evaluation compares the
   canonical training protocol and exact training source hashes against the
   selection receipt. The evaluation protocol is a separate frozen document.

## Reviewed final source hashes

| File | SHA256 |
| --- | --- |
| prepare_holdout.py | baa43173353705893dec58a7f6ab73c1dfb3c0d1ef8fc965e54ee85fe9c91cb0 |
| test_holdout.py | 228fe1be72eaf937df329c413231e06869a8d2e7c5ddb3d61bed220444051b3a |
| visual_adapter.py | 933de9d32de9782e4b399ef7f5d0a87c94e8389dd65f7ed1eae96a541f0250b1 |
| train_visual.py | 0bb23a98c3d747b87252f72c1b3765a08ecb367e833f0a815c8bb084a1d05b50 |
| test_visual_adapter.py | fcfd362e125763134083c0e43204d2fe6d032992e2d15ede0d81bec1a197a666 |
| evaluation.py | 3bc293ded8d212150a559ea31e8e1e59b2b023567a751ed0e29e6dc2dea5f259 |
| test_evaluation.py | acbe01a6515384116322de1408d1e159577a7d828b91e28ac63354472e683fbf |
| runtime.py | e2bb3096ef062758fc956a81b780f4954bbc7224465cc787bec16a77c406328d |
| test_runtime.py | b3bbeb1095b629a305f7605769831b6faf6433c847b2d1e61baf9b83fa4c5e4d |
| protocol.json | 0900b0d4d96e6787fa9f63a9d0e04af087d65dc33202810a4fd29f1ebefb1756 |

The final read-only source review reported no remaining concrete P1/P2 issue in
this bounded scope. It confirmed FAIL-before-threshold abstention, exact identity
score parity, separate ablation loading, calibration-before-test selection, and
combined family risk accounting across all variants. Training uses only prior
train rows; model selection uses only dev. No source review establishes useful
real-world performance, model pretraining independence, or live device access.

Earlier scratch checks explicitly skipped missing Torch/Safetensors cases.
The real dependency-enabled Mac executor subsequently ran **36/36 checks with no
skips** on the frozen source; `results/logs/focused-tests.log` is the raw evidence.
NumPy warnings are retained in that log; the checks completed successfully.
The actual training histories separately attest finite gradients and weight
updates for all six runs.

## Delivery verifier review

The same read-only reviewer checked the score-event exporter and decisive-metric
verifier, with no remaining P1/P2 finding in that scope:

- `export_results.py`: `79a8c3b277db65fb94c39221695e75ad8bf245b712d7e051dfd1821b8e5fcf74`.
- `verify_results.py`: `cc8d8ef666d60ae54c4e785f232399d27e73ee3a4f1d8a2f123413f65ceaacb1`.

This verifier recomputes the decisive retrieval, coverage, combined-family risk,
paired-bootstrap and product-gate results for eight partition/method pairs.
It does not recompute every descriptive field, including nDCG@10 and each policy
subcounter. A verifier PASS is artifact integrity, not product-gate success.
The review also corrected the README's premature phrase "prospectively confirmed"
to "selected for prospective confirmation" before final result reporting.
