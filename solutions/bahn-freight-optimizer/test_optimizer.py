import copy
import json
import unittest
import optimizer as m

class Safety(unittest.TestCase):
    def setUp(self):
        self.s=m.scenario(11,8,1); self.r=self.s['requests'][0]
        self.r['note']='';self.r['legs'][0]['roadMinutes']=60
        self.r['legs'][0]['delivery']['window'][1]=1600
        self.r['options']['same_day']['deadline']=1600
    def test_integer(self):
        for x in (True,1.2,float('inf'),2**53,-1):
            with self.assertRaises(ValueError): m.integer(x)
        self.assertEqual(m.ceildiv((2**53-1)*99,100),8917127262193582)
    def test_safe_high_fee(self):
        row=m.recommend(self.s)['rows'][0]
        self.assertEqual(row['decision'],'QUOTE')
        self.assertTrue(row['recommendation']['highFee'])
        self.assertGreaterEqual(row['recommendation']['lowerSafetyBps'],9000)
    def test_below_90(self):
        for d in self.s['drivers']:d['reliabilityBps']=8900
        self.assertEqual(m.recommend(self.s)['rows'][0]['decision'],'ABSTAIN')
    def test_deadline_and_cancel(self):
        self.s['now']=self.r['respondBy']
        self.assertEqual(m.recommend(self.s)['rows'][0]['decision'],'ABSTAIN')
        self.s['now']=480;self.r['status']='cancelled'
        self.assertEqual(m.recommend(self.s)['rows'][0]['decision'],'ABSTAIN')
    def test_release_and_notes(self):
        self.r['legs'][0]['releasedAt']=None
        self.assertEqual(m.recommend(self.s)['rows'][0]['decision'],'ABSTAIN')
        self.r['legs'][0]['releasedAt']=480;self.r['note']='<img src=x onerror=alert(1)>'
        self.assertEqual(m.recommend(self.s)['rows'][0]['decision'],'ABSTAIN')
    def test_eligibility(self):
        self.r['legs'][0].update(premium=True,manualGearbox=True)
        for d in self.s['drivers']:d['manualLicence']=False
        self.assertEqual(m.recommend(self.s)['rows'][0]['decision'],'ABSTAIN')
    def test_ev_and_schedule(self):
        self.r['legs'][0].update(electric=True,chargePercent=20,km=201)
        for level in range(1,9):
            self.s['level']=level
            p=m.recommend(self.s)['rows'][0]['recommendation']
            self.assertTrue(p['stops'][0]['withCharging'])
            fees=[x['feeCents'] for x in p['schedule']];self.assertEqual(fees,sorted(fees))
            if level==1:self.assertEqual(len(fees),1)
    def test_tradein_limit(self):
        l=self.r['legs'][0];l['roadMinutes']=361
        other=copy.deepcopy(l);other['pickup']['placeId']='B'
        self.r['legs'].append(other)
        for leg in self.r['legs']:
            for place in ('pickup','delivery'):
                leg[place]['window']=[480,19000];leg[place]['open']=[480,19000]
        p,why=m.plan(self.s,self.r,{'deadline':19000},True)
        self.assertIsNone(p);self.assertIn('12h',why)
    def test_replay_restart(self):
        b=m.Book();e={'seq':1,'kind':'order_won','orderId':'R1','revision':0}
        self.assertTrue(b.event(e));b=m.Book(json.loads(json.dumps(b.state)));self.assertFalse(b.event(e))
        for seq,kind in enumerate(['order_changed','release','gig_expired','order_cancelled'],2):
            b.event({**e,'seq':seq,'kind':kind,'revision':seq})
        self.assertEqual(b.state['orders']['R1']['status'],'cancelled');self.assertFalse(b.state['orders']['R1']['repost'])
    def test_release_costs(self):
        self.assertEqual(m.release_fee(10001,1500),2501)
        self.assertEqual(m.release_fee(10001,1440),5001)
        self.assertEqual(m.release_fee(10001,119),10001)
        self.assertEqual(m.release_fee(10001,10,driver_late=True),0)
        with self.assertRaises(ValueError):m.release_fee(10001,100,started=True)
    def test_offer_caps(self):
        b=m.Book()
        for i in range(3):self.assertTrue(b.offer('D','G',480,8))
        self.assertFalse(b.offer('D','G2',480,8));self.assertFalse(b.offer('D2','G',480,8))
        self.assertFalse(b.offer('D2','G',1400,8));self.assertFalse(b.offer('D2','G',480,2))
    def test_strict_parser(self):
        for value in [True,1.1,2**53]:
            s=copy.deepcopy(self.s);s['requests'][0]['referenceFeeCents']=value
            with self.assertRaises(ValueError):m.validate(s)
        self.r['id']='<script>'
        with self.assertRaises(ValueError):m.validate(self.s)
    def test_deterministic_serializable_no_order(self):
        self.assertEqual(m.recommend(self.s),m.recommend(self.s))
        json.dumps(m.recommend(self.s),allow_nan=False)
        # Empty requests are a valid decision desk, but no-order score is never ranked.
        self.s['requests']=[];self.assertEqual(m.recommend(self.s)['rows'],[])
        self.assertFalse(m.ranked(0,0));self.assertFalse(m.ranked(10,8));self.assertTrue(m.ranked(10,9))

if __name__=='__main__':unittest.main()
