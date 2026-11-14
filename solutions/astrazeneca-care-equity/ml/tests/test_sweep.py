import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO
from urllib.parse import parse_qs, urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import ROOT, save, windows, np
from fetch_panel import coverage_failure, fetch
from sweep import select_validation, default_grid

class SweepTests(unittest.TestCase):
    def test_selection_validation_only(self):
        validation={'persistence':2.,'config-00':1.,'config-01':3.}
        self.assertEqual(select_validation(validation),'config-00')
        # The selector accepts only validation scores; arbitrary test scores cannot enter.
        record={'validation':validation,'test':{'config-00':999,'config-01':0}}
        before=select_validation(record['validation'])
        record['test']={'config-00':0,'config-01':999}
        self.assertEqual(before,select_validation(record['validation']))
        self.assertEqual(select_validation({'persistence':1,'config-00':1}),'persistence')
        self.assertIsNone(select_validation({'x':None,'y':float('nan')}))

    def test_grid_and_coverage(self):
        grid=default_grid('base','extended')
        self.assertEqual(len(grid),14)
        self.assertEqual({g['window'] for g in grid},{5,8,12})
        self.assertEqual({g['d_model'] for g in grid},{64,128,256})
        cells={f'KU{i}':{str(y):1. for y in range(2000,2015)} for i in range(250)}
        self.assertIsNone(coverage_failure(cells))
        cells['KU0'].pop('2014')
        self.assertIsNotNone(coverage_failure(cells))
        self.assertIsNotNone(coverage_failure({'FI':{str(y):1 for y in range(2000,2026)}}))


    def test_fetch_deterministic_extra_indicators(self):
        regions=[dict(id=i,category='KUNTA',code=str(i),title={'fi':str(i)}) for i in range(250)]
        metadata=[dict(id=i,classifications={'region':{'values':['Kunta']}}) for i in (9002,3621,9001,9000)]
        def response(request,timeout):
            path=urlparse(request.full_url)
            if path.path.endswith('/regions'): data=regions
            elif path.path.endswith('/indicators'): data=metadata
            else:
                iid=int(parse_qs(path.query)['indicator'][0])
                # First candidate fails the 15-year threshold; second is eligible.
                years=range(2000,2014 if iid==9000 else 2015)
                data=[dict(region=i,year=y,gender='total',value=1.) for i in range(250) for y in years]
            return BytesIO(json.dumps(data).encode())
        with tempfile.TemporaryDirectory() as directory, patch('fetch_panel.urllib.request.urlopen',side_effect=response), patch('fetch_panel.time.sleep'):
            panel=fetch(Path(directory)/'panel.json',extra_indicators=1)
        ids=[i['id'] for i in panel['indicators']]
        self.assertIn(9001,ids); self.assertNotIn(9000,ids); self.assertNotIn(9002,ids)
        self.assertEqual(ids.count(3621),1)
        self.assertFalse(next(i for i in panel['indicators'] if i['id']==9001)['isTarget'])
        self.assertIn(9000,[i['id'] for i in panel['skippedIndicators']])
        self.assertEqual(panel['extraIndicatorsAdded'],1)

    def test_configurable_windows(self):
        years=np.arange(2000,2026); x=years[None,:,None].astype(float)
        for length in (5,8,12):
            w,_,meta=windows(x,years,[0],years,window=length)
            self.assertEqual(w.shape[1],length)
            for row,(_,origin) in zip(w,meta): self.assertLessEqual(np.nanmax(row),origin)

    def test_cpu_sweep_no_test_leakage_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            years=list(range(2000,2026))
            panel=dict(units=[dict(id='HVA01',category='HYVINVOINTIALUE',name='Synthetic county'),
                             dict(id='KU001',category='KUNTA',name='Synthetic municipality')],
                       indicators=[dict(id=1,key='screen_breast',isTarget=True)],
                       years=years,values={'1':{u:{str(y):50+(y-2000)*.5+offset for y in years}
                                               for u,offset in [('HVA01',0),('KU001',5)]}},manifest=[])
            save(d/'panel.json',panel)
            extended=copy.deepcopy(panel)
            extended['indicators'].append(dict(id=2,key='covariate',isTarget=False))
            extended['values']['2']={unit['id']:{str(y):float(y-2000) for y in years} for unit in panel['units']}
            save(d/'extended.json',extended)
            save(d/'grid.json',[dict(window=5,d_model=8,layers=1,heads=2),
                                dict(window=12,d_model=16,layers=1,heads=2,panel=str(d/'extended.json'))])
            command=[sys.executable,str(ROOT/'sweep.py'),'--device','cpu','--epochs','1','--seeds','2',
                     '--panel',str(d/'panel.json'),'--grid',str(d/'grid.json')]
            def run(tag):
                subprocess.run(command+['--artifacts',str(d/tag)],check=True,text=True)
                return json.loads((d/tag/'sweep.json').read_text())
            first=run('first')
            for unit in panel['values']['1'].values():
                unit['2024']=999.; unit['2025']=-999.
            save(d/'panel.json',panel)
            extended['values']['1']=copy.deepcopy(panel['values']['1'])
            save(d/'extended.json',extended)
            second=run('second')
            self.assertEqual(first['validation'],second['validation'])
            self.assertEqual(first['chosen'],second['chosen'])
            self.assertEqual(first['bestTransformer'],second['bestTransformer'])
            methods=second['test']['screen_breast']['methods']
            self.assertEqual(set(methods),{'persistence','drift','ridge',second['bestTransformer']['screen_breast']})
            self.assertEqual(len(second['test']['screen_breast']['seedMAE']),2)
            self.assertTrue((d/'second'/'SWEEP_REPORT.md').exists())
            subprocess.run([sys.executable,str(ROOT/'export_forecasts.py'),'--device','cpu','--sweep',
                            '--artifacts',str(d/'second'),'--out',str(d/'forecast.json')],check=True,text=True)
            output=json.loads((d/'forecast.json').read_text())
            self.assertIn('chosenConfig',output['metrics']['screen_breast'])
            self.assertEqual(set(output['metrics']['screen_breast']['h1']),{'transformer','persistence','drift','ridge'})
            self.assertIn('screen_breast',output['trainedOn']['chosenConfigs'])
            self.assertEqual(output['forecasts']['screen_breast']['HVA01']['h2']['year'],2027)
            second['chosen']['screen_breast']=second['bestTransformer']['screen_breast']
            save(d/'second'/'sweep.json',second)
            subprocess.run([sys.executable,str(ROOT/'export_forecasts.py'),'--device','cpu','--sweep',
                            '--artifacts',str(d/'second'),'--out',str(d/'transformer.json')],check=True,text=True)
            forced=json.loads((d/'transformer.json').read_text())
            self.assertEqual(forced['metrics']['screen_breast']['chosen'],'transformer')
            self.assertTrue(forced['trainedOn']['transformerRefitted'])
            panel['values']['1']['HVA01']['2025']=123.
            save(d/'panel.json',panel)
            denied=subprocess.run([sys.executable,str(ROOT/'export_forecasts.py'),'--device','cpu','--sweep',
                                   '--artifacts',str(d/'second'),'--out',str(d/'denied.json')],capture_output=True,text=True)
            self.assertNotEqual(denied.returncode,0)
            self.assertIn('Panel changed since sweep',denied.stderr)

if __name__=='__main__': unittest.main()
