import unittest,threading,time,json
from unittest.mock import patch
from fractions import Fraction as F
from src.protocol import Peer,wire_fraction,read_fraction,blank
from src.finite_reports import DEFAULT
from src.release_gate import rigorous_finite_certificate

class FiniteProtocolTests(unittest.TestCase):
    def peer(self):
        p=Peer.__new__(Peer);p.cfg=dict(id=0,n=1,a=1.,s=.25,neighbors={},rho_per_release=.1,rho_total=.2,finite_parameters=DEFAULT);p.i=0;p.state='IDLE';p.history=[];p.rho_spent=0.;p.lock=threading.RLock();p.phase={};return p
    def test_abort_prefix_retry_charged(self):
        p=self.peer();p.dispatch({'op':'prepare','epoch':'one'},'control');self.assertEqual(p.rho_spent,.1)
        p.dispatch({'op':'abort'},'control');self.assertEqual(p.history[-1]['rho_spent_cumulative'],.1)
        p.dispatch({'op':'prepare','epoch':'two'},'control');self.assertEqual(p.rho_spent,.2)
        p.dispatch({'op':'release'},'control');self.assertEqual(p.rho_spent,.2)
        p.dispatch({'op':'finish'},'control')
        with self.assertRaises(ValueError):p.dispatch({'op':'prepare','epoch':'three'},'control')
        with self.assertRaises(ValueError):p.dispatch({'op':'prepare','epoch':'one'},'control')
    def test_actual_report_wire_is_exact(self):
        p=self.peer();p.dispatch({'op':'prepare','epoch':'one'},'control');p.dispatch({'op':'release'},'control')
        report=p.dispatch({'op':'report'},'control');self.assertIsInstance(report['z'],F)
        text=json.dumps(report,default=wire_fraction);self.assertEqual(json.loads(text,object_hook=read_fraction),report)
        self.assertNotIn('coins',text);self.assertNotIn('mask',text)
    def test_fixed_width_rationals(self):
        wires=[json.dumps({'z':F(k,1<<20)},default=wire_fraction) for k in [-10**30,-1,0,1,10**30]]
        self.assertEqual(len(set(map(len,wires))),1)
    def test_corrupt_induced_inverse_unequal(self):
        peers=[dict(id=0,a=2.,neighbors={'1':100.},rho_per_release=.25),dict(id=1,a=4.,neighbors={'0':100.},rho_per_release=.25)]
        c=rigorous_finite_certificate(peers);self.assertTrue(c['passed']);self.assertEqual(c['constraints'],4)
        peers[0]['a']=1.
        with self.assertRaises(ValueError):rigorous_finite_certificate(peers)

    def test_shared_incident_bin_and_opposite_sign_complete_reports(self):
        left=self.peer();right=self.peer();right.i=1;right.cfg['id']=1
        left.cfg.update(neighbors={'1':9.},n=2)
        right.cfg.update(neighbors={'0':9.},n=2,s=.5)
        for p in [left,right]:p.dispatch({'op':'prepare','epoch':'fixture'},'control')
        left.metrics=blank();right.metrics=blank()
        left.call=lambda j,msg:right.dispatch(msg,'0')
        coin=(1<<256)*3//5
        with patch('src.protocol.draw',return_value=coin):
            left.dispatch({'op':'setup'},'control')
            self.assertEqual(left.masks[1],right.masks[0])
            left.dispatch({'op':'release'},'control');right.dispatch({'op':'release'},'control')
        # Only complete report outputs are rounded; incident finite bin is known
        # to the endpoint, and no primitive field enters either public report.
        text=json.dumps([left.dispatch({'op':'report'},'control'),right.dispatch({'op':'report'},'control')],default=wire_fraction)
        self.assertNotIn('coins',text);self.assertNotIn('masks',text)
        from src.finite_reports import primitive,sqrt_interval,mul
        local=primitive(coin);expected=F(3,4)+local[0]+local[1]
        self.assertLessEqual(abs(left.z+right.z-expected),F(1,1<<20)+(local[1]-local[0]))

    def test_integer_attempt_limit_precedes_sampling(self):
        p=self.peer();p.cfg.update(max_prepared_attempts=1,rho_total=10.)
        p.dispatch({'op':'prepare','epoch':'one'},'control');p.dispatch({'op':'abort'},'control')
        with self.assertRaises(ValueError):p.dispatch({'op':'prepare','epoch':'two'},'control')
