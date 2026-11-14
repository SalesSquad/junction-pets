#!/usr/bin/env python3
"""Focused source provenance, sealed split and class-agnostic IoU regressions."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import lens_hb_detector_data as source
import lens_hb_domain_train as trainer


def fake_manifest(root):
    scenes=[("train",5,40),("train",9,40),("calibration",10,30),("sealed",12,30)]
    rows=[]
    for split,scene,count in scenes:
        for idx in range(count):
            file=f"{split}_s{scene:02d}_f{idx:06}.png"
            (root/file).write_bytes(b"PUBLIC_FAKE_FOR_UNIT_TEST")
            row={
              "file":file,"split":split,"scene_id":scene,
              "frame_id":idx,
              "source_png_sha256":f"{len(rows):064x}",
              "resized_sha256":"0"*64,
              "source_dimensions":[640,480],
              "image_dimensions":[320,240],
              "has_annotations":split!="sealed",
            }
            if split!="sealed":
                row["boxes_xyxy"]=[[10,10,30,30]]
                row["object_class_ids_audit_only"]=[12]
            rows.append(row)
    manifest={
      "schema":"chibi.lens.hb.domain-detector-data.v1",
      "source":"PUBLIC_BOP_HOMEBREWEDDB_CC0",
      "sceneSplits":{"train":[5,9],"calibration":[10],"sealed":[12]},
      "sealedSceneGTRead":False,
      "rawImagesLocalOnly":True,
      "familyMediaUsed":False,"privateOCRUsed":False,
      "samples":rows,
    }
    (root/"manifest.json").write_text(json.dumps(manifest))
    return manifest

class Provenance(unittest.TestCase):
    def test_source_scene_sampling_unique_and_deterministic(self):
        for n in (24,30,40):
            ids=source.sample_ids(340,n)
            self.assertEqual(len(ids),n)
            self.assertEqual(len(set(ids)),n)
            self.assertEqual(ids,source.sample_ids(340,n))
            self.assertTrue(all(0<=v<340 for v in ids))

    def test_sealed_test_labels_are_completely_absent(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            data=fake_manifest(root)
            with patch.object(trainer,"file_sha256",return_value="0"*64):
                recovered,_=trainer.read_manifest(root)
            self.assertEqual(len(recovered["samples"]),140)
            self.assertEqual([x for x in data["samples"] if x["split"]=="sealed"][0]["has_annotations"],False)
            self.assertTrue(all(
                "boxes_xyxy" not in x and "object_class_ids_audit_only" not in x
                for x in recovered["samples"] if x["split"]=="sealed"))

    def test_any_gt_on_sealed_frame_must_refuse_training(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            data=fake_manifest(root)
            next(x for x in data["samples"] if x["split"]=="sealed")["boxes_xyxy"]=[[1,2,5,6]]
            (root/"manifest.json").write_text(json.dumps(data))
            with patch.object(trainer,"file_sha256",return_value="0"*64):
                with self.assertRaisesRegex(ValueError,"Sealed scene annotation"):
                    trainer.read_manifest(root)

    def test_replaced_video_group_and_duplicate_frame_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            data=fake_manifest(root)
            data["samples"][-1]["scene_id"]=10
            (root/"manifest.json").write_text(json.dumps(data))
            with patch.object(trainer,"file_sha256",return_value="0"*64):
                with self.assertRaisesRegex(ValueError,"Missing or substituted"):
                    trainer.read_manifest(root)
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            data=fake_manifest(root)
            data["samples"][-1]["source_png_sha256"]=data["samples"][0]["source_png_sha256"]
            (root/"manifest.json").write_text(json.dumps(data))
            with patch.object(trainer,"file_sha256",return_value="0"*64):
                with self.assertRaisesRegex(ValueError,"Source-frame digest"):
                    trainer.read_manifest(root)

    def test_model_evaluation_is_real_one_to_one_box_matching(self):
        row={"scene":5,"frame":0,
             "predictions":[
                {"score":.91,"xyxy":[0,0,40,30]},
                {"score":.89,"xyxy":[40,0,80,30]},
             ],
             "target_boxes_xyxy":[[0,0,40,30],[40,0,80,30]]}
        matched=trainer.match_predictions([row],.9)
        self.assertEqual(matched["matched"],1)
        self.assertEqual(matched["objects"],2)
        self.assertEqual(matched["proposals"],1)
        all_pred=trainer.match_predictions([row],.5)
        self.assertEqual(all_pred["matched"],2)
        self.assertEqual(all_pred["precisionAtIoU50"],1)


if __name__=="__main__":
    unittest.main()
