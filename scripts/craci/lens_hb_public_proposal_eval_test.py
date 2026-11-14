#!/usr/bin/env python3
"""Ground truth must be separate from proposals; test one-to-one IoU scoring."""
import importlib.util
from pathlib import Path
import unittest
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


if __name__=="__main__":
    unittest.main()
