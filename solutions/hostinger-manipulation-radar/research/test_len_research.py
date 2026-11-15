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
if __name__=='__main__':unittest.main()
