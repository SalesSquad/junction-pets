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

## Second hypothesis: scene-diverse warm-start without test reuse (15 November)

The initial *real* full-frame detector (source revision before this section, on MBP) trained 80 optimizer steps from a COCO-pretrained generic Faster R-CNN with public scene 5/9 annotations. On source scene 10 **calibration** it achieved 127/147 true positives at IoU 0.5 (**86.4% recall**) with 127/144 accepted proposals (**88.2% precision**) at a threshold frozen to 0.40. Exact model checkpoint SHA-256: `df9b0155636392be4220248b2cc3b8fe96157edd26e580a423ddd033bf3bb2c6`; source manifest SHA-256: `2197e6c3d0721d6c452a7b4914fe35286ef501ddf76b1424de3a21b1d0591e43`. Its **one-time heldout physical scene 12** result at that same threshold was **76/224 objects (33.93% IoU50 recall)** and **76/163 proposals (46.63% IoU50 precision)**. The heldout predictions were written/frozen to SHA-256 `04989e092cc14b0b2f8320d9737cfb27a7ebb33331adcb8bbedc771bd2cc1376` before scene-12 GT was opened. This is strong evidence of domain shift. Do not retune the original model to scene 12; preserve that negative outcome.

The new *distinct* `--plan diverse` source hypothesis is **pre-registered before inspecting scene 13 ground truth**:
- Train: **10 distinct public physical scenes 1–10**, 16 sampled RGB frames per scene = **160 training images** with source-labelled boxes. Broader object shapes and cameras help mitigate the two-scene failure.
- Calibration: scene **11**, 24 independent RGB frames, boxes opened for threshold selection only (scene 11 was previously assessed in a different study, so its role here is calibration, not novel test).
- One-time sealed evaluation: scene **13**, 24 RGB frames; **no labels/boxes are fetched during preparation, warm-start, training, threshold selection or inference**. GT can be opened only after all 24 predictions and their SHA-256 have been written to immutable task-owned scratch.

The new experiment restores the exact previous **trained** 80-step checkpoint, verifies the original model checkpoint and data-manifest SHA-256, and fits bounded additional RPN/ROI optimizer steps on diverse public scene data. The original trained weights/receipts are retained unchanged; this is **source-bound transfer learning, not 160 from-scratch steps**. No private data, OCR, raw customer photos, secrets, new cloud credentials or CRACI spending are involved.

`scripts/craci/lens_hb_detector_data.py` implements *both* the original immutable scientific split and the new diverse source plan. The reader accepts the exact historical v1 schema (which predated `plan` and `framesPerScene` fields) and requires explicit versioned fields for diverse v2; **no original V1 report/weight/manifest bytes were rewritten**. `scripts/craci/lens_hb_domain_v2_eval.py` separately asserts the new scene/initial-checkpoint/manifest identity, freezes all 24 RGB-only predictions, and *only then* downloads the scene-13 GT via the pinned official BOP HomebrewedDB CC0 ZIP byte-range source. It independently computes IoU50 one-to-one matches, per-object class diagnostics and a within-one-scene frame-cluster bootstrap. It must **never be sold as multi-camera field qualification or recognition/identity authorization**.

Targeted verification: 13/13 v1 backward-compatibility and new v2 sealed-source tests pass, including refusing changed initial weights, threshold drift, duplicate test frame hashes and test GT leaked into the manifest. The source-trained model still needs a new **actual** heldout-scene result to determine whether this distinct hypothesis improved localization. Commit actual model and test SHA details separately after execution, not assumed in advance.
