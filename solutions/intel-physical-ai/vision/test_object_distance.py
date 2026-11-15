import tempfile,unittest
from pathlib import Path
import cv2,numpy as np
from object_core import extract_objects,object_score
import object_pipeline as pipeline

class DistanceBoundedForeground(unittest.TestCase):
    def test_far_background_speck_not_object_evidence(self):
        rgb=np.zeros((400,400,3),np.uint8)
        cv2.rectangle(rgb,(120,120),(280,280),(220,180,120),-1)
        cv2.circle(rgb,(103,103),2,(220,180,120),-1)
        obj=extract_objects(rgb)[0];left,top,side=obj['square']
        x=int((103-left)*256/side);y=int((103-top)*256/side)
        self.assertFalse(obj['mask'][y,x])
        a=np.zeros((1,1,256,256),np.float32);a[0,0,y,x]=1000.
        self.assertEqual(object_score(a,obj['mask']),0.)
    def test_fit_reuse_rejects_wrong_source_pin(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'artifacts.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Fit bundle ledger pin mismatch'):
                pipeline.restore_verified_fit(None,p,'0'*64,'wide_resnet50_2')
if __name__=='__main__':unittest.main()
