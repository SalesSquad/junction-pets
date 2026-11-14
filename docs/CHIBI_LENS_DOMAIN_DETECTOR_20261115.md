# Chibi Lens — REAL full-frame domain objectness detector

Work ID: `CHIBI-LENS-DOMAIN-DETECTOR-20261115`.
Task-owned branch `codex/chibi-lens-domain-detector-20261115`, stacked explicitly on [PR #208](https://github.com/SalesSquad/junction-pets/pull/208). No production app release or protected merge.

## Gap that this implements

The previous 96.1% accepted-precision result was **classification of externally pre-cropped** RGB objects, and the generic Apple Vision/YOLO proposal smoke on BOP HomebrewedDB (CC0) failed (0/15 objects matched). Neither is an end-to-end camera detector. This task actually **fine-tunes a region proposal network and objectness classifier** using ground-truth bounding boxes for TRAINING only. A full frame at prediction receives no BOP masks/labels/boxes and produces independently measured object proposals.

**Stack:** Torchvision Faster R-CNN MobileNetV3 320-FPN, pretrained on COCO, replace final ROI classifier with background+generic-object and fit RPN/ROI heads on BOP public RGB full frames. Torchvision source is BSD-3-Clause ([upstream](https://github.com/pytorch/vision)). Pretrained weights are fetched only to an authorized Mac task scratch, never checked into GitHub, redistributed, installed in Chibi or automatically licensed for proprietary commercial use. Ultralytics AGPL models are not used.

## Source and scientific split, frozen BEFORE downloading test annotations

Source archive HomebrewedDB/BOP CC0 `hb_val_primesense.zip`. Exact official HF linked SHA-256 `8dd87de6eed1067063081bd4aed3d32a9f0bb6e00887bde78b941eaefc6fec0f` and 2,354,714,266 bytes. Only selected ZIP HTTP byte ranges are retrieved with CRC checks; **the entire archive is not downloaded or independently rehashed**. Public source: <https://bop.felk.cvut.cz/datasets/> and <https://huggingface.co/datasets/bop-benchmark/hb/>.

Pre-registered physical video scene split (never random adjacent video-frame split):
- Train: scenes **5 and 9**, 40 complete RGB frames each, annotated all sufficiently visible BOP objects.
- Calibration: scene **10**, 30 complete RGB frames and annotations; select model score threshold here only. No scene 11 repeated.
- **Sealed evaluation: scene 12**, 30 complete RGB frames. The producer writes **no source GT annotations** for scene 12 and deliberately never reads the scene12 GT/metadata ZIP member. At test time, the inference program MUST first freeze all 30 predictions and their file digest, and only **then** fetch GT/visibility to score IoU50. Failure at any step leaves the test unqualified, never silently retunes.
- All BOP visible objects (known and unknown physical categories) are one **objectness** target. The semantic ROI classifier later decides whether an object looks like 12/15 or is unknown. Class labels are audit-only in the objectness detector. There is no face, person, child or personal object photo in this research.

`scripts/craci/lens_hb_detector_data.py` prepares source frames locally at 320×240, with exact manifest+per-frame SHA. `scripts/craci/lens_hb_domain_train.py` fits a real detection model (bounded train steps; deterministic order), freezes its checkpoint with SHA-256, and calibrates its confidence threshold only on scene 10 using one-to-one IoU matching. `scripts/craci/lens_hb_domain_eval.py` handles the sealed scene 12 after model freeze. The full-image numeric IoU matcher is inherited from PR #208.

## Qualification and deployment boundary

Report true visible object recall@IoU50 and proposal precision@IoU50 separately. A *green training process* is not a usable detector. One previously untouched real physical scene is stronger evidence than reusing scene 11 but is still **not** multi-device or multi-scene field qualification. Production acceptance still requires the existing `lens_field_gate.py`: >=4 truly independent scenes, >=2 devices, *novel unseen unknown objects*, safe risk/coverage and source/rights receipts. No new product permission is conferred. Calibrated ROI accepted precision (74/77) must never be conflated with end-to-end object detection accuracy.

Use a pinned existing local MacBook Pro MPS environment for the actual bounded training; the Mac Mini has <10 GiB disk free. Only task-owned scratch stores image bytes, model weights and calibration/test inference records; **do not commit RGB/PNG, pretrained or trained .pt weights, OCR, family/user/ScreenshotContext media, or credentials**. The repo stores reproducible code and a small evidence JSON with exact source/model/checkpoint SHAs, observed rates, all blockers and model limits. No CRACI jobs or new paid vendor services are needed for this initial training run. Costs for local power are not metered.

**Acceptance:** a detector is not promoted until trained + scene-heldout scored, independent downstream ROI recognition and field privacy gates are satisfied. A failed validation produces a negative source-bound result, not an automatic threshold relaxation or a claim of production readiness.
