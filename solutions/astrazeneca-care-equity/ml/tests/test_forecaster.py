import json,subprocess,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import *
from train_forecaster import loss,Forecaster
class Tests(unittest.TestCase):
    def test_windows(self):
        years=np.arange(2000,2026); x=np.tile(years[None,:,None],(3,1,1)); w,y,m=windows(x,years,[0],years)
        for a,(_,t) in zip(w,m): self.assertLessEqual(np.nanmax(a),t)
    def test_pinball_and_sort(self):
        self.assertAlmostEqual(float(loss(torch.zeros(1,1,1,5),torch.ones(1,1,1))),.5)
        model=Forecaster(1,1).eval(); q=model(torch.zeros(2,8,2),torch.zeros(2,dtype=torch.long),torch.zeros(2)); self.assertTrue(bool((q.diff(dim=-1)>=0).all()))
    def test_baselines(self):
        w=np.array([[[i+s] for i in range(8)] for s in (0,10,20)],float)
        np.testing.assert_allclose(baseline(w,[0],'persistence')[:,:,0],[[7],[17],[27]])
        np.testing.assert_allclose(baseline(w,[0],'drift')[:,:,1],[[9],[19],[29]])
        y=np.array([[[8,9]],[[18,19]],[[28,29]]],float); r=fit_ridge(w,y,[0]); self.assertLess(np.max(abs(baseline(w,[0],'ridge',r)-y)),.02)
    def test_probability(self):
        q=np.array([1,2,3,4,5]); self.assertEqual(probability(q,3),.5); self.assertTrue(np.all(np.diff([probability(q,t) for t in range(7)])>=0))
    def test_smoke(self):
        # Deterministic pre-validation variation gives non-degenerate interval evidence.
        # Perfect linear drift is covered separately as an abstention case.
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as d:
            d=Path(d); years=list(range(2000,2026)); p=dict(units=[dict(id='HVA01',category='HYVINVOINTIALUE',name='Toy')],indicators=[dict(id=1,key='screen_breast',isTarget=True)],years=years,values={'1':{'HVA01':{str(y):50+(y-2000)*.5+((y-2000)%3)*.35 for y in years}}},manifest=[])
            save(d/'panel.json',p)
            for script in ['train_forecaster.py','evaluate.py','export_forecasts.py']:
                subprocess.run([sys.executable,str(ROOT/script),'--smoke','--panel',str(d/'panel.json'),'--artifacts',str(d/'artifacts'),'--out',str(d/'forecast.json')],check=True,capture_output=True)
            out=json.loads((d/'forecast.json').read_text()); self.assertEqual(out['schemaVersion'],'care-equity-forecast-v1'); self.assertEqual(set(out['metrics']['screen_breast']['h1']),set(METHODS)); self.assertEqual(out['forecasts']['screen_breast']['HVA01']['h2']['year'],2027)
if __name__=='__main__': unittest.main()
