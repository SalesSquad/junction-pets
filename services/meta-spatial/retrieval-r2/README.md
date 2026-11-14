# Meta Lens: measured retrieval training, R2

Work: `META-LENS-TRAIN-20261114-R2` · 14 November 2026 · [PR #145](https://github.com/SalesSquad/junction-pets/pull/145)

**Actual training and inference completed on one NVIDIA A100 80 GB. The trained image-to-metadata adapter did not pass the product research gate and must not be activated.** NVIDIA Nemotron improved metadata candidate retrieval in this public-catalog benchmark. These are offline findings, not qualification of live glasses, OCR, physical identity, or personal memory.

The code, checkpoints, reports and provenance are retained so a failed product hypothesis remains useful engineering evidence. Four machines and USD 50 were authorized; one machine was sufficient. The provider shutdown and quote-derived cost are recorded in `results/execution-summary.json`. No automatic deployment is part of this change.

## What ran

| Track | Execution | What changed |
|---|---|---|
| SigLIP2 retrieval | Real pixel and metadata encoding; three seeds, 12 epochs each | 196,608 residual projection parameters per seed; frozen image/text backbone |
| Meta DINOv2-small | Real inference on main and alternate catalog images | Frozen image-to-image baseline; no DINO training |
| NVIDIA Nemotron-3-Embed-1B-BF16 | Real BF16 inference; 4,675 text inputs, 294 batches | Frozen metadata embeddings; 512/1,024/2,048-dimensional comparisons |
| Cross-model arbitration | CPU replay of the actual cached embeddings | Fixed reciprocal-rank fusion and disagreement recommendations; no training or camera operation |
| SAM3.1 | Anonymous and existing-account access preflight | Blocked by model approval; no weights downloaded or inference claimed |

Core model execution is bound to commit `6103e6d09141090348ff213d850192b895c6cc8a`. Arbitration and the final numerical unit tests are bound to `9b799ed80acaae0a099e9f84c247e9aeb38deaf8`. The source digests in each report identify the actual executed bytes independently of the final report commit.

### Data and split

[Amazon Berkeley Objects](https://amazon-berkeley-objects.s3.amazonaws.com/index.html), Collins et al., CVPR 2022; [CC BY 4.0 source registry](https://registry.opendata.aws/amazon-berkeley-objects/). The campaign contains **6,000 products, two different image bytes per product, 12,000 view placements and 10,425 unique images overall**. Some related products share images, so “12,000 independent photographs” would be incorrect.

| Partition | Products / queries | Connected families | Role |
|---|---:|---:|---|
| Train | 3,313 | 2,058 | Gradients and hard negatives |
| Development | 727 | 489 | Seed, epoch and frozen-hybrid weight selection |
| Calibration | 620 | 422 | Confidence thresholds |
| Test | 700 | 434 | Heldout campaign report |
| OOD categories | 640 | 259 | Category-shift report |

Dataset SHA256: `bd70decf437dd34dfa9e2866c2110b142d7e746ea66c6f1098ac81deb6cac59c`.

Families connect shared images, matching image bytes, model identifiers and normalized variant titles before splitting. This is a useful duplicate barrier, not proof that every related variant was detected. Foundation-model pretraining overlap with public ABO is **unknown**. A campaign holdout does not establish foundation-model decontamination. Evaluation galleries contain only the corresponding partition: 700 candidates for test and 640 for OOD, not all 6,000 products.

Metadata hints are generated from published product attributes. They are neither observed OCR nor independent natural user requests. The multilingual track uses publisher-provided translated titles, largely German; it does not measure Finnish queries. No ScreenshotContext content, private images, OCR history or personal memory was uploaded.

## Findings that change the product decision

### Visual retrieval

| Method | Test exact-product Recall@1 | OOD exact-product Recall@1 |
|---|---:|---:|
| Frozen SigLIP2 image + metadata hybrid, dev-selected | 56.14% | 42.97% |
| Frozen SigLIP2 image-to-image | 55.71% | 43.28% |
| Frozen DINOv2 image-to-image | 34.57% | 26.25% |
| Frozen SigLIP2 image-to-text | 3.14% | 1.72% |
| Trained image-to-text projection, dev-selected seed 31 | 4.00% | 1.88% |

The learned adapter numerically improves its matching image-to-text baseline by **0.86 percentage points on test and 0.16 on OOD**. That small change is not a statistically established gain. The strong frozen hybrid also receives the gallery image, so comparing 56.14% with 4.00% is a product-choice comparison, not evidence that training destroyed the same visual retrieval task.

The predeclared product gate still fails: the learned method is weaker than the available hybrid, useful coverage is inadequate, and the absent-family upper bound misses the target. The selected adapter accepts zero heldout candidates under its calibrated policy. No threshold was loosened and no favorable test seed substituted after seeing the outcome.

The frozen hybrid is also **not production-qualified**. Its calibrated candidate coverage is only 5.43% on test and 2.50% on OOD, with one wrong accepted candidate in each partition. Ranking quality and a sufficiently reliable automatic answer are different requirements.

### NVIDIA metadata retrieval

Same published attribute hints and target documents, with each model's documented token budget:

| Method | Test Recall@1 | Test Recall@10 | OOD Recall@1 | OOD Recall@10 |
|---|---:|---:|---:|---:|
| BM25 lexical retrieval | 44.29% | 76.86% | 31.88% | 72.19% |
| Nemotron, 512 dimensions | 53.14% | 94.14% | 31.88% | 79.53% |
| Nemotron, 1,024 dimensions | 55.29% | 95.43% | 33.12% | 79.53% |
| Nemotron, full 2,048 dimensions | 54.71% | 95.29% | 33.91% | 80.16% |

The full-width, predeclared Nemotron reference improves test top-10 candidate recall by **18.43 percentage points** over BM25. That makes it a promising candidate generator for metadata lookup. It does not justify automatic exact-item identification: its strict-policy coverage is 2.43% on test and 0.31% on OOD.

The 512-dimensional prefix retains 94.14% test top-10 recall while using one quarter of the full vector's scalar count. This is a measured storage/accuracy tradeoff; vector-index overhead, quantization, device energy and production latency were not benchmarked. The 1,024-dimensional row is an exploratory comparison, not a test-selected production winner.

Published non-English titles provide a separate cross-language check. Full Nemotron exact-product top-1 is 78.93% versus BM25 50.31% on the 318-query test subset, and 62.01% versus 34.10% on the 437-query OOD subset. Those smaller galleries and translated-title queries make these results non-comparable with the main attribute-hint task.

### Disagreement and requesting another view

`arbitration.py` compares a fixed three-component reciprocal-rank fusion (`k=60`) and an additional exact-product agreement condition with the frozen baselines. DINO and SigLIP vectors remain in their own spaces; only candidate ranks are fused. The sources, cache digests, product order and model pins are verified before use.

The worker fixed this protocol without seeing the campaign test metrics. The coordinator had already seen the main experiment, so this is **exploratory follow-up on reused holdouts**, not a fresh confirmatory test. The measured table is in `results/arbitration-summary.json` and the complete report is under `results/arbitration-r2/`.

Risk targets of 1% and 5% and calibration-coverage targets of 10%, 25%, 50% and 75% are separate comparison tracks. Coverage-only policies do not enforce a risk bound. The 5% curve does not replace the original 1% research gate. Thresholds are written before the replay forms test/OOD matrices.

`ask_new_view` is a typed recommendation with `actual_device_action=false`. No second view was captured, no counterfactual quality benefit was observed, and no saved cloud calls are claimed. Model agreement is not truth or physical identity.

The fixed equal-weight RRF itself underperformed: test/OOD top-1 was **18.86% / 14.53%**, versus the frozen hybrid's **56.14% / 42.97%**. Requiring agreement rejected 609 of 700 test queries and 573 of 640 OOD queries before the confidence threshold. Under the 1% calibration target, that agreement policy covered only **0.57% / 0%** of present test/OOD queries and did not establish the required absent-family risk bound. Combining more models is therefore not automatically useful. This fixed fusion should not replace the hybrid; the next view-request idea needs a separate prospective experiment.

### Statistical limitation that matters

Absent-family evaluation removes every gallery member of the query's family and counts **any acceptance across every variant query in that family** as an error event. Present-item errors are counted over all query rows as well. A reviewer found and corrected an earlier first-variant-only error before the real run; the 320-family × 2-variant regression case is retained in the tests.

With 259 OOD families, even **zero** observed absent-family events has a one-sided exact 95% upper bound of approximately **1.15%**. Therefore this OOD sample cannot demonstrate a 1% bound by zero events alone. At least 299 independent families would be needed for that particular zero-event bound; more data and meaningful coverage remain necessary. The campaign preserves this insufficient-evidence result. Family independence is an assumption, and source correlations remain. The bound does not certify conditional error among accepted answers.

## How to use NVIDIA better in the next integration

1. **Use the small NVIDIA embedder for metadata candidates.** Keep BM25 for exact identifiers and explicit attributes. Retrieve a bounded candidate set, then combine independently scored visual, textual and provenance evidence. Reuse encoded metadata instead of sending every camera frame to a large VLM. This campaign supports the candidate-recall hypothesis; it does not measure live call savings.
2. **Make the next image answer a specific uncertainty.** If candidates differ by a label, connector, color or geometry, the phone can ask for that discriminating detail. A future experiment must record the actual second view, randomize the alternative capture policies and measure the resulting answer quality and user effort. Current arbitration supplies recommendations only.
3. **Train against the task the product actually performs.** A next bounded recipe should use one shared visual residual (98,304 parameters), symmetric image-to-image loss, train-only visual hard negatives and a frozen identity baseline at epoch zero. Tune only on train/dev; use new family-disjoint holdouts for confirmation. Do not enlarge the VLM merely to compensate for a mismatched objective.
4. **Use expensive visual reasoning only after the cheap evidence is insufficient.** A Nemotron VLM can propose distinguishing attributes or next observations, while the typed decision layer retains provenance and action authority. No new hosted endpoint or VLM service was launched in this campaign.
5. **Keep user learning local and explicit.** Learn which questions and corrections helped from consented feedback, rather than treating every viewed screen as training material. ScreenshotContext can supply local OCR, window/source context and evidence references. Export only a deliberately selected, redacted evaluation set if separately authorized.

These are engineering proposals, not claims of scientific novelty. Their value must be measured against the strong, cheap frozen baseline.

## Meta, RealityKit, Metal and existing portfolio work

The [Meta Wearables documentation MCP](https://mcp.developer.meta.com/wearables) answered initialization, tool discovery and two documentation searches successfully on 14 November. `results/meta-docs-provenance.json` preserves response digests and source URLs without copying long documentation excerpts. This verifies public documentation access, not developer-account or live-glasses access.

[Device state](https://wearables.developer.meta.com/docs/develop/dat/device-state) exposes battery, charging, worn/hinge status and thermal state before a camera session. [Streaming guidance](https://wearables.developer.meta.com/docs/develop/dat/streaming) documents supported frame-rate choices and adaptive transport quality. Use those signals to defer redundant captures and choose an appropriate stream request. Requested quality is not a delivery guarantee; these device controls were researched, not implemented or measured here. Camera access belongs to the phone's DAT integration; a glasses Web App is a separate presentation/control surface.

**RealityKit** belongs in the phone/Apple spatial presentation layer: render candidate bounds, uncertainty and capture guidance using verified ARKit poses. It does not establish a glasses-to-phone coordinate transform. Apple's [RealityKit performance guidance](https://developer.apple.com/documentation/realitykit/improving-the-performance-of-a-realitykit-app.md) is the reference for keeping that interface responsive.

**Metal/Core ML** are relevant for a future small local encoder or projection, avoiding a cloud round trip for every observation. Apple's [Metal machine-learning passes](https://developer.apple.com/documentation/metal/machine-learning-passes.md) describe GPU-timeline integration. No Metal conversion, Apple runtime performance, or SAM Metal port was executed in this campaign.

Source-reviewed reuse opportunities:

| Existing work | Source pin | Reuse boundary |
|---|---|---|
| ECRE / Valmet Truth Engine | `21f2cc44bb3d05aeebf481a7a5e5c3f878a1222e` | Multi-view prototypes; unknown/ambiguous/single-candidate decisions. A single candidate is not proof of physical identity. |
| Reality Twin | `738a3986bb5e091770f42f848a7872395a2d2b02` | Aligned RGB/depth/intrinsics/camera poses; cheap proposal followed by independent full-evidence checking. Physics weights are not visual retrieval weights. |
| Taimi Native | `fc4beaaf22f1dcfcf8404fe8630cbcd007633ebc` | `SourceReferenceV1` correlation and explicit evidence ownership. Client-supplied references do not confer authority. |
| ScreenshotContext | Existing local app, source considered separately | Local OCR and source metadata for deliberate context retrieval; private data remains local. |

No private portfolio source was copied into this experiment. The earlier ARKit implementation remains its own PR #142; this training change does not claim to merge or activate it.

## Model pins and runtime

| Model | Revision | Weight SHA256 |
|---|---|---|
| `google/siglip2-base-patch16-224` | `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2` | `612923381c76ec5a9bed335d1c48827e3f2e506ac31b044b63b2031fadee6a0b` |
| `facebook/dinov2-small` | `ed25f3a31f01632728cabb09d1542f84ab7b0056` | `ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1` |
| `nvidia/Nemotron-3-Embed-1B-BF16` | `c0c9fea93ea424587517f2c59e20db9f1d6bf615` | `f959c3b04e66b42de280bfb97c140cb7e0bfe25e3ecb0b4464c68a8436b2d04f` |

All three downloaded model weight hashes were verified. Runtime: Python 3.12, PyTorch 2.8.0+cu128, torchvision 0.23.0+cu128, NVIDIA driver 580.178.04, A100-SXM4-80GB. The main environment uses Transformers 4.57.1; Nemotron uses an isolated Transformers 5.5.0 environment. The original environment's package freeze was checked unchanged afterward. Nemotron uses native BF16, SDPA, masked float32 mean pooling and query/passage prefixes; no remote model code is trusted.

NVIDIA Skills catalog `894f2d7dfee49085e84e21c1aad2513bc44a5b6d` informed the design: [retrieval recipes](https://github.com/NVIDIA/skills/tree/894f2d7dfee49085e84e21c1aad2513bc44a5b6d/skills/nemotron-retrieval-recipes) and [CLIP fine-tuning](https://github.com/NVIDIA/skills/tree/894f2d7dfee49085e84e21c1aad2513bc44a5b6d/skills/tao-finetune-clip). Execution was this pinned PyTorch/Hugging Face implementation, not an executed TAO recipe. See the [official NVIDIA model reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-embed-1b) and [current NVIDIA recipe documentation](https://docs.nvidia.com/nemotron/nightly/nemotron/embed/text.html).

The main experiment's approximately 60-second wall time includes 43.73 seconds of frozen image/text encoding and roughly 8.24 seconds across the three small adapter training runs, plus evaluation and output work. It excludes provisioning, downloads and data preparation. Warm CPU projection/search p95 of 0.181 ms excludes the encoder, camera, network and audio. It must not be presented as glasses end-to-end latency.

## Reproduction and evidence

`prepare_data.py`, `train_retrieval.py`, `dino_baseline.py`, `nemotron_metadata.py` and `arbitration.py` expose bounded CLI arguments (`--help`). Install the pinned requirements into isolated environments with the PyTorch CUDA build listed above. Use a task-specific output directory: the runners reject overwriting completed outputs.

The exact execution scripts, source snapshots, dataset seal, feature digests, reports, logs and selected checkpoint manifest were preserved. All three small learned checkpoints are included under `results/checkpoints/` and remain **rejected for deployment**. Large feature caches and public-image data remain in the preserved experiment storage; archive and file digests are recorded, rather than adding large caches to Git.

The numerical verification on the executed arbitration source runs:

```sh
python -m unittest -v test_retrieval test_arbitration
```

Twelve targeted numerical/provenance tests passed on the cloud runtime. Independent review covered the exact core and arbitration digests. The final report commit changes evidence/documentation, so it is not represented as a fresh model-training run. Use `python verify_results.py` to verify the committed artifact digests, model/source bindings and preserved non-deployment decision.

SAM3.1 remains the concrete access blocker: the already-authenticated Hugging Face account's dry-run download returned **access denied; model approval required**. Request/accept access for `facebook/sam3.1` through the existing account before that separate track can run. No credentials were copied to the GPU host and no access control was bypassed.
