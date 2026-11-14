"""Plumbing/security checks; synthetic pixels never establish anomaly quality."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
import pipeline as p


class Boundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        rows=[]
        for i in range(392):
            name=f'{i}.png'; dest=self.root/name
            Image.new('RGB',(8,8),(i%256,i//256,0)).save(dest)
            rows.append(dict(image=name,sha256=p.digest(dest.read_bytes()),bytes=dest.stat().st_size,
                             object='candle',split='train',partition='train',label='normal'))
        normals=sorted(rows[:192],key=lambda r:p.digest(('330|'+r['image']).encode()))
        for i,r in enumerate(normals):r['partition']='train' if i<128 else 'calibration'
        for i,r in enumerate(rows[192:]):
            r.update(split='test',partition='heldout',label='normal' if i<100 else 'anomaly')
        self.manifest=dict(schema=1,dataset='VisA_20220922',category='candle',license='CC-BY-4.0',
                           source_commit=p.SOURCE,split_csv_sha256=p.SPLIT_SHA,samples=rows)
        self.path=self.root/'manifest.json'

    def validate(self):
        self.path.write_text(json.dumps(self.manifest))
        return p.validate_manifest(self.path,self.root)

    def test_valid_plumbing_only(self):
        self.validate()
        self.assertEqual(tuple(p.image_tensor(self.root,self.manifest['samples'][0]).shape),(1,3,128,128))
        self.assertEqual(p.CONFIG['mode'],'REAL_DATA_OFFLINE')
        self.assertEqual(p.CONFIG['robot'],'NO ROBOT')

    def test_duplicates(self):
        self.manifest['samples'][-1]['sha256']=self.manifest['samples'][0]['sha256']
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.validate()

    def test_hash_mismatch(self):
        (self.root/'0.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.validate()

    def test_split_leakage(self):
        self.manifest['samples'][0]['split']='test'
        with self.assertRaisesRegex(ValueError,'split leakage'):self.validate()

    def test_non_normal_calibration(self):
        next(r for r in self.manifest['samples'] if r['partition']=='calibration')['label']='anomaly'
        with self.assertRaises(ValueError):self.validate()

    def test_unsafe_paths(self):
        for name in ('../outside','/etc/passwd','a\\b'):
            with self.assertRaises(ValueError):p.safe_file(self.root,name)
        (self.root/'link').symlink_to(self.root/'0.png')
        with self.assertRaises(ValueError):p.safe_file(self.root,'link')

    def test_nonfinite_thresholds(self):
        for val in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):p.thresholds([val]*64)
            with self.assertRaises(ValueError):p.proposal(1,dict(good=0,binary=val,defect=2))
        t=p.thresholds(list(range(64)))
        self.assertEqual(t,dict(good=57.,binary=60.,defect=63.))
        self.assertEqual(p.proposal(t['good'],t),'hold')
        self.assertEqual(p.proposal(t['defect'],t),'hold')

    def test_corrupt_artifact_refused(self):
        out=self.root/'output';out.mkdir();(out/'model').write_bytes(b'original')
        p.seal(out);p.verify(out)
        (out/'model').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'Corrupted'):p.verify(out)

    def test_output_exclusive_and_outside_checkout(self):
        with self.assertRaises(FileExistsError):p.new_output(self.root)
        with self.assertRaisesRegex(ValueError,'outside'):p.new_output(Path(p.__file__).parent/'forbidden-output')

    def test_evaluation_denominators(self):
        rows=[dict(partition='heldout',label='normal',score=0.,binary_defect=False,proposal='good'),
              dict(partition='heldout',label='anomaly',score=1.,binary_defect=True,proposal='hold')]
        m=p.evaluate(rows)
        self.assertEqual(m['image_auroc'],1.);self.assertEqual(m['coverage'],.5)
        self.assertEqual(m['binary_confusion'],dict(tp=1,fp=0,tn=1,fn=0))


if __name__=='__main__':unittest.main()
