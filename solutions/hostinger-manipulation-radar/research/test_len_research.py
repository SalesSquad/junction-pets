import unittest, math
from evaluate_len import split_records,metrics,interval,fit,score,threshold
from extract_len import topology
class NumericalOracle(unittest.TestCase):
 def test_confusion_and_wilson(self):
  m=metrics([1,1,1,0,0,0,0],[1,1,0,1,0,0,0])
  self.assertEqual([m[k] for k in ('tp','fp','tn','fn')],[2,1,3,1])
  self.assertAlmostEqual(m['accuracy'],5/7);self.assertAlmostEqual(m['precision'],2/3)
  self.assertAlmostEqual(m['recall'],2/3);self.assertAlmostEqual(m['false_positive_rate'],1/4)
  self.assertAlmostEqual(interval(0,11)[1],.2588329669680318)
  self.assertIsNone(metrics([1,0],[0,0])['precision'])
 def test_split_is_disjoint_and_fixed(self):
  rows=[{'case':str(i).zfill(3),'label':int(i<51)} for i in range(100)]
  parts=split_records(rows)
  self.assertEqual([len(v) for v in parts.values()],[59,19,22])
  self.assertEqual([sum(r['label'] for r in v) for v in parts.values()],[30,10,11])
  self.assertEqual(sum(len({r['case'] for r in v}) for v in parts.values()),100)
  self.assertEqual(parts,split_records(list(reversed(rows))))
 def test_direction_and_concentration(self):
  x,n,m=topology([('a','b'),('b','a'),('c','b')])
  self.assertEqual((n,m),(3,3));self.assertAlmostEqual(x[2],1/3)
  self.assertAlmostEqual(x[5],2/3);self.assertAlmostEqual(x[6],4/9)
  self.assertAlmostEqual(x[10],5/9);self.assertAlmostEqual(x[11],1/3)
 def test_fit_and_calibration(self):
  rows=[{'x':[v]*12,'label':int(v>0)} for v in [-3,-2,-1,1,2,3]]
  model=fit(rows,[0])
  self.assertGreater(score(model,rows[-1]),score(model,rows[0]))
  t,cal=threshold(model,rows)
  self.assertEqual((cal['tp'],cal['fp'],cal['tn'],cal['fn']),(3,0,3,0))
  self.assertTrue(all(math.isfinite(v) for v in model['weights']))

 def test_false_alarm_constraint_is_binding_and_can_abstain(self):
  model={'indices':[0],'means':[0],'scales':[1],'weights':[1],'intercept':0}
  def row(z,y):return {'x':[z]*12,'label':y}
  calibration=[row(2,1),row(0,1)]+[row(z,0) for z in [1.5,1,.5,-.5,-1,-2,-3,-4,-5]]
  t,m=threshold(model,calibration)
  self.assertEqual((m['tp'],m['fn'],m['fp'],m['tn']),(1,1,0,9))
  self.assertGreater(t,score(model,row(1.5,0)))
  t,m=threshold(model,[row(-2,1),row(-1,1)]+[row(z,0) for z in range(9)])
  self.assertEqual((m['tp'],m['fp']),(0,0));self.assertIsNone(m['precision'])
  self.assertGreater(t,1)
 def test_missing_classes_are_undefined(self):
  self.assertIsNone(metrics([0,0],[0,0])['recall'])
  self.assertIsNone(metrics([1,1],[1,1])['false_positive_rate'])
  self.assertIsNone(metrics([],[])['accuracy'])
 def test_actual_release_split_shape(self):
  rows=[{'case':str(i).zfill(3),'label':int(i<53)} for i in range(104)]
  parts=split_records(rows)
  self.assertEqual([len(v) for v in parts.values()],[61,20,23])
  self.assertEqual([sum(r['label'] for r in v) for v in parts.values()],[31,10,12])
 def test_pipeline_deduplicates_and_refuses_conflicting_annotations(self):
  import tempfile,json
  from pathlib import Path
  from evaluate_len import run,FEATURES
  rows=[{'case':str(i).zfill(64),'source_sha256':str(i).zfill(64),'label':int(i<53),'x':[float(i<53)]*12} for i in range(104)]
  rows[1]['source_sha256']=rows[0]['source_sha256'];rows[1]['x']=rows[0]['x'][:]
  data={'features':FEATURES,'records':rows,'source':'fixture-only','source_sha256':'a'*64,'source_bytes':1,'extracted_at':'fixture-only'}
  with tempfile.TemporaryDirectory() as directory:
   source=Path(directory)/'input.json';out=Path(directory)/'out';source.write_text(json.dumps(data))
   import contextlib,io
   with contextlib.redirect_stdout(io.StringIO()):run(source,out)
   report=json.loads((out/'len-evaluation.json').read_text())
   self.assertEqual(report['byte_identical_duplicates_removed'],1)
   self.assertEqual(report['unique_graphs'],103)
   self.assertEqual([v['n'] for v in report['counts'].values()],[61,20,22])
   rows[1]['label']=0;source.write_text(json.dumps(data))
   with self.assertRaisesRegex(ValueError,'Conflicting duplicate labels'):run(source,out)

if __name__=='__main__':unittest.main()

