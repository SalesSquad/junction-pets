# Chibi Lens — precise full-frame detection and qualification corrections

Work ID: `CHIBI-LENS-DETECTOR-OPENSET-20261115`. Source branch `codex/chibi-lens-detector-open-set-20261114`, stacked on HomebrewedDB / Apple Vision correction [PR #190](https://github.com/SalesSquad/junction-pets/pull/190). This is **developer research** on public CC0 BOP HomebrewedDB images. It is **not** a live Meta glasses app deployment, new training permission or a claim of ready-to-ship object recognition.

## Actual source problem, separate from the already fixed R-model selector

- The earlier HomebrewedDB source-bound [run #43643014716](https://github.com/SalesSquad/junction-pets/actions/runs/43643014716), after the pure R selection defect fix, recorded known-object correct suggestions **74/93**, total wrongly accepted **3/235**, unknown wrongly accepted **2/142**, accepted precision **74/77 = 96.1%**. This is **ROI classification** on pre-cropped images using BOP ground-truth `bbox_visib` and `mask_visib`, **not end-to-end object detection**.
- The original real public source scene 11 was seen in the earlier baseline-only experiment; the corrected result is exploratory, not an independently sealed field qualification. Calibration and heldout also shared **the same unknown object classes 3,22,23**. This can overstate unknown-class robustness.
- Green CRACI and trained RDS receipts prove execution on pinned source; they cannot prove detector box quality, on-device latency, independent camera generalization or safe parent consent.

## Full-frame correction probes

Three **independent** Apple-native object proposal implementations were prepared as research-only Swift executables. All consume only a public `hb_XX_XXXXXX.png` inside an exact task-owned local Mac scratch directory; **no BOP annotation enters proposal code**:

1. `scripts/craci/LensHBSaliency.swift` uses Apple's `VNGenerateObjectnessBasedSaliencyImageRequest`. On 3 frozen **training** scene-5 frames containing 15 visible BOP-annotated objects in total, it produced 5 generic boxes, with **0/15 objects matched at IoU ≥0.50**. The source-bound local receipt is `docs/CHIBI_LENS_FULL_FRAME_SALIENCY_TRAIN_SMOKE_20261115.json`. Failing localization is deliberately preserved; do NOT claim that 96.1% ROI classification applies to full camera frames.
2. `scripts/craci/LensHBCoreMLProposal.swift` loads Apple's official **YOLOv3TinyFP16** Core ML baseline from <https://developer.apple.com/machine-learning/models/>. This local, research-only candidate was downloaded directly from Apple's model assets, compiled on the verified Mac Mini and is **NOT shipped to Git** (weights are separate, and any redistribution/commercial license requires review). Apple model file SHA-256 `73406178d0f5793d0d5d1e38274acd146a744c2245c9b63a11998a5015925dda`. On the first public train scene-5 frame it returned **zero** `VNRecognizedObjectObservation` proposals: the COCO-pretrained generic detector is not a proven match for these small, domain-specific YCB/HB objects. No extra vendor GPU usage or spending.
3. `scripts/craci/LensHBProposal.swift` tests Apple's `VNGenerateForegroundInstanceMaskRequest` on full public RGB. Its initial variant failed because the returned mask format was not the assumed 8-bit scalar pixel type. The corrected research implementation now decodes Apple's actual **L00f Float32** mask format and refuses unknown pixel buffers. On the first public source frame it returned **one coarse instance box covering several objects, 0/5 matched at IoU ≥0.50**. It is NOT incorporated into product runtime because the actual generated instance boxes fail localization.

`scripts/craci/lens_hb_public_proposal_eval.py` retrieves only bounded ranges of the pinned public HB archive over HTTPS, does not download the entire ~2.35GB source, and computes **one-to-one IoU ≥.50** between output boxes and GT **only after inference**. The code limits all evaluation to source train scene 5, does not inspect previously exposed test scene 11 or use owner/child/iCloud footage; it removes each temporary original RGB frame after inference. Results include proposal count, object recall and proposal precision separately from classification.

## Implemented mandatory full-frame readiness gate

`scripts/craci/lens_field_gate.py` does **not** promote any model or permission. It validates an immutable, licensed, sealed field evidence record. Requirements include:

- *True* GT-free full-frame proposals from a detector, plus a model and source checksum, no training/calibration on the final sealed test.
- At least four distinct heldout physical scenes, two camera/device groups, ≥40 independent frames per scene; known and previously unseen unknown object classes must be represented and **unknown test classes cannot overlap unknown calibration classes**.
- Acceptance must have nonzero real utility; minimum target accepted proposal precision ≥97%, known-object coverage ≥80%, unknown-object false-acceptance ≤1%, and localization recall IoU ≥.5 of ≥90%, each backed by conservative **Wilson 95% bounds**. A per-scene utility/risk minimum prevents one terrible scene from being hidden by pooled averages.
- Any missing rights, privacy admission, model/detector provenance, metric integrity or novel test evidence **fails closed**. Children/family captures, personal ScreenshotContext OCR, event videos and raw Meta glasses footage remain excluded unless independently approved under the appropriate consent and license controls.

`scripts/craci/lens_field_gate_test.py` tests a synthetic valid control and ten negative/edge controls, including zero-acceptance baselines, unknown-class overlap, untrusted GT-assisted proposals, a single previously exposed scene, private media, source drift and statistically inadequate small samples. **11 tests** pass. Synthetic passing controls do not prove real model success.

## Next actual correction before a production claim

The initial Apple generic detectors are not a validated instance-localizer for these objects. The **only defensible next step** is to train or license a detector on public/consented full-frame object detection data, with no ground-truth bounding box used during inference, then evaluate on **new sealed scenes, cameras, and never-calibrated unknown classes**. Use the existing ROI Vision embeddings for downstream classification only after the detector passes its separate proposal-quality gate. Any CRACI/R CPU training is limited to new hypotheses and source-bound evidence; do not repeat old green jobs or loosen thresholds to create a green badge.

No production code/model was replaced, no repository merges were performed in this task, no user private media was copied to cloud, and no new paid execution was authorized or initiated.
