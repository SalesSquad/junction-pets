#!/usr/bin/env python3
"""Ground truth must be separate from proposals; test one-to-one IoU scoring."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
p=Path(__file__).with_name("lens_hb_public_proposal_eval.py")
spec=importlib.util.spec_from_file_location("hb_proposal_eval",p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Proposals(unittest.TestCase):
    def test_precise_match(self):
        self.assertEqual(module.overlap((10,20,20,30),(10,20,20,30)),1)
        self.assertEqual(module.overlap((10,20,20,30),(100,200,20,30)),0)

    def test_unmatched_proposals_do_not_boost_object_recall(self):
        gt=[(0,0,10,10)]
        candidates=[(0,0,10,10),(0,0,10,10)]
        r=module.evaluate(candidates,gt)
        self.assertEqual(r["matched"],1)
        self.assertEqual(r["unmatchedProposals"],1)
        self.assertEqual(r["objectRecall"],1)
        self.assertEqual(r["proposalPrecision"],.5)

    def test_multiple_gt_objects_cannot_match_one_giant_proposal(self):
        gt=[(0,0,40,30),(40,0,40,30)]
        large=[(0,0,80,30)]
        r=module.evaluate(large,gt)
        self.assertEqual(r["matched"],1)
        self.assertEqual(r["objectRecall"],.5)
        self.assertEqual(r["iouThreshold"],.5)

    def test_large_union_box_fails_iou(self):
        gt=[(0,0,10,10),(15,0,10,10)]
        proposal=[(0,0,80,30)]
        r=module.evaluate(proposal,gt)
        self.assertEqual(r["matched"],0)
        self.assertEqual(r["objectRecall"],0)
        self.assertEqual(r["proposalPrecision"],0)

    def test_no_detected_boxes_is_not_perfect_precision(self):
        r=module.evaluate([],[(1,1,20,20)])
        self.assertIsNone(r["proposalPrecision"])
        self.assertEqual(r["objectRecall"],0)
        self.assertEqual(r["unmatchedObjects"],1)

    def test_unannotated_frame_precision_is_not_invented(self):
        r=module.evaluate([],[])
        self.assertIsNone(r["objectRecall"])
        self.assertIsNone(r["proposalPrecision"])

    def test_malformed_bbox_never_counts(self):
        with self.assertRaises(ValueError):
            module.overlap((0,0,-1,20),(0,0,10,10))

    def test_maximum_cardinality_avoids_greedy_missed_object(self):
        # Proposal 0 prefers GT 0, but GT 1 is also feasible. Proposal 1
        # can ONLY match GT 0. Greedy sorts by IoU and returns 1; correct
        # maximum matching reassigns proposal 0 to GT 1 and returns 2.
        proposals=[(0,0,85,40),(0,0,40,40)]
        annotations=[(0,0,60,40),(45,0,60,40)]
        result=module.evaluate(proposals,annotations,threshold=.35)
        self.assertEqual(result["matched"],2)
        self.assertEqual(result["assignment"],"max_cardinality_bipartite_iou")
        self.assertEqual({(p,g) for p,g,_ in result["matches"]},{(0,1),(1,0)})
        self.assertEqual(result["proposalPrecision"],1)

    def test_no_silent_fractional_pixel_or_nan_threshold(self):
        for box in ((0.2,0,20,30),(True,0,20,30),(-1,0,20,30),
                    (0,0,0,20),(0,0,99999,20)):
            with self.subTest(box=box),self.assertRaises(ValueError):
                module.overlap(box,(0,0,10,10))
        for bad in (float("nan"),float("inf"),-0.1,0,1.1):
            with self.subTest(threshold=bad),self.assertRaises(ValueError):
                module.evaluate([],[],threshold=bad)


class FrameIsolation(unittest.TestCase):
    def _run(self, should_fail):
        processed={"detector_called":False,"annotation_read":False}

        class PublicOnlyArchive:
            def read(self,path,**_):
                if path.endswith("rgb/000000.png"):
                    return bytes.fromhex("89504e470d0a1a0a") + b"FAKE_PUBLIC_IMAGE"
                if path.endswith("scene_gt.json") or path.endswith("scene_gt_info.json"):
                    if not processed["detector_called"]:
                        raise AssertionError("GT was fetched before detector inference")
                    processed["annotation_read"]=True
                    content=(
                        [{"obj_id":12}] if path.endswith("scene_gt.json")
                        else [{"bbox_visib":[0,0,20,20],"visib_fract":1.0}]
                    )
                    return json.dumps({str(i):content for i in range(340)}).encode()
                raise AssertionError("Unexpected source read: "+path)

        def fake_detector(cmd,**_):
            processed["detector_called"]=True
            if should_fail:
                return subprocess.CompletedProcess(cmd,2,stderr="synthetic fail")
            result={"schema":"chibi.lens.hb.vision-proposal.v1",
                    "detector":"AppleObjectnessBasedSaliency",
                    "source":"BOP_HB_CC0_PUBLIC_RGB",
                    "frame":"hb_05_000000.png",
                    "usesGroundTruth":False,"physicalIdentityVerified":False,
                    "actionAuthorized":False,
                    "maskInstances":1,
                    "proposals":[{"x":0,"y":0,"width":20,"height":20}]}
            Path(cmd[-1]).write_text(json.dumps(result))
            return subprocess.CompletedProcess(cmd,0,stdout="ok",stderr="")

        with tempfile.TemporaryDirectory(prefix="chibi-hb-detector-",dir="/private/tmp") as scratch:
            argv=["evaluation","--detector",sys.executable,"--scratch",scratch,
                  "--sample-size","1"]
            with (mock.patch.object(module,"archive_reader",return_value=PublicOnlyArchive()),
                  mock.patch.object(module.subprocess,"run",side_effect=fake_detector),
                  mock.patch.object(sys,"argv",argv)):
                if should_fail:
                    with self.assertRaisesRegex(RuntimeError,"Real detector failure"):
                        module.main()
                else:
                    module.main()
                    report=json.loads((Path(scratch)/"evaluation.json").read_text())
                    self.assertEqual(report["matched"],1)
                    self.assertEqual(report["totalAnnotatedObjects"],1)
                    self.assertEqual(report["metrics"][0]["assignment"],
                                     "max_cardinality_bipartite_iou")
            self.assertFalse((Path(scratch)/"hb_05_000000.png").exists())
            self.assertEqual(processed["annotation_read"],not should_fail)
            self.assertTrue(processed["detector_called"])

    def test_source_gt_is_read_only_after_completed_detector_inference(self):
        self._run(False)

    def test_failed_detector_removes_transient_full_frame_before_gt(self):
        self._run(True)


if __name__=="__main__":
    unittest.main()
