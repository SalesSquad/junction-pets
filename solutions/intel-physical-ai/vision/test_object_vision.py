"""Synthetic structural cases only; they are not detector-quality evidence."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import cv2,numpy as np
from object_core import CaptureRefusal,extract_objects,object_score,calibrate,decide,metrics
import object_pipeline as op

class RiskCalibrationTests(unittest.TestCase):
    def rows(self):return [{'label':'normal','score':i/100} for i in range(64)]+[{'label':'anomaly','score':2+i/100} for i in range(40)]
    def test_labelled_targets(self):
        c=calibrate(self.rows());self.assertTrue(c['feasible']);self.assertGreaterEqual(c['calibration_tp'],38);self.assertLessEqual(c['calibration_fp'],6)
    def test_overlap_is_not_hidden_by_hold(self):
        rows=[{'label':label,'score':1.} for label,n in [('normal',64),('anomaly',40)] for _ in range(n)]
        c=calibrate(rows);self.assertFalse(c['feasible']);self.assertEqual(c['calibration_fp'],64);self.assertEqual(decide(1.,c)['diagnostic'],'hold')
    def test_serialization_and_boundary_ties(self):
        c=calibrate(self.rows());loaded=json.loads(json.dumps(c))
        for t in [c['good'],c['defect']]:
            for s in [np.nextafter(t,-np.inf),t,np.nextafter(t,np.inf)]:self.assertEqual(decide(s,c),decide(s,loaded))
        self.assertFalse(decide(c['binary'],c)['binary_defect'])
    def test_refusal_keeps_calibration_denominators(self):
        r=self.rows();r[-1]['score']=None;c=calibrate(r)
        self.assertEqual(c['counts']['anomaly'],40);self.assertEqual(c['refused']['anomaly'],1);self.assertFalse(c['feasible']);self.assertIsNone(c['binary'])
    def test_nonfinite_rejected(self):
        r=self.rows();r[0]['score']=float('nan')
        with self.assertRaises(ValueError):calibrate(r)
        self.assertEqual(decide(float('nan'),calibrate(self.rows()))['diagnostic'],'hold')
    def test_unknown_not_detection_or_true_negative(self):
        c=calibrate(self.rows());p=[{'image':'a','score':None},{'image':'b','score':None}]
        m=metrics(p,{'a':'anomaly','b':'normal'},c)
        self.assertEqual(m['binary']['fn'],1);self.assertEqual(m['binary']['tn'],0);self.assertFalse(m['offline_point_targets_met']);self.assertEqual(m['hold_rate'],1.)
    def test_truth_membership_exact(self):
        with self.assertRaises(ValueError):metrics([{'image':'x','score':1.}],{'y':'anomaly'},calibrate(self.rows()))

class ObjectBoundaryTests(unittest.TestCase):
    def picture(self):
        x=np.zeros((400,400,3),np.uint8);cv2.circle(x,(200,200),80,(200,180,130),-1);return x
    def test_context_and_map_focus(self):
        objects=extract_objects(self.picture());self.assertEqual(len(objects),1);o=objects[0]
        self.assertEqual(o['tensor'].shape,(1,3,256,256));self.assertEqual(o['mask'].dtype,np.bool_)
        self.assertTrue(np.isfinite(o['tensor']).all());self.assertGreater(o['square'][2],o['bbox'][2])
        a=np.zeros((1,1,256,256),np.float32);a[0,0][~o['mask']]=999.;a[0,0][o['mask']]=3.
        self.assertEqual(object_score(a,o['mask']),3.)
    def test_missing_and_extra_objects_refuse(self):
        with self.assertRaises(CaptureRefusal):extract_objects(np.zeros((400,400,3),np.uint8))
        x=np.zeros((400,400,3),np.uint8)
        for y in [80,200,320]:
            for z in [80,200,320]:cv2.circle(x,(z,y),23,(230,230,230),-1)
        with self.assertRaises(CaptureRefusal):extract_objects(x)
    def test_truncated_capture_refuses(self):
        x=np.zeros((400,400,3),np.uint8);cv2.rectangle(x,(0,100),(160,300),(230,230,230),-1)
        with self.assertRaises(CaptureRefusal):extract_objects(x)
    def test_map_shape_and_nan_refuse(self):
        mask=np.ones((256,256),bool)
        with self.assertRaises(ValueError):object_score(np.zeros((256,256)),mask)
        with self.assertRaises(ValueError):object_score(np.full((1,1,256,256),np.nan),mask)
    def test_manifest_tamper_precedes_model_loading(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'manifest.json').write_text('{"samples":[]}')
            with self.assertRaisesRegex(ValueError,'Frozen input mismatch'):op.validate_inputs(d)
    def test_bundle_tamper_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'model.xml').write_text('old');op.legacy.seal(p);(p/'model.xml').write_text('new')
            with self.assertRaisesRegex(ValueError,'Corrupted artifact'):op.inspect_image(SimpleNamespace(bundle=d))

if __name__=='__main__':unittest.main()
