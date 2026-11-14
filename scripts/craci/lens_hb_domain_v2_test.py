#!/usr/bin/env python3
"""Focused v2 sealed-scene evidence and IoU/source regression tests."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import lens_hb_detector_data as preparer
import lens_hb_domain_train as trainer
import lens_hb_domain_v2_eval as v2
import lens_hb_public_proposal_eval as matcher


def fixture():
    frames=[dict(split="sealed",scene_id=13,frame_id=i,
                 source_dimensions=[640,480],source_png_sha256=f"{i+1:064x}")
            for i in range(24)]
    record=dict(schema="chibi.lens.hb.domain-detector-diverse-data.v2",
                plan="diverse",
                sceneSplits=dict(train=list(range(1,11)),calibration=[11],sealed=[13]),
                sourceArchivePointerSHA256=v2.ARCHIVE,
                sealedSceneGTRead=False,samples=frames)
    report=dict(datasetPlan="diverse",datasetSchema=record["schema"],
                manifestSHA256="c"*64,sourceArchivePointerSha256=v2.ARCHIVE,
                initialSourceModelSHA256=v2.INITIAL_MODEL_SHA,
                trainingScenes=v2.TRAIN_SCENES,calibrationScene=11,sealedScene=13,
                sealedSceneGTEverRead=False,sourceOnlyCalibrationDecision=True,
                productionDeploymentAllowed=False,frozenThreshold=.4)
    checkpoint=dict(manifest_sha256="c"*64,dataset_plan="diverse",
                    initial_model_sha256=v2.INITIAL_MODEL_SHA,
                    threshold=.4,trained_steps=80)
    return record,report,checkpoint,"c"*64


class SealedV2(unittest.TestCase):
    def test_valid_new_scene_no_label(self):
        rows=v2.check_frozen_source(*fixture())
        self.assertEqual(len(rows),24)
        self.assertTrue(all("boxes_xyxy" not in x for x in rows))

    def test_fails_on_sealed_labels_or_duplicate_frame(self):
        for mutate in (lambda r:r["samples"][0].update(boxes_xyxy=[[1,2,3,4]]),
                       lambda r:r["samples"][0].update(source_png_sha256=r["samples"][1]["source_png_sha256"]),
                       lambda r:r["samples"][0].update(scene_id=12)):
            record,report,checkpoint,hash_=fixture()
            mutate(record)
            with self.assertRaises(RuntimeError):
                v2.check_frozen_source(record,report,checkpoint,hash_)

    def test_fails_on_source_checkpoint_or_threshold_drift(self):
        for key in ("initial_model_sha256","threshold","manifest_sha256"):
            record,report,checkpoint,hash_=fixture()
            checkpoint[key]=.7 if key=="threshold" else "f"*64
            with self.assertRaises(RuntimeError):
                v2.check_frozen_source(record,report,checkpoint,hash_)

    def test_readonly_per_class_detector_iou(self):
        rows=[{"frame":7,"predictions":[{"score":.9,"xyxy":[50,50,100,100]}]}]
        gt={"7":[{"obj_id":12}]}
        info={"7":[{"visib_fract":1.0,"bbox_visib":[100,100,100,100]}]}
        count,cls,hits,_=v2.report_metrics(rows,gt,info,.4,matcher)
        self.assertEqual(count,{"proposals":1,"matches":1,"objects":1})
        self.assertEqual(dict(cls),{12:1})
        self.assertEqual(dict(hits),{12:1})

    def test_frame_bootstrap_labels_not_field_cert(self):
        result=v2.frame_cluster_intervals(
            [dict(matches=2,objects=4,proposals=3) for _ in range(24)],60)
        self.assertEqual(result["recallIoU50_95pct"],[.5,.5])
        self.assertTrue(result["notMultiSceneFieldCertification"])


class PlanV2(unittest.TestCase):
    def _dataset(self,folder):
        rows=[]
        plan=preparer.PLANS["diverse"]
        for split,scenes in plan["splits"].items():
            for scene in scenes:
                for i in range(plan["frames"][split]):
                    filename=f"{split}_s{scene:02}_f{i:06}.png"
                    (folder/filename).write_bytes(b"TEST_PUBLIC_RGB")
                    row=dict(file=filename,split=split,scene_id=scene,
                             frame_id=i,source_png_sha256=f"{len(rows)+1:064x}",
                             resized_sha256="a"*64,source_dimensions=[640,480],
                             image_dimensions=[320,240],
                             has_annotations=split!="sealed")
                    if split!="sealed":
                        row["boxes_xyxy"]=[[1,2,9,12]]
                        row["object_class_ids_audit_only"]=[12]
                    rows.append(row)
        record=dict(schema=plan["schema"],plan="diverse",
                    source="PUBLIC_BOP_HOMEBREWEDDB_CC0",
                    sourceUrl=preparer.URL,
                    sourceArchivePointerSHA256=preparer.ARCHIVE_SHA,
                    sourceArchiveSizeBytes=preparer.ARCHIVE_BYTES,
                    officialLicense="CC0-1.0",
                    sourceFrameCounts={s:len(plan["splits"][s])*plan["frames"][s]
                                      for s in plan["splits"]},
                    framesPerScene=plan["frames"],
                    sceneSplits={s:list(v) for s,v in plan["splits"].items()},
                    sealedSceneGTRead=False,gtOnlyTrainAndCalibration=True,
                    knownInstanceClassesNotUsedForDetector=True,
                    allVisibleObjectsSingleObjectnessClass=True,
                    rawImagesLocalOnly=True,familyMediaUsed=False,privateOCRUsed=False,
                    samples=rows)
        (folder/"manifest.json").write_text(json.dumps(record))
        return record

    def test_diverse_scene_count_and_heldout_metadata_isolation(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            source=self._dataset(folder)
            with patch.object(trainer,"file_sha256",return_value="a"*64):
                admitted,_=trainer.read_manifest(folder)
            self.assertEqual(len(admitted["samples"]),208)
            self.assertEqual(admitted["sceneSplits"]["sealed"],[13])
            self.assertEqual(sum("boxes_xyxy" in r for r in admitted["samples"]
                                 if r["split"]=="sealed"),0)

    def test_false_archive_or_extra_test_annotations_fail_closed(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            record=self._dataset(folder)
            record["samples"][-1]["boxes_xyxy"]=[[1,2,9,12]]
            (folder/"manifest.json").write_text(json.dumps(record))
            with patch.object(trainer,"file_sha256",return_value="a"*64):
                with self.assertRaisesRegex(ValueError,"Sealed scene annotation"):
                    trainer.read_manifest(folder)
            record=self._dataset(folder)
            record["sourceArchivePointerSHA256"]="b"*64
            (folder/"manifest.json").write_text(json.dumps(record))
            with patch.object(trainer,"file_sha256",return_value="a"*64):
                with self.assertRaisesRegex(ValueError,"Public archive"):
                    trainer.read_manifest(folder)


if __name__=="__main__":
    unittest.main()
