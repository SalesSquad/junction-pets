import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2,numpy as np
import object_pipeline as op
from object_core import extract_objects,calibrate,metrics

class ConcreteReviewRepairs(unittest.TestCase):
    def calibration(self):
        return calibrate([{'label':'normal','score':i/100} for i in range(64)]+[{'label':'anomaly','score':2+i/100} for i in range(40)])
    def test_failed_image_retained_and_later_image_scored(self):
        rgb=np.zeros((400,400,3),np.uint8);cv2.circle(rgb,(200,200),80,(220,180,120),-1);objects=extract_objects(rgb)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'maps').mkdir()
            with patch.object(op,'image_objects',return_value=objects),patch.object(op,'torch_map',side_effect=[RuntimeError('test-only scorer failure'),np.zeros((1,1,256,256),np.float32)]):
                first=op.predict(None,{'image':'a','sha256':'a'*64},out,out)
                second=op.predict(None,{'image':'b','sha256':'b'*64},out,out)
            self.assertIsNone(first['score']);self.assertEqual(second['score'],0.)
            m=metrics([first,second],{'a':'anomaly','b':'normal'},self.calibration())
            self.assertEqual(m['binary']['fn'],1);self.assertEqual(m['binary']['tn'],1);self.assertFalse(m['offline_point_targets_met'])
    def test_failed_export_diagnostics_refused(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);(out/'report.json').write_text(json.dumps({'parity':{'status':'fail'}}));op.legacy.seal(out)
            with self.assertRaisesRegex(ValueError,'Export unqualified'):op.inspect_image(SimpleNamespace(bundle=d))
    def test_notch_and_nearby_detached_fragment_scored(self):
        rgb=np.zeros((400,400,3),np.uint8)
        cv2.rectangle(rgb,(120,120),(280,280),(220,180,120),-1)
        cv2.rectangle(rgb,(190,120),(210,175),(0,0,0),-1)
        cv2.circle(rgb,(294,200),3,(220,180,120),-1)
        objects=extract_objects(rgb);self.assertEqual(len(objects),1);o=objects[0];left,top,side=o['square']
        for x,y in [(200,150),(294,200)]:
            px=int((x-left)*256/side);py=int((y-top)*256/side)
            self.assertTrue(o['mask'][py,px],(x,y))
    def test_nonfinite_map_becomes_explicit_refusal(self):
        rgb=np.zeros((400,400,3),np.uint8);cv2.circle(rgb,(200,200),80,(220,180,120),-1)
        with tempfile.TemporaryDirectory() as d,patch.object(op,'image_objects',return_value=extract_objects(rgb)),patch.object(op,'torch_map',return_value=np.full((1,1,256,256),np.nan)):
            r=op.predict(None,{'image':'bad','sha256':'a'*64},Path(d),Path(d))
            self.assertIsNone(r['score']);self.assertIn('INFERENCE_REFUSAL',r['refusal'])
if __name__=='__main__':unittest.main()
